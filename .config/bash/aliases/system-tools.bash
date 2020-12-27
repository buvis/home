if type "bat" &> /dev/null; then
    alias cat="bat --paging never"
fi

if type "lsd" &> /dev/null; then
    alias ls="lsd"
fi

alias l="ls -l"
alias la="ls -a"
alias ll="ls -la"
alias lt="ls --tree"

if hash most 2>/dev/null; then export PAGER="most"; fi

alias ssh="TERM=xterm-256color ssh"

if type "vim" &> /dev/null; then
    alias vi="vim"
fi

alias vifm='vifm ~/Downloads "$(pwd)"'
