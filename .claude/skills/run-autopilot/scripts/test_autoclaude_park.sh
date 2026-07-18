#!/usr/bin/env bash
# test_autoclaude_park.sh — died-retry, park-signal, and park-marker write for
# the `autoclaude` wrapper (~/.config/bash/plugins/development.plugin.bash).
#
# Today a session that dies without touching dev/local/autopilot/state.json
# halts the whole loop (return 1). This suite binds the new contract:
#   1. _autopilot_died_next PRD RETRIES MAX — pure decision (retry|park|die).
#   2. A died session with a selected PRD is retried up to
#      _AUTOPILOT_DIED_RETRIES_MAX (default 1) consecutive times.
#   3. On retry exhaustion the wrapper writes dev/local/autopilot/park-requested
#      (one-line JSON {"prd":..., "reason":...}) and RELAUNCHES — it does not
#      halt and does not touch state.json.
#   4. If the park path is reached again with the marker already present
#      (unconsumed), the wrapper relaunches at most _AUTOPILOT_DIED_RETRIES_MAX
#      more times (sleeping _AUTOPILOT_PARK_BACKOFF between), then halts loud.
#      A pre-existing marker older than _AUTOPILOT_SESSION_MAX halts loud
#      immediately, with zero guarded relaunches, and the marker is never
#      overwritten.
#   5. A died session with NO state.json at all (bootstrap) still halts loud,
#      exactly as today, and writes no marker.
#
# The feature does not exist yet: this suite is RED today at the coverage-1
# function guard by design, and turns GREEN once _autopilot_died_next and the
# park/died-retry wiring land in the plugin.
#
# Run: bash ~/.claude/skills/run-autopilot/scripts/test_autoclaude_park.sh
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

# ── coverage 1: the decision function must be defined ─────────────────────────
type _autopilot_died_next >/dev/null 2>&1 \
    || FAIL "function defined: _autopilot_died_next" "not defined in development.plugin.bash — implement it first"
PASS "_autopilot_died_next defined"

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
# Coverage 2: unit tests for _autopilot_died_next PRD RETRIES MAX
# =============================================================================

out=$(_autopilot_died_next "00001-x.md" 0 1)
[ "$out" = "retry" ] || FAIL "died_next: retries < max -> retry" "got '$out' for (00001-x.md, 0, 1)"
PASS "died_next(00001-x.md, 0, 1) = retry"

out=$(_autopilot_died_next "00001-x.md" 1 1)
[ "$out" = "park" ] || FAIL "died_next: retries == max -> park" "got '$out' for (00001-x.md, 1, 1)"
PASS "died_next(00001-x.md, 1, 1) = park"

out=$(_autopilot_died_next "" 0 1)
[ "$out" = "die" ] || FAIL "died_next: empty prd (bootstrap) -> die" "got '$out' for ('', 0, 1)"
PASS "died_next('', 0, 1) = die"

out=$(_autopilot_died_next "00001-x.md" 2 1)
[ "$out" = "park" ] || FAIL "died_next: retries > max -> park" "got '$out' for (00001-x.md, 2, 1)"
PASS "died_next(00001-x.md, 2, 1) = park"

# =============================================================================
# Coverage 3 — scenario (a): died session then recovery continues the batch,
# counter reset, no park marker
# =============================================================================

SBOX_A=$(mktemp -d); _DIRS+=("$SBOX_A")
mkdir -p "$SBOX_A/dev/local/autopilot" "$SBOX_A/bin"
printf '%s\n' '{"prd":"00001-x.md","next_phase":"build","batch":{"id":"a1"}}' \
  >"$SBOX_A/dev/local/autopilot/state.json"
# Backdate: a fixture written in the launch second would read as "touched by
# the session" (state_touched=1) and the died branch would never be reached.
touch -t 202601010000 "$SBOX_A/dev/local/autopilot/state.json"

cat >"$SBOX_A/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
COUNTER="$DIR/claude-calls.count"
N=$(( $(cat "$COUNTER" 2>/dev/null || echo 0) + 1 ))
printf '%s\n' "$N" >"$COUNTER"
if [ "$N" -eq 1 ]; then
  echo '{"type":"result","subtype":"success","result":"stub death (state untouched)"}'
  exit 0
fi
printf '%s\n' '{"prd":"00001-x.md","next_phase":""}' >"$DIR/dev/local/autopilot/state.json"
echo '{"type":"result","subtype":"success","total_cost_usd":0.01,"usage":{"output_tokens":10}}'
exit 0
EOF
chmod +x "$SBOX_A/bin/claude"

run_with_timeout "$SBOX_A" 15
rc_a=$RUN_RC
[ -f "$SBOX_A/.timeout-fired" ] && FAIL "scenario a: safety timeout" "loop did not converge within 15s"
[ "$rc_a" -eq 0 ] || FAIL "scenario a: drained loop returns 0" "rc=$rc_a"
grep -q "Backlog drained" "$SBOX_A/stdout.log" \
  || FAIL "scenario a: prints Backlog drained" "$(cat "$SBOX_A/stdout.log")"
calls_a=$(cat "$SBOX_A/claude-calls.count" 2>/dev/null || echo 0)
[ "$calls_a" -eq 2 ] || FAIL "scenario a: stub called exactly twice (died then recovered, not halted)" "got $calls_a calls"
[ ! -f "$SBOX_A/dev/local/autopilot/park-requested" ] \
  || FAIL "scenario a: no park marker on a retried recovery" "marker was written"
PASS "died session retried (not halted); recovery drains the batch, no park marker (calls=$calls_a)"

# =============================================================================
# Coverage 4 — scenario (b): retry exhaustion writes marker naming state.prd,
# relaunches, then halts loud on the unconsumed-marker guard
# =============================================================================

SBOX_B=$(mktemp -d); _DIRS+=("$SBOX_B")
mkdir -p "$SBOX_B/dev/local/autopilot" "$SBOX_B/bin"
printf '%s\n' '{"prd":"00002-y.md","next_phase":"build","batch":{"id":"b1"}}' \
  >"$SBOX_B/dev/local/autopilot/state.json"
touch -t 202601010000 "$SBOX_B/dev/local/autopilot/state.json"

cat >"$SBOX_B/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
COUNTER="$DIR/claude-calls.count"
MARKERLOG="$DIR/marker-seen.log"
MARKER="$DIR/dev/local/autopilot/park-requested"
N=$(( $(cat "$COUNTER" 2>/dev/null || echo 0) + 1 ))
printf '%s\n' "$N" >"$COUNTER"
[ -f "$MARKER" ] && printf '%s\n' "$N" >>"$MARKERLOG"
echo '{"type":"result","subtype":"success","result":"stub death (always dies)"}'
exit 0
EOF
chmod +x "$SBOX_B/bin/claude"

_AUTOPILOT_DIED_RETRIES_MAX=1 _AUTOPILOT_PARK_BACKOFF=0 _AUTOPILOT_SESSION_MAX=999999 \
  run_with_timeout "$SBOX_B" 20
rc_b=$RUN_RC
[ -f "$SBOX_B/.timeout-fired" ] && FAIL "scenario b: safety timeout" "loop did not converge within 20s"
[ "$rc_b" -eq 1 ] || FAIL "scenario b: exhausted guard halts loud" "rc=$rc_b"

MARKER_B="$SBOX_B/dev/local/autopilot/park-requested"
[ -f "$MARKER_B" ] || FAIL "scenario b: park-requested marker created on retry exhaustion" "no marker file"
marker_lines_b=$(grep -c . "$MARKER_B")
[ "$marker_lines_b" -eq 1 ] || FAIL "scenario b: marker is exactly one line" "got $marker_lines_b lines"
jq -e . "$MARKER_B" >/dev/null 2>&1 || FAIL "scenario b: marker is valid JSON" "$(cat "$MARKER_B")"
jq -e '.prd == "00002-y.md"' "$MARKER_B" >/dev/null \
  || FAIL "scenario b: marker names state.prd" "$(cat "$MARKER_B")"
jq -e '(.reason // "") | length > 0' "$MARKER_B" >/dev/null \
  || FAIL "scenario b: marker reason is non-empty" "$(cat "$MARKER_B")"

seen_b=$(grep -c . "$SBOX_B/marker-seen.log" 2>/dev/null || echo 0)
[ "$seen_b" -ge 1 ] \
  || FAIL "scenario b: loop relaunched after writing the marker" \
          "no later claude call observed the marker file — wrote it but never relaunched"

calls_b=$(cat "$SBOX_B/claude-calls.count")
[ "$calls_b" -ge 3 ] \
  || FAIL "scenario b: call count consistent with retry+park+guard bounds" \
          "only $calls_b calls — too few for a retry, the park write, and a guarded relaunch"
[ "$calls_b" -le 10 ] \
  || FAIL "scenario b: call count bounded (no runaway relaunching)" "got $calls_b calls"

grep -qi "unconsumed" "$SBOX_B/stderr.log" \
  || FAIL "scenario b: halts with an unconsumed-marker message" "$(cat "$SBOX_B/stderr.log")"

PASS "retry exhaustion writes a valid one-line park-requested marker naming state.prd, relaunches, then halts loud on the unconsumed guard (calls=$calls_b)"

# =============================================================================
# Coverage 5 — scenario (c): bootstrap death (no state.json, no PRD) still
# halts loud, writes no marker
# =============================================================================

SBOX_C=$(mktemp -d); _DIRS+=("$SBOX_C")
mkdir -p "$SBOX_C/dev/local/autopilot" "$SBOX_C/bin"   # dir exists; NO state.json ever

cat >"$SBOX_C/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
COUNTER="$DIR/claude-calls.count"
N=$(( $(cat "$COUNTER" 2>/dev/null || echo 0) + 1 ))
printf '%s\n' "$N" >"$COUNTER"
echo '{"type":"result","subtype":"success","result":"stub death (bootstrap, no state ever)"}'
exit 0
EOF
chmod +x "$SBOX_C/bin/claude"

run_with_timeout "$SBOX_C" 15
rc_c=$RUN_RC
[ -f "$SBOX_C/.timeout-fired" ] && FAIL "scenario c: safety timeout" "loop did not converge within 15s"
[ "$rc_c" -eq 1 ] || FAIL "scenario c: bootstrap death halts loud" "rc=$rc_c"
calls_c=$(cat "$SBOX_C/claude-calls.count")
[ "$calls_c" -eq 1 ] \
  || FAIL "scenario c: no relaunch beyond the classification (empty prd -> die)" "got $calls_c calls"
[ ! -f "$SBOX_C/dev/local/autopilot/park-requested" ] \
  || FAIL "scenario c: no park marker written on bootstrap death" "marker was written"
PASS "bootstrap death (no state.json, no PRD) halts loud immediately, no marker, no retry"

# =============================================================================
# Coverage 6 — guard age bound: a stale unconsumed marker halts loud on the
# FIRST guarded encounter via age, before any guarded relaunch, and the
# marker is never overwritten
# =============================================================================

SBOX_D=$(mktemp -d); _DIRS+=("$SBOX_D")
mkdir -p "$SBOX_D/dev/local/autopilot" "$SBOX_D/bin"
printf '%s\n' '{"prd":"00003-z.md","next_phase":"build","batch":{"id":"d1"}}' \
  >"$SBOX_D/dev/local/autopilot/state.json"
touch -t 202601010000 "$SBOX_D/dev/local/autopilot/state.json"

MARKER_CONTENT='{"prd":"00099-old.md","reason":"pre-existing unconsumed marker"}'
printf '%s\n' "$MARKER_CONTENT" >"$SBOX_D/dev/local/autopilot/park-requested"
touch -t 202601010000 "$SBOX_D/dev/local/autopilot/park-requested"   # ancient -> age >> _AUTOPILOT_SESSION_MAX

cat >"$SBOX_D/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
COUNTER="$DIR/claude-calls.count"
N=$(( $(cat "$COUNTER" 2>/dev/null || echo 0) + 1 ))
printf '%s\n' "$N" >"$COUNTER"
echo '{"type":"result","subtype":"success","result":"stub death (always dies)"}'
exit 0
EOF
chmod +x "$SBOX_D/bin/claude"

# MAX=1 lets the first death retry once (RETRIES(0) < MAX(1) is true); the
# second death then reaches the park path with the marker already present —
# the FIRST guarded encounter. There, the count bound cannot fire
# (RETRIES(1) > MAX(1) is false), so only the age bound (stale >=
# _AUTOPILOT_SESSION_MAX) can halt loud, isolating it from the count bound.
# A missing age check would instead relaunch (backoff 0), die a third time,
# and halt via the count bound at calls == 3 — calls == 2 is what proves the
# age check fired.
_AUTOPILOT_DIED_RETRIES_MAX=1 _AUTOPILOT_SESSION_MAX=1 _AUTOPILOT_PARK_BACKOFF=0 \
  run_with_timeout "$SBOX_D" 15
rc_d=$RUN_RC
[ -f "$SBOX_D/.timeout-fired" ] && FAIL "scenario age-guard: safety timeout" "loop did not converge within 15s"
[ "$rc_d" -eq 1 ] || FAIL "scenario age-guard: stale marker halts loud" "rc=$rc_d"

calls_d=$(cat "$SBOX_D/claude-calls.count")
[ "$calls_d" -eq 2 ] \
  || FAIL "scenario age-guard: halts on the FIRST guarded encounter via age, before any guarded relaunch" "got $calls_d calls"

after_content=$(cat "$SBOX_D/dev/local/autopilot/park-requested")
[ "$after_content" = "$MARKER_CONTENT" ] \
  || FAIL "scenario age-guard: marker content never overwritten" \
          "before: $MARKER_CONTENT / after: $after_content"

PASS "stale unconsumed marker (age >= _AUTOPILOT_SESSION_MAX) halts on the FIRST guarded encounter via age, content byte-identical"

# =============================================================================
echo ""
echo "All checks passed."
exit 0
