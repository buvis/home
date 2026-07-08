#!/usr/bin/env bash
# test_loop_metrics.sh — PRD 00013 metrics + PRD 00014 decision-table check.
#
# Sources the real autoclaude wrapper, stubs the external calls (claude,
# sysctl, python3 helpers, session cap), runs loop iterations against fake
# state.json files, and asserts exactly one valid JSONL metrics line per
# session with all eight keys and the branch-derived signal
# (continue|paused|done|died). Hermetic: no network, no real claude, temp
# dirs only. The usage-limit branch sleeps ≥60s by design and is covered by
# test_detect_usage_limit.py instead.
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
trap 'rm -rf "$TMP1" "$TMP2" "$TMP3" "$TMP4"' EXIT

# ── Scenario 1: continue then done (happy path across two sessions) ──
# Session 1 advances next_phase build->review (branch 4, signal=continue);
# session 2 writes next_phase "" (branch 3, signal=done, state archived).
AP1="$TMP1/dev/local/autopilot"
mkdir -p "$AP1"
printf '%s\n' '{"prd":"00013-test.md","next_phase":"build","batch":{"id":"209901010000"}}' > "$AP1/state.json"

claude() {
  if [ "$(jq -r '.next_phase // ""' "$AP_DIR/state.json" 2>/dev/null)" = "review" ]; then
    printf '%s\n' '{"prd":"00013-test.md","next_phase":"","batch":{"id":"209901010000"}}' > "$AP_DIR/state.json"
  else
    printf '%s\n' '{"prd":"00013-test.md","next_phase":"review","batch":{"id":"209901010000"}}' > "$AP_DIR/state.json"
  fi
  echo "stub session output"
}

run_loop "$AP1"
rc1=$?
[ "$rc1" -eq 0 ] || fail "scenario 1: drained loop did not return 0 (rc=$rc1)"

M1="$AP1/loop-metrics.jsonl"
[ -f "$M1" ] || fail "scenario 1: no loop-metrics.jsonl written"
n1=$(grep -c . "$M1")
[ "$n1" -eq 2 ] || fail "scenario 1: expected 2 lines (continue, done), got $n1"
line1=$(sed -n 1p "$M1")
line2=$(sed -n 2p "$M1")
echo "scenario 1 line 1: $line1"
echo "scenario 1 line 2: $line2"
echo "$line1" | jq -e . >/dev/null || fail "scenario 1: line 1 not valid JSON"
for key in ts_start ts_end wall_secs prd batch phase_launched phase_end signal; do
  echo "$line1" | jq -e "has(\"$key\")" >/dev/null || fail "scenario 1: missing key $key"
done
echo "$line1" | jq -e '.wall_secs | type == "number"' >/dev/null \
  || fail "scenario 1: wall_secs not a number"
echo "$line1" | jq -e '.prd == "00013-test.md" and .batch == "209901010000" and .phase_launched == "build" and .phase_end == "review" and .signal == "continue"' >/dev/null \
  || fail "scenario 1: line 1 field values wrong"
echo "$line2" | jq -e '.phase_launched == "review" and .phase_end == "" and .signal == "done"' >/dev/null \
  || fail "scenario 1: line 2 field values wrong"
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

echo "PASS: metrics + decision table across all four paths (continue/done, died, silent-append, paused)"
