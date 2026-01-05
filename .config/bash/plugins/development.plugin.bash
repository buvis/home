cite about-plugin
about-plugin 'functions for software development'

# start Claude Code working around the bugs
claude() {
  SHELL=/bin/sh command claude --plugin-dir ~/.config/claude/ "$@"
}
