#!/usr/bin/env bash
# test_autoclaude_tracon_launch.sh — the surviving BASH front-end of
# autoclaude after the PRD-00106 loop cutover: the tracon presentation
# branch (_AUTOPILOT_TRACON routing, _autoclaude_tracon and its stop /
# surface helpers), the duplicate-loop guard + registry prune the
# front-end runs BEFORE forking, the child pgrp self-guard, and trap
# hygiene in the invoking shell.
#
# The loop body itself lives in cli/loop.py since PRD 00106 and is tested
# in cli/test_loop.py; here the loop child (`autopilot loop`) is emulated
# by a per-scenario AUTOPILOT_LOOP_STUB shell function, so no scenario
# ever launches the real CLI loop, a real claude, or a real notifier.
# Scenario numbers are historical (pre-cutover); the deleted numbers
# tested loop-body behavior that moved to cli/test_loop.py.
#
# Hermetic: no network, no real claude/uv/python-loop, bounded wall-clock.
# Per-scenario temp dirs for both the autopilot state dir (AP_DIR) and the
# registry dir — always export _AUTOPILOT_LOOPS_DIR so nothing touches the
# real $HOME/.claude/autopilot-loops.
#
# Run: bash ~/.claude/skills/run-autopilot/scripts/test_autoclaude_tracon_launch.sh

PLUGIN="$HOME/.config/bash/plugins/development.plugin.bash"
export PLUGIN   # inherited by the child-process scenarios (20, 25) below

# cite/about-plugin run at source time (buvis plugin framework); stub them so
# sourcing works in a bare bash shell. Defined BEFORE source so the plugin's
# top-level calls resolve.
cite() { :; }
about-plugin() { :; }

# shellcheck source=/dev/null
source "$PLUGIN"

# This suite may itself run from inside a live autoclaude loop, which exports
# _AUTOPILOT_TRACON_CHILD=1 and _AUTOPILOT_LOOP=<pid> into every subshell
# beneath it (development.plugin.bash:119). _AUTOPILOT_TRACON_CHILD gates the
# tracon TUI branch itself (development.plugin.bash:323 —
# `[ -z "$_AUTOPILOT_TRACON_CHILD" ]`), so an inherited copy silently skips
# that branch and every scenario below that depends on it running for real
# (9, 10, 11, 15-25, 31, 34-40) would record zero uv/tracon activity and fail.
# run_loop() below calls autoclaude in THIS shell rather than a per-scenario
# subshell (unlike the sibling fable suite's run_sandboxed()), so a single
# neutralization here — after sourcing the plugin, before any scenario runs
# — is enough. Scenario 21 re-supplies _AUTOPILOT_TRACON_CHILD=1 as a
# per-command prefix assignment, and scenario 40 exports _AUTOPILOT_LOOP
# inside its own `bash -c` child — neither is affected by an unset that ran
# once, earlier, in this shell.
unset _AUTOPILOT_TRACON_CHILD _AUTOPILOT_LOOP

# AP_DIR is reassigned per scenario; the stubs below read it at call time.
AP_DIR=""

# Stubs defined AFTER source so they win over the plugin's own definitions.
python3() {
  case "$*" in
    *_walk_up.py*) printf '%s\n' "$AP_DIR" ;; # resolve ap dir -> temp
    *)             command python3 "$@" ;;    # real python3 (duplicate guard)
  esac
}

# The loop child, emulated. `autopilot loop` is what autoclaude hands off
# to post-00106; scenarios script AUTOPILOT_LOOP_STUB to shape the loop's
# lifetime and exit code without ever running the real CLI loop. Every
# non-loop verb still reaches the real CLI.
AUTOPILOT_LOOP_STUB="_loop_stub_drained"
_loop_stub_drained() { sleep 0.3; return 0; }
autopilot() {
  case "${1:-}" in
    loop) "$AUTOPILOT_LOOP_STUB" ;;
    *)    command python3 "$HOME/.claude/skills/run-autopilot/cli/__main__.py" "$@" ;;
  esac
}

# ---------------------------------------------------------------------------
# Shared stubs/helpers for the tracon launch matrix (scenarios 7+).
# uv is stubbed the same way as python3/autopilot above: a shell function
# defined after source, so it wins over the real `uv` that IS on this box's
# PATH (mise-managed). A shell function launched via `&` in THIS shell is a
# fork of the same process, so it — and every other stub here — is inherited
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

fail() { echo "FAIL: $1" >&2; rm -rf "$TMP1"; exit 1; }

run_loop() {  # $1 = temp autopilot dir
  AP_DIR="$1"
  autoclaude >/dev/null 2>&1
}

# G3: the tracon path forks the loop as a `&` job of THIS shell, and a
# `q`-detach scenario deliberately returns while that job is still alive —
# so it, and the backgrounded uv TUI job that spawns it each time
# _autoclaude_tracon runs in-process, are still running as this suite moves
# on to later scenarios. Any such job — a `(...) &` subshell — inherits a
# bare top-level `trap ... EXIT` by default, so once one of those detached
# jobs finally exits on its own, it fires the inherited trap TOO and wipes
# $TMP1 out from under this still-running suite (measured 2026-07-15).
# NOT fixed with a guarded trap (a guarded trap still fires in every
# detached subshell and that alone reproduced a separate bash job-control
# race, "wait_for: No record of process <pid>", ~50% of runs). Fixed by
# never installing a top-level EXIT trap at all: $TMP1 is removed explicitly
# on both of this suite's own exit paths — the natural end and fail().
TMP1="$(mktemp -d)"

# Child-process script shared by scenarios 20 (INT) and 25 (TERM): a
# standalone bash process that sources the real plugin the same way this
# script does and forces the FULL tracon launch path (_AUTOPILOT_TRACON=1),
# spawned under `set -m` so it is a process-group LEADER — reproducing the
# real terminal arrangement where a tty signal during the pre-raw-mode
# window (before Textual has grabbed the tty) delivers to the foreground
# process group. That group contains this child bash process and its OWN
# foreground `uv` call (job control is back OFF by the time `uv run`
# executes — _autoclaude_tracon only holds `set -m` across the fork so the
# LOOP lands in its own, separate group) — never the backgrounded loop.
# The loop stub records its own pid then execs a slow sleep (same pid), so
# "the loop process died" is assertable from outside. AP_DIR /
# _AUTOPILOT_LOOPS_DIR / STUB_PID_FILE are supplied via the environment at
# invocation time.
CHILD_SCRIPT_TRACON="$TMP1/child_tracon.sh"
cat > "$CHILD_SCRIPT_TRACON" <<'EOF'
#!/usr/bin/env bash
cite() { :; }
about-plugin() { :; }
# shellcheck source=/dev/null
source "$PLUGIN"
python3() {
  case "$*" in
    *_walk_up.py*) printf '%s\n' "$AP_DIR" ;;
    *)             command python3 "$@" ;;
  esac
}
autopilot() {
  case "${1:-}" in
    loop)
      # exec, not `sleep 30 &` + wait: an async command started without
      # job control gets SIGINT set to SIG_IGN (POSIX), so a group INT
      # could never reap it. exec keeps the loop subshell's own pid, so
      # the recorded pid IS the process the stop must kill.
      printf '%s\n' "$BASHPID" >"$STUB_PID_FILE"
      exec sleep 30
      ;;
  esac
}
uv() {
  case "$*" in
  *--preflight*) return 0 ;;
  *) sleep 30 ;;   # still "starting up" when the real signal below arrives
  esac
}
export _AUTOPILOT_TRACON=1
autoclaude
exit $?
EOF

# _wait_bounded <pid> <ceiling_secs> — like `wait`, but SIGKILLs the pid's
# own process GROUP if it hasn't returned within <ceiling_secs>, so a real
# stop regression (a hung teardown) fails this scenario loudly instead of
# hanging the whole suite. `trap - EXIT` first: defense-in-depth against a
# future top-level EXIT trap reappearing (see G3 above).
_wait_bounded() {
  local pid="$1" ceiling="$2" watchdog
  (trap - EXIT; sleep "$ceiling"; kill -KILL -"$pid" 2>/dev/null) &
  watchdog=$!
  wait "$pid"
  local rc=$?
  kill "$watchdog" 2>/dev/null
  wait "$watchdog" 2>/dev/null
  return "$rc"
}

# F23: scenarios identify pids via $BASHPID, which is unset under macOS's
# stock /bin/bash 3.2 (bash 4+ only).
if [ -z "$BASHPID" ]; then
  fail "this suite requires bash 4+ (\$BASHPID is unset — likely macOS's stock /bin/bash 3.2); re-run with a newer bash (e.g. \`brew install bash\`)"
fi

# ── Scenario 6: trap hygiene — the wrapper installs no INT trap of its own
#    anymore (teardown is the CLI loop's), so after a plain drained run the
#    invoking shell must carry no leaked `trap -p INT` and must survive to
#    keep running assertions ────────────────────────────────────────────────
AP6="$TMP1/s6/dev/local/autopilot"
mkdir -p "$AP6"
LOOPS6="$TMP1/s6-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS6"

STUB_CALLS6="$TMP1/s6-stub-calls"
: >"$STUB_CALLS6"
_loop_stub_s6() { printf 'x\n' >>"$STUB_CALLS6"; return 0; }
AUTOPILOT_LOOP_STUB="_loop_stub_s6"

export _AUTOPILOT_TRACON=0
run_loop "$AP6"
rc6=$?
unset _AUTOPILOT_TRACON
AUTOPILOT_LOOP_STUB="_loop_stub_drained"

[ "$rc6" -eq 0 ] || fail "scenario 6: drained loop did not return 0 (rc=$rc6)"
[ -s "$STUB_CALLS6" ] || fail "scenario 6: the plain path never handed off to \`autopilot loop\`"

leaked_int_trap="$(trap -p INT)"
[ -z "$leaked_int_trap" ] || fail "scenario 6: INT trap leaked in the invoking shell after a drained run: $leaked_int_trap"

echo "PASS: plain path hands off to autopilot loop, rc passthrough, no leaked INT trap + invoking shell survives (scenario 6)"

# ═══════════════════════════════════════════════════════════════════════════
# Tracon launch matrix (scenarios 7-11). Pins the approved design for
# autoclaude conditionally launching the tracon TUI in the foreground while
# the loop runs backgrounded as a process-group leader:
#   - _AUTOPILOT_TRACON=0 / unset+no-tty -> plain hand-off, uv never called
#   - _AUTOPILOT_TRACON=1 -> _autoclaude_tracon: duplicate-loop guard first,
#     then a uv --preflight check, then fork the loop
#     (_AUTOPILOT_TRACON_CHILD=1) and foreground
#     `uv run tracon.py --root <root> --wrapper-pid <loop pid>`
# ═══════════════════════════════════════════════════════════════════════════

# ── Scenario 7: escape hatch (_AUTOPILOT_TRACON=0) — uv is NEVER invoked,
#    the plain hand-off runs, rc 0 ─────────────────────────────────────────
AP7="$TMP1/s7/dev/local/autopilot"
mkdir -p "$AP7"
LOOPS7="$TMP1/s7-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS7"

UV_CALLS7="$TMP1/s7-uv-calls"
: >"$UV_CALLS7"
UV_CALLS_FILE="$UV_CALLS7"

STUB_CALLS7="$TMP1/s7-stub-calls"
: >"$STUB_CALLS7"
_loop_stub_s7() { printf 'x\n' >>"$STUB_CALLS7"; return 0; }
AUTOPILOT_LOOP_STUB="_loop_stub_s7"

export _AUTOPILOT_TRACON=0
run_loop "$AP7"
rc7=$?
unset _AUTOPILOT_TRACON
UV_CALLS_FILE=""
AUTOPILOT_LOOP_STUB="_loop_stub_drained"

[ "$rc7" -eq 0 ] || fail "scenario 7: escape-hatch run did not return 0 (rc=$rc7)"
[ -s "$STUB_CALLS7" ] || fail "scenario 7: the loop hand-off never ran under the escape hatch"
[ ! -s "$UV_CALLS7" ] || fail "scenario 7: uv was invoked with _AUTOPILOT_TRACON=0 set (escape hatch must never call uv): $(cat "$UV_CALLS7")"

# ── Scenario 8: auto-detect with no tty (_AUTOPILOT_TRACON unset) — the
#    same outcome as scenario 7 via the OTHER route to the plain hand-off.
#    run_loop redirects autoclaude's own stdout to /dev/null, so fd 1 is
#    never a tty here regardless of how this suite is invoked ─────────────
AP8="$TMP1/s8/dev/local/autopilot"
mkdir -p "$AP8"
LOOPS8="$TMP1/s8-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS8"

UV_CALLS8="$TMP1/s8-uv-calls"
: >"$UV_CALLS8"
UV_CALLS_FILE="$UV_CALLS8"

unset _AUTOPILOT_TRACON
run_loop "$AP8"
rc8=$?
UV_CALLS_FILE=""

[ "$rc8" -eq 0 ] || fail "scenario 8: auto-detect (no tty) run did not return 0 (rc=$rc8)"
[ ! -s "$UV_CALLS8" ] || fail "scenario 8: uv was invoked with _AUTOPILOT_TRACON unset and no tty (auto-detect must resolve to the plain hand-off): $(cat "$UV_CALLS8")"

# ── Scenario 9: _AUTOPILOT_TRACON=1, uv exits 0 for --preflight and 0 for
#    the TUI run (simulating a `q` quit) — tracon is invoked exactly ONCE
#    for the TUI, with BOTH --root and --wrapper-pid in its argv, and
#    --wrapper-pid is the genuinely backgrounded loop child's own pid ─────
AP9="$TMP1/s9/dev/local/autopilot"
mkdir -p "$AP9"
LOOPS9="$TMP1/s9-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS9"

UV_CALLS9="$TMP1/s9-uv-calls"
: >"$UV_CALLS9"
UV_CALLS_FILE="$UV_CALLS9"
UV_PREFLIGHT_RC=0
UV_TUI_RC=0

LOOP_PID9="$TMP1/s9-loop-pid"
: >"$LOOP_PID9"
_loop_stub_s9() {
  # $BASHPID here IS the backgrounded loop subshell's own pid — the same
  # pid _autoclaude_tracon captured as $_loop and must pass to the TUI.
  printf '%s\n' "$BASHPID" >"$LOOP_PID9"
  sleep 0.5   # outlive the belt-and-braces pgrp check and the TUI call
  return 0
}
AUTOPILOT_LOOP_STUB="_loop_stub_s9"

export _AUTOPILOT_TRACON=1
run_loop "$AP9"
rc9=$?
unset _AUTOPILOT_TRACON
UV_CALLS_FILE=""
AUTOPILOT_LOOP_STUB="_loop_stub_drained"

i=0
while [ ! -s "$LOOP_PID9" ] && [ "$i" -lt 20 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -s "$LOOP_PID9" ] || fail "scenario 9: the loop stub never ran; the loop never launched at all"

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

# ── Scenario 10: preflight FAILS — falls back to the plain hand-off, which
#    actually runs; uv is called once for --preflight and NEVER again to
#    launch a TUI it just told us is missing its deps ─────────────────────
AP10="$TMP1/s10/dev/local/autopilot"
mkdir -p "$AP10"
LOOPS10="$TMP1/s10-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS10"

UV_CALLS10="$TMP1/s10-uv-calls"
: >"$UV_CALLS10"
UV_CALLS_FILE="$UV_CALLS10"
UV_PREFLIGHT_RC=1 # simulate: rich/textual not importable
UV_TUI_RC=0

STUB_CALLS10="$TMP1/s10-stub-calls"
: >"$STUB_CALLS10"
_loop_stub_s10() { printf 'x\n' >>"$STUB_CALLS10"; return 0; }
AUTOPILOT_LOOP_STUB="_loop_stub_s10"

export _AUTOPILOT_TRACON=1
run_loop "$AP10"
rc10=$?
unset _AUTOPILOT_TRACON
UV_PREFLIGHT_RC=0
UV_CALLS_FILE=""
AUTOPILOT_LOOP_STUB="_loop_stub_drained"

[ "$rc10" -eq 0 ] || fail "scenario 10: preflight-fallback run did not return 0 (rc=$rc10)"
[ -s "$STUB_CALLS10" ] || fail "scenario 10: the loop hand-off never ran after the preflight fallback"

preflight_calls=$(grep -c -- '--preflight' "$UV_CALLS10" 2>/dev/null)
preflight_calls=${preflight_calls:-0}
[ "$preflight_calls" -eq 1 ] || fail "scenario 10: expected exactly one uv --preflight call, got $preflight_calls (uv calls: $(cat "$UV_CALLS10" 2>/dev/null))"

wpid_calls10=$(grep -c -- '--wrapper-pid' "$UV_CALLS10" 2>/dev/null)
wpid_calls10=${wpid_calls10:-0}
[ "$wpid_calls10" -eq 0 ] || fail "scenario 10: uv was invoked to launch the TUI ($wpid_calls10 times) despite a failed preflight"

# ── Scenario 11: duplicate-loop guard — a registry entry already exists for
#    this root with a LIVE, genuinely TAGGED pid (same seeding shape as
#    scenario 40 below): PRD 00127's discovery._pid_tagged reads ps's
#    exec-time environment, so a shell cannot tag itself after the fact —
#    the tag must sit on the registered pid itself or on a direct child of
#    it. autoclaude must refuse before spending any uv cost and before ever
#    handing off to the loop ─────────────────────────────────────────────
AP11="$TMP1/s11/dev/local/autopilot"
mkdir -p "$AP11"
LOOPS11="$TMP1/s11-registry"
mkdir -p "$LOOPS11"
ROOT11="$TMP1/s11"

# `export` AFTER this shell's own exec, then keep a tagged child alive: the
# tag is invisible on $LOOPSHELL11 itself, visible on the sleep beneath it
# (identical shape to scenario 40's seed below).
bash -c 'export _AUTOPILOT_LOOP=$$; sleep 60 & wait' &
LOOPSHELL11=$!
i=0
while [ -z "$(pgrep -P "$LOOPSHELL11" 2>/dev/null)" ] && [ "$i" -lt 100 ]; do
  sleep 0.05
  i=$((i + 1))
done

jq -n --argjson pid "$LOOPSHELL11" --arg root "$ROOT11" --arg ap_dir "$AP11" \
  --arg started_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{pid:$pid, root:$root, ap_dir:$ap_dir, started_at:$started_at}' \
  >"$LOOPS11/other-loop.json" # a DIFFERENT, already-registered loop for the same root; a LIVE loop, tagged on its CHILD only
export _AUTOPILOT_LOOPS_DIR="$LOOPS11"

UV_CALLS11="$TMP1/s11-uv-calls"
: >"$UV_CALLS11"
UV_CALLS_FILE="$UV_CALLS11"

STUB_CALLS11="$TMP1/s11-stub-calls"
: >"$STUB_CALLS11"
_loop_stub_s11() { printf 'x\n' >>"$STUB_CALLS11"; return 0; }
AUTOPILOT_LOOP_STUB="_loop_stub_s11"

export _AUTOPILOT_TRACON=1
run_loop "$AP11"
rc11=$?
unset _AUTOPILOT_TRACON
UV_CALLS_FILE=""
AUTOPILOT_LOOP_STUB="_loop_stub_drained"

pkill -P "$LOOPSHELL11" 2>/dev/null   # the tagged child first: this job shares
kill "$LOOPSHELL11" 2>/dev/null       # THIS shell's pgrp, so never signal the group
wait "$LOOPSHELL11" 2>/dev/null

[ "$rc11" -eq 1 ] || fail "scenario 11: duplicate-loop guard did not return 1 (rc=$rc11)"
[ ! -s "$STUB_CALLS11" ] || fail "scenario 11: the loop hand-off ran despite a live duplicate loop registered for this root"
[ ! -s "$UV_CALLS11" ] || fail "scenario 11: uv was invoked despite the duplicate-loop guard (the guard must run before any uv cost): $(cat "$UV_CALLS11")"

echo "PASS: escape hatch + auto-detect never call uv (scenarios 7-8), tracon TUI invoked once with --root/--wrapper-pid (scenario 9), preflight-fail fallback never launches a TUI (scenario 10), duplicate-loop guard blocks before any uv/loop cost (scenario 11)"

# ═══════════════════════════════════════════════════════════════════════════
# Ctrl-C stop semantics (scenarios 15-22). Pins the approved stop path:
#   - inside tracon's raw mode, Ctrl-C arrives as a KEY EVENT and tracon
#     exits rc=130 — an EXIT-CODE branch in _autoclaude_tracon's steady
#     state, driven here by stubbing `uv`'s TUI call to return 130
#   - _autoclaude_tracon_stop sends SIGINT to the LOOP's process GROUP
#     (`kill -INT -"$1"`), never a bare pid — a pid-directed INT is
#     DEFERRED by bash until the foreground pipeline ends (measured), the
#     known-bad path this suite must catch: scenario 15 pins the TIMING
#     (fast stop vs. the loop stub's slow sleep), not just the exit code
#   - before tracon grabs raw mode, a real tty Ctrl-C is an actual SIGINT
#     to the foreground process group, landing on _autoclaude_tracon's own
#     `trap ... INT` — scenario 20 drives this with a genuine signal
#   - the worst regression: after a stop, NO second session starts, and no
#     loop-tree process is left orphaned
# ═══════════════════════════════════════════════════════════════════════════

# ── Scenarios 15-19: steady-state Ctrl-C stop — rc 130 AND fast (15), the
#    loop stub's slow child is dead (16), exactly one hand-off ran (17),
#    the registry dir stays empty (18; the CLI loop owns registry writes
#    and none ran here), and the INT trap is not leaked in this shell,
#    which keeps running (19) ────────────────────────────────────────────
AP15="$TMP1/s15/dev/local/autopilot"
mkdir -p "$AP15"
LOOPS15="$TMP1/s15-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS15"

STUB_PID15="$TMP1/s15-stub-pid"
STUB_COUNT15="$TMP1/s15-stub-count"
: >"$STUB_COUNT15"
_loop_stub_s15() {
  # exec, not `sleep 30 &`: an async command started without job control
  # gets SIGINT ignored (POSIX), so the group INT could never reap it.
  printf 'x\n' >>"$STUB_COUNT15"
  printf '%s\n' "$BASHPID" >"$STUB_PID15"
  exec sleep 30
}
AUTOPILOT_LOOP_STUB="_loop_stub_s15"

# Scenario-local uv override: waits (bounded) for the loop stub's pid file
# to appear before returning 130 for the TUI call, so the stop lands on a
# genuinely in-flight loop. Restored to the shared stub right after.
UV_CALLS_FILE=""
uv() {
  case "$*" in
  *--preflight*) return 0 ;;
  *)
    local i=0
    while [ ! -s "$STUB_PID15" ] && [ "$i" -lt 100 ]; do
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
AUTOPILOT_LOOP_STUB="_loop_stub_drained"
uv() {   # restore the shared stub for later scenarios
  local rec="$*"
  [ -n "$UV_CALLS_FILE" ] && printf '%s\n' "$rec" >>"$UV_CALLS_FILE"
  case "$rec" in
  *--preflight*) return "$UV_PREFLIGHT_RC" ;;
  *) return "$UV_TUI_RC" ;;
  esac
}

# Scenario 15: rc 130, and FAST — well under the stub's 30s sleep.
[ "$rc15" -eq 130 ] || fail "scenario 15: Ctrl-C stop did not return 130 (rc=$rc15)"
[ "$_ts15_elapsed" -lt 10 ] || fail "scenario 15: Ctrl-C stop took ${_ts15_elapsed}s (>=10s) — deferred-trap bug: the stop did not return until near the stub's 30s sleep"

# Scenario 16: the loop stub's slow child (a grandchild of the forked loop
# subshell) is dead after the stop — the group INT reached the whole tree.
[ -s "$STUB_PID15" ] || fail "scenario 16 setup: loop stub never recorded its child pid"
stub_pid15="$(cat "$STUB_PID15")"
if kill -0 "$stub_pid15" 2>/dev/null; then
  fail "scenario 16: loop stub child pid $stub_pid15 still alive after the stop"
fi

# Scenario 17: exactly one hand-off ran — no second session started.
count15=$(wc -l <"$STUB_COUNT15")
[ "$count15" -eq 1 ] || fail "scenario 17: expected exactly 1 loop hand-off, got $count15 (a second one started after the stop)"

# Scenario 18: the registry dir stays empty (no CLI loop ran to write one).
[ ! -e "$LOOPS15" ] || [ -z "$(command ls -A "$LOOPS15" 2>/dev/null)" ] || fail "scenario 18: registry dir $LOOPS15 not empty after the stop: $(command ls "$LOOPS15")"

# Scenario 19: no leaked INT trap in this shell, and this shell survives.
leaked_int_trap15="$(trap -p INT)"
[ -z "$leaked_int_trap15" ] || fail "scenario 19: INT trap leaked in the invoking shell after a Ctrl-C stop: $leaked_int_trap15"

echo "PASS: Ctrl-C stop is rc 130 and fast, not deferred to the stub's slow sleep (scenario 15), loop-tree child reaped (scenario 16), no second hand-off (scenario 17), registry untouched (scenario 18), INT trap not leaked + shell survives (scenario 19)"

# ── Scenario 20: a REAL SIGINT (the pre-raw-mode window) — signal the
#    CHILD bash process's own process group exactly as a tty Ctrl-C would;
#    this lands on _autoclaude_tracon's own `trap ... INT`, not the
#    exit-code-130 branch. Converges: loop tree stopped, no orphan, rc 130 ─
AP20="$TMP1/s20/dev/local/autopilot"
mkdir -p "$AP20"
LOOPS20="$TMP1/s20-registry"
STUB_PID20="$TMP1/s20-stub-pid"

set -m
AP_DIR="$AP20" _AUTOPILOT_LOOPS_DIR="$LOOPS20" STUB_PID_FILE="$STUB_PID20" \
  bash "$CHILD_SCRIPT_TRACON" >/dev/null 2>&1 &
CHILD20=$!
set +m

i=0
while [ ! -s "$STUB_PID20" ] && [ "$i" -lt 100 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -s "$STUB_PID20" ] || fail "scenario 20 setup: the loop stub inside the child never started"

kill -INT -"$CHILD20"
_wait_bounded "$CHILD20" 20
rc20=$?

[ "$rc20" -eq 130 ] || fail "scenario 20: a real group SIGINT (pre-raw-mode window) did not converge to rc 130 (rc=$rc20)"

stub_pid20="$(cat "$STUB_PID20")"
if kill -0 "$stub_pid20" 2>/dev/null; then
  fail "scenario 20: loop stub child pid $stub_pid20 (inside the child's loop tree) still alive after the real SIGINT stop"
fi

echo "PASS: a real group SIGINT in the pre-raw-mode window converges on rc 130, loop tree stopped, no orphan (scenario 20)"

# ── Scenario 21: fork-window Ctrl-C — uv's stubbed TUI call returns 130
#    immediately, with no artificial wait for the loop stub to start,
#    maximizing the race between "loop just forked" and "stop fires".
#    Whichever way the race lands, no orphan may survive ─────────────────
AP21="$TMP1/s21/dev/local/autopilot"
mkdir -p "$AP21"
LOOPS21="$TMP1/s21-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS21"

STUB_PID21="$TMP1/s21-stub-pid"
: >"$STUB_PID21"
_loop_stub_s21() {
  printf '%s\n' "$BASHPID" >"$STUB_PID21"
  exec sleep 30
}
AUTOPILOT_LOOP_STUB="_loop_stub_s21"

UV_CALLS_FILE=""
UV_PREFLIGHT_RC=0
UV_TUI_RC=130   # returns immediately — no wait for the loop stub to start

export _AUTOPILOT_TRACON=1
_ts21_start=$SECONDS
run_loop "$AP21"
rc21=$?
_ts21_elapsed=$((SECONDS - _ts21_start))
unset _AUTOPILOT_TRACON
UV_TUI_RC=0
AUTOPILOT_LOOP_STUB="_loop_stub_drained"

[ "$rc21" -eq 130 ] || fail "scenario 21: fork-window Ctrl-C did not return 130 (rc=$rc21)"
[ "$_ts21_elapsed" -lt 10 ] || fail "scenario 21: fork-window stop took ${_ts21_elapsed}s (>=10s) — did not converge quickly"

if [ -s "$STUB_PID21" ]; then
  stub_pid21="$(cat "$STUB_PID21")"
  if kill -0 "$stub_pid21" 2>/dev/null; then
    fail "scenario 21: loop stub child pid $stub_pid21 still alive after the fork-window stop (the race landed with the stub running, and it was not reaped)"
  fi
fi

echo "PASS: fork-window Ctrl-C (stop arriving before the loop stub starts) still converges — no orphan, rc 130 (scenario 21)"

# ── Scenario 22: child pgrp self-guard — invoke autoclaude directly in
#    child mode (_AUTOPILOT_TRACON_CHILD=1) as a pipeline stage with
#    monitor mode explicitly OFF, so it inherits this shell's existing
#    process group rather than leading its own. Must refuse: return 1 and
#    never hand off to the loop ────────────────────────────────────────────
AP22="$TMP1/s22/dev/local/autopilot"
mkdir -p "$AP22"
LOOPS22="$TMP1/s22-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS22"

STUB_CALLS22="$TMP1/s22-stub-calls"
: >"$STUB_CALLS22"
_loop_stub_s22() { printf 'x\n' >>"$STUB_CALLS22"; return 0; }
AUTOPILOT_LOOP_STUB="_loop_stub_s22"

AP_DIR="$AP22"
set +m
_AUTOPILOT_TRACON_CHILD=1 autoclaude 2>/dev/null | cat >/dev/null
rc22=${PIPESTATUS[0]}
AUTOPILOT_LOOP_STUB="_loop_stub_drained"

[ "$rc22" -eq 1 ] || fail "scenario 22: non-pgrp-leader child self-guard did not return 1 (rc=$rc22)"
[ ! -s "$STUB_CALLS22" ] || fail "scenario 22: the loop hand-off ran despite the pgrp self-guard (calls: $(wc -l <"$STUB_CALLS22"))"

echo "PASS: child pgrp self-guard refuses a loop that cannot be stopped — rc 1, no hand-off (scenario 22)"

# ═══════════════════════════════════════════════════════════════════════════
# Two defects in _autoclaude_tracon's own INT/TERM handling that the
# steady-state scenarios above do not reach (scenarios 24-25):
#   (A) the parent installs its INT trap BEFORE the fork, gated on
#       `[ -n "$_loop" ]` rather than falling back to a bare `$!` — an INT
#       in the PRE-fork window is a no-op, never a misdirected kill.
#   (B) a SIGTERM to the foreground wrapper runs the same teardown as INT
#       instead of leaving the backgrounded loop orphaned.
# ═══════════════════════════════════════════════════════════════════════════

# ── Scenario 24: Defect A — an INT delivered in the PRE-fork window (after
#    the trap install, before the backgrounded loop's pid is captured) must
#    NOT signal an unrelated background job the caller already had running,
#    and autoclaude must still converge on rc 130. Reproduced
#    deterministically with a `functrace` DEBUG trap that recognizes the
#    ONE fork line by its unique literal (`_AUTOPILOT_TRACON_CHILD=1`) and
#    self-signals — via $BASHPID, not $$ — immediately before it executes ──
AP24="$TMP1/s24/dev/local/autopilot"
mkdir -p "$AP24"
LOOPS24="$TMP1/s24-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS24"

STUB_CALLS24="$TMP1/s24-stub-calls"
: >"$STUB_CALLS24"
_loop_stub_s24() { printf 'x\n' >>"$STUB_CALLS24"; return 0; }
AUTOPILOT_LOOP_STUB="_loop_stub_s24"

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
AUTOPILOT_LOOP_STUB="_loop_stub_drained"

[ "$rc24" -eq 130 ] || fail "scenario 24: a pre-fork-window INT did not converge to rc 130 (rc=$rc24)"
[ ! -s "$STUB_CALLS24" ] || fail "scenario 24 setup: the loop hand-off ran — the interrupt landed AFTER the fork completed, not in the pre-fork window this scenario targets"

kill -0 "$HARMLESS24" 2>/dev/null \
  || fail "scenario 24: the pre-fork-window INT killed the CALLER's unrelated background job (pid $HARMLESS24) — \${_loop:-\$!} fell back to \$!, and _autoclaude_tracon_stop signaled its process group"

kill -- -"$HARMLESS24" 2>/dev/null
wait "$HARMLESS24" 2>/dev/null

echo "PASS: a pre-fork-window INT converges on rc 130 without signaling the caller's unrelated background job (scenario 24)"

# ── Scenario 25: Defect B — a real SIGTERM to the tracon parent PROCESS
#    ONLY (never its group — a real terminal signals the foreground
#    process) must converge on rc 143 with the loop tree stopped and no
#    orphaned stub child. Reuses CHILD_SCRIPT_TRACON verbatim; only the
#    signal and its target (pid, not group) differ from scenario 20 ───────
AP25="$TMP1/s25/dev/local/autopilot"
mkdir -p "$AP25"
LOOPS25="$TMP1/s25-registry"
STUB_PID25="$TMP1/s25-stub-pid"

set -m
AP_DIR="$AP25" _AUTOPILOT_LOOPS_DIR="$LOOPS25" STUB_PID_FILE="$STUB_PID25" \
  bash "$CHILD_SCRIPT_TRACON" >/dev/null 2>&1 &
CHILD25=$!
set +m

i=0
while [ ! -s "$STUB_PID25" ] && [ "$i" -lt 100 ]; do
  sleep 0.05
  i=$((i + 1))
done
[ -s "$STUB_PID25" ] || fail "scenario 25 setup: the loop stub inside the child never started"

kill -TERM "$CHILD25"
i=0
while kill -0 "$CHILD25" 2>/dev/null && [ "$i" -lt 200 ]; do
  sleep 0.1
  i=$((i + 1))
done
kill -0 "$CHILD25" 2>/dev/null && kill -KILL "$CHILD25" 2>/dev/null
wait "$CHILD25" 2>/dev/null
rc25=$?

stub_pid25="$(cat "$STUB_PID25")"
stub_alive25=0
kill -0 "$stub_pid25" 2>/dev/null && stub_alive25=1

# Clean up the orphan (if any) BEFORE asserting, so a failure here can
# never leak a live stub child or loop process group into later scenarios.
kill -KILL "$stub_pid25" 2>/dev/null

[ "$rc25" -eq 143 ] || fail "scenario 25: TERM to the tracon parent did not converge to rc 143 (rc=$rc25)"
[ "$stub_alive25" -eq 0 ] || fail "scenario 25: loop stub child pid $stub_pid25 still alive after TERM to the tracon parent — SIGTERM took bash's default action and the backgrounded loop kept running as an orphan"

leaked_int_trap25="$(trap -p INT)"
leaked_term_trap25="$(trap -p TERM)"
[ -z "$leaked_int_trap25" ] || fail "scenario 25: INT trap leaked in the invoking shell after the TERM scenario: $leaked_int_trap25"
[ -z "$leaked_term_trap25" ] || fail "scenario 25: TERM trap leaked in the invoking shell after the TERM scenario: $leaked_term_trap25"

echo "PASS: a real SIGTERM to the tracon parent (pid, not group) converges on rc 143 with the loop tree stopped and no orphaned stub child (scenario 25)"

# ── Scenario 31: a live-but-NOT-autoclaude pid in the registry must not
#    read as a live wrapper — the front-end prune validates the
#    _AUTOPILOT_LOOP=<pid> tag, so a live-but-unrelated pid (a plain
#    `sleep`) is swept and never blocks a new loop ────────────────────────
AP31="$TMP1/s31/dev/local/autopilot"
mkdir -p "$AP31"
LOOPS31="$TMP1/s31-registry"
mkdir -p "$LOOPS31"
ROOT31="$TMP1/s31"

sleep 60 &
UNRELATED31=$!

jq -n --argjson pid "$UNRELATED31" --arg root "$ROOT31" --arg ap_dir "$AP31" \
  --arg started_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{pid:$pid, root:$root, ap_dir:$ap_dir, started_at:$started_at}' \
  >"$LOOPS31/other-loop.json" # a LIVE pid, but NOT tagged _AUTOPILOT_LOOP=<pid> — a plain sleep, not a real loop
export _AUTOPILOT_LOOPS_DIR="$LOOPS31"

STUB_CALLS31="$TMP1/s31-stub-calls"
: >"$STUB_CALLS31"
_loop_stub_s31() { printf 'x\n' >>"$STUB_CALLS31"; sleep 0.3; return 0; }
AUTOPILOT_LOOP_STUB="_loop_stub_s31"

UV_CALLS_FILE=""
UV_PREFLIGHT_RC=0
UV_TUI_RC=0

export _AUTOPILOT_TRACON=1
run_loop "$AP31"
rc31=$?
unset _AUTOPILOT_TRACON
AUTOPILOT_LOOP_STUB="_loop_stub_drained"

i=0
while [ ! -s "$STUB_CALLS31" ] && [ "$i" -lt 100 ]; do
  sleep 0.05
  i=$((i + 1))
done

kill "$UNRELATED31" 2>/dev/null
wait "$UNRELATED31" 2>/dev/null

[ "$rc31" -eq 0 ] || fail "scenario 31: a live-but-unrelated (untagged) pid in the registry blocked a new loop (rc=$rc31) — the prune must verify the _AUTOPILOT_LOOP tag, not just liveness"
[ -s "$STUB_CALLS31" ] || fail "scenario 31: the loop hand-off never ran — the loop was blocked by a live-but-unrelated registry entry"

echo "PASS: a live-but-unrelated (untagged) pid in the registry does not block a new loop (scenario 31)"

# ═══════════════════════════════════════════════════════════════════════════
# Loop-exit diagnostics surfaced from wrapper.log (scenarios 34-36, 39).
# In tracon mode the loop child's stdout/stderr are redirected to
# wrapper.log, so operator-facing diagnostics (the 3-step resume runbook,
# the died-session pointers) would otherwise be swallowed when the loop
# exits. _autoclaude_tracon_surface <wrapper_log_path> <child_rc>: a
# non-empty wrapper.log -> print a separator + its tail (~20 lines) to
# stderr, on ANY child_rc; a missing or empty wrapper.log -> nothing. The
# rc-0 gate was removed 2026-08-02: pause/park/drain all `return 0`, so it
# silenced exactly the exits that most needed a reason.
# ═══════════════════════════════════════════════════════════════════════════

# Shared wrapper.log fixture: real lines lifted verbatim from the loop's
# operator-pause branch and the paused-signal branch's 3-step resume
# runbook (now printed by cli/loop.py, same text), so the assertions bind
# the ACTUAL swallowed messages, not stand-ins.
WRAPPERLOG_F="$TMP1/f-wrapper.log"
cat > "$WRAPPERLOG_F" <<'EOF'
━━ 12:00:00 · phase build · prd tracon-test.md · claude-opus-5[1m]/xhigh ━━

autoclaude: paused by operator. State intact.
Resume unattended: autoclaude
To take over first: claude → /run-autopilot, then autoclaude

autoclaude: session paused — needs human input.
To resume (re-running autoclaude now would just pause again):
  1. claude            # interactive session in this repo
  2. /run-autopilot    # resumes from state.json; blockers become questions
  3. autoclaude        # after the decision, to continue unattended
EOF

# ── Scenario 34: non-zero child_rc surfaces the resume-runbook text on
#    stderr ──────────────────────────────────────────────────────────────
ERR34="$TMP1/f34-err"
_autoclaude_tracon_surface "$WRAPPERLOG_F" 1 2>"$ERR34"

grep -qF '1. claude' "$ERR34" ||
  fail "scenario 34: _autoclaude_tracon_surface did not surface the resume-runbook text ('1. claude') from wrapper.log to stderr on a non-zero child_rc (captured stderr: $(cat "$ERR34" 2>/dev/null))"

# ── Scenario 35: a CLEAN exit (child_rc 0) surfaces the tail too ─────────
ERR35="$TMP1/f35-err"
_autoclaude_tracon_surface "$WRAPPERLOG_F" 0 2>"$ERR35"

grep -qF 'paused by operator' "$ERR35" ||
  fail "scenario 35: _autoclaude_tracon_surface stayed silent on a clean exit (child_rc=0) — the pause reason in wrapper.log never reached the terminal (captured stderr: $(cat "$ERR35" 2>/dev/null))"

# ── Scenario 36: a missing or empty wrapper.log is safe — no output, no
#    error, even with a non-zero child_rc ─────────────────────────────────
MISSING36="$TMP1/f36-does-not-exist.log"
EMPTY36="$TMP1/f36-empty.log"
: >"$EMPTY36"

ERR36A="$TMP1/f36-err-missing"
_autoclaude_tracon_surface "$MISSING36" 1 2>"$ERR36A"
rc36a=$?
[ "$rc36a" -eq 0 ] || fail "scenario 36: _autoclaude_tracon_surface exited non-zero ($rc36a) for a missing wrapper.log — must not error"
[ ! -s "$ERR36A" ] || fail "scenario 36: _autoclaude_tracon_surface printed diagnostics for a MISSING wrapper.log: $(cat "$ERR36A" 2>/dev/null)"

ERR36B="$TMP1/f36-err-empty"
_autoclaude_tracon_surface "$EMPTY36" 1 2>"$ERR36B"
rc36b=$?
[ "$rc36b" -eq 0 ] || fail "scenario 36: _autoclaude_tracon_surface exited non-zero ($rc36b) for an empty wrapper.log — must not error"
[ ! -s "$ERR36B" ] || fail "scenario 36: _autoclaude_tracon_surface printed diagnostics for an EMPTY wrapper.log: $(cat "$ERR36B" 2>/dev/null)"

echo "PASS: non-zero child_rc surfaces the resume-runbook text from wrapper.log to stderr (scenario 34), a clean exit surfaces it too (scenario 35), a missing or empty wrapper.log is safe (scenario 36)"

# ── Scenario 37 (G1): the backgrounded tracon TUI call must receive the
#    parent shell's own stdin, not /dev/null — feed a sentinel on this
#    invocation's stdin and have the uv TUI-call stub read it back off its
#    own fd 0. A background job started under `set +m` gets /dev/null stdin
#    per POSIX in the absence of an explicit redirection; the `<&0` on the
#    TUI launch line is what keeps the real Textual TUI able to read keys ──
AP37="$TMP1/s37/dev/local/autopilot"
mkdir -p "$AP37"
LOOPS37="$TMP1/s37-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS37"

STDIN_CAP37="$TMP1/s37-stdin-capture"
: >"$STDIN_CAP37"
UV_CALLS_FILE=""
UV_PREFLIGHT_RC=0
UV_TUI_RC=0
# Scenario-local uv override: the TUI call reads ONE line off its own fd 0
# and records it. `IFS= read -r` returns non-zero on EOF and leaves the
# variable empty rather than blocking — the sentinel is already sitting on
# the pipe (fed via the here-string below). Restored right after.
uv() {
  case "$*" in
  *--preflight*) return "$UV_PREFLIGHT_RC" ;;
  *--wrapper-pid*)
    local _line=""
    IFS= read -r _line <&0
    printf '%s' "$_line" >"$STDIN_CAP37"
    return "$UV_TUI_RC" ;;
  *) return "$UV_TUI_RC" ;;
  esac
}

export _AUTOPILOT_TRACON=1
run_loop "$AP37" <<<'STDIN_SENTINEL_XYZ'
rc37=$?
unset _AUTOPILOT_TRACON
uv() {   # restore the shared stub
  local rec="$*"
  [ -n "$UV_CALLS_FILE" ] && printf '%s\n' "$rec" >>"$UV_CALLS_FILE"
  case "$rec" in
  *--preflight*) return "$UV_PREFLIGHT_RC" ;;
  *) return "$UV_TUI_RC" ;;
  esac
}

[ "$rc37" -eq 0 ] || fail "scenario 37 setup: tracon-path run did not return 0 (rc=$rc37)"

got37="$(cat "$STDIN_CAP37" 2>/dev/null)"
echo "scenario 37: backgrounded-uv observed stdin: '${got37:-<empty>}'"

[ "$got37" = "STDIN_SENTINEL_XYZ" ] || fail "scenario 37: the backgrounded uv TUI call's own fd 0 read '${got37:-<empty>}', expected the parent shell's stdin sentinel 'STDIN_SENTINEL_XYZ' — bash gave the async uv job a stdin other than the parent's own, which would leave the real tracon TUI deaf to tty keys"

echo "PASS: the backgrounded tracon TUI call inherits the parent shell's own stdin, not a bash-default /dev/null (scenario 37)"

# ── Scenario 38 (G2): _AUTOPILOT_LOOPS_DIR must be exported by the tracon
#    PARENT itself before it spawns anything that reads it from its own
#    environment — set with a plain (non-exported) assignment so only a
#    genuine `export` inside _autoclaude_tracon can make it visible to a
#    REAL exec'd child ─────────────────────────────────────────────────────
AP38="$TMP1/s38/dev/local/autopilot"
mkdir -p "$AP38"

LOOPS38="$TMP1/s38-registry"
mkdir -p "$LOOPS38"
unset _AUTOPILOT_LOOPS_DIR       # drop any earlier scenario's export attribute entirely — a plain
                                  # reassignment over an already-exported var stays exported
_AUTOPILOT_LOOPS_DIR="$LOOPS38"  # plain assignment, deliberately NOT exported

# Sandbox $HOME too: tracon_wrapper_alive.py (the duplicate-loop guard, run
# for real here) is invoked by the literal path
# `~/.claude/skills/.../tracon_wrapper_alive.py`, which tilde-expands
# against $HOME at call time. Under a sandboxed HOME that path does not
# exist, so the real `python3 <missing file>` call fails fast (nonzero rc,
# same as a proper "not alive" result) WITHOUT ever importing
# tracon.discovery and reading the real ~/.claude/autopilot-loops.
HOME38="$TMP1/s38-home"
mkdir -p "$HOME38"
_home_saved38="$HOME"
export HOME="$HOME38"

ENV_CAP38="$TMP1/s38-env-capture"
: >"$ENV_CAP38"
UV_CALLS_FILE=""
UV_PREFLIGHT_RC=0
UV_TUI_RC=0
# Scenario-local uv override: the TUI call execs a REAL external binary
# (printenv) — the only way to distinguish "truly exported" from "a plain
# shell variable the same-process async fork happens to see". Restored
# right after.
uv() {
  case "$*" in
  *--preflight*) return "$UV_PREFLIGHT_RC" ;;
  *--wrapper-pid*)
    command printenv _AUTOPILOT_LOOPS_DIR >"$ENV_CAP38" 2>/dev/null
    return "$UV_TUI_RC" ;;
  *) return "$UV_TUI_RC" ;;
  esac
}

export _AUTOPILOT_TRACON=1
run_loop "$AP38"
rc38=$?
unset _AUTOPILOT_TRACON
uv() {   # restore the shared stub
  local rec="$*"
  [ -n "$UV_CALLS_FILE" ] && printf '%s\n' "$rec" >>"$UV_CALLS_FILE"
  case "$rec" in
  *--preflight*) return "$UV_PREFLIGHT_RC" ;;
  *) return "$UV_TUI_RC" ;;
  esac
}
export HOME="$_home_saved38"
unset _AUTOPILOT_LOOPS_DIR   # leave no dangling non-exported value for later scenarios

[ "$rc38" -eq 0 ] || fail "scenario 38 setup: tracon-path run did not return 0 (rc=$rc38)"

got38="$(cat "$ENV_CAP38" 2>/dev/null)"
echo "scenario 38: observed _AUTOPILOT_LOOPS_DIR in the backgrounded uv TUI call's own (real, execed) environment: '${got38:-<empty>}' (parent used '$LOOPS38')"

[ "$got38" = "$LOOPS38" ] || fail "scenario 38: the backgrounded uv TUI call — a REAL child the tracon PARENT spawns — saw _AUTOPILOT_LOOPS_DIR='${got38:-<empty>}' in its own environment, expected the parent's resolved loops dir '$LOOPS38'"

echo "PASS: _AUTOPILOT_LOOPS_DIR is exported by the tracon PARENT itself before it spawns children (scenario 38)"

# ── Scenario 39: a paused loop's resume-runbook diagnostics, written to
#    wrapper.log by the backgrounded tracon child (the CLI loop prints them
#    to its stderr, which the fork redirects into wrapper.log), reach the
#    PARENT autoclaude call's own stderr via _autoclaude_tracon_surface at
#    its live call sites ──────────────────────────────────────────────────
AP39="$TMP1/s39/dev/local/autopilot"
mkdir -p "$AP39"
LOOPS39="$TMP1/s39-registry"
export _AUTOPILOT_LOOPS_DIR="$LOOPS39"

# The loop stub emulates cli/loop.py's paused exit: the runbook on stderr
# (== wrapper.log in child mode), rc 1. The brief sleep keeps the forked
# subshell alive through the front-end's belt-and-braces pgrp check.
_loop_stub_s39() {
  sleep 0.3
  {
    printf '⏸ autoclaude: session paused ON PURPOSE — needs human input\n'
    printf 'To resume (re-running autoclaude now would just pause again):\n'
    printf '  1. claude            # interactive session in this repo\n'
    printf '  2. /run-autopilot    # resumes from state.json; blockers become questions\n'
    printf '  3. autoclaude        # after the decision, to continue unattended\n'
  } >&2
  return 1
}
AUTOPILOT_LOOP_STUB="_loop_stub_s39"

UV_CALLS_FILE=""
UV_PREFLIGHT_RC=0
UV_TUI_RC=0
# Scenario-local uv override: the TUI call polls until the loop's own pid
# (read off its own argv) is dead, then returns 3 ("tracon says the loop
# ended"), landing on _autoclaude_tracon's case-3 verify branch (or the
# final `wait` fallback — both call the same helper). Restored right after.
uv() {
  case "$*" in
  *--preflight*) return 0 ;;
  *--wrapper-pid*)
    local wpid i
    wpid=$(_argv_value "$*" --wrapper-pid)
    i=0
    while kill -0 "$wpid" 2>/dev/null && [ "$i" -lt 100 ]; do
      sleep 0.05
      i=$((i + 1))
    done
    return 3 ;;
  *) return 0 ;;
  esac
}

ERR39="$TMP1/s39-err"
AP_DIR="$AP39"
export _AUTOPILOT_TRACON=1
autoclaude >/dev/null 2>"$ERR39"
rc39=$?
unset _AUTOPILOT_TRACON
AUTOPILOT_LOOP_STUB="_loop_stub_drained"
uv() {   # restore the shared stub
  local rec="$*"
  [ -n "$UV_CALLS_FILE" ] && printf '%s\n' "$rec" >>"$UV_CALLS_FILE"
  case "$rec" in
  *--preflight*) return "$UV_PREFLIGHT_RC" ;;
  *) return "$UV_TUI_RC" ;;
  esac
}

[ "$rc39" -eq 1 ] || fail "scenario 39: paused loop via the tracon path did not return 1 (rc=$rc39)"

grep -qF '1. claude' "$ERR39" ||
  fail "scenario 39: the paused loop's resume-runbook text ('1. claude') never reached the PARENT autoclaude call's own stderr — _autoclaude_tracon_surface is not wired at its live call sites (captured stderr: $(cat "$ERR39" 2>/dev/null))"

echo "PASS: a paused loop's resume-runbook diagnostics reach the PARENT autoclaude call's own stderr via _autoclaude_tracon_surface (scenario 39)"

# ── Scenario 40: a LIVE loop shaped exactly like the tracon fork — a shell
#    whose _AUTOPILOT_LOOP tag reaches ps only on its exec'd child — must
#    SURVIVE the prune and block a second loop. ps reports the exec-time
#    environment, so matching the shell alone swept live loops out of the
#    registry and left tracon reading them as dead (no pause chip, no
#    limit-wait, q → s "nothing to stop") ──────────────────────────────────
AP40="$TMP1/s40/dev/local/autopilot"
mkdir -p "$AP40"
LOOPS40="$TMP1/s40-registry"
mkdir -p "$LOOPS40"
ROOT40="$TMP1/s40"

# `export` AFTER this shell's own exec, then keep a tagged child alive: the
# tag is invisible on $LOOPSHELL40 itself, visible on the sleep beneath it.
bash -c 'export _AUTOPILOT_LOOP=$$; sleep 60 & wait' &
LOOPSHELL40=$!
i=0
while [ -z "$(pgrep -P "$LOOPSHELL40" 2>/dev/null)" ] && [ "$i" -lt 100 ]; do
  sleep 0.05
  i=$((i + 1))
done

jq -n --argjson pid "$LOOPSHELL40" --arg root "$ROOT40" --arg ap_dir "$AP40" \
  --arg started_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{pid:$pid, root:$root, ap_dir:$ap_dir, started_at:$started_at}' \
  >"$LOOPS40/other-loop.json" # a LIVE loop, tagged on its CHILD only
export _AUTOPILOT_LOOPS_DIR="$LOOPS40"

STUB_CALLS40="$TMP1/s40-stub-calls"
: >"$STUB_CALLS40"
_loop_stub_s40() { printf 'x\n' >>"$STUB_CALLS40"; sleep 0.3; return 0; }
AUTOPILOT_LOOP_STUB="_loop_stub_s40"

UV_CALLS_FILE=""
UV_PREFLIGHT_RC=0
UV_TUI_RC=0

export _AUTOPILOT_TRACON=1
run_loop "$AP40"
rc40=$?
unset _AUTOPILOT_TRACON
AUTOPILOT_LOOP_STUB="_loop_stub_drained"

pkill -P "$LOOPSHELL40" 2>/dev/null   # the tagged child first: this job shares
kill "$LOOPSHELL40" 2>/dev/null       # THIS shell's pgrp, so never signal the group
wait "$LOOPSHELL40" 2>/dev/null

[ -s "$LOOPS40/other-loop.json" ] || fail "scenario 40: the prune swept a LIVE loop's registry entry — its _AUTOPILOT_LOOP tag sits on the exec'd child, not on the registered shell, and ps shows the exec-time env"
[ "$rc40" -eq 1 ] || fail "scenario 40: the duplicate-loop guard did not refuse a second loop for a live incumbent (rc=$rc40)"
[ ! -s "$STUB_CALLS40" ] || fail "scenario 40: the loop hand-off ran despite a live loop already registered for this root"

echo "PASS: a live loop tagged only on its exec'd child survives the prune and still blocks a second loop (scenario 40)"

# Natural-completion cleanup for the $TMP1 scratch tree — see the G3 note
# for why this is a plain end-of-script `rm -rf`, not a trap.
rm -rf "$TMP1"

echo ""
echo "All checks passed."
exit 0
