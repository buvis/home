#!/usr/bin/env bash
# Test harness for codex-run.sh (macOS bash 3.2 compatible). Stubs the `codex`
# binary on PATH and asserts on its OBSERVABLE argv/stdin, never on
# codex-run.sh's internals. Extend this file with more assertions/invocations
# as codex-run.sh grows new behavior (thread-id capture, resume, etc.).
set -u

CODEX_RUN_SH=/Users/bob/.claude/skills/use-codex/scripts/codex-run.sh

# ── assert helpers ────────────────────────────────────────────────────────────
PASS_COUNT=0
FAIL_COUNT=0
PASS() { echo "PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
FAIL() { echo "FAIL: $1 -- $2"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

# ── cleanup registry ────────────────────────────────────────────────────────────
_DIRS=()
cleanup() {
    local d
    for d in "${_DIRS[@]+"${_DIRS[@]}"}"; do
        rm -rf "$d"
    done
}
trap cleanup EXIT

# ── stub `codex` binary on PATH ────────────────────────────────────────────────
STUBDIR=$(mktemp -d)
_DIRS+=("$STUBDIR")

STUB_ARGV_FILE="$STUBDIR/argv.log"
STUB_STDIN_FILE="$STUBDIR/stdin.log"

cat > "$STUBDIR/codex" <<'STUB'
#!/bin/bash
printf '%s\n' "$@" > "$STUB_ARGV_FILE"
cat > "$STUB_STDIN_FILE"
exit 0
STUB
chmod +x "$STUBDIR/codex"

# codex-run.sh re-prepends mise's own PATH ahead of ours whenever `mise` is
# reachable, and mise's PATH includes /opt/homebrew/bin (the REAL codex
# binary), which would shadow the stub. Excluding mise's location from the
# PATH we hand to codex-run.sh keeps that branch inert, so lookup always
# resolves to our stub.
RUN_PATH="$STUBDIR:/usr/bin:/bin"

# =============================================================================
# Single invocation feeds both assertions below: sentinel, non-empty, non-EOF
# stdin on the wrapper's own stdin, no permission flags.
# =============================================================================
SENTINEL_PROMPT="analyze the sentinel case"
: > "$STUB_ARGV_FILE"
: > "$STUB_STDIN_FILE"

PATH="$RUN_PATH" STUB_ARGV_FILE="$STUB_ARGV_FILE" STUB_STDIN_FILE="$STUB_STDIN_FILE" \
    bash "$CODEX_RUN_SH" "$SENTINEL_PROMPT" <<< 'SENTINEL_STDIN_DATA'

# 1. Codex child stdin must be redirected to /dev/null. Without the guard the
#    child inherits the wrapper's stdin and would read SENTINEL_STDIN_DATA.
if [ -s "$STUB_STDIN_FILE" ]; then
    FAIL "codex child stdin is /dev/null" \
         "stub captured $(wc -c < "$STUB_STDIN_FILE" | tr -d ' ') byte(s) of stdin; expected 0 (child inherited the wrapper's stdin instead of /dev/null)"
else
    PASS "codex child stdin is /dev/null"
fi

# 2. Argv regression lock: adding the stdin guard must not perturb argv.
EXPECTED_ARGV_FILE="$STUBDIR/argv.expected"
printf '%s\n' "exec" "--skip-git-repo-check" "--sandbox" "read-only" "$SENTINEL_PROMPT" > "$EXPECTED_ARGV_FILE"

if diff -q "$EXPECTED_ARGV_FILE" "$STUB_ARGV_FILE" >/dev/null 2>&1; then
    PASS "no-flag argv is exactly: codex exec --skip-git-repo-check --sandbox read-only <PROMPT>"
else
    FAIL "no-flag argv is exactly: codex exec --skip-git-repo-check --sandbox read-only <PROMPT>" \
         "got: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
fi

# =============================================================================
echo ""
echo "SUMMARY: $PASS_COUNT passed, $FAIL_COUNT failed"

[ "$FAIL_COUNT" -eq 0 ]
