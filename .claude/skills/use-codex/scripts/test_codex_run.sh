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

# Reads FILE (one argv token per line, as the stub writes it) into the
# global ARGV_ARR indexed array. Bash 3.2 has no mapfile/readarray.
read_argv_array() {
    ARGV_ARR=()
    local _line
    while IFS= read -r _line; do
        ARGV_ARR+=("$_line")
    done < "$1"
}

# True (exit 0) if FILE contains NEEDLE immediately followed by VALUE as
# consecutive argv tokens.
argv_has_pair() {
    local file="$1" needle="$2" value="$3" prev="" tok
    while IFS= read -r tok; do
        if [ "$prev" = "$needle" ] && [ "$tok" = "$value" ]; then
            return 0
        fi
        prev="$tok"
    done < "$file"
    return 1
}

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

# Multi-invocation bookkeeping (opt-in: only when the caller sets
# STUB_ALL_ARGV_FILE). Appends this call's argv to a cumulative log with a
# delimiter, and bumps an invocation counter, so tests that trigger more
# than one codex call per run (resume -> fresh fallback) can verify BOTH
# calls happened.
if [ -n "${STUB_ALL_ARGV_FILE:-}" ]; then
    COUNT=$(cat "$STUB_INVOKE_COUNT_FILE" 2>/dev/null)
    COUNT=${COUNT:-0}
    COUNT=$((COUNT + 1))
    printf '%s' "$COUNT" > "$STUB_INVOKE_COUNT_FILE"
    {
        printf '%s\n' "=== invocation $COUNT ==="
        printf '%s\n' "$@"
    } >> "$STUB_ALL_ARGV_FILE"
fi

# Simulate codex's JSON path when --output-last-message <FILE> is present:
# write the review text to that file and emit JSONL events on stdout. Legacy
# (no --output-last-message) path is untouched below.
LAST_MSG_FILE=""
PREV_ARG=""
IS_RESUME=""
for arg in "$@"; do
    if [ "$PREV_ARG" = "--output-last-message" ]; then
        LAST_MSG_FILE="$arg"
    fi
    if [ "$arg" = "resume" ]; then
        IS_RESUME=1
    fi
    PREV_ARG="$arg"
done

# Forced-failure hooks: STUB_FAIL_RESUME/STUB_FAIL_FRESH make this
# invocation exit non-zero (distinguished by whether its argv is a resume
# call), simulating a real codex failure. A forced-fail invocation writes
# neither the output file nor the JSONL events, like a real failed run.
if [ -n "$IS_RESUME" ] && [ -n "${STUB_FAIL_RESUME:-}" ]; then
    exit "$STUB_FAIL_RESUME"
fi
if [ -z "$IS_RESUME" ] && [ -n "${STUB_FAIL_FRESH:-}" ]; then
    exit "$STUB_FAIL_FRESH"
fi

if [ -n "$LAST_MSG_FILE" ]; then
    printf '%s' "STUB REVIEW OUTPUT" > "$LAST_MSG_FILE"
    # STUB_SUPPRESS_THREAD_STARTED (opt-in): omit the thread.started event,
    # simulating a resumed session that doesn't re-announce its thread id.
    # Default (unset) behavior is unchanged for every other test.
    if [ -z "${STUB_SUPPRESS_THREAD_STARTED:-}" ]; then
        echo '{"type":"thread.started","thread_id":"11111111-2222-3333-4444-555555555555"}'
    fi
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
# --resume-thread <uuid>: resume argv contract. Default permission flags (no -a/-y): resume
# forces read-only via `-c sandbox_mode=read-only` because `codex exec
# resume` rejects -s/--sandbox.
# =============================================================================
RESUME_UUID="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
RESUME_PROMPT="analyze the resume case"
RESUME_OUTFILE="$STUBDIR/resume.out"
: > "$STUB_ARGV_FILE"
: > "$STUB_STDIN_FILE"
rm -f "$RESUME_OUTFILE"

PATH="$RUN_PATH" STUB_ARGV_FILE="$STUB_ARGV_FILE" STUB_STDIN_FILE="$STUB_STDIN_FILE" \
    bash "$CODEX_RUN_SH" --resume-thread "$RESUME_UUID" -o "$RESUME_OUTFILE" "$RESUME_PROMPT" \
    > /dev/null 2>/dev/null < /dev/null

read_argv_array "$STUB_ARGV_FILE"

# 14. argv starts with: exec resume <uuid>
if [ "${ARGV_ARR[0]:-}" = "exec" ] && [ "${ARGV_ARR[1]:-}" = "resume" ] && [ "${ARGV_ARR[2]:-}" = "$RESUME_UUID" ]; then
    PASS "--resume-thread: argv starts with 'exec resume <uuid>'"
else
    FAIL "--resume-thread: argv starts with 'exec resume <uuid>'" \
         "argv: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
fi

# 15. argv contains --json.
if grep -qxF -- "--json" "$STUB_ARGV_FILE"; then
    PASS "--resume-thread: argv contains --json"
else
    FAIL "--resume-thread: argv contains --json" \
         "argv: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
fi

# 16. argv contains --output-last-message <RESUME_OUTFILE>.
if argv_has_pair "$STUB_ARGV_FILE" "--output-last-message" "$RESUME_OUTFILE"; then
    PASS "--resume-thread: argv contains --output-last-message <-o target>"
else
    FAIL "--resume-thread: argv contains --output-last-message <-o target>" \
         "argv: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
fi

# 17. argv contains the exact element sandbox_mode=read-only immediately
#     preceded by -c (resume forces read-only this way; codex exec resume
#     rejects -s/--sandbox).
if argv_has_pair "$STUB_ARGV_FILE" "-c" "sandbox_mode=read-only"; then
    PASS "--resume-thread: argv contains '-c sandbox_mode=read-only'"
else
    FAIL "--resume-thread: argv contains '-c sandbox_mode=read-only'" \
         "argv: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
fi

# 18. argv contains NEITHER -s NOR --sandbox NOR --add-dir.
if grep -qxF -- "-s" "$STUB_ARGV_FILE" || grep -qxF -- "--sandbox" "$STUB_ARGV_FILE" || grep -qxF -- "--add-dir" "$STUB_ARGV_FILE"; then
    FAIL "--resume-thread: argv has neither -s, --sandbox, nor --add-dir" \
         "argv: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
else
    PASS "--resume-thread: argv has neither -s, --sandbox, nor --add-dir"
fi

# =============================================================================
# --resume-thread <FILE>: id is read from the file's first line.
# =============================================================================
RESUME_FILE_UUID="bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
RESUME_ID_FILE="$STUBDIR/resume_id.txt"
printf '%s\n' "$RESUME_FILE_UUID" > "$RESUME_ID_FILE"
RESUME_FILE_OUTFILE="$STUBDIR/resume_file.out"
: > "$STUB_ARGV_FILE"
: > "$STUB_STDIN_FILE"

PATH="$RUN_PATH" STUB_ARGV_FILE="$STUB_ARGV_FILE" STUB_STDIN_FILE="$STUB_STDIN_FILE" \
    bash "$CODEX_RUN_SH" --resume-thread "$RESUME_ID_FILE" -o "$RESUME_FILE_OUTFILE" "analyze the resume-file case" \
    > /dev/null 2>/dev/null < /dev/null

read_argv_array "$STUB_ARGV_FILE"

# 19. VALUE is a file: argv resumes with the uuid read from its first line.
if [ "${ARGV_ARR[0]:-}" = "exec" ] && [ "${ARGV_ARR[1]:-}" = "resume" ] && [ "${ARGV_ARR[2]:-}" = "$RESUME_FILE_UUID" ]; then
    PASS "--resume-thread <FILE>: resumes with the uuid read from the file's first line"
else
    FAIL "--resume-thread <FILE>: resumes with the uuid read from the file's first line" \
         "argv: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
fi

# =============================================================================
# --resume-thread "": empty id -> fresh fallback with a stderr warning.
# =============================================================================
EMPTYID_OUTFILE="$STUBDIR/emptyid.out"
EMPTYID_STDERR_FILE="$STUBDIR/emptyid.stderr"
: > "$STUB_ARGV_FILE"
: > "$STUB_STDIN_FILE"

PATH="$RUN_PATH" STUB_ARGV_FILE="$STUB_ARGV_FILE" STUB_STDIN_FILE="$STUB_STDIN_FILE" \
    bash "$CODEX_RUN_SH" --resume-thread "" -o "$EMPTYID_OUTFILE" "analyze the empty-id case" \
    > /dev/null 2> "$EMPTYID_STDERR_FILE" < /dev/null

# 20. Empty id: argv is on the fresh JSON path (exec + --json +
#     --output-last-message), NOT resume.
if grep -qxF -- "exec" "$STUB_ARGV_FILE" && grep -qxF -- "--json" "$STUB_ARGV_FILE" && \
   argv_has_pair "$STUB_ARGV_FILE" "--output-last-message" "$EMPTYID_OUTFILE" && \
   ! grep -qxF -- "resume" "$STUB_ARGV_FILE"; then
    PASS "--resume-thread '': falls back to the fresh JSON path"
else
    FAIL "--resume-thread '': falls back to the fresh JSON path" \
         "argv: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
fi

# 21. Empty id: stderr warns about the empty/unreadable id.
if grep -qi "resume" "$EMPTYID_STDERR_FILE" 2>/dev/null && grep -Eqi "empty|unreadable" "$EMPTYID_STDERR_FILE" 2>/dev/null; then
    PASS "--resume-thread '': stderr warns about the empty/unreadable id"
else
    FAIL "--resume-thread '': stderr warns about the empty/unreadable id" \
         "stderr: $(cat "$EMPTYID_STDERR_FILE" 2>/dev/null)"
fi

# =============================================================================
# --resume-thread <EMPTY_FILE>: unreadable/empty file -> same fresh fallback.
# =============================================================================
EMPTY_RESUME_FILE="$STUBDIR/empty_resume_id.txt"
: > "$EMPTY_RESUME_FILE"
EMPTYFILE_OUTFILE="$STUBDIR/emptyfile.out"
EMPTYFILE_STDERR_FILE="$STUBDIR/emptyfile.stderr"
: > "$STUB_ARGV_FILE"
: > "$STUB_STDIN_FILE"

PATH="$RUN_PATH" STUB_ARGV_FILE="$STUB_ARGV_FILE" STUB_STDIN_FILE="$STUB_STDIN_FILE" \
    bash "$CODEX_RUN_SH" --resume-thread "$EMPTY_RESUME_FILE" -o "$EMPTYFILE_OUTFILE" "analyze the empty-file case" \
    > /dev/null 2> "$EMPTYFILE_STDERR_FILE" < /dev/null

# 22. Empty file: argv is on the fresh JSON path, NOT resume.
if grep -qxF -- "exec" "$STUB_ARGV_FILE" && grep -qxF -- "--json" "$STUB_ARGV_FILE" && \
   argv_has_pair "$STUB_ARGV_FILE" "--output-last-message" "$EMPTYFILE_OUTFILE" && \
   ! grep -qxF -- "resume" "$STUB_ARGV_FILE"; then
    PASS "--resume-thread <empty file>: falls back to the fresh JSON path"
else
    FAIL "--resume-thread <empty file>: falls back to the fresh JSON path" \
         "argv: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
fi

# 23. Empty file: stderr warns about the empty/unreadable id.
if grep -qi "resume" "$EMPTYFILE_STDERR_FILE" 2>/dev/null && grep -Eqi "empty|unreadable" "$EMPTYFILE_STDERR_FILE" 2>/dev/null; then
    PASS "--resume-thread <empty file>: stderr warns about the empty/unreadable id"
else
    FAIL "--resume-thread <empty file>: stderr warns about the empty/unreadable id" \
         "stderr: $(cat "$EMPTYFILE_STDERR_FILE" 2>/dev/null)"
fi

# =============================================================================
# -d DIR + --resume-thread <uuid>: codex exec resume can't take --add-dir,
# so this combo must run fresh, not resume.
# =============================================================================
ADDDIR_OUTFILE="$STUBDIR/adddir.out"
ADDDIR_STDERR_FILE="$STUBDIR/adddir.stderr"
ADDDIR_DIR="$STUBDIR/somedir"
mkdir -p "$ADDDIR_DIR"
: > "$STUB_ARGV_FILE"
: > "$STUB_STDIN_FILE"

PATH="$RUN_PATH" STUB_ARGV_FILE="$STUB_ARGV_FILE" STUB_STDIN_FILE="$STUB_STDIN_FILE" \
    bash "$CODEX_RUN_SH" -d "$ADDDIR_DIR" --resume-thread "$RESUME_UUID" -o "$ADDDIR_OUTFILE" "analyze the add-dir case" \
    > /dev/null 2> "$ADDDIR_STDERR_FILE" < /dev/null

# 24. -d DIR + --resume-thread: argv contains --add-dir DIR but NOT resume.
if argv_has_pair "$STUB_ARGV_FILE" "--add-dir" "$ADDDIR_DIR" && ! grep -qxF -- "resume" "$STUB_ARGV_FILE" && grep -qxF -- "exec" "$STUB_ARGV_FILE"; then
    PASS "-d DIR + --resume-thread: runs fresh with --add-dir, not resume"
else
    FAIL "-d DIR + --resume-thread: runs fresh with --add-dir, not resume" \
         "argv: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
fi

# 25. -d DIR + --resume-thread: stderr warns --add-dir is unsupported on
#     resume / starting fresh.
if grep -Eqi "add-dir" "$ADDDIR_STDERR_FILE" 2>/dev/null && grep -Eqi "resume|fresh" "$ADDDIR_STDERR_FILE" 2>/dev/null; then
    PASS "-d DIR + --resume-thread: stderr warns --add-dir is unsupported on resume"
else
    FAIL "-d DIR + --resume-thread: stderr warns --add-dir is unsupported on resume" \
         "stderr: $(cat "$ADDDIR_STDERR_FILE" 2>/dev/null)"
fi

# =============================================================================
# --resume-thread <uuid> -o OUT where the resume invocation fails: bounded
# fallback to exactly one fresh invocation, whose exit code wins.
# =============================================================================
FALLBACK_OUTFILE="$STUBDIR/fallback.out"
FALLBACK_STDERR_FILE="$STUBDIR/fallback.stderr"
FALLBACK_STDOUT_FILE="$STUBDIR/fallback.stdout"
STUB_ALL_ARGV_FILE="$STUBDIR/argv_all.log"
STUB_INVOKE_COUNT_FILE="$STUBDIR/invoke_count"
: > "$STUB_ARGV_FILE"
: > "$STUB_STDIN_FILE"
: > "$STUB_ALL_ARGV_FILE"
printf '0' > "$STUB_INVOKE_COUNT_FILE"
rm -f "$FALLBACK_OUTFILE"
RESUME_FAIL_EXIT=5

FALLBACK_EXIT=0
PATH="$RUN_PATH" STUB_ARGV_FILE="$STUB_ARGV_FILE" STUB_STDIN_FILE="$STUB_STDIN_FILE" \
    STUB_ALL_ARGV_FILE="$STUB_ALL_ARGV_FILE" STUB_INVOKE_COUNT_FILE="$STUB_INVOKE_COUNT_FILE" \
    STUB_FAIL_RESUME="$RESUME_FAIL_EXIT" \
    bash "$CODEX_RUN_SH" --resume-thread "$RESUME_UUID" -o "$FALLBACK_OUTFILE" "analyze the fallback case" \
    > "$FALLBACK_STDOUT_FILE" 2> "$FALLBACK_STDERR_FILE" < /dev/null || FALLBACK_EXIT=$?

# 26. Exactly two codex invocations happened: one resume call, one fresh
#     call (only the resume call's argv contains the "resume" token).
INVOKE_COUNT=$(cat "$STUB_INVOKE_COUNT_FILE" 2>/dev/null)
RESUME_CALLS=$(grep -cxF -- "resume" "$STUB_ALL_ARGV_FILE" 2>/dev/null)
if [ "${INVOKE_COUNT:-0}" -eq 2 ] && [ "${RESUME_CALLS:-0}" -eq 1 ]; then
    PASS "resume failure: exactly one resume call and one fresh call happened"
else
    FAIL "resume failure: exactly one resume call and one fresh call happened" \
         "invocation count: ${INVOKE_COUNT:-<missing>}, resume calls: ${RESUME_CALLS:-<missing>}, log: $(tr '\n' '|' < "$STUB_ALL_ARGV_FILE" 2>/dev/null)"
fi

# 27. Fresh fallback succeeds and its exit code (0) is codex-run.sh's own
#     overall exit code.
if [ "$FALLBACK_EXIT" -eq 0 ]; then
    PASS "resume failure: overall exit code is the fresh run's (0)"
else
    FAIL "resume failure: overall exit code is the fresh run's (0)" \
         "got exit code $FALLBACK_EXIT"
fi

# 28. stderr names the real resume exit code in its warning.
if grep -q "$RESUME_FAIL_EXIT" "$FALLBACK_STDERR_FILE" 2>/dev/null && grep -qi "resume" "$FALLBACK_STDERR_FILE" 2>/dev/null; then
    PASS "resume failure: stderr names the real resume exit code"
else
    FAIL "resume failure: stderr names the real resume exit code" \
         "stderr: $(cat "$FALLBACK_STDERR_FILE" 2>/dev/null)"
fi

# =============================================================================
# --emit-thread-id THREADFILE -o OUT (JSON path, no resume) where codex
# exits non-zero: codex-run.sh's exit code must equal codex's (regression
# lock for the pipefail exit-capture idiom; may already PASS today).
# =============================================================================
FRESHFAIL_THREAD_ID_FILE="$STUBDIR/freshfail_thread_id.out"
FRESHFAIL_OUTFILE="$STUBDIR/freshfail.out"
FRESHFAIL_STDERR_FILE="$STUBDIR/freshfail.stderr"
: > "$STUB_ARGV_FILE"
: > "$STUB_STDIN_FILE"
FRESH_FAIL_EXIT=7

FRESHFAIL_EXIT=0
PATH="$RUN_PATH" STUB_ARGV_FILE="$STUB_ARGV_FILE" STUB_STDIN_FILE="$STUB_STDIN_FILE" \
    STUB_FAIL_FRESH="$FRESH_FAIL_EXIT" \
    bash "$CODEX_RUN_SH" --emit-thread-id "$FRESHFAIL_THREAD_ID_FILE" -o "$FRESHFAIL_OUTFILE" "analyze the fresh-fail case" \
    > /dev/null 2> "$FRESHFAIL_STDERR_FILE" < /dev/null || FRESHFAIL_EXIT=$?

# 29. Fresh-path exit propagation: codex-run.sh's exit code equals codex's.
if [ "$FRESHFAIL_EXIT" -eq "$FRESH_FAIL_EXIT" ]; then
    PASS "fresh JSON path: codex-run.sh exit code equals codex's non-zero exit code"
else
    FAIL "fresh JSON path: codex-run.sh exit code equals codex's non-zero exit code" \
         "got exit code $FRESHFAIL_EXIT, expected $FRESH_FAIL_EXIT"
fi

# =============================================================================
# --resume-thread without -o must fail fast and never invoke codex.
# =============================================================================
NOOUT_RESUME_STDOUT_FILE="$STUBDIR/noout_resume.stdout"
NOOUT_RESUME_STDERR_FILE="$STUBDIR/noout_resume.stderr"
: > "$STUB_ARGV_FILE"
: > "$STUB_STDIN_FILE"

PATH="$RUN_PATH" STUB_ARGV_FILE="$STUB_ARGV_FILE" STUB_STDIN_FILE="$STUB_STDIN_FILE" \
    bash "$CODEX_RUN_SH" --resume-thread "$RESUME_UUID" "analyze without -o" \
    > "$NOOUT_RESUME_STDOUT_FILE" 2> "$NOOUT_RESUME_STDERR_FILE" < /dev/null
NOOUT_RESUME_EXIT=$?

# 30. Missing -o is a hard error: exit 1.
if [ "$NOOUT_RESUME_EXIT" -eq 1 ]; then
    PASS "--resume-thread without -o exits 1"
else
    FAIL "--resume-thread without -o exits 1" \
         "got exit code $NOOUT_RESUME_EXIT"
fi

# 31. Error message references the -o requirement (design message:
#     `ERROR: --resume-thread requires -o`).
if grep -qi "require" "$NOOUT_RESUME_STDOUT_FILE" "$NOOUT_RESUME_STDERR_FILE" 2>/dev/null && \
   grep -qF -- "-o" "$NOOUT_RESUME_STDOUT_FILE" "$NOOUT_RESUME_STDERR_FILE" 2>/dev/null; then
    PASS "--resume-thread without -o: error message names the -o requirement"
else
    FAIL "--resume-thread without -o: error message names the -o requirement" \
         "stdout: $(cat "$NOOUT_RESUME_STDOUT_FILE") -- stderr: $(cat "$NOOUT_RESUME_STDERR_FILE")"
fi

# 32. codex must never be invoked when --resume-thread lacks -o.
if [ -s "$STUB_ARGV_FILE" ]; then
    FAIL "--resume-thread without -o: codex is never invoked" \
         "argv file non-empty: $(tr '\n' ' ' < "$STUB_ARGV_FILE")"
else
    PASS "--resume-thread without -o: codex is never invoked"
fi

# =============================================================================
# --resume-thread <uuid> --emit-thread-id THREADFILE: successful resume run
# (codex exits 0) where the resumed session emits NO thread.started event.
# Resume doesn't change a session's thread id, so THREADFILE must still end
# up holding the id we resumed with -- otherwise the next cycle couldn't
# resume.
# =============================================================================
RESUME_NOSTART_OUTFILE="$STUBDIR/resume_nostart.out"
RESUME_NOSTART_THREAD_ID_FILE="$STUBDIR/resume_nostart_thread_id.out"
: > "$STUB_ARGV_FILE"
: > "$STUB_STDIN_FILE"
rm -f "$RESUME_NOSTART_OUTFILE" "$RESUME_NOSTART_THREAD_ID_FILE"

PATH="$RUN_PATH" STUB_ARGV_FILE="$STUB_ARGV_FILE" STUB_STDIN_FILE="$STUB_STDIN_FILE" \
    STUB_SUPPRESS_THREAD_STARTED=1 \
    bash "$CODEX_RUN_SH" --resume-thread "$RESUME_UUID" --emit-thread-id "$RESUME_NOSTART_THREAD_ID_FILE" \
    -o "$RESUME_NOSTART_OUTFILE" "analyze the resume no-thread-started case" \
    > /dev/null 2>/dev/null < /dev/null

# 33. resume with no thread.started: THREADFILE holds the resume uuid
if [ "$(cat "$RESUME_NOSTART_THREAD_ID_FILE" 2>/dev/null)" = "$RESUME_UUID" ]; then
    PASS "resume with no thread.started: THREADFILE holds the resume uuid"
else
    FAIL "resume with no thread.started: THREADFILE holds the resume uuid" \
         "got: $(cat "$RESUME_NOSTART_THREAD_ID_FILE" 2>/dev/null || echo '<missing>')"
fi

# =============================================================================
echo ""
echo "SUMMARY: $PASS_COUNT passed, $FAIL_COUNT failed"

[ "$FAIL_COUNT" -eq 0 ]
