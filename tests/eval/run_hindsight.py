#!/usr/bin/env python3
"""
Hindsight recall harness.

Talks directly to the local Hindsight MCP HTTP endpoint (default
http://localhost:8888/mcp/) using JSON-RPC 2.0 over Streamable HTTP.
Runs all queries from corpus/queries.json against the seeded
coding-test-eval bank, captures returned memory IDs (extracted from
F-tagged metadata), token counts, and latency.

This script does NOT seed the corpus — that step runs interactively
from inside Claude (one retain per fact, parallel batches) so the
caller can confirm async indexing has completed.

Usage:
    uv run --with httpx --with tiktoken run_hindsight.py

Output: results/hindsight_results.json
"""
from __future__ import annotations

import json
import re
import time
import uuid
from collections import OrderedDict
from pathlib import Path

import httpx
import tiktoken

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
RESULTS = HERE / "results"
BANK_ID = "coding-test-eval"
MCP_URL = "http://localhost:8888/mcp/"
ENC = tiktoken.get_encoding("o200k_base")

F_TAG = re.compile(r"^F\d+$")


def tokens(text: str) -> int:
    return len(ENC.encode(text))


def fact_id_from_tags(tags: list[str]) -> str:
    """Pull the F\\d+ tag — that's the source-corpus ID."""
    for t in tags or []:
        if F_TAG.match(t):
            return t
    return ""


def mcp_call(client: httpx.Client, method: str, params: dict, sess: dict) -> dict:
    """JSON-RPC over Streamable HTTP. The MCP spec uses SSE responses for
    streaming, but a single JSON-RPC response works too with the right
    Accept header. We grab the first JSON event and return it."""
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params,
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if sess.get("session_id"):
        headers["mcp-session-id"] = sess["session_id"]

    r = client.post(MCP_URL, json=payload, headers=headers, timeout=30.0)
    r.raise_for_status()

    # Capture session ID from initialize response
    if "mcp-session-id" in r.headers and not sess.get("session_id"):
        sess["session_id"] = r.headers["mcp-session-id"]

    # Response can be plain JSON or SSE. Detect by content-type.
    ct = r.headers.get("content-type", "")
    if "text/event-stream" in ct:
        for line in r.text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        raise RuntimeError(f"No data event in SSE response: {r.text[:500]}")
    return r.json()


def initialize(client: httpx.Client, sess: dict) -> None:
    """MCP initialize handshake."""
    resp = mcp_call(client, "initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "eval-harness", "version": "1.0"},
    }, sess)
    if "error" in resp:
        raise RuntimeError(f"initialize failed: {resp['error']}")
    # MCP requires a notifications/initialized after initialize
    payload = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "mcp-session-id": sess["session_id"],
    }
    client.post(MCP_URL, json=payload, headers=headers, timeout=10.0)


def recall(client: httpx.Client, sess: dict, query: str,
           budget: str = "low", max_tokens: int = 1024) -> tuple[list[dict], float]:
    t0 = time.perf_counter()
    resp = mcp_call(client, "tools/call", {
        "name": "recall",
        "arguments": {
            "bank_id": BANK_ID,
            "query": query,
            "budget": budget,
            "max_tokens": max_tokens,
        },
    }, sess)
    latency_ms = (time.perf_counter() - t0) * 1000

    if "error" in resp:
        raise RuntimeError(f"recall failed: {resp['error']}")
    # Tool result is wrapped: result.content[0].text is a JSON string
    result = resp["result"]
    text_content = result["content"][0]["text"]
    parsed = json.loads(text_content)
    return parsed.get("results", []), latency_ms


def run_query(client: httpx.Client, sess: dict, query: str,
              budget: str, max_tokens: int) -> dict:
    results, latency_ms = recall(client, sess, query, budget, max_tokens)

    # Dedup retrieved IDs by F-tag (one source fact may produce N memories;
    # we credit a hit on first appearance and report per-source coverage).
    seen_fids = []
    for r in results:
        fid = fact_id_from_tags(r.get("tags", []))
        if fid and fid not in seen_fids:
            seen_fids.append(fid)

    # Token cost: sum of all returned memory text fields. This is what
    # Claude would have to load into context to use the recall result.
    response_tokens = sum(tokens(r.get("text", "")) for r in results)

    return {
        "retrieved_ids": seen_fids,
        "raw_results_count": len(results),
        "response_tokens": response_tokens,
        "latency_ms": round(latency_ms, 2),
        "budget": budget,
        "max_tokens": max_tokens,
    }


def main() -> None:
    queries = json.loads((CORPUS / "queries.json").read_text())["queries"]

    out: dict = OrderedDict()
    out["_meta"] = {
        "system": "hindsight",
        "encoding": "o200k_base",
        "bank_id": BANK_ID,
        "mcp_url": MCP_URL,
        "budget": "low",
        "max_tokens": 1024,
        "notes": (
            "Calls Hindsight's recall tool over JSON-RPC HTTP. The "
            "retrieved_ids list is deduplicated by F-tag — Hindsight "
            "auto-decomposes source retains into multiple memory units "
            "but they all share the original F\\d+ tag. response_tokens "
            "counts the full text content of all returned memories (what "
            "Claude would load into context). raw_results_count is the "
            "number of distinct memory units returned, NOT capped by "
            "max_tokens — Hindsight's max_tokens is a soft hint, not a "
            "hard truncation (verified empirically: 30+ results came "
            "back at max_tokens=1024)."
        ),
    }

    with httpx.Client() as client:
        sess: dict = {}
        initialize(client, sess)
        out["per_query"] = {}
        for q in queries:
            r = run_query(client, sess, q["query"], "low", 1024)
            out["per_query"][q["id"]] = {
                "query": q["query"],
                "category": q["category"],
                "ground_truth": q["relevant"],
                **r,
            }
            print(f"  {q['id']}: {len(r['retrieved_ids'])} unique sources, "
                  f"{r['raw_results_count']} memory units, "
                  f"{r['response_tokens']} tokens, "
                  f"{r['latency_ms']:.0f}ms")

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "hindsight_results.json").write_text(json.dumps(out, indent=2))

    total = sum(v["response_tokens"] for v in out["per_query"].values())
    print(f"\nwrote {RESULTS / 'hindsight_results.json'}")
    print(f"  queries: {len(queries)}")
    print(f"  total response tokens (sum across queries): {total}")


if __name__ == "__main__":
    main()
