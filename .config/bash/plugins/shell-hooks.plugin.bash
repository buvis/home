cite about-plugin
about-plugin 'run scheduled shell hooks once before the first prompt'

# Runs after everything else has loaded, ~/.local/.bashrc included, so
# machine-local PATH entries are visible to the tasks.
function _shell_hooks_once() {
  [[ -n "${_SHELL_HOOKS_DONE:-}" ]] && return 0
  _SHELL_HOOKS_DONE=1
  [[ -x "$HOME/bin/run-shell-hooks" ]] && "$HOME/bin/run-shell-hooks"
}
safe_append_prompt_command _shell_hooks_once
