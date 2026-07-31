#!/usr/bin/env bash
# test_autoclaude_state_write_failed.sh — state-write-failed marker halt path
# for the `autoclaude` wrapper (~/.config/bash/plugins/development.plugin.bash).
#
# PRD 00051 task 9: a broken state boundary (cli/ unimportable, or the state
# transaction raising) leaves a one-line JSON marker at
# <autopilot_dir>/state-write-failed ({"site":"statectl_fail","detail":...}),
# written without depending on cli/ (the recovery path must not depend on the
# thing that just failed). The wrapper's post-session decision logic gains
# one row AHEAD of every other branch: marker present -> print its detail,
# notify, and STOP the loop (like a pause), WITHOUT needing state.json to be
# readable or writable. The marker is LEFT IN PLACE (forensic; a human clears
# it) — the wrapper does not delete it.
#
# The feature does not exist yet: this suite is RED today (the wrapper has no
# state-write-failed branch, so a pre-existing marker is ignored and the loop
# keeps relaunching on the otherwise-continue state.json until the safety
# timeout force-kills it). It turns GREEN once the marker row lands in the
# wrapper's post-session decision logic.
#
# Written without having seen the wrapper's implementation of this branch;
# mirrors test_autoclaude_park.sh's sourcing, stubbing, and run_with_timeout
# technique (the only driving technique available for this wrapper).
#
# Run: bash ~/.claude/skills/run-autopilot/scripts/test_autoclaude_state_write_failed.sh
set -u

# ── source the plugin (stubs silence the bash-it bootstrap calls) ─────────────
cite() { :; }
about-plugin() { :; }
source ~/.config/bash/plugins/development.plugin.bash

# ── assert helpers ────────────────────────────────────────────────────────────
PASS() { echo "PASS: $1"; }
FAIL() { echo "FAIL: $1 — $2"; exit 1; }

# ── cleanup registry ──────────────────────────────────────────────────────────
_PIDS=()
_DIRS=()

cleanup() {
    local p d
    for p in "${_PIDS[@]+"${_PIDS[@]}"}"; do
        kill -KILL "$p" 2>/dev/null || true
    done
    for d in "${_DIRS[@]+"${_DIRS[@]}"}"; do
        rm -rf "$d"
    done
}
trap cleanup EXIT

# ── global stubs (win over external commands; defined AFTER source) ───────────
# Never let a scenario touch the real machine: no memory-pressure wait, no
# real loop-registry writes, no real notifications/purges, no tracon TUI.
export _AUTOPILOT_TRACON=0
sysctl() { echo 1; }                                   # no memory pressure
python3() {
  case "$*" in
    *_walk_up.py*)           printf '%s\n' "$AP_DIR" ;; # resolve ap dir -> sandbox
    *detect_usage_limit.py*) return 1 ;;                # not usage-limited
    *notify.py*)             : ;;                       # swallow notifications
    *purge_devlocal.py*)     : ;;                        # swallow the drained-path purge
    *)                       command python3 "$@" ;;     # real python3 (mtime, render_stream)
  esac
}
_autopilot_session_cap() { :; }                        # no background wall-clock sidecar

# ── run_with_timeout <sandbox_dir> <timeout_secs> ──────────────────────────────
# Runs `autoclaude` inside <sandbox_dir> (cwd + PATH pointed at its bin/ stub),
# backgrounded under a safety-kill so a broken/unimplemented decision branch
# that loops forever is force-killed rather than hanging the suite. stdout/
# stderr land in <sandbox_dir>/{stdout,stderr}.log; the exit code lands in
# $RUN_RC. If the safety-kill actually had to fire, <sandbox_dir>/.timeout-fired
# is created — callers must check for it before trusting $RUN_RC.
run_with_timeout() {
  local dir="$1" timeout="$2"
  (
    cd "$dir" || exit 90
    AP_DIR="$dir/dev/local/autopilot"
    _AUTOPILOT_LOOPS_DIR="$dir/loops"
    PATH="$dir/bin:$PATH"
    # This suite may itself run from inside an autoclaude loop (a headless
    # review session, or a nested batch), which exports _AUTOPILOT_TRACON_CHILD
    # and _AUTOPILOT_LOOP into every subshell. The sandboxed autoclaude below is
    # NOT a process-group leader, so an inherited _AUTOPILOT_TRACON_CHILD trips
    # its pgrp self-guard and every scenario returns 1. Strip both so the
    # sandbox runs a clean top-level loop; autoclaude re-exports its own
    # _AUTOPILOT_LOOP. (_AUTOPILOT_LOOPS_DIR is already overridden above.)
    unset _AUTOPILOT_TRACON_CHILD _AUTOPILOT_LOOP
    # The wrapper targets a normal interactive shell (no set -u); the suite's
    # own `set -u` would trip pre-existing unguarded expansions inside
    # autoclaude (e.g. _AUTOPILOT_TRACON_CHILD) before any session launches.
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

# =============================================================================
# Coverage 1 — state-write-failed marker present at the post-session decision
# point wins over an otherwise-continue state.json (next_phase: "build"): the
# wrapper halts after the in-flight session instead of relaunching, prints
# the marker's detail, and leaves the marker in place (not consumed).
# =============================================================================

SBOX_A=$(mktemp -d); _DIRS+=("$SBOX_A")
mkdir -p "$SBOX_A/dev/local/autopilot" "$SBOX_A/bin"
printf '%s\n' '{"prd":"00001-x.md","next_phase":"build","batch":{"id":"a1"}}' \
  >"$SBOX_A/dev/local/autopilot/state.json"

DETAIL_A='DISTINCTIVE_STATE_WRITE_FAILED_DETAIL_9f3c'
printf '%s\n' "{\"site\":\"statectl_fail\",\"detail\":\"$DETAIL_A\"}" \
  >"$SBOX_A/dev/local/autopilot/state-write-failed"

cat >"$SBOX_A/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
COUNTER="$DIR/claude-calls.count"
N=$(( $(cat "$COUNTER" 2>/dev/null || echo 0) + 1 ))
printf '%s\n' "$N" >"$COUNTER"
# A normal, healthy session that would otherwise continue the loop: it
# touches state.json and leaves next_phase on "build".
printf '%s\n' '{"prd":"00001-x.md","next_phase":"build","batch":{"id":"a1"}}' \
  >"$DIR/dev/local/autopilot/state.json"
echo '{"type":"result","subtype":"success","total_cost_usd":0.01,"usage":{"output_tokens":10}}'
exit 0
EOF
chmod +x "$SBOX_A/bin/claude"

run_with_timeout "$SBOX_A" 15
rc_a=$RUN_RC
[ -f "$SBOX_A/.timeout-fired" ] \
  && FAIL "state-write-failed marker halts instead of looping forever" \
          "loop did not converge within 15s — the marker branch is missing (no halt), so the otherwise-continue state.json kept relaunching claude"

[ "$rc_a" -eq 1 ] \
  || FAIL "state-write-failed marker halts the loop (non-zero exit, like a pause)" "rc=$rc_a"

grep -q "$DETAIL_A" "$SBOX_A/stdout.log" "$SBOX_A/stderr.log" 2>/dev/null \
  || FAIL "wrapper output contains the marker's detail text" \
          "stdout: $(cat "$SBOX_A/stdout.log") / stderr: $(cat "$SBOX_A/stderr.log")"

calls_a=$(cat "$SBOX_A/claude-calls.count" 2>/dev/null || echo 0)
[ "$calls_a" -eq 1 ] \
  || FAIL "marker check wins AHEAD of the otherwise-continue branch (loop does not relaunch)" \
          "expected exactly 1 claude call before halt, got $calls_a"

[ -f "$SBOX_A/dev/local/autopilot/state-write-failed" ] \
  || FAIL "marker is left in place after the halt (not consumed)" "marker file is gone"

PASS "state-write-failed marker wins over an otherwise-continue state.json (next_phase: build): wrapper halts after 1 session, prints the marker's detail, and leaves the marker in place"

# =============================================================================
echo ""
echo "All checks passed."
exit 0
