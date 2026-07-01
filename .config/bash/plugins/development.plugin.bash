cite about-plugin
about-plugin 'functions for software development'

# start Claude Code working around the bugs
# claude() {
#   SHELL=/bin/sh GIT_PAGER=cat command claude --plugin-dir ~/.config/claude/ "$@"
# }

# _autopilot_loop_yield_stale <marker_path> <idle_mins>
# exit 0 == stale (file exists AND mtime older than idle_mins); exit 1 == fresh or absent.
# The Stop hook stamps the marker only on a background-task-orphan abstain; a PostToolUse
# hook clears it on any tool use. So "stale" means "yielded waiting >N min with no re-invoke".
_autopilot_loop_yield_stale() {
  local _m="$1" _mins="$2"
  [ -f "$_m" ] || return 1
  [ -n "$(find "$_m" -mmin +"$_mins" 2>/dev/null)" ]
}

# _autopilot_loop_watchdog <wrapper_pid> <marker_path> <idle_mins> <poll_secs> <kill_after>
# Sidecar around the foreground `claude`: resolves the wrapper's direct child whose comm is
# claude, polls every <poll_secs>; when the yield marker is stale it SIGINTs, escalating to
# SIGKILL after <kill_after> further stale polls. Returns when `claude` dies. Never touches
# the TTY for input. Converts a background-task-orphan idle into the loud no-signal halt.
_autopilot_loop_watchdog() {
  local _self="$BASHPID"          # FIRST statement — capture this sidecar subshell's own pid
                                  # OUTSIDE any $(...): $BASHPID inside a command substitution
                                  # is the substitution's subshell, NOT this function-subshell.
  local _wpid="$1" _m="$2" _mins="$3" _secs="$4" _kafter="$5"
  local _cpid="" _stale_streak=0 _p
  while true; do
    sleep "$_secs"
    # (Re)resolve claude: the wrapper's direct child, not the sidecar, whose comm is claude.
    if [ -z "$_cpid" ] || ! kill -0 "$_cpid" 2>/dev/null; then
      _cpid=""
      for _p in $(pgrep -P "$_wpid" 2>/dev/null); do
        [ "$_p" = "$_self" ] && continue
        # Exact comm match (design contract: comm == claude), not a `*claude`
        # glob — a bystander like `myclaude` must never be selected. `comm=`
        # is the basename on macOS but may be a full path elsewhere, so accept
        # a trailing `/claude` too.
        case "$(ps -p "$_p" -o comm= 2>/dev/null)" in
          claude|*/claude) _cpid="$_p"; break ;;
        esac
      done
    fi
    [ -n "$_cpid" ] && kill -0 "$_cpid" 2>/dev/null || break
    if _autopilot_loop_yield_stale "$_m" "$_mins"; then
      _stale_streak=$((_stale_streak + 1))
      if [ "$_stale_streak" -gt "$_kafter" ]; then
        printf '\nautoclaude: session idle-waiting >%s min and unresponsive to SIGINT; SIGKILL (idle watchdog).\n' "$_mins" >&2
        kill -KILL "$_cpid" 2>/dev/null
      else
        printf '\nautoclaude: session idle-waiting >%s min while alive; SIGINT (idle watchdog).\n' "$_mins" >&2
        kill -INT "$_cpid" 2>/dev/null
      fi
    else
      _stale_streak=0
    fi
  done
}

autoclaude() {
  export _AUTOPILOT_LOOP=$$
  local _wd_pid=""   # idle-watchdog sidecar pid; referenced by the INT/TERM traps

  # Kill orphaned (PPID=1) processes tagged with our marker.
  # Uses SIGHUP so shells propagate the signal to their children.
  _autopilot_loop_cleanup() {
    local pid
    while IFS= read -r pid; do
      [ -n "$pid" ] || continue
      ps ewww -p "$pid" -o command= 2>/dev/null | grep -qE "_AUTOPILOT_LOOP=${_AUTOPILOT_LOOP}( |$)" || continue
      kill -HUP "$pid" 2>/dev/null
    done < <(pgrep -u "$USER" -P 1 2>/dev/null)
  }

  trap '_autopilot_loop_cleanup; kill "$_wd_pid" 2>/dev/null; unset _AUTOPILOT_LOOP; trap - INT; kill -INT $$' INT
  trap '_autopilot_loop_cleanup; kill "$_wd_pid" 2>/dev/null; unset _AUTOPILOT_LOOP; trap - TERM; kill -TERM $$' TERM

  while true; do
    local signal

    # Memory circuit-breaker (2026-06-25): refuse to launch a session when the
    # machine is already under memory pressure. An overnight run fanned out
    # concurrent cargo/rustc builds and exhausted RAM (jetsam -> logout ->
    # ENOMEM lockout). Stopping loud beats piling another build-heavy session
    # onto a stressed box. Level: 1 normal, 2 warning, 4 critical.
    local _mem_pressure
    _mem_pressure=$(sysctl -n kern.memorystatus_vm_pressure_level 2>/dev/null)
    if [ -n "$_mem_pressure" ] && [ "$_mem_pressure" -ge 2 ] 2>/dev/null; then
      printf '\nautoclaude: memory pressure (level %s); stopping loop before launching next session. Free RAM, then re-run.\n' "$_mem_pressure" >&2
      python3 ~/.claude/hooks/notify.py --send "autopilot ⚠️ ${PWD##*/}" "Stopped: memory pressure (level $_mem_pressure). Free RAM, then re-run autoclaude." 2>/dev/null
      trap - INT TERM
      unset _AUTOPILOT_LOOP
      return 1
    fi

    # Resolve the autopilot dir once, BEFORE launch: the idle watchdog needs the
    # marker path, and the signal read below reuses it.
    local _ap_dir
    _ap_dir=$(python3 ~/.claude/skills/run-autopilot/scripts/_walk_up.py --bash 2>/dev/null)
    if [ -z "$_ap_dir" ]; then
      # Walk-up failed (python3 missing or import error). Fall back to an
      # absolute path anchored at the current dir rather than a bare
      # relative path, so the signal read/delete does not silently target
      # the wrong directory if cwd has drifted.
      printf 'autoclaude: _walk_up.py failed; falling back to %s/dev/local/autopilot\n' "$PWD" >&2
      _ap_dir="$PWD/dev/local/autopilot"
    fi

    # A stale yield marker from the prior session must not arm the watchdog
    # against a fresh session.
    rm -f "$_ap_dir/.yielded-waiting"

    # Idle watchdog (2026-06-30): a background task that orphans (never
    # re-invokes) leaves the Stop hook abstaining forever, idling the session
    # and blocking this loop (a subagent chmod +x prompt hung it 1h51m). The
    # Stop hook stamps <ap_dir>/.yielded-waiting on each such abstain; the
    # matcher-less PostToolUse clear hook removes it on any tool use. This
    # sidecar SIGINT→SIGKILLs a session whose marker stays stale past N min,
    # turning the idle into the loud no-signal halt below. Env-overridable.
    local _idle_mins="${_AUTOPILOT_IDLE_MINS:-20}"
    local _poll_secs="${_AUTOPILOT_POLL_SECS:-60}"
    local _kill_after="${_AUTOPILOT_KILL_AFTER:-2}"
    _autopilot_loop_watchdog "$$" "$_ap_dir/.yielded-waiting" "$_idle_mins" "$_poll_secs" "$_kill_after" &
    _wd_pid=$!

    # Static launch: every autopilot session runs on Opus 1M. The phase-based
    # model dispatch (_autoclaude_pick_model) is deleted — it never switched a
    # model in practice and its context_window bookkeeping misfired the cap.
    # next_phase remains in state.json as resume/log metadata (read by the
    # SKILL resume logic, not here); per-task tiering inside /work still does
    # the model split that works.
    # WARDEN_UNATTENDED: command-scoped so warden (claude's hook child) turns an
    # unanswerable `ask` into a fast `deny` instead of a forever-hang. NOT
    # exported to the shell, so interactive `claude` outside the loop still
    # prompts normally. (A subagent `chmod +x` ask deadlocked the loop 1h51m,
    # 2026-06-30.)
    WARDEN_UNATTENDED=1 claude --model claude-opus-4-8 --name "${PWD##*/}" --permission-mode auto "/run-autopilot"

    # Tear down the sidecar before reading the loop signal.
    kill "$_wd_pid" 2>/dev/null
    wait "$_wd_pid" 2>/dev/null
    _autopilot_loop_cleanup
    signal=$(cat "$_ap_dir/signal" 2>/dev/null)
    rm -f "$_ap_dir/signal"

    case "$signal" in
    next)
      printf '\nStarting next PRD…\n'
      ;;
    task_aborted)
      # Work-phase subagent_prompt_overrun. /work set stall_reason and
      # appended to task_aborts; /run-autopilot Phase 0 in the next session
      # replans the PRD in place (PRD stays in dev/local/prds/wip/) and
      # resumes. This is the one surviving replan path — the context cap no
      # longer aborts here; it ROTATES, writing the `next` signal instead.
      # Treat as continue-loop.
      printf '\nWork task prompt overran budget; PRD will be replanned. Continuing…\n'
      ;;
    done)
      # Written by batch-end review only — the one signal that means the
      # backlog is actually empty.
      printf '\nBacklog drained.\n'
      python3 ~/.claude/hooks/notify.py --send "autopilot ✅ ${PWD##*/}" "Backlog drained."
      trap - INT TERM
      unset _AUTOPILOT_LOOP
      return
      ;;
    '')
      # No signal at all: the session died, paused for attention, or a
      # Stop-hook gate blocked the handoff. NOT a drained backlog — fail
      # loud and leave state.json in place for inspection. (A missing
      # signal used to fall into the drained branch and masked a killed
      # handoff as success on 2026-06-11.)
      printf '\nautoclaude: session ended without a signal (died, paused, or gate-blocked). Backlog NOT drained. Check %s/state.json and the last transcript.\n' "$_ap_dir" >&2
      python3 ~/.claude/hooks/notify.py --send "autopilot ⚠️ ${PWD##*/}" "Stopped, no signal (died, paused, or gate-blocked). Needs attention."
      trap - INT TERM
      unset _AUTOPILOT_LOOP
      return 1
      ;;
    *)
      printf '\nautoclaude: unknown signal "%s", stopping loop. Check %s/state.json.\n' "$signal" "$_ap_dir" >&2
      python3 ~/.claude/hooks/notify.py --send "autopilot ⚠️ ${PWD##*/}" "Stopped, unknown signal '$signal'. Needs attention."
      trap - INT TERM
      unset _AUTOPILOT_LOOP
      return 1
      ;;
    esac
  done
}
