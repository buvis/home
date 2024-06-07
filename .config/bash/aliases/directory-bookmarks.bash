# https://stackoverflow.com/questions/7374534/directory-bookmarking-for-bash#comment125072031_30864873
alias cdb='echo ${PWD/#$HOME/\~} >> $DOTFILES_ROOT/.fzfcd; sort -u -o $DOTFILES_ROOT/.fzfcd < $DOTFILES_ROOT/.fzfcd'
alias cdf='target="$(fzf < ~/.fzfcd)" && cd "${target/#\~/$HOME}"'
