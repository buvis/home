#!/usr/bin/env bash
# Test harness for sonnet-run.sh (macOS bash 3.2 compatible). Stubs the
# `claude` binary on PATH and asserts on its OBSERVABLE argv/stdin/exit codes,
# never on sonnet-run.sh's internals. Modeled on
# use-codex/scripts/test_codex_run.sh.
set -u

SONNET_RUN_SH=/Users/bob/.claude/skills/use-sonnet/scripts/sonnet-run.sh
[ -n "${1:-}" ] && SONNET_RUN_SH="$1"

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

# ── stub `claude` binary on PATH ──────────────────────────────────────────────
STUBDIR="$WORK/stub"
mkdir -p "$STUBDIR"

cat > "$STUBDIR/claude" <<'STUB'
#!/bin/bash
printf '%s\n' "$@" > "${CLAUDE_ARGV_FILE:?}"
cat > "${CLAUDE_STDIN_FILE:?}"
echo "stub-claude-ran"
exit "${STUB_EXIT_CODE:-0}"
STUB
chmod +x "$STUBDIR/claude"

# sonnet-run.sh re-prepends mise's own PATH ahead of ours whenever `mise` is
# reachable, which would put the real claude binary ahead of the stub.
# Excluding mise's location from the PATH we hand to sonnet-run.sh keeps that
# branch inert, so lookup always resolves to our stub.
RUN_PATH="$STUBDIR:/usr/bin:/bin"

SONNET_PROMPT="say hi from sonnet"
PROMPT_FILE_T="$WORK/prompt.txt"
printf '%s' "$SONNET_PROMPT" > "$PROMPT_FILE_T"

# run_sonnet <name> [args...] — runs sonnet-run.sh with SENTINEL data on the
# wrapper's own stdin; sets RC, STDOUT_F, STDERR_F, and per-test capture paths.
run_sonnet() {
    local name="$1"
    shift
    export CLAUDE_ARGV_FILE="$WORK/$name.argv"
    export CLAUDE_STDIN_FILE="$WORK/$name.stdin"
    STDOUT_F="$WORK/$name.stdout"
    STDERR_F="$WORK/$name.stderr"
    RC=0
    PATH="$RUN_PATH" bash "$SONNET_RUN_SH" "$@" \
        > "$STDOUT_F" 2> "$STDERR_F" <<< 'SENTINEL_STDIN_DATA' || RC=$?
}

# ══ T1: plain -f run (headless claude --print) ════════════════════════════════
run_sonnet t1 -f "$PROMPT_FILE_T"

# 1. Child stdin must be redirected to /dev/null. Without the guard the child
#    inherits the wrapper's stdin and reads SENTINEL_STDIN_DATA (the PRD 00040
#    hang class: a child blocking on inherited stdin stalls unattended runs).
if [ -f "$CLAUDE_STDIN_FILE" ] && [ ! -s "$CLAUDE_STDIN_FILE" ]; then
    PASS "claude child stdin is /dev/null"
else
    FAIL "claude child stdin is /dev/null" \
         "stub captured $(wc -c < "$CLAUDE_STDIN_FILE" 2>/dev/null | tr -d ' ' || echo '?') byte(s) of stdin; expected 0 (child inherited the wrapper's stdin instead of /dev/null)"
fi

# 2. Argv regression lock for the plain -f run (adding the stdin guard must
#    not perturb argv): claude --print --model sonnet <PROMPT>.
EXPECTED_ARGV_FILE="$WORK/t1.expected"
printf '%s\n' "--print" "--model" "sonnet" "$SONNET_PROMPT" > "$EXPECTED_ARGV_FILE"
if diff -q "$EXPECTED_ARGV_FILE" "$CLAUDE_ARGV_FILE" >/dev/null 2>&1; then
    PASS "plain -f argv is exactly: --print --model sonnet <PROMPT>"
else
    FAIL "plain -f argv is exactly: --print --model sonnet <PROMPT>" \
         "got: $(tr '\n' ' ' < "$CLAUDE_ARGV_FILE" 2>/dev/null || echo '<no claude invocation>')"
fi

# 3. Happy path exits 0 and surfaces the backend's output.
if [ "$RC" -eq 0 ] && grep -qF "stub-claude-ran" "$STDOUT_F"; then
    PASS "plain -f run exits 0 and passes claude stdout through"
else
    FAIL "plain -f run exits 0 and passes claude stdout through" \
         "rc=$RC; stdout: $(cat "$STDOUT_F")"
fi

# ══ T2: -m opus overrides the model ═══════════════════════════════════════════
run_sonnet t2 -m opus -f "$PROMPT_FILE_T"

# 4. -m: argv carries --model opus (and stays on the headless --print path).
if argv_has_pair "$CLAUDE_ARGV_FILE" "--model" "opus" && grep -qxF -- "--print" "$CLAUDE_ARGV_FILE"; then
    PASS "-m opus: argv carries --print and --model opus"
else
    FAIL "-m opus: argv carries --print and --model opus" \
         "argv: $(tr '\n' ' ' < "$CLAUDE_ARGV_FILE" 2>/dev/null || echo '<no claude invocation>')"
fi

# ══ T3: -a maps to --permission-mode acceptEdits (NOT bypass) ═════════════════
run_sonnet t3 -a -f "$PROMPT_FILE_T"

# 5. -a: argv carries the two-token pair --permission-mode acceptEdits. The old
# mapping sent bypassPermissions, making the documented weaker flag a silent -y.
if argv_has_pair "$CLAUDE_ARGV_FILE" "--permission-mode" "acceptEdits"; then
    PASS "-a: argv carries --permission-mode acceptEdits"
else
    FAIL "-a: argv carries --permission-mode acceptEdits" \
         "argv: $(tr '\n' ' ' < "$CLAUDE_ARGV_FILE" 2>/dev/null || echo '<no claude invocation>')"
fi

# ══ T3b: -y maps to --permission-mode bypassPermissions ═══════════════════════
run_sonnet t3b -y -f "$PROMPT_FILE_T"

# 5b. -y: argv carries the two-token pair --permission-mode bypassPermissions.
if argv_has_pair "$CLAUDE_ARGV_FILE" "--permission-mode" "bypassPermissions"; then
    PASS "-y: argv carries --permission-mode bypassPermissions"
else
    FAIL "-y: argv carries --permission-mode bypassPermissions" \
         "argv: $(tr '\n' ' ' < "$CLAUDE_ARGV_FILE" 2>/dev/null || echo '<no claude invocation>')"
fi

# ══ T4: -d DIR maps to --add-dir DIR ══════════════════════════════════════════
run_sonnet t4 -d "$WORK" -f "$PROMPT_FILE_T"

# 6. -d: argv carries the pair --add-dir <DIR>.
if argv_has_pair "$CLAUDE_ARGV_FILE" "--add-dir" "$WORK"; then
    PASS "-d DIR: argv carries --add-dir DIR"
else
    FAIL "-d DIR: argv carries --add-dir DIR" \
         "argv: $(tr '\n' ' ' < "$CLAUDE_ARGV_FILE" 2>/dev/null || echo '<no claude invocation>')"
fi

# ══ T5: -o tees output to the file ════════════════════════════════════════════
T5_OUT="$WORK/t5.out"
run_sonnet t5 -f "$PROMPT_FILE_T" -o "$T5_OUT"

# 7. -o: output file receives the backend output.
if grep -qF "stub-claude-ran" "$T5_OUT" 2>/dev/null; then
    PASS "-o: output file contains the claude output"
else
    FAIL "-o: output file contains the claude output" \
         "rc=$RC; -o file contents: $(cat "$T5_OUT" 2>/dev/null || echo '<missing>')"
fi

# ══ T6: -s/--silent is accepted as a no-op ════════════════════════════════════
run_sonnet t6 -s -f "$PROMPT_FILE_T"

# 8. -s: run succeeds and no -s token leaks into claude's argv.
if [ "$RC" -eq 0 ] && ! grep -qxF -- "-s" "$CLAUDE_ARGV_FILE" 2>/dev/null && grep -qxF -- "--print" "$CLAUDE_ARGV_FILE" 2>/dev/null; then
    PASS "-s is accepted as a no-op (no -s token in claude argv)"
else
    FAIL "-s is accepted as a no-op (no -s token in claude argv)" \
         "rc=$RC; argv: $(tr '\n' ' ' < "$CLAUDE_ARGV_FILE" 2>/dev/null || echo '<no claude invocation>')"
fi

# ══ T7: missing prompt file -> stderr + non-zero + no dispatch ════════════════
run_sonnet t7 -f "$WORK/does-not-exist.txt"

# 9. Missing prompt file: non-zero exit.
if [ "$RC" -ne 0 ]; then
    PASS "missing prompt file exits non-zero"
else
    FAIL "missing prompt file exits non-zero" "rc=0"
fi

# 10. Missing prompt file: the error lands on stderr, not stdout.
if grep -q "not found" "$STDERR_F" 2>/dev/null && ! grep -q "not found" "$STDOUT_F" 2>/dev/null; then
    PASS "missing prompt file: error text is on stderr"
else
    FAIL "missing prompt file: error text is on stderr" \
         "stderr: $(cat "$STDERR_F") -- stdout: $(cat "$STDOUT_F")"
fi

# 11. Missing prompt file: claude is never invoked.
if [ ! -f "$CLAUDE_ARGV_FILE" ]; then
    PASS "missing prompt file: claude is never invoked"
else
    FAIL "missing prompt file: claude is never invoked" \
         "argv: $(tr '\n' ' ' < "$CLAUDE_ARGV_FILE")"
fi

# ══ T8: no prompt at all -> stderr + non-zero ═════════════════════════════════
run_sonnet t8

# 12. Missing prompt: non-zero exit with the error on stderr.
if [ "$RC" -ne 0 ] && grep -qi "prompt required" "$STDERR_F" 2>/dev/null; then
    PASS "missing prompt exits non-zero with the error on stderr"
else
    FAIL "missing prompt exits non-zero with the error on stderr" \
         "rc=$RC; stderr: $(cat "$STDERR_F") -- stdout: $(cat "$STDOUT_F")"
fi

# ══ T9: child exit code propagates ════════════════════════════════════════════
export STUB_EXIT_CODE=7
run_sonnet t9 -f "$PROMPT_FILE_T"
unset STUB_EXIT_CODE

# 13. Exit-code propagation: the wrapper's exit code equals the child's.
if [ "$RC" -eq 7 ]; then
    PASS "child exit code (7) propagates as sonnet-run.sh's own exit code"
else
    FAIL "child exit code (7) propagates as sonnet-run.sh's own exit code" \
         "got exit code $RC"
fi

# ══ summary ═══════════════════════════════════════════════════════════════════
echo ""
echo "SUMMARY: $PASS_COUNT passed, $FAIL_COUNT failed"

[ "$FAIL_COUNT" -eq 0 ]
