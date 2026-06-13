cite about-plugin
about-plugin 'functions for software development'

# start Claude Code working around the bugs
# claude() {
#   SHELL=/bin/sh GIT_PAGER=cat command claude --plugin-dir ~/.config/claude/ "$@"
# }

autoclaude() {
  export _AUTOPILOT_LOOP=$$

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

  trap '_autopilot_loop_cleanup; unset _AUTOPILOT_LOOP; trap - INT; kill -INT $$' INT
  trap '_autopilot_loop_cleanup; unset _AUTOPILOT_LOOP; trap - TERM; kill -TERM $$' TERM

  while true; do
    local signal

    # Static launch: every autopilot session runs on Opus 1M. The phase-based
    # model dispatch (_autoclaude_pick_model) is deleted — it never switched a
    # model in practice and its context_window bookkeeping misfired the cap.
    # next_phase remains in state.json as resume/log metadata (read by the
    # SKILL resume logic, not here); per-task tiering inside /work still does
    # the model split that works.
    claude --model claude-opus-4-8 --name "${PWD##*/}" --permission-mode auto "/run-autopilot"
    _autopilot_loop_cleanup

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
      trap - INT TERM
      unset _AUTOPILOT_LOOP
      return 1
      ;;
    *)
      printf '\nautoclaude: unknown signal "%s", stopping loop. Check %s/state.json.\n' "$signal" "$_ap_dir" >&2
      trap - INT TERM
      unset _AUTOPILOT_LOOP
      return 1
      ;;
    esac
  done
}
