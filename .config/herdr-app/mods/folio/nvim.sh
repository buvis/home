#!/bin/sh
# Replace a preview with Neovim, then restore it after a normal editor exit.
# Closing/killing the terminal intentionally does not reopen the preview.
set -eu
export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"
if [ "${1:-}" = "--check" ]; then
  command -v nvim >/dev/null
  command -v jq >/dev/null
  command -v herdr-app
  exit
fi
file=$1
preview=${2:-}
: "${HC_TERMINAL_ID:?Run this helper in a Herdr terminal}"

own_pane() {
  herdr-app ls | jq -r --arg terminal "$HC_TERMINAL_ID" \
    '[.spaces[].tabs[].terminals[] | select(.terminal == $terminal) | .pane][0] // empty'
}

# The process can start before the app has adopted its terminal into the pane.
attempt=0
pane=$(own_pane)
while [ -z "$pane" ] && [ "$attempt" -lt 50 ]; do
  sleep 0.1
  attempt=$((attempt + 1))
  pane=$(own_pane)
done
[ -n "$pane" ] || { echo "Could not locate the Neovim pane; the preview was kept." >&2; exit 1; }
command -v nvim >/dev/null
if [ -n "$preview" ]; then
  # Removal gives its share to the preceding sibling. Put the replacement first.
  herdr-app do pane.swap --pane "$preview" --target "$pane" >/dev/null
  herdr-app do pane.close --pane "$preview" >/dev/null
fi

nvim -- "$file" || true

# The user might have closed the containing pane/tab while the editor exited.
[ "$(own_pane)" = "$pane" ] || exit 0
args=$(jq -cn --arg pane "$pane" --arg path "$file" \
  '{pane:$pane,direction:"right",mod:"folio",props:{path:$path}}')
replacement=$(herdr-app do pane.split "$args" | jq -er .pane)
herdr-app do pane.swap --pane "$pane" --target "$replacement" >/dev/null
# Exiting removes this terminal pane, leaving the preview in the same region.
