#!/usr/bin/env python3
"""
Compute side-by-side metrics from markdown_results.json + hindsight_results.json.

Metrics:
  - tokens/query (mean, median, min, max)
  - recall@k for k in {1, 3, 5} per category
  - precision@k for k in {1, 3, 5} per category
  - latency

For adversarial queries (ground_truth = []), correct behavior is ZERO
relevant returns. We invert the metric: precision_adversarial =
1 - (count_returned / k), with 1.0 meaning "perfectly returned nothing".

Output: results/metrics.json + RESULTS.md (writeup) is hand-authored.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """Fraction of relevant items found in top-k."""
    if not relevant:
        return float("nan")  # not meaningful for adversarial
    top_k = retrieved[:k]
    hits = sum(1 for r in relevant if r in top_k)
    return hits / len(relevant)


def precision_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """Fraction of top-k items that were relevant."""
    if not relevant:
        return float("nan")
    top_k = retrieved[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for r in top_k if r in relevant)
    return hits / len(top_k)


def adversarial_correctness(retrieved: list[str], k: int) -> float:
    """For adversarial queries: 1.0 = returned nothing in top-k.
    Markdown returns nothing when no keywords match; Hindsight returns
    its top semantic matches regardless. The metric simply measures
    'fraction of slots correctly left empty'."""
    top_k = retrieved[:k]
    return 1.0 - (len(top_k) / k) if k > 0 else 0.0


def aggregate(per_query: dict, key: str) -> dict:
    """Stats for a numeric field across queries."""
    vals = [v[key] for v in per_query.values() if v.get(key) is not None]
    if not vals:
        return {}
    return {
        "mean": round(statistics.mean(vals), 2),
        "median": round(statistics.median(vals), 2),
        "min": min(vals),
        "max": max(vals),
        "sum": sum(vals),
        "n": len(vals),
    }


def per_category(per_query: dict, fn) -> dict[str, float]:
    """Average a per-query function across queries grouped by category."""
    by_cat: dict[str, list[float]] = defaultdict(list)
    for q in per_query.values():
        v = fn(q)
        if v == v:  # skip NaN
            by_cat[q["category"]].append(v)
    return {
        cat: round(statistics.mean(vs), 3) if vs else None
        for cat, vs in by_cat.items()
    }


def main() -> None:
    md = json.loads((RESULTS / "markdown_results.json").read_text())
    hs = json.loads((RESULTS / "hindsight_results.json").read_text())

    out: dict = {}

    # ---- Token cost ----
    out["tokens"] = {
        "markdown": aggregate(md["per_query"], "input_tokens"),
        "hindsight": aggregate(hs["per_query"], "response_tokens"),
    }

    # ---- Latency (less critical) ----
    out["latency_ms"] = {
        "markdown": aggregate(md["per_query"], "latency_ms"),
        "hindsight": aggregate(hs["per_query"], "latency_ms"),
    }

    # ---- Retrieval metrics by k and category ----
    out["recall_at_k"] = {}
    out["precision_at_k"] = {}
    for k in (1, 3, 5):
        out["recall_at_k"][f"k={k}"] = {
            "markdown": per_category(
                md["per_query"],
                lambda q: recall_at_k(q["retrieved_ids"], q["ground_truth"], k)
            ),
            "hindsight": per_category(
                hs["per_query"],
                lambda q: recall_at_k(q["retrieved_ids"], q["ground_truth"], k)
            ),
        }
        out["precision_at_k"][f"k={k}"] = {
            "markdown": per_category(
                md["per_query"],
                lambda q: precision_at_k(q["retrieved_ids"], q["ground_truth"], k)
            ),
            "hindsight": per_category(
                hs["per_query"],
                lambda q: precision_at_k(q["retrieved_ids"], q["ground_truth"], k)
            ),
        }

    # ---- Adversarial: did either system correctly return nothing? ----
    adv_md = [q for q in md["per_query"].values() if q["category"] == "adversarial"]
    adv_hs = [q for q in hs["per_query"].values() if q["category"] == "adversarial"]
    out["adversarial"] = {
        "markdown": {
            "queries": len(adv_md),
            "avg_returned_at_k=5": round(
                statistics.mean([min(len(q["retrieved_ids"]), 5) for q in adv_md]), 2
            ) if adv_md else None,
            "correctness@5": round(
                statistics.mean([adversarial_correctness(q["retrieved_ids"], 5) for q in adv_md]), 3
            ) if adv_md else None,
        },
        "hindsight": {
            "queries": len(adv_hs),
            "avg_returned_at_k=5": round(
                statistics.mean([min(len(q["retrieved_ids"]), 5) for q in adv_hs]), 2
            ) if adv_hs else None,
            "correctness@5": round(
                statistics.mean([adversarial_correctness(q["retrieved_ids"], 5) for q in adv_hs]), 3
            ) if adv_hs else None,
        },
    }

    # ---- Per-query side-by-side detail (compact) ----
    out["per_query"] = {}
    for qid in md["per_query"]:
        m = md["per_query"][qid]
        h = hs["per_query"][qid]
        out["per_query"][qid] = {
            "query": m["query"],
            "category": m["category"],
            "ground_truth": m["ground_truth"],
            "markdown": {
                "retrieved_ids": m["retrieved_ids"],
                "tokens": m["input_tokens"],
                "recall@1": recall_at_k(m["retrieved_ids"], m["ground_truth"], 1),
                "recall@3": recall_at_k(m["retrieved_ids"], m["ground_truth"], 3),
                "recall@5": recall_at_k(m["retrieved_ids"], m["ground_truth"], 5),
                "precision@5": precision_at_k(m["retrieved_ids"], m["ground_truth"], 5),
            },
            "hindsight": {
                "retrieved_ids": h["retrieved_ids"][:10],
                "raw_count": h["raw_results_count"],
                "tokens": h["response_tokens"],
                "recall@1": recall_at_k(h["retrieved_ids"], h["ground_truth"], 1),
                "recall@3": recall_at_k(h["retrieved_ids"], h["ground_truth"], 3),
                "recall@5": recall_at_k(h["retrieved_ids"], h["ground_truth"], 5),
                "precision@5": precision_at_k(h["retrieved_ids"], h["ground_truth"], 5),
            },
        }

    (RESULTS / "metrics.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"wrote {RESULTS / 'metrics.json'}")

    # Pretty summary to stdout
    print("\n=== TOKEN COST PER QUERY (input load) ===")
    for sys in ("markdown", "hindsight"):
        t = out["tokens"][sys]
        print(f"  {sys:10}  mean={t['mean']:>7}  median={t['median']:>7}  total={t['sum']:>7}")

    print("\n=== LATENCY ===")
    for sys in ("markdown", "hindsight"):
        l = out["latency_ms"][sys]
        print(f"  {sys:10}  mean={l['mean']:>6}ms  median={l['median']:>6}ms")

    print("\n=== RECALL@k by category (mean across queries in category) ===")
    for k in (1, 3, 5):
        print(f"  k={k}")
        for sys in ("markdown", "hindsight"):
            row = out["recall_at_k"][f"k={k}"][sys]
            cells = " ".join(f"{c}:{v}" for c, v in row.items())
            print(f"    {sys:10}  {cells}")

    print("\n=== ADVERSARIAL (lower returned = better) ===")
    for sys in ("markdown", "hindsight"):
        a = out["adversarial"][sys]
        print(f"  {sys:10}  avg_returned@5={a['avg_returned_at_k=5']}  correctness@5={a['correctness@5']}")


if __name__ == "__main__":
    main()
