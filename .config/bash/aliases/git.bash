if ! python3 -m gita &>/dev/null; then
  pip3 install -U gita
fi
alias gita="python3 -m gita"

alias gd="git diff"
alias gg="lazygit"
alias gl="git pull"
alias glog="git log --oneline --graph --decorate -20"
alias gp="git push"
alias gst="git status -sb"

alias sync-from-master="git_sync_master"
