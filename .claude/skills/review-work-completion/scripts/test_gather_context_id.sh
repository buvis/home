#!/usr/bin/env bash
# Regression: gather-context.sh reuses the caller's cycle id from
# review-prd-{id}.md so tmp review debris is PRD-linked (and dies with its
# PRD in purge-devlocal) instead of carrying an unlinkable epoch-pid name.
set -u

PASS() { echo "PASS: $1"; }
FAIL() { echo "FAIL: $1 — $2"; exit 1; }

SCRIPT="$HOME/.claude/skills/review-work-completion/scripts/gather-context.sh"
DIR="$(mktemp -d)"
trap 'rm -rf "$DIR"' EXIT
cd "$DIR"
git init -q .
git commit -q --allow-empty -m init
mkdir -p dev/local/tmp
echo "tasks" > dev/local/tmp/review-tasks-00042c1.md
echo "prd" > dev/local/tmp/review-prd-00042c1.md

OUT="$(bash "$SCRIPT" dev/local/tmp/review-tasks-00042c1.md dev/local/tmp/review-prd-00042c1.md)"
echo "$OUT" | grep -q "review-context-00042c1\.md" \
  || FAIL "prd-linked id" "expected review-context-00042c1.md in: $OUT"
PASS "context file reuses caller cycle id"

OUT2="$(bash "$SCRIPT")"
echo "$OUT2" | grep -qE "review-context-[0-9]{9,}-[0-9]+\.md" \
  || FAIL "fallback id" "expected epoch-pid name in: $OUT2"
PASS "fallback epoch-pid id when no prd file given"
