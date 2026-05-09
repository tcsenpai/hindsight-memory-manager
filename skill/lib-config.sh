#!/usr/bin/env bash
# hindsight-memory config loader.
# Resolves config from:
#   1. <repo>/.hindsight-memory.yaml (per-repo override, optional)
#   2. ~/.claude/.hindsight-memory.yaml (global defaults)
#   3. Hardcoded fallbacks (if both files missing)
#
# Source this file from other scripts:
#   source "$HOME/.claude/skills/hindsight-memory/lib-config.sh"
#   hm_config_load
#   echo "$HM_RECALL_ROUTINE_BUDGET"

# Hardcoded fallback defaults (mirror ~/.claude/.hindsight-memory.yaml).
# These ensure the skill works even if both config files are missing.
HM_RECALL_ROUTINE_BUDGET="low"
HM_RECALL_ROUTINE_MAX_TOKENS="1024"
HM_RECALL_ASK_BUDGET="high"
HM_RECALL_ASK_MAX_TOKENS="4096"
HM_RECALL_DEDUP_BUDGET="low"
HM_RECALL_DEDUP_MAX_TOKENS="512"
HM_LOG_RECALL_STATS="false"
HM_LOG_PATH="$HOME/.claude/hindsight-memory.log"
HM_BRANCHES_TAG_RETAINS="true"
HM_BRANCHES_UNKNOWN_TAG="branch:UNKNOWN"
HM_PRUNE_AGE_DAYS="30"
HM_PRUNE_CHECK_BRANCHES="true"
HM_PRUNE_PROTECTED_BRANCHES="main,master,develop,dev,trunk"
HM_PRUNE_CHECK_MYCELIUM="true"
HM_PRUNE_CLOSED_TASK_AGE_DAYS="3"
HM_MYCELIUM_SNAPSHOT_IN_SESSIONS="false"
HM_MYCELIUM_AVAILABLE="false"

# Internal: read a yq-style path from a YAML file, set default on miss.
# Usage: _hm_read <file> <yq-path> <default-value>
_hm_read() {
  local file="$1" path="$2" default="$3"
  if [ ! -f "$file" ]; then
    echo "$default"
    return
  fi
  if ! command -v yq >/dev/null 2>&1; then
    echo "$default"
    return
  fi
  local val
  val="$(yq -r "$path // \"\"" "$file" 2>/dev/null)"
  if [ -z "$val" ] || [ "$val" = "null" ] || [ "$val" = "~" ]; then
    echo "$default"
  else
    echo "$val"
  fi
}

# Public: load config into HM_* env vars.
# Resolution: local file overrides global, global overrides hardcoded.
hm_config_load() {
  local global="$HOME/.claude/.hindsight-memory.yaml"
  local repo_root local_file=""
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"
  [ -n "$repo_root" ] && local_file="$repo_root/.hindsight-memory.yaml"

  # Detect yq availability once. If missing and config files exist,
  # warn on stderr (non-fatal; we use hardcoded defaults).
  if ! command -v yq >/dev/null 2>&1; then
    if [ -f "$global" ] || [ -n "$local_file" ] && [ -f "$local_file" ]; then
      echo "hindsight-memory: yq not installed, using hardcoded defaults. Install with: brew install yq" >&2
    fi
    return 0
  fi

  # Helper: read with global → local override chain.
  _hm_chain() {
    local path="$1" default="$2" val
    val="$(_hm_read "$global" "$path" "$default")"
    if [ -n "$local_file" ] && [ -f "$local_file" ]; then
      val="$(_hm_read "$local_file" "$path" "$val")"
    fi
    echo "$val"
  }

  HM_RECALL_ROUTINE_BUDGET="$(_hm_chain '.recall.routine_budget' "$HM_RECALL_ROUTINE_BUDGET")"
  HM_RECALL_ROUTINE_MAX_TOKENS="$(_hm_chain '.recall.routine_max_tokens' "$HM_RECALL_ROUTINE_MAX_TOKENS")"
  HM_RECALL_ASK_BUDGET="$(_hm_chain '.recall.ask_budget' "$HM_RECALL_ASK_BUDGET")"
  HM_RECALL_ASK_MAX_TOKENS="$(_hm_chain '.recall.ask_max_tokens' "$HM_RECALL_ASK_MAX_TOKENS")"
  HM_RECALL_DEDUP_BUDGET="$(_hm_chain '.recall.dedup_budget' "$HM_RECALL_DEDUP_BUDGET")"
  HM_RECALL_DEDUP_MAX_TOKENS="$(_hm_chain '.recall.dedup_max_tokens' "$HM_RECALL_DEDUP_MAX_TOKENS")"
  HM_LOG_RECALL_STATS="$(_hm_chain '.logging.log_recall_stats' "$HM_LOG_RECALL_STATS")"
  HM_LOG_PATH="$(_hm_chain '.logging.log_path' "$HM_LOG_PATH")"
  # Expand ~ in log path
  HM_LOG_PATH="${HM_LOG_PATH/#\~/$HOME}"
  HM_BRANCHES_TAG_RETAINS="$(_hm_chain '.branches.tag_retains' "$HM_BRANCHES_TAG_RETAINS")"
  HM_BRANCHES_UNKNOWN_TAG="$(_hm_chain '.branches.unknown_tag' "$HM_BRANCHES_UNKNOWN_TAG")"
  HM_PRUNE_AGE_DAYS="$(_hm_chain '.prune.default_age_days' "$HM_PRUNE_AGE_DAYS")"
  HM_PRUNE_CHECK_BRANCHES="$(_hm_chain '.prune.check_branches' "$HM_PRUNE_CHECK_BRANCHES")"
  HM_PRUNE_PROTECTED_BRANCHES="$(_hm_chain '.prune.protected_branches' "$HM_PRUNE_PROTECTED_BRANCHES")"
  HM_PRUNE_CHECK_MYCELIUM="$(_hm_chain '.prune.check_mycelium' "$HM_PRUNE_CHECK_MYCELIUM")"
  HM_PRUNE_CLOSED_TASK_AGE_DAYS="$(_hm_chain '.prune.closed_task_age_days' "$HM_PRUNE_CLOSED_TASK_AGE_DAYS")"
  HM_MYCELIUM_SNAPSHOT_IN_SESSIONS="$(_hm_chain '.mycelium.snapshot_in_sessions' "$HM_MYCELIUM_SNAPSHOT_IN_SESSIONS")"

  # Detect mycelium availability (no config — purely environmental).
  if command -v myc >/dev/null 2>&1; then
    HM_MYCELIUM_AVAILABLE="true"
  else
    HM_MYCELIUM_AVAILABLE="false"
  fi
}

# Public: get current branch tag (or fallback if undeterminable).
# Outputs the full tag string, e.g., "branch:main".
# Slashes in branch names are normalized to dashes.
#
# Resolution rules:
#   - `git rev-parse --abbrev-ref HEAD` succeeds (exit 0) with a real
#     branch name → "branch:<name>".
#   - Command fails (non-zero exit, e.g., not a git repo, or repo has
#     no commits yet — git prints "HEAD" to stdout AND a fatal to
#     stderr, exit 128) → "branch:main". A fresh repo will become
#     "main" as soon as the first commit lands, so tagging that way
#     upfront keeps memories consistent across the boundary.
#   - Command succeeds but output is the literal "HEAD" (truly
#     detached state — a checked-out commit, not a branch) → fall back
#     to HM_BRANCHES_UNKNOWN_TAG (default "branch:UNKNOWN").
hm_branch_tag() {
  local branch rc
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  rc=$?
  if [ $rc -ne 0 ]; then
    echo "branch:main"
    return
  fi
  if [ -z "$branch" ]; then
    echo "branch:main"
    return
  fi
  if [ "$branch" = "HEAD" ]; then
    echo "$HM_BRANCHES_UNKNOWN_TAG"
    return
  fi
  echo "branch:${branch//\//-}"
}
