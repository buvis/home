cite about-plugin
about-plugin 'functions for software development'

# start Claude Code working around the bugs
# claude() {
#   SHELL=/bin/sh GIT_PAGER=cat command claude --plugin-dir ~/.config/claude/ "$@"
# }

# _autopilot_tagged <pid> — true when <pid> or a direct child of it carries
# _AUTOPILOT_LOOP=<pid> in its ps environment. Children count because ps
# reports the EXEC-time environment: _autoclaude_tracon forks the loop shell
# (the pid the registry stores — killpg needs the group leader) and the tag is
# exported only after that fork, so it shows on the exec'd driver beneath the
# shell and never on the shell itself. Matching the shell alone swept LIVE
# loops out of the registry, and tracon then read them as dead: no pause chip,
# no limit-wait countdown, and q → s answering "nothing to stop".
_autopilot_tagged() {
  local _pid="$1" _kids
  _kids=$(pgrep -P "$_pid" 2>/dev/null | tr '\n' ',')
  ps ewww -p "$_pid${_kids:+,${_kids%,}}" -o command= 2>/dev/null |
    grep -qE "_AUTOPILOT_LOOP=${_pid}( |$)"
}

# _autopilot_prune_registry <loops_dir> — sweep <loops_dir>/*.json for stale
# entries before a duplicate-loop check or a new registration: an entry
# whose stored pid is dead, or alive but not tagged with its own
# _AUTOPILOT_LOOP=<pid> (a recycled pid claimed by an unrelated process), is
# not a real loop and must not linger or block a new one. Malformed or
# unreadable entries (jq failure, empty pid) are swept the same way — they
# can never denote a live loop either. Never touches the CURRENT process's
# own entry (stored pid == $BASHPID, whatever the entry's filename) — this
# process is definitionally alive and is never its own stale duplicate.
_autopilot_prune_registry() {
  local _dir="$1" _f _pid
  for _f in "$_dir"/*.json; do
    [ -e "$_f" ] || continue
    _pid=$(jq -r '.pid // empty' "$_f" 2>/dev/null)
    [ "$_pid" = "$BASHPID" ] && continue
    if [ -z "$_pid" ] || ! kill -0 "$_pid" 2>/dev/null ||
      ! _autopilot_tagged "$_pid"; then
      rm -f "$_f"
    fi
  done
}

# _autopilot_skill_root — the installed autopilot plugin's skills/run-autopilot
# (the code the spawned sessions load; ~/.claude/skills/run-autopilot went away
# with the 2026-08-25 plugin extraction). _AUTOPILOT_SKILL_ROOT overrides it
# for a dev checkout. Never a pinned version: the cache rolled 0.1.1 -> 0.1.2
# under a running PRD once and stranded the driver that had pinned it.
_autopilot_skill_root() {
  if [ -n "$_AUTOPILOT_SKILL_ROOT" ]; then
    printf '%s\n' "$_AUTOPILOT_SKILL_ROOT"
    return 0
  fi
  local _cache="$HOME/.claude/plugins/cache/buvis-plugins/autopilot" _main _ver _best
  _best=$(for _main in "$_cache"/*/skills/run-autopilot/cli/__main__.py; do
      [ -e "$_main" ] || continue
      _ver="${_main#"$_cache"/}"
      printf '%s\n' "${_ver%%/*}"
    done | sort -t. -k1,1n -k2,2n -k3,3n | tail -n 1)
  if [ -n "$_best" ]; then
    printf '%s/%s/skills/run-autopilot\n' "$_cache" "$_best"
    return 0
  fi
  # Pre-extraction layout (a checkout linked at the old path): consulted only
  # when no plugin is installed, so a stale link can never shadow the cache.
  if [ -e "$HOME/.claude/skills/run-autopilot/cli/__main__.py" ]; then
    printf '%s/.claude/skills/run-autopilot\n' "$HOME"
    return 0
  fi
  printf 'autopilot: no autopilot plugin installed under %s (install it, or set _AUTOPILOT_SKILL_ROOT).\n' "$_cache" >&2
  return 1
}

# tracon [args...] — launch the autopilot TUI standalone (defaults to loop
# discovery; pass --root <repo> to pin one). Temporary until tracon ships as
# a buvis-gems tool; drop this function then.
tracon() {
  local _skill
  _skill=$(_autopilot_skill_root) || return 1
  uv run --quiet --no-project "$_skill/scripts/tracon.py" "$@"
}

# autopilot [args...] — dispatch to the cli/__main__.py subcommand CLI (PRD 00051).
autopilot() {
  local _skill
  _skill=$(_autopilot_skill_root) || return 1
  python3 "$_skill/cli/__main__.py" "$@"
}

# _autoclaude_tracon <args...> — foreground the tracon TUI while the loop runs
# backgrounded as a process-group leader. See autoclaude's presentation
# branch (_AUTOPILOT_TRACON=0/1/auto) for the routing decision.
_autoclaude_tracon() {
  local _ap_dir _root _loop="" _rc _mset _skill _tracon_py
  # A missing plugin is not fatal HERE: the guard below reads a missing probe
  # as "not alive" and the preflight falls back to the plain renderer, whose
  # `autopilot loop` hand-off is where the resolver refuses out loud.
  _skill=$(_autopilot_skill_root 2>/dev/null)
  _tracon_py="$_skill/scripts/tracon.py"
  _ap_dir=$(python3 "$_skill/scripts/_walk_up.py" --bash 2>/dev/null)
  [ -n "$_ap_dir" ] || _ap_dir="$PWD/dev/local/autopilot"
  _root="${_ap_dir%/dev/local/autopilot}"
  mkdir -p "$_ap_dir" 2>/dev/null

  # Export the resolved loops dir BEFORE any child is spawned (guard,
  # preflight, uv): unlike the plain loop body (~line 300) this function
  # never exported it, so a real child process (e.g. tracon's discovery.py)
  # could resolve a different dir than the wrapper itself writes to.
  export _AUTOPILOT_LOOPS_DIR="${_AUTOPILOT_LOOPS_DIR:-$HOME/.claude/autopilot-loops}"

  # Prune stale registry entries BEFORE the duplicate-loop guard reads them:
  # a dead pid or a live-but-untagged (recycled) pid must never block a new
  # loop.
  _autopilot_prune_registry "$_AUTOPILOT_LOOPS_DIR"

  # (1) Duplicate-loop guard FIRST (cheap; before any uv cost). The guard
  # prints the incumbent loop's pid on stdout when one is alive, so the
  # refusal can name it (a second loop on one repo double-drains the batch).
  local _live_pid
  _live_pid=$(python3 "$_skill/scripts/tracon_wrapper_alive.py" "$_root" 2>/dev/null)
  if [ -n "$_live_pid" ]; then
    printf 'autoclaude: a loop is already running for %s (pid %s; registry: %s). Refusing to start a second loop on the same repo.\n' \
      "$_root" "$_live_pid" "${_AUTOPILOT_LOOPS_DIR:-$HOME/.claude/autopilot-loops}" >&2
    printf 'Attach:  uv run --no-project %s --root %s\n' "$_tracon_py" "$_root" >&2
    return 1
  fi

  # (2) Dependency preflight. Failure => today's renderer, zero behavior change.
  if ! uv run --quiet --no-project "$_tracon_py" --preflight >/dev/null 2>&1; then
    printf 'autoclaude: tracon unavailable (uv/textual preflight failed); using the plain renderer.\n' >&2
    _AUTOPILOT_TRACON=0 autoclaude "$@"
    return $?
  fi

  # (3) Job control ON so the child is a process-group LEADER. Decided BEFORE forking:
  # if monitor mode will not stick, never fork a loop we cannot stop.
  case "$-" in *m*) _mset=1 ;; *) _mset=0 ;; esac
  set -m
  case "$-" in
    *m*) ;;
    *)  printf 'autoclaude: job control unavailable; using the plain renderer.\n' >&2
        _AUTOPILOT_TRACON=0 autoclaude "$@"
        return $? ;;
  esac

  # (4) Parent INT/TERM traps installed BEFORE the fork. Mirrors the loop's
  # own INT/TERM contract below (~line 199): only act once `_loop` actually
  # holds the backgrounded loop's pid — a signal landing before the fork
  # line runs must never fall back to $! (an unrelated job of the caller).
  trap 'trap - INT TERM; [ -n "$_loop" ] && _autoclaude_tracon_stop "$_loop"; return 130' INT
  trap 'trap - INT TERM; [ -n "$_loop" ] && _autoclaude_tracon_stop "$_loop"; return 143' TERM
  # ponytail: the trap above does not explicitly kill/wait the backgrounded
  # uv TUI or restore `set -m` before its `return` — folding that in risks
  # the INT/TERM return-code contract (scenarios 20/21/24/25) for a process
  # that is short-lived and reaped on shell exit anyway; skipped.

  # `</dev/null`: a background job that reads the tty is stopped with SIGTTIN.
  _AUTOPILOT_TRACON_CHILD=1 autoclaude "$@" </dev/null >"$_ap_dir/wrapper.log" 2>&1 &
  _loop=$!
  [ "$_mset" -eq 1 ] || set +m

  # (5) Belt-and-braces: never pid-INT a live loop.
  if ! kill -0 -"$_loop" 2>/dev/null; then
    wait "$_loop" 2>/dev/null
    trap - INT TERM
    printf 'autoclaude: loop is not a process-group leader; using the plain renderer.\n' >&2
    _AUTOPILOT_TRACON=0 autoclaude "$@"
    return $?
  fi

  # Backgrounded + `wait`-ed, not a plain synchronous foreground command: a
  # signal trapped by the shell while it is blocked inside a synchronous
  # foreground command is deferred until that command exits on its own
  # (measured) — a pid-only TERM would never reach the trap above while the
  # TUI is up. `wait` is interruptible immediately. `set +m` first keeps this
  # background job in THIS shell's own process group (no new pgrp), so it
  # still reads the tty exactly as a foreground command would — no SIGTTIN.
  set +m
  uv run --quiet --no-project "$_tracon_py" --root "$_root" --wrapper-pid "$_loop" <&0 &
  wait $!
  _rc=$?
  [ "$_mset" -eq 1 ] && set -m
  trap - INT TERM

  case "$_rc" in
    130)                                   # ctrl+c inside tracon: stop the loop
      _autoclaude_tracon_stop "$_loop"
      return 130 ;;
    3)                                     # tracon says the loop ended — verify
      if ! kill -0 "$_loop" 2>/dev/null; then
        wait "$_loop"
        local _crc=$?
        _autoclaude_tracon_surface "$_ap_dir/wrapper.log" "$_crc"
        return "$_crc"
      fi ;;                                # still alive => a stray 3: fall through
  esac

  if kill -0 "$_loop" 2>/dev/null; then    # q (or a tracon crash): detach
    [ "$_rc" -eq 0 ] || printf 'autoclaude: tracon exited rc=%s; loop still running.\n' "$_rc" >&2
    printf 'autoclaude: detached. Loop running (pid %s) as a job of THIS shell — closing this\n' "$_loop"
    printf 'terminal ends it. Reattach:\n  uv run --no-project %s --root %s\n' "$_tracon_py" "$_root"
    return 0
  fi
  wait "$_loop"                            # already ended: surface its exit code
  local _crc=$?
  _autoclaude_tracon_surface "$_ap_dir/wrapper.log" "$_crc"
  return "$_crc"
}

# SIGINT to the child's process GROUP. No pid-directed fallback: a pid-directed
# INT is DEFERRED by bash until the child's foreground pipeline ends (measured)
# — that is the known-bad path and must never be added.
_autoclaude_tracon_stop() {
  kill -INT -"$1" 2>/dev/null
  wait "$1" 2>/dev/null
}

# _autoclaude_tracon_surface <wrapper_log_path> <child_rc> — tracon mode
# redirects the loop child's stdout/stderr into wrapper.log (never the
# terminal), so operator-facing diagnostics (the paused resume runbook, the
# died-session state.json/last-session.log pointer) are otherwise swallowed
# when the loop exits on its own. Called only from the loop-child-exited
# paths above; ANY exit with a non-empty log surfaces the log's tail to
# stderr, a missing/empty log stays silent. Not gated on child_rc: the
# operator-pause, park and drained branches all `return 0`, so an rc-gate
# swallowed exactly the exits that most needed a reason (measured: an
# agent-written pause-requested stopped an 18h engram batch silently,
# 2026-08-02).
_autoclaude_tracon_surface() {   # $1=wrapper.log, $2=child rc — surface swallowed diagnostics on every loop exit
  [ -s "$1" ] || return 0
  printf '\n── autoclaude: loop exited (rc %s); last output below ──\n' "$2" >&2
  tail -n 20 "$1" >&2
  return 0
}

# _autopilot_fable_validate_prd <approve-fable|reject-fable> <prd>
# The single usage-message site for _autopilot_fable_decide's three reject
# shapes (empty, `/` or `..` traversal, or off the 00XXX-name.md naming
# convention). The traversal guard runs first on purpose: a bash glob's `*`
# matches `/` too, so `00076-a/../b.md` would otherwise slip past the naming
# pattern while still walking outside dev/local/prds. Exits 0 when <prd> is
# safe to use as a ledger key and an mv path component, 2 otherwise (with
# the usage line already on stderr).
_autopilot_fable_validate_prd() {
  local _verb="$1" _prd="$2"
  case "$_prd" in
    ''|*/*|*..*) ;;
    [0-9][0-9][0-9][0-9][0-9]-*.md) return 0 ;;
  esac
  printf 'usage: autoclaude %s <prd-filename.md>\n' "$_verb" >&2
  return 2
}

# _autopilot_fable_unpark <prds_dir> <prd>
# Moves an approved PRD out of parking (hold/ -> backlog/) and verifies the
# file actually arrived: `mv` exits 0 even when the destination names a
# directory, and the PRD would then be invisible to the next batch. It also
# refuses before touching a destination that is already a regular file:
# unlike a directory target, `mv` overwrites a same-named regular file
# silently and still exits 0, so the post-move existence check alone cannot
# tell that from a real success, and dev/local/ is gitignored, so the
# overwritten PRD would be unrecoverable. Prints the operator-facing outcome
# itself, success on stdout and failure on stderr, and returns 0 on success
# (including "nothing to move"), 2 on a failed or refused un-park.
_autopilot_fable_unpark() {
  local _prds="$1" _prd="$2" _mv_err
  if [ ! -f "$_prds/hold/$_prd" ]; then
    printf 'autoclaude: %s approved; it is not parked in hold/, so nothing was moved.\n' "$_prd"
    return 0
  fi
  if [ -f "$_prds/backlog/$_prd" ]; then
    printf 'autoclaude: %s approved, but backlog/%s already exists; move it aside by hand instead of overwriting it.\n' "$_prd" "$_prd" >&2
    return 2
  fi
  _mv_err=$(mv "$_prds/hold/$_prd" "$_prds/backlog/$_prd" 2>&1 >/dev/null)
  # `mv` can exit 0 and still not deliver (a destination that names a
  # directory), so there is a real failure path with no error text to quote.
  # Say that plainly rather than rendering an empty parenthetical.
  [ -n "$_mv_err" ] || _mv_err="mv reported no error but the file did not arrive"
  if [ ! -f "$_prds/backlog/$_prd" ]; then
    printf 'autoclaude: %s approved, but the un-park failed (%s); move it to %s by hand.\n' "$_prd" "$_mv_err" "$_prds/backlog" >&2
    return 2
  fi
  printf 'autoclaude: %s approved and un-parked into backlog/.\n' "$_prd"
}

# _autopilot_fable_decide <approve-fable|reject-fable> <prd>
# The operator's one-command decision on a pending Fable rescue. Positional args
# only — it runs outside any loop, so it reads no loop-local state: the autopilot
# dir comes from _walk_up.py (it therefore works from any subdirectory of the
# repo) and every ledger change goes through fablectl.py, the ledger's sole
# writer. `approve-fable` also un-parks the PRD (hold/ -> backlog/) and VERIFIES
# the file arrived: `mv` exits 0 when the destination name is a directory, and
# the PRD would then be invisible to the next batch. A failed un-park never rolls
# the decision back; the operator finishes the move by hand. <prd> is used both
# as a ledger key and as an mv path component, so it is validated up front
# (no `/`, no `..`, and the PRD naming convention) before either use, and a
# resolver failure or empty answer from _walk_up.py is refused before any path
# is derived from it. Exit 0 on success, 2 on every failure.
_autopilot_fable_decide() {
  local _verb="$1" _prd="$2" _status _ap_dir _ledger _prds _err _rc _cur _skill
  case "$_verb" in
    approve-fable) _status=approved ;;
    *)             _status=rejected ;;
  esac
  # <prd> becomes a ledger key (below) and an mv path component (further
  # down); validated once up front so there is a single usage-message site.
  _autopilot_fable_validate_prd "$_verb" "$_prd" || return 2
  # Tolerant like _autoclaude_tracon: with no plugin the _walk_up.py call below
  # fails and the existing "could not be resolved" refusal fires (exit 2).
  _skill=$(_autopilot_skill_root 2>/dev/null)

  _ap_dir=$(python3 "$_skill/scripts/_walk_up.py" --bash 2>/dev/null)
  # A resolver that fails outright and one that exits 0 but prints nothing
  # both land here as an empty string. Trusting either blindly would derive
  # _ledger/_prds rooted at `/` (a bare "/ledger/fable-requests.json" and
  # "/prds/hold|backlog") and hand that to fablectl. Refuse before either
  # path is built and before fablectl is ever invoked.
  if [ -z "$_ap_dir" ]; then
    printf 'autoclaude: the autopilot directory could not be resolved (_walk_up.py failed or returned nothing).\n' >&2
    return 2
  fi
  _ledger="$_ap_dir/ledger/fable-requests.json"
  _prds="${_ap_dir%/autopilot}/prds"

  _err=$(python3 "$_skill/scripts/fablectl.py" "$_ledger" decide "$_prd" "$_status" 2>&1 >/dev/null)
  _rc=$?
  if [ "$_rc" -eq 3 ]; then
    # fablectl's refusal does not carry the entry's status, so read THIS PRD's
    # own status back (a neighbour's is not it) and say plainly when nothing was
    # ever filed.
    _cur=$(python3 "$_skill/scripts/fablectl.py" "$_ledger" show "$_prd" 2>/dev/null | jq -r '.status // empty')
    if [ -n "$_cur" ]; then
      printf 'autoclaude: %s is already %s; leaving it alone.\n' "$_prd" "$_cur" >&2
    else
      printf 'autoclaude: no rescue request on file for %s.\n' "$_prd" >&2
    fi
    return 2
  fi
  if [ "$_rc" -ne 0 ]; then
    printf '%s\n' "$_err" >&2
    return 2
  fi

  if [ "$_status" = rejected ]; then
    printf 'autoclaude: %s rejected; it stays parked in hold/.\n' "$_prd"
    return 0
  fi
  _autopilot_fable_unpark "$_prds" "$_prd"
}

autoclaude() {
  # Operator subcommands FIRST: they decide a pending Fable rescue and return
  # without ever starting or attaching to a loop.
  case "${1:-}" in
    approve-fable|reject-fable) _autopilot_fable_decide "$1" "${2:-}"; return $? ;;
  esac

  local _tracon=0
  case "${_AUTOPILOT_TRACON:-auto}" in
    0) _tracon=0 ;;                                                    # escape hatch
    1) _tracon=1 ;;                                                    # forced (tests)
    *) { [ -t 1 ] && command -v uv >/dev/null 2>&1; } && _tracon=1 ;;  # auto-detect
  esac
  if [ "$_tracon" -eq 1 ] && [ -z "$_AUTOPILOT_TRACON_CHILD" ]; then
    _autoclaude_tracon "$@"
    return $?
  fi

  export _AUTOPILOT_LOOP=$BASHPID

  # Child pgrp self-guard: refuse to run a loop that cannot be stopped (the
  # tracon parent signals the whole process GROUP, never a bare pid).
  # Use $_AUTOPILOT_LOOP (the loop's own pid, captured just above in a plain
  # assignment) on BOTH sides: a bare $BASHPID inside the command substitution
  # would expand to the substitution's subshell, not this loop — it only read
  # correctly before because the subshell inherits the loop's process group.
  if [ -n "$_AUTOPILOT_TRACON_CHILD" ]; then
    if [ "$_AUTOPILOT_LOOP" != "$(ps -o pgid= -p "$_AUTOPILOT_LOOP" 2>/dev/null | tr -d ' ')" ]; then
      printf 'autoclaude: refusing to run a loop that cannot be stopped (not a process-group leader).\n' >&2
      return 1
    fi
  fi

  # Loop ownership lives in the CLI (PRD 00106): cli/loop.py drives the
  # PRD-00014 decision table, per-phase model routing, the wall-clock cap,
  # the usage-limit wait, the loop registry and its duplicate guard, the
  # pause/park markers, per-session metrics, and the drained-path purge +
  # agoge run. This wrapper keeps only the operator subcommands above, the
  # tracon presentation front-end, and this hand-off.
  autopilot loop
  local _rc=$?
  unset _AUTOPILOT_LOOP
  return $_rc
}

start_qwen() {
  # Serves the promoted default (qualified 2026-08-31) on :8002, matching
  # ~/.pi/agent/models.json provider llamacpp8002. No --alias, ever.
  "$HOME/.local/share/llama-cpp-head/bin/llama-server" \
    -hf unsloth/Qwen3.8-27B-GGUF:UD-Q6_K_XL \
    --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.00 \
    --ctx-size 131072 \
    --flash-attn on \
    --cache-type-k q8_0 --cache-type-v q8_0 \
    --jinja \
    --port 8002 \
    --no-log-timestamps 2>&1 |
    gawk '{ print strftime("%H:%M:%S"), $0; fflush() }'
}
