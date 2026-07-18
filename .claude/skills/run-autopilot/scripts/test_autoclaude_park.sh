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
# Coverage 7 — synthetic two-PRD batch: happy park (wrapper_died stall,
# PRD moved to hold/, batch continues and drains the second PRD)
# =============================================================================

SBOX_E=$(mktemp -d); _DIRS+=("$SBOX_E")
mkdir -p "$SBOX_E/dev/local/autopilot" "$SBOX_E/dev/local/prds/wip" "$SBOX_E/bin"
printf '# PRD 00001-a\n' >"$SBOX_E/dev/local/prds/wip/00001-a.md"
printf '# PRD 00002-b\n' >"$SBOX_E/dev/local/prds/wip/00002-b.md"
printf '%s\n' '{"prd":"00001-a.md","next_phase":"build","batch":{"id":"e1"}}' \
  >"$SBOX_E/dev/local/autopilot/state.json"
touch -t 202601010000 "$SBOX_E/dev/local/autopilot/state.json"

# Stub simulates the skill's Phase 0 park handler in-process: when it sees
# park-requested at session start it moves the named wip PRD to hold/, records
# a wrapper_died stall, bumps batch.parks_consecutive, then selects the next
# wip PRD and continues. Absent a marker, PRD 00001-a.md always dies (state
# untouched); PRD 00002-b.md is healthy and drains on its first session.
cat >"$SBOX_E/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$DIR/dev/local/autopilot/state.json"
MARKER="$DIR/dev/local/autopilot/park-requested"
DEFERRED="$DIR/dev/local/autopilot/deferred/e1-deferred.json"

if [ -f "$MARKER" ]; then
  prd=$(jq -r '.prd' "$MARKER")
  reason=$(jq -r '.reason' "$MARKER")
  if [ -f "$DIR/dev/local/prds/wip/$prd" ]; then
    mkdir -p "$DIR/dev/local/prds/hold"
    mv "$DIR/dev/local/prds/wip/$prd" "$DIR/dev/local/prds/hold/$prd"
    mkdir -p "$(dirname "$DEFERRED")"
    jq -nc --arg detail "$reason" --arg prd "$prd" \
      '{type:"stall", site:"wrapper_died", detail:$detail, prd:$prd}' >>"$DEFERRED"
    parks=$(jq -r '.batch.parks_consecutive // 0' "$STATE")
    parks=$((parks + 1))
    next=$(ls "$DIR/dev/local/prds/wip" 2>/dev/null | sort | head -n1)
    jq --argjson parks "$parks" --arg prd "$next" \
      '.prd=$prd | .next_phase="build" | .batch.parks_consecutive=$parks' \
      "$STATE" >"$STATE.tmp" && mv "$STATE.tmp" "$STATE"
  fi
  rm -f "$MARKER"
  echo '{"type":"result","subtype":"success","result":"park handled"}'
  exit 0
fi

prd=$(jq -r '.prd' "$STATE" 2>/dev/null)
case "$prd" in
00002-b.md)
  mkdir -p "$DIR/dev/local/prds/done"
  mv "$DIR/dev/local/prds/wip/00002-b.md" "$DIR/dev/local/prds/done/00002-b.md"
  jq '.next_phase=""' "$STATE" >"$STATE.tmp" && mv "$STATE.tmp" "$STATE"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.01,"usage":{"output_tokens":10}}'
  ;;
*)
  echo '{"type":"result","subtype":"success","result":"stub death (state untouched)"}'
  ;;
esac
exit 0
EOF
chmod +x "$SBOX_E/bin/claude"

_AUTOPILOT_DIED_RETRIES_MAX=1 _AUTOPILOT_PARK_BACKOFF=0 _AUTOPILOT_SESSION_MAX=999999 \
  run_with_timeout "$SBOX_E" 20
rc_e=$RUN_RC
[ -f "$SBOX_E/.timeout-fired" ] && FAIL "scenario happy-park: safety timeout" "loop did not converge within 20s"
[ "$rc_e" -eq 0 ] || FAIL "scenario happy-park: drained loop returns 0" "rc=$rc_e"
grep -q "Backlog drained" "$SBOX_E/stdout.log" \
  || FAIL "scenario happy-park: prints Backlog drained" "$(cat "$SBOX_E/stdout.log")"

[ -f "$SBOX_E/dev/local/prds/hold/00001-a.md" ] \
  || FAIL "scenario happy-park: parked PRD moved to hold/" "00001-a.md not in hold/"
[ ! -f "$SBOX_E/dev/local/prds/wip/00001-a.md" ] \
  || FAIL "scenario happy-park: parked PRD removed from wip/" "00001-a.md still in wip/"
[ ! -f "$SBOX_E/dev/local/prds/wip/00002-b.md" ] \
  || FAIL "scenario happy-park: drained PRD removed from wip/" "00002-b.md still in wip/"

DEFERRED_E="$SBOX_E/dev/local/autopilot/deferred/e1-deferred.json"
[ -f "$DEFERRED_E" ] || FAIL "scenario happy-park: deferred stall recorded" "no deferred file at $DEFERRED_E"
stall_count_e=$(jq -s '[.[] | select(.type=="stall" and .site=="wrapper_died" and .prd=="00001-a.md")] | length' "$DEFERRED_E")
[ "$stall_count_e" -eq 1 ] \
  || FAIL "scenario happy-park: exactly one wrapper_died stall for 00001-a.md" "got $stall_count_e"

[ ! -f "$SBOX_E/dev/local/autopilot/park-requested" ] \
  || FAIL "scenario happy-park: marker consumed exactly once" "marker still present at end"

PASS "synthetic two-PRD batch: died PRD parks to hold/ with a recorded wrapper_died stall, batch continues and drains the second PRD"

# =============================================================================
# Coverage 8 — all-die systemic breaker: two consecutive wrapper_died parks
# trip the systemic halt before the batch's third PRD is ever selected
# =============================================================================

SBOX_F=$(mktemp -d); _DIRS+=("$SBOX_F")
mkdir -p "$SBOX_F/dev/local/autopilot" "$SBOX_F/dev/local/prds/wip" "$SBOX_F/bin"
printf '# PRD 00001-a\n' >"$SBOX_F/dev/local/prds/wip/00001-a.md"
printf '# PRD 00002-b\n' >"$SBOX_F/dev/local/prds/wip/00002-b.md"
printf '# PRD 00003-c\n' >"$SBOX_F/dev/local/prds/wip/00003-c.md"
printf '%s\n' '{"prd":"00001-a.md","next_phase":"build","batch":{"id":"f1"}}' \
  >"$SBOX_F/dev/local/autopilot/state.json"
touch -t 202601010000 "$SBOX_F/dev/local/autopilot/state.json"

# Every PRD always dies; the marker-consuming session is the only source of
# progress. It parks the dying PRD and bumps batch.parks_consecutive; at 2 it
# halts systemically instead of selecting a next PRD.
cat >"$SBOX_F/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$DIR/dev/local/autopilot/state.json"
MARKER="$DIR/dev/local/autopilot/park-requested"
DEFERRED="$DIR/dev/local/autopilot/deferred/f1-deferred.json"

if [ -f "$MARKER" ]; then
  prd=$(jq -r '.prd' "$MARKER")
  reason=$(jq -r '.reason' "$MARKER")
  if [ -f "$DIR/dev/local/prds/wip/$prd" ]; then
    mkdir -p "$DIR/dev/local/prds/hold"
    mv "$DIR/dev/local/prds/wip/$prd" "$DIR/dev/local/prds/hold/$prd"
    mkdir -p "$(dirname "$DEFERRED")"
    jq -nc --arg detail "$reason" --arg prd "$prd" \
      '{type:"stall", site:"wrapper_died", detail:$detail, prd:$prd}' >>"$DEFERRED"
    parks=$(jq -r '.batch.parks_consecutive // 0' "$STATE")
    parks=$((parks + 1))
    if [ "$parks" -ge 2 ]; then
      jq --argjson parks "$parks" \
        '.phase="paused" | .batch.parks_consecutive=$parks
         | .pause_reason={site:"systemic_park",detail:"two consecutive parks"}
         | .next_phase="paused"' \
        "$STATE" >"$STATE.tmp" && mv "$STATE.tmp" "$STATE"
    else
      next=$(ls "$DIR/dev/local/prds/wip" 2>/dev/null | sort | head -n1)
      jq --argjson parks "$parks" --arg prd "$next" \
        '.prd=$prd | .next_phase="build" | .batch.parks_consecutive=$parks' \
        "$STATE" >"$STATE.tmp" && mv "$STATE.tmp" "$STATE"
    fi
  fi
  rm -f "$MARKER"
  echo '{"type":"result","subtype":"success","result":"park handled"}'
  exit 0
fi

echo '{"type":"result","subtype":"success","result":"stub death (always dies)"}'
exit 0
EOF
chmod +x "$SBOX_F/bin/claude"

_AUTOPILOT_DIED_RETRIES_MAX=1 _AUTOPILOT_PARK_BACKOFF=0 _AUTOPILOT_SESSION_MAX=999999 \
  run_with_timeout "$SBOX_F" 25
rc_f=$RUN_RC
[ -f "$SBOX_F/.timeout-fired" ] && FAIL "scenario systemic: safety timeout" "loop did not converge within 25s"

paused_ok=0
[ "$rc_f" -eq 1 ] && paused_ok=1
if [ "$paused_ok" -eq 0 ]; then
  phase_f=$(jq -r '.phase // ""' "$SBOX_F/dev/local/autopilot/state.json" 2>/dev/null)
  site_f=$(jq -r '.pause_reason.site // ""' "$SBOX_F/dev/local/autopilot/state.json" 2>/dev/null)
  [ "$phase_f" = "paused" ] && [ "$site_f" = "systemic_park" ] && paused_ok=1
fi
[ "$paused_ok" -eq 1 ] \
  || FAIL "scenario systemic: two consecutive wrapper_died parks halt loud (systemic_park)" "rc=$rc_f, state=$(cat "$SBOX_F/dev/local/autopilot/state.json" 2>/dev/null)"

[ -f "$SBOX_F/dev/local/prds/wip/00003-c.md" ] \
  || FAIL "scenario systemic: batch stops before the third PRD is ever selected" "00003-c.md missing from wip/"

PASS "all-die batch trips the systemic breaker at 2 consecutive wrapper_died parks; the third PRD is never selected"

# =============================================================================
# Coverage 9 — park-loop guard, COUNT bound: a fresh (non-stale) unconsumed
# marker is relaunched at most _AUTOPILOT_DIED_RETRIES_MAX times, then halts
# loud — distinct from Coverage 6's AGE bound
# =============================================================================

SBOX_G=$(mktemp -d); _DIRS+=("$SBOX_G")
mkdir -p "$SBOX_G/dev/local/autopilot" "$SBOX_G/bin"
printf '%s\n' '{"prd":"00004-w.md","next_phase":"build","batch":{"id":"g1"}}' \
  >"$SBOX_G/dev/local/autopilot/state.json"
touch -t 202601010000 "$SBOX_G/dev/local/autopilot/state.json"

MARKER_CONTENT_G='{"prd":"00099-old.md","reason":"pre-existing unconsumed marker"}'
printf '%s\n' "$MARKER_CONTENT_G" >"$SBOX_G/dev/local/autopilot/park-requested"
# Deliberately NOT backdated: mtime is "now", so the AGE bound cannot fire —
# only the relaunch COUNT bound can halt this scenario.

cat >"$SBOX_G/bin/claude" <<'EOF'
#!/usr/bin/env bash
echo '{"type":"result","subtype":"success","result":"stub death (always dies)"}'
exit 0
EOF
chmod +x "$SBOX_G/bin/claude"

_AUTOPILOT_DIED_RETRIES_MAX=1 _AUTOPILOT_PARK_BACKOFF=0 _AUTOPILOT_SESSION_MAX=999999 \
  run_with_timeout "$SBOX_G" 20
rc_g=$RUN_RC
[ -f "$SBOX_G/.timeout-fired" ] && FAIL "scenario count-guard: safety timeout" "loop did not converge within 20s"
[ "$rc_g" -eq 1 ] || FAIL "scenario count-guard: unconsumed marker halts loud on the count bound" "rc=$rc_g"

grep -qi "unconsumed" "$SBOX_G/stderr.log" \
  || FAIL "scenario count-guard: halts with an unconsumed-marker message" "$(cat "$SBOX_G/stderr.log")"

after_content_g=$(cat "$SBOX_G/dev/local/autopilot/park-requested")
[ "$after_content_g" = "$MARKER_CONTENT_G" ] \
  || FAIL "scenario count-guard: marker content never overwritten" \
          "before: $MARKER_CONTENT_G / after: $after_content_g"

PASS "fresh unconsumed park-requested marker is relaunched at most _AUTOPILOT_DIED_RETRIES_MAX times then halts loud on the count bound, marker byte-unchanged"

# =============================================================================
# Coverage 10 — stale park-requested marker (names a PRD not in wip/) is
# discarded without a hold/ move or a parks_consecutive bump; selection
# continues normally and the batch drains
# =============================================================================

SBOX_H=$(mktemp -d); _DIRS+=("$SBOX_H")
mkdir -p "$SBOX_H/dev/local/autopilot" "$SBOX_H/dev/local/prds/wip" "$SBOX_H/bin"
printf '# PRD 00005-v\n' >"$SBOX_H/dev/local/prds/wip/00005-v.md"
printf '%s\n' '{"prd":"00099-ghost.md","reason":"stale test marker"}' \
  >"$SBOX_H/dev/local/autopilot/park-requested"

cat >"$SBOX_H/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$DIR/dev/local/autopilot/state.json"
MARKER="$DIR/dev/local/autopilot/park-requested"

if [ -f "$MARKER" ]; then
  prd=$(jq -r '.prd' "$MARKER")
  if [ -f "$DIR/dev/local/prds/wip/$prd" ]; then
    mkdir -p "$DIR/dev/local/prds/hold"
    mv "$DIR/dev/local/prds/wip/$prd" "$DIR/dev/local/prds/hold/$prd"
  fi
  rm -f "$MARKER"
fi

next=$(ls "$DIR/dev/local/prds/wip" 2>/dev/null | sort | head -n1)
jq -n --arg prd "$next" '{prd:$prd, next_phase:""}' >"$STATE"
echo '{"type":"result","subtype":"success","total_cost_usd":0.01,"usage":{"output_tokens":5}}'
exit 0
EOF
chmod +x "$SBOX_H/bin/claude"

_AUTOPILOT_DIED_RETRIES_MAX=1 _AUTOPILOT_PARK_BACKOFF=0 _AUTOPILOT_SESSION_MAX=999999 \
  run_with_timeout "$SBOX_H" 15
rc_h=$RUN_RC
[ -f "$SBOX_H/.timeout-fired" ] && FAIL "scenario stale-park: safety timeout" "loop did not converge within 15s"
[ "$rc_h" -eq 0 ] || FAIL "scenario stale-park: drained loop returns 0" "rc=$rc_h"
grep -q "Backlog drained" "$SBOX_H/stdout.log" \
  || FAIL "scenario stale-park: prints Backlog drained" "$(cat "$SBOX_H/stdout.log")"

[ ! -e "$SBOX_H/dev/local/prds/hold/00099-ghost.md" ] \
  || FAIL "scenario stale-park: absent PRD named by a stale marker never appears in hold/" "00099-ghost.md was moved to hold/"
[ ! -f "$SBOX_H/dev/local/autopilot/park-requested" ] \
  || FAIL "scenario stale-park: marker consumed (deleted)" "marker still present"

PASS "stale park-requested marker (PRD absent from wip/) is discarded without a hold/ move; selection continues and the batch drains"

# =============================================================================
# Coverage 11 — breaker reset on a healthy outcome: a healthy session resets
# batch.parks_consecutive to 0, so a LATER wrapper_died park only reaches 1
# and never trips the systemic breaker
# =============================================================================

SBOX_I=$(mktemp -d); _DIRS+=("$SBOX_I")
mkdir -p "$SBOX_I/dev/local/autopilot" "$SBOX_I/dev/local/prds/wip" "$SBOX_I/bin"
printf '# PRD 00001-a\n' >"$SBOX_I/dev/local/prds/wip/00001-a.md"
printf '# PRD 00002-b\n' >"$SBOX_I/dev/local/prds/wip/00002-b.md"
printf '# PRD 00003-c\n' >"$SBOX_I/dev/local/prds/wip/00003-c.md"
printf '%s\n' '{"prd":"00001-a.md","next_phase":"build","batch":{"id":"i1"}}' \
  >"$SBOX_I/dev/local/autopilot/state.json"
touch -t 202601010000 "$SBOX_I/dev/local/autopilot/state.json"

# 00001-a.md and 00003-c.md always die and park; 00002-b.md is healthy and,
# mirroring the skill's Phase 9 reset, zeroes batch.parks_consecutive when it
# completes — so the second wrapper_died park (00003-c.md) starts from 0.
cat >"$SBOX_I/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$DIR/dev/local/autopilot/state.json"
MARKER="$DIR/dev/local/autopilot/park-requested"
DEFERRED="$DIR/dev/local/autopilot/deferred/i1-deferred.json"

if [ -f "$MARKER" ]; then
  prd=$(jq -r '.prd' "$MARKER")
  reason=$(jq -r '.reason' "$MARKER")
  if [ -f "$DIR/dev/local/prds/wip/$prd" ]; then
    mkdir -p "$DIR/dev/local/prds/hold"
    mv "$DIR/dev/local/prds/wip/$prd" "$DIR/dev/local/prds/hold/$prd"
    mkdir -p "$(dirname "$DEFERRED")"
    jq -nc --arg detail "$reason" --arg prd "$prd" \
      '{type:"stall", site:"wrapper_died", detail:$detail, prd:$prd}' >>"$DEFERRED"
    parks=$(jq -r '.batch.parks_consecutive // 0' "$STATE")
    parks=$((parks + 1))
    next=$(ls "$DIR/dev/local/prds/wip" 2>/dev/null | sort | head -n1)
    if [ -n "$next" ]; then
      jq --argjson parks "$parks" --arg prd "$next" \
        '.prd=$prd | .next_phase="build" | .batch.parks_consecutive=$parks' \
        "$STATE" >"$STATE.tmp" && mv "$STATE.tmp" "$STATE"
    else
      jq --argjson parks "$parks" \
        '.next_phase="" | .batch.parks_consecutive=$parks' \
        "$STATE" >"$STATE.tmp" && mv "$STATE.tmp" "$STATE"
    fi
  fi
  rm -f "$MARKER"
  echo '{"type":"result","subtype":"success","result":"park handled"}'
  exit 0
fi

prd=$(jq -r '.prd' "$STATE" 2>/dev/null)
case "$prd" in
00002-b.md)
  mkdir -p "$DIR/dev/local/prds/done"
  mv "$DIR/dev/local/prds/wip/00002-b.md" "$DIR/dev/local/prds/done/00002-b.md"
  next=$(ls "$DIR/dev/local/prds/wip" 2>/dev/null | sort | head -n1)
  jq --arg prd "$next" \
    '.prd=$prd | .next_phase="build" | .batch.parks_consecutive=0' \
    "$STATE" >"$STATE.tmp" && mv "$STATE.tmp" "$STATE"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.01,"usage":{"output_tokens":10}}'
  ;;
*)
  echo '{"type":"result","subtype":"success","result":"stub death (state untouched)"}'
  ;;
esac
exit 0
EOF
chmod +x "$SBOX_I/bin/claude"

_AUTOPILOT_DIED_RETRIES_MAX=1 _AUTOPILOT_PARK_BACKOFF=0 _AUTOPILOT_SESSION_MAX=999999 \
  run_with_timeout "$SBOX_I" 25
rc_i=$RUN_RC
[ -f "$SBOX_I/.timeout-fired" ] && FAIL "scenario breaker-reset: safety timeout" "loop did not converge within 25s"
[ "$rc_i" -eq 0 ] \
  || FAIL "scenario breaker-reset: drains without tripping the systemic breaker" "rc=$rc_i"
grep -q "Backlog drained" "$SBOX_I/stdout.log" \
  || FAIL "scenario breaker-reset: prints Backlog drained" "$(cat "$SBOX_I/stdout.log")"

DEFERRED_I="$SBOX_I/dev/local/autopilot/deferred/i1-deferred.json"
stall_count_i=$(jq -s '[.[] | select(.type=="stall")] | length' "$DEFERRED_I" 2>/dev/null)
[ "$stall_count_i" -eq 2 ] \
  || FAIL "scenario breaker-reset: two non-consecutive wrapper_died parks recorded" "got $stall_count_i"

PASS "a healthy session between two wrapper_died parks resets batch.parks_consecutive; the systemic breaker never trips and the batch drains"

# =============================================================================
echo ""
echo "All checks passed."
exit 0
