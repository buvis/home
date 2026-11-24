#!/usr/bin/env bash

# Claude supplies the reading and the session together. Publish only that pair.
if [[ -n ${HC_TERMINAL_ID:-} ]]; then
    reading=$(jq -r '
        select((.session_id | type) == "string" and (.context_window.remaining_percentage | type) == "number")
        | select((.session_id | test("^[A-Za-z0-9._:-]{1,128}$")) and (.context_window.remaining_percentage >= 0 and .context_window.remaining_percentage <= 100))
        | [.session_id, (.context_window.remaining_percentage | round), (now | floor)] | join("|")
    ') || reading=
    if [[ -n $reading ]]; then
        hc label "$HC_TERMINAL_ID" "herdr.context=$reading" >/dev/null &
    fi
fi

# Keep the existing status line output. Ponytail does not read stdin.
ponytail=$(ls -d "$HOME"/.claude/plugins/cache/ponytail/ponytail/*/hooks/ponytail-statusline.sh 2>/dev/null | sort -V | tail -n1)
if [[ -n $ponytail ]]; then
    exec bash "$ponytail"
fi
