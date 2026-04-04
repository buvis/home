#!/bin/bash
# Branch diff: show changes since fork from base branch
# Outputs metadata AND full diff — caller has context budget for it

set -e

# Get current branch
CURRENT=$(git branch --show-current)

if [ -z "$CURRENT" ]; then
    echo "SKIP: Detached HEAD state (commit $(git rev-parse --short HEAD))"
    exit 0
fi

# Check if on base branch
if [ "$CURRENT" = "master" ]; then
    echo "SKIP: On base branch ($CURRENT), no branch diff needed"
    exit 0
fi

# Detect base branch
if git rev-parse --verify origin/master >/dev/null 2>&1; then
    BASE="origin/master"
elif git rev-parse --verify master >/dev/null 2>&1; then
    BASE="master"
else
    echo "ERROR: Cannot find master branch"
    exit 1
fi

# Fetch latest
echo "Fetching latest from ${BASE}..."
git fetch origin "${BASE#origin/}" 2>/dev/null || true

# Find fork point
FORK_POINT=$(git merge-base "$BASE" HEAD)

echo ""
echo "=== Branch Info ==="
echo "Current branch: $CURRENT"
echo "Base branch:    $BASE"
echo "Fork point:     ${FORK_POINT:0:8}"
echo ""

echo "=== Changed Files ==="
git diff "$FORK_POINT"..HEAD --name-only
echo ""

echo "=== Diff Stats ==="
git diff "$FORK_POINT"..HEAD --stat
echo ""

echo "=== Commit History ==="
git log "$FORK_POINT"..HEAD --oneline
echo ""

echo "=== Full Diff ==="
git diff "$FORK_POINT"..HEAD
