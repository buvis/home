#!/usr/bin/env bash

if [[ -f "${HOME}/.profile" ]]; then
  source "${HOME}/.profile"
fi

if [[ -f "${HOME}/.bashrc" ]]; then
  source "${HOME}/.bashrc"
fi

if [[ -f "${HOME}/.local/.bashrc" ]]; then
  source "${HOME}/.local/.bashrc"
fi

# >>> herdr-revive >>>
# Resume the coding agent a herdr terminal lost to a restart or reboot.
# REVIVE_DEBUG=1 says why it did or didn't.
if [ -n "$HC_TERMINAL_ID" ] && [ -f "${HOME}/.config/herdr-app/mods/revive/revive.mjs" ] && command -v node >/dev/null 2>&1; then
  __revive_j="$("${REVIVE_HC:-hc}" get "$HC_TERMINAL_ID" --json 2>/dev/null)"
  case "$__revive_j" in *'"revive.session"'*) __revive_has=1 ;; *) __revive_has= ;; esac
  case "$__revive_j" in *'"pid":'"$$"','*|*'"pid": '"$$"','*) __revive_own=1 ;; *) __revive_own= ;; esac
  if [ -z "$__revive_has" ]; then
    if [ -n "$REVIVE_DEBUG" ]; then echo "revive: nothing remembered on $HC_TERMINAL_ID" >&2; fi
  elif [ -z "$__revive_own" ]; then
    if [ -n "$REVIVE_DEBUG" ]; then echo "revive: not the terminal's own shell" >&2; fi
  else
    if [ -n "$REVIVE_DEBUG" ]; then __revive="$(node "${HOME}/.config/herdr-app/mods/revive/revive.mjs" check --shell $$)"
    else __revive="$(node "${HOME}/.config/herdr-app/mods/revive/revive.mjs" check --shell $$ 2>/dev/null)"; fi
    if [ -z "$__revive" ]; then unset __revive
    elif [ -n "$ZSH_VERSION" ]; then
      __revive_run() { add-zsh-hook -d precmd __revive_run; eval "$__revive"; unset __revive; unfunction __revive_run; }
      autoload -Uz add-zsh-hook && add-zsh-hook precmd __revive_run
    elif [ -n "$BASH_VERSION" ]; then
      __revive_run() { PROMPT_COMMAND="${PROMPT_COMMAND#__revive_run;}"; eval "$__revive"; unset __revive; unset -f __revive_run; }
      PROMPT_COMMAND="__revive_run;${PROMPT_COMMAND}"
    else eval "$__revive"; unset __revive; fi
  fi
  unset __revive_j __revive_has __revive_own
fi
# <<< herdr-revive <<<
