#!/usr/bin/env bash
# ~/.codex/notify.sh

# Find script directory for logging (portable across invocations)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/notify.log"

# Source credentials (keep these in a separate file)
source "$SCRIPT_DIR/notify-config.env" 2>/dev/null || {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Failed to source notify-config.env" >> "$LOG_FILE"
  exit 1
}

# Redirect stdout/stderr to log file (keeps TUI clean)
exec >> "$LOG_FILE" 2>&1

# Log entry
echo "────────────────────────────────────────────────────────"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Notification triggered"

# Parse JSON event from Codex
EVENT="$1"
if [[ -z "$EVENT" ]]; then
  echo "ERROR: No event JSON received"
  exit 1
fi

# Debug: Print full event JSON (can be removed after testing)
echo "Full event JSON:"
echo "$EVENT" | jq '.' 2>/dev/null || echo "$EVENT"

# Extract event type
EVENT_TYPE=$(echo "$EVENT" | jq -r '.type // empty')
echo "Event type: $EVENT_TYPE"

# Only process agent-turn-complete events
if [[ "$EVENT_TYPE" != "agent-turn-complete" ]]; then
  echo "Skipping event type: $EVENT_TYPE"
  exit 0
fi

# Extract message details
LAST_MESSAGE=$(echo "$EVENT" | jq -r '."last-assistant-message" // "Turn complete"')

# Try multiple possible field names for the user's input/task
INPUT_MESSAGES=$(echo "$EVENT" | jq -r '
  if (."input-messages" // null) != null and (."input-messages" | length) > 0 then ."input-messages"[0]
  elif (."user-message" // null) != null then ."user-message"
  elif (."last-user-message" // null) != null then ."last-user-message"
  elif (.messages // null) != null then (.messages[] | select(.role == "user") | .content) // .messages[0].content
  elif (.input // null) != null then .input
  else "No task description"
  end
' 2>/dev/null | head -n 1)

echo "Task: ${INPUT_MESSAGES:-No task description}"
echo "Result: ${LAST_MESSAGE:0:100}..." # truncate for log readability

# Send notification to ntfy
HTTP_CODE=$(curl -s -w "%{http_code}" -o /tmp/ntfy-response.txt \
  -X POST "$NTFY_SERVER/$NTFY_TOPIC" \
  -u "$NTFY_USER:$NTFY_PASSWORD" \
  -H "Markdown: yes" \
  -H "Title: Codex wants you" \
  -H "Priority: 3" \
  -H "Tags: pleading_face" \
  -d "**Task**: ${INPUT_MESSAGES}

**Result**: ${LAST_MESSAGE}")

# Log curl outcome
if [[ "$HTTP_CODE" == "200" ]]; then
  echo "✓ Notification sent successfully (HTTP $HTTP_CODE)"
else
  echo "✗ Notification failed (HTTP $HTTP_CODE)"
  echo "Response:"
  cat /tmp/ntfy-response.txt
fi

rm -f /tmp/ntfy-response.txt
exit 0
