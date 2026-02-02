#!/usr/bin/env bash
# ~/.claude/hooks/notify.sh
# Reads JSON from stdin and forwards message to ntfy
LOGFILE="$HOME/.claude/hooks/notify.log"
NTFY_CREDENTIALS="$(cat "$HOME/.claude/hooks/.ntfy-secret" 2>/dev/null)"
payload="$(cat)"
event="$(printf '%s' "$payload" | jq -r '.hook_event_name')"
project="$(printf '%s' "$payload" | jq -r '.cwd | split("/") | last')"

# Build meaningful title and message based on event type
case "$event" in
Stop)
  title="Claude [$project]: done"
  msg="Task complete"
  ;;
Notification)
  title="Claude [$project]: waiting"
  msg="$(printf '%s' "$payload" | jq -r '.message // "Awaiting input"')"
  ;;
*)
  title="Claude [$project]: $event"
  msg="$(printf '%s' "$payload" | jq -r '.message // "Event triggered"')"
  ;;
esac

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Hook triggered: $event" >>"$LOGFILE"
echo "$payload" >>"$LOGFILE"

# Check if user is away (lid closed/low angle or screensaver active)
angle=$(uv run --with pybooklid python3 -c "from pybooklid import read_lid_angle; print(int(read_lid_angle()))" 2>/dev/null)
screensaver_active=false
pgrep -q ScreenSaverEngine && screensaver_active=true

should_notify=false
if [ -z "$angle" ] || [ "$angle" -lt 75 ] || [ "$screensaver_active" = true ]; then
  should_notify=true
fi

if [ "$should_notify" = true ]; then
  # Send notification with timeout
  if timeout 10 curl -sS --fail-with-body \
    --connect-timeout 5 -m 8 -u "$NTFY_CREDENTIALS" \
    -H "Title: $title" \
    -H "Tags: computer" \
    --data-raw "$msg" \
    -o /dev/null -w "http=%{http_code} ip=%{remote_ip} t_conn=%{time_connect} t_total=%{time_total}\n" \
    "$NTFY_URL"/"$NTFY_TOPIC" >>"$LOGFILE" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Notification sent successfully" >>"$LOGFILE"
  else
    rc=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Failed to send notification (exit code: $rc)" >>"$LOGFILE"
  fi
else
  # User present - show system notification instead
  ICON_PATH="$HOME/.claude/hooks/claude-icon.icns"
  if command -v terminal-notifier &>/dev/null; then
    terminal-notifier -title "$title" -message "$msg" -contentImage "$ICON_PATH"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] System notification shown (user present)" >>"$LOGFILE"
  else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Skipped: user present, terminal-notifier not available" >>"$LOGFILE"
  fi
fi

echo "---" >>"$LOGFILE"
