#!/usr/bin/env bash
# test_autoclaude_fable_subcommands.sh — the operator's one-command decision on a
# pending Fable rescue (~/.config/bash/plugins/development.plugin.bash).
#
# Under test:
#   1. the subcommand guard, the FIRST statement inside autoclaude():
#        case "${1:-}" in
#          approve-fable|reject-fable) _autopilot_fable_decide "$1" "${2:-}"; return $? ;;
#        esac
#      It must route both subcommands to the helper and return BEFORE the tracon
#      branch (so neither subcommand ever starts or attaches to a loop), and it
#      must leave a bare `autoclaude` call untouched.
#   2. _autopilot_fable_decide <approve-fable|reject-fable> <prd>, which resolves
#      the autopilot dir with _walk_up.py, delegates the ledger write to
#      fablectl.py (it never edits the ledger itself), and — for approve only —
#      un-parks the PRD with mv dev/local/prds/hold/<prd> -> …/backlog/<prd>.
#      Exit 0 on success, exit 2 with a one-line stderr message on an empty <prd>
#      or a fablectl refusal.
#
# Technique: every scenario runs inside a throwaway mktemp sandbox laid out like
# a repo (dev/local/autopilot/ledger, dev/local/prds/{hold,backlog}, bin/), with
# cwd pointed at it, so the real ~/.claude dev/local tree, the real ledger and
# the real PRD folders are never touched. python3 is stubbed for *_walk_up.py*
# (it answers the sandbox's autopilot dir); every other python3 call falls
# through to the real interpreter, so the REAL fablectl.py runs — ledger fixtures
# are built with `fablectl.py … request …` and read back with `fablectl.py … show
# …`, so they cannot drift from the real schema.
#
# The sandbox hands the implementation NOTHING it is supposed to derive. The
# harness's own path variable is `_STUB_AP_DIR` (a name no implementation would
# read), and run_sandboxed unsets every other suite global that names a sandbox
# path, the ledger or a PRD before calling the function under test. So the only
# route to the autopilot dir is the _walk_up.py resolver, and the only route to
# the ledger is <ap_dir>/ledger/. An earlier revision exported `AP_DIR` here,
# which handed the answer over for free and made the resolver optional.
#
# THREE RECORDERS make invisible obligations visible; each is proven non-vacuous
# by a loud pre-flight before anything depends on it:
#   - `claude` on PATH records every invocation, so each subcommand scenario can
#     prove no loop session was launched;
#   - `_autoclaude_tracon` records its invocation, so the guard's position
#     (before the tracon branch) is pinned rather than assumed (scenario 15);
#   - the python3 stub records *_walk_up.py* and *fablectl.py*decide* calls, so
#     "the autopilot dir was resolved, not guessed" and "fablectl did the ledger
#     write" are asserted rather than hoped for. The fablectl arm records and
#     then falls through to the REAL interpreter — it observes, it never
#     substitutes.
#
# Every write scenario seeds a SECOND, unrelated `requested` entry and asserts it
# is still `requested` with an empty decided_at afterwards: a whole-file rewrite
# (`sed s/requested/approved/g`) is then not a passing implementation, only a
# per-PRD transition is.
#
# Wrong implementations this suite must catch:
#   - a helper that ignores its first argument and always approves  -> scenario 2
#   - a helper that flips the ledger status but never moves the PRD -> scenario 1
#   - a helper that moves the PRD but returns 0 on a refusal        -> scenarios 3, 4
#   - a guard that swallows a bare `autoclaude` call                -> scenario 7
#   - a helper that returns 0 after a failed un-park, or that rolls
#     the ledger status back                                        -> scenarios 8, 13
#   - a helper that rewrites the whole ledger instead of one entry  -> scenarios 1, 2, 6, 8, 9
#   - a helper that hardcodes decided_at                            -> scenarios 1, 6, 8 (bounded stamp)
#   - a helper that answers every refusal with one canned sentence  -> scenarios 4, 10, 11
#   - a helper that treats "the ledger mentions approved" as the
#     state of THIS PRD                                             -> scenario 9
#   - a helper that hardcodes relative paths instead of resolving
#     the autopilot dir with _walk_up.py                            -> every
#     assert_walkup_called (scenario 1 first), then scenario 12
#   - a helper whose un-park decides from a `[ -w backlog ]` probe
#     instead of checking that the move landed                      -> scenario 13
#   - a usage line that hardcodes `approve-fable`                   -> scenario 14
#   - a guard placed AFTER the tracon branch                        -> scenario 15
#   - a helper that edits the ledger itself (sed/jq) instead of
#     delegating the write to fablectl.py                           -> every
#     assert_fablectl_wrote (scenario 1 first)
#   - a helper that reports a NEIGHBOUR's status as this PRD's in a
#     refusal ("grep the file for approved, else rejected")         -> scenarios 16, 17
#   - a helper that trusts `mv`'s exit code instead of checking the
#     PRD arrived at backlog/<prd>                                  -> scenario 18
#   - a helper that reports an unreadable ledger as "no request"    -> scenario 19
#
# Run: bash ~/.claude/skills/run-autopilot/scripts/test_autoclaude_fable_subcommands.sh
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FABLECTL="$SCRIPT_DIR/fablectl.py"
[ -f "$FABLECTL" ] || { echo "FAIL: preflight — fablectl.py not found at $FABLECTL"; exit 1; }

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

# The wrapper's loop registry. It lives OUTSIDE every sandbox on purpose: the
# wrapper exports _AUTOPILOT_LOOPS_DIR, so an implementation could otherwise
# strip the suffix off it and reach the repo root without ever resolving
# anything. In production this variable points into ~/.claude and says nothing
# about the repo, so pointing it at an unrelated temp dir is the faithful shape.
# Sharing one dir across scenarios is safe: the registry is keyed by pid and
# root, pruned of dead pids on entry, and each sandbox is a different root.
_STUB_LOOPS_DIR=$(mktemp -d)
_DIRS+=("$_STUB_LOOPS_DIR")

# ── global stubs (win over external commands; defined AFTER source) ───────────
# Never let a scenario touch the real machine: no memory-pressure wait, no real
# notifications/purges, no tracon TUI. The python3 stub redirects ONLY the
# autopilot-dir resolution into the sandbox; the fall-through arm matters, since
# the helper under test calls python3 for fablectl.py as well.
export _AUTOPILOT_TRACON=0
sysctl() { echo 1; }                                   # no memory pressure

# The tracon front-end, replaced by a RECORDER: it never launches a TUI, it just
# writes proof that the tracon branch was reached and returns 0. Scenario 15 runs
# a subcommand with _AUTOPILOT_TRACON=1 and asserts this file was never created,
# which is the only way to pin "the guard is the FIRST statement in autoclaude()"
# — with the global _AUTOPILOT_TRACON=0 alone, a guard placed AFTER the tracon
# branch would pass unnoticed.
_autoclaude_tracon() {
  printf 'tracon %s\n' "$*" >>"${_STUB_AP_DIR:-$PWD}/tracon-invocations.log"
  return 0
}
# $_STUB_AP_DIR is deliberately named so that no plausible implementation reads
# it; run_sandboxed sets it, and only this stub consumes it.
python3() {
  case "$*" in
    *_walk_up.py*)
      # RECORDER, then the answer. An implementation that hardcodes a relative
      # `dev/local/autopilot`, or that lifts a path out of the environment,
      # produces the right ledger from the repo root and never lands here — so
      # assert_walkup_called is the only assertion that can tell them apart.
      printf 'walk_up %s\n' "$*" >>"$_STUB_AP_DIR/walkup-invocations.log"
      printf '%s\n' "$_STUB_AP_DIR" ;;                  # resolve ap dir -> sandbox
    *fablectl.py*decide*)
      # RECORDER, then the REAL interpreter. fablectl.py must be the sole writer
      # of the ledger; a hand-rolled sed/jq edit satisfies every status and
      # bystander assertion in this suite, and only this log says who wrote.
      # The recorder observes — the real fablectl still does all the work.
      printf 'fablectl %s\n' "$*" >>"$_STUB_AP_DIR/fablectl-invocations.log"
      command python3 "$@" ;;
    *detect_usage_limit.py*) return 1 ;;                # not usage-limited
    *notify.py*)             : ;;                       # swallow notifications
    *purge_devlocal.py*)     : ;;                       # swallow the drained-path purge
    *)                       command python3 "$@" ;;    # real python3 (incl. fablectl show)
  esac
}

PRD="00076-fable-rescue.md"
# The unrelated entry every write scenario seeds beside $PRD. It is never named
# on any command line, so ANY change to it proves the write was not scoped.
BYSTANDER="00099-unrelated-bystander.md"
SENTINEL="# the parked PRD body — must survive the un-park move verbatim"

# Per-run knobs consumed by run_sandboxed (reset by every runner call).
RUN_SUBDIR=""     # relative dir inside the sandbox to run from ("" = repo root)
TRACON_MODE=0     # value exported as _AUTOPILOT_TRACON inside the sandbox

# ── sandbox construction ──────────────────────────────────────────────────────
# write_recording_claude <dir> — a `claude` that logs every invocation AND writes
# a terminal state.json. The log lets a subcommand scenario prove no session was
# launched; the terminal state means that if the guard were MISSING, the loop
# that wrongly starts still converges (and is caught) instead of hanging.
write_recording_claude() {
  local dir="$1"
  cat >"$dir/bin/claude" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
printf 'claude %s\n' "$*" >>"$DIR/claude-invocations.log"
printf '%s\n' '{"prd":"00001-x.md","next_phase":""}' >"$DIR/dev/local/autopilot/state.json"
echo '{"type":"result","subtype":"success","total_cost_usd":0.01,"usage":{"output_tokens":10}}'
exit 0
EOF
  chmod +x "$dir/bin/claude"
}

# make_sandbox — sets $SBOX to a fresh repo-shaped sandbox and registers it for
# cleanup. LEDGER is the ledger path the helper must derive:
# <ap_dir>/ledger/fable-requests.json.
make_sandbox() {
  SBOX=$(mktemp -d)
  _DIRS+=("$SBOX")
  mkdir -p "$SBOX/dev/local/autopilot/ledger" \
           "$SBOX/dev/local/prds/hold" \
           "$SBOX/dev/local/prds/backlog" \
           "$SBOX/bin"
  write_recording_claude "$SBOX"
  LEDGER="$SBOX/dev/local/autopilot/ledger/fable-requests.json"
}

# park_prd <dir> <hold|backlog> — drop the PRD fixture in that folder.
park_prd() {
  printf '%s\n' "$SENTINEL" >"$1/dev/local/prds/$2/$PRD"
}

# seed_request <ledger> <prd> — build the ledger fixture with the REAL fablectl,
# so the on-disk schema is whatever production writes.
seed_request() {
  command python3 "$FABLECTL" "$1" request "$2" 5 "wire the rescue" batch-r1 \
    '{"problem":"model stalled on the same task","attempts":"three reworks, same failure","impact":"batch blocked"}' \
    || FAIL "fixture setup" "fablectl request failed for $2"
}

# seed_decision <ledger> <prd> <approved|rejected> — advance the fixture past
# `requested` with the real writer.
seed_decision() {
  command python3 "$FABLECTL" "$1" decide "$2" "$3" \
    || FAIL "fixture setup" "fablectl decide $3 failed for $2"
}

# ── ledger readback (real fablectl show, then a JSON parse — never regex) ─────
# ledger_field <ledger> <prd> <field> — prints the field, or "" when the entry or
# the field is absent/null.
ledger_field() {
  local shown
  shown=$(command python3 "$FABLECTL" "$1" show "$2") \
    || FAIL "ledger readback" "fablectl show failed for $2 in $1"
  printf '%s' "$shown" | command python3 -c \
    'import json,sys; v=json.load(sys.stdin).get(sys.argv[1]); print("" if v is None else v)' "$3"
}

# ── runners ───────────────────────────────────────────────────────────────────
# run_sandboxed <dir> <timeout> <entry> [args…] — runs <entry> inside <dir>
# (cwd + PATH pointed at the sandbox), backgrounded under a safety-kill so a
# missing or broken implementation is force-killed rather than hanging the suite.
# stdout/stderr land in <dir>/{stdout,stderr}.log; the exit code lands in
# $RUN_RC. If the safety-kill fired, <dir>/.timeout-fired exists.
#
# $RUN_SUBDIR moves cwd into a SUBDIRECTORY of the sandbox, which is what makes
# the _walk_up.py resolution load-bearing: from dev/local/prds/ a hardcoded
# relative `dev/local/…` path resolves to nothing. $TRACON_MODE sets
# _AUTOPILOT_TRACON for this run only. Both are reset after every call, so one
# scenario can never leak its knob into the next.
#
# NOTHING in scope may spell out an answer the implementation is supposed to
# derive. The sandbox path lives in `_STUB_AP_DIR` (read only by the python3
# stub), every local of this function is `_rs_`-prefixed, and every suite global
# holding a sandbox path, the ledger path or a PRD filename is unset before the
# entry point runs. Bash's dynamic scoping means a plain `local dir=` here, or a
# global named `LEDGER`, is readable by the function under test — which is
# exactly how an implementation can skip the resolver and still pass.
run_sandboxed() {
  local _rs_dir="$1" _rs_timeout="$2"
  shift 2
  (
    cd "$_rs_dir${RUN_SUBDIR:+/$RUN_SUBDIR}" || exit 90
    _STUB_AP_DIR="$_rs_dir/dev/local/autopilot"
    export _AUTOPILOT_TRACON="$TRACON_MODE"
    _AUTOPILOT_LOOPS_DIR="$_STUB_LOOPS_DIR"
    PATH="$_rs_dir/bin:$PATH"
    # This suite may itself run from inside an autoclaude loop, which exports
    # _AUTOPILOT_TRACON_CHILD and _AUTOPILOT_LOOP into every subshell; an
    # inherited _AUTOPILOT_TRACON_CHILD trips the sandboxed wrapper's pgrp
    # self-guard. Strip both so the sandbox runs clean.
    unset _AUTOPILOT_TRACON_CHILD _AUTOPILOT_LOOP
    # The wrapper targets a normal interactive shell (no set -u); the suite's own
    # `set -u` would trip pre-existing unguarded expansions inside autoclaude.
    # It is relaxed BEFORE the prefix expansions below, which have no matches to
    # expand once the suite is still on its first scenario.
    set +u
    # Strip the harness's own vocabulary (see the comment above). AP_DIR is in
    # the list because it used to be the leak; nothing sets it any more, and
    # unsetting it keeps an inherited one from the operator's shell out too.
    unset AP_DIR SCRIPT_DIR FABLECTL SBOX LEDGER PRD BYSTANDER SENTINEL \
          OTHER_PRD NEIGHBOUR_PRD REJECTED_NEIGHBOUR_PRD NEIGHBOUR_DECIDED_AT \
          TRACON_RECORDER USAGE_LINE TS_BEFORE TS_AFTER RUN_RC RUN_SUBDIR \
          TRACON_MODE PF_RC _rs_dir _rs_timeout _rs_d _STUB_LOOPS_DIR \
          _DIRS _PIDS
    unset "${!SBOX_@}" "${!LEDGER_@}"
    "$@"
  ) >"$_rs_dir/stdout.log" 2>"$_rs_dir/stderr.log" &
  local _rs_run_pid=$!
  ( sleep "$_rs_timeout"; touch "$_rs_dir/.timeout-fired"; kill -KILL "$_rs_run_pid" 2>/dev/null ) &
  local _rs_safety_pid=$!
  _PIDS+=("$_rs_run_pid" "$_rs_safety_pid")
  wait "$_rs_run_pid" 2>/dev/null
  RUN_RC=$?
  kill "$_rs_safety_pid" 2>/dev/null
  wait "$_rs_safety_pid" 2>/dev/null
  RUN_SUBDIR=""
  TRACON_MODE=0
}

# run_helper <dir> [args…] — drive _autopilot_fable_decide directly (positional
# args only; it must not depend on loop-local variables).
run_helper() { local _rs_d="$1"; shift; run_sandboxed "$_rs_d" 20 _autopilot_fable_decide "$@"; }

# run_autoclaude <dir> [args…] — drive the real entry point, exercising the guard.
run_autoclaude() { local _rs_d="$1"; shift; run_sandboxed "$_rs_d" 20 autoclaude "$@"; }

# ── shared assertions ─────────────────────────────────────────────────────────
assert_no_timeout() {
  [ -f "$2/.timeout-fired" ] && FAIL "$1" "safety timeout — the call never returned"
  return 0
}

assert_rc() {  # <label> <dir> <expected>
  [ "$RUN_RC" -eq "$3" ] \
    || FAIL "$1" "expected exit $3, got $RUN_RC; stdout=$(cat "$2/stdout.log" 2>/dev/null); stderr=$(cat "$2/stderr.log" 2>/dev/null)"
}

assert_status() {  # <label> <ledger> <prd> <expected>
  local got
  got=$(ledger_field "$2" "$3" status)
  [ "$got" = "$4" ] || FAIL "$1" "ledger status for $3 is '$got', expected '$4'"
}

# utc_now — the same instant, in the same format fablectl stamps
# (%Y-%m-%dT%H:%M:%SZ). That format sorts lexicographically, so a string compare
# IS a time compare.
utc_now() {
  command python3 -c \
    'import datetime; print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))'
}

# assert_decided_at_between <label> <ledger> <prd> <before> <after> — the stamp
# must fall inside the window the run actually occupied. Checking only "not
# empty" would accept a hardcoded literal (the failure this replaces); bounding
# it on BOTH sides rejects both a frozen past constant and a frozen future one.
assert_decided_at_between() {
  local got
  got=$(ledger_field "$2" "$3" decided_at)
  [ -n "$got" ] || FAIL "$1" "decided_at is unset for $3"
  [ "$got" \< "$4" ] \
    && FAIL "$1" "decided_at for $3 is '$got', before the run started ($4) — that is a hardcoded stamp, not a real one"
  [ "$got" \> "$5" ] \
    && FAIL "$1" "decided_at for $3 is '$got', after the run ended ($5) — that is a hardcoded stamp, not a real one"
  return 0
}

# assert_bystander_untouched <label> <ledger> — the unrelated `requested` entry
# seeded beside the PRD under test must come through completely untouched. This
# is what separates a per-PRD transition from a whole-file rewrite.
assert_bystander_untouched() {
  local st da
  st=$(ledger_field "$2" "$BYSTANDER" status)
  [ "$st" = requested ] \
    || FAIL "$1" "the unrelated entry $BYSTANDER is now '$st', expected 'requested' — the write hit the whole ledger, not one PRD"
  da=$(ledger_field "$2" "$BYSTANDER" decided_at)
  [ -z "$da" ] \
    || FAIL "$1" "the unrelated entry $BYSTANDER now carries decided_at='$da' — the write hit the whole ledger, not one PRD"
}

assert_in_dir() {  # <label> <dir> <hold|backlog>
  local path="$2/dev/local/prds/$3/$PRD"
  [ -f "$path" ] || FAIL "$1" "PRD is not in $3/ (expected $path)"
  [ "$(cat "$path")" = "$SENTINEL" ] || FAIL "$1" "the file in $3/ is not the original PRD (body changed)"
}

assert_not_in_dir() {  # <label> <dir> <hold|backlog>
  [ -e "$2/dev/local/prds/$3/$PRD" ] && FAIL "$1" "PRD is still present in $3/"
  return 0
}

assert_ledger_unchanged() {  # <label> <dir> <ledger>
  cmp -s "$2/ledger.expected" "$3" \
    || FAIL "$1" "ledger was mutated; before=$(cat "$2/ledger.expected" 2>/dev/null); after=$(cat "$3" 2>/dev/null)"
}

assert_no_loop() {  # <label> <dir>
  if [ -f "$2/claude-invocations.log" ]; then
    FAIL "$1" "a loop session was launched: $(cat "$2/claude-invocations.log")"
  fi
  PASS "$1"
}

assert_one_line() {  # <label> <logfile>
  local n
  n=$(grep -c . "$2" 2>/dev/null)
  [ "${n:-0}" -eq 1 ] || FAIL "$1" "expected exactly one non-blank line, got ${n:-0}: $(cat "$2" 2>/dev/null)"
}

assert_mentions() {  # <label> <logfile> <needle>
  grep -qiF -- "$3" "$2" || FAIL "$1" "output does not mention '$3': $(cat "$2" 2>/dev/null)"
}

assert_not_mentions() {  # <label> <logfile> <needle>
  grep -qiF -- "$3" "$2" \
    && FAIL "$1" "output wrongly claims '$3': $(cat "$2" 2>/dev/null)"
  return 0
}

# assert_matches <label> <logfile> <extended-regex> <what-it-should-say> — for
# signals the contract pins by MEANING, not by sentence. Keep these regexes wide
# enough to accept any honest wording and narrow enough to reject a canned
# all-purpose refusal.
assert_matches() {
  grep -qiE -- "$3" "$2" \
    || FAIL "$1" "$4 — got: $(cat "$2" 2>/dev/null)"
}

# assert_not_matches <label> <logfile> <extended-regex> <what-it-must-not-say> —
# the mirror, for claims that are wrong by MEANING however they are worded.
assert_not_matches() {
  grep -qiE -- "$3" "$2" \
    && FAIL "$1" "$4 — got: $(cat "$2" 2>/dev/null)"
  return 0
}

# assert_walkup_called <label> <dir> — the autopilot dir was RESOLVED by running
# _walk_up.py, not guessed. Every functional assertion in this suite is satisfied
# by a hardcoded relative `dev/local/autopilot` as long as cwd happens to be the
# repo root, and by an environment lookup no matter where cwd is; this is the
# only assertion that separates "derived it" from "got lucky".
assert_walkup_called() {
  [ -f "$2/dev/local/autopilot/walkup-invocations.log" ] \
    || FAIL "$1" "_walk_up.py was never invoked — the autopilot dir was guessed, not resolved"
}

# assert_fablectl_wrote <label> <dir> — the ledger transition went through
# `fablectl.py … decide …`. A sed range over the pretty-printed ledger, or a jq
# rewrite, satisfies the status, decided_at and bystander assertions exactly as
# well; only this log names the writer. The contract is that the helper never
# edits the ledger itself.
assert_fablectl_wrote() {
  [ -f "$2/dev/local/autopilot/fablectl-invocations.log" ] \
    || FAIL "$1" "fablectl.py decide was never invoked — the helper wrote the ledger itself"
}

# =============================================================================
# Pre-flight — the two python3-stub recorders really fire, and the fablectl arm
# really falls through to the real interpreter.
#
# assert_walkup_called and assert_fablectl_wrote both assert that a file EXISTS.
# An assertion on a file that can never appear passes forever and proves nothing,
# so before any scenario leans on them, drive each stub arm directly inside a
# sandbox and show it recorded. The fablectl probe additionally checks that the
# ledger really moved to `approved`, which is what pins "the recorder observes,
# it does not substitute".
# =============================================================================
LPF="pre-flight (python3-stub recorders)"

# Probes, run INSIDE the sandbox by run_sandboxed. They take their paths as
# positional arguments because run_sandboxed unsets the suite's globals.
_walkup_probe()   { python3 ~/.claude/skills/run-autopilot/scripts/_walk_up.py --bash; }
_fablectl_probe() { python3 "$1" "$2" decide "$3" approved; }

make_sandbox; SBOX_PF="$SBOX"; LEDGER_PF="$LEDGER"
seed_request "$LEDGER_PF" "$PRD"

run_sandboxed "$SBOX_PF" 20 _walkup_probe
assert_no_timeout "$LPF" "$SBOX_PF"
[ -f "$SBOX_PF/dev/local/autopilot/walkup-invocations.log" ] \
  || FAIL "$LPF: the *_walk_up.py* arm records" "no walkup-invocations.log after a direct _walk_up.py call — assert_walkup_called could never fail"
[ "$(cat "$SBOX_PF/stdout.log")" = "$SBOX_PF/dev/local/autopilot" ] \
  || FAIL "$LPF: the *_walk_up.py* arm still answers the sandbox" "got '$(cat "$SBOX_PF/stdout.log" 2>/dev/null)', expected '$SBOX_PF/dev/local/autopilot'"

run_sandboxed "$SBOX_PF" 20 _fablectl_probe "$FABLECTL" "$LEDGER_PF" "$PRD"
assert_no_timeout "$LPF" "$SBOX_PF"
assert_rc "$LPF: the *fablectl.py*decide* arm exits like the real fablectl" "$SBOX_PF" 0
[ -f "$SBOX_PF/dev/local/autopilot/fablectl-invocations.log" ] \
  || FAIL "$LPF: the *fablectl.py*decide* arm records" "no fablectl-invocations.log after a direct fablectl decide — assert_fablectl_wrote could never fail"
assert_status "$LPF: the real fablectl still performed the write" "$LEDGER_PF" "$PRD" approved
PASS "$LPF: both recorders fire, and fablectl decide still runs for real"

# =============================================================================
# Scenario 1 — `autoclaude approve-fable <prd>` on a `requested` entry: status
# becomes approved with decided_at stamped inside the run's own time window, and
# the PRD is un-parked hold/ -> backlog/. One confirmation line names the PRD, the
# new status and where the PRD now sits. No loop session is ever launched. A
# second, unrelated `requested` entry sits in the same ledger and must survive
# completely untouched.
# =============================================================================
L1="scenario 1 (approve a requested rescue)"

make_sandbox; SBOX_1="$SBOX"; LEDGER_1="$LEDGER"
seed_request "$LEDGER_1" "$PRD"
seed_request "$LEDGER_1" "$BYSTANDER"
park_prd "$SBOX_1" hold
[ -z "$(ledger_field "$LEDGER_1" "$PRD" decided_at)" ] \
  || FAIL "$L1: fixture precondition" "a freshly requested entry already carries decided_at"

TS_BEFORE=$(utc_now)
run_autoclaude "$SBOX_1" approve-fable "$PRD"
TS_AFTER=$(utc_now)
assert_no_timeout "$L1" "$SBOX_1"
assert_rc "$L1: exits 0" "$SBOX_1" 0
assert_status "$L1: status becomes approved" "$LEDGER_1" "$PRD" approved
assert_decided_at_between "$L1: decided_at is stamped at decision time" "$LEDGER_1" "$PRD" "$TS_BEFORE" "$TS_AFTER"
assert_bystander_untouched "$L1: the unrelated requested entry is untouched" "$LEDGER_1"
assert_in_dir "$L1: PRD is un-parked into backlog/" "$SBOX_1" backlog
assert_not_in_dir "$L1: PRD no longer sits in hold/" "$SBOX_1" hold
assert_one_line "$L1: prints one confirmation line" "$SBOX_1/stdout.log"
assert_mentions "$L1: confirmation names the PRD" "$SBOX_1/stdout.log" "$PRD"
assert_mentions "$L1: confirmation names the new status" "$SBOX_1/stdout.log" "approved"
assert_mentions "$L1: confirmation says where the PRD now sits" "$SBOX_1/stdout.log" "backlog"
assert_walkup_called "$L1: the autopilot dir came from _walk_up.py" "$SBOX_1"
assert_fablectl_wrote "$L1: fablectl.py performed the ledger write" "$SBOX_1"
PASS "$L1: approved + live decided_at, one entry only, PRD moved hold/ -> backlog/, one confirmation line, exit 0"
assert_no_loop "$L1: no loop session launched" "$SBOX_1"

# =============================================================================
# Scenario 2 — reject-fable on a `requested` entry: status becomes rejected and
# the PRD STAYS in hold/ (a rejection is a normal stall for human disposition).
# A helper that ignored its first argument and always approved fails here twice.
# The unrelated `requested` entry must not be dragged along into `rejected`.
# =============================================================================
L2="scenario 2 (reject a requested rescue)"

make_sandbox; SBOX_2="$SBOX"; LEDGER_2="$LEDGER"
seed_request "$LEDGER_2" "$PRD"
seed_request "$LEDGER_2" "$BYSTANDER"
park_prd "$SBOX_2" hold

TS_BEFORE=$(utc_now)
run_helper "$SBOX_2" reject-fable "$PRD"
TS_AFTER=$(utc_now)
assert_no_timeout "$L2" "$SBOX_2"
assert_rc "$L2: exits 0" "$SBOX_2" 0
assert_status "$L2: status becomes rejected" "$LEDGER_2" "$PRD" rejected
assert_decided_at_between "$L2: decided_at is stamped at decision time" "$LEDGER_2" "$PRD" "$TS_BEFORE" "$TS_AFTER"
assert_bystander_untouched "$L2: the unrelated requested entry is untouched" "$LEDGER_2"
assert_in_dir "$L2: PRD stays parked in hold/" "$SBOX_2" hold
assert_not_in_dir "$L2: PRD is not un-parked into backlog/" "$SBOX_2" backlog
assert_one_line "$L2: prints one confirmation line" "$SBOX_2/stdout.log"
assert_mentions "$L2: confirmation names the PRD" "$SBOX_2/stdout.log" "$PRD"
assert_mentions "$L2: confirmation names the new status" "$SBOX_2/stdout.log" "rejected"
assert_walkup_called "$L2: the autopilot dir came from _walk_up.py" "$SBOX_2"
assert_fablectl_wrote "$L2: fablectl.py performed the ledger write" "$SBOX_2"
PASS "$L2: rejected, one entry only, PRD left in hold/, one confirmation line, exit 0"
assert_no_loop "$L2: no loop session launched" "$SBOX_2"

# =============================================================================
# Scenario 3 — a SECOND approve on an already-`approved` entry: fablectl refuses
# (exit 3), so the helper exits 2, the ledger stays byte identical, the PRD is
# not un-parked, and one stderr line names the PRD and its current status.
# =============================================================================
L3="scenario 3 (second approve on an approved entry)"

make_sandbox; SBOX_3="$SBOX"; LEDGER_3="$LEDGER"
seed_request "$LEDGER_3" "$PRD"
seed_decision "$LEDGER_3" "$PRD" approved
park_prd "$SBOX_3" hold
cp "$LEDGER_3" "$SBOX_3/ledger.expected"

run_helper "$SBOX_3" approve-fable "$PRD"
assert_no_timeout "$L3" "$SBOX_3"
assert_rc "$L3: exits 2" "$SBOX_3" 2
assert_ledger_unchanged "$L3: ledger is byte identical" "$SBOX_3" "$LEDGER_3"
assert_status "$L3: status is still approved" "$LEDGER_3" "$PRD" approved
assert_in_dir "$L3: PRD is not un-parked by a refused approval" "$SBOX_3" hold
assert_not_in_dir "$L3: PRD did not reach backlog/" "$SBOX_3" backlog
assert_one_line "$L3: one stderr line" "$SBOX_3/stderr.log"
assert_mentions "$L3: message names the PRD" "$SBOX_3/stderr.log" "$PRD"
assert_mentions "$L3: message names the current status" "$SBOX_3/stderr.log" "approved"
assert_walkup_called "$L3: the autopilot dir came from _walk_up.py" "$SBOX_3"
PASS "$L3: exit 2, ledger unchanged, PRD left in hold/, one stderr line naming PRD + status"
assert_no_loop "$L3: no loop session launched" "$SBOX_3"

# =============================================================================
# Scenario 4 — approve on a PRD with NO request in the ledger: exit 2, the
# ledger (which holds an unrelated entry) stays byte identical, and one stderr
# line names the PRD that has no request.
#
# The message must also be the RIGHT refusal. This PRD has no entry at all, so
# calling it `approved` is a flat lie about state that does not exist — the one
# canned "already approved" sentence that satisfies scenario 3 must not satisfy
# this one. Hence: stderr must NOT say "approved", and must carry a no-request
# signal ("no request", "no rescue request", "no ledger entry", "not requested",
# and the like — any honest wording of "nothing was ever filed for this PRD").
# =============================================================================
L4="scenario 4 (approve a PRD that has no request)"
OTHER_PRD="00077-other.md"

make_sandbox; SBOX_4="$SBOX"; LEDGER_4="$LEDGER"
seed_request "$LEDGER_4" "$OTHER_PRD"
park_prd "$SBOX_4" hold
cp "$LEDGER_4" "$SBOX_4/ledger.expected"

run_helper "$SBOX_4" approve-fable "$PRD"
assert_no_timeout "$L4" "$SBOX_4"
assert_rc "$L4: exits 2" "$SBOX_4" 2
assert_ledger_unchanged "$L4: ledger is byte identical" "$SBOX_4" "$LEDGER_4"
assert_status "$L4: the unrelated entry is untouched" "$LEDGER_4" "$OTHER_PRD" requested
assert_in_dir "$L4: PRD is not un-parked" "$SBOX_4" hold
assert_not_in_dir "$L4: PRD did not reach backlog/" "$SBOX_4" backlog
assert_one_line "$L4: one stderr line" "$SBOX_4/stderr.log"
assert_mentions "$L4: message names the PRD" "$SBOX_4/stderr.log" "$PRD"
assert_not_mentions "$L4: message does NOT call the missing entry approved" "$SBOX_4/stderr.log" "approved"
assert_matches "$L4: message says no request was ever filed" "$SBOX_4/stderr.log" \
  '(^|[^a-z])no ([a-z-]+ )*(request|entry|rescue)|not requested|never requested' \
  "stderr carries no no-request signal (expected wording like 'no rescue request' or 'no ledger entry')"
assert_walkup_called "$L4: the autopilot dir came from _walk_up.py" "$SBOX_4"
PASS "$L4: exit 2, ledger unchanged, PRD left in hold/, one stderr line naming the PRD and the real reason"
assert_no_loop "$L4: no loop session launched" "$SBOX_4"

# =============================================================================
# Scenario 5 — `autoclaude approve-fable` with NO PRD argument: exit 2 and the
# exact usage line on stderr, with nothing written and no loop started.
# =============================================================================
L5="scenario 5 (approve with no argument)"
USAGE_LINE="usage: autoclaude approve-fable <prd-filename.md>"

make_sandbox; SBOX_5="$SBOX"; LEDGER_5="$LEDGER"
seed_request "$LEDGER_5" "$PRD"
park_prd "$SBOX_5" hold
cp "$LEDGER_5" "$SBOX_5/ledger.expected"

run_autoclaude "$SBOX_5" approve-fable
assert_no_timeout "$L5" "$SBOX_5"
assert_rc "$L5: exits 2" "$SBOX_5" 2
[ "$(cat "$SBOX_5/stderr.log")" = "$USAGE_LINE" ] \
  || FAIL "$L5: prints the usage line" "expected '$USAGE_LINE', got '$(cat "$SBOX_5/stderr.log" 2>/dev/null)'"
assert_ledger_unchanged "$L5: ledger is byte identical" "$SBOX_5" "$LEDGER_5"
assert_in_dir "$L5: PRD is left parked in hold/" "$SBOX_5" hold
PASS "$L5: exit 2 with the exact usage line, nothing written"
assert_no_loop "$L5: no loop session launched" "$SBOX_5"

# =============================================================================
# Scenario 6 — approve when the PRD is NOT in hold/ (already un-parked): the
# status change still happens and the call succeeds; the move is skipped without
# error and the PRD stays where it is.
# =============================================================================
L6="scenario 6 (approve a PRD that is not parked in hold/)"

make_sandbox; SBOX_6="$SBOX"; LEDGER_6="$LEDGER"
seed_request "$LEDGER_6" "$PRD"
seed_request "$LEDGER_6" "$BYSTANDER"
park_prd "$SBOX_6" backlog

TS_BEFORE=$(utc_now)
run_helper "$SBOX_6" approve-fable "$PRD"
TS_AFTER=$(utc_now)
assert_no_timeout "$L6" "$SBOX_6"
assert_rc "$L6: exits 0" "$SBOX_6" 0
assert_status "$L6: status becomes approved" "$LEDGER_6" "$PRD" approved
assert_decided_at_between "$L6: decided_at is stamped at decision time" "$LEDGER_6" "$PRD" "$TS_BEFORE" "$TS_AFTER"
assert_bystander_untouched "$L6: the unrelated requested entry is untouched" "$LEDGER_6"
assert_in_dir "$L6: PRD stays in backlog/" "$SBOX_6" backlog
assert_not_in_dir "$L6: nothing is created in hold/" "$SBOX_6" hold
assert_mentions "$L6: confirmation names the PRD" "$SBOX_6/stdout.log" "$PRD"
assert_mentions "$L6: confirmation names the new status" "$SBOX_6/stdout.log" "approved"
assert_walkup_called "$L6: the autopilot dir came from _walk_up.py" "$SBOX_6"
assert_fablectl_wrote "$L6: fablectl.py performed the ledger write" "$SBOX_6"
PASS "$L6: approved and exit 0 with the move skipped, PRD left in backlog/"
assert_no_loop "$L6: no loop session launched" "$SBOX_6"

# =============================================================================
# Scenario 7 — a bare `autoclaude` call is UNAFFECTED by the guard: it still
# launches a session (the recording stub is invoked) and drains normally.
# =============================================================================
L7="scenario 7 (bare autoclaude still runs the loop)"

make_sandbox; SBOX_7="$SBOX"
printf '%s\n' '{"prd":"00001-x.md","next_phase":"build","batch":{"id":"b1"}}' \
  >"$SBOX_7/dev/local/autopilot/state.json"

run_autoclaude "$SBOX_7"
assert_no_timeout "$L7" "$SBOX_7"
assert_rc "$L7: drained loop returns 0" "$SBOX_7" 0
grep -q "Backlog drained" "$SBOX_7/stdout.log" \
  || FAIL "$L7: prints Backlog drained" "$(cat "$SBOX_7/stdout.log" 2>/dev/null)"
[ -f "$SBOX_7/claude-invocations.log" ] \
  || FAIL "$L7: the loop launched a session" "bin/claude was never invoked — the guard swallowed a bare call"
PASS "$L7: loop launched a session and drained with exit 0"

# =============================================================================
# Scenario 8 — approve when the un-park move CANNOT land: backlog/ is made
# unwritable, so the mv fails. The decision still stands — status stays approved
# with decided_at stamped (the ledger write is NOT rolled back) — the PRD is
# still in hold/, the call exits 2, and stderr names the PRD and tells the
# operator to move it by hand. A helper that returns 0 after a failed move, or
# that rolls the status back, fails here.
#
# Scope, honestly: this failure is a MODE-BIT failure, so a helper that never
# looks at the move's outcome and instead guesses from a `[ -w backlog ]` probe
# passes this scenario. Scenario 13 is the one that pins the post-move existence
# check, by failing the move in a way no permission probe can predict.
# =============================================================================
L8="scenario 8 (approve when the un-park move fails: backlog/ unwritable)"

make_sandbox; SBOX_8="$SBOX"; LEDGER_8="$LEDGER"
seed_request "$LEDGER_8" "$PRD"
seed_request "$LEDGER_8" "$BYSTANDER"
park_prd "$SBOX_8" hold
chmod 500 "$SBOX_8/dev/local/prds/backlog"
# Pre-flight: the scenario is only meaningful if the mode bits really do block
# writes here (they do not for root). Prove it before running, so a permissive
# filesystem fails loudly instead of passing for the wrong reason.
# (stderr is redirected FIRST: a failing redirect reports through whatever stderr
# the shell already has, so the order keeps the probe's error out of the output.)
if : 2>/dev/null >"$SBOX_8/dev/local/prds/backlog/.write-probe"; then
  rm -f "$SBOX_8/dev/local/prds/backlog/.write-probe"
  chmod 700 "$SBOX_8/dev/local/prds/backlog"
  FAIL "$L8: preflight" "cannot make backlog/ unwritable on this filesystem (running as root?) — the failed-move branch cannot be exercised"
fi

TS_BEFORE=$(utc_now)
run_helper "$SBOX_8" approve-fable "$PRD"
TS_AFTER=$(utc_now)
chmod 700 "$SBOX_8/dev/local/prds/backlog"   # restore so the cleanup trap can rm -rf
assert_no_timeout "$L8" "$SBOX_8"
assert_rc "$L8: exits 2" "$SBOX_8" 2
assert_status "$L8: status stays approved (the decision is not rolled back)" "$LEDGER_8" "$PRD" approved
assert_decided_at_between "$L8: decided_at is stamped at decision time" "$LEDGER_8" "$PRD" "$TS_BEFORE" "$TS_AFTER"
assert_bystander_untouched "$L8: the unrelated requested entry is untouched" "$LEDGER_8"
assert_in_dir "$L8: PRD is still parked in hold/" "$SBOX_8" hold
assert_not_in_dir "$L8: PRD did not reach backlog/" "$SBOX_8" backlog
assert_mentions "$L8: message names the PRD" "$SBOX_8/stderr.log" "$PRD"
# The contract pins the intent, not the sentence: the operator must be told to
# move the PRD themselves. Accept any wording carrying that signal.
grep -qiE 'manual|by hand|move|mv ' "$SBOX_8/stderr.log" \
  || FAIL "$L8: message tells the operator to move the PRD manually" "no manual-move instruction in stderr: $(cat "$SBOX_8/stderr.log" 2>/dev/null)"
assert_walkup_called "$L8: the autopilot dir came from _walk_up.py" "$SBOX_8"
assert_fablectl_wrote "$L8: fablectl.py performed the ledger write" "$SBOX_8"
PASS "$L8: exit 2, status left approved, PRD left in hold/, stderr names the PRD and asks for a manual move"
assert_no_loop "$L8: no loop session launched" "$SBOX_8"

# =============================================================================
# Scenario 9 — a MIXED-STATE ledger: an already-`approved` entry for one PRD sits
# beside the `requested` entry under test (and an untouched `requested`
# bystander). Approving the requested one SUCCEEDS. A helper that decides state
# by asking "does this ledger FILE contain the word approved" refuses here and
# fails; only a helper that reads THIS PRD's own status passes. The neighbour's
# own decided_at must come through byte-for-byte: it was decided earlier, and
# nothing about this call may re-stamp it.
# =============================================================================
L9="scenario 9 (approve a requested entry while another entry is already approved)"
NEIGHBOUR_PRD="00088-already-approved.md"

make_sandbox; SBOX_9="$SBOX"; LEDGER_9="$LEDGER"
seed_request "$LEDGER_9" "$NEIGHBOUR_PRD"
seed_decision "$LEDGER_9" "$NEIGHBOUR_PRD" approved
seed_request "$LEDGER_9" "$PRD"
seed_request "$LEDGER_9" "$BYSTANDER"
park_prd "$SBOX_9" hold
NEIGHBOUR_DECIDED_AT=$(ledger_field "$LEDGER_9" "$NEIGHBOUR_PRD" decided_at)
[ -n "$NEIGHBOUR_DECIDED_AT" ] \
  || FAIL "$L9: fixture precondition" "the already-approved neighbour carries no decided_at"

TS_BEFORE=$(utc_now)
run_helper "$SBOX_9" approve-fable "$PRD"
TS_AFTER=$(utc_now)
assert_no_timeout "$L9" "$SBOX_9"
assert_rc "$L9: exits 0 (a neighbour's approval is not this PRD's state)" "$SBOX_9" 0
assert_status "$L9: status becomes approved" "$LEDGER_9" "$PRD" approved
assert_decided_at_between "$L9: decided_at is stamped at decision time" "$LEDGER_9" "$PRD" "$TS_BEFORE" "$TS_AFTER"
assert_status "$L9: the neighbour stays approved" "$LEDGER_9" "$NEIGHBOUR_PRD" approved
[ "$(ledger_field "$LEDGER_9" "$NEIGHBOUR_PRD" decided_at)" = "$NEIGHBOUR_DECIDED_AT" ] \
  || FAIL "$L9: the neighbour's decided_at is untouched" \
          "it changed from '$NEIGHBOUR_DECIDED_AT' to '$(ledger_field "$LEDGER_9" "$NEIGHBOUR_PRD" decided_at)' — the write hit the whole ledger"
assert_bystander_untouched "$L9: the unrelated requested entry is untouched" "$LEDGER_9"
assert_in_dir "$L9: PRD is un-parked into backlog/" "$SBOX_9" backlog
assert_not_in_dir "$L9: PRD no longer sits in hold/" "$SBOX_9" hold
assert_one_line "$L9: prints one confirmation line" "$SBOX_9/stdout.log"
assert_mentions "$L9: confirmation names the PRD" "$SBOX_9/stdout.log" "$PRD"
assert_walkup_called "$L9: the autopilot dir came from _walk_up.py" "$SBOX_9"
assert_fablectl_wrote "$L9: fablectl.py performed the ledger write" "$SBOX_9"
PASS "$L9: approved beside an approved neighbour, neighbour and bystander untouched, exit 0"
assert_no_loop "$L9: no loop session launched" "$SBOX_9"

# =============================================================================
# Scenario 10 — approve on a `rejected` entry: fablectl refuses (exit 3), so the
# helper exits 2 with the ledger byte identical and the PRD left in hold/. The
# stderr line must name the PRD and its ACTUAL status, `rejected` — a single
# canned "already approved" sentence is wrong here.
# =============================================================================
L10="scenario 10 (approve an entry that was already rejected)"

make_sandbox; SBOX_10="$SBOX"; LEDGER_10="$LEDGER"
seed_request "$LEDGER_10" "$PRD"
seed_decision "$LEDGER_10" "$PRD" rejected
park_prd "$SBOX_10" hold
cp "$LEDGER_10" "$SBOX_10/ledger.expected"

run_helper "$SBOX_10" approve-fable "$PRD"
assert_no_timeout "$L10" "$SBOX_10"
assert_rc "$L10: exits 2" "$SBOX_10" 2
assert_ledger_unchanged "$L10: ledger is byte identical" "$SBOX_10" "$LEDGER_10"
assert_status "$L10: status is still rejected" "$LEDGER_10" "$PRD" rejected
assert_in_dir "$L10: PRD is not un-parked by a refused approval" "$SBOX_10" hold
assert_not_in_dir "$L10: PRD did not reach backlog/" "$SBOX_10" backlog
assert_one_line "$L10: one stderr line" "$SBOX_10/stderr.log"
assert_mentions "$L10: message names the PRD" "$SBOX_10/stderr.log" "$PRD"
assert_mentions "$L10: message names the current status" "$SBOX_10/stderr.log" "rejected"
assert_walkup_called "$L10: the autopilot dir came from _walk_up.py" "$SBOX_10"
PASS "$L10: exit 2, ledger unchanged, PRD left in hold/, stderr names the PRD and 'rejected'"
assert_no_loop "$L10: no loop session launched" "$SBOX_10"

# =============================================================================
# Scenario 11 — reject on an `approved` entry: the mirror of scenario 10. An
# approved rescue is already spent; rejecting it is outside the transition table,
# so exit 2, ledger byte identical, PRD left in hold/, and the message names the
# current status `approved`.
# =============================================================================
L11="scenario 11 (reject an entry that was already approved)"

make_sandbox; SBOX_11="$SBOX"; LEDGER_11="$LEDGER"
seed_request "$LEDGER_11" "$PRD"
seed_decision "$LEDGER_11" "$PRD" approved
park_prd "$SBOX_11" hold
cp "$LEDGER_11" "$SBOX_11/ledger.expected"

run_helper "$SBOX_11" reject-fable "$PRD"
assert_no_timeout "$L11" "$SBOX_11"
assert_rc "$L11: exits 2" "$SBOX_11" 2
assert_ledger_unchanged "$L11: ledger is byte identical" "$SBOX_11" "$LEDGER_11"
assert_status "$L11: status is still approved" "$LEDGER_11" "$PRD" approved
assert_in_dir "$L11: PRD stays in hold/" "$SBOX_11" hold
assert_one_line "$L11: one stderr line" "$SBOX_11/stderr.log"
assert_mentions "$L11: message names the PRD" "$SBOX_11/stderr.log" "$PRD"
assert_mentions "$L11: message names the current status" "$SBOX_11/stderr.log" "approved"
assert_walkup_called "$L11: the autopilot dir came from _walk_up.py" "$SBOX_11"
PASS "$L11: exit 2, ledger unchanged, PRD left in hold/, stderr names the PRD and 'approved'"
assert_no_loop "$L11: no loop session launched" "$SBOX_11"

# =============================================================================
# Scenario 12 — the same approval, run from a SUBDIRECTORY of the repo
# (dev/local/prds/). Everything still lands: the ledger entry flips and the PRD
# is un-parked. This is the scenario that makes _walk_up.py load-bearing — from
# here a hardcoded relative `dev/local/autopilot/ledger/...` (or
# `dev/local/prds/hold/...`) points at nothing, so a helper that never resolves
# the autopilot dir fails, while one that derives both paths from the resolver's
# answer passes regardless of where the operator stands.
# =============================================================================
L12="scenario 12 (approve from a subdirectory of the repo)"

make_sandbox; SBOX_12="$SBOX"; LEDGER_12="$LEDGER"
seed_request "$LEDGER_12" "$PRD"
seed_request "$LEDGER_12" "$BYSTANDER"
park_prd "$SBOX_12" hold

RUN_SUBDIR="dev/local/prds"
TS_BEFORE=$(utc_now)
run_autoclaude "$SBOX_12" approve-fable "$PRD"
TS_AFTER=$(utc_now)
assert_no_timeout "$L12" "$SBOX_12"
assert_rc "$L12: exits 0 from dev/local/prds/" "$SBOX_12" 0
assert_status "$L12: status becomes approved" "$LEDGER_12" "$PRD" approved
assert_decided_at_between "$L12: decided_at is stamped at decision time" "$LEDGER_12" "$PRD" "$TS_BEFORE" "$TS_AFTER"
assert_bystander_untouched "$L12: the unrelated requested entry is untouched" "$LEDGER_12"
assert_in_dir "$L12: PRD is un-parked into backlog/" "$SBOX_12" backlog
assert_not_in_dir "$L12: PRD no longer sits in hold/" "$SBOX_12" hold
assert_one_line "$L12: prints one confirmation line" "$SBOX_12/stdout.log"
assert_mentions "$L12: confirmation names the PRD" "$SBOX_12/stdout.log" "$PRD"
assert_walkup_called "$L12: the autopilot dir came from _walk_up.py" "$SBOX_12"
assert_fablectl_wrote "$L12: fablectl.py performed the ledger write" "$SBOX_12"
PASS "$L12: cwd inside the repo still resolves the ledger and both PRD folders, exit 0"
assert_no_loop "$L12: no loop session launched" "$SBOX_12"

# =============================================================================
# Scenario 13 — the un-park cannot land, and NO permission probe can tell.
# backlog/ stays writable; the destination NAME backlog/<prd> is occupied by a
# non-empty directory, which rename(2) will not replace. So a helper that asks
# `[ -w backlog ]` and then trusts the move is told "go ahead" and is wrong,
# while a helper that checks the file actually arrived is right. The decision
# still stands (status approved, decided_at kept), the call exits 2, and the
# operator is told to move the PRD by hand.
# =============================================================================
L13="scenario 13 (approve when the un-park is blocked by an occupied destination)"

make_sandbox; SBOX_13="$SBOX"; LEDGER_13="$LEDGER"
seed_request "$LEDGER_13" "$PRD"
seed_request "$LEDGER_13" "$BYSTANDER"
park_prd "$SBOX_13" hold
mkdir -p "$SBOX_13/dev/local/prds/backlog/$PRD"
printf '%s\n' "# occupies the un-park destination name" \
  >"$SBOX_13/dev/local/prds/backlog/$PRD/blocker.md"

# Pre-flight, loud: prove on THIS filesystem that no regular file can arrive at
# a path held by a non-empty directory — for both spellings of the move, since
# `mv src dst/<name>` and `mv src dst/` behave differently (the first moves the
# file INSIDE the directory and still exits 0). Whichever spelling the helper
# uses, the post-move existence check is the only thing that can catch it.
mkdir -p "$SBOX_13/.preflight/dst/$PRD" "$SBOX_13/.preflight/src"
printf 'keep\n' >"$SBOX_13/.preflight/dst/$PRD/keep"
printf 'probe\n' >"$SBOX_13/.preflight/src/$PRD"
mv "$SBOX_13/.preflight/src/$PRD" "$SBOX_13/.preflight/dst/$PRD" 2>/dev/null
[ -f "$SBOX_13/.preflight/dst/$PRD" ] \
  && FAIL "$L13: preflight" "on this filesystem a file CAN replace a non-empty directory (mv src dst/<name>) — the blocked-move branch cannot be exercised"
printf 'probe\n' >"$SBOX_13/.preflight/src/$PRD"
if mv "$SBOX_13/.preflight/src/$PRD" "$SBOX_13/.preflight/dst/" 2>/dev/null; then
  FAIL "$L13: preflight" "on this filesystem mv into a directory whose <name> is a non-empty directory SUCCEEDS — the blocked-move branch cannot be exercised"
fi
[ -w "$SBOX_13/dev/local/prds/backlog" ] \
  || FAIL "$L13: preflight" "backlog/ is not writable — this scenario must fail the move WITHOUT withdrawing write permission"

TS_BEFORE=$(utc_now)
run_helper "$SBOX_13" approve-fable "$PRD"
TS_AFTER=$(utc_now)
assert_no_timeout "$L13" "$SBOX_13"
assert_rc "$L13: exits 2 (the move never landed)" "$SBOX_13" 2
assert_status "$L13: status stays approved (the decision is not rolled back)" "$LEDGER_13" "$PRD" approved
assert_decided_at_between "$L13: decided_at is stamped at decision time" "$LEDGER_13" "$PRD" "$TS_BEFORE" "$TS_AFTER"
assert_bystander_untouched "$L13: the unrelated requested entry is untouched" "$LEDGER_13"
[ -f "$SBOX_13/dev/local/prds/backlog/$PRD" ] \
  && FAIL "$L13: the un-park did not land" "backlog/$PRD is a regular file — impossible, the name is held by a directory"
[ -d "$SBOX_13/dev/local/prds/backlog/$PRD" ] \
  || FAIL "$L13: the blocking directory survives" "backlog/$PRD is no longer a directory — the helper destroyed the thing in its way"
[ -f "$SBOX_13/dev/local/prds/backlog/$PRD/blocker.md" ] \
  || FAIL "$L13: the blocking directory's content survives" "blocker.md is gone — the helper clobbered unrelated files"
# The PRD body must still exist somewhere the operator can reach: either left in
# hold/ (mv refused) or nested under the blocking directory (mv moved it inside).
# Either is recoverable by hand; losing it is not.
[ -f "$SBOX_13/dev/local/prds/hold/$PRD" ] || [ -f "$SBOX_13/dev/local/prds/backlog/$PRD/$PRD" ] \
  || FAIL "$L13: the PRD body survives the failed un-park" "the PRD is in neither hold/ nor backlog/$PRD/ — the failed move lost it"
assert_mentions "$L13: message names the PRD" "$SBOX_13/stderr.log" "$PRD"
grep -qiE 'manual|by hand|move|mv ' "$SBOX_13/stderr.log" \
  || FAIL "$L13: message tells the operator to move the PRD manually" "no manual-move instruction in stderr: $(cat "$SBOX_13/stderr.log" 2>/dev/null)"
assert_walkup_called "$L13: the autopilot dir came from _walk_up.py" "$SBOX_13"
assert_fablectl_wrote "$L13: fablectl.py performed the ledger write" "$SBOX_13"
PASS "$L13: exit 2 on a move a permission probe cannot predict, status left approved, PRD body preserved"
assert_no_loop "$L13: no loop session launched" "$SBOX_13"

# =============================================================================
# Scenario 14 — `autoclaude reject-fable` with NO PRD argument: exit 2 and a
# usage line that names the subcommand the operator actually typed. The contract
# pins the exact sentence only for approve (scenario 5), so this asserts the
# SHAPE: one stderr line, the word `usage`, and `reject-fable` — never
# `approve-fable`, which is what a hardcoded usage string would print.
# =============================================================================
L14="scenario 14 (reject with no argument)"

make_sandbox; SBOX_14="$SBOX"; LEDGER_14="$LEDGER"
seed_request "$LEDGER_14" "$PRD"
park_prd "$SBOX_14" hold
cp "$LEDGER_14" "$SBOX_14/ledger.expected"

run_autoclaude "$SBOX_14" reject-fable
assert_no_timeout "$L14" "$SBOX_14"
assert_rc "$L14: exits 2" "$SBOX_14" 2
assert_one_line "$L14: one stderr line" "$SBOX_14/stderr.log"
assert_mentions "$L14: the line is a usage line" "$SBOX_14/stderr.log" "usage"
assert_mentions "$L14: usage names the subcommand that was invoked" "$SBOX_14/stderr.log" "reject-fable"
assert_not_mentions "$L14: usage does not name the other subcommand" "$SBOX_14/stderr.log" "approve-fable"
assert_ledger_unchanged "$L14: ledger is byte identical" "$SBOX_14" "$LEDGER_14"
assert_status "$L14: status is still requested" "$LEDGER_14" "$PRD" requested
assert_in_dir "$L14: PRD is left parked in hold/" "$SBOX_14" hold
PASS "$L14: exit 2 with a usage line naming reject-fable, nothing written"
assert_no_loop "$L14: no loop session launched" "$SBOX_14"

# =============================================================================
# Scenario 15 — the guard is the FIRST statement in autoclaude(), pinned
# hermetically. The rest of the suite runs with _AUTOPILOT_TRACON=0, which would
# let a guard sitting AFTER the tracon branch pass unnoticed. Here the branch is
# FORCED on (_AUTOPILOT_TRACON=1) and _autoclaude_tracon is a stub that records
# its own invocation and returns 0 — no TUI, no session, no loop. A correct guard
# returns before that branch is ever evaluated, so the recorder file is never
# created; the approval itself still has to work.
# =============================================================================
L15="scenario 15 (the guard precedes the tracon branch)"

# Pre-flight, loud: an assertion on a file that never appears proves nothing, so
# first show the recorder DOES fire. A bare `autoclaude` under _AUTOPILOT_TRACON=1
# must reach the tracon branch and leave the file behind (the stub returns 0
# immediately, so no loop and no session follow). If this does not fire, the
# scenario below is vacuous and the suite says so instead of passing.
make_sandbox; SBOX_15P="$SBOX"
TRACON_MODE=1
run_autoclaude "$SBOX_15P"
assert_no_timeout "$L15: preflight" "$SBOX_15P"
[ -f "$SBOX_15P/dev/local/autopilot/tracon-invocations.log" ] \
  || FAIL "$L15: preflight" "a bare autoclaude with _AUTOPILOT_TRACON=1 did NOT reach the tracon branch — the recorder is not wired, so the assertion below could never fail"

make_sandbox; SBOX_15="$SBOX"; LEDGER_15="$LEDGER"
seed_request "$LEDGER_15" "$PRD"
seed_request "$LEDGER_15" "$BYSTANDER"
park_prd "$SBOX_15" hold
TRACON_RECORDER="$SBOX_15/dev/local/autopilot/tracon-invocations.log"
[ -e "$TRACON_RECORDER" ] \
  && FAIL "$L15: fixture precondition" "the tracon recorder file already exists before the run"

TRACON_MODE=1
TS_BEFORE=$(utc_now)
run_autoclaude "$SBOX_15" approve-fable "$PRD"
TS_AFTER=$(utc_now)
assert_no_timeout "$L15" "$SBOX_15"
[ -e "$TRACON_RECORDER" ] \
  && FAIL "$L15: the tracon branch is never reached" "_autoclaude_tracon ran ($(cat "$TRACON_RECORDER" 2>/dev/null)) — the subcommand guard is not the first statement in autoclaude()"
assert_rc "$L15: exits 0" "$SBOX_15" 0
assert_status "$L15: status becomes approved" "$LEDGER_15" "$PRD" approved
assert_decided_at_between "$L15: decided_at is stamped at decision time" "$LEDGER_15" "$PRD" "$TS_BEFORE" "$TS_AFTER"
assert_bystander_untouched "$L15: the unrelated requested entry is untouched" "$LEDGER_15"
assert_in_dir "$L15: PRD is un-parked into backlog/" "$SBOX_15" backlog
assert_not_in_dir "$L15: PRD no longer sits in hold/" "$SBOX_15" hold
assert_walkup_called "$L15: the autopilot dir came from _walk_up.py" "$SBOX_15"
assert_fablectl_wrote "$L15: fablectl.py performed the ledger write" "$SBOX_15"
PASS "$L15: tracon forced on and still never entered, approval landed, exit 0"
assert_no_loop "$L15: no loop session launched" "$SBOX_15"

# =============================================================================
# Scenario 16 — a refusal must report THIS entry's status, not a neighbour's.
# Scenarios 3, 10 and 11 each hold exactly one entry, so "grep the whole ledger
# for approved, else rejected" answers all three correctly. Here the ledger holds
# two decided entries with DIFFERENT statuses: the neighbour is `approved`, the
# PRD under test is `rejected`. `approve-fable <prd>` must refuse and say
# `rejected` — the word `approved` in that message would be a flat lie about the
# PRD the operator named.
#
# Wording contract this pins: a refusal names exactly ONE status, the entry's
# own. "already rejected", "is rejected", "status rejected" all pass; the
# subcommand name `approve-fable` is not the word `approved`, so quoting the verb
# back at the operator stays legal.
# =============================================================================
L16="scenario 16 (refusal names this entry's status, not the neighbour's)"

make_sandbox; SBOX_16="$SBOX"; LEDGER_16="$LEDGER"
seed_request  "$LEDGER_16" "$NEIGHBOUR_PRD"
seed_decision "$LEDGER_16" "$NEIGHBOUR_PRD" approved
seed_request  "$LEDGER_16" "$PRD"
seed_decision "$LEDGER_16" "$PRD" rejected
park_prd "$SBOX_16" hold
cp "$LEDGER_16" "$SBOX_16/ledger.expected"
# Fixture precondition, loud: the two entries really do disagree. If both were
# `rejected` the scenario would pass for a whole-file grep too.
[ "$(ledger_field "$LEDGER_16" "$NEIGHBOUR_PRD" status)" = approved ] \
  && [ "$(ledger_field "$LEDGER_16" "$PRD" status)" = rejected ] \
  || FAIL "$L16: fixture precondition" "the ledger does not hold an approved neighbour beside a rejected PRD under test"

run_helper "$SBOX_16" approve-fable "$PRD"
assert_no_timeout "$L16" "$SBOX_16"
assert_rc "$L16: exits 2" "$SBOX_16" 2
assert_ledger_unchanged "$L16: ledger is byte identical" "$SBOX_16" "$LEDGER_16"
assert_status "$L16: the PRD under test is still rejected" "$LEDGER_16" "$PRD" rejected
assert_status "$L16: the neighbour is still approved" "$LEDGER_16" "$NEIGHBOUR_PRD" approved
assert_in_dir "$L16: PRD is not un-parked by a refused approval" "$SBOX_16" hold
assert_not_in_dir "$L16: PRD did not reach backlog/" "$SBOX_16" backlog
assert_one_line "$L16: one stderr line" "$SBOX_16/stderr.log"
assert_mentions "$L16: message names the PRD" "$SBOX_16/stderr.log" "$PRD"
assert_mentions "$L16: message names THIS entry's status" "$SBOX_16/stderr.log" "rejected"
assert_not_mentions "$L16: message does NOT report the neighbour's status" "$SBOX_16/stderr.log" "approved"
assert_walkup_called "$L16: the autopilot dir came from _walk_up.py" "$SBOX_16"
PASS "$L16: exit 2, ledger unchanged, stderr reports 'rejected' and never the neighbour's 'approved'"
assert_no_loop "$L16: no loop session launched" "$SBOX_16"

# =============================================================================
# Scenario 17 — the mirror of 16, with the statuses swapped: the PRD under test
# is `approved` and the neighbour is `rejected`. `reject-fable <prd>` must refuse
# and say `approved`. Together, 16 and 17 make the fallback chain "if the file
# mentions approved say approved, else if it mentions rejected say rejected"
# wrong in both directions, whichever order the chain is written in.
# =============================================================================
L17="scenario 17 (the mirror: reject an approved PRD beside a rejected neighbour)"
REJECTED_NEIGHBOUR_PRD="00089-already-rejected.md"

make_sandbox; SBOX_17="$SBOX"; LEDGER_17="$LEDGER"
seed_request  "$LEDGER_17" "$REJECTED_NEIGHBOUR_PRD"
seed_decision "$LEDGER_17" "$REJECTED_NEIGHBOUR_PRD" rejected
seed_request  "$LEDGER_17" "$PRD"
seed_decision "$LEDGER_17" "$PRD" approved
park_prd "$SBOX_17" hold
cp "$LEDGER_17" "$SBOX_17/ledger.expected"
[ "$(ledger_field "$LEDGER_17" "$REJECTED_NEIGHBOUR_PRD" status)" = rejected ] \
  && [ "$(ledger_field "$LEDGER_17" "$PRD" status)" = approved ] \
  || FAIL "$L17: fixture precondition" "the ledger does not hold a rejected neighbour beside an approved PRD under test"

run_helper "$SBOX_17" reject-fable "$PRD"
assert_no_timeout "$L17" "$SBOX_17"
assert_rc "$L17: exits 2" "$SBOX_17" 2
assert_ledger_unchanged "$L17: ledger is byte identical" "$SBOX_17" "$LEDGER_17"
assert_status "$L17: the PRD under test is still approved" "$LEDGER_17" "$PRD" approved
assert_status "$L17: the neighbour is still rejected" "$LEDGER_17" "$REJECTED_NEIGHBOUR_PRD" rejected
assert_in_dir "$L17: PRD stays in hold/" "$SBOX_17" hold
assert_not_in_dir "$L17: PRD did not reach backlog/" "$SBOX_17" backlog
assert_one_line "$L17: one stderr line" "$SBOX_17/stderr.log"
assert_mentions "$L17: message names the PRD" "$SBOX_17/stderr.log" "$PRD"
assert_mentions "$L17: message names THIS entry's status" "$SBOX_17/stderr.log" "approved"
assert_not_mentions "$L17: message does NOT report the neighbour's status" "$SBOX_17/stderr.log" "rejected"
assert_walkup_called "$L17: the autopilot dir came from _walk_up.py" "$SBOX_17"
PASS "$L17: exit 2, ledger unchanged, stderr reports 'approved' and never the neighbour's 'rejected'"
assert_no_loop "$L17: no loop session launched" "$SBOX_17"

# =============================================================================
# Scenario 18 — the un-park move EXITS 0 and the PRD still never arrives.
#
# Scenarios 8 and 13 both fail the move in ways that also make `mv` exit
# non-zero, so an implementation that only tests `$?` passes both. Here
# backlog/<prd> is an EMPTY directory: `mv hold/<prd> backlog/<prd>` treats the
# destination as a directory and lands the file at backlog/<prd>/<prd>, exiting
# 0. The PRD is NOT at backlog/<prd> — that name is a directory — so the operator
# would be told "un-parked into backlog/" about a file the next autopilot batch
# will never see. Only a real post-move `[ -f "<backlog>/<prd>" ]` check catches
# it. (The other spelling, `mv hold/<prd> backlog/`, fails outright here with
# EISDIR, so both spellings must end in exit 2 — one via $?, one via the check.)
#
# The decision itself still stands: approved, decided_at kept, and the operator
# is told to finish the move by hand.
# =============================================================================
L18="scenario 18 (the un-park exits 0 but the PRD never arrives)"

make_sandbox; SBOX_18="$SBOX"; LEDGER_18="$LEDGER"
seed_request "$LEDGER_18" "$PRD"
seed_request "$LEDGER_18" "$BYSTANDER"
park_prd "$SBOX_18" hold
mkdir -p "$SBOX_18/dev/local/prds/backlog/$PRD"      # EMPTY dir on the destination name

# Pre-flight, loud: on THIS filesystem the move must really exit 0 and really
# nest the file. If mv refused instead, the scenario would silently degrade into
# another copy of scenario 13 and the exit-code-trusting bug would go unpinned.
mkdir -p "$SBOX_18/.preflight/dst/$PRD" "$SBOX_18/.preflight/src"
printf 'probe\n' >"$SBOX_18/.preflight/src/$PRD"
mv "$SBOX_18/.preflight/src/$PRD" "$SBOX_18/.preflight/dst/$PRD" \
  || FAIL "$L18: preflight" "mv <file> <empty-dir> exits non-zero on this filesystem — the exit-0-but-missing branch cannot be exercised"
[ -f "$SBOX_18/.preflight/dst/$PRD/$PRD" ] \
  || FAIL "$L18: preflight" "mv <file> <empty-dir> did not nest the file — the exit-0-but-missing branch cannot be exercised"
[ -w "$SBOX_18/dev/local/prds/backlog" ] \
  || FAIL "$L18: preflight" "backlog/ is not writable — this scenario must fail the move WITHOUT withdrawing write permission"

TS_BEFORE=$(utc_now)
run_helper "$SBOX_18" approve-fable "$PRD"
TS_AFTER=$(utc_now)
assert_no_timeout "$L18" "$SBOX_18"
assert_rc "$L18: exits 2 (the move returned 0, the PRD did not arrive)" "$SBOX_18" 2
assert_status "$L18: status stays approved (the decision is not rolled back)" "$LEDGER_18" "$PRD" approved
assert_decided_at_between "$L18: decided_at is stamped at decision time" "$LEDGER_18" "$PRD" "$TS_BEFORE" "$TS_AFTER"
assert_bystander_untouched "$L18: the unrelated requested entry is untouched" "$LEDGER_18"
[ -f "$SBOX_18/dev/local/prds/backlog/$PRD" ] \
  && FAIL "$L18: the un-park did not land" "backlog/$PRD is a regular file — impossible, the name is held by a directory"
[ -d "$SBOX_18/dev/local/prds/backlog/$PRD" ] \
  || FAIL "$L18: the occupying directory survives" "backlog/$PRD is no longer a directory — the helper destroyed the thing in its way"
# The PRD body must still be reachable: left in hold/ (mv refused) or nested
# inside the occupying directory (mv exited 0 and put it there). Either is
# recoverable by hand; losing it is not.
[ -f "$SBOX_18/dev/local/prds/hold/$PRD" ] || [ -f "$SBOX_18/dev/local/prds/backlog/$PRD/$PRD" ] \
  || FAIL "$L18: the PRD body survives the failed un-park" "the PRD is in neither hold/ nor backlog/$PRD/ — the failed move lost it"
assert_mentions "$L18: message names the PRD" "$SBOX_18/stderr.log" "$PRD"
grep -qiE 'manual|by hand|move|mv ' "$SBOX_18/stderr.log" \
  || FAIL "$L18: message tells the operator to move the PRD manually" "no manual-move instruction in stderr: $(cat "$SBOX_18/stderr.log" 2>/dev/null)"
assert_not_matches "$L18: stdout does not claim a successful un-park" "$SBOX_18/stdout.log" \
  'un-?parked|moved (it )?(in)?to|now in backlog' \
  "stdout announces an un-park that never happened"
assert_walkup_called "$L18: the autopilot dir came from _walk_up.py" "$SBOX_18"
assert_fablectl_wrote "$L18: fablectl.py performed the ledger write" "$SBOX_18"
PASS "$L18: exit 2 on a move that returned 0 without delivering, status left approved, PRD body preserved"
assert_no_loop "$L18: no loop session launched" "$SBOX_18"

# =============================================================================
# Scenario 19 — the ledger is PRESENT but unreadable. fablectl exits 2 on it
# ("ledger is not valid JSON"), and the contract for a fablectl exit 1 or 2 is:
# print the stderr verbatim and exit 2; nothing retries, nothing is written.
#
# The failure this pins is the comfortable misreport: an implementation that
# reads the ledger itself (grep, sed, a `case` over the raw text) finds no
# matching entry in `not json` and announces "no rescue request on file" — so the
# operator hears "you never filed one" when the truth is "your ledger is
# corrupt". One of those is fixed by re-filing, the other by restoring a backup.
# =============================================================================
L19="scenario 19 (the ledger is present but unreadable)"

make_sandbox; SBOX_19="$SBOX"; LEDGER_19="$LEDGER"
printf 'not json\n' >"$LEDGER_19"
park_prd "$SBOX_19" hold

# Pre-flight, loud: the REAL fablectl must classify this ledger as unreadable
# (exit 2), not as a missing request (exit 3). If it ever stopped doing so, this
# scenario would quietly test the wrong branch of the contract.
command python3 "$FABLECTL" "$LEDGER_19" decide "$PRD" approved >/dev/null 2>"$SBOX_19/preflight.err"
PF_RC=$?
[ "$PF_RC" -eq 2 ] \
  || FAIL "$L19: preflight" "fablectl exits $PF_RC on an unreadable ledger, expected 2 — got: $(cat "$SBOX_19/preflight.err" 2>/dev/null)"
cp "$LEDGER_19" "$SBOX_19/ledger.expected"

run_helper "$SBOX_19" approve-fable "$PRD"
assert_no_timeout "$L19" "$SBOX_19"
assert_rc "$L19: exits 2" "$SBOX_19" 2
assert_ledger_unchanged "$L19: the unreadable ledger is left exactly as found" "$SBOX_19" "$LEDGER_19"
assert_in_dir "$L19: PRD is not un-parked" "$SBOX_19" hold
assert_not_in_dir "$L19: PRD did not reach backlog/" "$SBOX_19" backlog
assert_one_line "$L19: one stderr line" "$SBOX_19/stderr.log"
assert_mentions "$L19: message names the ledger" "$SBOX_19/stderr.log" "ledger"
assert_matches "$L19: message says the ledger cannot be read" "$SBOX_19/stderr.log" \
  'not valid json|invalid json|unreadable|cannot be read|corrupt|damaged|malformed|parse' \
  "stderr carries no unreadable-ledger signal (expected wording like 'ledger is not valid JSON')"
assert_not_matches "$L19: message does NOT blame a missing request" "$SBOX_19/stderr.log" \
  '(^|[^a-z])no ([a-z-]+ )*(request|entry|rescue)|not requested|never requested' \
  "stderr blames a missing request when the real fault is an unreadable ledger"
assert_walkup_called "$L19: the autopilot dir came from _walk_up.py" "$SBOX_19"
PASS "$L19: exit 2, ledger untouched, PRD left in hold/, stderr names the unreadable ledger"
assert_no_loop "$L19: no loop session launched" "$SBOX_19"

# =============================================================================
echo ""
echo "All checks passed."
exit 0
