#!/usr/bin/env python3
"""
Markdown auto-memory simulator.

Models the Claude Code default ~/.claude/projects/<encoded-cwd>/memory/
flow: a MEMORY.md index plus per-fact .md files with frontmatter. The
"recall" simulation matches what Claude actually does — read the index
on every turn, then read individual files when their frontmatter
description looks query-relevant.

Usage:
    uv run run_markdown.py        # generates corpus + runs all queries

Output: results/markdown_results.json
"""
from __future__ import annotations

import json
import re
import shutil
import time
from collections import OrderedDict
from pathlib import Path

try:
    import tiktoken
except ImportError:
    raise SystemExit(
        "tiktoken not installed. Run: uv pip install tiktoken"
    )

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
RESULTS = HERE / "results"
MEMORY_DIR = HERE / "_markdown_corpus"

ENC = tiktoken.get_encoding("o200k_base")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "have", "in", "is", "it", "of", "on", "or", "that", "the",
    "to", "was", "what", "when", "where", "who", "why", "how", "do",
    "does", "did", "should", "can", "i", "we", "our", "their", "there",
    "this", "these", "those", "with", "about", "any", "not", "no",
    "would", "could", "will", "have", "had", "about", "us",
}


def tokens(text: str) -> int:
    return len(ENC.encode(text))


def write_markdown_corpus() -> None:
    """Materialize the JSON corpus as a directory of markdown files +
    a MEMORY.md index, mirroring Claude Code's default layout."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    for old in MEMORY_DIR.glob("*.md"):
        old.unlink()

    facts = json.loads((CORPUS / "facts.json").read_text())["facts"]

    index_lines = [
        "# MEMORY",
        "",
        "Index of all memory files. Lines are: `- [Title](file.md) — one-line hook`.",
        "",
    ]
    for f in facts:
        slug = re.sub(r"[^a-z0-9-]+", "-", f["title"].lower()).strip("-")
        fname = f"{f['id'].lower()}-{slug}.md"
        body = (
            f"---\n"
            f"id: {f['id']}\n"
            f"name: {f['title']}\n"
            f"description: {f['title']}\n"
            f"type: {f['type']}\n"
            f"tags: [{', '.join(f['tags'])}]\n"
            f"---\n"
            f"\n"
            f"{f['content']}\n"
        )
        (MEMORY_DIR / fname).write_text(body)
        index_lines.append(f"- [{f['title']}]({fname}) — {f['type']}")

    (MEMORY_DIR / "MEMORY.md").write_text("\n".join(index_lines) + "\n")


def keyword_set(text: str) -> set[str]:
    """Lowercase words >=3 chars, minus stopwords. Crude but matches what
    a substring/keyword reader does in practice."""
    return {
        w for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) >= 3 and w not in STOPWORDS
    }


def score_file_for_query(query: str, file_text: str) -> float:
    """Tally keyword overlap between query and the file's frontmatter +
    body. We score against the file's title/description AND a short
    body window — what Claude effectively does after opening the file."""
    qk = keyword_set(query)
    if not qk:
        return 0.0
    fk = keyword_set(file_text)
    overlap = len(qk & fk)
    return overlap / max(len(qk), 1)


def parse_index(index_text: str) -> list[tuple[str, str]]:
    """Return list of (filename, hook_text) from MEMORY.md."""
    out = []
    for line in index_text.splitlines():
        m = re.match(r"-\s+\[([^\]]+)\]\(([^)]+)\)\s+—\s+(.*)", line)
        if m:
            title, fname, hook = m.groups()
            out.append((fname, f"{title} {hook}"))
    return out


def fact_id_from_filename(fname: str) -> str:
    m = re.match(r"(f\d+)-", fname)
    return m.group(1).upper() if m else ""


def run_query(query: str, index_text: str, k_max: int = 5) -> dict:
    """Simulate Claude's recall flow:
    1. Index is always in context (counted as input tokens).
    2. Score every index entry by keyword overlap with the query.
    3. Open the top-k_max files (by score). Count their tokens.
    4. Return the top-k_max file IDs as the "retrieved" set, in score
       order. This is what Claude effectively surfaces.
    """
    t0 = time.perf_counter()
    index_tokens = tokens(index_text)

    entries = parse_index(index_text)
    scored = [
        (fname, score_file_for_query(query, hook))
        for fname, hook in entries
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    nonzero = [(f, s) for f, s in scored if s > 0]
    to_open = nonzero[:k_max] if nonzero else []

    body_tokens_total = 0
    retrieved_ids = []
    for fname, score in to_open:
        body = (MEMORY_DIR / fname).read_text()
        body_tokens_total += tokens(body)
        retrieved_ids.append(fact_id_from_filename(fname))

    latency_ms = (time.perf_counter() - t0) * 1000

    return {
        "retrieved_ids": retrieved_ids,
        "scores": [s for _, s in to_open],
        "input_tokens": index_tokens + body_tokens_total,
        "index_tokens": index_tokens,
        "body_tokens": body_tokens_total,
        "files_opened": len(to_open),
        "latency_ms": round(latency_ms, 2),
    }


def main() -> None:
    write_markdown_corpus()
    queries = json.loads((CORPUS / "queries.json").read_text())["queries"]
    index_text = (MEMORY_DIR / "MEMORY.md").read_text()

    out: dict = OrderedDict()
    out["_meta"] = {
        "system": "markdown",
        "encoding": "o200k_base",
        "memory_dir": str(MEMORY_DIR),
        "k_max": 5,
        "notes": (
            "Simulates Claude reading MEMORY.md every turn (always in "
            "context) plus opening up to k_max files whose index entries "
            "share keywords with the query. Approximates what Claude "
            "actually does with the default ~/.claude/projects/.../memory/ "
            "directory. See RESEARCH.md for fairness notes."
        ),
    }
    out["per_query"] = {}
    for q in queries:
        out["per_query"][q["id"]] = {
            "query": q["query"],
            "category": q["category"],
            "ground_truth": q["relevant"],
            **run_query(q["query"], index_text),
        }

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "markdown_results.json").write_text(
        json.dumps(out, indent=2)
    )
    print(f"wrote {RESULTS / 'markdown_results.json'}")
    print(f"  queries: {len(queries)}")
    print(f"  total input tokens (sum across queries): "
          f"{sum(v['input_tokens'] for v in out['per_query'].values())}")


if __name__ == "__main__":
    main()
