#!/usr/bin/env bash
# Test harness for _autopilot_session_cap (implemented in
# ~/.config/bash/plugins/development.plugin.bash). PRD 00014: the cap is the
# only kill path in the headless loop — a hung `claude -p` child dies at a
# hard wall-clock cap (SIGTERM, then SIGKILL after a grace period). Sources
# the plugin and drives the sidecar against stub `claude` binaries.
set -u

# ── source the plugin (stubs silence the bash-it bootstrap calls) ─────────────
cite() { :; }
about-plugin() { :; }
source ~/.config/bash/plugins/development.plugin.bash

# ── assert helpers ────────────────────────────────────────────────────────────
PASS() { echo "PASS: $1"; }
FAIL() { echo "FAIL: $1 — $2"; exit 1; }

# ── cleanup registry ──────────────────────────────────────────────────────────
_PIDS=()
_DIRS=()

cleanup() {
    local p d
    for p in "${_PIDS[@]+"${_PIDS[@]}"}"; do
        kill -KILL "$p" 2>/dev/null || true
    done
    for d in "${_DIRS[@]+"${_DIRS[@]}"}"; do
        rm -rf "$d"
    done
}
trap cleanup EXIT

# ── guard: the cap function must be defined; the marker machinery must be gone ─
type _autopilot_session_cap >/dev/null 2>&1 \
    || FAIL "function defined: _autopilot_session_cap" "not defined in development.plugin.bash — implement it first"
type _autopilot_loop_yield_stale >/dev/null 2>&1 \
    && FAIL "marker machinery retired" "_autopilot_loop_yield_stale still defined — PRD 00014 deletes it"
type _autopilot_loop_watchdog >/dev/null 2>&1 \
    && FAIL "marker machinery retired" "_autopilot_loop_watchdog still defined — PRD 00014 deletes it"
PASS "cap defined; marker machinery gone"

# ── workspace ─────────────────────────────────────────────────────────────────
WORKDIR=$(mktemp -d)
_DIRS+=("$WORKDIR")
mkdir -p "$WORKDIR/bin" "$WORKDIR/bin2"
cp /bin/sleep "$WORKDIR/bin/claude"   # stub process whose comm is "claude"
# macOS SIGKILLs a copied platform binary (its signature no longer validates); ad-hoc
# re-sign so the stub can exec. codesign is absent on Linux, where the copy runs as-is.
codesign -f -s - "$WORKDIR/bin/claude" 2>/dev/null || true
# bash copies for TERM-immune stubs: comm=claude_immune (must NOT be selected)
# and comm=claude (must be KILL-escalated).
cp /bin/bash "$WORKDIR/bin/claude_immune"
codesign -f -s - "$WORKDIR/bin/claude_immune" 2>/dev/null || true
cp /bin/bash "$WORKDIR/bin2/claude"
codesign -f -s - "$WORKDIR/bin2/claude" 2>/dev/null || true

# =============================================================================
# A. Under the cap: neither target nor bystander is touched
# =============================================================================

"$WORKDIR/bin/claude" 300 &
STUB_A=$!
_PIDS+=($STUB_A)

sleep 300 &
BYSTANDER_A=$!
_PIDS+=($BYSTANDER_A)

# cap 60s, poll 1s — well under the cap for the whole section
_autopilot_session_cap "$$" 60 1 1 &
CAP_A=$!
_PIDS+=($CAP_A)

sleep 3

if kill -0 $STUB_A 2>/dev/null; then
    PASS "under cap: target (claude) not signaled"
else
    FAIL "under cap: target (claude) not signaled" \
         "stub-claude was killed after 3 polls with a 60s cap"
fi

if kill -0 $BYSTANDER_A 2>/dev/null; then
    PASS "under cap: bystander (sleep) not signaled"
else
    FAIL "under cap: bystander (sleep) not signaled" \
         "bystander (comm=sleep) was killed under the cap"
fi

# Kill the target so the sidecar returns, then verify it does return
kill $STUB_A 2>/dev/null || true

( sleep 5; kill $CAP_A 2>/dev/null ) &
SAFETY_A=$!
wait $CAP_A 2>/dev/null || true
kill $SAFETY_A 2>/dev/null; wait $SAFETY_A 2>/dev/null || true

if kill -0 $BYSTANDER_A 2>/dev/null; then
    PASS "sidecar returns when the child dies; bystander still alive"
else
    FAIL "sidecar returns when the child dies; bystander still alive" \
         "bystander was killed when the sidecar returned"
fi

kill $BYSTANDER_A 2>/dev/null || true
wait $BYSTANDER_A 2>/dev/null || true
wait $STUB_A 2>/dev/null || true

# =============================================================================
# B. Over the cap: SIGTERM kills a TERM-obeying child
# =============================================================================

"$WORKDIR/bin/claude" 300 &
STUB_B=$!
_PIDS+=($STUB_B)

sleep 300 &
BYSTANDER_B=$!
_PIDS+=($BYSTANDER_B)

# cap 1s, poll 1s, grace 1s → TERM at first poll past the cap
_autopilot_session_cap "$$" 1 1 1 &
CAP_B=$!

( sleep 15; kill $CAP_B 2>/dev/null ) &
SAFETY_B=$!
wait $CAP_B 2>/dev/null || true
kill $SAFETY_B 2>/dev/null; wait $SAFETY_B 2>/dev/null || true

if ! kill -0 $STUB_B 2>/dev/null; then
    PASS "over cap: target killed by SIGTERM"
else
    FAIL "over cap: target killed by SIGTERM" \
         "stub-claude still alive after the cap fired (cap=1s, poll=1s)"
fi

if kill -0 $BYSTANDER_B 2>/dev/null; then
    PASS "over cap: bystander untouched"
else
    FAIL "over cap: bystander untouched" \
         "bystander (comm=sleep) was killed by the cap"
fi

kill $BYSTANDER_B 2>/dev/null || true
wait $BYSTANDER_B 2>/dev/null || true
wait $STUB_B 2>/dev/null || true

# =============================================================================
# C. comm exact-match contract, then KILL escalation for a TERM-immune target
# =============================================================================

# comm=claude_immune must be invisible to the resolver (exact-match contract):
# with no comm=claude child present the sidecar finds nothing and returns.
"$WORKDIR/bin/claude_immune" -c 'trap "" TERM; while :; do sleep 1; done' &
STUB_C=$!
_PIDS+=($STUB_C)

_autopilot_session_cap "$$" 1 1 1 &
CAP_C0=$!
( sleep 6; kill $CAP_C0 2>/dev/null ) &
SAFETY_C0=$!
wait $CAP_C0 2>/dev/null || true
kill $SAFETY_C0 2>/dev/null; wait $SAFETY_C0 2>/dev/null || true

if kill -0 $STUB_C 2>/dev/null; then
    PASS "comm=claude_immune is not selected (exact-match contract)"
else
    FAIL "comm=claude_immune is not selected (exact-match contract)" \
         "a process whose comm merely contains 'claude' was signaled"
fi
kill -KILL $STUB_C 2>/dev/null || true
wait $STUB_C 2>/dev/null || true

# TERM-immune comm=claude target: TERM ignored → SIGKILL after grace.
"$WORKDIR/bin2/claude" -c 'trap "" TERM; while :; do sleep 1; done' &
STUB_C2=$!
_PIDS+=($STUB_C2)

# cap 1s, poll 1s, grace 2s → TERM ignored → KILL two seconds later
_autopilot_session_cap "$$" 1 1 2 &
CAP_C=$!

( sleep 20; kill $CAP_C 2>/dev/null ) &
SAFETY_C=$!
wait $CAP_C 2>/dev/null || true
kill $SAFETY_C 2>/dev/null; wait $SAFETY_C 2>/dev/null || true

if ! kill -0 $STUB_C2 2>/dev/null; then
    PASS "TERM-immune target: SIGKILL after grace"
else
    FAIL "TERM-immune target: SIGKILL after grace" \
         "TERM-immune stub-claude survived the cap's KILL escalation"
fi

wait $STUB_C2 2>/dev/null || true

# =============================================================================
echo ""
echo "All checks passed."
exit 0
