#!/usr/bin/env bash
# Tests for track-cost.sh
set -euo pipefail

HOOK="$HOME/.claude/hooks/track-cost.sh"
TEST_DIR="$(mktemp -d)"
trap 'rm -rf "$TEST_DIR"' EXIT

pass=0
fail=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "  PASS: $label"
    pass=$((pass + 1))
  else
    echo "  FAIL: $label"
    echo "    expected: $expected"
    echo "    actual:   $actual"
    fail=$((fail + 1))
  fi
}

# Create a fixture transcript with known values
# Two messages, one with 2 streaming chunks (same message.id)
cat > "$TEST_DIR/transcript.jsonl" << 'FIXTURE'
{"type":"user","message":{"role":"user","content":"hello"},"uuid":"u1"}
{"type":"assistant","message":{"model":"claude-opus-4-6","id":"msg_001","role":"assistant","content":[{"type":"text","text":"hi"}],"usage":{"input_tokens":100,"cache_creation_input_tokens":200,"cache_read_input_tokens":1000,"output_tokens":50}},"uuid":"a1"}
{"type":"assistant","message":{"model":"claude-opus-4-6","id":"msg_001","role":"assistant","content":[{"type":"text","text":"hi there"}],"usage":{"input_tokens":100,"cache_creation_input_tokens":200,"cache_read_input_tokens":1000,"output_tokens":50}},"uuid":"a2"}
{"type":"assistant","message":{"model":"claude-opus-4-6","id":"msg_002","role":"assistant","content":[{"type":"text","text":"bye"}],"usage":{"input_tokens":500,"cache_creation_input_tokens":0,"cache_read_input_tokens":2000,"output_tokens":100}},"uuid":"a3"}
FIXTURE

# Override HOME so metrics go to temp dir
export HOME="$TEST_DIR"
mkdir -p "$TEST_DIR/.claude/metrics"

echo "=== Test 1: Normal transcript produces correct JSONL ==="
printf '{"session_id":"test-001","transcript_path":"%s/transcript.jsonl","hook_event_name":"Stop"}' "$TEST_DIR" | "$HOOK"
row="$(cat "$TEST_DIR/.claude/metrics/costs.jsonl")"
# After dedup: msg_001 (in=100, cw=200, cr=1000, out=50) + msg_002 (in=500, cw=0, cr=2000, out=100)
# Totals: in=600, cache_write=200, cache_read=3000, out=150
# Opus rates: in=$15, cw=$18.75, cr=$1.50, out=$75
# Cost: (600*15 + 200*18.75 + 3000*1.50 + 150*75) / 1000000 = (9000+3750+4500+11250)/1000000 = 0.02850
assert_eq "sid" "test-001" "$(echo "$row" | jq -r '.sid')"
assert_eq "model" "claude-opus-4-6" "$(echo "$row" | jq -r '.model')"
assert_eq "tier" "opus" "$(echo "$row" | jq -r '.tier')"
assert_eq "in" "600" "$(echo "$row" | jq -r '.in')"
assert_eq "cache_write" "200" "$(echo "$row" | jq -r '.cache_write')"
assert_eq "cache_read" "3000" "$(echo "$row" | jq -r '.cache_read')"
assert_eq "out" "150" "$(echo "$row" | jq -r '.out')"
assert_eq "cost" "0.02850" "$(echo "$row" | jq -r '.cost_usd')"
rm "$TEST_DIR/.claude/metrics/costs.jsonl"

echo "=== Test 2: Empty transcript_path exits silently ==="
printf '{"session_id":"test-002","transcript_path":"","hook_event_name":"Stop"}' | "$HOOK"
if [ ! -f "$TEST_DIR/.claude/metrics/costs.jsonl" ]; then
  echo "  PASS: no row written"
  pass=$((pass + 1))
else
  echo "  FAIL: row was written for empty path"
  fail=$((fail + 1))
fi

echo "=== Test 3: Missing transcript file exits silently ==="
printf '{"session_id":"test-003","transcript_path":"/nonexistent/file.jsonl","hook_event_name":"Stop"}' | "$HOOK"
if [ ! -f "$TEST_DIR/.claude/metrics/costs.jsonl" ]; then
  echo "  PASS: no row written"
  pass=$((pass + 1))
else
  echo "  FAIL: row was written for missing file"
  fail=$((fail + 1))
fi

echo "=== Test 4: Sonnet model detected correctly ==="
cat > "$TEST_DIR/sonnet.jsonl" << 'FIXTURE'
{"type":"assistant","message":{"model":"claude-sonnet-4-6","id":"msg_s1","role":"assistant","content":[{"type":"text","text":"hi"}],"usage":{"input_tokens":1000,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":500}},"uuid":"s1"}
FIXTURE
printf '{"session_id":"test-004","transcript_path":"%s/sonnet.jsonl","hook_event_name":"Stop"}' "$TEST_DIR" | "$HOOK"
row="$(cat "$TEST_DIR/.claude/metrics/costs.jsonl")"
assert_eq "sonnet tier" "sonnet" "$(echo "$row" | jq -r '.tier')"
assert_eq "sonnet model" "claude-sonnet-4-6" "$(echo "$row" | jq -r '.model')"
# Cost: (1000*3 + 500*15) / 1000000 = 10500/1000000 = 0.01050
assert_eq "sonnet cost" "0.01050" "$(echo "$row" | jq -r '.cost_usd')"
rm "$TEST_DIR/.claude/metrics/costs.jsonl"

echo "=== Test 5: Haiku model detected correctly ==="
cat > "$TEST_DIR/haiku.jsonl" << 'FIXTURE'
{"type":"assistant","message":{"model":"claude-haiku-4-5-20251001","id":"msg_h1","role":"assistant","content":[{"type":"text","text":"hi"}],"usage":{"input_tokens":2000,"cache_creation_input_tokens":500,"cache_read_input_tokens":10000,"output_tokens":1000}},"uuid":"h1"}
FIXTURE
printf '{"session_id":"test-005","transcript_path":"%s/haiku.jsonl","hook_event_name":"Stop"}' "$TEST_DIR" | "$HOOK"
row="$(cat "$TEST_DIR/.claude/metrics/costs.jsonl")"
assert_eq "haiku tier" "haiku" "$(echo "$row" | jq -r '.tier')"
assert_eq "haiku model" "claude-haiku-4-5-20251001" "$(echo "$row" | jq -r '.model')"
# Cost: (2000*0.80 + 500*1.00 + 10000*0.08 + 1000*4.00) / 1000000 = (1600+500+800+4000)/1000000 = 0.00690
assert_eq "haiku cost" "0.00690" "$(echo "$row" | jq -r '.cost_usd')"
rm "$TEST_DIR/.claude/metrics/costs.jsonl"

echo "=== Test 6: Aggregation query works ==="
printf '{"session_id":"agg-1","transcript_path":"%s/transcript.jsonl","hook_event_name":"Stop"}' "$TEST_DIR" | "$HOOK"
printf '{"session_id":"agg-2","transcript_path":"%s/sonnet.jsonl","hook_event_name":"Stop"}' "$TEST_DIR" | "$HOOK"
total="$(jq -s 'map(.cost_usd) | add' "$TEST_DIR/.claude/metrics/costs.jsonl")"
assert_eq "aggregation" "0.039" "$total"

echo ""
echo "Results: $pass passed, $fail failed"
[ "$fail" -eq 0 ] && exit 0 || exit 1
