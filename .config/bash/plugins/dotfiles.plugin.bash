cite about-plugin
about-plugin 'buvis dotfiles management in bare git repo'

alias cfg="/usr/bin/git --git-dir=$DOTFILES_ROOT/.buvis/ --work-tree=$DOTFILES_ROOT"
alias cfga="cfg add"
alias cfgapa="cfga -p"
alias cfgm="cfg commit -m"
alias cfgp="cfg push"
if [[ $(command -v git-secret) ]]; then
    alias cfgl="cfg pull && cfg submodule foreach git reset --hard && cfg submodule update --init && cfg submodule update --remote --merge; cfg secret reveal -f; rm -f {$DOTFILES_ROOT}/README.md {$DOTFILES_ROOT}/get-buvis.sh {$DOTFILES_ROOT}/get-buvis.bat; cfg update-index --skip-worktree README.md get-buvis.sh get-buvis.bat"
    alias cfgs="cfg secret hide -m; cfg status"
else
    alias cfgl="cfg pull && cfg submodule foreach git reset --hard && cfg submodule update --init && cfg submodule update --remote --merge; rm -f {$DOTFILES_ROOT}/README.md {$DOTFILES_ROOT}/get-buvis.sh {$DOTFILES_ROOT}/get-buvis.bat; cfg update-index --skip-worktree README.md get-buvis.sh get-buvis.bat"
    alias cfgs="cfg status"
fi
