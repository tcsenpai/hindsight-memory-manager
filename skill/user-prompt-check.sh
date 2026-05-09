#!/usr/bin/env bash
# hindsight-memory UserPromptSubmit fallback hook
# If the bootstrap marker still exists when the user submits a prompt,
# the skill never fired this session. Emit a forceful directive once,
# then delete the marker so we don't spam every prompt.

set -u

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
[ -z "$REPO_ROOT" ] && exit 0

ENCODED_CWD="$(echo "$REPO_ROOT" | sed 's|/|-|g')"
MARKER="/tmp/.claude-hm-pending${ENCODED_CWD}"

[ ! -f "$MARKER" ] && exit 0

# Marker exists — skill didn't activate. Emit directive.
echo "hindsight-memory: activation pending"
cat "$MARKER" | sed 's/^/  /'
echo "  ACTION REQUIRED: invoke the hindsight-memory skill now (the SessionStart hook fired but the skill did not run). Run the bootstrap flow before responding to the user's prompt."

# Delete marker so this only fires once per session.
rm -f "$MARKER"
exit 0
