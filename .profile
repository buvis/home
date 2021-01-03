export BUKUSERVER_DB_FILE="/Users/bob/reference/b/bookmark/bookmarks.db"
export PATH="$HOME/.cargo/bin:$PATH"
export PATH="$HOME/.yarn/bin:$HOME/.config/yarn/global/node_modules/.bin:$PATH"

# Doogat
export DOOGAT_CFG="${HOME}/.doogat/config.yml"
export PATH="$PATH:${HOME}/bin/doogat/pingl:${HOME}/bin/doogat/doo"

# My scripts
export PATH="$PATH:${HOME}/bin/script"

# Set my editor and git editor
export EDITOR="vim"
export GIT_EDITOR='vim'

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
