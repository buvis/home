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
cleanup() {
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
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

cat > "$WORK/server.py" <<'PY'
import http.server
import json
import sys

PORT = int(sys.argv[1])
MODE_FILE = sys.argv[2]


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip('/') == '/v1/models':
            body = json.dumps({"object": "list", "data": [{"id": "mock-qwen", "object": "model"}]}).encode()
            self._send(200, body)
        else:
            self._send(404, b'{}')

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        self.rfile.read(n)
        with open(MODE_FILE) as f:
            mode = f.read().strip()
        if self.path.rstrip('/') == '/v1/chat/completions' and mode == 'ok':
            body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "x"}}]}).encode()
            self._send(200, body)
        else:
            self._send(500, b'{"error": "failed to spawn server instance"}')


http.server.HTTPServer(('127.0.0.1', PORT), H).serve_forever()
PY

PORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 "$WORK/server.py" "$PORT" "$MODE_FILE" &
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

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS_COUNT passed, $FAIL_COUNT failed"
[ "$FAIL_COUNT" -eq 0 ] || exit 1
