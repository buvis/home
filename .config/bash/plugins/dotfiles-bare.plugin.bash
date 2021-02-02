cite about-plugin
about-plugin 'buvis dotfiles management in bare git repo'

if [[ $(command -v git-secret) ]]; then
    alias cfg="/usr/bin/git --git-dir=$HOME/.buvis/ --work-tree=$HOME"
    alias cfga="cfg secret hide;cfg add"
    alias cfgapa="cfg secret hide;cfga -p"
    alias cfgm="cfg commit -m"
    alias cfgp="cfg push"
    alias cfgl="cfg pull && cfg submodule update --init && cfg submodule update --remote --merge;cfg secret reveal"
    alias cfgs="cfg secret hide;cfg status"
else
    alias cfg="/usr/bin/git --git-dir=$HOME/.buvis/ --work-tree=$HOME"
    alias cfga="cfg add"
    alias cfgapa="cfga -p"
    alias cfgm="cfg commit -m"
    alias cfgp="cfg push"
    alias cfgl="cfg pull && cfg submodule update --init && cfg submodule update --remote --merge"
    alias cfgs="cfg status"
fi
