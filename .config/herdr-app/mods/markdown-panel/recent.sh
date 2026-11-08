#!/bin/sh
# By Johannes Hund (https://github.com/h0ru5), from https://github.com/h0ru5/herdr-md-review. Apache-2.0.
# Markdown files the focused terminal is talking about, best first: the clipboard,
# paths on the terminal's screen and in its history (newest first), and the
# scratchpad of a Claude Code session running in it.
# Usage: recent.sh <hc terminal id>. Prints existing absolute paths, one per line.
t=$1
{
  (wl-paste -n 2>/dev/null || pbpaste 2>/dev/null) | head -c 4096
  echo
  # A path wrapped across screen lines is missed; the scratchpad list covers the usual case.
  [ -n "$t" ] && hc read "$t" 2>/dev/null | grep -oE '(~|/)[^][ "`'"'"'()<>|:]*\.(md|markdown|mdx)' | sed -n '1!G;h;$p'
  pid=$([ -n "$t" ] && hc get "$t" --json 2>/dev/null | python3 -c 'import json,sys; print((json.load(sys.stdin).get("foreground") or {}).get("pid",""))' 2>/dev/null)
  sid=$([ -n "$pid" ] && python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sessionId"])' "$HOME/.claude/sessions/$pid.json" 2>/dev/null)
  [ -n "$sid" ] && ls -t /tmp/claude-"$(id -u)"/*/"$sid"/scratchpad/*.md 2>/dev/null
} | sed "s|^~|$HOME|" | while IFS= read -r p; do
  case $p in /*) [ -f "$p" ] && printf '%s\n' "$p" ;; esac
done | awk '!seen[$0]++' | head -15
