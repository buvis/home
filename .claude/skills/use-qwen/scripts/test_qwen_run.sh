#!/usr/bin/env bash
# Test harness for qwen-run.sh (macOS bash 3.2 compatible). Stubs the `pi`
# binary on PATH and runs a mock llama-server that reproduces the false-healthy
# incident (2026-06-19): /v1/models returns 200 while /chat/completions returns
# 500 ("failed to spawn server instance"). Asserts on OBSERVABLE behavior
# (exit code, whether pi dispatched, child stdin), never on script internals.
set -u

QWEN_RUN_SH=/Users/bob/.claude/skills/use-qwen/scripts/qwen-run.sh
[ -n "${1:-}" ] && QWEN_RUN_SH="$1"

# ── assert helpers ────────────────────────────────────────────────────────────
PASS_COUNT=0
FAIL_COUNT=0
PASS() { echo "PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
FAIL() { echo "FAIL: $1 -- $2"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

# ── cleanup registry ──────────────────────────────────────────────────────────
_DIRS=()
SERVER_PID=""
SERVER_LOW_PID=""
SERVER_HIGH_PID=""
SERVER_MULTI_PID=""
SERVER_EMPTY_PID=""
SERVER_DASH_PID=""
SERVER_PIN_LOW_PID=""
SERVER_PIN_HIGH_PID=""
SERVER_REG_PID=""
SERVER_REG2_PID=""
SERVER_REG3_PID=""
SERVER_DEF_PID=""
cleanup() {
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
    [ -n "$SERVER_LOW_PID" ] && kill "$SERVER_LOW_PID" 2>/dev/null
    [ -n "$SERVER_HIGH_PID" ] && kill "$SERVER_HIGH_PID" 2>/dev/null
    [ -n "$SERVER_MULTI_PID" ] && kill "$SERVER_MULTI_PID" 2>/dev/null
    [ -n "$SERVER_EMPTY_PID" ] && kill "$SERVER_EMPTY_PID" 2>/dev/null
    [ -n "$SERVER_DASH_PID" ] && kill "$SERVER_DASH_PID" 2>/dev/null
    [ -n "$SERVER_PIN_LOW_PID" ] && kill "$SERVER_PIN_LOW_PID" 2>/dev/null
    [ -n "$SERVER_PIN_HIGH_PID" ] && kill "$SERVER_PIN_HIGH_PID" 2>/dev/null
    [ -n "$SERVER_REG_PID" ] && kill "$SERVER_REG_PID" 2>/dev/null
    [ -n "$SERVER_REG2_PID" ] && kill "$SERVER_REG2_PID" 2>/dev/null
    [ -n "$SERVER_REG3_PID" ] && kill "$SERVER_REG3_PID" 2>/dev/null
    [ -n "$SERVER_DEF_PID" ] && kill "$SERVER_DEF_PID" 2>/dev/null
    local d
    for d in "${_DIRS[@]+"${_DIRS[@]}"}"; do
        rm -rf "$d"
    done
}
trap cleanup EXIT

WORK=$(mktemp -d)
_DIRS+=("$WORK")

# ── stub `pi` and `mise` on PATH ──────────────────────────────────────────────
# The pi stub records argv + stdin; the mise stub neutralizes the real mise
# (qwen-run.sh prepends `mise env` PATH, which would put the real pi ahead of
# the stub).
STUBDIR="$WORK/stub"
mkdir -p "$STUBDIR"

cat > "$STUBDIR/pi" <<'STUB'
#!/bin/bash
printf '%s\n' "$@" > "${STUB_ARGV_FILE:?}"
cat > "${STUB_STDIN_FILE:?}"
echo "stub-pi-ran"
STUB
chmod +x "$STUBDIR/pi"

cat > "$STUBDIR/mise" <<'STUB'
#!/bin/bash
if [ "${1:-}" = "env" ]; then echo "export PATH='/var/empty'"; fi
exit 0
STUB
chmod +x "$STUBDIR/mise"

# ── mock llama-server ─────────────────────────────────────────────────────────
# GET /v1/models  -> always 200 with mock-qwen listed (config-backed listing).
# POST /v1/chat/completions -> 500 when mode file says "fail500", 200 on "ok".
MODE_FILE="$WORK/mode"
echo "fail500" > "$MODE_FILE"

# Shared with test_eval_automation.sh - see mock-llama-server.py itself for
# the false-healthy shape (models 200 / completions 500) it reproduces.
cp "$(dirname "$QWEN_RUN_SH")/mock-llama-server.py" "$WORK/server.py"

PORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 "$WORK/server.py" "$PORT" "$MODE_FILE" "mock-qwen" &
SERVER_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "FATAL: mock server did not start on port $PORT"
        exit 1
    fi
    sleep 0.1
done

# ── pi config pointing at the mock server ─────────────────────────────────────
CFGDIR="$WORK/agent"
mkdir -p "$CFGDIR"
cat > "$CFGDIR/models.json" <<EOF
{"providers": {"llamacpp": {"baseUrl": "http://127.0.0.1:$PORT/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": [{"id": "mock-qwen"}]}}}
EOF

PROMPT_FILE_T="$WORK/prompt.txt"
echo "say hi" > "$PROMPT_FILE_T"

# run_qwen <test-name> [args...] — runs qwen-run.sh with stubs; sets RC and OUT.
run_qwen() {
    local name="$1"
    shift
    export STUB_ARGV_FILE="$WORK/$name.argv"
    export STUB_STDIN_FILE="$WORK/$name.stdin"
    OUT=$(PI_CODING_AGENT_DIR="$CFGDIR" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH" "$@" < /dev/null 2>&1)
    RC=$?
}

# ══ T1: REGRESSION — false healthy (models 200 / completion 500) ══════════════
# The 2026-06-19 incident shape: the listing passes but the inference worker
# cannot spawn. An honest preflight must refuse BEFORE dispatching pi.
echo "fail500" > "$MODE_FILE"
run_qwen t1 -f "$PROMPT_FILE_T"
if [ "$RC" -ne 0 ]; then
    PASS "false-healthy dispatch exits nonzero (completion 500 refuses dispatch)"
else
    FAIL "false-healthy dispatch exits nonzero (completion 500 refuses dispatch)" "rc=0; output: $OUT"
fi
if [ ! -f "$WORK/t1.argv" ]; then
    PASS "pi is NOT dispatched when the completion probe fails"
else
    FAIL "pi is NOT dispatched when the completion probe fails" "stub pi ran with argv: $(tr '\n' ' ' < "$WORK/t1.argv")"
fi
case "$OUT" in
    *completion_failed*) PASS "failure names the preflight outcome completion_failed" ;;
    *) FAIL "failure names the preflight outcome completion_failed" "output: $OUT" ;;
esac

# ══ T2: --preflight verdict on the false-healthy backend ══════════════════════
run_qwen t2 --preflight
if [ "$RC" -ne 0 ]; then
    PASS "--preflight exits nonzero on models-200/completion-500"
else
    FAIL "--preflight exits nonzero on models-200/completion-500" "rc=0; output: $OUT"
fi
case "$OUT" in
    *completion_failed*) PASS "--preflight names completion_failed on completion 500" ;;
    *) FAIL "--preflight names completion_failed on completion 500" "output: $OUT" ;;
esac

# ══ T3: --preflight healthy when a real completion succeeds ═══════════════════
echo "ok" > "$MODE_FILE"
run_qwen t3 --preflight
if [ "$RC" -eq 0 ]; then
    PASS "--preflight exits 0 when the 1-token completion succeeds"
else
    FAIL "--preflight exits 0 when the 1-token completion succeeds" "rc=$RC; output: $OUT"
fi
case "$OUT" in
    *healthy*) PASS "--preflight reports healthy" ;;
    *) FAIL "--preflight reports healthy" "output: $OUT" ;;
esac
if [ ! -f "$WORK/t3.argv" ]; then
    PASS "--preflight never dispatches pi (probe only)"
else
    FAIL "--preflight never dispatches pi (probe only)" "stub pi ran with argv: $(tr '\n' ' ' < "$WORK/t3.argv")"
fi

# ══ T4: healthy dispatch reaches pi; child stdin is guarded ═══════════════════
export STUB_ARGV_FILE="$WORK/t4.argv"
export STUB_STDIN_FILE="$WORK/t4.stdin"
OUT=$(printf 'MUST_NOT_REACH_CHILD' | PI_CODING_AGENT_DIR="$CFGDIR" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH" -f "$PROMPT_FILE_T" 2>&1)
RC=$?
if [ "$RC" -eq 0 ]; then
    PASS "healthy backend: dispatch exits 0"
else
    FAIL "healthy backend: dispatch exits 0" "rc=$RC; output: $OUT"
fi
if [ -f "$WORK/t4.argv" ] && grep -q "say hi" "$WORK/t4.argv"; then
    PASS "healthy backend: pi dispatched with the prompt"
else
    FAIL "healthy backend: pi dispatched with the prompt" "argv file: $(cat "$WORK/t4.argv" 2>/dev/null || echo MISSING)"
fi
if [ -f "$WORK/t4.stdin" ] && [ ! -s "$WORK/t4.stdin" ]; then
    PASS "child pi stdin is guarded (< /dev/null; parent stdin not consumed)"
else
    FAIL "child pi stdin is guarded (< /dev/null; parent stdin not consumed)" "stdin capture: '$(cat "$WORK/t4.stdin" 2>/dev/null || echo MISSING)'"
fi

# ══ T4b: -s/--silent accepted as a no-op (flag parity with codex/gemini/sonnet)
# Needs the live healthy server, so it runs before T5 kills it.
run_qwen t4b -s -f "$PROMPT_FILE_T"
if [ "$RC" -eq 0 ] && [ -f "$WORK/t4b.argv" ] && grep -q "say hi" "$WORK/t4b.argv" && ! grep -qx -- "-s" "$WORK/t4b.argv"; then
    PASS "-s is accepted as a no-op (dispatch succeeds, no -s token in pi argv)"
else
    FAIL "-s is accepted as a no-op (dispatch succeeds, no -s token in pi argv)" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t4b.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# ══ T5: server down entirely -> endpoint_unreachable ══════════════════════════
kill "$SERVER_PID" 2>/dev/null
wait "$SERVER_PID" 2>/dev/null
SERVER_PID=""
run_qwen t5 --preflight
if [ "$RC" -ne 0 ]; then
    PASS "--preflight exits nonzero when no server responds"
else
    FAIL "--preflight exits nonzero when no server responds" "rc=0; output: $OUT"
fi
case "$OUT" in
    *endpoint_unreachable*) PASS "--preflight names endpoint_unreachable when no server responds" ;;
    *) FAIL "--preflight names endpoint_unreachable when no server responds" "output: $OUT" ;;
esac

# ══ T6: usage errors land on stderr with non-zero exit ════════════════════════
# No server needed: the prompt-file check runs before any preflight probing.
export STUB_ARGV_FILE="$WORK/t6.argv"
export STUB_STDIN_FILE="$WORK/t6.stdin"
RC=0
T6_STDOUT=$(PI_CODING_AGENT_DIR="$CFGDIR" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH" -f "$WORK/does-not-exist.txt" < /dev/null 2> "$WORK/t6.stderr") || RC=$?
if [ "$RC" -ne 0 ] && grep -q "not found" "$WORK/t6.stderr" 2>/dev/null; then
    PASS "missing prompt file: non-zero exit with the error on stderr"
else
    FAIL "missing prompt file: non-zero exit with the error on stderr" "rc=$RC; stderr: $(cat "$WORK/t6.stderr" 2>/dev/null); stdout: $T6_STDOUT"
fi
case "$T6_STDOUT" in
    *"not found"*) FAIL "missing prompt file: error text stays off stdout" "stdout: $T6_STDOUT" ;;
    *) PASS "missing prompt file: error text stays off stdout" ;;
esac

# ══ --approved-only fixture: two live, fully HEALTHY providers ═══════════════
# LOW port serves an UNAPPROVED id, HIGH port serves the APPROVED id. BOTH pass
# their /chat/completions probe (mode "ok"). Health is deliberately identical so
# that approval is the ONLY variable: if a provider gets skipped, the registry
# is the only thing that could have skipped it. (A LOW that 500s would let an
# implementation with no approval logic at all — one that just falls through to
# the next provider on a failed probe — pass these asserts.)
MODE_FILE_2="$WORK/mode2"
echo "ok" > "$MODE_FILE_2"

PORT_X=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
PORT_Y=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
if [ "$PORT_X" -lt "$PORT_Y" ]; then
    PORT_LOW=$PORT_X
    PORT_HIGH=$PORT_Y
else
    PORT_LOW=$PORT_Y
    PORT_HIGH=$PORT_X
fi

CFGDIR2="$WORK/agent2"
mkdir -p "$CFGDIR2"
cat > "$CFGDIR2/models.json" <<EOF
{"providers": {"llamacpp_low": {"baseUrl": "http://127.0.0.1:$PORT_LOW/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": [{"id": "mock-unapproved"}]}, "llamacpp_high": {"baseUrl": "http://127.0.0.1:$PORT_HIGH/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": [{"id": "mock-approved"}]}}}
EOF

# Registry path is resolved script-relative ($(dirname "$0")/approved-models.txt)
# with no env override, so the only way to inject a fake registry is to copy
# qwen-run.sh next to it and run the copy.
APPROVED_WORK="$WORK/approved"
mkdir -p "$APPROVED_WORK"
cp "$QWEN_RUN_SH" "$APPROVED_WORK/qwen-run.sh"
cat > "$APPROVED_WORK/approved-models.txt" <<'EOF'
# fake registry for --approved-only tests: only the mock APPROVED id.
mock-approved
EOF
QWEN_RUN_SH_APPROVED="$APPROVED_WORK/qwen-run.sh"
REGISTRY_PATH="$APPROVED_WORK/approved-models.txt"

# run_qwen2 <test-name> [args...] — like run_qwen but against the copied
# script + CFGDIR2 (two-provider fixture).
run_qwen2() {
    local name="$1"
    shift
    export STUB_ARGV_FILE="$WORK/$name.argv"
    export STUB_STDIN_FILE="$WORK/$name.stdin"
    OUT=$(PI_CODING_AGENT_DIR="$CFGDIR2" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_APPROVED" "$@" < /dev/null 2>&1)
    RC=$?
}

# Start the LOW (healthy, unapproved) server only; HIGH stays down for T7.
python3 "$WORK/server.py" "$PORT_LOW" "$MODE_FILE_2" "mock-unapproved" &
SERVER_LOW_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT_LOW/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "FATAL: mock low server did not start on port $PORT_LOW"
        exit 1
    fi
    sleep 0.1
done

# ══ T7: --approved-only, only the (healthy) unapproved provider is live ═══════
# The backend is healthy, so completion_failed would be the WRONG outcome here:
# the only honest reason to refuse is that the approved id is not live.
run_qwen2 t7 --approved-only -f "$PROMPT_FILE_T"
if [ "$RC" -ne 0 ] && [ ! -f "$WORK/t7.argv" ]; then
    PASS "a healthy but unapproved sole provider is refused, not dispatched"
else
    FAIL "a healthy but unapproved sole provider is refused, not dispatched" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t7.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi
case "$OUT" in
    *model_id_missing*) PASS "no-approved-id-live refusal names model_id_missing (not completion_failed: the backend is healthy)" ;;
    *) FAIL "no-approved-id-live refusal names model_id_missing (not completion_failed: the backend is healthy)" "output: $OUT" ;;
esac
case "$OUT" in
    *"$REGISTRY_PATH"*) PASS "no-approved-id-live refusal names the registry path" ;;
    *) FAIL "no-approved-id-live refusal names the registry path" "output: $OUT" ;;
esac

# Bring up the HIGH (healthy, approved) server. From here BOTH providers are
# live and healthy; only the registry can explain a skip.
python3 "$WORK/server.py" "$PORT_HIGH" "$MODE_FILE_2" "mock-approved" &
SERVER_HIGH_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT_HIGH/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "FATAL: mock high server did not start on port $PORT_HIGH"
        exit 1
    fi
    sleep 0.1
done

# ══ T8: --approved-only skips a healthy unapproved LOWER port for the approved
# HIGHER port ═════════════════════════════════════════════════════════════════
# Both are live and healthy and the unapproved one sorts first, so ascending-port
# order alone would pick it. Only the registry can send resolution to the higher
# port. Asserts pin WHICH provider/model was resolved, not merely rc=0 (both
# providers succeed, so rc=0 alone proves nothing).
run_qwen2 t8 --approved-only -f "$PROMPT_FILE_T"
if [ "$RC" -eq 0 ] && [ -f "$WORK/t8.argv" ] && grep -q "mock-approved" "$WORK/t8.argv" && ! grep -q "mock-unapproved" "$WORK/t8.argv"; then
    PASS "unapproved lower port is skipped for the approved higher port (pi dispatched with the approved provider/model)"
else
    FAIL "unapproved lower port is skipped for the approved higher port (pi dispatched with the approved provider/model)" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t8.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# ══ T9: default no-flag run on the SAME fixture is unchanged ══════════════════
# PRD edge case: flag absent -> ascending-port behavior identical to today, i.e.
# the healthy unapproved lower port WINS and dispatches. A script-adjacent
# approved-models.txt must be inert without the flag.
run_qwen2 t9 -f "$PROMPT_FILE_T"
if [ "$RC" -eq 0 ] && [ -f "$WORK/t9.argv" ] && grep -q "mock-unapproved" "$WORK/t9.argv"; then
    PASS "without the flag the ascending port rule still wins (healthy unapproved lower port dispatches)"
else
    FAIL "without the flag the ascending port rule still wins (healthy unapproved lower port dispatches)" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t9.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# ══ T10: -m naming an unapproved id is refused ════════════════════════════════
run_qwen2 t10 -m mock-unapproved --approved-only -f "$PROMPT_FILE_T"
if [ "$RC" -ne 0 ] && [ ! -f "$WORK/t10.argv" ]; then
    PASS "-m an unapproved id is refused, not dispatched (even though that model is live and healthy)"
else
    FAIL "-m an unapproved id is refused, not dispatched (even though that model is live and healthy)" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t10.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi
case "$OUT" in
    *model_id_missing*"$REGISTRY_PATH"* | *"$REGISTRY_PATH"*model_id_missing*)
        PASS "-m unapproved refusal names model_id_missing and the registry path" ;;
    *) FAIL "-m unapproved refusal names model_id_missing and the registry path" "output: $OUT" ;;
esac

# ══ T11: -P naming a provider that serves an unapproved id is refused ═════════
run_qwen2 t11 -P llamacpp_low --approved-only -f "$PROMPT_FILE_T"
if [ "$RC" -ne 0 ] && [ ! -f "$WORK/t11.argv" ]; then
    PASS "-P a provider serving an unapproved id is refused, not dispatched (even though it is live and healthy)"
else
    FAIL "-P a provider serving an unapproved id is refused, not dispatched (even though it is live and healthy)" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t11.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi
case "$OUT" in
    *model_id_missing*"$REGISTRY_PATH"* | *"$REGISTRY_PATH"*model_id_missing*)
        PASS "-P unapproved-provider refusal names model_id_missing and the registry path" ;;
    *) FAIL "-P unapproved-provider refusal names model_id_missing and the registry path" "output: $OUT" ;;
esac

# ══ T12: --preflight --approved-only composes ═════════════════════════════════
# Both providers would pass a probe, so "healthy" alone proves nothing — the
# verdict must name the APPROVED candidate to prove the probe ran against it.
run_qwen2 t12 --preflight --approved-only
# The unapproved id may appear in the (loud, T37) skip WARNING; the intent
# here is that the VERDICT line proves the probe ran against the approved
# candidate, so assert on the "healthy" line alone.
T12_OK=no
T12_HEALTHY_LINE="$(grep "healthy" <<< "$OUT")"
if [ "$RC" -eq 0 ]; then
    case "$T12_HEALTHY_LINE" in
        *"mock-unapproved"*) ;;
        *"mock-approved"*) T12_OK=yes ;;
    esac
fi
if [ "$T12_OK" = yes ]; then
    PASS "--preflight --approved-only completes against the approved candidate, not the unapproved lower port"
else
    FAIL "--preflight --approved-only completes against the approved candidate, not the unapproved lower port" "rc=$RC; output: $OUT"
fi

# ══ multi-id fixture: ONE healthy provider whose /v1/models lists TWO ids ═════
# "decoy-multi-id" is listed FIRST, "mock-approved" SECOND. Only the registry
# (already loaded with "mock-approved" from the T7-T12 fixture) makes the
# second position resolvable; reading only .data[0].id would see the decoy and
# nothing else, so it must fail today.
PORT_MULTI=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 "$WORK/server.py" "$PORT_MULTI" "$MODE_FILE_2" "decoy-multi-id" "mock-approved" &
SERVER_MULTI_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT_MULTI/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "FATAL: mock multi-id server did not start on port $PORT_MULTI"
        exit 1
    fi
    sleep 0.1
done

CFGDIR3="$WORK/agent3"
mkdir -p "$CFGDIR3"
cat > "$CFGDIR3/models.json" <<EOF
{"providers": {"llamacpp_multi": {"baseUrl": "http://127.0.0.1:$PORT_MULTI/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": [{"id": "decoy-multi-id"}, {"id": "mock-approved"}]}}}
EOF

# ══ T13: --approved-only resolves an approved id at a NON-FIRST list position ═
export STUB_ARGV_FILE="$WORK/t13.argv"
export STUB_STDIN_FILE="$WORK/t13.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR3" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_APPROVED" --approved-only -f "$PROMPT_FILE_T" < /dev/null 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && [ -f "$WORK/t13.argv" ] && grep -q "mock-approved" "$WORK/t13.argv" && ! grep -q "decoy-multi-id" "$WORK/t13.argv"; then
    PASS "an approved id listed at a non-first /v1/models position still resolves and dispatches (not just .data[0].id)"
else
    FAIL "an approved id listed at a non-first /v1/models position still resolves and dispatches (not just .data[0].id)" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t13.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# ══ T14: flagless path on the SAME multi-id endpoint still takes .data[0].id ══
export STUB_ARGV_FILE="$WORK/t14.argv"
export STUB_STDIN_FILE="$WORK/t14.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR3" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_APPROVED" -f "$PROMPT_FILE_T" < /dev/null 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && [ -f "$WORK/t14.argv" ] && grep -q "decoy-multi-id" "$WORK/t14.argv" && ! grep -q "mock-approved" "$WORK/t14.argv"; then
    PASS "without --approved-only, resolution still takes the FIRST listed id even on a multi-id endpoint (ascending-port + .data[0].id byte-identical)"
else
    FAIL "without --approved-only, resolution still takes the FIRST listed id even on a multi-id endpoint (ascending-port + .data[0].id byte-identical)" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t14.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# ══ T14b: --approved-only -P forcing the multi-id provider with NO -m must
# still resolve the approved id at a non-first position (same multi-id
# fixture as T13/T14; llamacpp_multi is already a named -P-addressable
# provider in CFGDIR3/models.json) — the forced-provider branch must not be
# .data[0].id-only. ═════════════════════════════════════════════════════════
export STUB_ARGV_FILE="$WORK/t14b.argv"
export STUB_STDIN_FILE="$WORK/t14b.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR3" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_APPROVED" --approved-only -P llamacpp_multi -f "$PROMPT_FILE_T" < /dev/null 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && [ -f "$WORK/t14b.argv" ] && grep -q "mock-approved" "$WORK/t14b.argv" && ! grep -q "decoy-multi-id" "$WORK/t14b.argv"; then
    PASS "-P a provider serving the approved id at a non-first position resolves and dispatches it (forced-provider path is not .data[0].id-only)"
else
    FAIL "-P a provider serving the approved id at a non-first position resolves and dispatches it (forced-provider path is not .data[0].id-only)" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t14b.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# ══ T15: -P forcing a provider that SERVES an unapproved id, plus an approved
# -m, is refused (the live-served id is probed, not the claimed -m value) ═════
run_qwen2 t15 -P llamacpp_low -m mock-approved --approved-only -f "$PROMPT_FILE_T"
if [ "$RC" -ne 0 ] && [ ! -f "$WORK/t15.argv" ]; then
    PASS "-P a provider that actually serves an unapproved id, combined with a claimed-approved -m, is refused, not dispatched"
else
    FAIL "-P a provider that actually serves an unapproved id, combined with a claimed-approved -m, is refused, not dispatched" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t15.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi
case "$OUT" in
    *model_id_missing*"$REGISTRY_PATH"* | *"$REGISTRY_PATH"*model_id_missing*)
        PASS "-P+-m mismatch refusal names model_id_missing and the registry path" ;;
    *) FAIL "-P+-m mismatch refusal names model_id_missing and the registry path" "output: $OUT" ;;
esac

# ══ empty-string-id fixture: a healthy provider whose /v1/models reports the
# EMPTY STRING as its sole id, against a registry containing only a blank line.
# An exact-match against an unfiltered blank line would wrongly approve "".
APPROVED_EMPTY="$WORK/approved_empty"
mkdir -p "$APPROVED_EMPTY"
cp "$QWEN_RUN_SH" "$APPROVED_EMPTY/qwen-run.sh"
cat > "$APPROVED_EMPTY/approved-models.txt" <<'EOF'
# registry with only a blank line below: must never approve an empty id

EOF
QWEN_RUN_SH_EMPTY="$APPROVED_EMPTY/qwen-run.sh"

PORT_EMPTY=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 "$WORK/server.py" "$PORT_EMPTY" "$MODE_FILE_2" "" &
SERVER_EMPTY_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT_EMPTY/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "FATAL: mock empty-id server did not start on port $PORT_EMPTY"
        exit 1
    fi
    sleep 0.1
done

CFGDIR_EMPTY="$WORK/agent_empty"
mkdir -p "$CFGDIR_EMPTY"
cat > "$CFGDIR_EMPTY/models.json" <<EOF
{"providers": {"llamacpp_empty": {"baseUrl": "http://127.0.0.1:$PORT_EMPTY/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": [{"id": ""}]}}}
EOF

# ══ T16: an empty-string served model id is never approved ═══════════════════
export STUB_ARGV_FILE="$WORK/t16.argv"
export STUB_STDIN_FILE="$WORK/t16.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_EMPTY" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_EMPTY" --approved-only -f "$PROMPT_FILE_T" < /dev/null 2>&1)
RC=$?
if [ "$RC" -ne 0 ] && [ ! -f "$WORK/t16.argv" ]; then
    PASS "an empty-string served model id is never approved, even against a registry containing a blank line"
else
    FAIL "an empty-string served model id is never approved, even against a registry containing a blank line" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t16.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# ══ dash-id fixture: a healthy provider whose /v1/models reports "-e" (an
# option-shaped id) as its sole id. Append "-e" to the shared T7-T12 registry
# (safe: those assertions already ran and check unrelated ids).
# printf, NOT echo: bash's echo builtin eats a sole "-e" as its own flag and
# appends an empty line, which silently left the registry without the very id
# this fixture exists to test.
printf '%s\n' "-e" >> "$REGISTRY_PATH"

PORT_DASH=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 "$WORK/server.py" "$PORT_DASH" "$MODE_FILE_2" "-e" &
SERVER_DASH_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT_DASH/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "FATAL: mock dash-id server did not start on port $PORT_DASH"
        exit 1
    fi
    sleep 0.1
done

CFGDIR_DASH="$WORK/agent_dash"
mkdir -p "$CFGDIR_DASH"
cat > "$CFGDIR_DASH/models.json" <<EOF
{"providers": {"llamacpp_dash": {"baseUrl": "http://127.0.0.1:$PORT_DASH/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": [{"id": "-e"}]}}}
EOF

# ══ T17: a model id beginning with "-" is compared as a literal string ═══════
export STUB_ARGV_FILE="$WORK/t17.argv"
export STUB_STDIN_FILE="$WORK/t17.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_DASH" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_APPROVED" --approved-only -f "$PROMPT_FILE_T" < /dev/null 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && [ -f "$WORK/t17.argv" ] && grep -qx -- "-e" "$WORK/t17.argv"; then
    PASS "a model id beginning with - is compared as a literal string, never parsed as an option, and still dispatches when approved"
else
    FAIL "a model id beginning with - is compared as a literal string, never parsed as an option, and still dispatches when approved" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t17.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# ══ T18: --approved-only with a MISSING registry file fails closed, and is
# distinguishable from the ordinary "unapproved model" refusal ═══════════════
APPROVED_MISSING="$WORK/approved_missing"
mkdir -p "$APPROVED_MISSING"
cp "$QWEN_RUN_SH" "$APPROVED_MISSING/qwen-run.sh"
# Deliberately no approved-models.txt written here.
QWEN_RUN_SH_MISSING="$APPROVED_MISSING/qwen-run.sh"
REGISTRY_PATH_MISSING="$APPROVED_MISSING/approved-models.txt"

export STUB_ARGV_FILE="$WORK/t18.argv"
export STUB_STDIN_FILE="$WORK/t18.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR2" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_MISSING" --approved-only -f "$PROMPT_FILE_T" < /dev/null 2>&1)
RC=$?
if [ "$RC" -ne 0 ] && [ ! -f "$WORK/t18.argv" ]; then
    PASS "a missing registry file fails closed under --approved-only, not dispatched"
else
    FAIL "a missing registry file fails closed under --approved-only, not dispatched" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t18.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi
case "$OUT" in
    *"$REGISTRY_PATH_MISSING"*) PASS "missing-registry refusal names the registry path" ;;
    *) FAIL "missing-registry refusal names the registry path" "output: $OUT" ;;
esac
# Strip both the sanctioned outcome token AND the registry path itself before
# looking for a cause phrase: the fixture's own path (.../approved_missing/...)
# contains the literal substring "missing", which would otherwise make this
# assert pass on path coincidence rather than on real diagnosis text.
OUT_SANS_TOKEN="${OUT//model_id_missing/}"
OUT_SANS_TOKEN="${OUT_SANS_TOKEN//$REGISTRY_PATH_MISSING/}"
case "$OUT_SANS_TOKEN" in
    *"not found"*|*"missing"*)
        PASS "missing-registry refusal states the registry file is missing (cause phrase, e.g. not found/missing)" ;;
    *)
        FAIL "missing-registry refusal states the registry file is missing (cause phrase, e.g. not found/missing)" "output: $OUT" ;;
esac
case "$OUT" in
    *"is not in the approved registry ($REGISTRY_PATH_MISSING)"*)
        FAIL "missing-registry refusal is distinguishable from the ordinary unapproved-model refusal (must not reuse its wording)" "output: $OUT" ;;
    *)
        PASS "missing-registry refusal is distinguishable from the ordinary unapproved-model refusal (must not reuse its wording)" ;;
esac
case "$OUT" in
    *model_id_missing*) PASS "missing-registry refusal still uses the existing model_id_missing outcome token (no new enum member)" ;;
    *) FAIL "missing-registry refusal still uses the existing model_id_missing outcome token (no new enum member)" "output: $OUT" ;;
esac

# ══ T19: the SHIPPED registry actually contains the documented default id ═════
# Every assert above runs against a FAKE registry (mock-approved), so a typo or
# an accidental emptying of the real approved-models.txt would darken the whole
# autopilot qwen lane with zero test signal. This is the one assert that binds
# the shipped file. The id below is the one use-qwen/SKILL.md and
# work/references/qwen-integration.md both document as the default; if you
# genuinely retire it, update those docs in the same commit.
SHIPPED_REGISTRY="$(dirname "$QWEN_RUN_SH")/approved-models.txt"
SHIPPED_DEFAULT_ID="unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL"
if [ -f "$SHIPPED_REGISTRY" ] && grep -qFx -- "$SHIPPED_DEFAULT_ID" "$SHIPPED_REGISTRY"; then
    PASS "the shipped approved-models.txt lists the documented default model id"
else
    FAIL "the shipped approved-models.txt lists the documented default model id" "registry: $SHIPPED_REGISTRY; expected exact line: $SHIPPED_DEFAULT_ID"
fi

# ══ --approved-only fixture: TWO approved ids, each on its own provider,
# LOWER port serving mock-approved-a, HIGHER port serving mock-approved-b.
# Both fully healthy (completion mode "ok"). Registry approves BOTH ids, so
# ascending-port auto-detect logic alone could still resolve the wrong
# provider for a forced -m id — this fixture isolates that failure mode.
MODE_FILE_PIN="$WORK/mode_pin"
echo "ok" > "$MODE_FILE_PIN"

PORT_PIN_X=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
PORT_PIN_Y=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
if [ "$PORT_PIN_X" -lt "$PORT_PIN_Y" ]; then
    PORT_PIN_LOW=$PORT_PIN_X
    PORT_PIN_HIGH=$PORT_PIN_Y
else
    PORT_PIN_LOW=$PORT_PIN_Y
    PORT_PIN_HIGH=$PORT_PIN_X
fi

python3 "$WORK/server.py" "$PORT_PIN_LOW" "$MODE_FILE_PIN" "mock-approved-a" &
SERVER_PIN_LOW_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT_PIN_LOW/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "FATAL: mock pin-low server did not start on port $PORT_PIN_LOW"
        exit 1
    fi
    sleep 0.1
done

python3 "$WORK/server.py" "$PORT_PIN_HIGH" "$MODE_FILE_PIN" "mock-approved-b" &
SERVER_PIN_HIGH_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT_PIN_HIGH/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "FATAL: mock pin-high server did not start on port $PORT_PIN_HIGH"
        exit 1
    fi
    sleep 0.1
done

CFGDIR_PIN="$WORK/agent_pin"
mkdir -p "$CFGDIR_PIN"
cat > "$CFGDIR_PIN/models.json" <<EOF
{"providers": {"prov_a": {"baseUrl": "http://127.0.0.1:$PORT_PIN_LOW/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": [{"id": "mock-approved-a"}]}, "prov_b": {"baseUrl": "http://127.0.0.1:$PORT_PIN_HIGH/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": [{"id": "mock-approved-b"}]}}}
EOF

APPROVED_PIN="$WORK/approved_pin"
mkdir -p "$APPROVED_PIN"
cp "$QWEN_RUN_SH" "$APPROVED_PIN/qwen-run.sh"
cat > "$APPROVED_PIN/approved-models.txt" <<'EOF'
# fake registry for T20: both ids approved so ascending-port order alone
# cannot explain a correct pick — only pinning to the id actually served can.
mock-approved-a
mock-approved-b
EOF
QWEN_RUN_SH_PIN="$APPROVED_PIN/qwen-run.sh"

# ══ T20: auto-detect with an explicit -m must bind the provider that actually
# serves THAT id, not merely a provider serving SOME approved id ═════════════
# Both providers are live, healthy, and approved; the lower port serves
# mock-approved-a and would win under plain ascending-port order. Forcing
# -m mock-approved-b must steer resolution to the HIGHER port — llama.cpp
# ignores the request's model field, so binding the wrong provider would
# silently run the prompt against the wrong checkpoint.
export STUB_ARGV_FILE="$WORK/t20.argv"
export STUB_STDIN_FILE="$WORK/t20.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_PIN" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_PIN" --approved-only -m mock-approved-b -f "$PROMPT_FILE_T" < /dev/null 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && [ -f "$WORK/t20.argv" ] && grep -q "prov_b" "$WORK/t20.argv" && grep -q "mock-approved-b" "$WORK/t20.argv" && ! grep -q "prov_a" "$WORK/t20.argv"; then
    PASS "auto-detect with an explicit -m binds the provider that actually serves that id, not merely one serving some approved id"
else
    FAIL "auto-detect with an explicit -m binds the provider that actually serves that id, not merely one serving some approved id" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t20.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# ══ down-endpoint fixture: a provider defined in config but with NO server
# listening (endpoint down), paired with an -m id that IS in the approved
# registry (reusing the T7+ APPROVED_WORK registry, which already lists
# mock-approved) ═══════════════════════════════════════════════════════════
PORT_DOWN21=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')

CFGDIR_DOWN21="$WORK/agent_down21"
mkdir -p "$CFGDIR_DOWN21"
cat > "$CFGDIR_DOWN21/models.json" <<EOF
{"providers": {"prov_down": {"baseUrl": "http://127.0.0.1:$PORT_DOWN21/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": [{"id": "mock-approved"}]}}}
EOF

# ══ T21: -P naming a DOWN provider, with an -m id that IS in the registry,
# must be diagnosed as endpoint_unreachable — never as a registry problem ════
# The id IS approved; only the backend is unreachable. Misreporting this as
# "not in the approved registry" points debugging at the wrong file.
export STUB_ARGV_FILE="$WORK/t21.argv"
export STUB_STDIN_FILE="$WORK/t21.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_DOWN21" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_APPROVED" --approved-only -P prov_down -m mock-approved -f "$PROMPT_FILE_T" < /dev/null 2>&1)
RC=$?
case "$OUT" in
    *endpoint_unreachable*) PASS "a down provider with an approved -m id is diagnosed as endpoint_unreachable" ;;
    *) FAIL "a down provider with an approved -m id is diagnosed as endpoint_unreachable" "rc=$RC; output: $OUT" ;;
esac
case "$OUT" in
    *"not in the approved registry"*) FAIL "a down provider with an approved -m id is NOT misreported as a registry problem" "output: $OUT" ;;
    *) PASS "a down provider with an approved -m id is NOT misreported as a registry problem" ;;
esac

# ══ trailing-whitespace registry fixture: the sole entry is "mock-approved"
# followed by trailing spaces. printf (not a heredoc) guarantees the trailing
# whitespace survives byte-for-byte. ═════════════════════════════════════════
APPROVED_TRAILWS="$WORK/approved_trailws"
mkdir -p "$APPROVED_TRAILWS"
cp "$QWEN_RUN_SH" "$APPROVED_TRAILWS/qwen-run.sh"
printf 'mock-approved   \n' > "$APPROVED_TRAILWS/approved-models.txt"
QWEN_RUN_SH_TRAILWS="$APPROVED_TRAILWS/qwen-run.sh"

# ══ T22: a registry entry with trailing whitespace still approves its id ═════
# "mock-approved   " (trailing spaces) must still approve the id
# "mock-approved" — a registry typo like this must not silently darken an
# otherwise-live, otherwise-approved lane.
export STUB_ARGV_FILE="$WORK/t22.argv"
export STUB_STDIN_FILE="$WORK/t22.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR2" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_TRAILWS" --approved-only -P llamacpp_high -f "$PROMPT_FILE_T" < /dev/null 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && [ -f "$WORK/t22.argv" ] && grep -q "mock-approved" "$WORK/t22.argv"; then
    PASS "a registry entry with trailing whitespace still approves its id (dispatch succeeds)"
else
    FAIL "a registry entry with trailing whitespace still approves its id (dispatch succeeds)" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t22.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# ══ comment-only-id registry fixture: the id appears ONLY inside a comment
# line, with no bare entry anywhere in the file ══════════════════════════════
APPROVED_COMMENTONLY="$WORK/approved_commentonly"
mkdir -p "$APPROVED_COMMENTONLY"
cp "$QWEN_RUN_SH" "$APPROVED_COMMENTONLY/qwen-run.sh"
printf '# mock-approved\n' > "$APPROVED_COMMENTONLY/approved-models.txt"
QWEN_RUN_SH_COMMENTONLY="$APPROVED_COMMENTONLY/qwen-run.sh"

# ══ T23: a #-commented id does NOT approve ════════════════════════════════
# "# mock-approved" is a comment, not an approval. The (healthy) provider
# serving mock-approved must be refused, not dispatched.
export STUB_ARGV_FILE="$WORK/t23.argv"
export STUB_STDIN_FILE="$WORK/t23.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR2" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_COMMENTONLY" --approved-only -P llamacpp_high -f "$PROMPT_FILE_T" < /dev/null 2>&1)
RC=$?
if [ "$RC" -ne 0 ] && [ ! -f "$WORK/t23.argv" ]; then
    PASS "a #-commented id (no bare entry) does not approve; the healthy provider serving it is refused"
else
    FAIL "a #-commented id (no bare entry) does not approve; the healthy provider serving it is refused" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t23.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# ══ T24: -P naming a LIVE, HEALTHY provider that does NOT serve the forced
# (approved) -m id must name the ACTUAL cause. Reuses the T20 fixture
# ($CFGDIR_PIN / $QWEN_RUN_SH_PIN): prov_a is live and serves mock-approved-a;
# mock-approved-b IS in that registry, just not served by prov_a. The refusal
# must say the model is not SERVED BY THAT PROVIDER — it must NOT claim the
# model is missing from the registry (it isn't; that wording would send the
# reader to edit an already-correct file). ═══════════════════════════════════
export STUB_ARGV_FILE="$WORK/t24.argv"
export STUB_STDIN_FILE="$WORK/t24.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_PIN" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_PIN" --approved-only -P prov_a -m mock-approved-b -f "$PROMPT_FILE_T" < /dev/null 2>&1)
RC=$?
if [ "$RC" -ne 0 ] && [ ! -f "$WORK/t24.argv" ]; then
    PASS "-P naming a live provider that does not serve the forced approved -m id is refused, not dispatched"
else
    FAIL "-P naming a live provider that does not serve the forced approved -m id is refused, not dispatched" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t24.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi
case "$OUT" in
    *model_id_missing*) PASS "provider/model mismatch refusal still uses the existing model_id_missing outcome token (no new enum member)" ;;
    *) FAIL "provider/model mismatch refusal still uses the existing model_id_missing outcome token (no new enum member)" "output: $OUT" ;;
esac
case "$OUT" in
    *"not in the approved registry"*)
        FAIL "provider/model mismatch refusal does NOT falsely claim the model is missing from the registry (mock-approved-b IS approved)" "output: $OUT" ;;
    *)
        PASS "provider/model mismatch refusal does NOT falsely claim the model is missing from the registry (mock-approved-b IS approved)" ;;
esac
if grep -q "not served" <<< "$OUT" && grep -q "prov_a" <<< "$OUT" && grep -q "mock-approved-b" <<< "$OUT"; then
    PASS "provider/model mismatch refusal states the model is not served by that provider, naming both the provider and the model id"
else
    FAIL "provider/model mismatch refusal states the model is not served by that provider, naming both the provider and the model id" "output: $OUT"
fi

# ══ T25 fixture: a THIRD approved id ("mock-approved-c") added to a fresh
# registry copy, layered on the SAME $CFGDIR_PIN config as T20/T24 (prov_a /
# prov_b). No server serves mock-approved-c — reuses the T20 servers, starts
# none new. ═══════════════════════════════════════════════════════════════
APPROVED_PIN3="$WORK/approved_pin3"
mkdir -p "$APPROVED_PIN3"
cp "$QWEN_RUN_SH" "$APPROVED_PIN3/qwen-run.sh"
cat > "$APPROVED_PIN3/approved-models.txt" <<'EOF'
# T25 registry: three approved ids; mock-approved-c is approved but live on
# neither provider in CFGDIR_PIN.
mock-approved-a
mock-approved-b
mock-approved-c
EOF
QWEN_RUN_SH_PIN3="$APPROVED_PIN3/qwen-run.sh"

# ══ T25: auto-detect (no -P) forcing an approved -m id that is live on NEITHER
# provider must name the ACTUAL cause. mock-approved-a and mock-approved-b are
# both live AND approved on $CFGDIR_PIN's two providers, so "no approved model
# id is live" would be false here — only the specific forced id
# (mock-approved-c) is unreachable. The refusal must name that id. ══════════
export STUB_ARGV_FILE="$WORK/t25.argv"
export STUB_STDIN_FILE="$WORK/t25.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_PIN" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH_PIN3" --approved-only -m mock-approved-c -f "$PROMPT_FILE_T" < /dev/null 2>&1)
RC=$?
if [ "$RC" -ne 0 ] && [ ! -f "$WORK/t25.argv" ]; then
    PASS "auto-detect forcing an approved -m id that is live on no provider is refused, not dispatched"
else
    FAIL "auto-detect forcing an approved -m id that is live on no provider is refused, not dispatched" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t25.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi
case "$OUT" in
    *model_id_missing*) PASS "forced-id-not-live refusal still uses the existing model_id_missing outcome token (no new enum member)" ;;
    *) FAIL "forced-id-not-live refusal still uses the existing model_id_missing outcome token (no new enum member)" "output: $OUT" ;;
esac
case "$OUT" in
    *"no approved model id is live"*)
        FAIL "forced-id-not-live refusal does NOT falsely claim no approved id at all is live (mock-approved-a and mock-approved-b both are)" "output: $OUT" ;;
    *)
        PASS "forced-id-not-live refusal does NOT falsely claim no approved id at all is live (mock-approved-a and mock-approved-b both are)" ;;
esac
case "$OUT" in
    *mock-approved-c*) PASS "forced-id-not-live refusal names the forced model id" ;;
    *) FAIL "forced-id-not-live refusal names the forced model id" "output: $OUT" ;;
esac

# ══ T26-T30: --register-model probes a live provider and upserts by id ═══════
# Independent fixture (fresh mock server + throwaway models.json copy) so
# these tests can freely mutate config without touching the shared fixtures
# used above.
MODE_FILE_REG="$WORK/mode_reg"
echo "ok" > "$MODE_FILE_REG"
PORT_REG=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 "$WORK/server.py" "$PORT_REG" "$MODE_FILE_REG" "unsloth/Qwen3.6-27B-MTP" &
SERVER_REG_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT_REG/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "FATAL: register-mode mock server did not start on port $PORT_REG"
        exit 1
    fi
    sleep 0.1
done

CFGDIR_REG="$WORK/agent_reg"
mkdir -p "$CFGDIR_REG"
cat > "$CFGDIR_REG/models.json" <<EOF
{"providers": {"regprov": {"baseUrl": "http://127.0.0.1:$PORT_REG/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": [{"id": "stale-placeholder"}]}}}
EOF

# T26: happy path - probed id lands in models.json, contextWindow falls back
# to 131072 (this mock, like real llama.cpp servers pre-meta, may omit
# meta.n_ctx), and pi is never dispatched (config-only operation).
export STUB_ARGV_FILE="$WORK/t26.argv"
export STUB_STDIN_FILE="$WORK/t26.stdin"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_REG" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH" --register-model -P regprov < /dev/null 2>&1)
RC=$?
if [ "$RC" -eq 0 ]; then
    PASS "--register-model exits 0 against a healthy live server"
else
    FAIL "--register-model exits 0 against a healthy live server" "rc=$RC; output: $OUT"
fi
if jq -e '.providers.regprov.models | any(.id == "unsloth/Qwen3.6-27B-MTP")' "$CFGDIR_REG/models.json" > /dev/null 2>&1; then
    PASS "--register-model writes the probed id (never a guessed/derived one) into models.json"
else
    FAIL "--register-model writes the probed id (never a guessed/derived one) into models.json" "models.json: $(cat "$CFGDIR_REG/models.json" 2>/dev/null)"
fi
CTX_GOT="$(jq -r '.providers.regprov.models[] | select(.id == "unsloth/Qwen3.6-27B-MTP") | .contextWindow' "$CFGDIR_REG/models.json" 2>/dev/null)"
if [ "$CTX_GOT" = "131072" ]; then
    PASS "--register-model falls back to contextWindow 131072 when the probe has no meta.n_ctx"
else
    FAIL "--register-model falls back to contextWindow 131072 when the probe has no meta.n_ctx" "got: $CTX_GOT"
fi
if [ ! -f "$WORK/t26.argv" ]; then
    PASS "--register-model never dispatches pi (config-only operation)"
else
    FAIL "--register-model never dispatches pi (config-only operation)" "stub pi ran with argv: $(tr '\n' ' ' < "$WORK/t26.argv")"
fi

# T27: re-running upserts in place - no duplicate entries, --name overrides
# the default label, and unrelated sibling entries are left untouched.
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_REG" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH" --register-model -P regprov --name "Qwen3.6 27B MTP" < /dev/null 2>&1)
RC=$?
COUNT_GOT="$(jq '[.providers.regprov.models[] | select(.id == "unsloth/Qwen3.6-27B-MTP")] | length' "$CFGDIR_REG/models.json" 2>/dev/null)"
if [ "$RC" -eq 0 ] && [ "$COUNT_GOT" = "1" ]; then
    PASS "re-running --register-model for the same id upserts in place (no duplicate entries)"
else
    FAIL "re-running --register-model for the same id upserts in place (no duplicate entries)" "rc=$RC; count=$COUNT_GOT; output: $OUT"
fi
NAME_GOT="$(jq -r '.providers.regprov.models[] | select(.id == "unsloth/Qwen3.6-27B-MTP") | .name' "$CFGDIR_REG/models.json" 2>/dev/null)"
if [ "$NAME_GOT" = "Qwen3.6 27B MTP" ]; then
    PASS "--name overrides the default (id-as-name) label"
else
    FAIL "--name overrides the default (id-as-name) label" "got: $NAME_GOT"
fi
STALE_STILL_THERE="$(jq '[.providers.regprov.models[] | select(.id == "stale-placeholder")] | length' "$CFGDIR_REG/models.json" 2>/dev/null)"
if [ "$STALE_STILL_THERE" = "1" ]; then
    PASS "--register-model does not disturb other pre-existing entries in the same provider"
else
    FAIL "--register-model does not disturb other pre-existing entries in the same provider" "count=$STALE_STILL_THERE"
fi

# T28: no -P is refused before touching the file.
BEFORE_HASH="$(md5 -q "$CFGDIR_REG/models.json" 2>/dev/null || md5sum "$CFGDIR_REG/models.json" | cut -d' ' -f1)"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_REG" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH" --register-model < /dev/null 2>&1)
RC=$?
AFTER_HASH="$(md5 -q "$CFGDIR_REG/models.json" 2>/dev/null || md5sum "$CFGDIR_REG/models.json" | cut -d' ' -f1)"
if [ "$RC" -ne 0 ]; then
    PASS "--register-model without -P/--provider is refused"
else
    FAIL "--register-model without -P/--provider is refused" "rc=0; output: $OUT"
fi
if [ "$BEFORE_HASH" = "$AFTER_HASH" ]; then
    PASS "--register-model without -P/--provider leaves models.json untouched"
else
    FAIL "--register-model without -P/--provider leaves models.json untouched" "file changed despite refusal"
fi

# T29: unknown provider name is refused (this adds models to an EXISTING
# provider only - it must not silently create one).
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_REG" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH" --register-model -P nope-does-not-exist < /dev/null 2>&1)
RC=$?
if [ "$RC" -ne 0 ]; then
    PASS "--register-model against an unconfigured provider name is refused"
else
    FAIL "--register-model against an unconfigured provider name is refused" "rc=0; output: $OUT"
fi

# T30: dead server names endpoint_unreachable (same honesty contract as the
# rest of the script - no silent no-op).
kill "$SERVER_REG_PID" 2>/dev/null
wait "$SERVER_REG_PID" 2>/dev/null
SERVER_REG_PID=""
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_REG" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH" --register-model -P regprov < /dev/null 2>&1)
RC=$?
if [ "$RC" -ne 0 ]; then
    PASS "--register-model against a dead server is refused"
else
    FAIL "--register-model against a dead server is refused" "rc=0; output: $OUT"
fi
case "$OUT" in
    *endpoint_unreachable*) PASS "--register-model dead-server refusal names endpoint_unreachable" ;;
    *) FAIL "--register-model dead-server refusal names endpoint_unreachable" "output: $OUT" ;;
esac

# ══ T31-T32: --register-model -m picks the id on multi-model servers ═════════
# LlamaBarn-style servers list every downloaded model in /v1/models, so
# .data[0] is not necessarily the model just added. -m selects the intended
# live id; an id the server does not list is refused (never written from a
# guess).
MODE_FILE_REG2="$WORK/mode_reg2"
echo "ok" > "$MODE_FILE_REG2"
PORT_REG2=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 "$WORK/server.py" "$PORT_REG2" "$MODE_FILE_REG2" "decoy-first-id" "wanted-second-id" &
SERVER_REG2_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT_REG2/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "FATAL: multi-model register mock server did not start on port $PORT_REG2"
        exit 1
    fi
    sleep 0.1
done

CFGDIR_REG2="$WORK/agent_reg2"
mkdir -p "$CFGDIR_REG2"
cat > "$CFGDIR_REG2/models.json" <<EOF
{"providers": {"regprov2": {"baseUrl": "http://127.0.0.1:$PORT_REG2/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": []}}}
EOF

# T31: -m registers the named live id, not .data[0].
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_REG2" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH" --register-model -P regprov2 -m wanted-second-id < /dev/null 2>&1)
RC=$?
WANTED_IN="$(jq '[.providers.regprov2.models[] | select(.id == "wanted-second-id")] | length' "$CFGDIR_REG2/models.json" 2>/dev/null)"
DECOY_IN="$(jq '[.providers.regprov2.models[] | select(.id == "decoy-first-id")] | length' "$CFGDIR_REG2/models.json" 2>/dev/null)"
if [ "$RC" -eq 0 ] && [ "$WANTED_IN" = "1" ] && [ "$DECOY_IN" = "0" ]; then
    PASS "--register-model -m registers the named id on a multi-model server (not .data[0])"
else
    FAIL "--register-model -m registers the named id on a multi-model server (not .data[0])" "rc=$RC; wanted=$WANTED_IN decoy=$DECOY_IN; output: $OUT"
fi

# T32: -m naming an id the live server does not list is refused, file untouched.
BEFORE_HASH="$(md5 -q "$CFGDIR_REG2/models.json" 2>/dev/null || md5sum "$CFGDIR_REG2/models.json" | cut -d' ' -f1)"
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_REG2" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH" --register-model -P regprov2 -m not-served-anywhere < /dev/null 2>&1)
RC=$?
AFTER_HASH="$(md5 -q "$CFGDIR_REG2/models.json" 2>/dev/null || md5sum "$CFGDIR_REG2/models.json" | cut -d' ' -f1)"
if [ "$RC" -ne 0 ] && [ "$BEFORE_HASH" = "$AFTER_HASH" ]; then
    PASS "--register-model -m with an id the server does not list is refused, models.json untouched"
else
    FAIL "--register-model -m with an id the server does not list is refused, models.json untouched" "rc=$RC; output: $OUT"
fi

# ══ T33-T36: promoted default steers resolution on multi-model servers ═══════
# promote-default.sh writes scripts/default-model.txt; resolution prefers that
# id whenever the resolved server lists it (--approved-only additionally
# demands it be approved). Without this, .data[0]/first-approved wins and a
# promotion is documentation-only: dispatches keep using the old model.
MODE_FILE_DEF="$WORK/mode_def"
echo "ok" > "$MODE_FILE_DEF"
PORT_DEF=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 "$WORK/server.py" "$PORT_DEF" "$MODE_FILE_DEF" "listed-first-id" "promoted-default-id" &
SERVER_DEF_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT_DEF/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "FATAL: default-pref mock server did not start on port $PORT_DEF"
        exit 1
    fi
    sleep 0.1
done

CFGDIR_DEF="$WORK/agent_def"
mkdir -p "$CFGDIR_DEF"
cat > "$CFGDIR_DEF/models.json" <<EOF
{"providers": {"defprov": {"baseUrl": "http://127.0.0.1:$PORT_DEF/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": [{"id": "listed-first-id"}, {"id": "promoted-default-id"}]}}}
EOF

# default-model.txt is resolved script-relative (same contract as the
# registry), so inject a fake one by copying the script next to it.
DEFAULT_WORK="$WORK/default"
mkdir -p "$DEFAULT_WORK"
cp "$QWEN_RUN_SH" "$DEFAULT_WORK/qwen-run.sh"
cat > "$DEFAULT_WORK/approved-models.txt" <<'EOF'
# fake registry for T34: BOTH ids approved, so only the default file can
# explain resolution skipping the first-listed one.
listed-first-id
promoted-default-id
EOF
cat > "$DEFAULT_WORK/default-model.txt" <<'EOF'
# fake promoted default for T33-T35
promoted-default-id
EOF

run_qwen3() {
    local name="$1"
    shift
    export STUB_ARGV_FILE="$WORK/$name.argv"
    export STUB_STDIN_FILE="$WORK/$name.stdin"
    OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_DEF" PATH="$STUBDIR:$PATH" bash "$DEFAULT_WORK/qwen-run.sh" "$@" < /dev/null 2>&1)
    RC=$?
}

# T33: plain dispatch prefers the promoted default over .data[0].
run_qwen3 t33 -f "$PROMPT_FILE_T"
if [ "$RC" -eq 0 ] && [ -f "$WORK/t33.argv" ] && grep -q "promoted-default-id" "$WORK/t33.argv" && ! grep -q "listed-first-id" "$WORK/t33.argv"; then
    PASS "plain dispatch prefers the promoted default over the first listed id"
else
    FAIL "plain dispatch prefers the promoted default over the first listed id" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t33.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# T34: --approved-only prefers the promoted default over an earlier-listed
# approved id (both approved - only the default file distinguishes them).
run_qwen3 t34 --approved-only -f "$PROMPT_FILE_T"
if [ "$RC" -eq 0 ] && [ -f "$WORK/t34.argv" ] && grep -q "promoted-default-id" "$WORK/t34.argv" && ! grep -q "listed-first-id" "$WORK/t34.argv"; then
    PASS "--approved-only prefers the promoted default over an earlier-listed approved id"
else
    FAIL "--approved-only prefers the promoted default over an earlier-listed approved id" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t34.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# T35: a promoted default that is not live anywhere falls back to the old
# behavior (first listed id) instead of refusing.
cat > "$DEFAULT_WORK/default-model.txt" <<'EOF'
not-live-anywhere-id
EOF
run_qwen3 t35 -f "$PROMPT_FILE_T"
if [ "$RC" -eq 0 ] && [ -f "$WORK/t35.argv" ] && grep -q "listed-first-id" "$WORK/t35.argv"; then
    PASS "a not-live promoted default falls back to the first listed id"
else
    FAIL "a not-live promoted default falls back to the first listed id" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t35.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi

# T36: the SHIPPED default-model.txt pins the documented default - promotion
# is now a four-file invariant (SKILL.md, qwen-integration.md, T19's
# SHIPPED_DEFAULT_ID, and the resolution-level default file).
SHIPPED_DEFAULT_FILE="$(dirname "$QWEN_RUN_SH")/default-model.txt"
if [ -f "$SHIPPED_DEFAULT_FILE" ] && grep -qFx -- "$SHIPPED_DEFAULT_ID" "$SHIPPED_DEFAULT_FILE"; then
    PASS "shipped default-model.txt exists and pins the documented default id"
else
    FAIL "shipped default-model.txt exists and pins the documented default id" "file: $SHIPPED_DEFAULT_FILE; content: $(cat "$SHIPPED_DEFAULT_FILE" 2>/dev/null || echo MISSING)"
fi

# ══ T37: the approved-only skip of a live-but-unapproved provider is LOUD ════
# 2026-07-19 incident: a server launched with --alias served an id without its
# quant tag, --approved-only silently skipped it, and every dispatch fell
# through to the next port for days with zero trace. Same fixture as T8 (low
# port live+unapproved, high port live+approved): dispatch must still land on
# the approved lane, AND stderr must name the skipped provider and its ids.
run_qwen2 t37 --approved-only -f "$PROMPT_FILE_T"
if [ "$RC" -eq 0 ] && [ -f "$WORK/t37.argv" ] && grep -q "mock-approved" "$WORK/t37.argv"; then
    PASS "loud skip does not change resolution (approved higher port still dispatches)"
else
    FAIL "loud skip does not change resolution (approved higher port still dispatches)" "rc=$RC; argv: $(tr '\n' ' ' < "$WORK/t37.argv" 2>/dev/null || echo MISSING); output: $OUT"
fi
if grep -q "WARNING" <<< "$OUT" && grep -q "llamacpp_low" <<< "$OUT" && grep -q "mock-unapproved" <<< "$OUT"; then
    PASS "skipping a live unapproved provider warns on stderr, naming the skipped provider and its live ids"
else
    FAIL "skipping a live unapproved provider warns on stderr, naming the skipped provider and its live ids" "output: $OUT"
fi

# T37b: the flagless path on the same fixture stays silent - the warning
# belongs to the approved-only gate, not to ordinary ascending-port probing.
run_qwen2 t37b -f "$PROMPT_FILE_T"
if [ "$RC" -eq 0 ] && ! grep -q "WARNING" <<< "$OUT"; then
    PASS "flagless dispatch on the same fixture emits no skip warning"
else
    FAIL "flagless dispatch on the same fixture emits no skip warning" "rc=$RC; output: $OUT"
fi

# ══ T38: --register-model warns when the served id carries no ':<quant>' tag ═
# The signature of a llama-server --alias: the id registers and evals fine but
# can never match the quant-exact approved registry, so --approved-only later
# skips the provider. Registration still succeeds (warning, not refusal - a
# local-file-served model may legitimately report a plain id). Reuses the T31
# multi-model server (decoy-first-id has no colon).
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_REG2" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH" --register-model -P regprov2 -m decoy-first-id < /dev/null 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && grep -q "no ':<quant>' tag" <<< "$OUT" && grep -q -- "--alias" <<< "$OUT"; then
    PASS "registering an id without a ':<quant>' tag still succeeds but warns, naming --alias as the likely cause"
else
    FAIL "registering an id without a ':<quant>' tag still succeeds but warns, naming --alias as the likely cause" "rc=$RC; output: $OUT"
fi

# ══ T39: a quant-tagged id registers with NO alias warning ═══════════════════
MODE_FILE_REG3="$WORK/mode_reg3"
echo "ok" > "$MODE_FILE_REG3"
PORT_REG3=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 "$WORK/server.py" "$PORT_REG3" "$MODE_FILE_REG3" "org/Mock-GGUF:Q6_K" &
SERVER_REG3_PID=$!
i=0
until curl -sf --max-time 1 "http://127.0.0.1:$PORT_REG3/v1/models" > /dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "FATAL: quant-id register mock server did not start on port $PORT_REG3"
        exit 1
    fi
    sleep 0.1
done
CFGDIR_REG3="$WORK/agent_reg3"
mkdir -p "$CFGDIR_REG3"
cat > "$CFGDIR_REG3/models.json" <<EOF
{"providers": {"regprov3": {"baseUrl": "http://127.0.0.1:$PORT_REG3/v1", "api": "openai-completions", "apiKey": "llamacpp", "models": []}}}
EOF
OUT=$(PI_CODING_AGENT_DIR="$CFGDIR_REG3" PATH="$STUBDIR:$PATH" bash "$QWEN_RUN_SH" --register-model -P regprov3 < /dev/null 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && ! grep -q "no ':<quant>' tag" <<< "$OUT"; then
    PASS "registering a quant-tagged id emits no alias warning"
else
    FAIL "registering a quant-tagged id emits no alias warning" "rc=$RC; output: $OUT"
fi

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS_COUNT passed, $FAIL_COUNT failed"
[ "$FAIL_COUNT" -eq 0 ] || exit 1
