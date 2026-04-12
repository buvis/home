#!/usr/bin/env bash

# If not running interactively, don't do anything
case $- in
*i*) ;;
*) return ;;
esac

# Fallback for non-login shells that skip .profile
export DOTFILES_ROOT="${DOTFILES_ROOT:-$HOME}"

# Path to the bash it configuration
export BASH_IT="${DOTFILES_ROOT}/.bash_it"

# Path to custom bash-it aliases, plugins, etc.
export BASH_IT_CUSTOM="${DOTFILES_ROOT}/.config/bash"

# Lock and Load a custom theme file.
# Leave empty to disable theming.
# location /.bash_it/themes/
export BASH_IT_THEME="$DOTFILES_ROOT/.config/bash/themes/powerline-multiline/powerline-multiline.theme.bash"
export POWERLINE_PROMPT_USER_INFO_MODE="sudo"

# Set this to false to turn off version control status checking within the prompt for all themes
export SCM_CHECK=true

# Set Xterm/screen/Tmux title with shortened command and directory.
export SHORT_TERM_LINE=true

# (Advanced): Uncomment this to make Bash-it reload itself automatically
# after enabling or disabling aliases, plugins, and completions.
export BASH_IT_AUTOMATIC_RELOAD_AFTER_CONFIG_CHANGE=1

# Set shell options
shopt -s globstar   # Use recursive globbing with **
shopt -s nocaseglob # Case-insensitive globbing
shopt -s cdspell    # Autocorrect typos in cd
shopt -s dirspell   # Autocorrect directory names
shopt -s autocd     # Type directory name to cd into it
shopt -s checkwinsize

# Use darker background for git status
SCM_THEME_PROMPT_CLEAN_COLOR=${POWERLINE_SCM_CLEAN_COLOR:=22}
SCM_THEME_PROMPT_DIRTY_COLOR=${POWERLINE_SCM_DIRTY_COLOR:=52}
SCM_THEME_PROMPT_STAGED_COLOR=${POWERLINE_SCM_STAGED_COLOR:=24}
SCM_THEME_PROMPT_UNSTAGED_COLOR=${POWERLINE_SCM_UNSTAGED_COLOR:=56}

# Optimize history settings
export HISTCONTROL=ignoreboth:erasedups
export HISTFILESIZE=100000
export HISTSIZE=50000
shopt -s histappend
PROMPT_COMMAND="history -a${PROMPT_COMMAND:+;$PROMPT_COMMAND}"

# Support Android development
export ANDROID_NDK_HOME=/opt/homebrew/share/android-ndk
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"

# Use non-local gateway in faas-cli
export OPENFAAS_URL=https://fn.buvis.net

# Initialize mise shims and autocompletion
command -v mise >/dev/null && eval "$(mise activate bash)"

# Initialize smart jumps
command -v zoxide >/dev/null && eval "$(zoxide init --cmd cd bash)"

# Load Bash It
[ -f "$BASH_IT/bash_it.sh" ] && source "$BASH_IT"/bash_it.sh
