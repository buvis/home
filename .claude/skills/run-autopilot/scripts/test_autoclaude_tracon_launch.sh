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
