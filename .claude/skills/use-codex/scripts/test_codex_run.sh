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

# Simulate codex's JSON path when --output-last-message <FILE> is present:
# write the review text to that file and emit JSONL events on stdout. Legacy
# (no --output-last-message) path is untouched below.
LAST_MSG_FILE=""
PREV_ARG=""
for arg in "$@"; do
    if [ "$PREV_ARG" = "--output-last-message" ]; then
        LAST_MSG_FILE="$arg"
    fi
    PREV_ARG="$arg"
done

if [ -n "$LAST_MSG_FILE" ]; then
    printf '%s' "STUB REVIEW OUTPUT" > "$LAST_MSG_FILE"
    echo '{"type":"thread.started","thread_id":"11111111-2222-3333-4444-555555555555"}'
    echo '{"type":"item.completed"}'
    echo '{"type":"turn.completed"}'
fi

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
# --emit-thread-id JSON path: codex invoked with --json/--output-last-message,
# thread id captured from the thread.started event, review text delivered via
# -o (tee-parity), raw JSONL surfaced only as stderr liveness markers.
# =============================================================================
FIXED_UUID="11111111-2222-3333-4444-555555555555"
THREAD_PROMPT="analyze the thread case"
THREAD_ID_FILE="$STUBDIR/thread_id.out"
JSON_OUTFILE="$STUBDIR/review.out"
JSON_STDOUT_FILE="$STUBDIR/thread.stdout"
JSON_STDERR_FILE="$STUBDIR/thread.stderr"
: > "$STUB_ARGV_FILE"
: > "$STUB_STDIN_FILE"
rm -f "$THREAD_ID_FILE" "$JSON_OUTFILE"

PATH="$RUN_PATH" STUB_ARGV_FILE="$STUB_ARGV_FILE" STUB_STDIN_FILE="$STUB_STDIN_FILE" \
    bash "$CODEX_RUN_SH" --emit-thread-id "$THREAD_ID_FILE" -o "$JSON_OUTFILE" "$THREAD_PROMPT" \
    > "$JSON_STDOUT_FILE" 2> "$JSON_STDERR_FILE" <<< 'SENTINEL_STDIN_DATA'

# 3. codex is invoked on the JSON path: argv contains --json.
if grep -qxF -- "--json" "$STUB_ARGV_FILE"; then
    PASS "--emit-thread-id: codex argv contains --json"
else
    FAIL "--emit-thread-id: codex argv contains --json" \
         "argv: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
fi

# 4. --output-last-message's value is exactly the -o target (the review text
#    is delivered via --output-last-message, not plain stdout).
OUTLAST_VALUE=""
PREV_TOK=""
while IFS= read -r TOK; do
    if [ "$PREV_TOK" = "--output-last-message" ]; then
        OUTLAST_VALUE="$TOK"
    fi
    PREV_TOK="$TOK"
done < "$STUB_ARGV_FILE"

if [ "$OUTLAST_VALUE" = "$JSON_OUTFILE" ]; then
    PASS "--emit-thread-id: codex argv --output-last-message value is the -o target"
else
    FAIL "--emit-thread-id: codex argv --output-last-message value is the -o target" \
         "got --output-last-message value '$OUTLAST_VALUE', expected '$JSON_OUTFILE' -- argv: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
fi

# 5. Thread id captured: THREADFILE holds exactly the thread.started uuid
#    (plus optional trailing newline), nothing else.
if [ "$(cat "$THREAD_ID_FILE" 2>/dev/null)" = "$FIXED_UUID" ]; then
    PASS "--emit-thread-id: THREADFILE contains exactly the thread.started uuid"
else
    FAIL "--emit-thread-id: THREADFILE contains exactly the thread.started uuid" \
         "got: $(cat "$THREAD_ID_FILE" 2>/dev/null || echo '<missing>')"
fi

# 6. Output contract: OUTFILE gets the review text.
if grep -qF "STUB REVIEW OUTPUT" "$JSON_OUTFILE" 2>/dev/null; then
    PASS "--emit-thread-id: OUTFILE contains the review text"
else
    FAIL "--emit-thread-id: OUTFILE contains the review text" \
         "OUTFILE contents: $(cat "$JSON_OUTFILE" 2>/dev/null || echo '<missing>')"
fi

# 7. Output contract: codex-run.sh's own stdout also carries the review text
#    (tee-parity for downstream consumers).
if grep -qF "STUB REVIEW OUTPUT" "$JSON_STDOUT_FILE"; then
    PASS "--emit-thread-id: codex-run.sh stdout contains the review text"
else
    FAIL "--emit-thread-id: codex-run.sh stdout contains the review text" \
         "stdout contents: $(cat "$JSON_STDOUT_FILE")"
fi

# 8. Output contract: raw JSONL events must never leak onto codex-run.sh's
#    own stdout.
if grep -qF "thread.started" "$JSON_STDOUT_FILE"; then
    FAIL "--emit-thread-id: raw JSONL does not leak onto stdout" \
         "stdout contents: $(cat "$JSON_STDOUT_FILE")"
else
    PASS "--emit-thread-id: raw JSONL does not leak onto stdout"
fi

# 9. Liveness markers: every JSONL event codex emits gets a
#    'codex-event: <type>' marker on stderr.
if grep -qxF "codex-event: thread.started" "$JSON_STDERR_FILE" && \
   grep -qxF "codex-event: item.completed" "$JSON_STDERR_FILE" && \
   grep -qxF "codex-event: turn.completed" "$JSON_STDERR_FILE"; then
    PASS "--emit-thread-id: stderr carries a codex-event marker per JSONL event"
else
    FAIL "--emit-thread-id: stderr carries a codex-event marker per JSONL event" \
         "stderr contents: $(cat "$JSON_STDERR_FILE" | tr '\n' '|')"
fi

# 10. stdin guard still applies on the JSON-path codex invocation.
if [ -s "$STUB_STDIN_FILE" ]; then
    FAIL "--emit-thread-id: codex child stdin is /dev/null" \
         "stub captured $(wc -c < "$STUB_STDIN_FILE" | tr -d ' ') byte(s) of stdin"
else
    PASS "--emit-thread-id: codex child stdin is /dev/null"
fi

# =============================================================================
# --emit-thread-id without -o must fail fast and never invoke codex.
# =============================================================================
NOOUT_THREAD_ID_FILE="$STUBDIR/thread_id_noout.out"
NOOUT_STDOUT_FILE="$STUBDIR/noout.stdout"
NOOUT_STDERR_FILE="$STUBDIR/noout.stderr"
: > "$STUB_ARGV_FILE"
: > "$STUB_STDIN_FILE"

PATH="$RUN_PATH" STUB_ARGV_FILE="$STUB_ARGV_FILE" STUB_STDIN_FILE="$STUB_STDIN_FILE" \
    bash "$CODEX_RUN_SH" --emit-thread-id "$NOOUT_THREAD_ID_FILE" "analyze without -o" \
    > "$NOOUT_STDOUT_FILE" 2> "$NOOUT_STDERR_FILE" < /dev/null
NOOUT_EXIT=$?

# 11. Missing -o is a hard error: exit 1.
if [ "$NOOUT_EXIT" -eq 1 ]; then
    PASS "--emit-thread-id without -o exits 1"
else
    FAIL "--emit-thread-id without -o exits 1" \
         "got exit code $NOOUT_EXIT"
fi

# 12. Error message names the missing requirement. Per the design contract the
#     message is `ERROR: --emit-thread-id requires -o`, so it must reference the
#     `-o` flag and the requirement (matches "requires"/"required"); it need not
#     contain the literal word "output".
if grep -qi "require" "$NOOUT_STDOUT_FILE" "$NOOUT_STDERR_FILE" 2>/dev/null && \
   grep -qF -- "-o" "$NOOUT_STDOUT_FILE" "$NOOUT_STDERR_FILE" 2>/dev/null; then
    PASS "--emit-thread-id without -o: error message names the -o requirement"
else
    FAIL "--emit-thread-id without -o: error message names the -o requirement" \
         "stdout: $(cat "$NOOUT_STDOUT_FILE") -- stderr: $(cat "$NOOUT_STDERR_FILE")"
fi

# 13. codex must never be invoked when the -o/--emit-thread-id pairing is invalid.
if [ -s "$STUB_ARGV_FILE" ]; then
    FAIL "--emit-thread-id without -o: codex is never invoked" \
         "argv file non-empty: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
else
    PASS "--emit-thread-id without -o: codex is never invoked"
fi

# =============================================================================
echo ""
echo "SUMMARY: $PASS_COUNT passed, $FAIL_COUNT failed"

[ "$FAIL_COUNT" -eq 0 ]
