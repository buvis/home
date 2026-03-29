cite about-plugin
about-plugin 'functions for software development'

# start Claude Code working around the bugs
# claude() {
#   SHELL=/bin/sh GIT_PAGER=cat command claude --plugin-dir ~/.config/claude/ "$@"
# }

claude-autopilot() {
  while true; do
    claude "/autopilot"
    signal=$(cat .local/autopilot/signal 2>/dev/null)
    rm -f .local/autopilot/signal

    if [ "$signal" != "next" ]; then
      printf '\nBacklog drained.\n'
      return
    fi

    printf '\nStarting next PRD…\n'
  done
}
