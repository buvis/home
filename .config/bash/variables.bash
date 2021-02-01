CDPATH=:~/git/src/gitlab.com/doogat
if [[ $(command -v dircolors) ]]; then
    eval $(dircolors $HOME/.config/dircolors/256dark)
fi

# Enable transparent gpg encryption handling in vim through vim-gnupg script
# see: https://github.com/jamessan/vim-gnupg#gpg-agent
export GPG_TTY=$(tty)
