# Research notes — agentic memory evaluation methodology

Background research for the hindsight-memory vs. markdown auto-memory
benchmark in this directory. Conducted 2026-05-09.

## What Hindsight claims

From the [Hindsight blog](https://hindsight.vectorize.io/blog/2026/03/04/mcp-agent-memory)
and the [Vectorize repo](https://github.com/vectorize-io/hindsight):

- **Architecture**: Not a vector database. Extracts structured facts,
  resolves entities, builds an entity graph, indexes with both sparse
  and dense vectors, and uses a cross-encoder for reranking.
- **Recall pipeline**: Four parallel retrieval strategies — semantic
  search, BM25, entity-graph traversal, temporal filtering — then
  cross-encoder rerank. Default response budget: 4096 tokens.
- **Bank model**: World facts vs. experiences pathways, both
  represented as entities + relationships + time-series.
- **Async indexing**: `retain` is fire-and-forget; new memories take a
  few seconds to be recallable. (Matches the SKILL.md guidance to
  avoid `sync_retain` in normal flow.)
- **Benchmark claim**: SOTA on LongMemEval as of January 2026, with
  third-party reproduction at Virginia Tech's Sanghani Center and The
  Washington Post.

## What "the default" actually is

The "default markdown auto-memory" we're comparing against isn't a
purpose-built memory system — it's Claude Code's per-project
`~/.claude/projects/<encoded-cwd>/memory/` directory. Claude reads
`MEMORY.md` (an index) into context every turn, then opens individual
`*.md` files when their frontmatter `description` looks relevant.

This is closer to what [Letta tested](https://www.letta.com/blog/benchmarking-ai-agent-memory)
(filesystem + agent-driven retrieval) than to a naive "load everything"
baseline. Letta's finding: **a simple file-based agent achieves 74%
on LoCoMo, beating Mem0's 68.5%**. That's a strong incumbent — the
benchmark needs to take it seriously and not strawman the markdown
side.

## Standard methodology

From [LongMemEval](https://arxiv.org/pdf/2410.10813) (ICLR 2025) and
[LoCoMo](https://snap-research.github.io/locomo/):

- **Retrieval metrics**: `Recall@k`, `NDCG@k`. Did the system surface
  a relevant memory in its top-k results?
- **QA metrics**: end-to-end accuracy, judged by GPT-4o (reported 97%
  agreement with human experts on LongMemEval).
- **Critical caveat from the field**: retrieval recall and QA accuracy
  are NOT the same thing — conflating them inflates scores by 20-30
  percentage points. Our test is **retrieval-only** by user request, so
  this report must be careful to frame results that way.
- **Question categories**: single-hop (direct factual), multi-hop
  (chain across sessions), temporal (ordinal/precedence), open-domain
  (external knowledge), adversarial (unanswerable / no relevant
  memory).

## Limitations of retrieval-only benchmarks

Per the [MemoryArena](https://arxiv.org/html/2602.19320) and
[MemoryAgentBench](https://arxiv.org/html/2507.05257v3) papers, the
field is moving away from pure retrieval metrics:

> Models that score near-perfectly on LoCoMo plummet to 40–60% in
> MemoryArena, exposing a deep gap between passive recall and active,
> decision-relevant memory use.

What this means for our test:

- **Our metrics tell us about retrieval quality**, not whether Claude
  would actually answer a downstream question correctly.
- **Token cost comparisons are valid** regardless of QA quality —
  fewer tokens to load the same relevant memory is a real win.
- **We will explicitly NOT claim** that "Hindsight makes Claude a
  better agent." We'll claim "Hindsight retrieves more relevant
  memories with fewer tokens" *if* that's what the data shows.

## Why a small synthetic corpus is fine for a smoke test

LongMemEval has 500 hand-crafted multi-session questions. We have ~50
synthetic atomic facts and ~20 queries. This will not produce
publication-grade numbers. It WILL:

- Catch order-of-magnitude differences (e.g., 10x token reduction).
- Surface obvious failure modes (e.g., Hindsight returns nothing for a
  paraphrased query).
- Validate that the system actually works end-to-end at all.

## What we are NOT testing (and why)

| Not testing | Why |
|---|---|
| End-to-end QA accuracy | Adds LLM noise; user explicitly scoped to retrieval-only |
| Multi-session conversation memory | Out of scope for a project-bank test |
| Selective forgetting | The skill's `prune` flow exists but isn't the question here |
| Async indexing latency | Single confound — we'll wait long enough between retain and recall |
| Cross-bank reasoning | Out of scope; we test one bank |
| Real-world long-tail noise | Synthetic corpus by definition |

## Methodological commitments

1. **Same content, both sides.** The 50 facts go into Hindsight as
   `retain` calls and into a markdown directory as `*.md` files with
   matching frontmatter. No advantage to either via better content.
2. **Markdown side gets a fair retrieval simulation.** Not "Claude
   loads every file" (strawman) — instead, a `MEMORY.md` index +
   filename/frontmatter substring match for the query, then read the
   matched files. This mirrors what Claude actually does.
3. **Token measurement uses the same tokenizer for both sides.**
   `tiktoken` with the `o200k_base` encoding (closest public proxy
   for Claude's tokenizer).
4. **Cleanup is mandatory.** The throwaway `coding-test-eval` bank is
   deleted at the end of every run. The script aborts if it finds a
   pre-existing `coding-test-eval` bank with non-test content.
5. **We report failures, not just wins.** If a query returns nothing
   useful from either system, that's a data point.

## Sources

- [Hindsight blog: The Open-Source MCP Memory Server](https://hindsight.vectorize.io/blog/2026/03/04/mcp-agent-memory)
- [Hindsight Claude Code integration guide](https://hindsight.vectorize.io/guides/2026/05/04/guide-claude-code-memory-with-hindsight)
- [Vectorize Hindsight GitHub](https://github.com/vectorize-io/hindsight)
- [LongMemEval paper (arxiv:2410.10813)](https://arxiv.org/pdf/2410.10813)
- [LoCoMo benchmark](https://snap-research.github.io/locomo/)
- [Letta filesystem memory benchmark](https://www.letta.com/blog/benchmarking-ai-agent-memory)
- [MemoryAgentBench / MemoryArena (arxiv:2507.05257)](https://arxiv.org/html/2507.05257v3)
- [Anatomy of Agentic Memory survey (arxiv:2602.19320)](https://arxiv.org/html/2602.19320)
- [LongMemEval and LoCoMo benchmarks overview](https://www.emergentmind.com/topics/locomo-and-longmemeval-_s-benchmarks)
