cite about-plugin
about-plugin 'advanced tools for searching'

# start interactive ripgrep in fzf and open the selected file in vim
function fe () {
    FILE_TO_EDIT=$(
    INITIAL_QUERY=""
    RG_PREFIX="rg --files-with-matches --color=always --smart-case "
    FZF_DEFAULT_COMMAND="$RG_PREFIX '$INITIAL_QUERY'" \
    fzf --bind "change:reload:$RG_PREFIX {q} || true" \
        --ansi --disabled --query "$INITIAL_QUERY" \
        --height=50% --layout=reverse \
        --preview 'bat --style numbers,changes --color=always --line-range=:500 {}'
    )
    [[ -f "$FILE_TO_EDIT" ]] && vim "$FILE_TO_EDIT"
}

# search with ripgrep interactively in fzf and open selected files in vim
function rfv () {
    RG_PREFIX="rg --column --line-number --no-heading --color=always --smart-case "
    INITIAL_QUERY="${*:-}"
    IFS=: read -ra selected < <(
    FZF_DEFAULT_COMMAND="$RG_PREFIX $(printf %q "$INITIAL_QUERY")" \
    fzf --ansi \
        --disabled --query "$INITIAL_QUERY" \
        --bind "change:reload:sleep 0.1; $RG_PREFIX {q} || true" \
        --delimiter : \
        --preview 'bat --color=always {1} --highlight-line {2}' \
        --preview-window 'up,60%,border-bottom,+{2}+3/3,~3'
    )
    [[ -n "${selected[0]}" ]] && vim "${selected[0]}" "+${selected[1]}"
}

# checkout a git branch (local or remote), most recently committed first
# a remote branch checks out as a local tracking branch
function fbr () {
    local target
    target=$(
    git for-each-ref --sort=-committerdate refs/heads refs/remotes \
        --format=$'%(refname:short)\t%(refname)' |
    awk -F'\t' '$2 !~ /\/HEAD$/ { n = $2; sub(/^refs\/(heads|remotes\/[^\/]+)\//, "", n); if (!seen[n]++) print $1 "\t" n }' |
    fzf --delimiter=$'\t' --with-nth=1 --no-multi --height=40% --reverse |
    cut -f2
    ) || return
    [[ -n "$target" ]] && git checkout "$target"
}

# checkout a git branch or tag, previewing the commits between it and HEAD
# (from the fzf wiki examples, fco_preview)
function fco () {
    local tags branches target
    branches=$(
        git --no-pager branch --all \
            --format="%(if)%(HEAD)%(then)%(else)%(if:equals=HEAD)%(refname:strip=3)%(then)%(else)%1B[0;34;1mbranch%09%1B[m%(refname:short)%(end)%(end)" \
        | sed '/^$/d') || return
    tags=$(
        git --no-pager tag | awk '{print "\x1b[35;1mtag\x1b[m\t" $1}') || return
    target=$(
        (echo "$branches"; echo "$tags") |
        fzf --no-hscroll --no-multi -n 2 \
            --ansi --preview="git --no-pager log -150 --pretty=format:%s '..{2}'") || return
    git checkout "$(awk '{print $2}' <<<"$target")"
}

# kill processes picked in fzf (your own, or all as root); signal defaults to TERM
function fkill () {
    local pid
    if [[ "$UID" != 0 ]]; then
        pid=$(ps -f -u "$UID" | sed 1d | fzf -m | awk '{print $2}')
    else
        pid=$(ps -ef | sed 1d | fzf -m | awk '{print $2}')
    fi
    [[ -n "$pid" ]] && echo "$pid" | xargs kill -"${1:-15}"
}
