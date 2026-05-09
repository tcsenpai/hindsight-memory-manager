# Hindsight Memory Management

A Claude Code skill that replaces the default markdown auto-memory system
with [Hindsight MCP](https://github.com/) banks for persistent, recallable
project memory.

## What it does

- Auto-bootstraps a `coding-<repo>` Hindsight bank for every git repo on
  session start.
- Always recalls a global `coding-knowledge` bank alongside, surfacing
  cross-project rules (style, workflow, tooling preferences).
- Hard-scoped to `coding-*` banks — refuses to read or write any other.
- Branch-tags every project-bank retain so future cleanups can identify
  memories tied to dead branches.
- Cross-links with [Mycelium](https://github.com/tcsenpai/mycelium)
  (`myc`) when present — tagging retains by `myc-task:N`, prompting on
  `myc task close`, pruning closed-task memories.
- Provides a slash command (`/hindsight-memory-operations`) for manual
  ops: bootstrap, migrate, status, retain, forget, prune, disable.
- Shows live state in the Claude Code statusline (e.g.,
  `[hm coding-sdks]`, `[hm err:no-mcp]`, `[hm off]`).
- Configurable via global + per-repo YAML (recall budgets, branch
  tagging, prune thresholds, logging).

## Repository layout

```
hmm/
├── EXPLANATION.md              # this file
└── skill/
    ├── SKILL.md                # the skill definition (loaded by Claude)
    ├── README.md               # ops + install guide for end users
    ├── bootstrap.sh            # SessionStart hook — emits activation flag
    ├── user-prompt-check.sh    # UserPromptSubmit fallback hook
    ├── lib-config.sh           # YAML config loader + branch helper
    ├── hindsight-memory.yaml.example  # default global config
    └── hindsight-memory-operations.md # slash command (/hindsight-memory-operations)
```

## Install (manual, until packaged)

```bash
# 1. Place skill files under ~/.claude/
cp -r skill/SKILL.md skill/README.md skill/bootstrap.sh \
      skill/user-prompt-check.sh skill/lib-config.sh \
      ~/.claude/skills/hindsight-memory/

chmod +x ~/.claude/skills/hindsight-memory/*.sh

# 2. Place slash command
cp skill/hindsight-memory-operations.md \
   ~/.claude/commands/hindsight-memory-operations.md

# 3. Place global config (rename from .example)
cp skill/hindsight-memory.yaml.example \
   ~/.claude/.hindsight-memory.yaml

# 4. Touch the global enable file
touch ~/.claude/hindsight-memory.enabled

# 5. Wire SessionStart + UserPromptSubmit hooks in ~/.claude/settings.json
# (see SKILL.md §How all the automatic hooks work)
```

Optional but recommended: `brew install yq` so per-repo
`.hindsight-memory.yaml` overrides actually load.

## How activation works (no user action needed after install)

Three layered paths ensure the skill activates on every fresh session in
a git repo:

1. **SessionStart hook** (`bootstrap.sh`) emits `hindsight-memory: activate`
   to the session, writes a pending marker.
2. **Context injection** (`inject-local-context.sh`) reads the marker on
   the same session-start event and injects a strong activation directive.
3. **UserPromptSubmit fallback** (`user-prompt-check.sh`) fires on the
   user's first prompt; if the marker still exists, emits an "ACTION
   REQUIRED" line and consumes the marker.

The skill itself never makes shell decisions — Claude reads the
activation flag and runs the bootstrap flow (verify banks exist, seed
`coding-knowledge` if first run, append AGENTS.md block if applicable,
output one short confirmation line).

## On/off

| Action | Method |
|---|---|
| Disable globally (one shot) | `HINDSIGHT_MEMORY=off claude` |
| Disable globally (persistent) | `rm ~/.claude/hindsight-memory.enabled` |
| Disable per-repo | `/hindsight-memory-operations disable` (or add `enabled: false` to `<repo>/.bank`) |

## Memory model

- **Project bank** (`coding-<repo>`): facts/decisions/context for *this*
  repo. Branch-tagged, optionally `myc-task`-tagged.
- **`coding-knowledge`** (global): cross-project rules — style,
  workflow, tooling, INVEST/DAG/PMS for Mycelium, etc.
- **Retain triggers**: explicit only — user says "remember", slash
  command, Mycelium close prompt, or initial migration. Auto-retain via
  heuristics is disabled by design (avoids bank pollution).
- **Recall**: parallel against project bank + `coding-knowledge` at task
  start, with budget tuned per intent (config-driven).

## Failure handling

Statusline reflects all states without ever calling MCP:

| State | Meaning |
|---|---|
| `[hm coding-foo]` | Healthy, active |
| `[hm new]` | Active in repo with no `.bank` yet (will bootstrap) |
| `[hm off]` / `[hm off:repo]` / `[hm --]` | Intentionally disabled |
| `[hm err:no-mcp]` | Hindsight MCP not connected |
| `[hm err:bad-bank]` | `.bank` contains a non-`coding-` name |
| `[hm err:stale]` | Activation flag fired but skill never ran |
| `[hm err:no-yq]` | `yq` missing AND a config file exists (config silently ignored) |

Errors stack with the bank name (e.g., `[hm coding-foo err:stale]`) so
no info is hidden.

## Why this exists

Claude Code's default memory system writes markdown files to a
project-keyed directory. Useful for short-term, but:

- No semantic recall — Claude has to read filenames + frontmatter
- No cross-project knowledge sharing
- Memories accumulate forever with no cleanup story
- Plain text, no auto-decomposition

Hindsight provides ranked semantic recall, multi-bank scoping, async
indexing with auto-decomposition, and a reflection model. This skill
just plumbs Claude Code into it cleanly with strong defaults.

## Status

Working in production for the author across multiple repos. See
`skill/SKILL.md` for the full behavioral spec, `skill/README.md` for
operator-facing docs, and `skill/hindsight-memory-operations.md` for
the slash command reference.

## License

MIT — see [LICENSE](LICENSE).
