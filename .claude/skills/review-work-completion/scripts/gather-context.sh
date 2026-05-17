#!/usr/bin/env bash
# Gathers review context into dev/local/tmp/
# Usage: gather-context.sh [--since <ref>] [tasks_file] [prd_summary_file]
#   --since <ref>:    diff base for an incremental review (rework cycles);
#                     when omitted or invalid, diffs against the branch base
#   tasks_file:       path to file containing tasks markdown (optional)
#   prd_summary_file: path to file containing PRD summary (optional)
# Outputs: paths to created files (one per line)

set -euo pipefail

PROJECT_ROOT="$(pwd)"

# Parse args: optional `--since <ref>` flag, then up to two positionals.
SINCE_REF=""
POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --since)
      SINCE_REF="${2:-}"
      shift
      [[ $# -gt 0 ]] && shift
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done
TASKS_FILE="${POSITIONAL[0]:-}"
PRD_FILE="${POSITIONAL[1]:-}"

TASKS_MD=""
PRD_SUMMARY=""
[[ -n "$TASKS_FILE" && -f "$TASKS_FILE" ]] && TASKS_MD="$(cat "$TASKS_FILE")"
[[ -n "$PRD_FILE" && -f "$PRD_FILE" ]] && PRD_SUMMARY="$(cat "$PRD_FILE")"

TMP_DIR="$PROJECT_ROOT/dev/local/tmp"
mkdir -p "$TMP_DIR"

# Track all created files
CREATED_FILES=()
_ID="$(date +%s)-$$"
CONTEXT_FILE="$TMP_DIR/review-context-${_ID}.md"
CREATED_FILES+=("$CONTEXT_FILE")

{
  echo "# Review Context"
  echo
  echo "## Completed Tasks"
  echo
  if [[ -n "$TASKS_MD" ]]; then
    echo "$TASKS_MD"
  else
    echo "_No tasks provided_"
  fi
  echo
  echo "## Code Changes"
  echo

  # Determine base branch
  BASE_BRANCH=""
  CURRENT_BRANCH=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)

  # Try: remote default branch (most reliable)
  if [[ -z "$BASE_BRANCH" ]]; then
    BASE_BRANCH=$(git -C "$PROJECT_ROOT" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || true)
  fi

  # Try: find merge-base with common defaults
  if [[ -z "$BASE_BRANCH" ]]; then
    for candidate in master develop; do
      if git -C "$PROJECT_ROOT" rev-parse --verify "$candidate" >/dev/null 2>&1; then
        BASE_BRANCH="$candidate"
        break
      fi
    done
  fi

  # Try: first parent of current branch's root commit (feature branch base)
  if [[ -z "$BASE_BRANCH" && -n "$CURRENT_BRANCH" ]]; then
    # Get the merge-base between HEAD and all remote tracking branches
    for remote_branch in $(git -C "$PROJECT_ROOT" branch -r 2>/dev/null | grep -v HEAD | head -5); do
      if MERGE_BASE=$(git -C "$PROJECT_ROOT" merge-base HEAD "$remote_branch" 2>/dev/null); then
        BASE_BRANCH="$remote_branch"
        break
      fi
    done
  fi

  # Resolve the diff base: an explicit, valid --since <ref> (incremental
  # rework review) overrides the detected branch base.
  DIFF_BASE="$BASE_BRANCH"
  DIFF_SCOPE="full review (vs ${BASE_BRANCH:-unknown base})"
  if [[ -n "$SINCE_REF" ]] && git -C "$PROJECT_ROOT" rev-parse --verify "$SINCE_REF" >/dev/null 2>&1; then
    DIFF_BASE="$SINCE_REF"
    DIFF_SCOPE="incremental review (changes since ${SINCE_REF})"
  fi

  if [[ -n "$DIFF_BASE" ]]; then
    echo "### Changed Files"
    echo "_Diff scope: ${DIFF_SCOPE}_"
    echo
    echo '```'
    git -C "$PROJECT_ROOT" diff "$DIFF_BASE" --stat 2>/dev/null || echo "_No diff available_"
    echo '```'
    echo
    DIFF_FILE="$TMP_DIR/review-diff-${_ID}.diff"
    git -C "$PROJECT_ROOT" diff "$DIFF_BASE" > "$DIFF_FILE" 2>/dev/null || echo "_No diff available_" > "$DIFF_FILE"
    CREATED_FILES+=("$DIFF_FILE")
    echo "### Diff Content"
    echo "Full diff available at: $DIFF_FILE"
    echo
    DIFF_LINES=$(wc -l < "$DIFF_FILE")
    echo "($DIFF_LINES lines)"
  else
    echo "_No base branch found for diff_"
  fi
  echo
  echo "## PRD Requirements"
  echo
  if [[ -n "$PRD_SUMMARY" ]]; then
    echo "$PRD_SUMMARY"
  else
    echo "_No PRD summary provided_"
  fi
} > "$CONTEXT_FILE"

# Output all created files
for f in "${CREATED_FILES[@]}"; do
  echo "$f"
done
