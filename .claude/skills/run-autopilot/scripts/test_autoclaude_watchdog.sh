#!/usr/bin/env bash
# TDD harness for _autopilot_loop_yield_stale and _autopilot_loop_watchdog.
# Both functions are NOT yet implemented; these tests drive their creation and
# will FAIL (with a clear "not defined" message) until the implementation lands
# in ~/.config/bash/plugins/development.plugin.bash.
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
        kill "$p" 2>/dev/null || true
    done
    for d in "${_DIRS[@]+"${_DIRS[@]}"}"; do
        rm -rf "$d"
    done
}
trap cleanup EXIT

# ── guard: both functions must be defined ─────────────────────────────────────
type _autopilot_loop_yield_stale >/dev/null 2>&1 \
    || FAIL "function defined: _autopilot_loop_yield_stale" "not defined in development.plugin.bash — implement it first"
type _autopilot_loop_watchdog >/dev/null 2>&1 \
    || FAIL "function defined: _autopilot_loop_watchdog" "not defined in development.plugin.bash — implement it first"

# ── workspace ─────────────────────────────────────────────────────────────────
WORKDIR=$(mktemp -d)
_DIRS+=("$WORKDIR")
MARKER="$WORKDIR/autopilot.marker"
mkdir -p "$WORKDIR/bin"
cp /bin/sleep "$WORKDIR/bin/claude"   # stub process whose comm ends in "claude"
# macOS SIGKILLs a copied platform binary (its signature no longer validates); ad-hoc
# re-sign so the stub can exec. codesign is absent on Linux, where the copy runs as-is.
codesign -f -s - "$WORKDIR/bin/claude" 2>/dev/null || true

# =============================================================================
# A. _autopilot_loop_yield_stale
# =============================================================================

# A1: marker backdated 30 min — older than 20-min threshold → stale (exit 0)
touch "$MARKER"
touch -t "$(date -v-30M +%Y%m%d%H%M 2>/dev/null || date -d '30 minutes ago' +%Y%m%d%H%M)" "$MARKER"
if _autopilot_loop_yield_stale "$MARKER" 20; then
    PASS "30-min-old marker is stale (exit 0)"
else
    FAIL "30-min-old marker is stale (exit 0)" \
         "function returned non-zero for a file backdated 30 min with a 20-min threshold"
fi
rm -f "$MARKER"

# A2: just-touched marker — newer than threshold → not stale (exit 1)
touch "$MARKER"
if ! _autopilot_loop_yield_stale "$MARKER" 20; then
    PASS "fresh marker is not stale (exit 1)"
else
    FAIL "fresh marker is not stale (exit 1)" \
         "function returned 0 (stale) for a just-touched file"
fi
rm -f "$MARKER"

# A3: absent marker → not stale (exit 1)
if ! _autopilot_loop_yield_stale "$MARKER" 20; then
    PASS "absent marker is not stale (exit 1)"
else
    FAIL "absent marker is not stale (exit 1)" \
         "function returned 0 (stale) for a non-existent file"
fi

# =============================================================================
# B. _autopilot_loop_watchdog: pid targeting — never itself, never bystander
# =============================================================================

# Spawn target (comm = "claude") and bystander (comm = "sleep") as direct
# children of $$ so the watchdog sees them as children of <wrapper_pid>.
"$WORKDIR/bin/claude" 300 &
STUB_B=$!
_PIDS+=($STUB_B)

sleep 300 &
BYSTANDER_B=$!
_PIDS+=($BYSTANDER_B)

# Fresh marker — watchdog must not signal anything
touch "$MARKER"

# Run watchdog in background (it loops until stub-claude dies)
_autopilot_loop_watchdog "$$" "$MARKER" 20 1 5 &
WATCHDOG_B=$!
_PIDS+=($WATCHDOG_B)

# Allow 3 poll intervals with fresh marker; neither process should be touched
sleep 3

if kill -0 $STUB_B 2>/dev/null; then
    PASS "fresh marker: watchdog does not signal target (claude)"
else
    FAIL "fresh marker: watchdog does not signal target (claude)" \
         "stub-claude (comm=claude) was killed after 3 polls with a fresh marker"
fi

if kill -0 $BYSTANDER_B 2>/dev/null; then
    PASS "fresh marker: watchdog does not signal bystander (sleep)"
else
    FAIL "fresh marker: watchdog does not signal bystander (sleep)" \
         "bystander (comm=sleep) was killed after 3 polls with a fresh marker"
fi

# Kill stub-claude so the watchdog returns, then verify bystander still alive
kill $STUB_B 2>/dev/null || true

( sleep 5; kill $WATCHDOG_B 2>/dev/null ) &
SAFETY_B=$!
wait $WATCHDOG_B 2>/dev/null || true
kill $SAFETY_B 2>/dev/null; wait $SAFETY_B 2>/dev/null || true

if kill -0 $BYSTANDER_B 2>/dev/null; then
    PASS "bystander alive after watchdog returns"
else
    FAIL "bystander alive after watchdog returns" \
         "bystander was killed when the watchdog returned after stub-claude died"
fi

# Teardown B
kill $BYSTANDER_B 2>/dev/null || true
wait $BYSTANDER_B 2>/dev/null || true
wait $STUB_B 2>/dev/null || true
rm -f "$MARKER"

# =============================================================================
# C. _autopilot_loop_watchdog: stale marker → child is killed
# =============================================================================

# Pre-age marker (30 min old, threshold 20 min)
touch "$MARKER"
touch -t "$(date -v-30M +%Y%m%d%H%M 2>/dev/null || date -d '30 minutes ago' +%Y%m%d%H%M)" "$MARKER"

# Spawn stub-claude as child of $$
"$WORKDIR/bin/claude" 300 &
STUB_C=$!
_PIDS+=($STUB_C)

# Watchdog: poll=1s, kill_after=2
# Expected: stale detected -> SIGINT; 2 more stale polls -> SIGKILL; child dies; returns
_autopilot_loop_watchdog "$$" "$MARKER" 20 1 2 &
WATCHDOG_C=$!

# Safety: force-kill watchdog at 15s so a buggy implementation cannot hang the suite
( sleep 15; kill $WATCHDOG_C 2>/dev/null ) &
SAFETY_C=$!
wait $WATCHDOG_C 2>/dev/null || true
kill $SAFETY_C 2>/dev/null; wait $SAFETY_C 2>/dev/null || true

if ! kill -0 $STUB_C 2>/dev/null; then
    PASS "stale marker: watchdog kills target"
else
    FAIL "stale marker: watchdog kills target" \
         "stub-claude still alive after watchdog ran with a stale marker (poll=1s, kill_after=2)"
fi

wait $STUB_C 2>/dev/null || true
rm -f "$MARKER"

# =============================================================================
# D. _autopilot_loop_watchdog: no marker → child survives
# =============================================================================

# No marker present — absent is not-stale (proven by A3 above)
"$WORKDIR/bin/claude" 300 &
STUB_D=$!
_PIDS+=($STUB_D)

_autopilot_loop_watchdog "$$" "$MARKER" 20 1 5 &
WATCHDOG_D=$!
_PIDS+=($WATCHDOG_D)

# Allow 3 poll intervals; stub-claude must not be touched
sleep 3

if kill -0 $STUB_D 2>/dev/null; then
    PASS "absent marker: target survives multiple polls"
else
    FAIL "absent marker: target survives multiple polls" \
         "stub-claude was killed despite no marker being present"
fi

# Teardown D — kill stub-claude so watchdog can exit, then wait for both
kill $STUB_D 2>/dev/null || true

( sleep 5; kill $WATCHDOG_D 2>/dev/null ) &
SAFETY_D=$!
wait $WATCHDOG_D 2>/dev/null || true
kill $SAFETY_D 2>/dev/null; wait $SAFETY_D 2>/dev/null || true
wait $STUB_D 2>/dev/null || true

# =============================================================================
echo ""
echo "All checks passed."
exit 0
