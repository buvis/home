if [[ $(command -v bat) ]]; then alias cat="bat --paging never"; fi

alias ls="ls --color=auto"
alias l="ls -l"
alias la="ls -a"
alias ll="ls -la"
alias lt="ls -lrt"

if [[ $(command -v most) ]]; then export PAGER="most"; fi

if [[ $(command -v nvim) ]]; then alias vim="nvim"; fi

alias ssh="LC_CTYPE=\"en_US.UTF-8\" TERM=xterm-256color ssh"

if [[ $(command -v vim) ]]; then alias vi="vim"; fi

if [[ $(command -v vifm) ]]; then alias vifm='vifm ~/Downloads "$(pwd)"'; fi
