#!/usr/bin/env bash
# Stop hook: track per-session token usage and estimated cost
# Reads transcript_path from Stop hook stdin payload, parses token counts,
# calculates cost estimate, appends JSONL row to ~/.claude/metrics/costs.jsonl

payload="$(cat)"
transcript="$(printf '%s' "$payload" | jq -r '.transcript_path // empty')"
sid="$(printf '%s' "$payload" | jq -r '.session_id // empty')"

# Exit silently if no transcript
[ -z "$transcript" ] && exit 0
[ ! -f "$transcript" ] && exit 0

# Extract unique assistant messages (dedup by message.id), sum token usage
# jq reads the JSONL, filters assistant entries, deduplicates, and aggregates
read -r model in_tok cache_create cache_read out_tok <<< "$(
  jq -rs '
    [ .[] | select(.type == "assistant" and .message.usage) ]
    | group_by(.message.id)
    | map(last)
    | {
        model: (map(.message.model // empty) | map(select(. != "")) | last // "unknown"),
        in_tok: (map(.message.usage.input_tokens // 0) | add // 0),
        cache_create: (map(.message.usage.cache_creation_input_tokens // 0) | add // 0),
        cache_read: (map(.message.usage.cache_read_input_tokens // 0) | add // 0),
        out_tok: (map(.message.usage.output_tokens // 0) | add // 0)
      }
    | "\(.model) \(.in_tok) \(.cache_create) \(.cache_read) \(.out_tok)"
  ' "$transcript" 2>/dev/null
)"

# Exit if parsing failed
[ -z "$model" ] && exit 0

# Detect pricing tier from model string (rates per million tokens)
# in_rate = base input, cw_rate = cache write (1.25x), cr_rate = cache read (0.1x)
if [[ "$model" == *haiku* ]]; then
  tier="haiku"
  in_rate="0.80"; cw_rate="1.00"; cr_rate="0.08"; out_rate="4.00"
elif [[ "$model" == *opus* ]]; then
  tier="opus"
  in_rate="15.00"; cw_rate="18.75"; cr_rate="1.50"; out_rate="75.00"
else
  tier="sonnet"
  in_rate="3.00"; cw_rate="3.75"; cr_rate="0.30"; out_rate="15.00"
fi

# Calculate cost in USD (awk for floating point)
cost="$(awk -v in_tok="$in_tok" -v cw="$cache_create" -v cr="$cache_read" -v out="$out_tok" \
  -v in_r="$in_rate" -v cw_r="$cw_rate" -v cr_r="$cr_rate" -v out_r="$out_rate" \
  'BEGIN { printf "%.5f", (in_tok * in_r + cw * cw_r + cr * cr_r + out * out_r) / 1000000 }')"

# Timestamp
ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# Ensure output directory exists
mkdir -p "$HOME/.claude/metrics"

# Append JSONL row with granular token breakdown
printf '{"ts":"%s","sid":"%s","model":"%s","tier":"%s","in":%d,"cache_write":%d,"cache_read":%d,"out":%d,"cost_usd":%s}\n' \
  "$ts" "$sid" "$model" "$tier" "$in_tok" "$cache_create" "$cache_read" "$out_tok" "$cost" \
  >> "$HOME/.claude/metrics/costs.jsonl"

exit 0
