#!/usr/bin/env bash
# PostToolUse hook: log tool usage observations for instinct detection
# Appends JSONL rows to project-scoped observation files

# Skip automated sessions
case "${CLAUDE_SESSION_NAME:-}" in
  *autopilot*|*de-sloppify*) exit 0 ;;
esac

payload="$(cat)"

tool_name="$(printf '%s' "$payload" | jq -r '.tool_name // empty')"
[ -z "$tool_name" ] && exit 0

# Extract structural fields only - strip content to avoid logging sensitive data.
# Detectors need: file_path, command binary, tool name, error messages. Not raw content.
tool_in="$(printf '%s' "$payload" | jq -c '.tool_input // {} | {file_path, path, pattern, command: (.command // "" | split(" ") | .[0])} | with_entries(select(.value != null and .value != ""))')"
tool_out="$(printf '%s' "$payload" | jq -c '.tool_response // "" | tostring | if test("error|Error|ERROR|failed|FAILED|exception|Exception|command not found|No such file|Permission denied") then .[0:500] else "ok" end')"
sid="$(printf '%s' "$payload" | jq -r '.session_id // empty')"

# Detect project identity
proj_hash="global"
proj_name="global"
proj_remote=""

remote="$(git remote get-url origin 2>/dev/null || true)"
if [ -n "$remote" ]; then
  # Strip credentials from URL (user:pass@host -> host)
  clean_remote="$(printf '%s' "$remote" | sed -E 's|://[^@]+@|://|')"
  proj_hash="$(printf '%s' "$clean_remote" | shasum -a 256 | cut -c1-12)"
  proj_name="$(basename -s .git "$remote")"
  proj_remote="$clean_remote"
else
  toplevel="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "$toplevel" ]; then
    proj_hash="$(printf '%s' "$toplevel" | shasum -a 256 | cut -c1-12)"
    proj_name="$(basename "$toplevel")"
  fi
fi

# Ensure project directory exists
proj_dir="$HOME/.claude/instincts/projects/$proj_hash"
mkdir -p "$proj_dir"

obs_file="$proj_dir/observations.jsonl"

# Auto-rotate if file exceeds 5MB
if [ -f "$obs_file" ]; then
  file_size="$(stat -f%z "$obs_file" 2>/dev/null || stat -c%s "$obs_file" 2>/dev/null || echo 0)"
  if [ "$file_size" -gt 5242880 ]; then
    mv "$obs_file" "${obs_file}.1"
  fi
fi

# Append observation (use jq for safe JSON construction)
ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
jq -nc --arg ts "$ts" --arg tool "$tool_name" --arg in "$tool_in" --arg out "$tool_out" --arg sid "$sid" --arg pid "$proj_hash" \
  '{"ts":$ts,"tool":$tool,"in":$in,"out":$out,"sid":$sid,"pid":$pid}' \
  >> "$obs_file"

# Update project registry
registry="$HOME/.claude/instincts/projects.json"
if [ ! -f "$registry" ]; then
  printf '{}' > "$registry"
fi

today="$(date -u '+%Y-%m-%d')"
tmp_reg="$(mktemp)"
jq --arg h "$proj_hash" --arg n "$proj_name" --arg r "$proj_remote" --arg d "$today" \
  '.[$h] = {"name": $n, "remote": $r, "last_seen": $d}' "$registry" > "$tmp_reg"
mv "$tmp_reg" "$registry"

exit 0
