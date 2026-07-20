#!/usr/bin/env bash
# test_autoclaude_plugin_pin.sh — plugin-version pin for the `autoclaude` wrapper
# (~/.config/bash/plugins/development.plugin.bash), PRD 00086 R3.
#
# A batch pins its enforcement plugins' versions (state.batch.plugin_versions) at
# selection; the wrapper's preflight compares that pin against what is installed
# now before each session launch and, on drift (aegis/warden auto-updated
# mid-batch), halts loud with state intact rather than run on rotated
# enforcement code. This suite binds:
#   1. _autopilot_plugin_drift — pure decision (0 = match/no-pin, 1 = drift).
#   2. A drifted pin halts the wrapper loud BEFORE any session launches.
#
# Run: bash ~/.claude/skills/run-autopilot/scripts/test_autoclaude_plugin_pin.sh
set -u

# ── source the plugin (stubs silence the bash-it bootstrap calls) ─────────────
cite() { :; }
about-plugin() { :; }
source ~/.config/bash/plugins/development.plugin.bash

# ── assert helpers ────────────────────────────────────────────────────────────
PASS() { echo "PASS: $1"; }
FAIL() { echo "FAIL: $1 — $2"; exit 1; }

_PIDS=()
_DIRS=()
cleanup() {
  local p d
  for p in "${_PIDS[@]+"${_PIDS[@]}"}"; do kill -KILL "$p" 2>/dev/null || true; done
  for d in "${_DIRS[@]+"${_DIRS[@]}"}"; do rm -rf "$d"; done
}
trap cleanup EXIT

# ── coverage 1: the decision function must be defined ─────────────────────────
type _autopilot_plugin_drift >/dev/null 2>&1 \
  || FAIL "function defined: _autopilot_plugin_drift" "not defined in development.plugin.bash — implement it first"
PASS "_autopilot_plugin_drift defined"

# ── coverage 2: unit tests for _autopilot_plugin_drift ────────────────────────
U=$(mktemp -d); _DIRS+=("$U")
INSTALLED="$U/installed.json"
cat >"$INSTALLED" <<'EOF'
{"plugins": {
  "aegis@buvis-plugins":  [{"version": "0.3.1"}],
  "warden@buvis-plugins": [{"version": "0.13.0"}]
}}
EOF

# match: pin equals installed -> exit 0
printf '%s\n' '{"batch":{"plugin_versions":{"aegis@buvis-plugins":"0.3.1","warden@buvis-plugins":"0.13.0"}}}' >"$U/state-match.json"
if _autopilot_plugin_drift "$U/state-match.json" "$INSTALLED" >/dev/null; then
  PASS "drift: matching pin -> exit 0 (no drift)"
else
  FAIL "drift: matching pin should be no-drift" "returned nonzero"
fi

# drift: pinned aegis differs from installed -> exit 1, names the plugin
printf '%s\n' '{"batch":{"plugin_versions":{"aegis@buvis-plugins":"0.3.0","warden@buvis-plugins":"0.13.0"}}}' >"$U/state-drift.json"
if out=$(_autopilot_plugin_drift "$U/state-drift.json" "$INSTALLED"); then
  FAIL "drift: bumped aegis should be drift" "returned 0, out='$out'"
else
  case "$out" in
    *aegis*pinned=0.3.0*now=0.3.1*) PASS "drift: bumped enforcement plugin -> exit 1 ($out)" ;;
    *) FAIL "drift: message names plugin+versions" "got '$out'" ;;
  esac
fi

# no pin recorded (pre-R3 batch) -> exit 0, backward-compatible
printf '%s\n' '{"batch":{"id":"x"}}' >"$U/state-nopin.json"
if _autopilot_plugin_drift "$U/state-nopin.json" "$INSTALLED" >/dev/null; then
  PASS "drift: unpinned batch -> exit 0 (never blocked)"
else
  FAIL "drift: unpinned batch must not block" "returned nonzero"
fi

# pinned plugin absent from installed manifest -> MISSING != pin -> drift
printf '%s\n' '{"batch":{"plugin_versions":{"ghost@buvis-plugins":"1.0.0"}}}' >"$U/state-ghost.json"
if _autopilot_plugin_drift "$U/state-ghost.json" "$INSTALLED" >/dev/null; then
  FAIL "drift: a pinned-but-uninstalled plugin should be drift" "returned 0"
else
  PASS "drift: pinned plugin missing from install -> drift (MISSING)"
fi

# ── coverage 3: scenario — a drifted pin halts the wrapper before any launch ──
export _AUTOPILOT_TRACON=0
sysctl() { echo 1; }                                   # no memory pressure
python3() {
  case "$*" in
    *_walk_up.py*)           printf '%s\n' "$AP_DIR" ;;
    *detect_usage_limit.py*) return 1 ;;
    *notify.py*)             : ;;
    *purge_devlocal.py*)     : ;;
    *)                       command python3 "$@" ;;
  esac
}
_autopilot_session_cap() { :; }

run_with_timeout() {
  local dir="$1" timeout="$2"
  (
    cd "$dir" || exit 90
    AP_DIR="$dir/dev/local/autopilot"
    _AUTOPILOT_LOOPS_DIR="$dir/loops"
    PATH="$dir/bin:$PATH"
    unset _AUTOPILOT_TRACON_CHILD _AUTOPILOT_LOOP
    set +u
    autoclaude
  ) >"$dir/stdout.log" 2>"$dir/stderr.log" &
  local run_pid=$!
  ( sleep "$timeout"; touch "$dir/.timeout-fired"; kill -KILL "$run_pid" 2>/dev/null ) &
  local safety_pid=$!
  _PIDS+=("$run_pid" "$safety_pid")
  wait "$run_pid" 2>/dev/null
  RUN_RC=$?
  kill "$safety_pid" 2>/dev/null
  wait "$safety_pid" 2>/dev/null
}

SBOX=$(mktemp -d); _DIRS+=("$SBOX")
mkdir -p "$SBOX/dev/local/autopilot" "$SBOX/bin"
# The batch pinned aegis 0.3.0; the installed manifest below says 0.3.1 -> drift.
printf '%s\n' '{"prd":"00001-x.md","next_phase":"build","batch":{"id":"p1","plugin_versions":{"aegis@buvis-plugins":"0.3.0"}}}' \
  >"$SBOX/dev/local/autopilot/state.json"
touch -t 202601010000 "$SBOX/dev/local/autopilot/state.json"
cat >"$SBOX/installed.json" <<'EOF'
{"plugins": {"aegis@buvis-plugins": [{"version": "0.3.1"}]}}
EOF

# stub claude records whether it was ever launched (it must NOT be, on drift).
cat >"$SBOX/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
printf 'x' >>"$DIR/claude-called"
echo '{"type":"result","subtype":"success","total_cost_usd":0.01,"usage":{"output_tokens":5}}'
exit 0
EOF
chmod +x "$SBOX/bin/claude"

_AUTOPILOT_PLUGINS_JSON="$SBOX/installed.json" run_with_timeout "$SBOX" 15
rc=$RUN_RC
[ -f "$SBOX/.timeout-fired" ] && FAIL "scenario drift-halt: safety timeout" "loop did not converge within 15s"
[ "$rc" -eq 1 ] || FAIL "scenario drift-halt: plugin drift halts loud" "rc=$rc"
[ ! -f "$SBOX/claude-called" ] \
  || FAIL "scenario drift-halt: no session launched on drift" "claude was called despite the version drift"
grep -qi "plugin version drift" "$SBOX/stderr.log" \
  || FAIL "scenario drift-halt: halts with a plugin-drift message" "$(cat "$SBOX/stderr.log")"
PASS "a mid-batch enforcement-plugin bump halts the wrapper loud before any session launches (claude never called)"

echo ""
echo "All checks passed."
exit 0
