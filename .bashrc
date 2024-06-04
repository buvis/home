#!/usr/bin/env bash

# If not running interactively, don't do anything
case $- in
  *i*) ;;
    *) return;;
esac

# Get dotfiles root
export DOTFILES_ROOT="${HOME}"

# Path to the bash it configuration
export BASH_IT="${DOTFILES_ROOT}/.bash_it"

# Path to custom bash-it aliases, plugins, etc.
export BASH_IT_CUSTOM="${DOTFILES_ROOT}/.config/bash"

# Lock and Load a custom theme file.
# Leave empty to disable theming.
# location /.bash_it/themes/
export BASH_IT_THEME='powerline-multiline'
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
# Set to actual location of gitstatus directory if installed
#export SCM_GIT_GITSTATUS_DIR="$DOTFILES_ROOT/gitstatus"
# per default gitstatus uses 2 times as many threads as CPU cores, you can change this here if you must
#export GITSTATUS_NUM_THREADS=8

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

# Use recursive glob
shopt -s globstar

# Use darker background for git status
SCM_THEME_PROMPT_CLEAN_COLOR=${POWERLINE_SCM_CLEAN_COLOR:=22}
SCM_THEME_PROMPT_DIRTY_COLOR=${POWERLINE_SCM_DIRTY_COLOR:=52}
SCM_THEME_PROMPT_STAGED_COLOR=${POWERLINE_SCM_STAGED_COLOR:=24}
SCM_THEME_PROMPT_UNSTAGED_COLOR=${POWERLINE_SCM_UNSTAGED_COLOR:=56}

# Use non-local gateway in faas-cli
export OPENFAAS_URL=https://fn.buvis.net

# Load asdf
source "${DOTFILES_ROOT}/.asdf/asdf.sh"

# Load direnv
eval "$(direnv hook bash)"

# Load p
source "${DOTFILES_ROOT}/.p/p.sh"

# Load Bash It
source "$BASH_IT"/bash_it.sh

# Start with tmux default session
# if [ "$TMUX" = "" ]; then
#     tmux new -As default
# fi

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
