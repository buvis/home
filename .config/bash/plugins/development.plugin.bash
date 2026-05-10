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
    local before_sha signal

    before_sha=$(git rev-parse HEAD 2>/dev/null)

    claude --name "${PWD##*/}" --permission-mode acceptEdits "/run-autopilot"
    _autopilot_loop_cleanup

    signal=$(cat dev/local/autopilot/signal 2>/dev/null)
    rm -f dev/local/autopilot/signal

    if [ "$(git rev-parse HEAD 2>/dev/null)" != "$before_sha" ]; then
      local report
      report=$(ls -t dev/local/autopilot/reports/*-report.md 2>/dev/null | head -1)

      CLEANUP_SINCE="$before_sha" AUTOPILOT_REPORT="$report" \
        ~/.claude/skills/use-codex/scripts/codex-run.sh -m gpt-5.5 -a \
        -f ~/.claude/skills/run-autopilot/prompts/de-sloppify.md
      _autopilot_loop_cleanup
    fi

    if [ "$signal" != "next" ]; then
      printf '\nBacklog drained.\n'
      trap - INT TERM
      unset _AUTOPILOT_LOOP
      return
    fi

    printf '\nStarting next PRD…\n'
  done
}
