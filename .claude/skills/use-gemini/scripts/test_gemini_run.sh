#!/usr/bin/env bash
# Test harness for gemini-run.sh (macOS bash 3.2 compatible). Stubs the
# `copilot` and `gemini` binaries on PATH and asserts on their OBSERVABLE
# argv/stdin/exit codes, never on gemini-run.sh's internals. Modeled on
# use-codex/scripts/test_codex_run.sh.
set -u

GEMINI_RUN_SH=/Users/bob/.claude/skills/use-gemini/scripts/gemini-run.sh
[ -n "${1:-}" ] && GEMINI_RUN_SH="$1"

# ── assert helpers ────────────────────────────────────────────────────────────
PASS_COUNT=0
FAIL_COUNT=0
PASS() { echo "PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
FAIL() { echo "FAIL: $1 -- $2"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

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

# ── cleanup registry ──────────────────────────────────────────────────────────
_DIRS=()
cleanup() {
    local d
    for d in "${_DIRS[@]+"${_DIRS[@]}"}"; do
        rm -rf "$d"
    done
}
trap cleanup EXIT

WORK=$(mktemp -d)
_DIRS+=("$WORK")

# ── stub `copilot` and `gemini` binaries on PATH ──────────────────────────────
STUBDIR="$WORK/stub"
mkdir -p "$STUBDIR"

cat > "$STUBDIR/copilot" <<'STUB'
#!/bin/bash
printf '%s\n' "$@" > "${COPILOT_ARGV_FILE:?}"
cat > "${COPILOT_STDIN_FILE:?}"
echo "stub-copilot-ran"
exit "${STUB_EXIT_CODE:-0}"
STUB
chmod +x "$STUBDIR/copilot"

cat > "$STUBDIR/gemini" <<'STUB'
#!/bin/bash
printf '%s\n' "$@" > "${GEMINI_ARGV_FILE:?}"
cat > "${GEMINI_STDIN_FILE:?}"
echo "stub-gemini-ran"
exit "${STUB_EXIT_CODE:-0}"
STUB
chmod +x "$STUBDIR/gemini"

# gemini-run.sh re-prepends mise's own PATH ahead of ours whenever `mise` is
# reachable, which would put the real binaries ahead of the stubs. Excluding
# mise's location from the PATH we hand to gemini-run.sh keeps that branch
# inert, so lookup always resolves to our stubs.
RUN_PATH="$STUBDIR:/usr/bin:/bin"

GEMINI_PROMPT="say hi from gemini"
PROMPT_FILE_T="$WORK/prompt.txt"
printf '%s' "$GEMINI_PROMPT" > "$PROMPT_FILE_T"

# run_gemini <name> [args...] — runs gemini-run.sh with SENTINEL data on the
# wrapper's own stdin; sets RC, STDOUT_F, STDERR_F, and per-test capture paths.
run_gemini() {
    local name="$1"
    shift
    export COPILOT_ARGV_FILE="$WORK/$name.copilot.argv"
    export COPILOT_STDIN_FILE="$WORK/$name.copilot.stdin"
    export GEMINI_ARGV_FILE="$WORK/$name.gemini.argv"
    export GEMINI_STDIN_FILE="$WORK/$name.gemini.stdin"
    STDOUT_F="$WORK/$name.stdout"
    STDERR_F="$WORK/$name.stderr"
    RC=0
    PATH="$RUN_PATH" bash "$GEMINI_RUN_SH" "$@" \
        > "$STDOUT_F" 2> "$STDERR_F" <<< 'SENTINEL_STDIN_DATA' || RC=$?
}

# ══ T1: plain -f run on the preferred copilot backend ═════════════════════════
run_gemini t1 -f "$PROMPT_FILE_T"

# 1. Child stdin must be redirected to /dev/null. Without the guard the child
#    inherits the wrapper's stdin and reads SENTINEL_STDIN_DATA (the PRD 00040
#    hang class: a child blocking on inherited stdin stalls unattended runs).
if [ -f "$COPILOT_STDIN_FILE" ] && [ ! -s "$COPILOT_STDIN_FILE" ]; then
    PASS "copilot child stdin is /dev/null"
else
    FAIL "copilot child stdin is /dev/null" \
         "stub captured $(wc -c < "$COPILOT_STDIN_FILE" 2>/dev/null | tr -d ' ' || echo '?') byte(s) of stdin; expected 0 (child inherited the wrapper's stdin instead of /dev/null)"
fi

# 2. Argv regression lock for the plain -f run (adding the stdin guard must
#    not perturb argv): --model <default> + read-review perms + -p <prompt>.
EXPECTED_ARGV_FILE="$WORK/t1.expected"
printf '%s\n' "--model" "gemini-3.1-pro-preview" "--allow-all-tools" "--deny-tool=write" "-p" "$GEMINI_PROMPT" > "$EXPECTED_ARGV_FILE"
if diff -q "$EXPECTED_ARGV_FILE" "$COPILOT_ARGV_FILE" >/dev/null 2>&1; then
    PASS "plain -f argv is exactly: --model gemini-3.1-pro-preview --allow-all-tools --deny-tool=write -p <PROMPT>"
else
    FAIL "plain -f argv is exactly: --model gemini-3.1-pro-preview --allow-all-tools --deny-tool=write -p <PROMPT>" \
         "got: $(tr '\n' ' ' < "$COPILOT_ARGV_FILE" 2>/dev/null || echo '<no copilot invocation>')"
fi

# 3. Backend order: with both CLIs present, copilot is preferred and the
#    native gemini CLI is never invoked.
if [ ! -f "$GEMINI_ARGV_FILE" ]; then
    PASS "copilot preferred: native gemini CLI is not invoked when copilot exists"
else
    FAIL "copilot preferred: native gemini CLI is not invoked when copilot exists" \
         "gemini stub ran with argv: $(tr '\n' ' ' < "$GEMINI_ARGV_FILE")"
fi

# 4. Happy path exits 0 and surfaces the backend's output.
if [ "$RC" -eq 0 ] && grep -qF "stub-copilot-ran" "$STDOUT_F"; then
    PASS "plain -f run exits 0 and passes backend stdout through"
else
    FAIL "plain -f run exits 0 and passes backend stdout through" \
         "rc=$RC; stdout: $(cat "$STDOUT_F")"
fi

# ══ T2: -o tees output to the file ════════════════════════════════════════════
T2_OUT="$WORK/t2.out"
run_gemini t2 -f "$PROMPT_FILE_T" -o "$T2_OUT"

# 5. -o: output file receives the backend output.
if grep -qF "stub-copilot-ran" "$T2_OUT" 2>/dev/null; then
    PASS "-o: output file contains the backend output"
else
    FAIL "-o: output file contains the backend output" \
         "rc=$RC; -o file contents: $(cat "$T2_OUT" 2>/dev/null || echo '<missing>')"
fi

# ══ T3: GEMINI_BACKEND=gemini forces the native backend ═══════════════════════
export GEMINI_BACKEND=gemini
run_gemini t3 -f "$PROMPT_FILE_T"
unset GEMINI_BACKEND

# 6. Forced native backend: gemini argv is exactly --skip-trust -p <prompt>.
EXPECTED_NATIVE_ARGV_FILE="$WORK/t3.expected"
printf '%s\n' "--skip-trust" "-p" "$GEMINI_PROMPT" > "$EXPECTED_NATIVE_ARGV_FILE"
if diff -q "$EXPECTED_NATIVE_ARGV_FILE" "$GEMINI_ARGV_FILE" >/dev/null 2>&1; then
    PASS "GEMINI_BACKEND=gemini: native argv is exactly --skip-trust -p <PROMPT>"
else
    FAIL "GEMINI_BACKEND=gemini: native argv is exactly --skip-trust -p <PROMPT>" \
         "got: $(tr '\n' ' ' < "$GEMINI_ARGV_FILE" 2>/dev/null || echo '<no gemini invocation>')"
fi

# 7. Forced native backend: copilot is never invoked.
if [ ! -f "$COPILOT_ARGV_FILE" ]; then
    PASS "GEMINI_BACKEND=gemini: copilot is not invoked"
else
    FAIL "GEMINI_BACKEND=gemini: copilot is not invoked" \
         "copilot stub ran with argv: $(tr '\n' ' ' < "$COPILOT_ARGV_FILE")"
fi

# 8. Stdin guard holds on the native backend too.
if [ -f "$GEMINI_STDIN_FILE" ] && [ ! -s "$GEMINI_STDIN_FILE" ]; then
    PASS "native gemini child stdin is /dev/null"
else
    FAIL "native gemini child stdin is /dev/null" \
         "stub captured $(wc -c < "$GEMINI_STDIN_FILE" 2>/dev/null | tr -d ' ' || echo '?') byte(s) of stdin; expected 0"
fi

# ══ T4: copilot absent -> native gemini fallback ══════════════════════════════
FALLBACK_STUBDIR="$WORK/stub-gemini-only"
mkdir -p "$FALLBACK_STUBDIR"
cp "$STUBDIR/gemini" "$FALLBACK_STUBDIR/gemini"
SAVED_RUN_PATH="$RUN_PATH"
RUN_PATH="$FALLBACK_STUBDIR:/usr/bin:/bin"
run_gemini t4 -f "$PROMPT_FILE_T"
RUN_PATH="$SAVED_RUN_PATH"

# 9. Fallback order: with copilot absent, the native gemini CLI serves the run.
if [ -f "$GEMINI_ARGV_FILE" ] && argv_has_pair "$GEMINI_ARGV_FILE" "-p" "$GEMINI_PROMPT" && [ "$RC" -eq 0 ]; then
    PASS "copilot absent: falls back to the native gemini CLI"
else
    FAIL "copilot absent: falls back to the native gemini CLI" \
         "rc=$RC; gemini argv: $(tr '\n' ' ' < "$GEMINI_ARGV_FILE" 2>/dev/null || echo '<no gemini invocation>'); stderr: $(cat "$STDERR_F")"
fi

# ══ T5: -s/--silent maps to copilot's -s ══════════════════════════════════════
run_gemini t5 -s -f "$PROMPT_FILE_T"

# 10. -s: accepted and forwarded to the copilot backend as -s.
if [ "$RC" -eq 0 ] && grep -qxF -- "-s" "$COPILOT_ARGV_FILE" 2>/dev/null; then
    PASS "-s is accepted and forwarded to copilot"
else
    FAIL "-s is accepted and forwarded to copilot" \
         "rc=$RC; argv: $(tr '\n' ' ' < "$COPILOT_ARGV_FILE" 2>/dev/null || echo '<no copilot invocation>')"
fi

# ══ T6: missing prompt file -> stderr + non-zero + no dispatch ════════════════
run_gemini t6 -f "$WORK/does-not-exist.txt"

# 11. Missing prompt file: non-zero exit.
if [ "$RC" -ne 0 ]; then
    PASS "missing prompt file exits non-zero"
else
    FAIL "missing prompt file exits non-zero" "rc=0"
fi

# 12. Missing prompt file: the error lands on stderr, not stdout.
if grep -q "not found" "$STDERR_F" 2>/dev/null && ! grep -q "not found" "$STDOUT_F" 2>/dev/null; then
    PASS "missing prompt file: error text is on stderr"
else
    FAIL "missing prompt file: error text is on stderr" \
         "stderr: $(cat "$STDERR_F") -- stdout: $(cat "$STDOUT_F")"
fi

# 13. Missing prompt file: no backend is ever invoked.
if [ ! -f "$COPILOT_ARGV_FILE" ] && [ ! -f "$GEMINI_ARGV_FILE" ]; then
    PASS "missing prompt file: no backend CLI is invoked"
else
    FAIL "missing prompt file: no backend CLI is invoked" \
         "copilot: $(cat "$COPILOT_ARGV_FILE" 2>/dev/null || echo -) gemini: $(cat "$GEMINI_ARGV_FILE" 2>/dev/null || echo -)"
fi

# ══ T7: no prompt at all -> stderr + non-zero ═════════════════════════════════
run_gemini t7

# 14. Missing prompt: non-zero exit with the error on stderr.
if [ "$RC" -ne 0 ] && grep -qi "prompt required" "$STDERR_F" 2>/dev/null; then
    PASS "missing prompt exits non-zero with the error on stderr"
else
    FAIL "missing prompt exits non-zero with the error on stderr" \
         "rc=$RC; stderr: $(cat "$STDERR_F") -- stdout: $(cat "$STDOUT_F")"
fi

# ══ T8: child exit code propagates ════════════════════════════════════════════
export STUB_EXIT_CODE=7
run_gemini t8 -f "$PROMPT_FILE_T"
unset STUB_EXIT_CODE

# 15. Exit-code propagation: the wrapper's exit code equals the child's.
if [ "$RC" -eq 7 ]; then
    PASS "child exit code (7) propagates as gemini-run.sh's own exit code"
else
    FAIL "child exit code (7) propagates as gemini-run.sh's own exit code" \
         "got exit code $RC"
fi

# ══ summary ═══════════════════════════════════════════════════════════════════
echo ""
echo "SUMMARY: $PASS_COUNT passed, $FAIL_COUNT failed"

[ "$FAIL_COUNT" -eq 0 ]
