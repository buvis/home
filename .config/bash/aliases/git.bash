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

alias gcp="git_catchup_parent"
alias grc="git_resolve_conflict"

alias gbkp='tar czf ~/git/src-$(date +%Y%m%d).tar.gz -C ~/git src'
