#!/bin/sh
# Installed by the herdr-agent-activity plugin. Safe to delete; it exits
# quietly once the plugin is uninstalled.
ROOT='/Users/bob/.config/herdr/plugins/github/resilient-software.agent-activity-fd7bccc1f2e1'
STATE='/Users/bob/.local/state/herdr/plugins/resilient-software.agent-activity'
NODE='/Users/bob/.local/share/mise/installs/node/latest/bin/node'
[ -x "$NODE" ] || NODE="$(command -v node 2>/dev/null)" || NODE=""
if [ -z "$NODE" ] || [ ! -f "$ROOT/bin/hook.mjs" ]; then cat >/dev/null 2>&1; exit 0; fi
exec "$NODE" "$ROOT/bin/hook.mjs" "$1" --state "$STATE"
