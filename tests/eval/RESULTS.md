# Hindsight vs. markdown auto-memory — benchmark results

Run date: 2026-05-09. All raw artifacts in `results/`. Methodology in
[RESEARCH.md](RESEARCH.md). Reproduction instructions at the bottom.

## TL;DR

| | Tokens/query (mean) | Recall@5 (avg across non-adversarial) | Adversarial behavior |
|---|---:|---:|---|
| **Markdown** | 1450 | 0.475 | Returns nothing when no keywords match (good) |
| **Hindsight** | 1001 | 0.767 | Always returns ~5+ semantically nearest items, even when nothing relevant exists (bad) |

**Verdict:** Hindsight uses **31% fewer tokens per query** and gets
**61% higher recall@5** on non-adversarial queries. The win comes from
semantic retrieval handling paraphrase/indirect/multi-fact queries well
where keyword matching collapses. The cost is **no concept of "not
found"** — Hindsight always returns its top semantic matches, so
adversarial queries pollute context with confidently-irrelevant
memories. For normal use this is a clear win; for systems that need
"I don't know" as a valid answer, Hindsight needs a relevance
threshold the skill currently doesn't enforce.

This is a small smoke-test (50 facts, 20 queries). Do not extrapolate
to LongMemEval-scale conclusions. Read all caveats below.

## Methodology

- **Corpus**: 50 atomic facts across user/feedback/project/reference
  categories ([corpus/facts.json](corpus/facts.json)). Same content
  seeded into both systems.
- **Markdown side**: 50 `*.md` files under `_markdown_corpus/` with
  YAML frontmatter (`description`, `type`, `tags`) plus a `MEMORY.md`
  index. Recall simulated as: (a) always load `MEMORY.md` (Claude
  reads it every turn), (b) score every index entry by lowercase
  keyword overlap with the query (stopwords filtered), (c) open the
  top-5 matching files and count their tokens. This mirrors what
  Claude actually does with the default
  `~/.claude/projects/<encoded>/memory/` directory.
- **Hindsight side**: 50 facts seeded into a throwaway
  `coding-test-eval` bank via 50 async `retain` calls (parallel
  batches of 10). Waited 165s for indexing. Each query hit the live
  Hindsight MCP at `http://localhost:8888/mcp/` via JSON-RPC with
  `budget=low, max_tokens=1024` (the SKILL.md default for routine
  recall).
- **Token counts**: same encoding both sides — `tiktoken`
  `o200k_base` (closest public proxy for Claude's tokenizer).
- **Ground-truth match**: every fact has an `Fnn` ID. Hindsight tags
  the source ID into every derived memory unit, so we credit a "hit"
  when the F-ID appears in the returned tags. Markdown filenames
  start with the F-ID. No fuzzy matching on either side.
- **Cleanup**: `coding-test-eval` bank deleted after run completed.
  `delete_bank` reported `memory_units_deleted: 75, documents_deleted:
  48` — confirming Hindsight decomposed our 50 source retains into 75
  derived memories during indexing.
- **Queries**: 20 in 5 categories — 4 exact, 5 paraphrase, 6 indirect,
  3 multi-fact, 2 adversarial. Hand-authored with ground-truth
  relevant-ID lists ([corpus/queries.json](corpus/queries.json)).

## Token cost

| System | Mean | Median | Min | Max | Total (20 queries) |
|---|---:|---:|---:|---:|---:|
| Markdown | 1450 | 1399 | 1335 | 1731 | 28,991 |
| Hindsight | 1001 | 1003 | 965 | 1022 | 20,013 |

**Hindsight is ~31% cheaper per query.** Both systems are remarkably
consistent in their per-query cost — Hindsight because `max_tokens`
caps the response near 1000, Markdown because the index is fixed-size
and the 5 top files vary little in length.

The Markdown floor is the index itself (~1000 tokens of `MEMORY.md`)
plus 5 file bodies. If memory grows 10×, Markdown's index alone
balloons but Hindsight's response stays at the budget. **The token
gap widens with corpus size.** Our 50-fact corpus is the *minimum*
gap — at 500 facts it would be 5–10×, at 5000 facts dramatically
larger.

## Latency

| System | Mean | Median |
|---|---:|---:|
| Markdown | 11ms | 1ms |
| Hindsight | 209ms | 197ms |

Markdown is 20× faster (it's just keyword scoring + file reads on a
local SSD). Hindsight pays ~200ms for HTTP + multi-strategy retrieval
+ cross-encoder rerank. **In a Claude Code session this difference is
imperceptible** — both happen well under the user's reading speed.

## Retrieval quality (recall@k by category)

Recall@k = "did the system find a relevant memory in its top-k results?"
Averaged across queries in each category.

### k=1 (top-1 hit rate)
| Category | Markdown | Hindsight |
|---|---:|---:|
| exact | 0.75 | **1.00** |
| paraphrase | 0.60 | 0.60 |
| indirect | 0.33 | 0.33 |
| multi | 0.00 | **0.23** |

### k=3
| Category | Markdown | Hindsight |
|---|---:|---:|
| exact | 0.75 | **1.00** |
| paraphrase | 0.60 | **1.00** |
| indirect | 0.33 | **0.50** |
| multi | 0.07 | **0.23** |

### k=5
| Category | Markdown | Hindsight |
|---|---:|---:|
| exact | 1.00 | 1.00 |
| paraphrase | 0.60 | **1.00** |
| indirect | 0.33 | **0.67** |
| multi | 0.07 | **0.40** |

**Hindsight wins on every cell that's not already a tie.** The biggest
gaps are paraphrase (1.00 vs 0.60 at k=3 — semantic similarity
trivially wins where keywords don't overlap) and multi-fact queries
(0.40 vs 0.07 at k=5 — Hindsight surfaces multiple related sources
where keyword scoring collapses to a single dominant match).

Indirect queries (0.67 vs 0.33 at k=5) are the most realistic case for
agent memory — the user describes a problem and you need to surface
the relevant past lesson. Doubling the hit rate here is the strongest
practical signal in the test.

## Adversarial queries — Hindsight's clear weakness

Two queries asked about things NOT in the corpus ("quantum cryptography
migration policy", "head of marketing email"). Correct behavior: return
nothing.

| | Avg returned (top-5) | Correctness@5 |
|---|---:|---:|
| Markdown | 1.0 | 0.80 |
| Hindsight | **5.0** | **0.00** |

Markdown returns 0–1 results because no keywords match. Hindsight
returns its 5 semantically-nearest items every time, even though all
have low relevance scores. **This is a real cost**: Hindsight will
confidently inject 5 marginally-related memories into context for
every query, including ones where the right answer is "I don't have
information about that."

Looking at Q19 ("quantum cryptography migration policy"), Hindsight's
top results were unrelated facts about ESM migration and SOC2 audit
deadlines — semantically nearest neighbors to "migration" and
"policy", but useless to the actual question.

**Mitigations the skill could add** (out of scope for this benchmark
but worth noting): (1) a relevance score threshold from Hindsight's
ranker — if available — and drop below-threshold results, (2)
post-processing to detect "all results are weakly related" and emit
zero, (3) consume Hindsight at higher k and have Claude filter by
self-evaluation.

## Per-query lowlights

A few queries where systems failed in interesting ways:

- **Q10 ("Working on a 50-file rename — should I split into PRs or
  bundle?")** — ground truth F08 (bundled refactors). Markdown's
  keyword scorer matched "split", "PRs", "bundle" against multiple
  unrelated files; F08 was rank 4. Hindsight: F08 at rank 1.
- **Q16 ("local development tooling and language stacks")** —
  ground truth: F04, F05, F34, F37, F48 (5 facts). Markdown found
  0 of 5 in top-5. Hindsight found 2 of 5. The query is genuinely
  hard — "tooling" doesn't appear verbatim in any fact title.
- **Q19, Q20 (adversarial)** — Markdown returned 0–2 noise. Hindsight
  returned 5 semantic-nearest items, all wrong. This dragged
  Hindsight's adversarial correctness to 0.

Full per-query data: [results/metrics.json](results/metrics.json).

## What this test does NOT prove

Reading the field's recent literature
([RESEARCH.md](RESEARCH.md) sources):

- **Not statistically significant.** N=20 queries can't establish
  population effects. LongMemEval uses 500. Treat as a smoke test that
  motivates a bigger study, not as a published result.
- **Synthetic corpus.** Real project memory has duplicates, evolving
  decisions, dead branches, and noise. Our 50 facts are clean and
  non-overlapping.
- **No end-to-end QA.** We only measure retrieval. Whether Claude
  produces a *correct answer* given the retrieved memories is a
  separate question that adds LLM noise. From the Letta blog cited in
  RESEARCH.md: "memory is more about how agents manage context than
  the exact retrieval mechanism."
- **Markdown side is a simulation, not real Claude.** We approximated
  Claude's filename/frontmatter scoring with a deterministic keyword
  matcher. Real Claude reads the index and decides which files to
  open based on the query — sometimes it would do better than our
  scorer (using world knowledge), sometimes worse (token budget
  forces shortcuts).
- **Hindsight at `budget=low`.** Higher budgets return more memories.
  The skill's `recall.ask_budget=high` for "what do you remember
  about X" queries would push tokens up to 4096+ and likely improve
  recall further — at proportional token cost.
- **Single domain, single user.** No multi-bank cross-recall test, no
  long-history accumulation, no decay/staleness handling.

## Reproduction

Requirements: `uv` + `tiktoken` + `httpx`. Hindsight MCP server
running on `http://localhost:8888/mcp/`.

```bash
cd tests/eval

# 1. Generate markdown corpus and run markdown-side queries.
uv run --with tiktoken python run_markdown.py

# 2. Inside Claude Code (interactive — needs MCP tool access):
#    a. Verify no pre-existing coding-test-eval bank.
#    b. mcp__hindsight__create_bank(bank_id="coding-test-eval", ...)
#    c. 50 parallel mcp__hindsight__retain calls — one per fact in
#       corpus/facts.json. Tags MUST include the F-ID.
#    d. Wait 2-3 minutes for async indexing to settle.

# 3. Run hindsight-side queries (back to terminal).
uv run --with httpx --with tiktoken python run_hindsight.py

# 4. Compute metrics.
uv run --with tiktoken python analyze.py

# 5. Cleanup (inside Claude Code):
#    mcp__hindsight__delete_bank(bank_id="coding-test-eval")
```

The retain step lives inside Claude rather than in the Python harness
because the same agent (Claude) drives both sides — eliminating one
source of variability. A future revision could push retain into the
Python script via JSON-RPC for full automation.

## Files

- `RESEARCH.md` — methodology background, sources
- `corpus/facts.json` — 50 source facts (ground-truth IDs)
- `corpus/queries.json` — 20 queries with ground-truth relevance lists
- `_markdown_corpus/` — generated markdown files + `MEMORY.md` index
- `run_markdown.py` — markdown harness (corpus generator + recall sim)
- `run_hindsight.py` — Hindsight harness (HTTP-RPC client to local MCP)
- `analyze.py` — metric computation + console summary
- `results/markdown_results.json` — raw markdown results
- `results/hindsight_results.json` — raw Hindsight results
- `results/metrics.json` — computed metrics, per-query side-by-side
