#!/usr/bin/env bash
# test_autoclaude_agoge_drain.sh — the agoge drain hook in the `autoclaude`
# wrapper (~/.config/bash/plugins/development.plugin.bash).
#
# PRD 00102: a batch that actually drains work fires exactly ONE unattended
# agoge product-QA run over the repo. A batch that drains nothing fires none.
# The run's failure is swallowed — a QA pass must never turn a successful drain
# into a failed one — and it never writes into dev/local/prds/.
#
# The drained-PRD count this hook keys on (`.batch.completed_prds | length`,
# wrapper line ~1004) was previously executed by every done-branch scenario in
# the suite and asserted by none: every other fixture omits `batch.completed_prds`
# entirely, so `_prds_done` was always the empty path. These scenarios seed it
# both ways.
#
# Mirrors test_autoclaude_state_write_failed.sh's sourcing, stubbing and
# run_with_timeout technique — the only driving technique available for this
# wrapper. The `claude` stub records every argv it is handed, so an agoge
# invocation is told apart from a session launch by grep rather than by count.
#
# Run: bash ~/.claude/skills/run-autopilot/scripts/test_autoclaude_agoge_drain.sh
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

# ── global stubs (win over external commands; defined AFTER source) ───────────
export _AUTOPILOT_TRACON=0
sysctl() { echo 1; }                                   # no memory pressure
python3() {
  case "$*" in
    *_walk_up.py*)           printf '%s\n' "$AP_DIR" ;; # resolve ap dir -> sandbox
    *detect_usage_limit.py*) return 1 ;;                # not usage-limited
    *notify.py*)             : ;;                       # swallow notifications
    *purge_devlocal.py*)     : ;;                       # swallow the drained-path purge
    *)                       command python3 "$@" ;;    # real python3 (mtime, render_stream)
  esac
}
_autopilot_session_cap() { :; }                        # no background wall-clock sidecar

# ── run_with_timeout <sandbox_dir> <timeout_secs> ─────────────────────────────
run_with_timeout() {
  local dir="$1" timeout="$2"
  (
    cd "$dir" || exit 90
    AP_DIR="$dir/dev/local/autopilot"
    _AUTOPILOT_LOOPS_DIR="$dir/loops"
    PATH="$dir/bin:$PATH"
    unset _AUTOPILOT_TRACON_CHILD _AUTOPILOT_LOOP
    set +u
    autoclaude
  ) >"$dir/stdout.log" 2>"$dir/stderr.log" &
  local run_pid=$!
  ( sleep "$timeout"; touch "$dir/.timeout-fired"; kill -KILL "$run_pid" 2>/dev/null ) &
  local safety_pid=$!
  _PIDS+=("$run_pid" "$safety_pid")
  wait "$run_pid" 2>/dev/null
  RUN_RC=$?
  kill "$safety_pid" 2>/dev/null
  wait "$safety_pid" 2>/dev/null
}

# ── build_sandbox <completed_prds_json_or_empty> <agoge_exit_code> ────────────
# Seeds a state.json whose first session hands straight to the done branch, and
# a claude stub that logs every argv. `$1` is spliced into state.json as the
# value of batch.completed_prds ('' omits the key entirely, which is what every
# other suite's fixture does).
build_sandbox() {
  local completed="$1" agoge_rc="$2"
  local dir
  dir=$(mktemp -d); _DIRS+=("$dir")
  mkdir -p "$dir/dev/local/autopilot" "$dir/bin" "$dir/dev/local/prds/backlog"

  local batch_json='{"id":"b1"'
  [ -n "$completed" ] && batch_json="$batch_json,\"completed_prds\":$completed"
  batch_json="$batch_json}"
  # An EMPTY next_phase is what the wrapper reads as "backlog drained" — the
  # literal string "done" is a phase that still has work queued after it, and
  # seeding that spins the loop forever.
  printf '%s\n' "{\"prd\":\"00001-x.md\",\"next_phase\":\"\",\"batch\":$batch_json}" \
    >"$dir/dev/local/autopilot/state.json"

  # A pre-existing backlog file, so "prds/ untouched" is a real comparison and
  # not a comparison of two empty listings.
  printf '# untouched\n' >"$dir/dev/local/prds/backlog/00001-pre-existing-v1.md"

  cat >"$dir/bin/claude" <<EOF
#!/usr/bin/env bash
DIR="\$(cd "\$(dirname "\$0")/.." && pwd)"
printf '%s\n' "\$*" >>"\$DIR/claude-argv.log"
case "\$*" in
  */run-agoge*)
    printf '%s\n' "agoge stub ran" >>"\$DIR/agoge-ran.log"
    exit $agoge_rc
    ;;
esac
printf '%s\n' '{"prd":"00001-x.md","next_phase":"","batch":$batch_json}' \\
  >"\$DIR/dev/local/autopilot/state.json"
echo '{"type":"result","subtype":"success","total_cost_usd":0.01,"usage":{"output_tokens":10}}'
exit 0
EOF
  chmod +x "$dir/bin/claude"
  printf '%s\n' "$dir"
}

# `grep -c` prints 0 AND exits 1 on no match, so a `|| echo 0` fallback emits
# the count twice. Capture it, then fall back only when grep could not run.
agoge_calls() {
  local log="$1/claude-argv.log" n=0
  if [ -f "$log" ]; then
    n=$(grep -c -- '/run-agoge' "$log" 2>/dev/null) || n=0
  fi
  printf '%s\n' "$n"
}

# =============================================================================
# Coverage 1 — a batch that drained work fires exactly one agoge run, and the
# run never writes into dev/local/prds/.
# =============================================================================

SBOX_A=$(build_sandbox '["00001-x.md","00002-y.md"]' 0)
prds_before_a=$(cd "$SBOX_A" && find dev/local/prds -type f | sort)

run_with_timeout "$SBOX_A" 20
[ -f "$SBOX_A/.timeout-fired" ] \
  && FAIL "drained batch converges" "loop did not converge within 20s"

[ "$RUN_RC" -eq 0 ] || FAIL "drained batch exits 0" "rc=$RUN_RC"

grep -q "Backlog drained" "$SBOX_A/stdout.log" \
  || FAIL "drained batch reaches the done branch" "stdout: $(cat "$SBOX_A/stdout.log")"

calls_a=$(agoge_calls "$SBOX_A")
[ "$calls_a" -eq 1 ] \
  || FAIL "a drained batch fires exactly one agoge run" \
          "expected 1 /run-agoge invocation, got $calls_a; argv log: $(cat "$SBOX_A/claude-argv.log" 2>/dev/null)"

grep -q -- '--permission-mode auto' "$SBOX_A/claude-argv.log" \
  || FAIL "the agoge run is launched unattended" \
          "argv: $(cat "$SBOX_A/claude-argv.log")"

# PRD 00117: without this flag the runtime-security lane is dark in every
# unattended drain — a fresh profile reads `Authorization: not asserted` and
# recon may not change it. The source must be named, never a bare --authorized:
# an anonymous assertion is one the report cannot attribute to a human act.
grep -q -- '--authorized autoclaude-drain' "$SBOX_A/claude-argv.log" \
  || FAIL "the drain asserts trudy's authorization and names itself as the source" \
          "argv: $(cat "$SBOX_A/claude-argv.log")"

prds_after_a=$(cd "$SBOX_A" && find dev/local/prds -type f | sort)
[ "$prds_before_a" = "$prds_after_a" ] \
  || FAIL "an unattended agoge run writes nothing into dev/local/prds/" \
          "before: $prds_before_a / after: $prds_after_a"

[ -f "$SBOX_A/dev/local/autopilot/reports/b1-agoge.log" ] \
  || FAIL "the run reference is recorded beside the batch's autopilot artifacts" \
          "no b1-agoge.log in $(ls "$SBOX_A/dev/local/autopilot/reports" 2>/dev/null)"

PASS "a drained batch (2 PRDs completed) fires exactly one unattended agoge run, records its log beside the batch artifacts, and writes nothing into dev/local/prds/"

# =============================================================================
# Coverage 2 — a batch that drained nothing fires no run at all, and says so.
# =============================================================================

SBOX_B=$(build_sandbox '[]' 0)

run_with_timeout "$SBOX_B" 20
[ -f "$SBOX_B/.timeout-fired" ] \
  && FAIL "zero-drain batch converges" "loop did not converge within 20s"

[ "$RUN_RC" -eq 0 ] || FAIL "zero-drain batch exits 0" "rc=$RUN_RC"

calls_b=$(agoge_calls "$SBOX_B")
[ "$calls_b" -eq 0 ] \
  || FAIL "a zero-drain batch fires NO agoge run" \
          "expected 0 /run-agoge invocations, got $calls_b"

grep -qi "agoge: skipped" "$SBOX_B/stdout.log" \
  || FAIL "the drain log says the agoge run was skipped" \
          "stdout: $(cat "$SBOX_B/stdout.log")"

PASS "a batch that drained no PRDs fires no agoge run and says so in the drain log"

# =============================================================================
# Coverage 3 — a fixture with no `batch.completed_prds` key at all (the shape
# every other suite seeds) is treated as a zero drain, not as a drained batch.
# =============================================================================

SBOX_C=$(build_sandbox '' 0)

run_with_timeout "$SBOX_C" 20
[ -f "$SBOX_C/.timeout-fired" ] \
  && FAIL "absent-key batch converges" "loop did not converge within 20s"

calls_c=$(agoge_calls "$SBOX_C")
[ "$calls_c" -eq 0 ] \
  || FAIL "an absent completed_prds key fires no agoge run" \
          "expected 0 /run-agoge invocations, got $calls_c"

PASS "a state.json with no batch.completed_prds key fires no agoge run (jq's null is not a drain)"

# =============================================================================
# Coverage 4 — a failing agoge run does not break the drain. This is the whole
# reason the call is last and its status swallowed.
# =============================================================================

SBOX_D=$(build_sandbox '["00001-x.md"]' 7)

run_with_timeout "$SBOX_D" 20
[ -f "$SBOX_D/.timeout-fired" ] \
  && FAIL "failing-agoge batch converges" "loop did not converge within 20s"

[ "$RUN_RC" -eq 0 ] \
  || FAIL "a failing agoge run leaves the drain successful" \
          "drain exited $RUN_RC after the QA run failed"

grep -q "Backlog drained" "$SBOX_D/stdout.log" \
  || FAIL "the drain still reports success" "stdout: $(cat "$SBOX_D/stdout.log")"

grep -qi "agoge: run failed" "$SBOX_D/stderr.log" \
  || FAIL "the failure is reported rather than hidden" \
          "stderr: $(cat "$SBOX_D/stderr.log")"

[ "$(agoge_calls "$SBOX_D")" -eq 1 ] \
  || FAIL "a failing run is not retried" "expected exactly 1 attempt"

PASS "a failing agoge run is reported on stderr, is not retried, and leaves the drain exiting 0"

# =============================================================================
# Coverage 5 — kill switch OFF (_AUTOPILOT_AGOGE_AUTHORIZED=0). Requirement R5:
# every neighbouring knob in the wrapper (_AUTOPILOT_AGOGE_CAP,
# _AUTOPILOT_MODEL_BUILD, _AUTOPILOT_SESSION_MAX) is overridable without
# editing the plugin; --authorized was not. The switch only removes the flag —
# the agoge QA pass itself still runs. Asserting on the bare substring
# '--authorized' (not just the sourced form) closes the gap a bug that swapped
# in an unnamed or differently-sourced assertion would otherwise slip through.
# =============================================================================

SBOX_E=$(build_sandbox '["00001-x.md"]' 0)

export _AUTOPILOT_AGOGE_AUTHORIZED=0
run_with_timeout "$SBOX_E" 20
unset _AUTOPILOT_AGOGE_AUTHORIZED

[ -f "$SBOX_E/.timeout-fired" ] \
  && FAIL "kill-switch-off batch converges" "loop did not converge within 20s"

[ "$RUN_RC" -eq 0 ] || FAIL "kill-switch-off batch exits 0" "rc=$RUN_RC"

calls_e=$(agoge_calls "$SBOX_E")
[ "$calls_e" -eq 1 ] \
  || FAIL "the kill switch does not disable the agoge run itself, only the flag" \
          "expected 1 /run-agoge invocation, got $calls_e; argv log: $(cat "$SBOX_E/claude-argv.log" 2>/dev/null)"

grep -q -- '--authorized' "$SBOX_E/claude-argv.log" \
  && FAIL "_AUTOPILOT_AGOGE_AUTHORIZED=0 removes --authorized entirely, bare or sourced" \
          "argv still carries --authorized: $(cat "$SBOX_E/claude-argv.log")"

PASS "_AUTOPILOT_AGOGE_AUTHORIZED=0 still fires the agoge run once but strips --authorized from its argv completely"

# =============================================================================
# Coverage 6 — kill switch explicitly ON (_AUTOPILOT_AGOGE_AUTHORIZED=1): the
# --authorized autoclaude-drain assertion still fires, named exactly as today.
# Paired with Coverage 5, this makes the pair non-vacuous — the same grep on
# the same argv shape must flip depending only on the variable, so a wrapper
# that always/never emitted the flag could not pass both.
# =============================================================================

SBOX_F=$(build_sandbox '["00001-x.md"]' 0)

export _AUTOPILOT_AGOGE_AUTHORIZED=1
run_with_timeout "$SBOX_F" 20
unset _AUTOPILOT_AGOGE_AUTHORIZED

[ -f "$SBOX_F/.timeout-fired" ] \
  && FAIL "kill-switch-on batch converges" "loop did not converge within 20s"

[ "$RUN_RC" -eq 0 ] || FAIL "kill-switch-on batch exits 0" "rc=$RUN_RC"

calls_f=$(agoge_calls "$SBOX_F")
[ "$calls_f" -eq 1 ] \
  || FAIL "the kill switch left ON still fires the agoge run once" \
          "expected 1 /run-agoge invocation, got $calls_f; argv log: $(cat "$SBOX_F/claude-argv.log" 2>/dev/null)"

grep -q -- '--authorized autoclaude-drain' "$SBOX_F/claude-argv.log" \
  || FAIL "_AUTOPILOT_AGOGE_AUTHORIZED=1 keeps the named assertion unchanged" \
          "argv: $(cat "$SBOX_F/claude-argv.log")"

PASS "_AUTOPILOT_AGOGE_AUTHORIZED=1 leaves --authorized autoclaude-drain in the argv unchanged"

# =============================================================================
echo ""
echo "All checks passed."
exit 0
