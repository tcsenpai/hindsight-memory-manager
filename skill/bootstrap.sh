#!/usr/bin/env bash
# hindsight-memory SessionStart hook
# Emits "hindsight-memory: activate" to stdout if all preconditions hold,
# AND writes a pending marker to /tmp so context-injection / fallback
# hooks can re-trigger the skill if it didn't fire on session start.
#
# Hooks cannot call MCP tools — that's Claude's job. This script only
# decides whether the skill should activate this session.

set -u

# --- Kill switch checks -------------------------------------------------

# Env var off wins everything.
if [ "${HINDSIGHT_MEMORY:-on}" = "off" ] || [ "${HINDSIGHT_MEMORY:-on}" = "OFF" ]; then
  exit 0
fi

# Global enable file must exist.
if [ ! -f "$HOME/.claude/hindsight-memory.enabled" ]; then
  exit 0
fi

# --- Repo check ---------------------------------------------------------

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

# --- Per-repo opt-out ---------------------------------------------------

BANK_FILE="$REPO_ROOT/.bank"
if [ -f "$BANK_FILE" ] && grep -qE '^[[:space:]]*enabled:[[:space:]]*false[[:space:]]*$' "$BANK_FILE"; then
  exit 0
fi

# --- All checks passed --------------------------------------------------

# Encode cwd for marker filename: replace / with -
ENCODED_CWD="$(echo "$REPO_ROOT" | sed 's|/|-|g')"
MARKER="/tmp/.claude-hm-pending${ENCODED_CWD}"

# Write marker (consumed by inject-local-context.sh and user-prompt-check.sh)
{
  echo "repo_root=$REPO_ROOT"
  if [ -f "$BANK_FILE" ]; then
    BANK_NAME="$(grep -vE '^[[:space:]]*(#|$)' "$BANK_FILE" | grep -vE '^[[:space:]]*enabled:' | head -1 | tr -d '[:space:]')"
    echo "existing_bank=$BANK_NAME"
  else
    echo "new_bank_candidate=coding-$(basename "$REPO_ROOT")"
  fi
  echo "created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$MARKER"

echo "hindsight-memory: activate"
echo "  repo_root=$REPO_ROOT"
if [ -f "$BANK_FILE" ]; then
  BANK_NAME="$(grep -vE '^[[:space:]]*(#|$)' "$BANK_FILE" | grep -vE '^[[:space:]]*enabled:' | head -1 | tr -d '[:space:]')"
  echo "  existing_bank=$BANK_NAME"
else
  echo "  new_bank_candidate=coding-$(basename "$REPO_ROOT")"
fi
exit 0
