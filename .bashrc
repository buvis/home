#!/usr/bin/env bash

# If not running interactively, don't do anything
case $- in
*i*) ;;
*) return ;;
esac

# Path to the bash it configuration
export BASH_IT="${DOTFILES_ROOT}/.bash_it"

# Path to custom bash-it aliases, plugins, etc.
export BASH_IT_CUSTOM="${DOTFILES_ROOT}/.config/bash"

# Lock and Load a custom theme file.
# Leave empty to disable theming.
# location /.bash_it/themes/
export BASH_IT_THEME="$DOTFILES_ROOT/.config/bash/themes/powerline-multiline/powerline-multiline.theme.bash"
export POWERLINE_PROMPT_USER_INFO_MODE="sudo"

# (Advanced): Change this to the name of your remote repo if you
# cloned bash-it with a remote other than origin such as `bash-it`.
# export BASH_IT_REMOTE='bash-it'

# (Advanced): Change this to the name of the main development branch if
# you renamed it or if it was changed for some reason
# export BASH_IT_DEVELOPMENT_BRANCH='master'

# Your place for hosting Git repos. I use this for private repos.
export GIT_HOSTING='git@git.domain.com'

# Don't check mail when opening terminal.
unset MAILCHECK

# Change this to your console based IRC client of choice.
export IRC_CLIENT='irssi'

# Set this to the command you use for todo.txt-cli
export TODO="t"

# Set this to false to turn off version control status checking within the prompt for all themes
export SCM_CHECK=true
# Set Xterm/screen/Tmux title with only a short hostname.
# Uncomment this (or set SHORT_HOSTNAME to something else),
# Will otherwise fall back on $HOSTNAME.
#export SHORT_HOSTNAME=$(hostname -s)

# Set Xterm/screen/Tmux title with only a short username.
# Uncomment this (or set SHORT_USER to something else),
# Will otherwise fall back on $USER.
#export SHORT_USER=${USER:0:8}

# Set Xterm/screen/Tmux title with shortened command and directory.
# Uncomment this to set.
export SHORT_TERM_LINE=true

# Set vcprompt executable path for scm advance info in prompt (demula theme)
# https://github.com/djl/vcprompt
#export VCPROMPT_EXECUTABLE=~/.vcprompt/bin/vcprompt

# (Advanced): Uncomment this to make Bash-it reload itself automatically
# after enabling or disabling aliases, plugins, and completions.
export BASH_IT_AUTOMATIC_RELOAD_AFTER_CONFIG_CHANGE=1

# Uncomment this to make Bash-it create alias reload.
# export BASH_IT_RELOAD_LEGACY=1

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
PROMPT_COMMAND="history -a; ${PROMPT_COMMAND:-}"

# Use non-local gateway in faas-cli
export OPENFAAS_URL=https://fn.buvis.net

# Initialize mise shims and autocompletion
eval "$(mise activate bash)"

# Load Bash It
source "$BASH_IT"/bash_it.sh
