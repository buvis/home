cite about-plugin
about-plugin 'buvis dotfiles management in bare git repo'

alias cfg="/usr/bin/git --git-dir=$HOME/.buvis/ --work-tree=$HOME"
alias cfga="cfg add"
alias cfgapa="cfga -p"
alias cfgm="cfg commit -m"
alias cfgp="cfg push"
alias cfgl="cfg pull && cfg submodule update --init --recursive && cfg submodule update --remote --merge"
alias cfgs="cfg status"
