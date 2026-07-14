#!/usr/bin/env bash
# test_autoclaude_tracon_launch.sh — wrapper loop-registry lifecycle +
# return-based trap teardown check (feature: "Add wrapper loop-registry
# lifecycle and return-based trap teardown to autoclaude"; no PRD number was
# given to this test-writing task, so none is cited here).
#
# Sources the real autoclaude wrapper, stubs the external calls (claude,
# sysctl, python3 helpers, session cap), and asserts the wrapper's per-run
# loop-registry file:
#
#   ${_AUTOPILOT_LOOPS_DIR:-$HOME/.claude/autopilot-loops}/<pid>.json
#   { "pid": <int>, "root": <abs path>, "ap_dir": <abs path>,
#     "started_at": <ISO-8601 UTC> }   (root = ap_dir minus trailing
#     "/dev/local/autopilot")
#
# is created (dir mkdir -p'd if absent) before the first session runs, and
# removed on every exit path: drained (rc 0), paused (rc 1), died (rc 1),
# INT (rc 130), TERM (rc 143). Also asserts INT/TERM trap teardown is
# return-based: no leaked `trap -p INT` in the invoking shell after a normal
# run, and that shell survives to keep running assertions.
#
# EXPECTED TO FAIL TODAY: the loop registry does not exist yet in the
# plugin. This file is red-first.
#
# Hermetic: no network, no real claude, bounded wall-clock (short polls only,
# the two child-process scenarios sleep ~1.5s each inside their own stub).
# Per-scenario temp dirs for both the autopilot state dir (AP_DIR) and the
# registry dir (_AUTOPILOT_LOOPS_DIR) — always export _AUTOPILOT_LOOPS_DIR so
# the wrapper never touches the real $HOME/.claude/autopilot-loops.
#
# Later tasks may append further scenarios below PASS; keep shared
# helpers/stubs above the "── Scenario 1" banner.
#
# Run: bash ~/.claude/skills/run-autopilot/scripts/test_autoclaude_tracon_launch.sh

PLUGIN="$HOME/.config/bash/plugins/development.plugin.bash"
export PLUGIN   # inherited by the child-process scenarios (4, 5) below

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

# assert_registry_shape <captured-json-file> <label> <expected-pid> <expected-ap_dir>
#
# Validates the full pinned registry contract on a snapshot file captured
# mid-session (the live registry file is removed by the time the wrapper
# returns, so callers must cp it out from inside a claude stub while the
# session is still running). Checks: all four keys present, correct JSON
# types (pid integer, others strings), both path fields absolute, pid
# matches the actual loop pid, ap_dir matches the actual autopilot dir, root
# equals ap_dir with the trailing "/dev/local/autopilot" stripped, and
# started_at looks like an ISO-8601 UTC timestamp.
assert_registry_shape() {
  local f="$1" label="$2" want_pid="$3" want_ap_dir="$4" want_root

  [ -s "$f" ] || fail "$label: registry file was not present (or was empty) mid-session at $f"

  jq -e 'has("pid")'        "$f" >/dev/null || fail "$label: registry JSON missing key 'pid'"
  jq -e 'has("root")'       "$f" >/dev/null || fail "$label: registry JSON missing key 'root'"
  jq -e 'has("ap_dir")'     "$f" >/dev/null || fail "$label: registry JSON missing key 'ap_dir'"
  jq -e 'has("started_at")' "$f" >/dev/null || fail "$label: registry JSON missing key 'started_at'"

  jq -e '.pid | type == "number"'        "$f" >/dev/null || fail "$label: 'pid' is not a JSON number"
  jq -e '(.pid | floor) == .pid'         "$f" >/dev/null || fail "$label: 'pid' is not an integer"
  jq -e '.root | type == "string"'       "$f" >/dev/null || fail "$label: 'root' is not a JSON string"
  jq -e '.ap_dir | type == "string"'     "$f" >/dev/null || fail "$label: 'ap_dir' is not a JSON string"
  jq -e '.started_at | type == "string"' "$f" >/dev/null || fail "$label: 'started_at' is not a JSON string"
  jq -e '.root | startswith("/")'        "$f" >/dev/null || fail "$label: 'root' is not an absolute path"
  jq -e '.ap_dir | startswith("/")'      "$f" >/dev/null || fail "$label: 'ap_dir' is not an absolute path"

  jq -e --argjson want "$want_pid" '.pid == $want' "$f" >/dev/null \
    || fail "$label: registry 'pid' != expected loop pid $want_pid (got $(jq -r '.pid' "$f"))"

  jq -e --arg want "$want_ap_dir" '.ap_dir == $want' "$f" >/dev/null \
    || fail "$label: registry 'ap_dir' != expected $want_ap_dir (got $(jq -r '.ap_dir' "$f"))"

  want_root="${want_ap_dir%/dev/local/autopilot}"
  jq -e --arg want "$want_root" '.root == $want' "$f" >/dev/null \
    || fail "$label: registry 'root' != ap_dir with trailing /dev/local/autopilot stripped ($want_root) (got $(jq -r '.root' "$f"))"

  jq -e '.started_at | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?(Z|[+-][0-9]{2}:?[0-9]{2})$")' "$f" >/dev/null \
    || fail "$label: 'started_at' does not look like an ISO-8601 UTC timestamp (got $(jq -r '.started_at' "$f"))"
}

TMP1="$(mktemp -d)"
trap 'rm -rf "$TMP1"' EXIT

# Child-process script shared by scenarios 4 (INT) and 5 (TERM): a standalone
# bash process that sources the real plugin the same way this script does,
# with a SLOW claude stub so the signal lands while a "session" is in
# flight. AP_DIR / _AUTOPILOT_LOOPS_DIR are supplied via the environment at
# invocation time (see scenarios 4/5), not hardcoded here, so this one file
# is reused for both. The heredoc is quoted so nothing expands at write
# time; $PLUGIN, $AP_DIR, $* etc. are resolved when the child actually runs.
CHILD_SCRIPT="$TMP1/child.sh"
cat > "$CHILD_SCRIPT" <<'EOF'
#!/usr/bin/env bash
cite() { :; }
about-plugin() { :; }
# shellcheck source=/dev/null
source "$PLUGIN"
sysctl() { echo 1; }
python3() {
  case "$*" in
    *_walk_up.py*)           printf '%s\n' "$AP_DIR" ;;
    *detect_usage_limit.py*) return 1 ;;
    *notify.py*)             : ;;
    *)                       command python3 "$@" ;;
  esac
}
_autopilot_session_cap() { :; }
claude() { sleep 1.5; echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'; }
autoclaude
exit $?
EOF

# ── Scenario 1: registry dir absent at start; file created before the first
#    session runs with a valid pid/root/ap_dir/started_at shape; removed
#    after a drained exit (rc 0) ────────────────────────────────────────────
AP1="$TMP1/s1/dev/local/autopilot"
mkdir -p "$AP1"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010001"}}' > "$AP1/state.json"

LOOPS1="$TMP1/s1-registry"   # deliberately NOT pre-created
CAP1="$TMP1/s1-capture.json"
export _AUTOPILOT_LOOPS_DIR="$LOOPS1"

[ ! -e "$LOOPS1" ] || fail "scenario 1 setup: registry dir must not pre-exist"

claude() {
  local src="$LOOPS1/$$.json"
  [ -e "$src" ] && cp "$src" "$CAP1" 2>/dev/null
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010001"}}' > "$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":1.0,"usage":{"output_tokens":10}}'
}

run_loop "$AP1"
rc1=$?
[ "$rc1" -eq 0 ] || fail "scenario 1: drained loop did not return 0 (rc=$rc1)"

[ -d "$LOOPS1" ] || fail "scenario 1: registry dir $LOOPS1 was not created (contract: mkdir -p before first write)"

assert_registry_shape "$CAP1" "scenario 1" "$$" "$AP1"

[ ! -e "$LOOPS1/$$.json" ] || fail "scenario 1: registry file still present after drained exit"

# ── Scenario 2: registry file present mid-session and removed after a
#    paused exit (rc 1; state.json carries phase=paused + pause_reason) ────
AP2="$TMP1/s2/dev/local/autopilot"
mkdir -p "$AP2"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010002"}}' > "$AP2/state.json"

LOOPS2="$TMP1/s2-registry"
CAP2="$TMP1/s2-capture.json"
export _AUTOPILOT_LOOPS_DIR="$LOOPS2"

claude() {
  local src="$LOOPS2/$$.json"
  [ -e "$src" ] && cp "$src" "$CAP2" 2>/dev/null
  printf '%s\n' '{"prd":"tracon-test.md","phase":"paused","pause_reason":{"summary":"needs human input"},"batch":{"id":"209901010002"}}' > "$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.4,"usage":{"output_tokens":4}}'
}

run_loop "$AP2"
rc2=$?
[ "$rc2" -eq 1 ] || fail "scenario 2: paused loop did not return 1 (rc=$rc2)"

assert_registry_shape "$CAP2" "scenario 2" "$$" "$AP2"

[ ! -e "$LOOPS2/$$.json" ] || fail "scenario 2: registry file still present after paused exit"

# ── Scenario 3: registry file present mid-session and removed after a died
#    exit (rc 1; state.json backdated and never rewritten by the session) ──
AP3="$TMP1/s3/dev/local/autopilot"
mkdir -p "$AP3"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010003"}}' > "$AP3/state.json"
touch -t 202001010000 "$AP3/state.json"   # backdate: a stub that never rewrites it must count as "untouched"

LOOPS3="$TMP1/s3-registry"
CAP3="$TMP1/s3-capture.json"
export _AUTOPILOT_LOOPS_DIR="$LOOPS3"

claude() {
  local src="$LOOPS3/$$.json"
  [ -e "$src" ] && cp "$src" "$CAP3" 2>/dev/null
  echo '{"type":"result","subtype":"success","total_cost_usd":0.3,"usage":{"output_tokens":3}}'
  # deliberately does NOT touch state.json -> simulates a died/no-progress session
}

run_loop "$AP3"
rc3=$?
[ "$rc3" -eq 1 ] || fail "scenario 3: died loop did not return 1 (rc=$rc3)"

assert_registry_shape "$CAP3" "scenario 3" "$$" "$AP3"

[ ! -e "$LOOPS3/$$.json" ] || fail "scenario 3: registry file still present after died exit"

# ── Scenario 4: registry file present before the signal and removed after
#    an INT-terminated run (separate child process; rc 130) ────────────────
AP4="$TMP1/s4/dev/local/autopilot"
mkdir -p "$AP4"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010004"}}' > "$AP4/state.json"
LOOPS4="$TMP1/s4-registry"

# Spawn under monitor mode so the child is a process-group LEADER, and signal
# the GROUP — that is what a tty Ctrl-C does. A pid-only INT to a bash whose
# foreground pipeline survives the signal is DISCARDED by bash (measured
# 2026-07-14: trap never fires, loop keeps iterating), so it cannot test the
# teardown contract.
set -m
AP_DIR="$AP4" _AUTOPILOT_LOOPS_DIR="$LOOPS4" bash "$CHILD_SCRIPT" >/dev/null 2>&1 &
CHILD4=$!
set +m

i=0
while [ ! -e "$LOOPS4/$CHILD4.json" ] && [ "$i" -lt 20 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -e "$LOOPS4/$CHILD4.json" ] || fail "scenario 4: registry file for child pid $CHILD4 never appeared before INT"

kill -INT -"$CHILD4"
wait "$CHILD4"
rc4=$?

[ "$rc4" -eq 130 ] || fail "scenario 4: INT-terminated autoclaude did not return 130 (rc=$rc4)"
[ ! -e "$LOOPS4/$CHILD4.json" ] || fail "scenario 4: registry file for child pid $CHILD4 still present after INT"

# ── Scenario 5: registry file present before the signal and removed after
#    a TERM-terminated run (separate child process; rc 143) ────────────────
AP5="$TMP1/s5/dev/local/autopilot"
mkdir -p "$AP5"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010005"}}' > "$AP5/state.json"
LOOPS5="$TMP1/s5-registry"

AP_DIR="$AP5" _AUTOPILOT_LOOPS_DIR="$LOOPS5" bash "$CHILD_SCRIPT" >/dev/null 2>&1 &
CHILD5=$!

i=0
while [ ! -e "$LOOPS5/$CHILD5.json" ] && [ "$i" -lt 20 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -e "$LOOPS5/$CHILD5.json" ] || fail "scenario 5: registry file for child pid $CHILD5 never appeared before TERM"

kill -TERM "$CHILD5"
wait "$CHILD5"
rc5=$?

[ "$rc5" -eq 143 ] || fail "scenario 5: TERM-terminated autoclaude did not return 143 (rc=$rc5)"
[ ! -e "$LOOPS5/$CHILD5.json" ] || fail "scenario 5: registry file for child pid $CHILD5 still present after TERM"

# ── Scenario 6: INT/TERM trap teardown is return-based — no leaked
#    `trap -p INT` in the invoking shell after a normal drained run, and
#    that shell survives to keep running assertions (proven by reaching the
#    PASS line below in this same, still-alive shell) ──────────────────────
AP6="$TMP1/s6/dev/local/autopilot"
mkdir -p "$AP6"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010006"}}' > "$AP6/state.json"
LOOPS6="$TMP1/s6-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS6"

claude() {
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010006"}}' > "$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.2,"usage":{"output_tokens":2}}'
}

run_loop "$AP6"
rc6=$?
[ "$rc6" -eq 0 ] || fail "scenario 6: drained loop did not return 0 (rc=$rc6) before trap-hygiene check"

leaked_int_trap="$(trap -p INT)"
[ -z "$leaked_int_trap" ] || fail "scenario 6: INT trap leaked in the invoking shell after a drained run: $leaked_int_trap"

echo "PASS: registry create-at-start + shape (scenario 1), removal on drain/pause/died/INT/TERM (scenarios 1-5), INT trap not leaked + invoking shell survives (scenario 6)"
