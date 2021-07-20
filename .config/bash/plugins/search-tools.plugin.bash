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
    [ -n "${selected[0]}" ] && vim "${selected[0]}" "+${selected[1]}"
}
