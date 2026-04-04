cite about-plugin
about-plugin 'functions for software development'

# start Claude Code working around the bugs
# claude() {
#   SHELL=/bin/sh GIT_PAGER=cat command claude --plugin-dir ~/.config/claude/ "$@"
# }

autoclaude() {
  export _AUTOCLAUDE=$$

  # Kill orphaned (PPID=1) processes tagged with our marker.
  # Uses SIGHUP so shells propagate the signal to their children.
  _session_cleanup() {
    local pid
    while IFS= read -r pid; do
      [ -n "$pid" ] || continue
      ps ewww -p "$pid" -o command= 2>/dev/null | grep -qE "_AUTOCLAUDE=${_AUTOCLAUDE}( |$)" || continue
      kill -HUP "$pid" 2>/dev/null
    done < <(pgrep -u "$USER" -P 1 2>/dev/null)
  }

  trap '_session_cleanup; unset _AUTOCLAUDE; trap - INT; kill -INT $$' INT
  trap '_session_cleanup; unset _AUTOCLAUDE; trap - TERM; kill -TERM $$' TERM

  while true; do
    local before_sha signal

    before_sha=$(git rev-parse HEAD 2>/dev/null)

    claude --name "${PWD##*/}" --permission-mode acceptEdits "/run-autopilot"
    _session_cleanup

    signal=$(cat dev/local/autopilot/signal 2>/dev/null)
    rm -f dev/local/autopilot/signal

    if [ "$(git rev-parse HEAD 2>/dev/null)" != "$before_sha" ]; then
      local report
      report=$(ls -t dev/local/autopilot/reports/*-report.md 2>/dev/null | head -1)

      CLEANUP_SINCE="$before_sha" AUTOPILOT_REPORT="$report" \
        claude --name de-sloppify -p "$(cat ~/.claude/skills/run-autopilot/prompts/de-sloppify.md)" \
        --effort high --permission-mode acceptEdits
      _session_cleanup
    fi

    if [ "$signal" != "next" ]; then
      printf '\nBacklog drained.\n'
      trap - INT TERM
      unset _AUTOCLAUDE
      return
    fi

    printf '\nStarting next PRD…\n'
  done
}
