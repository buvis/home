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

# ---------------------------------------------------------------------------
# Shared stubs/helpers for section A (tracon launch matrix, scenarios 7+).
# uv is stubbed the same way as python3/claude above: a shell function
# defined after source, so it wins over the real `uv` that IS on this box's
# PATH (mise-managed). A shell function launched via `&` in THIS shell is a
# fork of the same process (not a new bash binary, unlike the CHILD_SCRIPT
# scenarios below), so it — and every other stub here — is inherited
# automatically by the backgrounded loop the tracon path forks; no
# `export -f` needed. UV_CALLS_FILE is "" by default (record nothing); a
# scenario that must prove uv was NEVER called leaves it that way and
# asserts the (still-existing, empty) capture file stays empty.
# UV_PREFLIGHT_RC/UV_TUI_RC script the exit code for the two distinct calls
# the design makes (`--preflight` vs the `--root/--wrapper-pid` TUI launch).
UV_CALLS_FILE=""
UV_PREFLIGHT_RC=0
UV_TUI_RC=0
uv() {
  local rec="$*"
  [ -n "$UV_CALLS_FILE" ] && printf '%s\n' "$rec" >>"$UV_CALLS_FILE"
  case "$rec" in
  *--preflight*) return "$UV_PREFLIGHT_RC" ;;
  *) return "$UV_TUI_RC" ;;
  esac
}

# _argv_value <captured-argv-line> <flag> — echoes the token right after
# <flag> in a space-split argv line (e.g. "run --quiet --root /x --wrapper-pid
# 123"). Written by hand instead of `grep -oP` because this box's default
# grep is BSD grep (no -P/lookahead support).
_argv_value() {
  local line="$1" flag="$2" parts=() i
  read -ra parts <<<"$line"
  for i in "${!parts[@]}"; do
    if [ "${parts[$i]}" = "$flag" ]; then
      printf '%s\n' "${parts[$((i + 1))]}"
      return 0
    fi
  done
  return 1
}
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Shared stubs/helpers for section B (Ctrl-C stop semantics, scenarios 15+).

# _wait_bounded <pid> <ceiling_secs> — like `wait`, but SIGKILLs the pid's
# own process GROUP if it hasn't returned within <ceiling_secs>, so a real
# stop regression (a hung teardown) fails this scenario loudly instead of
# hanging the whole suite. Sets $? to the waited process's own exit status
# on the happy path (watchdog loses the race and is reaped silently).
_wait_bounded() {
  local pid="$1" ceiling="$2" watchdog
  (sleep "$ceiling"; kill -KILL -"$pid" 2>/dev/null) &
  watchdog=$!
  wait "$pid"
  local rc=$?
  kill "$watchdog" 2>/dev/null
  wait "$watchdog" 2>/dev/null
  return "$rc"
}

# Child-process script for scenario 20: forces the FULL tracon launch path
# (_AUTOPILOT_TRACON=1) inside its own standalone bash process, spawned
# under `set -m` so it is a process-group LEADER — reproducing the real
# terminal arrangement where a tty Ctrl-C during the pre-raw-mode window
# (before Textual has grabbed the tty) delivers an actual SIGINT to the
# foreground process group. That group contains this child bash process
# and its OWN foreground `uv` call (job control is back OFF by the time
# `uv run` executes — _autoclaude_tracon only holds `set -m` across the
# fork so the LOOP lands in its own, separate group) — never the
# backgrounded loop, which is a distinct process group by design. So this
# signal lands on _autoclaude_tracon's own `trap ... INT` (the
# async-interrupt path), not the exit-code-130 case branch scenarios
# 15/21 exercise via a stubbed uv return; the trap then issues its OWN,
# separate `kill -INT` at the loop's group. AP_DIR / _AUTOPILOT_LOOPS_DIR /
# CLAUDE_PID_FILE are supplied via the environment at invocation time.
CHILD_SCRIPT_TRACON="$TMP1/child_tracon.sh"
cat > "$CHILD_SCRIPT_TRACON" <<'EOF'
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
claude() {
  printf '%s\n' "$BASHPID" >"$CLAUDE_PID_FILE"
  sleep 30
  echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
}
uv() {
  case "$*" in
  *--preflight*) return 0 ;;
  *) sleep 30 ;;   # still "starting up" when the real SIGINT below arrives
  esac
}
export _AUTOPILOT_TRACON=1
autoclaude
exit $?
EOF
# ---------------------------------------------------------------------------

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

# ═══════════════════════════════════════════════════════════════════════════
# Section A: tracon launch matrix (scenarios 7-14). Pins the approved design
# for autoclaude conditionally launching the tracon TUI in the foreground
# while the loop runs backgrounded as a process-group leader:
#   - _AUTOPILOT_TRACON=0 / unset+no-tty -> plain render path, uv never called
#   - _AUTOPILOT_TRACON=1 -> _autoclaude_tracon: duplicate-loop guard first,
#     then a uv --preflight check, then fork the loop (_AUTOPILOT_TRACON_CHILD=1)
#     and foreground `uv run tracon.py --root <root> --wrapper-pid <loop pid>`
#   - the session-cap sidecar must see the CHILD's own BASHPID, not the
#     parent tracon process's
#   - last-session.log must stay byte-identical between the two presentations
#     (the tee sits at the same pipeline position in both)
#
# NOT implemented yet (development.plugin.bash has no _AUTOPILOT_TRACON
# check, no _autoclaude_tracon, no uv call anywhere) — these scenarios are
# red-first for the tracon feature specifically. Scenarios 7/8/12 pin
# behavior that already holds today (there is no branch yet to break the
# escape hatch/auto-detect/render-path contract), which is expected: they
# are regression pins against a FUTURE conditional, not proof a mechanism
# exists yet. Scenarios 9/10/11/13/14 assert the NEW mechanism directly
# (uv gets invoked with specific argv, the duplicate guard blocks a launch,
# the child's own pid propagates) and fail today for that reason.
#
# The tracon fork this design describes is a `&` job of THIS bash process
# (not a new bash binary, unlike CHILD_SCRIPT above), so every stub in this
# file — python3, claude, uv, _autopilot_session_cap — is inherited by it
# automatically; no separate child script or export -f is needed here.
# ═══════════════════════════════════════════════════════════════════════════

# ── Scenario 7: escape hatch (_AUTOPILOT_TRACON=0) — uv is NEVER invoked,
#    the loop takes the render path, and drains normally (rc 0) ────────────
AP7="$TMP1/s7/dev/local/autopilot"
mkdir -p "$AP7"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010007"}}' >"$AP7/state.json"
LOOPS7="$TMP1/s7-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS7"

UV_CALLS7="$TMP1/s7-uv-calls"
: >"$UV_CALLS7"
UV_CALLS_FILE="$UV_CALLS7"

claude() {
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010007"}}' >"$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
}

export _AUTOPILOT_TRACON=0
run_loop "$AP7"
rc7=$?
unset _AUTOPILOT_TRACON
UV_CALLS_FILE=""

[ "$rc7" -eq 0 ] || fail "scenario 7: escape-hatch loop did not return 0 (rc=$rc7)"
[ ! -s "$UV_CALLS7" ] || fail "scenario 7: uv was invoked with _AUTOPILOT_TRACON=0 set (escape hatch must never call uv): $(cat "$UV_CALLS7")"

# ── Scenario 8: auto-detect with no tty (_AUTOPILOT_TRACON unset) — the
#    same outcome as scenario 7 via the OTHER route to the render path.
#    run_loop redirects autoclaude's own stdout to /dev/null, so fd 1 is
#    never a tty here regardless of how this test script itself is
#    invoked; auto-detect must fall through to the render path ───────────
AP8="$TMP1/s8/dev/local/autopilot"
mkdir -p "$AP8"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010008"}}' >"$AP8/state.json"
LOOPS8="$TMP1/s8-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS8"

UV_CALLS8="$TMP1/s8-uv-calls"
: >"$UV_CALLS8"
UV_CALLS_FILE="$UV_CALLS8"

claude() {
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010008"}}' >"$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
}

unset _AUTOPILOT_TRACON
run_loop "$AP8"
rc8=$?
UV_CALLS_FILE=""

[ "$rc8" -eq 0 ] || fail "scenario 8: auto-detect (no tty) loop did not return 0 (rc=$rc8)"
[ ! -s "$UV_CALLS8" ] || fail "scenario 8: uv was invoked with _AUTOPILOT_TRACON unset and no tty (auto-detect must resolve to the render path): $(cat "$UV_CALLS8")"

# ── Scenario 9: _AUTOPILOT_TRACON=1, uv exits 0 for --preflight and 0 for
#    the TUI run (simulating a `q` quit) — tracon is invoked exactly ONCE
#    for the TUI, with BOTH --root and --wrapper-pid in its argv; the loop
#    (a genuinely backgrounded child) drains and autoclaude returns 0 ─────
AP9="$TMP1/s9/dev/local/autopilot"
mkdir -p "$AP9"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010009"}}' >"$AP9/state.json"
LOOPS9="$TMP1/s9-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS9"

UV_CALLS9="$TMP1/s9-uv-calls"
: >"$UV_CALLS9"
UV_CALLS_FILE="$UV_CALLS9"
UV_PREFLIGHT_RC=0
UV_TUI_RC=0

LOOP_PID9="$TMP1/s9-loop-pid"
claude() {
  # $BASHPID here is the PIPELINE fork's own pid (claude is stage 1 of
  # `claude | tee | ...`), NOT the loop's own pid — read the loop's real
  # identity back off the registry entry it wrote before the pipeline
  # started (same file scenarios 1-3 read from, just by content, not by
  # assumed filename, since we don't know the loop's pid in advance here).
  local reg
  reg=$(command ls "$LOOPS9"/*.json 2>/dev/null | head -n 1)
  [ -n "$reg" ] && jq -r '.pid' "$reg" >"$LOOP_PID9" 2>/dev/null
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010009"}}' >"$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
}

export _AUTOPILOT_TRACON=1
run_loop "$AP9"
rc9=$?
unset _AUTOPILOT_TRACON
UV_CALLS_FILE=""

i=0
while [ ! -s "$LOOP_PID9" ] && [ "$i" -lt 20 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -s "$LOOP_PID9" ] || fail "scenario 9: claude stub never ran; the loop never launched at all"

tui_calls=$(grep -c -- '--wrapper-pid' "$UV_CALLS9" 2>/dev/null)
tui_calls=${tui_calls:-0}
[ "$tui_calls" -eq 1 ] || fail "scenario 9: expected exactly one uv TUI invocation (--wrapper-pid), got $tui_calls (uv calls: $(cat "$UV_CALLS9" 2>/dev/null))"

tui_line=$(grep -- '--wrapper-pid' "$UV_CALLS9")
want_root="${AP9%/dev/local/autopilot}"
got_root=$(_argv_value "$tui_line" --root)
[ "$got_root" = "$want_root" ] || fail "scenario 9: uv TUI call --root=$got_root, expected $want_root"

want_wpid=$(cat "$LOOP_PID9")
got_wpid=$(_argv_value "$tui_line" --wrapper-pid)
[ "$got_wpid" = "$want_wpid" ] || fail "scenario 9: uv TUI call --wrapper-pid=$got_wpid, expected the backgrounded loop's own pid $want_wpid"

[ "$rc9" -eq 0 ] || fail "scenario 9: autoclaude did not return 0 after a q-quit TUI (rc=$rc9)"

i=0
while [ -e "$LOOPS9/$want_wpid.json" ] && [ "$i" -lt 20 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ ! -e "$LOOPS9/$want_wpid.json" ] || fail "scenario 9: registry entry for the backgrounded loop pid $want_wpid still present — the loop never drained"

# ── Scenario 10: preflight FAILS — falls back to the plain render path,
#    which actually runs; uv is called once for --preflight and NEVER
#    again to launch a TUI it just told us is missing its deps ──────────
AP10="$TMP1/s10/dev/local/autopilot"
mkdir -p "$AP10"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010010"}}' >"$AP10/state.json"
LOOPS10="$TMP1/s10-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS10"

UV_CALLS10="$TMP1/s10-uv-calls"
: >"$UV_CALLS10"
UV_CALLS_FILE="$UV_CALLS10"
UV_PREFLIGHT_RC=1 # simulate: rich/textual not importable
UV_TUI_RC=0

CLAUDE_CALLS10="$TMP1/s10-claude-calls"
: >"$CLAUDE_CALLS10"
claude() {
  printf 'x\n' >>"$CLAUDE_CALLS10"
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010010"}}' >"$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
}

export _AUTOPILOT_TRACON=1
run_loop "$AP10"
rc10=$?
unset _AUTOPILOT_TRACON
UV_PREFLIGHT_RC=0
UV_CALLS_FILE=""

[ "$rc10" -eq 0 ] || fail "scenario 10: preflight-fallback loop did not return 0 (rc=$rc10)"
[ -s "$CLAUDE_CALLS10" ] || fail "scenario 10: claude was never invoked after the preflight fallback (render path did not run)"

preflight_calls=$(grep -c -- '--preflight' "$UV_CALLS10" 2>/dev/null)
preflight_calls=${preflight_calls:-0}
[ "$preflight_calls" -eq 1 ] || fail "scenario 10: expected exactly one uv --preflight call, got $preflight_calls (uv calls: $(cat "$UV_CALLS10" 2>/dev/null))"

wpid_calls10=$(grep -c -- '--wrapper-pid' "$UV_CALLS10" 2>/dev/null)
wpid_calls10=${wpid_calls10:-0}
[ "$wpid_calls10" -eq 0 ] || fail "scenario 10: uv was invoked to launch the TUI ($wpid_calls10 times) despite a failed preflight"

# ── Scenario 11: duplicate-loop guard — a registry entry already exists for
#    this root with a LIVE pid; autoclaude must refuse before spending any
#    uv cost and before ever launching claude ───────────────────────────
AP11="$TMP1/s11/dev/local/autopilot"
mkdir -p "$AP11"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010011"}}' >"$AP11/state.json"
LOOPS11="$TMP1/s11-registry"
mkdir -p "$LOOPS11"
ROOT11="$TMP1/s11"
jq -n --argjson pid "$$" --arg root "$ROOT11" --arg ap_dir "$AP11" \
  --arg started_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{pid:$pid, root:$root, ap_dir:$ap_dir, started_at:$started_at}' \
  >"$LOOPS11/other-loop.json" # a DIFFERENT, already-registered loop for the same root; pid=$$ is genuinely alive for this whole test run
export _AUTOPILOT_LOOPS_DIR="$LOOPS11"

UV_CALLS11="$TMP1/s11-uv-calls"
: >"$UV_CALLS11"
UV_CALLS_FILE="$UV_CALLS11"

CLAUDE_CALLS11="$TMP1/s11-claude-calls"
: >"$CLAUDE_CALLS11"
claude() {
  printf 'x\n' >>"$CLAUDE_CALLS11"
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010011"}}' >"$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
}

export _AUTOPILOT_TRACON=1
run_loop "$AP11"
rc11=$?
unset _AUTOPILOT_TRACON
UV_CALLS_FILE=""

[ "$rc11" -eq 1 ] || fail "scenario 11: duplicate-loop guard did not return 1 (rc=$rc11)"
[ ! -s "$CLAUDE_CALLS11" ] || fail "scenario 11: claude was invoked despite a live duplicate loop registered for this root (calls: $(wc -l <"$CLAUDE_CALLS11" 2>/dev/null))"
[ ! -s "$UV_CALLS11" ] || fail "scenario 11: uv was invoked despite the duplicate-loop guard (the guard must run before any uv cost): $(cat "$UV_CALLS11")"

# ── Scenario 12: registry lifecycle on the RENDER path is unchanged by the
#    new presentation branch — the same create-before-first-session shape
#    and the same removal-on-drain contract scenarios 1-3 already prove for
#    the pre-tracon wrapper, re-checked here through auto-detect (unset
#    _AUTOPILOT_TRACON, no tty) so a broken conditional can't silently skip
#    the registry write ──────────────────────────────────────────────────
AP12="$TMP1/s12/dev/local/autopilot"
mkdir -p "$AP12"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010012"}}' >"$AP12/state.json"
LOOPS12="$TMP1/s12-registry"
CAP12="$TMP1/s12-capture.json"
export _AUTOPILOT_LOOPS_DIR="$LOOPS12"

claude() {
  local src="$LOOPS12/$$.json"
  [ -e "$src" ] && cp "$src" "$CAP12" 2>/dev/null
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010012"}}' >"$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
}

unset _AUTOPILOT_TRACON
run_loop "$AP12"
rc12=$?

[ "$rc12" -eq 0 ] || fail "scenario 12: drained loop (render path via auto-detect) did not return 0 (rc=$rc12)"
assert_registry_shape "$CAP12" "scenario 12" "$$" "$AP12"
[ ! -e "$LOOPS12/$$.json" ] || fail "scenario 12: registry file still present after drained exit (render path via auto-detect)"

# ── Scenario 13: the session-cap sidecar must be spawned as a child of the
#    backgrounded LOOP, never of the parent tracon process. Measured (probe,
#    bash 5.3.9): `_autopilot_session_cap "$BASHPID" ... &` expands
#    "$BASHPID" INSIDE the newly-forked async subshell — bash forks THEN
#    expands words for a backgrounded simple command — so the sidecar's own
#    $1 is always self-referential (equal to its own pid), never usable as
#    "the loop's pid". The only externally-observable, achievable pin is
#    process ANCESTRY: read the sidecar's own PPID via `ps`, captured with
#    a plain statement first (exactly how the real function's own `_self`
#    capture avoids the "$BASHPID inside $(...) is the substitution's own
#    subshell" trap its comment warns about), and assert that PPID equals
#    the backgrounded loop's own pid (from the registry) — not the parent
#    test-script's pid ────────────────────────────────────────────────────
AP13="$TMP1/s13/dev/local/autopilot"
mkdir -p "$AP13"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010013"}}' >"$AP13/state.json"
LOOPS13="$TMP1/s13-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS13"
UV_CALLS_FILE=""
UV_PREFLIGHT_RC=0
UV_TUI_RC=0

SESSIONCAP13="$TMP1/s13-sessioncap-ppid"
SESSIONCAP13_ARG="$TMP1/s13-sessioncap-arg"
: >"$SESSIONCAP13"
: >"$SESSIONCAP13_ARG"
_autopilot_session_cap() {
  local _self="$BASHPID" _parent # same "plain statement, not $()" capture the real function uses
  _parent=$(ps -o ppid= -p "$_self" 2>/dev/null | tr -d ' ')
  printf '%s\n' "$_parent" >>"$SESSIONCAP13"
  printf '%s\n' "$1" >>"$SESSIONCAP13_ARG"
}

LOOP_PID13="$TMP1/s13-loop-pid"
claude() {
  local reg
  reg=$(command ls "$LOOPS13"/*.json 2>/dev/null | head -n 1)
  [ -n "$reg" ] && jq -r '.pid' "$reg" >"$LOOP_PID13" 2>/dev/null
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010013"}}' >"$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
}

export _AUTOPILOT_TRACON=1
run_loop "$AP13"
rc13=$?
unset _AUTOPILOT_TRACON
_autopilot_session_cap() { :; } # restore the shared no-op stub for later scenarios

i=0
while [ ! -s "$LOOP_PID13" ] && [ "$i" -lt 20 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -s "$LOOP_PID13" ] || fail "scenario 13: claude stub never ran; nothing to compare the session-cap parentage against"
[ "$rc13" -eq 0 ] || fail "scenario 13: autoclaude did not return 0 (rc=$rc13)"
[ -s "$SESSIONCAP13" ] || fail "scenario 13: _autopilot_session_cap was never called"

want_pid="$(cat "$LOOP_PID13")"
got_parent="$(tail -n 1 "$SESSIONCAP13")"
[ "$got_parent" = "$want_pid" ] || fail "scenario 13: session-cap sidecar's parent pid is $got_parent, expected the backgrounded loop's own pid $want_pid"
[ "$got_parent" != "$$" ] || fail "scenario 13: session-cap sidecar's parent is the PARENT test-script's pid ($$) — the loop must be forked and must launch the sidecar from ITS OWN context, not the tracon-parent's"

# The sidecar's $1 (_wpid) must be the LOOP's pid, because the sidecar hunts
# `claude` with `pgrep -P "$_wpid"` — claude is a child of the loop, never of
# the sidecar. Passing a bare `"$BASHPID"` at a BACKGROUNDED call site cannot
# satisfy this: bash forks first and expands the word inside the new async
# subshell, so the sidecar receives its OWN pid, `pgrep -P` matches nothing,
# and the wall-clock cap breaks out of its poll loop after the first sleep --
# the "one remaining kill path" silently never fires. The loop's pid must be
# captured in the loop's own process (plain assignment) and the VARIABLE
# passed. Asserting on $1 -- not merely on ancestry -- is what pins that.
got_arg="$(tail -n 1 "$SESSIONCAP13_ARG")"
[ -n "$got_arg" ] || fail "scenario 13: session-cap sidecar received no pid argument at all"
[ "$got_arg" = "$want_pid" ] || fail "scenario 13: session-cap sidecar got _wpid=$got_arg, expected the loop's own pid $want_pid (a self-referential \$BASHPID at a backgrounded call site makes 'pgrep -P \$_wpid' find nothing, so the session cap never fires)"

# ── Scenario 14: log identity — last-session.log must be byte-identical
#    between the tracon child's presentation sink and the plain render
#    path (the tee sits at the same pipeline position in both; only what
#    happens to _autopilot_present's OWN copy of the stream may differ).
#    First confirm run (b) actually took the tracon path (uv got the
#    --wrapper-pid call) — a cmp that happens to match without the branch
#    existing at all would be a false pass, not a real pin ──────────────
CLAUDE_LOG_LINE14='{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'

# (a) render path
AP14A="$TMP1/s14a/dev/local/autopilot"
mkdir -p "$AP14A"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010014"}}' >"$AP14A/state.json"
LOOPS14A="$TMP1/s14a-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS14A"
UV_CALLS_FILE=""

claude() {
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010014"}}' >"$AP_DIR/state.json"
  printf '%s\n' "$CLAUDE_LOG_LINE14"
}

unset _AUTOPILOT_TRACON
run_loop "$AP14A"
rc14a=$?
[ "$rc14a" -eq 0 ] || fail "scenario 14: render-path (a) drain did not return 0 (rc=$rc14a)"
[ -s "$AP14A/last-session.log" ] || fail "scenario 14: render-path (a) produced no last-session.log"

# (b) tracon path (forced; no tty needed since it's forced)
AP14B="$TMP1/s14b/dev/local/autopilot"
mkdir -p "$AP14B"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010014"}}' >"$AP14B/state.json"
LOOPS14B="$TMP1/s14b-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS14B"

UV_CALLS14B="$TMP1/s14b-uv-calls"
: >"$UV_CALLS14B"
UV_CALLS_FILE="$UV_CALLS14B"
UV_PREFLIGHT_RC=0
UV_TUI_RC=0

claude() {
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010014"}}' >"$AP_DIR/state.json"
  printf '%s\n' "$CLAUDE_LOG_LINE14"
}

export _AUTOPILOT_TRACON=1
run_loop "$AP14B"
rc14b=$?
unset _AUTOPILOT_TRACON
UV_CALLS_FILE=""

[ "$rc14b" -eq 0 ] || fail "scenario 14: tracon-path (b) drain did not return 0 (rc=$rc14b)"

i=0
while [ ! -s "$AP14B/last-session.log" ] && [ "$i" -lt 20 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -s "$AP14B/last-session.log" ] || fail "scenario 14: tracon-path (b) produced no last-session.log"

wpid_calls14=$(grep -c -- '--wrapper-pid' "$UV_CALLS14B" 2>/dev/null)
wpid_calls14=${wpid_calls14:-0}
[ "$wpid_calls14" -eq 1 ] || fail "scenario 14: uv was not invoked to launch the TUI in the tracon-path run ($wpid_calls14 times) — a cmp match here would be a false pass, not a real pin, if the branch was never taken"

cmp "$AP14A/last-session.log" "$AP14B/last-session.log" ||
  fail "scenario 14: last-session.log differs between the render path and the tracon path (tee must sit in the same pipeline position in both)"

echo "PASS: escape hatch + auto-detect never call uv (scenarios 7-8), tracon TUI invoked once with --root/--wrapper-pid + loop drains (scenario 9), preflight-fail fallback never launches a TUI (scenario 10), duplicate-loop guard blocks before any uv/claude cost (scenario 11), render-path registry contract unchanged (scenario 12), session-cap sees the child's own pid not the parent's (scenario 13), last-session.log byte-identical across presentations (scenario 14)"

# ═══════════════════════════════════════════════════════════════════════════
# Section B: Ctrl-C stop semantics (scenarios 15-23). Pins the approved stop
# path:
#   - inside tracon's raw mode, Ctrl-C arrives as a KEY EVENT and tracon
#     exits rc=130 — an EXIT-CODE branch in _autoclaude_tracon's steady
#     state, driven here by stubbing `uv`'s TUI call to return 130 (no pty
#     needed: scenarios 15-19, 21, 23)
#   - _autoclaude_tracon_stop sends SIGINT to the LOOP's process GROUP
#     (`kill -INT -"$1"`), never a bare pid — a pid-directed INT is
#     DEFERRED by bash until the foreground pipeline ends (measured), which
#     is the known-bad path this suite must catch: scenario 15 pins the
#     TIMING (fast stop vs. the claude stub's slow sleep), not just the
#     exit code
#   - before tracon grabs raw mode, a real tty Ctrl-C is an actual SIGINT
#     to the foreground process group, landing on _autoclaude_tracon's own
#     `trap ... INT` (the async-interrupt path) rather than the exit-code
#     branch — scenario 20 is the one scenario that drives this with a
#     genuine signal, per the CHILD_SCRIPT_TRACON recipe above
#   - the worst regression this section must catch: after a stop, NO
#     second session starts, and no `claude`/loop process is left orphaned
#
# Scenarios 15-19 assert on a SINGLE stop run (fewer, denser scenarios);
# 20-23 are each a separate run.
# ═══════════════════════════════════════════════════════════════════════════

# ── Scenarios 15-19: steady-state Ctrl-C stop — rc 130 AND fast (15), the
#    claude stub is dead (16), exactly one session ran (17), the registry
#    is emptied (18), and the INT trap is not leaked in this shell, which
#    keeps running (19). uv's TUI call deliberately waits for the loop's
#    claude stub to actually be in flight before returning 130, so this
#    scenario tests the STEADY-STATE stop, not the fork-window race
#    (scenario 21 tests that race on purpose) ───────────────────────────
AP15="$TMP1/s15/dev/local/autopilot"
mkdir -p "$AP15"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010015"}}' >"$AP15/state.json"
LOOPS15="$TMP1/s15-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS15"

CLAUDE_PID15="$TMP1/s15-claude-pid"
CLAUDE_COUNT15="$TMP1/s15-claude-count"
: >"$CLAUDE_COUNT15"
claude() {
  printf '%s\n' "$BASHPID" >"$CLAUDE_PID15"
  printf 'x\n' >>"$CLAUDE_COUNT15"
  sleep 30
  echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
}

# Scenario-local uv override: waits (bounded) for the claude stub's pid
# file to appear before returning 130 for the TUI call, so the stop lands
# on a genuinely in-flight session. Restored to the shared section-A stub
# right after this run so scenarios 20-23 below get the normal one back.
UV_CALLS_FILE=""
uv() {
  case "$*" in
  *--preflight*) return 0 ;;
  *)
    local i=0
    while [ ! -s "$CLAUDE_PID15" ] && [ "$i" -lt 100 ]; do
      sleep 0.05
      i=$((i + 1))
    done
    return 130
    ;;
  esac
}

export _AUTOPILOT_TRACON=1
_ts15_start=$SECONDS
run_loop "$AP15"
rc15=$?
_ts15_elapsed=$((SECONDS - _ts15_start))
unset _AUTOPILOT_TRACON
uv() {   # restore the shared section-A stub for scenarios 20-23
  local rec="$*"
  [ -n "$UV_CALLS_FILE" ] && printf '%s\n' "$rec" >>"$UV_CALLS_FILE"
  case "$rec" in
  *--preflight*) return "$UV_PREFLIGHT_RC" ;;
  *) return "$UV_TUI_RC" ;;
  esac
}

# Scenario 15: rc 130, and FAST — well under the claude stub's 30s sleep.
[ "$rc15" -eq 130 ] || fail "scenario 15: Ctrl-C stop did not return 130 (rc=$rc15)"
[ "$_ts15_elapsed" -lt 10 ] || fail "scenario 15: Ctrl-C stop took ${_ts15_elapsed}s (>=10s) — deferred-trap bug: the stop did not return until near the claude stub's 30s sleep"

# Scenario 16: the claude stub process is dead after the stop.
[ -s "$CLAUDE_PID15" ] || fail "scenario 16 setup: claude stub never recorded its own pid"
claude_pid15="$(cat "$CLAUDE_PID15")"
if kill -0 "$claude_pid15" 2>/dev/null; then
  fail "scenario 16: claude stub pid $claude_pid15 still alive after the stop"
fi

# Scenario 17: exactly one session ran — no second session started.
count15=$(wc -l <"$CLAUDE_COUNT15")
[ "$count15" -eq 1 ] || fail "scenario 17: expected exactly 1 claude invocation, got $count15 (a second session started after the stop)"

# Scenario 18: the registry dir is empty after the stop.
[ -z "$(command ls -A "$LOOPS15" 2>/dev/null)" ] || fail "scenario 18: registry dir $LOOPS15 not empty after the stop: $(command ls "$LOOPS15")"

# Scenario 19: no leaked INT trap in this shell, and this shell survives to
# keep running (proven by reaching every assertion below in this same,
# still-alive shell — same technique scenario 6 already established).
leaked_int_trap15="$(trap -p INT)"
[ -z "$leaked_int_trap15" ] || fail "scenario 19: INT trap leaked in the invoking shell after a Ctrl-C stop: $leaked_int_trap15"

echo "PASS: Ctrl-C stop is rc 130 and fast, not deferred to the claude stub's slow sleep (scenario 15), claude stub reaped (scenario 16), no second session (scenario 17), registry emptied (scenario 18), INT trap not leaked + shell survives (scenario 19)"

# ── Scenario 20: a REAL SIGINT (the pre-raw-mode window) — signal the
#    CHILD bash process's own process group exactly as a tty Ctrl-C would;
#    per the CHILD_SCRIPT_TRACON comment above, this lands on
#    _autoclaude_tracon's own `trap ... INT`, not the exit-code-130 branch.
#    Converges on the same outcome: loop stopped, no orphan, rc 130 ───────
AP20="$TMP1/s20/dev/local/autopilot"
mkdir -p "$AP20"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010020"}}' >"$AP20/state.json"
LOOPS20="$TMP1/s20-registry"
CLAUDE_PID20="$TMP1/s20-claude-pid"

set -m
AP_DIR="$AP20" _AUTOPILOT_LOOPS_DIR="$LOOPS20" CLAUDE_PID_FILE="$CLAUDE_PID20" \
  bash "$CHILD_SCRIPT_TRACON" >/dev/null 2>&1 &
CHILD20=$!
set +m

i=0
while [ ! -s "$CLAUDE_PID20" ] && [ "$i" -lt 100 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -s "$CLAUDE_PID20" ] || fail "scenario 20 setup: the loop's claude stub inside the child never started"

kill -INT -"$CHILD20"
_wait_bounded "$CHILD20" 20
rc20=$?

[ "$rc20" -eq 130 ] || fail "scenario 20: a real group SIGINT (pre-raw-mode window) did not converge to rc 130 (rc=$rc20)"

claude_pid20="$(cat "$CLAUDE_PID20")"
if kill -0 "$claude_pid20" 2>/dev/null; then
  fail "scenario 20: claude stub pid $claude_pid20 (inside the child's loop) still alive after the real SIGINT stop"
fi

i=0
while [ -n "$(command ls -A "$LOOPS20" 2>/dev/null)" ] && [ "$i" -lt 40 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -z "$(command ls -A "$LOOPS20" 2>/dev/null)" ] || fail "scenario 20: registry dir $LOOPS20 not empty after the real SIGINT stop: $(command ls "$LOOPS20")"

echo "PASS: a real group SIGINT in the pre-raw-mode window converges on rc 130, loop stopped, no orphan (scenario 20)"

# ── Scenario 21: fork-window Ctrl-C — uv's stubbed TUI call returns 130
#    immediately, with no artificial wait for the loop to reach its claude
#    stub, maximizing the race between "loop just forked" and "stop
#    fires". Whichever way the race lands, no orphan may survive and the
#    registry must end up empty ──────────────────────────────────────────
AP21="$TMP1/s21/dev/local/autopilot"
mkdir -p "$AP21"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010021"}}' >"$AP21/state.json"
LOOPS21="$TMP1/s21-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS21"

CLAUDE_PID21="$TMP1/s21-claude-pid"
claude() {
  printf '%s\n' "$BASHPID" >"$CLAUDE_PID21"
  sleep 30
  echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
}

UV_CALLS_FILE=""
UV_PREFLIGHT_RC=0
UV_TUI_RC=130   # returns immediately — no wait for the claude stub to start

export _AUTOPILOT_TRACON=1
_ts21_start=$SECONDS
run_loop "$AP21"
rc21=$?
_ts21_elapsed=$((SECONDS - _ts21_start))
unset _AUTOPILOT_TRACON
UV_TUI_RC=0

[ "$rc21" -eq 130 ] || fail "scenario 21: fork-window Ctrl-C did not return 130 (rc=$rc21)"
[ "$_ts21_elapsed" -lt 10 ] || fail "scenario 21: fork-window stop took ${_ts21_elapsed}s (>=10s) — did not converge quickly"

i=0
while [ -n "$(command ls -A "$LOOPS21" 2>/dev/null)" ] && [ "$i" -lt 40 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -z "$(command ls -A "$LOOPS21" 2>/dev/null)" ] || fail "scenario 21: registry dir $LOOPS21 not empty after the fork-window stop: $(command ls "$LOOPS21")"

if [ -s "$CLAUDE_PID21" ]; then
  claude_pid21="$(cat "$CLAUDE_PID21")"
  if kill -0 "$claude_pid21" 2>/dev/null; then
    fail "scenario 21: claude stub pid $claude_pid21 still alive after the fork-window stop (the race landed with the stub running, and it was not reaped)"
  fi
fi

echo "PASS: fork-window Ctrl-C (stop arriving before the loop reaches its claude stub) still converges — no orphan, registry emptied, rc 130 (scenario 21)"

# ── Scenario 22: child pgrp self-guard — invoke autoclaude directly in
#    child mode (_AUTOPILOT_TRACON_CHILD=1) as a pipeline stage with
#    monitor mode explicitly OFF, so it inherits this shell's existing
#    process group rather than leading its own (a pipeline stage's own pid
#    can never equal a pgid that was already fixed before it was forked).
#    Must refuse: return 1, launch NO claude, write NO registry file ─────
AP22="$TMP1/s22/dev/local/autopilot"
mkdir -p "$AP22"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010022"}}' >"$AP22/state.json"
LOOPS22="$TMP1/s22-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS22"

CLAUDE_CALLS22="$TMP1/s22-claude-calls"
: >"$CLAUDE_CALLS22"
claude() {
  printf 'x\n' >>"$CLAUDE_CALLS22"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
}

AP_DIR="$AP22"
set +m
_AUTOPILOT_TRACON_CHILD=1 autoclaude 2>/dev/null | cat >/dev/null
rc22=${PIPESTATUS[0]}

[ "$rc22" -eq 1 ] || fail "scenario 22: non-pgrp-leader child self-guard did not return 1 (rc=$rc22)"
[ ! -s "$CLAUDE_CALLS22" ] || fail "scenario 22: claude was invoked despite the pgrp self-guard (calls: $(wc -l <"$CLAUDE_CALLS22"))"
[ ! -e "$LOOPS22" ] || [ -z "$(command ls -A "$LOOPS22" 2>/dev/null)" ] || fail "scenario 22: a registry file was written despite the pgrp self-guard refusing before the loop's main body: $(command ls "$LOOPS22")"

echo "PASS: child pgrp self-guard refuses a loop that cannot be stopped — rc 1, no claude, no registry file (scenario 22)"

# ── Scenario 23: presentation sink — wrapper.log holds the wrapper's own
#    banners but NO session event lines (_autopilot_present's child-mode
#    branch discards its copy of the stream); last-session.log holds every
#    session event (the tee sits upstream of that discard) ──────────────
AP23="$TMP1/s23/dev/local/autopilot"
mkdir -p "$AP23"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010023"}}' >"$AP23/state.json"
LOOPS23="$TMP1/s23-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS23"

CLAUDE_LOG_LINE23='{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
claude() {
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010023"}}' >"$AP_DIR/state.json"
  printf '%s\n' "$CLAUDE_LOG_LINE23"
}

UV_CALLS_FILE=""
UV_PREFLIGHT_RC=0
UV_TUI_RC=0

export _AUTOPILOT_TRACON=1
run_loop "$AP23"
rc23=$?
unset _AUTOPILOT_TRACON

[ "$rc23" -eq 0 ] || fail "scenario 23: tracon-path drain did not return 0 (rc=$rc23)"

i=0
while [ ! -s "$AP23/last-session.log" ] && [ "$i" -lt 40 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -s "$AP23/last-session.log" ] || fail "scenario 23: last-session.log was never created/populated"
[ -s "$AP23/wrapper.log" ] || fail "scenario 23: wrapper.log was never created/populated"

grep -qF "$CLAUDE_LOG_LINE23" "$AP23/last-session.log" ||
  fail "scenario 23: last-session.log is missing the session event line (tee did not capture it)"

if grep -qF "$CLAUDE_LOG_LINE23" "$AP23/wrapper.log"; then
  fail "scenario 23: wrapper.log leaked a session event line — _autopilot_present's child-mode branch must sink it, not the wrapper's own log"
fi

grep -q '━━' "$AP23/wrapper.log" ||
  fail "scenario 23: wrapper.log is missing the wrapper's own banner lines"

echo "PASS: presentation sink — wrapper.log carries only the wrapper's own banners, last-session.log carries every session event (scenario 23)"

# ═══════════════════════════════════════════════════════════════════════════
# Section C: two defects in _autoclaude_tracon's own INT/TERM handling that
# Section B's scenarios (15-23) do not reach, because they all drive the
# STEADY-STATE stop (loop already forked, uv's TUI call in flight) or the
# post-fork real-signal race (scenario 20/21). Both defects are UNFIXED
# today:
#
#   (A) the parent installs its INT trap BEFORE the fork
#       (`trap ... "${_loop:-$!}" ... INT`), but `_loop` is a `local` that
#       is still empty between the trap install and `_loop=$!` capturing
#       the backgrounded loop's pid. An INT landing in that PRE-fork window
#       falls back to `$!` — the CALLER's own most recent background job,
#       which may be a completely unrelated process the user backgrounded
#       earlier. `_autoclaude_tracon_stop` then signals THAT job's process
#       group instead of the (not-yet-existing) loop.
#
#   (B) `_autoclaude_tracon` installs only an INT trap, never a TERM trap.
#       A SIGTERM to the foreground wrapper takes bash's default action
#       (the parent dies outright); the backgrounded loop keeps running as
#       an orphan, and its own teardown contract
#       (`_autopilot_loop_teardown; return 143`) never runs because nothing
#       ever tells the loop to stop.
#
# Scenario 24 pins (A); scenario 25 pins (B). Both are EXPECTED TO FAIL
# today.
# ═══════════════════════════════════════════════════════════════════════════

# ── Scenario 24: Defect A — an INT delivered in the PRE-fork window (after
#    the trap install, before the backgrounded loop's pid is captured) must
#    NOT signal an unrelated background job the caller already had running,
#    and autoclaude must still converge on rc 130.
#
#    The real danger window is a single bash "simple command" wide (the
#    fork line itself) and far too small to hit with a real, externally
#    delivered `kill` in wall-clock time. Reproduced deterministically
#    instead with a `functrace` DEBUG trap (DEBUG traps are not inherited
#    into function calls without it) that recognizes the ONE fork line by
#    its literal, unique text (`_AUTOPILOT_TRACON_CHILD=1`, which appears
#    nowhere else in the function) and self-signals — via $BASHPID, not $$,
#    which stays pinned to the OUTER script's pid inside a subshell —
#    immediately before that line executes. That lands the INT exactly
#    where the trap is already installed but `_loop` is still unset, same
#    as a real pre-fork tty Ctrl-C would. Measured against this plugin
#    (2026-07-15): the harmless job dies and rc is still 130 — proving the
#    stop path is reached with the WRONG target, not that the stop path is
#    skipped ───────────────────────────────────────────────────────────────
AP24="$TMP1/s24/dev/local/autopilot"
mkdir -p "$AP24"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010024"}}' >"$AP24/state.json"
LOOPS24="$TMP1/s24-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS24"

CLAUDE_CALLS24="$TMP1/s24-claude-calls"
: >"$CLAUDE_CALLS24"
claude() {
  printf 'x\n' >>"$CLAUDE_CALLS24"
  printf '%s\n' '{"prd":"tracon-test.md","next_phase":"","batch":{"id":"209901010024"}}' >"$AP_DIR/state.json"
  echo '{"type":"result","subtype":"success","total_cost_usd":0.1,"usage":{"output_tokens":1}}'
}

UV_CALLS_FILE=""
UV_PREFLIGHT_RC=0
UV_TUI_RC=0

# The caller's own unrelated background job, in its OWN process group (set
# -m) — exactly the shape _autoclaude_tracon_stop's `kill -INT -"$1"` would
# hit if it were ever handed this job's pid instead of the loop's.
set -m
sleep 60 &
HARMLESS24=$!
set +m

AP_DIR="$AP24"
(
  set -o functrace
  trap 'case "$BASH_COMMAND" in
    *_AUTOPILOT_TRACON_CHILD=1*) kill -INT $BASHPID ;;
  esac' DEBUG
  export _AUTOPILOT_TRACON=1
  autoclaude >/dev/null 2>&1
  exit $?
)
rc24=$?

[ "$rc24" -eq 130 ] || fail "scenario 24: a pre-fork-window INT did not converge to rc 130 (rc=$rc24)"

[ ! -s "$CLAUDE_CALLS24" ] || fail "scenario 24 setup: claude was invoked — the interrupt landed AFTER the fork completed, not in the pre-fork window this scenario targets (calls: $(wc -l <"$CLAUDE_CALLS24"))"
[ ! -e "$LOOPS24" ] || [ -z "$(command ls -A "$LOOPS24" 2>/dev/null)" ] || fail "scenario 24 setup: a registry entry exists at $LOOPS24 — the loop was forked before the interrupt landed, not in the pre-fork window this scenario targets"

kill -0 "$HARMLESS24" 2>/dev/null \
  || fail "scenario 24: the pre-fork-window INT killed the CALLER's unrelated background job (pid $HARMLESS24) — \${_loop:-\$!} fell back to \$!, which pointed at this harmless job (not the not-yet-forked loop), and _autoclaude_tracon_stop signaled its process group"

kill -- -"$HARMLESS24" 2>/dev/null
wait "$HARMLESS24" 2>/dev/null

echo "PASS: a pre-fork-window INT converges on rc 130 without signaling the caller's unrelated background job (scenario 24)"

# ── Scenario 25: Defect B — no TERM trap on the tracon parent. A real
#    SIGTERM to the foreground wrapper PROCESS ONLY (never its group — a
#    real terminal signals the foreground process, not indiscriminately the
#    whole session) must converge on rc 143 with the loop's own teardown
#    contract honored: loop stopped, its registry entry removed, no
#    orphaned claude stub. Reuses CHILD_SCRIPT_TRACON verbatim — the same
#    "loop genuinely running, claude in flight" setup scenario 20 already
#    established for a real INT — only the signal and its target (pid, not
#    group) differ. Measured against this plugin (2026-07-15): rc IS 143
#    (bash's own default-signal-exit convention, not a real trap-driven
#    teardown), but the registry entry survives and the claude stub is left
#    running as an orphan — the discriminating assertions below, not the
#    rc, are what catch this defect ─────────────────────────────────────────
AP25="$TMP1/s25/dev/local/autopilot"
mkdir -p "$AP25"
printf '%s\n' '{"prd":"tracon-test.md","next_phase":"build","batch":{"id":"209901010025"}}' >"$AP25/state.json"
LOOPS25="$TMP1/s25-registry"
CLAUDE_PID25="$TMP1/s25-claude-pid"

set -m
AP_DIR="$AP25" _AUTOPILOT_LOOPS_DIR="$LOOPS25" CLAUDE_PID_FILE="$CLAUDE_PID25" \
  bash "$CHILD_SCRIPT_TRACON" >/dev/null 2>&1 &
CHILD25=$!
set +m

i=0
while [ ! -s "$CLAUDE_PID25" ] && [ "$i" -lt 100 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -s "$CLAUDE_PID25" ] || fail "scenario 25 setup: the loop's claude stub inside the child never started"

reg25=$(command ls "$LOOPS25"/*.json 2>/dev/null | head -n 1)
[ -n "$reg25" ] || fail "scenario 25 setup: no registry entry for the loop before the TERM"
loop_pid25=$(jq -r '.pid' "$reg25" 2>/dev/null)
[ -n "$loop_pid25" ] && [ "$loop_pid25" != "null" ] || fail "scenario 25 setup: could not read the loop's pid from its registry entry $reg25"

# Bounded wait WITHOUT _wait_bounded: its watchdog is a `(...) &` subshell,
# which inherits this file's own top-level `trap ... rm -rf "$TMP1" EXIT`
# (subshells inherit EXIT-trap dispositions from their parent by default,
# no functrace needed). Killing that watchdog subshell (its normal
# cleanup path) makes IT run the inherited EXIT trap too, wiping $TMP1
# out from under this still-running scenario before the assertions below
# ever read it (measured 2026-07-15: this exact interaction, isolated). A
# plain poll-then-`wait` never forks anything that could inherit the trap.
kill -TERM "$CHILD25"
i=0
while kill -0 "$CHILD25" 2>/dev/null && [ "$i" -lt 200 ]; do
  sleep 0.1
  i=$((i + 1))
done
kill -0 "$CHILD25" 2>/dev/null && kill -KILL "$CHILD25" 2>/dev/null
wait "$CHILD25" 2>/dev/null
rc25=$?

i=0
while [ -e "$LOOPS25/$loop_pid25.json" ] && [ "$i" -lt 40 ]; do
  sleep 0.05
  i=$((i + 1))
done
reg_survived25=0
[ -e "$LOOPS25/$loop_pid25.json" ] && reg_survived25=1

claude_pid25="$(cat "$CLAUDE_PID25")"
claude_alive25=0
kill -0 "$claude_pid25" 2>/dev/null && claude_alive25=1

# Clean up the orphan (if any) BEFORE asserting, so a failure here can
# never leak a live claude stub or loop process group into later scenarios.
kill -KILL "$claude_pid25" 2>/dev/null
kill -KILL -"$loop_pid25" 2>/dev/null
rm -f "$LOOPS25/$loop_pid25.json"

[ "$rc25" -eq 143 ] || fail "scenario 25: TERM to the tracon parent did not converge to rc 143 (rc=$rc25)"
[ "$reg_survived25" -eq 0 ] || fail "scenario 25: registry entry for the loop pid $loop_pid25 still present after TERM to the tracon parent — the loop's own teardown (_autopilot_loop_teardown) never ran because nothing told it to stop"
[ "$claude_alive25" -eq 0 ] || fail "scenario 25: claude stub pid $claude_pid25 (inside the orphaned loop) still alive after TERM to the tracon parent — SIGTERM took bash's default action on the parent and the backgrounded loop kept running as an orphan"

leaked_int_trap25="$(trap -p INT)"
leaked_term_trap25="$(trap -p TERM)"
[ -z "$leaked_int_trap25" ] || fail "scenario 25: INT trap leaked in the invoking shell after the TERM scenario: $leaked_int_trap25"
[ -z "$leaked_term_trap25" ] || fail "scenario 25: TERM trap leaked in the invoking shell after the TERM scenario: $leaked_term_trap25"

echo "PASS: a real SIGTERM to the tracon parent (pid, not group) converges on rc 143 with the loop stopped, its registry entry removed, and no orphaned claude stub (scenario 25)"
