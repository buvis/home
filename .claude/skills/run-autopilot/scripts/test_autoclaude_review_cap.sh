#!/usr/bin/env bash
# test_autoclaude_review_cap.sh — the session-cap sidecar's wall-clock budget
# must depend on the LAUNCH PHASE (~/.config/bash/plugins/development.plugin.bash).
#
# The wrapper arms one background sidecar per session launch:
#   _autopilot_session_cap "$_AUTOPILOT_LOOP" "<cap_seconds>" 30 60 &
# <cap_seconds> (the sidecar's 2nd positional arg) must be chosen from
# state.json's next_phase AT LAUNCH:
#   next_phase == "review"  -> _AUTOPILOT_SESSION_MAX_REVIEW, default 10800
#   anything else            -> _AUTOPILOT_SESSION_MAX,        default 7200
#                                (a build-phase launch must IGNORE
#                                _AUTOPILOT_SESSION_MAX_REVIEW entirely)
#
# Today the wrapper arms the sidecar (line ~378) BEFORE it even reads
# next_phase from state.json (line ~396) — a single hardcoded
# ${_AUTOPILOT_SESSION_MAX:-7200} regardless of phase. This suite is RED by
# design until the wrapper selects the cap per phase; scenarios 1/2/4 below
# fail against today's code (scenario 3 happens to pass, since build's
# expected default equals today's only cap).
#
# Technique: override _autopilot_session_cap so it RECORDS its 2nd arg
# instead of running a real sidecar, drive the wrapper for exactly one loop
# iteration (a stub `claude` that drains on its first call), then assert the
# recording has EXACTLY ONE line equal to the expected cap — both the count
# (one sidecar armed, not two) and the value (the right cap for the phase).
#
# Run: bash ~/.claude/skills/run-autopilot/scripts/test_autoclaude_review_cap.sh
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
# real loop-registry writes, no real notifications/purges, no tracon TUI, no
# real wall-clock sidecar — record its cap arg instead of running it.
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
_autopilot_session_cap() { echo "$2" >> "$AP_DIR/.cap-args"; }  # record the cap instead of arming a real sidecar

# ── run_with_timeout <sandbox_dir> <timeout_secs> ──────────────────────────────
# Runs `autoclaude` inside <sandbox_dir> (cwd + PATH pointed at its bin/ stub),
# backgrounded under a safety-kill so a broken implementation that never
# converges is force-killed rather than hanging the suite. stdout/stderr land
# in <sandbox_dir>/{stdout,stderr}.log; the exit code lands in $RUN_RC. If the
# safety-kill actually had to fire, <sandbox_dir>/.timeout-fired is created —
# callers must check for it before trusting $RUN_RC.
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

# write_stub_claude <sandbox_dir> — the SIMPLE drain-immediately variant: on
# its (only) call, writes a TERMINAL state.json (next_phase empty) so the
# wrapper's decision table takes signal=done after exactly one iteration —
# exactly one _autopilot_session_cap arming happens per scenario.
write_stub_claude() {
  local dir="$1"
  cat >"$dir/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
printf '%s\n' '{"prd":"00001-x.md","next_phase":""}' >"$DIR/dev/local/autopilot/state.json"
echo '{"type":"result","subtype":"success","total_cost_usd":0.01,"usage":{"output_tokens":10}}'
exit 0
EOF
  chmod +x "$dir/bin/claude"
}

# assert_cap_file <sandbox_dir> <label> <expected_cap> — the core assertion:
# .cap-args must have EXACTLY ONE line, equal to the expected cap. Two lines
# would mean the wrapper armed two sidecars for one launch; a wrong value
# means the phase->cap selection is missing or wrong.
assert_cap_file() {
  local dir="$1" label="$2" expected="$3"
  local capfile="$dir/dev/local/autopilot/.cap-args"
  [ -f "$capfile" ] || FAIL "$label: .cap-args recorded" "no file at $capfile"
  local lines
  lines=$(grep -c . "$capfile")
  [ "$lines" -eq 1 ] \
    || FAIL "$label: exactly one sidecar armed" "got $lines lines: $(cat "$capfile" 2>/dev/null)"
  local got
  got=$(cat "$capfile")
  [ "$got" = "$expected" ] \
    || FAIL "$label: cap == $expected" "got '$got'"
  PASS "$label: exactly one sidecar armed with cap=$expected"
}

# =============================================================================
# Scenario 1 — review phase, no cap env vars -> default 10800
# =============================================================================

SBOX_1=$(mktemp -d); _DIRS+=("$SBOX_1")
mkdir -p "$SBOX_1/dev/local/autopilot" "$SBOX_1/bin"
printf '%s\n' '{"prd":"00001-x.md","next_phase":"review","batch":{"id":"r1"}}' \
  >"$SBOX_1/dev/local/autopilot/state.json"
write_stub_claude "$SBOX_1"

run_with_timeout "$SBOX_1" 15
rc_1=$RUN_RC
[ -f "$SBOX_1/.timeout-fired" ] && FAIL "scenario 1 (review, default)" "safety timeout — loop did not converge within 15s"
[ "$rc_1" -eq 0 ] \
  || FAIL "scenario 1 (review, default): drained loop returns 0" "rc=$rc_1; stdout=$(cat "$SBOX_1/stdout.log" 2>/dev/null); stderr=$(cat "$SBOX_1/stderr.log" 2>/dev/null)"
grep -q "Backlog drained" "$SBOX_1/stdout.log" \
  || FAIL "scenario 1 (review, default): prints Backlog drained" "$(cat "$SBOX_1/stdout.log" 2>/dev/null)"
assert_cap_file "$SBOX_1" "scenario 1 (review, default)" "10800"

# =============================================================================
# Scenario 2 — review phase, _AUTOPILOT_SESSION_MAX_REVIEW=9999 -> 9999
# =============================================================================

SBOX_2=$(mktemp -d); _DIRS+=("$SBOX_2")
mkdir -p "$SBOX_2/dev/local/autopilot" "$SBOX_2/bin"
printf '%s\n' '{"prd":"00001-x.md","next_phase":"review","batch":{"id":"r2"}}' \
  >"$SBOX_2/dev/local/autopilot/state.json"
write_stub_claude "$SBOX_2"

_AUTOPILOT_SESSION_MAX_REVIEW=9999 run_with_timeout "$SBOX_2" 15
rc_2=$RUN_RC
[ -f "$SBOX_2/.timeout-fired" ] && FAIL "scenario 2 (review, env override)" "safety timeout — loop did not converge within 15s"
[ "$rc_2" -eq 0 ] \
  || FAIL "scenario 2 (review, env override): drained loop returns 0" "rc=$rc_2; stdout=$(cat "$SBOX_2/stdout.log" 2>/dev/null); stderr=$(cat "$SBOX_2/stderr.log" 2>/dev/null)"
grep -q "Backlog drained" "$SBOX_2/stdout.log" \
  || FAIL "scenario 2 (review, env override): prints Backlog drained" "$(cat "$SBOX_2/stdout.log" 2>/dev/null)"
assert_cap_file "$SBOX_2" "scenario 2 (review, _AUTOPILOT_SESSION_MAX_REVIEW=9999)" "9999"

# =============================================================================
# Scenario 3 — build phase, no cap env vars -> default 7200
# =============================================================================

SBOX_3=$(mktemp -d); _DIRS+=("$SBOX_3")
mkdir -p "$SBOX_3/dev/local/autopilot" "$SBOX_3/bin"
printf '%s\n' '{"prd":"00001-x.md","next_phase":"build","batch":{"id":"b1"}}' \
  >"$SBOX_3/dev/local/autopilot/state.json"
write_stub_claude "$SBOX_3"

run_with_timeout "$SBOX_3" 15
rc_3=$RUN_RC
[ -f "$SBOX_3/.timeout-fired" ] && FAIL "scenario 3 (build, default)" "safety timeout — loop did not converge within 15s"
[ "$rc_3" -eq 0 ] \
  || FAIL "scenario 3 (build, default): drained loop returns 0" "rc=$rc_3; stdout=$(cat "$SBOX_3/stdout.log" 2>/dev/null); stderr=$(cat "$SBOX_3/stderr.log" 2>/dev/null)"
grep -q "Backlog drained" "$SBOX_3/stdout.log" \
  || FAIL "scenario 3 (build, default): prints Backlog drained" "$(cat "$SBOX_3/stdout.log" 2>/dev/null)"
assert_cap_file "$SBOX_3" "scenario 3 (build, default)" "7200"

# =============================================================================
# Scenario 4 — build phase, BOTH _AUTOPILOT_SESSION_MAX_REVIEW=9999 and
# _AUTOPILOT_SESSION_MAX=5555 set -> 5555 (build honors the global knob and
# ignores the review knob entirely)
# =============================================================================

SBOX_4=$(mktemp -d); _DIRS+=("$SBOX_4")
mkdir -p "$SBOX_4/dev/local/autopilot" "$SBOX_4/bin"
printf '%s\n' '{"prd":"00001-x.md","next_phase":"build","batch":{"id":"b2"}}' \
  >"$SBOX_4/dev/local/autopilot/state.json"
write_stub_claude "$SBOX_4"

_AUTOPILOT_SESSION_MAX_REVIEW=9999 _AUTOPILOT_SESSION_MAX=5555 run_with_timeout "$SBOX_4" 15
rc_4=$RUN_RC
[ -f "$SBOX_4/.timeout-fired" ] && FAIL "scenario 4 (build, both env vars)" "safety timeout — loop did not converge within 15s"
[ "$rc_4" -eq 0 ] \
  || FAIL "scenario 4 (build, both env vars): drained loop returns 0" "rc=$rc_4; stdout=$(cat "$SBOX_4/stdout.log" 2>/dev/null); stderr=$(cat "$SBOX_4/stderr.log" 2>/dev/null)"
grep -q "Backlog drained" "$SBOX_4/stdout.log" \
  || FAIL "scenario 4 (build, both env vars): prints Backlog drained" "$(cat "$SBOX_4/stdout.log" 2>/dev/null)"
assert_cap_file "$SBOX_4" "scenario 4 (build, _AUTOPILOT_SESSION_MAX_REVIEW=9999 + _AUTOPILOT_SESSION_MAX=5555, ignores review knob)" "5555"

# =============================================================================
echo ""
echo "All checks passed."
exit 0
