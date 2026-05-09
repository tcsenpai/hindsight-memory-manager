# hmm — Hindsight Memory for Claude Code

A Claude Code skill that swaps the default markdown auto-memory system
for [Hindsight MCP](https://github.com/) banks. Per-project memory lives
in a `coding-<repo>` bank; cross-project rules live in a single
`coding-knowledge` bank that's recalled alongside on every task.

> Status: working in production for the author across multiple repos.
> No packager yet — install is manual (see below).

## Why

Claude Code's built-in memory writes markdown files to a project-keyed
directory. It works for short-term notes, but:

- No semantic recall — Claude has to read filenames + frontmatter to find
  anything.
- No cross-project knowledge sharing.
- Memories accumulate forever with no cleanup story.
- Plain text, no auto-decomposition into atomic facts.

Hindsight gives you ranked semantic recall, multi-bank scoping, async
indexing with auto-decomposition, and a reflection model. This skill
plumbs Claude Code into it cleanly with strong defaults (hard
`coding-*` bank scope, branch-tagged retains, explicit-only retain
triggers, optional Mycelium cross-linking).

## What you get

- **Auto-bootstrap** on every session in a git repo — creates a
  `coding-<basename>` bank if missing, records the name in `.bank`.
- **Always-on `coding-knowledge` recall** — universal rules (no `any`,
  prefer `bun`, plan-before-code, etc.) ride along on every task.
- **Hard scope**: skill refuses to read or write any bank not prefixed
  `coding-`, even on user request.
- **Branch tagging** on every project-bank retain — future cleanups can
  flag memories tied to dead branches.
- **Mycelium integration** ([github.com/tcsenpai/mycelium](https://github.com/tcsenpai/mycelium))
  when present: tags retains by `myc-task:N`, prompts on `myc task close`,
  prunes closed-task memories. Silently no-ops when `myc` isn't installed.
- **Slash command** (`/hindsight-memory-operations`) for manual ops:
  `bootstrap`, `migrate`, `status`, `retain`, `extract`, `forget`,
  `prune`, `enable`, `disable`.
- **Statusline integration** — `/tmp` marker files surface state without
  any MCP calls (e.g., `[hm coding-foo]`, `[hm err:no-mcp]`,
  `[hm off]`).
- **Configurable** via global + per-repo YAML (recall budgets, branch
  tagging, prune thresholds, logging).

## Repository layout

```
hmm/
├── README.md                          # this file
├── EXPLANATION.md                     # design rationale + activation flow
└── skill/
    ├── SKILL.md                       # the skill instructions Claude reads
    ├── README.md                      # operator guide for the installed skill
    ├── bootstrap.sh                   # SessionStart hook — emits activation flag
    ├── user-prompt-check.sh           # UserPromptSubmit fallback hook
    ├── lib-config.sh                  # YAML loader + branch tag helper
    ├── hindsight-memory.yaml.example  # default global config
    └── hindsight-memory-operations.md # /hindsight-memory-operations slash command
```

## Install

Two paths — pick one.

### Option A: symlink (recommended for development)

If you want edits to `skill/*` in this repo to take effect immediately
in your live Claude Code sessions:

```bash
# Clone wherever you keep your code
git clone <this-repo> ~/code/hmm
cd ~/code/hmm

# Symlink the skill files into ~/.claude/
mkdir -p ~/.claude/skills/hindsight-memory ~/.claude/commands
ln -s "$PWD/skill/SKILL.md"                       ~/.claude/skills/hindsight-memory/SKILL.md
ln -s "$PWD/skill/README.md"                      ~/.claude/skills/hindsight-memory/README.md
ln -s "$PWD/skill/bootstrap.sh"                   ~/.claude/skills/hindsight-memory/bootstrap.sh
ln -s "$PWD/skill/user-prompt-check.sh"           ~/.claude/skills/hindsight-memory/user-prompt-check.sh
ln -s "$PWD/skill/lib-config.sh"                  ~/.claude/skills/hindsight-memory/lib-config.sh
ln -s "$PWD/skill/hindsight-memory-operations.md" ~/.claude/commands/hindsight-memory-operations.md

chmod +x skill/*.sh

# Global config (rename from .example, then edit if you want)
cp skill/hindsight-memory.yaml.example ~/.claude/.hindsight-memory.yaml

# Global enable file
touch ~/.claude/hindsight-memory.enabled
```

### Option B: copy (for end users who don't want to track upstream)

```bash
mkdir -p ~/.claude/skills/hindsight-memory ~/.claude/commands
cp skill/SKILL.md skill/README.md skill/bootstrap.sh \
   skill/user-prompt-check.sh skill/lib-config.sh \
   ~/.claude/skills/hindsight-memory/
cp skill/hindsight-memory-operations.md ~/.claude/commands/
cp skill/hindsight-memory.yaml.example  ~/.claude/.hindsight-memory.yaml
chmod +x ~/.claude/skills/hindsight-memory/*.sh
touch ~/.claude/hindsight-memory.enabled
```

### Wire the hooks (both options)

Add to `~/.claude/settings.json` under `hooks`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command",
            "command": "$HOME/.claude/skills/hindsight-memory/bootstrap.sh" }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          { "type": "command",
            "command": "$HOME/.claude/skills/hindsight-memory/user-prompt-check.sh" }
        ]
      }
    ]
  }
}
```

### Recommended

```bash
brew install yq    # so per-repo .hindsight-memory.yaml overrides actually load
```

Without `yq`, both YAML config files are silently ignored and hardcoded
defaults are used (statusline shows `err:no-yq` if a config file exists).

## Usage

Once installed, you don't need to do anything. The skill activates on
session start in every git repo and quietly bootstraps a per-repo bank.
Confirmation is one line:

```
hindsight-memory: bank=coding-foo, knowledge=ready
```

Memory is **explicit-only** by design — auto-retain via heuristics is
disabled (it pollutes the bank). Memories enter via four paths:

| Path | Trigger |
|---|---|
| Explicit "remember" | You say "remember this", "save that", "don't forget X" in chat. |
| Slash command | You run `/hindsight-memory-operations retain ...` or `extract ...`. |
| Mycelium close prompt | After `myc task close N` (only if `myc` is installed). |
| Migration | One-shot — `/hindsight-memory-operations migrate [path]` or `coding-knowledge` seeding. |

Recall happens automatically against both banks (project + knowledge) at
the start of every relevant task.

## Slash command

`/hindsight-memory-operations <subcommand> [args]`

| Subcommand | Purpose |
|---|---|
| `bootstrap` | Run the bootstrap flow (idempotent). |
| `migrate [path]` | Bulk-import existing markdown notes into the bank. |
| `status` | Show bank info, counts, recall stats. |
| `retain [prompt]` | Explicit retain (with text), or smart-detect from recent conversation (no text). |
| `extract <path> [--auto]` | Analyze a file/folder/repo and propose memories worth retaining. Splits into atomic memories where possible; pointer-only for codemaps. |
| `forget <query>` | List matching memories, delete on confirm. |
| `prune` | Interactive cleanup: stale by age, dead branches, closed Mycelium tasks. |
| `enable` / `disable` | Per-repo on/off via `.bank`. |

## On/off

| Action | Method |
|---|---|
| Disable globally (one shot) | `HINDSIGHT_MEMORY=off claude` |
| Disable globally (persistent) | `rm ~/.claude/hindsight-memory.enabled` |
| Disable per-repo | `/hindsight-memory-operations disable` |

Resolution order: `HINDSIGHT_MEMORY=off` env wins; then global enable file
must exist; then per-repo `.bank` must not contain `enabled: false`.

## Statusline states

| State | Meaning |
|---|---|
| `[hm coding-foo]` | Healthy, active |
| `[hm new]` | Active in repo with no `.bank` yet (will bootstrap on first prompt) |
| `[hm off]` / `[hm off:repo]` / `[hm --]` | Intentionally disabled |
| `[hm err:no-mcp]` | Hindsight MCP not connected |
| `[hm err:bad-bank]` | `.bank` contains a non-`coding-` name |
| `[hm err:stale]` | Activation flag fired but skill never ran |
| `[hm err:no-yq]` | `yq` missing AND a config file exists (config silently ignored) |

Errors stack with the bank name (e.g., `[hm coding-foo err:stale]`) so
no info is hidden. The statusline reads `/tmp` marker files for most
state and does a single 300ms-budget HTTP probe against the configured
Hindsight URL to detect `err:no-mcp` live (a stale marker no longer
produces false positives — the probe is authoritative and clears the
marker when the server is reachable).

## Configuration

Two YAML files, same name, different scopes:

| File | Scope |
|---|---|
| `~/.claude/.hindsight-memory.yaml` | Global defaults |
| `<repo>/.hindsight-memory.yaml` | Per-repo override (optional, partial keys allowed) |

Local overrides global per-key. Missing keys fall through to global,
then to hardcoded defaults. See `skill/hindsight-memory.yaml.example`
for the full schema (recall budgets, branch tagging, prune thresholds,
logging).

## Benchmark

There's a small empirical comparison between this skill (Hindsight-backed
recall) and Claude Code's default markdown auto-memory in
[`tests/eval/`](tests/eval/). 50 synthetic facts, 20 ground-truth queries,
retrieval-only metrics (no end-to-end QA). Headline numbers:

| | Tokens/query (mean) | Recall@5 (avg, non-adversarial) | Adversarial behavior |
|---|---:|---:|---|
| Markdown | 1450 | 0.475 | Returns nothing when no keywords match (good) |
| Hindsight | 1001 | 0.767 | Always returns top semantic-nearest items, even when nothing relevant exists (bad) |

Hindsight uses ~31% fewer tokens per query and gets ~61% higher recall@5
on real-world query types (paraphrase, indirect, multi-fact). The token
gap is the *minimum* gap — it widens with corpus size since markdown's
index grows linearly while Hindsight's response stays at the budget.
The clear cost is no concept of "not found" — adversarial queries return
5 confidently-irrelevant memories. Full methodology, per-query data,
caveats, and reproduction steps in [`tests/eval/RESULTS.md`](tests/eval/RESULTS.md).

> N=20 is a smoke test, not a published result. Treat as motivating
> evidence, not statistical proof. The accompanying
> [`tests/eval/RESEARCH.md`](tests/eval/RESEARCH.md) frames the
> methodology against LongMemEval / LoCoMo / MemoryArena.

## Further reading

- [`tests/eval/RESULTS.md`](tests/eval/RESULTS.md) — benchmark results
  and per-query breakdown
- [`tests/eval/RESEARCH.md`](tests/eval/RESEARCH.md) — methodology
  background and field literature
- `EXPLANATION.md` — design rationale, activation flow, why three layers
  of hooks, comparison with the default markdown auto-memory
- `skill/SKILL.md` — the full behavioral spec Claude reads. Authoritative.
- `skill/README.md` — operator guide for the installed skill (covers
  failure modes, common ops)
- `skill/hindsight-memory-operations.md` — slash command reference

## License

MIT — see [LICENSE](LICENSE).
