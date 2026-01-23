#!/usr/bin/env bash
# ~/.claude/hooks/notify.sh
# Reads JSON from stdin and forwards message to ntfy
LOGFILE="$HOME/.claude/hooks/notify.log"
NTFY_CREDENTIALS="$(cat "$HOME/.claude/hooks/.ntfy-secret" 2>/dev/null)"
payload="$(cat)"
msg="$(printf '%s' "$payload" | jq -r '.message // .hook_event_name // "Claude Code event"')"
event="$(printf '%s' "$payload" | jq -r '.hook_event_name')"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Hook triggered: $event" >>"$LOGFILE"
echo "$payload" >>"$LOGFILE"

# Send notification with timeout
if timeout 10 curl -sS --fail-with-body \
  --connect-timeout 5 -m 8 -u "$NTFY_CREDENTIALS" \
  -H "Title: Claude Code - ${event}" \
  -H "Tags: computer" \
  --data-raw "$msg" \
  -o /dev/null -w "http=%{http_code} ip=%{remote_ip} t_conn=%{time_connect} t_total=%{time_total}\n" \
  "$NTFY_URL"/"$NTFY_TOPIC" >>"$LOGFILE" 2>&1; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Notification sent successfully" >>"$LOGFILE"
else
  rc=$?
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Failed to send notification (exit code: $rc)" >>"$LOGFILE"
fi

echo "---" >>"$LOGFILE"
