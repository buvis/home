if ! python3 -m gita &>/dev/null; then
  pip3 install -U gita
fi
alias gita="python3 -m gita"
alias gg="lazygit"
