# /hindsight-memory-operations

Operate on the Hindsight memory bank for this repo. Coexists with the
description-based invocation of the `hindsight-memory` skill.

## Preflight (always run first)

1. **MCP availability**: if no `mcp__hindsight__*` tools are loaded in
   this session, abort and tell the user: "Hindsight MCP not available
   — install/enable it first." Do NOT proceed.
2. **Git repo**: if `git rev-parse --show-toplevel` fails, abort with
   "Not in a git repo — `/hindsight-memory-operations` requires one."
3. **Activation**: if `~/.claude/hindsight-memory.enabled` is missing
   OR `HINDSIGHT_MEMORY=off`, tell the user the kill switch is on and
   ask if they want to enable it.

## Configuration

Source the config loader at the start of every subcommand:

```bash
source "$HOME/.claude/skills/hindsight-memory/lib-config.sh"
hm_config_load
```

This populates `HM_*` env vars (recall budgets, branch tag, log path,
prune age, etc.). Resolution: `<repo>/.hindsight-memory.yaml` overrides
`~/.claude/.hindsight-memory.yaml` overrides hardcoded defaults. See
SKILL.md §Configuration for the schema.

The current branch tag is `hm_branch_tag` (e.g., `branch:main`,
`branch:UNKNOWN`). All retains in this command against the project
bank MUST include this tag in their `tags` array.

## Argument parsing

Read `$ARGUMENTS`. Subcommands (first whitespace-separated token):

- (empty) → `bootstrap`
- `bootstrap` → run the skill's bootstrap flow (idempotent)
- `migrate` → autodetect & migrate common dirs
- `migrate <path>` → migrate a specific directory
- `status` → show bank info + recall stats (if logging enabled)
- `disable` → add `enabled: false` to `<repo>/.bank`
- `enable` → remove `enabled: false` line from `<repo>/.bank`
- `forget <query>` → list matches, ask user, delete on confirm
- `prune` → interactive cleanup of stale memories (project bank only)
- `retain [prompt]` → explicit retain. With prompt: store that text.
  Without: smart-detect candidates from recent conversation context
- `extract <path> [--auto]` → analyze a file/folder/repo and propose
  memories worth retaining (judgment-driven, file-sourced cousin of
  `retain` Mode B)

If the subcommand is unknown, list these and ask which the user meant.

---

## Subcommand: `bootstrap`

Run the full bootstrap flow from `SKILL.md` (Steps 1–7). It's idempotent
— safe to run any time. Report what changed (new bank? new `.bank`?
AGENTS.md updated? coding-knowledge seeded?).

---

## Subcommand: `migrate` (autodetect)

Scan the repo root for common memory/doc folders. For each found:

| Folder | Tag | Treatment |
|---|---|---|
| `.serena/memories/` | `serena-import` | Hybrid (see below) |
| `~/.claude/projects/<encoded-cwd>/memory/` | `auto-memory-import` | Parse frontmatter `type:`, retain with that tag |
| `claudedocs/` | `claudedocs-import`, `analysis` | One retain per `.md` |
| `.notes/` or `notes/` | `notes-import` | One retain per `.md` |
| `docs/decisions/` or `docs/adrs/` | `decision-import` | One retain per ADR |

**Codemap heuristic** (applies to ALL sources, deterministic):

A file is a "codemap" if **either**:
- Filename matches `*_codemapper.md`, `*_codemap.md`, or `codemap_*.md`.
- File has **>300 lines** (use `wc -l` — pure integer threshold, no
  fuzzy "% headers" judgment).

For codemap files: do NOT retain the full content. Instead, group them
into a **single pointer memory** per source folder, listing the
filenames and a one-line description each (parse the first H1 or first
non-blank line). Tag the pointer with `codemap-pointer` and the source
tag (e.g., `serena-import`).

For files between 200 and 300 lines that don't match the filename
pattern: ask the user with filename + first 5 lines: "retain in full /
treat as codemap pointer / skip".

**Other `*.md` in repo root** (NOT in any of the dirs above): list them
and ask the user which to migrate. Skip `CLAUDE.md`, `AGENTS.md`,
`README.md`, `CHANGELOG.md`, `LICENSE*`, `CONTRIBUTING.md` by default
(they're either already injected or boilerplate).

**Dedup** (do this BEFORE every retain):

1. Compute a content fingerprint: first 200 chars of the file content,
   stripped of leading whitespace.
2. Call `mcp__hindsight__recall(bank_id="coding-<repo>", query=<first
   80 chars>, tags=[<source-tag>])`.
3. If any returned memory has high textual overlap (≥85% of fingerprint
   present in returned text), **skip** and log "skipped (dup)".

**Retain calls** are async (`mcp__hindsight__retain`, NOT `sync_retain`)
and sent in **parallel batches** of up to 8 per message.

**Branch tagging**: every retain to the project bank MUST include the
current branch tag (from `hm_branch_tag`, e.g., `branch:main`) in its
`tags` array, alongside the source tag. Skip if config has
`branches.tag_retains: false`. `coding-knowledge` retains are NEVER
branch-tagged.

**Report at the end**:
```
hindsight-memory: migration complete
  source: .serena/memories/        migrated: 14   codemap-pointer: 1   skipped (dup): 0
  source: claudedocs/              migrated:  3   skipped (dup): 1
  source: docs/decisions/          migrated:  5   asked: 1 (skipped)
  total memories added: 22
```

---

## Subcommand: `migrate <path>`

Same logic as `migrate`, but scoped to the given path. The path can be
absolute or relative to the repo root. Apply the same codemap heuristic
and dedup. Report similarly.

---

## Subcommand: `status`

Output:
```
hindsight-memory status
  bank:           coding-<name>
  bank_exists:    true
  bank_file:      <repo>/.bank
  enabled:        true | false (per-repo)
  global_enable:  ~/.claude/hindsight-memory.enabled (present | missing)
  env_override:   HINDSIGHT_MEMORY=<value>  (or unset)
  current_branch: branch:<name>
  agents_md:      block present | block absent | AGENTS.md missing
  config:         global=<path> local=<path|none>
  mycelium:       available | not installed
  coding-knowledge: present | missing
  total memories (project):  <N>     (from list_memories)
  total memories (knowledge): <N>
  recent memories: <last 3 retain dates>
```

Use `mcp__hindsight__list_memories(bank_id=..., limit=1)` for counts
(returned `total` field) — don't dump full memory bodies.

**If `HM_LOG_RECALL_STATS=true`** AND the log file exists: parse the
last 7 days of lines from `$HM_LOG_PATH` and append:
```
recall stats (last 7 days):
  total recalls:        <N>
  total tokens:         <sum>
  avg tokens/recall:    <avg>
  zero-result recalls:  <count of lines with results=0>
```
Use `awk` or `jq` if log is JSON-lines. If logging is disabled, skip
this section silently (do not warn — it's opt-in).

---

## Subcommand: `disable` / `enable`

- `disable`: append `enabled: false\n` to `<repo>/.bank` if not already
  there. Confirm.
- `enable`: remove any line matching `^[[:space:]]*enabled:[[:space:]]*false[[:space:]]*$`
  from `<repo>/.bank`. Confirm.

These are repo-local. To toggle globally, the user must `rm` or `touch`
`~/.claude/hindsight-memory.enabled`.

---

## Subcommand: `forget <query>`

1. `recall` with the query against `coding-<repo>`.
2. List matches as a numbered table:
   - `[N] id=<id> doc=<document_id|null> tags=<tags> | <first 100 chars>`
   - For each entry, also print fact_type (`world` / `observation` / etc.)
3. Ask the user which to delete (numeric indexes, or "all", or "none").
4. On confirmation, partition the selection:
   - **Has `document_id`** → call `mcp__hindsight__delete_document` for
     each unique `document_id`. Report count deleted.
   - **`document_id` is null** (typically `observation` fact_type) →
     report explicitly: "N memory/memories cannot be deleted via
     `delete_document` because they have no document_id (Hindsight
     auto-generated observations from a parent retain). To remove them,
     either: (a) delete the parent `world`-type memory with the same
     content (which may cascade), (b) use `mcp__hindsight__clear_memories`
     to wipe ALL memories in the bank (DESTRUCTIVE — will require a
     fresh `/hindsight-memory-operations bootstrap` and re-migration),
     or (c) accept that they remain (they're auto-summaries and will
     fade in recall ranking as more relevant memories accumulate)."
   - Do NOT auto-invoke (b). Always ask the user explicitly.
5. Print final summary: `forgot: N | un-forgettable: M | refused: K`.

NEVER touch `coding-knowledge` via `forget` unless the user explicitly
includes `--knowledge` after the query. NEVER touch banks not
prefixed with `coding-`.

---

## Subcommand: `retain [prompt]`

Two modes — choose by whether `$ARGUMENTS` (after the subcommand token)
is empty.

### Mode A — explicit content (`retain <prompt>`)

The text after `retain ` is the memory content (or its core meaning —
condense if rambling, but preserve all facts).

Steps:

1. **Tag detection** (deterministic):
   - Type tag: scan content for keywords → `user` (preferences/role),
     `feedback` (correction/validation), `project` (decision/deadline/
     status), `reference` (URL/dashboard/ext system pointer). If
     ambiguous, default to `project`.
   - Branch tag: `hm_branch_tag` (skip if `HM_BRANCHES_TAG_RETAINS=false`).
   - Mycelium tag: if content mentions `task N`, `task #N`, `myc-N`,
     `epic N`, `epic #N` → add `myc-task:<N>` or `myc-epic:<N>` AND
     prepend `task #<N>: ` or `epic #<N>: ` to content if not already
     present.
2. **Dedup** — recall with `query=<first 80 chars of content>,
   tags=[<type tag>], budget=HM_RECALL_DEDUP_BUDGET, max_tokens=
   HM_RECALL_DEDUP_MAX_TOKENS`. If results show ≥85% textual overlap
   with the candidate → tell the user "already remembered (id=<id>)"
   and skip. Don't ask, don't retain.
3. **Retain async** — `mcp__hindsight__retain(bank_id=<project bank>,
   content=<final content>, tags=[<all tags>], context="manual-retain")`.
4. **Confirm** — one line: `retained: tags=[...] (op_id=<id>)`.

If the user phrased the prompt as a *meaning* ("remember that we use
bun for everything"), expand to the full retain template:
`<rule/fact>. Why: <reason from context>. How to apply: <how>.` Only
expand if you can fill all three honestly from session context. If
not, retain as-is.

### Mode B — smart-detect (`retain` alone)

No prompt → review the conversation context available to you (focus on
user messages and your own conclusions; ignore tool results and system
reminders) for retain candidates.

Look for:

- User corrections: "no, that's wrong" / "actually we do X" / "stop
  doing Y"
- Validated approaches: user accepts an unusual choice without
  pushback, or says "yes exactly" / "perfect"
- Decisions made: "let's go with X" / "we decided Y"
- References mentioned: external dashboards, Linear/Jira tickets, URLs
- User-stated preferences/role/expertise
- Completed-but-undocumented work the user described

Build a numbered list of candidates (≤10), each formatted as:

```
[1] type=feedback  | "User corrected approach to use BigInt over
                     Number for decimal precision (after I suggested
                     Number first)"
[2] type=reference | "Project tracking lives in Mycelium epic 5"
[3] type=project   | "Decided to defer ESM migration until Q3"
```

Ask: "retain all / select N,N,N / refine N / none". On selection:
go through Mode A's steps 1-4 for each accepted candidate, in
parallel.

If zero candidates found: report `no retain candidates found in
recent context — nothing to remember`. Don't push.

**Hard rule**: NEVER retain candidates the user didn't approve.
Mode B is suggestion-only; user must confirm before any retain fires.

---

## Subcommand: `extract <path> [--auto]`

Analyze the contents of `<path>` and propose memories worth retaining.
This is the **judgment-driven, file-sourced** cousin of `retain` Mode B
(which sources from conversation). Use it when the user says things
like "look at this folder and pull out what's worth remembering" or
"extract memories from this repo".

### Argument parsing

After the `extract` token, parse the rest of `$ARGUMENTS`:

- **Required**: `<path>` — a file, directory, glob, or absolute path.
  Resolution:
  - Bare filename or relative path → resolve relative to the current
    repo root (output of `git rev-parse --show-toplevel`).
  - Absolute path → use as-is. May point inside or outside the current
    repo. If it's inside another git repo, retains still go to the
    bank for **the current repo** (not the target repo's bank) — this
    is an extraction-into-this-bank operation, not a cross-bank ferry.
  - Glob (e.g., `docs/*.md`, `**/*.adr.md`) → expand via shell glob.
  - Directory → walk recursively. Skip `.git/`, `node_modules/`,
    `.venv/`, `__pycache__/`, `dist/`, `build/`, `target/`, and any
    `.gitignore`-listed paths. Skip binary files (use `file --mime`
    or extension blacklist: `.png .jpg .gif .pdf .zip .tar .gz .bin
    .so .dylib .exe`).

- **Optional flag**: `--auto` — skip the confirmation step. Every
  proposed candidate is retained automatically (still subject to
  dedup). Use only when the user explicitly opts in (e.g.,
  `extract <path> --auto`). Without `--auto`, the default is
  user-confirmed.

If `<path>` is missing → ask: "extract from where? (file, directory,
glob, or absolute path)".

If `<path>` resolves to zero files → report `nothing to extract from
<path>` and exit.

### Codemap-or-split heuristic

For each file in the resolved set, decide its treatment **before**
extracting candidates:

1. **Pointer-only** (don't read body for content extraction; emit a
   single pointer memory):
   - Filename matches `*_codemapper.md`, `*_codemap.md`, `codemap_*.md`.
   - Filename or first-non-blank-line strongly suggests a code-mapping
     artifact: e.g., AST dumps, raw symbol tables, full API-surface
     dumps, serena-style structural breakdowns. Use judgment — if the
     content's value is "where the code lives" rather than "what's
     true and why", it's a codemap.
   - The pointer memory says: `Codemap pointer: <path> — <one-line
     description from H1 or first content line>. See file directly or
     equivalent serena memory if present.` Tagged
     `["reference", "codemap-pointer", <branch tag>]`.
2. **Split-into-atoms** (default for everything else worth retaining):
   - Read the file. Identify each independent fact/decision/pointer
     and propose it as a SEPARATE candidate memory. One file can yield
     0, 1, or many candidates — there is no upper bound but use the
     "what to retain vs not retain" table from SKILL.md as the filter.
   - **Pointer is the fallback only when splitting isn't useful** —
     e.g., a long monolithic narrative whose points are inseparable
     from full context, or a file whose value is its existence/location
     more than its facts. When falling back, emit a pointer memory like
     above and note `(fallback: not splittable into atoms)`.

There is **no line-count threshold** in `extract` — length alone never
forces pointer treatment. The 300-line rule applies to `migrate` only,
where bulk one-shot import makes length a reasonable proxy. `extract`
is judgment-driven.

### Candidate extraction (per file, after split decision)

For files in "split-into-atoms" mode, build memory candidates by
scanning for:

- **Decisions with stated reasoning** ("we chose X because Y", "decided
  to defer Z until …", "rejected approach A because …").
- **Architectural constraints / invariants** ("must never do X",
  "always Y", "the contract is Z").
- **Subtle gotchas / hidden assumptions** ("this only works because
  …", "be aware that …", "footgun: …").
- **Pointers to external systems** (URLs, dashboard IDs, Linear/Jira
  ticket refs, Slack channels, doc links).
- **Cross-project rules** (statements that apply broadly, not just to
  this repo — these route to `coding-knowledge` with `coding-rule`
  tag, NOT the project bank).
- **Validated approaches** (the user explicitly endorsed something
  unusual; "this worked, keep doing it").
- **Past-session summaries** (what shipped, what's pending and why).
- **User role / preferences** (if the file states them).

**Skip** (matches the "DO NOT RETAIN" column in SKILL.md):
- Code blocks (the code is in the repo).
- File trees, directory listings.
- Install/setup steps already documented in README.
- Boilerplate (license headers, generic onboarding).
- Anything trivially re-derivable by reading the file again.

For each candidate, infer:
- **target_bank**: `coding-knowledge` if cross-project rule, otherwise
  the current project bank.
- **type tag**: `user` / `feedback` / `project` / `reference` /
  `coding-rule` (last only for `coding-knowledge`).
- **content**: rewritten to be atomic, self-contained, clear. Include
  `Why:` and `How to apply:` clauses for `feedback`/`project`/
  `coding-rule` candidates per SKILL.md.
- **source pointer**: the file path the candidate came from (added as
  a tag like `extract-source:<relative-path>` so future prune/forget
  can trace provenance).

### Presentation & confirmation

Group candidates by source file:

```
extract candidates from <path>:

docs/decisions/2026-03-storage-engine.md (split into 3 atoms)
  [1] target=coding-hmm  type=project  tags=[project, branch:main, extract-source:docs/decisions/2026-03-storage-engine.md]
      "Decided on SQLite over Postgres for the local cache layer.
       Why: zero-config single-process workloads dominate. How to
       apply: any new persistent state at-rest goes to SQLite unless
       cross-process concurrent writers are required."
  [2] target=coding-hmm  type=reference  tags=[reference, branch:main, extract-source:...]
      "Storage benchmarks live at https://internal.example/bench-2026-03"
  [3] target=coding-knowledge  type=coding-rule  tags=[coding-rule, persistence, extract-source:...]
      "RULE (persistence): default to SQLite for local-only single-
       writer state. Why: configless and reliable. How to apply: only
       reach for Postgres when concurrent writers are required."

CODEMAP-pointer files (1):
  - .serena/memories/auth_module_codemapper.md → "Auth module symbol map (pointer)"

skipped (no extractable content): 4 files
```

Then ask:

> retain all / select N,N,N / refine N / drop N / none

Selection semantics match `retain` Mode B. `--auto` skips this prompt
and proceeds as if the user said "retain all".

### Dedup

For each accepted candidate, dedup BEFORE retain:

1. `mcp__hindsight__recall(bank_id=<target_bank>, query=<first 80
   chars of content>, tags=[<type tag>],
   budget=HM_RECALL_DEDUP_BUDGET, max_tokens=HM_RECALL_DEDUP_MAX_TOKENS)`.
2. If any returned memory has ≥85% textual overlap with the candidate
   → skip with note `skipped (dup of id=<id>)`.

### Retain (parallel async)

Send `mcp__hindsight__retain` calls in parallel batches of up to 8
per message. NEVER use `sync_retain`. Each call:

- `bank_id` = the resolved `target_bank`.
- `content` = the candidate's rewritten content.
- `tags` = `[type-tag, branch-tag (project bank only),
  extract-source:<path>, <other relevant tags>]`. `coding-knowledge`
  retains are NEVER branch-tagged.
- `context` = `"extract"`.

### Final report

```
hindsight-memory: extract complete (target=<path>)
  files scanned:           N
  files with candidates:   M
  codemap pointers:        K
  candidates proposed:     P
  retained:                R
  skipped (dup):           D
  declined by user:        U   (omitted if --auto)
  files with no value:     S
  destinations:
    coding-<repo>:         X
    coding-knowledge:      Y
```

### Hard rules (extract)

- NEVER retain to a bank not matching `^coding-`.
- NEVER auto-route to `coding-knowledge` without `coding-rule` tag and
  cross-project applicability.
- NEVER use `sync_retain`.
- ALWAYS dedup before retain.
- ALWAYS branch-tag project-bank retains (subject to
  `HM_BRANCHES_TAG_RETAINS`).
- NEVER scan: `.git/`, `node_modules/`, `.venv/`, `__pycache__/`,
  `dist/`, `build/`, `target/`, binary files, `.gitignore`-listed
  paths.
- NEVER follow symlinks pointing outside the resolved root.
- NEVER fetch URLs found in files — only retain them as references.
- NEVER read files larger than 1 MB (skip with note `skipped (too
  large: <size>)`).

---

## Subcommand: `prune`

Interactive cleanup. **Project bank only** — refuses if user passes
`--knowledge` (cross-project rules are timeless and have no branch
context).

**Phase 1 — stale by age:**

1. Call `mcp__hindsight__list_memories(bank_id=<project bank>,
   limit=500)` (paginate if `total` > 500).
2. Filter memories where `mentioned_at` is older than
   `HM_PRUNE_AGE_DAYS` (default 30).
3. Group by `document_id` (so we don't ask twice about
   auto-decomposed facts from the same parent retain).
4. For each group, show:
   ```
   [N] age=<days>d doc=<doc_id|null> tags=<tags> | <first 100 chars>
   ```
5. Ask: keep / delete / skip per entry, or "delete all", "keep all".
6. On delete: `mcp__hindsight__delete_document(document_id=...)` for
   each unique doc_id. Skip null-doc entries with note (same logic
   as `forget`).

**Phase 2 — stale by branch** (only if `HM_PRUNE_CHECK_BRANCHES=true`):

1. Collect every distinct `branch:*` tag across `list_memories`.
2. Build the protected set from `HM_PRUNE_PROTECTED_BRANCHES`
   (comma-separated). Default protects `main,master,develop,dev,trunk`.
   Always also protect `branch:UNKNOWN` (memories with no branch info
   shouldn't be auto-flagged).
3. For each non-protected tag:
   - Run `git branch --list <branch>` AND `git branch -r --list
     "origin/<branch>"`.
   - If BOTH return empty, the branch is gone (merged or deleted).
4. List memories with that tag, ask user per branch:
   `keep all from branch:X / delete all from branch:X / skip / review one by one`.
5. On delete: same `delete_document` flow.

**Phase 3 — closed Mycelium tasks** (only if
`HM_PRUNE_CHECK_MYCELIUM=true` AND `HM_MYCELIUM_AVAILABLE=true`):

1. Collect every distinct `myc-task:N` tag across `list_memories`.
2. For each task ID:
   - Run `myc task show <N> --format json` (or equivalent).
   - If task does not exist → treat as deleted, group memories under
     "task gone" and ask user.
   - If task `status == "closed"` AND `closed_at` (or `updated_at`
     when closed) is older than `HM_PRUNE_CLOSED_TASK_AGE_DAYS` days
     → flag for prune.
3. List flagged memories grouped by task:
   ```
   task #42 (closed 5 days ago: "decimal precision fix"):
     [a] doc=<id> tags=<...> | <first 100 chars>
     [b] doc=<id> tags=<...> | <first 100 chars>
   ```
4. Ask per task: `keep all / delete all / review one by one / skip`.
5. On delete: `delete_document` per unique `document_id`.

If `HM_MYCELIUM_AVAILABLE=false`: skip Phase 3 silently — no warning,
no log line.

**Final report**:
```
prune complete
  stale by age:       pruned=N kept=M skipped=K
  stale by branch:    branches_dead=N pruned=M kept=K
  closed myc tasks:   tasks_closed=N pruned=M kept=K
  un-prunable:        P  (null document_id)
  total deleted:      T memories
```

Hard rule: NEVER prune `coding-knowledge`. NEVER prune memories
tagged `coding-rule` even if they're in the project bank by mistake.

## Hard rules (inherited from skill)

- NEVER call any Hindsight tool with a `bank_id` not matching `^coding-`.
- NEVER call `delete_bank`, `clear_memories`, `delete_directive`,
  `delete_mental_model` from this command (use the dedicated
  Hindsight tools manually if needed, with explicit user request).
- ALWAYS use async `retain` (not `sync_retain`) for migration batches.
- ALWAYS dedup before retain.
- ALWAYS branch-tag project-bank retains (when `HM_BRANCHES_TAG_RETAINS=true`).
- NEVER branch-tag `coding-knowledge` retains.
- NEVER prune `coding-knowledge`.

---

## Arguments

The user's arguments are below. Parse them per the rules above.

---

$ARGUMENTS

---
