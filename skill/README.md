# hindsight-memory (operator guide)

Operator-facing reference for the installed skill. For the project
landing page (what this is and why), see the repo-root `README.md`.
For Claude's authoritative behavioral spec, see `SKILL.md`.

## What it does

- On every session in a git repo, auto-bootstraps a Hindsight bank named
  `coding-<basename(repo_root)>` and records the name in `<repo>/.bank`.
- Always recalls against `coding-knowledge` alongside the project bank,
  so universal rules ride along on every task.
- One-time migration of pre-existing markdown memories from
  `~/.claude/projects/<encoded-cwd>/memory/*.md` (only finds anything if
  you had memories before installing the skill).
- Appends an idempotent instruction block to `AGENTS.md` (only if
  `AGENTS.md` exists and the block isn't already there). Never creates
  it from scratch.
- Hard-scoped to `coding-*` banks. Refuses to read or write any other
  bank, even on user request.
- Branch-tags every project-bank retain so future cleanups can identify
  memories tied to dead branches.
- Optional Mycelium (`myc`) cross-linking and prune integration —
  silently no-ops if `myc` isn't installed.

## Files

| Path | Purpose |
|---|---|
| `SKILL.md` | The skill instructions Claude reads. Authoritative spec. |
| `README.md` | This file — operator guide. |
| `bootstrap.sh` | SessionStart hook. Decides whether to emit `hindsight-memory: activate`. Pure shell — no MCP calls. |
| `user-prompt-check.sh` | UserPromptSubmit fallback hook. Re-emits the activation flag on first prompt if the skill never fired. |
| `lib-config.sh` | YAML config loader (`hm_config_load`) + branch tag helper (`hm_branch_tag`). Source from other scripts. |
| `hindsight-memory.yaml.example` | Default global config. Copy to `~/.claude/.hindsight-memory.yaml` on install. |
| `hindsight-memory-operations.md` | The `/hindsight-memory-operations` slash command. Installed under `~/.claude/commands/`. |
| `~/.claude/hindsight-memory.enabled` | Touch file. Presence = globally enabled. |
| `~/.claude/.hindsight-memory.yaml` | Global config (optional — defaults work). |
| `<repo>/.bank` | Per-repo plain-text marker. First non-comment line is the bank name. Add `enabled: false` to disable for one repo. |
| `<repo>/.hindsight-memory.yaml` | Per-repo config override (optional, partial keys allowed). |

## Install

See the repo-root `README.md` for full install instructions (symlink vs.
copy, hook wiring in `~/.claude/settings.json`, optional `yq`).

Quick verification after install:

```bash
ls ~/.claude/skills/hindsight-memory/SKILL.md     # should exist
ls ~/.claude/commands/hindsight-memory-operations.md
ls ~/.claude/hindsight-memory.enabled              # touch file
yq --version                                       # optional but recommended
```

The skill activates automatically on session start in any git repo. It
also activates manually whenever you say "bootstrap memory", "check the
bank", "what do you remember about X", or "remember/save/don't forget"
something.

## How activation works (three layers)

The skill must always activate cleanly on session start, so there are
three layered paths instead of one:

1. **SessionStart hook** (`bootstrap.sh`) emits
   `hindsight-memory: activate` to the session and writes a pending
   marker file (`/tmp/.claude-hm-pending<encoded-cwd>`).
2. **Context injection** (any inject-local-context flow) reads the
   marker on the same session-start event and injects an activation
   directive into Claude's context.
3. **UserPromptSubmit fallback** (`user-prompt-check.sh`) fires on the
   first user prompt; if the marker still exists, emits an "ACTION
   REQUIRED" line and consumes the marker.

Layer 3 is the safety net — if the SessionStart hook didn't reach
Claude (bug, race, restart), the first user prompt still triggers
bootstrap.

`<encoded-cwd>` is the repo root absolute path with `/` replaced by `-`
(e.g., `/Users/me/code/hmm` → `-Users-me-code-hmm`). The statusline
reader uses the same encoding to find marker files.

## On/off

| Action | Command |
|---|---|
| Disable globally (one-shot, env) | `HINDSIGHT_MEMORY=off claude` |
| Disable globally (persistent) | `rm ~/.claude/hindsight-memory.enabled` |
| Re-enable | `touch ~/.claude/hindsight-memory.enabled` |
| Disable for one repo | `/hindsight-memory-operations disable` (or `echo 'enabled: false' >> .bank`) |
| Re-enable for one repo | `/hindsight-memory-operations enable` |

Resolution order: env var `HINDSIGHT_MEMORY=off` wins; then global enable
file must exist; then per-repo `.bank` must not contain `enabled: false`;
then the Hindsight MCP must be connected.

## How memory is structured

Memories follow Hindsight's strengths: **atomic, self-contained, clear**.
Each memory is one fact / rule / event, readable on its own, with the
*why* baked in.

Tags taxonomy:

| Tag | Use for | Bank |
|---|---|---|
| `user` | Role, expertise, preferences | project bank |
| `feedback` | Corrections from the user, validated approaches | project bank |
| `project` | Decisions, deadlines, who/why/when | project bank |
| `reference` | Pointers to external systems (Linear, dashboards, docs) | project bank |
| `coding-rule` | Cross-project rules that should bias behavior everywhere | `coding-knowledge` only |

> **Note on directives:** Hindsight's `create_directive` API exists, but
> directives are **not returned by `recall` or `reflect`** (verified
> empirically). The skill therefore stores cross-project rules as
> *memories* tagged `coding-rule`, not as directives. Don't use
> `mcp__hindsight__list_directives` to inspect rules — use
> `mcp__hindsight__list_memories(bank_id="coding-knowledge",
> tags=["coding-rule"])` instead.

### Branch tagging

Every retain to the **project bank** also gets a `branch:<current>` tag
(slashes normalized to dashes — `feature/x` → `branch:feature-x`). This
lets `prune` flag memories tied to dead branches later.

`coding-knowledge` retains are **never** branch-tagged — cross-project
rules are timeless.

Resolution (see `hm_branch_tag` in `lib-config.sh`):
- `git rev-parse --abbrev-ref HEAD` succeeds → `branch:<name>`.
- Command fails (not a git repo, or repo has no commits yet) →
  `branch:main`. A fresh repo will become `main` on first commit.
- Output is the literal `HEAD` (truly detached state) →
  `HM_BRANCHES_UNKNOWN_TAG` (default `branch:UNKNOWN`).

Disable per-repo: set `branches.tag_retains: false` in
`<repo>/.hindsight-memory.yaml`.

### Mycelium cross-linking

When [Mycelium](https://github.com/tcsenpai/mycelium) (`myc`) is
installed, project-bank retains about known tasks/epics get tagged
`myc-task:<N>` / `myc-epic:<N>` and the content is prefixed
`task #<N>:` / `epic #<N>:`. Detection is deterministic — the user
mentions `task N`, `task #N`, `myc-N`, etc., or a task ID was touched
in a recent `myc task` Bash call.

After observing `myc task close <N>`, the skill prompts once: "what
did you learn from task #N?" — and retains the response (if non-empty)
tagged `myc-task:<N>`, `feedback`, plus branch tag. Suppress for the
rest of the session by saying "skip all".

All Mycelium features silently no-op if `myc` isn't installed
(`HM_MYCELIUM_AVAILABLE=false`).

## Bank naming and collisions

- Project bank = `coding-` + lowercased basename of the git repo root.
- If that name is already taken in Hindsight (different repo with the
  same basename, or a manual bank), the skill suffixes `-2`, `-3`, …
  until it finds a free name and writes that into `.bank`.
- Banks **must** be `coding-`-prefixed. The skill refuses to operate on
  any other bank, even on explicit user request — that's a hard scope
  rule, not a default.

## `.bank` file format

Plain text. First non-comment, non-blank line that is not
`enabled: false` is the bank name. Comments start with `#`. Example:

```
coding-sdks
# created 2026-05-08
```

Disable for this repo:

```
coding-sdks
enabled: false
```

`.bank` should be **committed** so teammates share the same bank name.

## `coding-knowledge` seed

On first creation the skill seeds `coding-knowledge` with rules
extracted from the author's global instructions (no sycophantic
openers, prefer `bun`/`uv`, ethers v6, no `any`, scope discipline,
plan-before-code, `retain` over `sync_retain`, etc.). See
`SKILL.md §Seed rules for coding-knowledge` for the full list.

Inspect what's there:
```
mcp__hindsight__list_memories(bank_id="coding-knowledge",
                              tags=["coding-rule"])
```

Add more by retaining with `coding-rule` in the tags array. The skill
never auto-prunes `coding-knowledge` (rules are timeless).

## Slash command — `/hindsight-memory-operations`

Manual operations on the bank. Coexists with the description-based
auto-invocation (it does NOT trigger the skill again, avoiding a
duplicate-bootstrap loop).

| Subcommand | Purpose |
|---|---|
| (empty) or `bootstrap` | Run the bootstrap flow (idempotent). |
| `migrate` | Autodetect & bulk-migrate common memory/doc folders (`.serena/memories/`, `~/.claude/projects/.../memory/`, `claudedocs/`, `.notes/`, `docs/decisions/`). Applies a 300-line/codemap heuristic to avoid bloat. |
| `migrate <path>` | Same logic, scoped to one path. |
| `status` | Show bank info, counts, AGENTS.md state, config, optional recall stats. |
| `retain <prompt>` | Explicit retain — store the given text with auto-detected tags. |
| `retain` (no args) | Smart-detect candidates from recent conversation; ask for confirmation before retaining. |
| `extract <path> [--auto]` | Analyze a file/folder/repo and propose memories worth retaining. Splits into atomic memories where possible; pointer-only for codemaps. `--auto` skips confirmation. |
| `forget <query>` | List matching memories, delete on confirm. Handles null-`document_id` observations gracefully. |
| `prune` | Interactive cleanup: stale by age, dead branches, closed Mycelium tasks. Project bank only. |
| `enable` / `disable` | Per-repo on/off via `.bank`. |

All retains use **async `retain`** (not `sync_retain`, which blocks
30+ seconds). Migration batches send up to 8 parallel retains per
message. Dedup runs before every retain (≥85% textual overlap → skip).

## Configuration

Two YAML files, same name, different scopes:

| File | Scope |
|---|---|
| `~/.claude/.hindsight-memory.yaml` | Global defaults |
| `<repo>/.hindsight-memory.yaml` | Per-repo override (partial keys allowed) |

Local overrides global per-key. Missing keys fall through to global,
then to hardcoded defaults in `lib-config.sh`. Requires `yq` —
without it, both files are silently ignored (statusline shows
`err:no-yq` if a config file exists).

Schema (see `hindsight-memory.yaml.example` for the annotated version):

```yaml
recall:
  routine_budget: low          # task-start recalls
  routine_max_tokens: 1024
  ask_budget: high             # "what do you remember about X"
  ask_max_tokens: 4096
  dedup_budget: low            # pre-retain dedup checks
  dedup_max_tokens: 512
logging:
  log_recall_stats: false      # one log line per recall when true
  log_path: ~/.claude/hindsight-memory.log
branches:
  tag_retains: true            # add branch:<name> to project-bank retains
  unknown_tag: branch:UNKNOWN  # tag for truly-detached HEAD
prune:
  default_age_days: 30
  check_branches: true
  protected_branches: "main,master,develop,dev,trunk"  # never flagged dead
  check_mycelium: true
  closed_task_age_days: 3
mycelium:
  snapshot_in_sessions: false  # inline `myc summary` in session retains
```

To override one key per-repo, write a partial file:

```yaml
# /path/to/repo/.hindsight-memory.yaml
recall:
  routine_max_tokens: 2048   # this repo has lots of context
logging:
  log_recall_stats: true     # debug recall quality just here
```

## Statusline states

The statusline reads small marker files in `/tmp` to surface state
without making MCP calls (zero latency per prompt).

| State | Meaning |
|---|---|
| `[hm coding-foo]` | Healthy, active |
| `[hm new]` | Active in repo with no `.bank` yet (will bootstrap on first prompt) |
| `[hm off]` / `[hm off:repo]` / `[hm --]` | Intentionally disabled (global env / per-repo / global file missing) |
| `[hm err:no-mcp]` | Hindsight MCP not connected |
| `[hm err:bad-bank]` | `.bank` contains a non-`coding-` name |
| `[hm err:stale]` | Activation flag fired but skill never ran |
| `[hm err:no-yq]` | `yq` missing AND a config file exists (config silently ignored) |

Errors stack with the bank name (e.g., `[hm coding-foo err:stale]`) so
no info is hidden.

Marker files (`<encoded>` = repo root with `/` → `-`):

| Marker | Written by | Removed by |
|---|---|---|
| `/tmp/.claude-hm-pending<encoded>` | `bootstrap.sh` on session start | `user-prompt-check.sh` on first prompt; skill on successful bootstrap |
| `/tmp/.claude-hm-mcp-unavailable<encoded>` | Skill when MCP tools missing OR an MCP call fails | Statusline auto-clears it when its live probe sees the server back. **Informational only** — statusline's `err:no-mcp` is driven by a live HTTP probe (300ms timeout), not this file. |

## AGENTS.md block

If `AGENTS.md` exists in the repo and doesn't already contain the start
marker, the skill appends an instruction block summarizing how this
repo uses Hindsight memory. The markers (`<!-- hindsight-memory:start -->`
and `<!-- hindsight-memory:end -->`) make future updates idempotent.

The skill **never creates `AGENTS.md` from scratch** — if it doesn't
exist, the append step is silently skipped.

## Failure modes

| Situation | What happens |
|---|---|
| Hindsight MCP not connected | Skill is silent. No bootstrap, no warnings. Falls back to default markdown auto-memory. Marker `err:no-mcp` written. |
| MCP connected but a call fails mid-session | One-time warning, fallback to markdown for the rest of the session. `err:no-mcp` marker written. |
| `.bank` has a non-`coding-` name | Hard error. Asks you to fix manually. Statusline `err:bad-bank`. |
| Pending marker stale (>5 min, skill never fired) | Statusline `err:stale`. Skill bootstraps if invoked. |
| `yq` missing AND a config file exists | Statusline `err:no-yq`. Hardcoded defaults used. |
| Bank in `.bank` was deleted upstream | Recreated empty. Warning emitted. |
| Name collision on `create_bank` | Suffix with `-2`, `-3`, … until free. `.bank` updated. |
| AGENTS.md missing | Skip the append silently. |
| Non-git directory | Skill stays silent. |
| Request to operate on a non-`coding-` bank | Refused with explanation of the hard scope rule. |

## Common ops the user can ask for

- "What do you remember about X" — recall on both banks (high budget).
- "Remember/save/don't forget X" — explicit retain, auto-tagged.
- "Forget X" — list memories matching X, delete on confirm
  (`coding-` banks only).
- "Reseed coding-knowledge" — diff current rules against the seed list
  in `SKILL.md` and add any missing.
- "Extract memories from this folder" — runs `extract` flow.
- "Disable hindsight-memory" — see the on/off table above.

## Why a skill + hooks (not just hooks)

Hooks are shell scripts and cannot call MCP tools. The bootstrap shell
script only decides *whether* the skill should run; the actual memory
work — `create_bank`, `retain`, `recall`, AGENTS.md edits — has to
happen inside Claude. So the hooks just emit flags / write markers,
Claude reads them, and the skill takes over.

The three-layer activation chain (SessionStart hook + context
injection + UserPromptSubmit fallback) ensures the skill fires on every
fresh session even when one path fails.
