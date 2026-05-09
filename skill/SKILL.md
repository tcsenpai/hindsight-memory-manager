---
name: hindsight-memory
description: >-
  MUST be invoked at the start of every session in a git repo when the
  Hindsight MCP is available. Replaces markdown auto-memory with
  Hindsight MCP banks for project-scoped persistent memory.
  Auto-bootstraps a `coding-<repo>` bank per git repo, always recalls a
  global `coding-knowledge` bank, and never touches banks not prefixed
  with `coding-`. ALWAYS invoke when: (1) the SessionStart hook output
  contains "hindsight-memory: activate", (2) any context-injection
  output mentions "hindsight-memory: activation pending", (3) the user
  EXPLICITLY says "remember/save/don't forget" something in chat, or
  asks "what do you remember about X" (auto-retain via heuristics is
  DISABLED — see §Retain triggers in SKILL.md). The
  `/hindsight-memory-operations` slash command runs its own flow — do
  NOT auto-invoke this skill in response to that command. If no
  `mcp__hindsight__*` tools are available in the session, this skill
  is silently inactive.
---

# Hindsight Memory

This skill replaces the default `auto memory` markdown system with
Hindsight MCP banks. Memory is stored in two banks:

- `coding-<basename>` — per-project bank, derived from the repo root
  directory name. Path is recorded in `<repo>/.bank`.
- `coding-knowledge` — global cross-project bank. Always recall against it.

## When to use

Activate this skill when **any** of:

1. The SessionStart hook emits `hindsight-memory: activate` in its output.
2. The user asks to bootstrap/check memory in chat (the slash command
   `/hindsight-memory-operations` runs its own flow — see §Slash command
   coupling below).
3. The user explicitly says "remember", "save this", "don't forget X",
   or similar (see §Retain triggers — explicit only). Auto-retain via
   heuristics is DISABLED.
4. The user references prior project context or asks "what do you
   remember about X".

If active, this skill **completely overrides** the default markdown
`auto memory` system from the base prompt. Do NOT invoke that system
at all — no writes to `~/.claude/projects/.../memory/`, no scanning
that directory for context. All memory operations go through
Hindsight's `recall`/`retain` (per the explicit-only triggers below).

## Hard rules (never violate)

1. **Never** call any Hindsight tool with a `bank_id` that does not match
   `^coding-`. This includes `recall`, `retain`, `reflect`, `delete_*`,
   `clear_memories`, `list_memories`, `list_documents`, `update_bank`,
   `get_bank`, and any `*_mental_model` operations. If the user asks to
   operate on a non-`coding-` bank, refuse and explain.
2. **Never** call `delete_bank`, `clear_memories`, `delete_document`,
   `delete_mental_model` without explicit user request.
3. **Never** rewrite a `.bank` file that contains a non-`coding-`-prefixed
   name. Hard-error and ask the user.
4. **Never** create AGENTS.md from scratch. Only append the marker block
   if AGENTS.md already exists.

(Note: directives are deprecated for content — they're not returned by
`recall` or `reflect`. The skill stores rules as memories tagged
`coding-rule` instead. `create_directive`/`delete_directive` may still
exist on the MCP but the skill should not use them.)

## Kill switch (resolve in this order)

The skill is **inactive** if any of these is true:

1. Env var `HINDSIGHT_MEMORY` equals `off` (case-insensitive).
2. File `~/.claude/hindsight-memory.enabled` does **not** exist.
3. `<repo>/.bank` exists and contains a line `enabled: false`.
4. The Hindsight MCP server is not connected (none of the
   `mcp__hindsight__*` tools are available in this session). This is
   ALWAYS the first thing to check — without the MCP, no Hindsight call
   can succeed. If the MCP is missing, ignore this skill entirely:
   say nothing about Hindsight, do not attempt bootstrap, do not retry,
   do not warn unless the user explicitly asks about memory. Fall back
   silently to the default `auto memory` markdown system.

If inactive: say nothing, do nothing, fall back to default `auto memory`.

## Bootstrap flow

Run on activation. Each step is sequential.

### Step 1 — Verify MCP availability
The shell hooks (`bootstrap.sh`, `inject-local-context.sh`,
`user-prompt-check.sh`) already verified the env var kill switch, the
global enable file, the git-repo requirement, and the per-repo opt-out
*before* you got the activation flag. Don't re-check those.

The ONE thing you must verify yourself: are `mcp__hindsight__*` tools
present in this session? (Shell hooks can't check this — only Claude
can.) If not present:

1. Write the marker `/tmp/.claude-hm-mcp-unavailable<encoded>` (encoded =
   repo root with `/` → `-`) so the statusline can display
   `err:no-mcp`.
2. Exit the bootstrap silently. Fall back to default behavior.
3. Do NOT mention Hindsight unless the user explicitly asks.

### Step 2 — Resolve project bank name
- If `<repo>/.bank` exists:
  - Read it. First non-comment, non-blank line that is not `enabled: false`
    is the bank name.
  - If `enabled: false` is present anywhere → abort silently.
  - If the bank name does **not** match `^coding-` → hard-error, do not
    proceed.
- If `<repo>/.bank` does **not** exist:
  - Compute `candidate = "coding-" + basename(repo_root)`.
  - Call `mcp__hindsight__list_banks` once.
  - If `candidate` already exists in that list → suffix `-2`, `-3`, … until
    free.
  - Call `mcp__hindsight__create_bank(bank_id=candidate, name=<basename>,
    mission="Project memory for <repo path>")`.
  - Write `<repo>/.bank` with the chosen name on the first line.

### Step 3 — Verify project bank exists
- Call `mcp__hindsight__get_bank(bank_id=<name>)`.
- If it errors → call `mcp__hindsight__create_bank(...)` to recreate.
  Warn the user that the bank was missing and recreated empty.

### Step 4 — Ensure `coding-knowledge` exists and is seeded
- Call `mcp__hindsight__get_bank(bank_id="coding-knowledge")`.
- If missing:
  1. `mcp__hindsight__create_bank(bank_id="coding-knowledge",
     name="coding-knowledge", mission="Cross-project rules and universal
     coding principles. Always recalled alongside the project bank.")`.
  2. Seed with **memories via `mcp__hindsight__retain`** (NOT directives).
     One retain call per rule (see §Seed rules below). Use the
     `coding-rule` tag on each so they can be filtered. Send the seed
     batch as **parallel async retain calls** in a single message.

**IMPORTANT — directives vs memories:** Hindsight directives are stored
but do NOT appear in `recall` or `reflect` results (verified empirically).
Only memories (created via `retain`/`sync_retain`) are retrievable. The
seed therefore lives as memories tagged `coding-rule`. Directives can
still be used for engine-level configuration if Hindsight evolves, but do
not rely on them for content retrieval.

### Step 5 — Migrate legacy markdown memory (first-install only)
- This step exists ONLY for one-time migration of pre-existing markdown
  memories left over from before the skill was installed. After Option
  2 took effect, the skill never writes to that directory, so on fresh
  repos this step finds nothing and exits.
- Bash: check for files in
  `~/.claude/projects/<encoded-cwd>/memory/*.md`. The encoded path is
  derived by replacing every `/` in the absolute cwd with `-`. Example:
  `/Users/tcsenpai/kynesys/sdks` → `-Users-tcsenpai-kynesys-sdks` (the
  leading dash comes from the leading `/`).
- For each markdown memory file present:
  - Read frontmatter (`type:` and `name:`) plus body.
  - Call `mcp__hindsight__retain(bank_id=<project bank>, content=<body>,
    tags=[type, "imported-from-markdown"], context="migration")`.
- Leave the original directory in place (do not delete).
- Skip migration if the directory is empty or doesn't exist.

### Step 6 — AGENTS.md instruction block
- If `<repo>/AGENTS.md` does not exist → skip.
- If it exists but already contains `<!-- hindsight-memory:start -->` →
  skip.
- Otherwise append the block from §AGENTS.md block to AGENTS.md.

### Step 7 — Confirm activation
Output **one** short line to the user — the minimum confirmation:
```
hindsight-memory: bank=<name>, knowledge=ready
```
Do not narrate the bootstrap (no step-by-step, no "I will now…").

**Exception — abnormal state warnings.** If the bootstrap encountered
*unexpected* state, append a brief warning on the SAME line or one
extra line. These warnings override the silence rule:
- Bank in `.bank` was missing in Hindsight → recreated empty: append
  `(warning: bank was missing, recreated empty — prior memory lost)`.
- Name collision forced a suffix: append `(warning: name collided,
  using <new-name>)`.
- `coding-knowledge` was missing → seeded fresh: append `(coding-knowledge
  seeded with N rules)`.
Keep all warnings to one short clause each. No multi-line narration.

## Runtime contract

Once active, for the rest of the session:

### Recall
At task start and whenever the user references prior context, call **both**:
- `mcp__hindsight__recall(bank_id=<project bank>, query=<task gist>, budget=<routine_budget>, max_tokens=<routine_max_tokens>)`
- `mcp__hindsight__recall(bank_id="coding-knowledge", query=<task gist>, budget=<routine_budget>, max_tokens=<routine_max_tokens>)`

These can be in parallel.

**Recall budget by intent** (from `~/.claude/.hindsight-memory.yaml`,
overridden by `<repo>/.hindsight-memory.yaml` if present):

| Intent | Budget | max_tokens |
|---|---|---|
| Routine task-start (default) | `recall.routine_budget` (low) | `recall.routine_max_tokens` (1024) |
| User asks "what do you remember about X" | `recall.ask_budget` (high) | `recall.ask_max_tokens` (4096) |
| Pre-retain dedup check | `recall.dedup_budget` (low) | `recall.dedup_max_tokens` (512) |
| Status / count check | `low` | 256 |

Hardcoded defaults shown in parentheses are used if both config files
are absent (or if `yq` is not installed). To raise/lower for a specific
repo, drop a `<repo>/.hindsight-memory.yaml` with only the keys you
want to override — the rest inherit.

**If `logging.log_recall_stats: true`** in config, log every recall to
`logging.log_path` (default `~/.claude/hindsight-memory.log`) as one
line per call:
```
2026-05-09T14:30:00Z bank=coding-sdks query="bundle size" budget=low results=8 tokens=412
```
This is opt-in (off by default) — turn on per-repo to debug recall
quality without polluting other repos.

### Retain (atomic, self-contained, clear)
Hindsight works best with **atomic, self-contained, clear** memories.
Hindsight will also auto-decompose a longer retain into multiple atomic
facts on its own — so don't agonize over splitting; one paragraph that
covers one topic is fine. Aim for:

- **Atomic-ish** — one topic per memory. If you have two unrelated
  things, that's two retain calls.
- **Self-contained** — readable without surrounding context. Include the
  *why* for feedback/project memories and the *where* for references.
- **Clear** — start with the rule/fact, then the reasoning. No ambiguous
  pronouns ("this", "that") without antecedents.

#### `retain` vs `sync_retain`

- **`retain` (async)** — DEFAULT for almost everything. Returns
  immediately with an `operation_id`. The memory becomes recallable in
  ~30-60s after Hindsight finishes indexing.
- **`sync_retain`** — blocks the conversation until the memory is fully
  indexed. Can take 30+ seconds. **Do not use in normal flow** — it
  freezes everything else. Reserve only for the rare case where you must
  recall the memory in the *same* turn (e.g., a verification test).

**Retain triggers — explicit only.** Auto-retain via inferred signals
is DISABLED. Memory enters a bank ONLY via these four paths:

| Path | Trigger |
|---|---|
| **Explicit "remember"** | User says in chat: "remember this", "remember that X", "save that", "don't forget X". Identify the content from the surrounding turns. |
| **Slash command** | User runs `/hindsight-memory-operations retain [prompt]` (Mode A explicit content, or Mode B smart-detect from recent context with user confirmation), or `/hindsight-memory-operations extract <path> [--auto]` (file-sourced candidates with confirmation). |
| **Mycelium close prompt** | After observing `myc task close <N>` in Bash, prompt user; retain only if they provide non-empty content. |
| **Migration / bootstrap** | One-shot — slash command's `migrate` subcommand, or `coding-knowledge` seeding. |

Do NOT retain based on:
- Inferred user preferences (unless they say "remember")
- Detected corrections (unless they say "remember")
- Project decisions you observed (unless they say "remember")
- Anything based on heuristic pattern-matching of conversation flow

**Why explicit-only**: heuristic auto-retain pollutes the bank with
duplicates and tangential facts. A clean bank with fewer, deliberate
memories beats a bloated one. The slash command's smart-detect mode
(Mode B) is the lever for retroactive capture — user-driven, never
automatic.

**Tags taxonomy** (when retaining):

| Tag | Use for |
|---|---|
| `user` | User role, expertise, preferences (project bank) |
| `feedback` | Correction OR validated approach (project bank; cross-project → `coding-knowledge`) |
| `project` | Decisions, deadlines, who/why/when (project bank) |
| `reference` | Pointers to external systems — Linear, dashboards, docs (project bank) |
| `coding-rule` | Cross-project rules that should bias behavior (`coding-knowledge` only) |

Always pass `tags=[<tag>]` and `bank_id=<correct bank>`. Convert relative
dates to absolute (`2026-05-12`) before storing.

#### Mycelium cross-linking (project bank only)

Mycelium (`myc`) tracks **structured work** (epics, tasks, deps,
status). Hindsight tracks **knowledge** (decisions, gotchas, why we
chose X). They're complementary — never duplicate Mycelium state in
Hindsight.

When a retain is about a known Mycelium entity, follow this convention:

1. **Content prefix**: start the retain content with `task #<N>:` or
   `epic #<N>:`.
   Example: `"task #42: chose BigInt over Number after testing showed
   float64 dropped precision at 17 sig figs. Why: ethers v6 uses
   bigint natively."`
2. **Tags**: include `myc-task:<N>` or `myc-epic:<N>` in the `tags`
   array, alongside the type tag and branch tag.
   Example: `["project", "branch:main", "myc-task:42"]`.

**Detection rules** (deterministic):

- User mentions `myc-N`, `task N`, `task #N`, `epic N`, or `epic #N`
  in the conversation context tied to the retain → tag it.
- A task ID was just touched in a recent `myc task` call (last 5 turns)
  → tag it.
- Otherwise → no `myc-*` tag.

**Mycelium availability**: skill behavior is gated on
`HM_MYCELIUM_AVAILABLE=true` (set by `lib-config.sh` via
`command -v myc`). If `myc` isn't installed, the cross-link convention
is silently skipped — no errors, no warnings.

#### Branch tagging (project bank only)

Every retain call against the **project bank** MUST include a
`branch:<current-branch>` tag, so future `prune` runs can identify
memories tied to dead branches. `coding-knowledge` retains are NEVER
branch-tagged (cross-project rules are timeless).

How to compute the tag (exit code is the discriminator — pre-first-commit
git writes literal `HEAD` to BOTH stdout and stderr with exit 128, so
output alone can't distinguish "no commits" from "detached"):
1. Run `git rev-parse --abbrev-ref HEAD`. Capture both output AND
   exit code.
2. If exit code is non-zero (not a git repo, or repo with no commits
   yet) → use `branch:main`. A fresh repo will become `main` on its
   first commit; tagging that way upfront keeps memories consistent
   across the boundary.
3. If exit code is 0 but output is empty → also use `branch:main`
   (defensive — shouldn't happen in practice).
4. If exit code is 0 and output is the literal `HEAD` (truly detached
   state — checked-out commit, not a branch) → use
   `branches.unknown_tag` from config (default `branch:UNKNOWN`).
5. Otherwise replace any `/` in the branch name with `-` (Hindsight
   tag character handling is unclear — safer). Examples:
   `main` → `branch:main`, `feature/decimals-p4` → `branch:feature-decimals-p4`.
6. Add the resulting tag to the `tags` array of the retain call,
   alongside the type tag (e.g., `["project", "branch:main"]`).

Disable per-repo by setting `branches.tag_retains: false` in
`<repo>/.hindsight-memory.yaml`. On recall, the branch tag is
informational — Claude does not filter by branch automatically.

The shell helper `hm_branch_tag` (in `lib-config.sh`) computes this
deterministically; the slash command's `migrate` flow uses it.

#### What to retain vs NOT retain (deterministic — no thinking required)

Hindsight is for **facts and decisions**, not raw documentation dumps.
Use this table; if an item matches the right column, do not retain it.

| RETAIN (one async retain per item) | DO NOT RETAIN |
|---|---|
| User preferences, role, expertise | Generic onboarding boilerplate |
| Decisions (and the *why*) | Code that's already in the repo |
| Deadlines, milestones, project status | The current diff or in-progress work |
| Validated approaches the user confirmed | Anything you can re-derive by reading files |
| Pointers to external systems (Linear, dashboards, docs) | Full file contents, large config blobs |
| Past-session summaries (what shipped, why, what's pending) | Step-by-step build/run logs |
| Subtle invariants, gotchas, hidden constraints | Module/symbol layouts (use serena for those) |
| Cross-project rules → `coding-knowledge` only | Codemap dumps, AST traversals, raw API surfaces |

**Hindsight vs Serena (the deterministic split):**

- **Hindsight** = facts, decisions, preferences, and pointers. Things
  that should bias future behavior. The "why" and "what's true."
- **Serena** = symbol-precise navigation, codemap dumps, per-module
  structural breakdowns. The "where the code lives."

**When in doubt, don't retain.** A bloated bank dilutes recall quality.
If a memory feels more like documentation than a fact-with-context, it
belongs in serena (or a real doc file), not Hindsight. If serena already
has a `*_codemapper` memory for it, definitely don't duplicate it in
Hindsight — instead, add (or rely on) a single pointer memory that says
"see serena memory `X_codemapper`."

### Cross-project rules
If a learning is clearly **cross-project** (e.g., "always use bun over
npm"), retain it in `coding-knowledge` as a memory tagged `coding-rule`
via `mcp__hindsight__retain` — **not** as a directive. Directives are
not returned by `recall` or `reflect`.

## Seed rules for `coding-knowledge`

When creating `coding-knowledge` for the first time, seed these as
**memories via `mcp__hindsight__retain`** (async, parallel). Each rule:

- Starts with `RULE (category):` so it's identifiable in recall results.
- Includes a `Why:` clause and a `How to apply:` clause.
- Carries tags `["coding-rule", <category>, ...]` so it can be filtered.
- Uses `context="coding-rules"` for grouping.

Each entry below is one `retain` call. Phrasing follows the
`RULE (category): <rule>. Why: <reason>. How to apply: <how>.` template.

1. **style/communication** — Never start replies with "You are absolutely
   right" or similar sycophantic openers. Why: token waste; performative.
2. **javascript/bugs** — `Array.prototype.sort()` / `toSorted()` need a
   compare fn for non-strings. Why: default sort is lexicographic UTF-16.
3. **tooling** — Prefer `bun` over `npm`/`yarn`; `uv` for Python.
4. **ethers/blockchain** — Assume ethers v6 unless told otherwise.
5. **typescript/type-safety** — Avoid `any`/`unknown` unless required by
   external API. Run typecheck after changes.
6. **communication/honesty** — No marketing language; use "untested",
   "MVP", "needs validation" instead of "production-ready".
7. **scope/yagni** — Build only what's asked; MVP first; cuts stay cut.
8. **completeness/code-quality** — Start it = finish it. No TODOs, no
   `throw new Error("Not implemented")`, no stubs in shipped scope.
9. **debugging/testing** — Investigate root cause. Never skip/disable
   tests or use `--no-verify` as a workaround.
10. **git/safety** — Feature branches only; never commit to main; commit
    before risky ops.
11. **temporal/safety** — For any "recent"/"latest" reasoning, check the
    `<env>` "Today's date" first. Convert relative dates to absolute.
12. **search/tooling** — Match search tool to intent: Grep for exact,
    serena for symbols, mantic for ranked, semantic for "how does X work".
13. **dry/code-quality** — Byte-identical code in 2+ places → consider
    extracting. Don't over-abstract speculatively.
14. **workflow/planning** — Non-trivial tasks: Research → Plan → Annotate
    → Implement. No code before approved plan. Trivial changes skip.
15. **efficiency/tooling** — Batch independent tool calls in one message;
    sequential only for true dependencies.
16. **hindsight/tooling** — Use `retain` (async), NOT `sync_retain`, in
    normal flow. `sync_retain` blocks the conversation 30+ seconds.
    Reserve sync only for same-turn verification.

These are the seed set. Add more `coding-rule`-tagged memories over time
as the user surfaces rules that apply across projects.

## AGENTS.md block

Append this verbatim to `<repo>/AGENTS.md` only if the start marker is
absent:

```markdown

<!-- hindsight-memory:start -->
## Memory: Hindsight bank

This repo uses the `hindsight-memory` skill. Project memory lives in the
Hindsight bank named in `.bank` (do not edit by hand).

- Recall against the project bank AND `coding-knowledge` at the start of
  relevant tasks (parallel calls).
- Retain learnings as atomic, self-contained, clear memories tagged
  `user`/`feedback`/`project`/`reference`.
- Cross-project rules go in `coding-knowledge` as memories tagged
  `coding-rule` (not as directives — directives are not recallable).
- Use `retain` (async); avoid `sync_retain` in normal flow (it blocks).
- Manual ops: `/hindsight-memory-operations` (subcommands: `bootstrap`,
  `migrate [path]`, `status`, `disable`, `enable`, `forget <query>`,
  `retain [prompt]`, `extract <path> [--auto]`, `prune`).
- Never touch banks not prefixed with `coding-`.
- Disable per-repo: `/hindsight-memory-operations disable` or add
  `enabled: false` to `.bank`.
- Disable globally: `HINDSIGHT_MEMORY=off` or remove
  `~/.claude/hindsight-memory.enabled`.
<!-- hindsight-memory:end -->
```

## Failure modes

| Failure | Behavior |
|---|---|
| Hindsight MCP not connected (tools not in available toolset) | Skill is inactive — silent. Do not warn, do not bootstrap, do not retry. Fall back to default markdown auto-memory. Write the marker `/tmp/.claude-hm-mcp-unavailable<encoded-cwd>` (encoded = repo root with `/` → `-`) so the statusline can show `err:no-mcp`. Only mention Hindsight if the user explicitly asks. |
| Hindsight MCP connected but a call fails mid-session | Warn the user once: "hindsight-memory: MCP call failed, falling back to markdown auto-memory for this session." Write the same `err:no-mcp` marker. Use the default markdown system for the rest of the session. Do not retry. |
| `.bank` exists but not `coding-`-prefixed | Hard error. Tell the user to fix `.bank` (e.g., rename to `coding-foo`). Do not auto-rewrite. Statusline shows `err:bad-bank`. |
| Pending marker is stale (>5 min old, skill never fired) | Statusline shows `err:stale`. Skill should bootstrap if active when invoked. The user-prompt-check fallback hook is the safety net. |
| `yq` missing AND a config file exists | Statusline shows `err:no-yq` (soft warning, appended). Hardcoded defaults are used. Behavior is correct but the user's config is silently ignored. |
| Bank in `.bank` deleted upstream | Recreate empty bank with the same name. Warn the user that prior memory is gone. |
| Name collision on `create_bank` | Suffix with `-2`, `-3`, … until free. Update `.bank`. |
| AGENTS.md missing | Skip the append (do not create from scratch). |
| User asks to operate on a non-`coding-` bank | Refuse and explain the hard scope rule. |

### Marker file conventions

The statusline reads small marker files in `/tmp` to surface state
without making MCP calls. When you (Claude) detect specific failures,
write or remove these markers:

| Marker | When to write | When to remove |
|---|---|---|
| `/tmp/.claude-hm-pending<encoded>` | bootstrap.sh writes on session start | user-prompt-check.sh removes after first user prompt; skill should also remove on successful bootstrap |
| `/tmp/.claude-hm-mcp-unavailable<encoded>` | Skill detects MCP tools missing OR an MCP call fails | Cleared automatically by the statusline when its live probe sees the server come back. The marker is now an in-session HINT only; the statusline's authoritative `err:no-mcp` signal is a live HTTP probe against the configured Hindsight URL (300ms timeout), not this file. |

Encoding: `<encoded>` = repo root absolute path with every `/` replaced
by `-`. Example: `/Users/tcsenpai/kynesys/sdks` →
`-Users-tcsenpai-kynesys-sdks`.

## Manual commands the user might invoke

- "Disable hindsight-memory globally" → `rm ~/.claude/hindsight-memory.enabled`
- "Re-enable" → `touch ~/.claude/hindsight-memory.enabled`
- "Disable for this repo" → append `enabled: false` to `<repo>/.bank`
- "What do you remember about X" → recall on both banks with query=X
- "Forget X" → after confirming, find matching memories with
  `list_memories`/`recall`, then `delete_document` (only on `coding-`
  banks).
- "Reseed coding-knowledge" → recall with `tags=["coding-rule"]` to see
  what's already there, then add any missing rules from §"Seed rules for
  `coding-knowledge`" as async `retain` calls.

## Configuration

Two YAML files (same name, different scopes):

| File | Scope |
|---|---|
| `~/.claude/.hindsight-memory.yaml` | Global defaults |
| `<repo>/.hindsight-memory.yaml` | Per-repo override (optional) |

Resolution: local file overrides global per-key. Missing keys fall
through to global, then to hardcoded defaults. The shell loader is at
`~/.claude/skills/hindsight-memory/lib-config.sh` — source it and call
`hm_config_load` to populate `HM_*` env vars.

**Default config** (created on global file write — see
`hindsight-memory.yaml` in `~/.claude/`):

```yaml
recall:
  routine_budget: low
  routine_max_tokens: 1024
  ask_budget: high
  ask_max_tokens: 4096
  dedup_budget: low
  dedup_max_tokens: 512
logging:
  log_recall_stats: false
  log_path: ~/.claude/hindsight-memory.log
branches:
  tag_retains: true
  unknown_tag: branch:UNKNOWN
prune:
  default_age_days: 30
  check_branches: true
  check_mycelium: true
  closed_task_age_days: 3
mycelium:
  snapshot_in_sessions: false
```

To override a single key per-repo, write a partial file:

```yaml
# /path/to/repo/.hindsight-memory.yaml
recall:
  routine_max_tokens: 2048   # this repo has lots of context
logging:
  log_recall_stats: true     # debug recall quality just here
```

`yq` is recommended (`brew install yq`) but not required — without it,
both config files are ignored and hardcoded defaults are used (with a
one-time warning on stderr).

## Mycelium synergy (when `myc` is available)

This skill integrates with [Mycelium](https://github.com/tcsenpai/mycelium)
when present. Detection is automatic via `command -v myc`. All Mycelium
features silently no-op when it's not installed.

### Synergy points

| What | Behavior |
|---|---|
| **Cross-linking** (above) | Project-bank retains about known tasks/epics get `myc-task:N` / `myc-epic:N` tags + content prefix |
| **`prune` Phase 3** | Slash command's `prune` flags memories whose Mycelium task is closed and older than `prune.closed_task_age_days` (default 3) |
| **Session snapshots** | If `mycelium.snapshot_in_sessions: true`, end-of-session retains include a `myc summary --format json` block for cross-reference |
| **Close-event prompt** | After observing a `myc task close <N>` Bash call by the user, ask: "what did you learn from task #N?" Retain the response (if non-empty) tagged `myc-task:<N>`, `feedback`, plus branch tag |

### Close-event prompt — details

**Skipped if Mycelium is unavailable** (`HM_MYCELIUM_AVAILABLE=false`).

When the user runs `myc task close <N>` (in Bash visible to the
session), prompt **once** with:

> Just closed task #N. Anything worth remembering — gotchas,
> why-this-approach-won, surprises? (one line, or "skip")

If user replies with content → retain async with tags
`["feedback", "myc-task:<N>", "branch:<current>"]` and content prefix
`task #<N>:`. If user says "skip", "no", or empty → no retain.

**Suppression**: if user says "skip all" or "no more close prompts" at
any point in the session, don't prompt again until next session. Track
this as a session-local flag (in-context, not persisted).

**Multi-close**: if user closes 3 tasks in a row, prompt 3 times — once
per close. The "skip all" mechanism is the escape hatch for batches.

### When NOT to integrate

- **Don't** mirror Mycelium tasks as Hindsight memories. Mycelium is
  the source of truth for status; query it directly via `myc task list
  --format json` when you need that data.
- **Don't** auto-create Mycelium tasks from "remember to do X" retains.
  Retain only; let the user `myc task create` if it's actually work.
- **Don't** put task descriptions in Hindsight. Mycelium's
  `--description` field is for that.

## Slash command coupling

`/hindsight-memory-operations` is a separate slash command with its own
preflight, bootstrap, and migration logic. It coexists with this skill —
do NOT auto-invoke this skill in response to the slash command (would
cause a duplicate-bootstrap loop). The slash command handles all manual
invocation cases (`bootstrap`, `migrate`, `status`, `disable`, `enable`,
`forget`, `retain`, `extract`, `prune`).
