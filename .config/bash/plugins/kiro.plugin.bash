# Bash-it automatically loads this from its custom/plugins directory.
# Preserve Kiro prompt markers when the theme redraws PS1 without a command
# (initial prompt, empty input, or Ctrl-C). Keep the existing Bash-it setup.
_kiro_refresh_prompt() {
    local previous_status=$?
    if [[ ${TERM_PROGRAM:-} == kiro ]] && declare -F __vsc_update_prompt >/dev/null; then
        __vsc_in_command_execution=1
        __vsc_update_prompt
    fi
    return "$previous_status"
}

if [[ ${TERM_PROGRAM:-} == kiro ]] && declare -F safe_append_prompt_command >/dev/null; then
    safe_append_prompt_command _kiro_refresh_prompt
fi
