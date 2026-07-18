#!/usr/bin/env bash
# test_loop_metrics.sh — PRD 00013 metrics + PRD 00014 decision-table check.
#
# Sources the real autoclaude wrapper, stubs the external calls (claude,
# sysctl, python3 helpers, session cap), runs loop iterations against fake
# state.json files, and asserts exactly one valid JSONL metrics line per
# session with all eight keys and the branch-derived signal
# (continue|paused|done|died|park). Hermetic: no network, no real claude, temp
# dirs only. The usage-limit branch sleeps ≥60s by design and is covered by
# test_detect_usage_limit.py instead. Scenarios 5-7 cover the network-outage
# branch (connection-level API failure -> bounded relaunch; curl stubbed).
#
# Run: bash ~/.claude/skills/run-autopilot/scripts/test_loop_metrics.sh

PLUGIN="$HOME/.config/bash/plugins/development.plugin.bash"

# cite/about-plugin run at source time (buvis plugin framework); stub them so
# sourcing works in a bare bash shell. Defined BEFORE source so the plugin's
# top-level calls resolve.
cite() { :; }
about-plugin() { :; }

# shellcheck source=/dev/null
source "$PLUGIN"

# AP_DIR is reassigned per scenario; the stubs below read it at call time.
AP_DIR=""

# Stubs defined AFTER source so they win over the plugin's own definitions.
sysctl() { echo 1; }                                   # no memory pressure
python3() {
  case "$*" in
    *_walk_up.py*)           printf '%s\n' "$AP_DIR" ;; # resolve ap dir -> temp
    *detect_usage_limit.py*) return 1 ;;                # not usage-limited
    *notify.py*)             : ;;                        # swallow notifications
    *)                       command python3 "$@" ;;
  esac
}
_autopilot_session_cap() { :; }                        # no background sidecar
# Scenario-specific `claude` stubs are defined inline below.

fail() { echo "FAIL: $1" >&2; exit 1; }

run_loop() {  # $1 = temp autopilot dir
  AP_DIR="$1"
  autoclaude >/dev/null 2>&1
}

TMP1="$(mktemp -d)"
TMP2="$(mktemp -d)"
TMP3="$(mktemp -d)"
TMP4="$(mktemp -d)"
TMP5="$(mktemp -d)"
TMP6="$(mktemp -d)"
TMP7="$(mktemp -d)"
TMP8="$(mktemp -d)"
trap 'rm -rf "$TMP1" "$TMP2" "$TMP3" "$TMP4" "$TMP5" "$TMP6" "$TMP7" "$TMP8"' EXIT

# ── Scenario 1: build -> review -> done -> drained (happy path) ──────
# Three sessions advance the phases (branch 4 twice, branch 3 last); the
# per-phase model routing (PRD 00018) must pick opus for build/review and
# sonnet for the done/finalize launch, and the fake result event's cost
# fields must land on every line.
AP1="$TMP1/dev/local/autopilot"
mkdir -p "$AP1"
printf '%s\n' '{"prd":"00013-test.md","next_phase":"build","batch":{"id":"209901010000"}}' > "$AP1/state.json"

claude() {
  local next
  next=$(jq -r '.next_phase // ""' "$AP_DIR/state.json" 2>/dev/null)
  case "$next" in
    build)  printf '%s\n' '{"prd":"00013-test.md","next_phase":"review","batch":{"id":"209901010000"}}' > "$AP_DIR/state.json" ;;
    review) printf '%s\n' '{"prd":"00013-test.md","next_phase":"done","batch":{"id":"209901010000"}}' > "$AP_DIR/state.json" ;;
    done)   printf '%s\n' '{"prd":"00013-test.md","next_phase":"","batch":{"id":"209901010000"}}' > "$AP_DIR/state.json" ;;
  esac
  echo '{"type":"result","subtype":"success","total_cost_usd":1.23,"usage":{"output_tokens":456}}'
}

run_loop "$AP1"
rc1=$?
[ "$rc1" -eq 0 ] || fail "scenario 1: drained loop did not return 0 (rc=$rc1)"

M1="$AP1/loop-metrics.jsonl"
[ -f "$M1" ] || fail "scenario 1: no loop-metrics.jsonl written"
n1=$(grep -c . "$M1")
[ "$n1" -eq 3 ] || fail "scenario 1: expected 3 lines (continue, continue, done), got $n1"
line1=$(sed -n 1p "$M1")
line3=$(sed -n 3p "$M1")
echo "scenario 1 line 1: $line1"
echo "scenario 1 line 3: $line3"
echo "$line1" | jq -e . >/dev/null || fail "scenario 1: line 1 not valid JSON"
for key in ts_start ts_end wall_secs prd batch phase_launched phase_end signal model; do
  echo "$line1" | jq -e "has(\"$key\")" >/dev/null || fail "scenario 1: missing key $key"
done
echo "$line1" | jq -e '.wall_secs | type == "number"' >/dev/null \
  || fail "scenario 1: wall_secs not a number"
echo "$line1" | jq -e '.prd == "00013-test.md" and .batch == "209901010000" and .phase_launched == "build" and .phase_end == "review" and .signal == "continue"' >/dev/null \
  || fail "scenario 1: line 1 field values wrong"
echo "$line1" | jq -e '.model == "claude-opus-4-8" and .cost_usd == 1.23 and .tokens_out == 456' >/dev/null \
  || fail "scenario 1: line 1 model/cost fields wrong (PRD 00018)"
echo "$line3" | jq -e '.phase_launched == "done" and .phase_end == "" and .signal == "done"' >/dev/null \
  || fail "scenario 1: line 3 field values wrong"
echo "$line3" | jq -e '.model == "claude-sonnet-5"' >/dev/null \
  || fail "scenario 1: done/finalize session did not route to sonnet (PRD 00018)"
[ -f "$AP1/reports/209901010000-state-final.json" ] \
  || fail "scenario 1: drained state.json not archived to reports/"
[ ! -f "$AP1/state.json" ] || fail "scenario 1: state.json still present after archive"

# ── Scenario 2: no state.json ever written (died path) ───────────────
AP2="$TMP2/dev/local/autopilot"
mkdir -p "$AP2"   # dir exists, but no state.json

claude() { echo "stub session output"; }

run_loop "$AP2"
rc2=$?
[ "$rc2" -eq 1 ] || fail "scenario 2: died loop did not return 1 (rc=$rc2)"

M2="$AP2/loop-metrics.jsonl"
[ -f "$M2" ] || fail "scenario 2: line not written when state.json absent"
n2=$(grep -c . "$M2")
[ "$n2" -eq 1 ] || fail "scenario 2: expected 1 line, got $n2"
line2=$(cat "$M2")
echo "scenario 2 line: $line2"
echo "$line2" | jq -e '.prd == "" and .batch == "" and .phase_launched == "" and .phase_end == "" and .signal == "died"' >/dev/null \
  || fail "scenario 2: died-path fields wrong"
echo "$line2" | jq -e '.model == "claude-opus-4-8" and (has("cost_usd") | not) and (has("tokens_out") | not)' >/dev/null \
  || fail "scenario 2: absent-phase default model or spurious cost keys (PRD 00018: no result event -> omit keys, never fake zeros)"

# ── Scenario 3: append target unwritable — silent by design ──────────
# `2>/dev/null` must precede `>>` so a failed append-target open is
# suppressed; the loop itself must survive and still drain.
AP3="$TMP3/dev/local/autopilot"
mkdir -p "$AP3"
printf '%s\n' '{"prd":"00013-test.md","next_phase":"","batch":{"id":"209901010000"}}' > "$AP3/state.json"
mkdir "$AP3/loop-metrics.jsonl"   # append target is a directory → `>>` open fails

claude() { echo "stub session output"; }

AP_DIR="$AP3"
err3="$TMP3/stderr.txt"
autoclaude >/dev/null 2>"$err3"
rc3=$?
[ "$rc3" -eq 0 ] || fail "scenario 3: autoclaude did not return 0 — the append failure broke the loop"
if grep -q 'loop-metrics' "$err3"; then
  echo "scenario 3 leaked stderr:"; cat "$err3"
  fail "scenario 3: metrics append leaked a diagnostic to stderr (not silent by design)"
fi
echo "scenario 3: append on unwritable target was silent; loop survived (rc=$rc3)"

# ── Scenario 4: paused state (branch 1) ──────────────────────────────
AP4="$TMP4/dev/local/autopilot"
mkdir -p "$AP4"
printf '%s\n' '{"prd":"00013-test.md","next_phase":"review","phase":"paused","pause_reason":{"site":"phase5","detail":"cap reached"},"batch":{"id":"209901010000"}}' > "$AP4/state.json"

claude() { echo "stub session output"; }

run_loop "$AP4"
rc4=$?
[ "$rc4" -eq 1 ] || fail "scenario 4: paused loop did not return 1 (rc=$rc4)"

M4="$AP4/loop-metrics.jsonl"
[ -f "$M4" ] || fail "scenario 4: line not written on the paused path"
n4=$(grep -c . "$M4")
[ "$n4" -eq 1 ] || fail "scenario 4: expected 1 line, got $n4"
line4=$(cat "$M4")
echo "scenario 4 line: $line4"
echo "$line4" | jq -e '.signal == "paused"' >/dev/null \
  || fail "scenario 4: signal not \"paused\""
[ -f "$AP4/state.json" ] || fail "scenario 4: paused state.json was not left intact"

# ── Scenario 5: connect-error session, network back — retry then drain ──
# Regression (2026-07-12): a relaunch that got ConnectionRefused for its
# whole 3-minute life was classified as a no-progress death and killed the
# batch. Session 1 emits a connection-failure result and leaves state
# untouched; the wrapper must poll connectivity (curl stub: up) and
# relaunch. Session 2 drains.
AP5="$TMP5/dev/local/autopilot"
mkdir -p "$AP5"
printf '%s\n' '{"prd":"00054-test.md","next_phase":"build","batch":{"id":"209901010000"}}' > "$AP5/state.json"
# Backdate: a fixture written in the launch second reads as "touched by the
# session" (branch 4) and the died branch is never reached.
touch -t 202601010000 "$AP5/state.json"

curl() { return 0; }                                   # network reachable
claude() {
  if [ ! -f "$AP_DIR/first-done" ]; then
    : > "$AP_DIR/first-done"
    echo '{"type":"result","subtype":"success","is_error":true,"result":"API Error: Unable to connect to API (ConnectionRefused)","total_cost_usd":0,"usage":{"output_tokens":0}}'
    return 0
  fi
  printf '%s\n' '{"prd":"00054-test.md","next_phase":"","batch":{"id":"209901010000"}}' > "$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":1.23,"usage":{"output_tokens":456}}'
}

run_loop "$AP5"
rc5=$?
[ "$rc5" -eq 0 ] || fail "scenario 5: loop did not survive a transient connect-error (rc=$rc5)"
M5="$AP5/loop-metrics.jsonl"
[ -f "$M5" ] || fail "scenario 5: no loop-metrics.jsonl written"
n5=$(grep -c . "$M5")
[ "$n5" -eq 2 ] || fail "scenario 5: expected 2 lines (net-retry continue, done), got $n5"
sed -n 1p "$M5" | jq -e '.signal == "continue"' >/dev/null \
  || fail "scenario 5: connect-error session did not signal continue"
sed -n 2p "$M5" | jq -e '.signal == "done"' >/dev/null \
  || fail "scenario 5: recovery session did not drain"

# ── Scenario 6: persistent connect-error — retry cap, then died ──────
# TCP reachable (curl up) but every session's API calls fail: the
# consecutive-retry cap must stop the relaunch loop.
AP6="$TMP6/dev/local/autopilot"
mkdir -p "$AP6"
printf '%s\n' '{"prd":"00054-test.md","next_phase":"build","batch":{"id":"209901010000"}}' > "$AP6/state.json"
touch -t 202601010000 "$AP6/state.json"

curl() { return 0; }
claude() {
  echo '{"type":"result","subtype":"success","is_error":true,"result":"API Error: Unable to connect to API (ConnectionRefused)","total_cost_usd":0,"usage":{"output_tokens":0}}'
}

_AUTOPILOT_NET_RETRIES_MAX=2
run_loop "$AP6"
rc6=$?
unset _AUTOPILOT_NET_RETRIES_MAX
[ "$rc6" -eq 1 ] || fail "scenario 6: capped connect-error loop did not return 1 (rc=$rc6)"
M6="$AP6/loop-metrics.jsonl"
n6=$(grep -c . "$M6")
[ "$n6" -eq 3 ] || fail "scenario 6: expected 3 lines (2 retries + died), got $n6"
sed -n 1p "$M6" | jq -e '.signal == "continue"' >/dev/null \
  || fail "scenario 6: retry 1 did not signal continue"
sed -n 2p "$M6" | jq -e '.signal == "continue"' >/dev/null \
  || fail "scenario 6: retry 2 did not signal continue"
sed -n 3p "$M6" | jq -e '.signal == "died"' >/dev/null \
  || fail "scenario 6: exhausted retries did not signal died"
[ -f "$AP6/state.json" ] || fail "scenario 6: state.json not left intact for inspection"

# ── Scenario 7: connect-error and network stays down — bounded, died ──
# curl never succeeds; with a zero wait budget the poll must give up
# immediately (no relaunch) and halt loud.
AP7="$TMP7/dev/local/autopilot"
mkdir -p "$AP7"
printf '%s\n' '{"prd":"00054-test.md","next_phase":"build","batch":{"id":"209901010000"}}' > "$AP7/state.json"
touch -t 202601010000 "$AP7/state.json"

curl() { return 1; }
claude() {
  echo '{"type":"result","subtype":"success","is_error":true,"result":"API Error: Unable to connect to API (ConnectionRefused)","total_cost_usd":0,"usage":{"output_tokens":0}}'
}

_AUTOPILOT_NET_WAIT_MAX=0
run_loop "$AP7"
rc7=$?
unset _AUTOPILOT_NET_WAIT_MAX
[ "$rc7" -eq 1 ] || fail "scenario 7: dead-network loop did not return 1 (rc=$rc7)"
M7="$AP7/loop-metrics.jsonl"
n7=$(grep -c . "$M7")
[ "$n7" -eq 1 ] || fail "scenario 7: expected 1 line (died without relaunch), got $n7"
jq -e '.signal == "died"' "$M7" >/dev/null \
  || fail "scenario 7: unreachable-network session did not signal died"

# ── Scenario 8: multiple result events — cost comes from the LAST ────
# Background-task re-invokes make a headless session emit one result
# event per re-invoke, each carrying the CUMULATIVE conversation cost
# (observed on 00054 review sessions, 2026-07-13). The metrics parse
# must take the last event, not choke on a multi-line jq match and
# silently drop cost_usd/tokens_out.
AP8="$TMP8/dev/local/autopilot"
mkdir -p "$AP8"
printf '%s\n' '{"prd":"00054-test.md","next_phase":"done","batch":{"id":"209901010000"}}' > "$AP8/state.json"
touch -t 202601010000 "$AP8/state.json"

claude() {
  printf '%s\n' '{"prd":"00054-test.md","next_phase":"","batch":{"id":"209901010000"}}' > "$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":1.11,"usage":{"output_tokens":100}}'
  echo '{"type":"result","subtype":"success","total_cost_usd":8.02,"usage":{"output_tokens":1072}}'
}

run_loop "$AP8"
rc8=$?
[ "$rc8" -eq 0 ] || fail "scenario 8: loop did not drain (rc=$rc8)"
M8="$AP8/loop-metrics.jsonl"
n8=$(grep -c . "$M8")
[ "$n8" -eq 1 ] || fail "scenario 8: expected 1 line, got $n8"
line8=$(cat "$M8")
echo "scenario 8 line: $line8"
echo "$line8" | jq -e '.cost_usd == 8.02 and .tokens_out == 1072' >/dev/null \
  || fail "scenario 8: cost/tokens not taken from the LAST result event"

echo "PASS: metrics + decision table across all paths (continue/done, died, silent-append, paused, net-retry recover/cap/down, multi-result cost)"
