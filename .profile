# Detect OS
UNAME_BIN=$(command -v uname)

case $("${UNAME_BIN}" | tr '[:upper:]' '[:lower:]') in
  linux*)
    if [[ $("${UNAME_BIN}" -r) =~ Microsoft ]]; then
        export IS_WSL=true
    else
        export IS_LINUX=true
    fi
    ;;
  darwin*)
    export IS_MAC=true
    ;;
  msys*|cygwin*|mingw*|nt|win*)
    export IS_WIN=true
    ;;
esac

# Determine dotfiles root
#if [[ $IS_WSL ]]; then
    #WINHOME=$(wslvar USERPROFILE)
    #export DOTFILES_ROOT=$(wslpath "${WINHOME}")
#else
    export DOTFILES_ROOT=${HOME}
#fi

export PATH="$DOTFILES_ROOT/.cargo/bin:$PATH"
export PATH="$DOTFILES_ROOT/.yarn/bin:$DOTFILES_ROOT/.config/yarn/global/node_modules/.bin:$PATH"

# Doogat
export DOOGAT_CFG="${DOTFILES_ROOT}/.doogat/config.yml"
export DOO_CFG="${DOTFILES_ROOT}/.doogat/doo.conf.yml"
export PATH="$PATH:${DOTFILES_ROOT}/.local/bin/doogat/pingl:${DOTFILES_ROOT}/.local/bin/doogat/doo"

# My scripts
export PATH="$PATH:${DOTFILES_ROOT}/scripts/bin"

# Avoid ./ to run scripts in current directory
export PATH=$PATH:.

# Support kubectl plugins
export PATH="${PATH}:${DOTFILES_ROOT}/.krew/bin"

# Python wheels
export PATH="${PATH}:${DOTFILES_ROOT}/.local/bin"

# Workaround CFFI lack of python 3.13 support
# ref: https://www.perplexity.ai/search/i-m-unable-to-update-my-python-cd0DHG4uSIGenz37A7nRoQ#0
export PYTHONNOGIL=0

# Set my editor and git editor
export EDITOR="nvim"
export GIT_EDITOR="nvim"

# Use ag for feeding into fzf for searching files.
export FZF_DEFAULT_COMMAND='ag -U --hidden --ignore .git -g ""'

# Color: https://github.com/junegunn/fzf/wiki/Color-schemes - Solarized Dark
# Bind F1 key to toggle preview window on/off
export FZF_DEFAULT_OPTS='--bind "F1:toggle-preview" --preview "rougify {} 2> /dev/null || cat {} 2> /dev/null || tree -C {} 2> /dev/null | head -100" --color dark,hl:33,hl+:37,fg+:235,bg+:136,fg+:254 --color info:254,prompt:37,spinner:108,pointer:235,marker:235'

# Show long commands if needed
# From https://github.com/junegunn/fzf/wiki/Configuring-shell-key-bindings
# Bind F1 key to toggle preview window on/off
export FZF_CTRL_R_OPTS='--bind "F1:toggle-preview" --preview "echo {}" --preview-window down:3:hidden:wrap'

# Fix locale when sshing
export LANG=en_US.UTF-8

# Use brew
if [[ $IS_MAC ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# Prefer GNU utils on Mac
if [[ $IS_MAC ]]; then
   export PATH="/usr/local/opt/grep/libexec/gnubin:$PATH"
   export PATH="/usr/local/opt/coreutils/libexec/gnubin:$PATH"
fi

# Use gpg with ssh
if [[ $IS_MAC ]]; then
   export GPG_TTY=$(tty)
   export SSH_AUTH_SOCK=$(gpgconf --list-dirs agent-ssh-socket)
   gpgconf --launch gpg-agent
fi

# Use rust on Mac
if [[ $IS_MAC ]]; then
    if [[ -f "$HOME/.cargo/env" ]]; then
        . "$HOME/.cargo/env"
    fi
fi
