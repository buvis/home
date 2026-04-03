#!/usr/bin/env bash
# Gathers review context into dev/local/tmp/
# Usage: gather-context.sh [tasks_file] [prd_summary_file]
#   tasks_file:       path to file containing tasks markdown (optional)
#   prd_summary_file: path to file containing PRD summary (optional)
# Outputs: paths to created files (one per line)

set -euo pipefail

PROJECT_ROOT="$(pwd)"
TASKS_FILE="${1:-}"
PRD_FILE="${2:-}"

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
    BASE_BRANCH=$(git -C "$PROJECT_ROOT" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
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

  if [[ -n "$BASE_BRANCH" ]]; then
    echo "### Changed Files"
    echo '```'
    git -C "$PROJECT_ROOT" diff "$BASE_BRANCH" --stat 2>/dev/null || echo "_No diff available_"
    echo '```'
    echo
    DIFF_FILE="$TMP_DIR/review-diff-${_ID}.diff"
    git -C "$PROJECT_ROOT" diff "$BASE_BRANCH" > "$DIFF_FILE" 2>/dev/null || echo "_No diff available_" > "$DIFF_FILE"
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
