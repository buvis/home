#!/usr/bin/env bash
# test_loop_metrics.sh — PRD 00013 runnable check.
#
# Sources the real autoclaude wrapper, stubs the external calls (claude,
# sysctl, python3 helpers, watchdog) and a fake state.json, runs ONE loop
# iteration, and asserts exactly one valid JSONL metrics line with all eight
# keys. Hermetic: no network, no real claude, temp dirs only.
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
claude() { printf 'done' > "$AP_DIR/signal"; }         # terminate after 1 iter
_autopilot_loop_watchdog() { :; }                      # no background poller

fail() { echo "FAIL: $1" >&2; exit 1; }

run_iteration() {  # $1 = temp autopilot dir
  AP_DIR="$1"
  autoclaude >/dev/null 2>&1
}

TMP1="$(mktemp -d)"
TMP2="$(mktemp -d)"
trap 'rm -rf "$TMP1" "$TMP2"' EXIT

# ── Scenario 1: state.json present (happy path) ──────────────────────
AP1="$TMP1/dev/local/autopilot"
mkdir -p "$AP1"
printf '%s\n' '{"prd":"00013-test.md","next_phase":"build","batch":{"id":"209901010000"}}' > "$AP1/state.json"

run_iteration "$AP1"

M1="$AP1/loop-metrics.jsonl"
[ -f "$M1" ] || fail "scenario 1: no loop-metrics.jsonl written"
n1=$(grep -c . "$M1")
[ "$n1" -eq 1 ] || fail "scenario 1: expected 1 line, got $n1"
line1=$(cat "$M1")
echo "scenario 1 line: $line1"
echo "$line1" | jq -e . >/dev/null || fail "scenario 1: not valid JSON"
for key in ts_start ts_end wall_secs prd batch phase_launched phase_end signal; do
  echo "$line1" | jq -e "has(\"$key\")" >/dev/null || fail "scenario 1: missing key $key"
done
echo "$line1" | jq -e '.wall_secs | type == "number"' >/dev/null \
  || fail "scenario 1: wall_secs not a number"
echo "$line1" | jq -e '.prd == "00013-test.md" and .batch == "209901010000" and .phase_launched == "build" and .signal == "done"' >/dev/null \
  || fail "scenario 1: field values wrong"

# ── Scenario 2: state.json absent (first-ever run) ───────────────────
AP2="$TMP2/dev/local/autopilot"
mkdir -p "$AP2"   # dir exists, but no state.json

run_iteration "$AP2"

M2="$AP2/loop-metrics.jsonl"
[ -f "$M2" ] || fail "scenario 2: line not written when state.json absent"
n2=$(grep -c . "$M2")
[ "$n2" -eq 1 ] || fail "scenario 2: expected 1 line, got $n2"
line2=$(cat "$M2")
echo "scenario 2 line: $line2"
echo "$line2" | jq -e . >/dev/null || fail "scenario 2: not valid JSON"
echo "$line2" | jq -e '.prd == "" and .batch == "" and .phase_launched == "" and .phase_end == ""' >/dev/null \
  || fail "scenario 2: state fields not empty strings"

echo "PASS: one valid metrics line with all eight keys (state present and absent)"
