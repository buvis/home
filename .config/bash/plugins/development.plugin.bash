cite about-plugin
about-plugin 'functions for software development'

# start Claude Code working around the bugs
# claude() {
#   SHELL=/bin/sh GIT_PAGER=cat command claude --plugin-dir ~/.config/claude/ "$@"
# }

# _autopilot_session_cap <wrapper_pid> <max_secs> <poll_secs> <grace_secs>
# The one remaining kill path (PRD 00014). Headless sessions exit on their own
# at turn end; only a genuinely hung child (stuck tool, wedged child CLI)
# needs reaping. If the wrapper's direct `claude` child is still alive
# <max_secs> after this sidecar starts: SIGTERM, then SIGKILL <grace_secs>
# later if TERM was ignored. No marker files, no transcript parsing, no
# SIGINT etiquette — a capped session is a died session and takes the
# wrapper's no-progress branch.
_autopilot_session_cap() {
  local _self="$BASHPID" # FIRST statement — capture this sidecar subshell's own pid
  # OUTSIDE any $(...): $BASHPID inside a command substitution
  # is the substitution's subshell, NOT this function-subshell.
  local _wpid="$1" _max="$2" _secs="$3" _grace="$4"
  local _start _cpid="" _p
  _start=$(date +%s)
  while true; do
    sleep "$_secs"
    # (Re)resolve claude: the wrapper's direct child, not the sidecar, whose comm is claude.
    if [ -z "$_cpid" ] || ! kill -0 "$_cpid" 2>/dev/null; then
      _cpid=""
      for _p in $(pgrep -P "$_wpid" 2>/dev/null); do
        [ "$_p" = "$_self" ] && continue
        # Exact comm match (design contract: comm == claude), not a `*claude`
        # glob — a bystander like `myclaude` must never be selected. `comm=`
        # is the basename on macOS but may be a full path elsewhere, so accept
        # a trailing `/claude` too.
        case "$(ps -p "$_p" -o comm= 2>/dev/null)" in
        claude | */claude)
          _cpid="$_p"
          break
          ;;
        esac
      done
    fi
    [ -n "$_cpid" ] && kill -0 "$_cpid" 2>/dev/null || break
    if [ $(($(date +%s) - _start)) -ge "$_max" ]; then
      printf '\nautoclaude: session exceeded the %ss wall-clock cap; SIGTERM (session cap).\n' "$_max" >&2
      kill -TERM "$_cpid" 2>/dev/null
      sleep "$_grace"
      if kill -0 "$_cpid" 2>/dev/null; then
        printf '\nautoclaude: session ignored SIGTERM; SIGKILL (session cap).\n' >&2
        kill -KILL "$_cpid" 2>/dev/null
      fi
      break
    fi
  done
}

# _autoclaude_tracon <args...> — foreground the tracon TUI while the loop runs
# backgrounded as a process-group leader. See autoclaude's presentation
# branch (_AUTOPILOT_TRACON=0/1/auto) for the routing decision.
_autoclaude_tracon() {
  local _ap_dir _root _loop _rc _mset _tracon_py="$HOME/.claude/skills/run-autopilot/scripts/tracon.py"
  _ap_dir=$(python3 ~/.claude/skills/run-autopilot/scripts/_walk_up.py --bash 2>/dev/null)
  [ -n "$_ap_dir" ] || _ap_dir="$PWD/dev/local/autopilot"
  _root="${_ap_dir%/dev/local/autopilot}"
  mkdir -p "$_ap_dir" 2>/dev/null

  # (1) Duplicate-loop guard FIRST (cheap; before any uv cost).
  if python3 ~/.claude/skills/run-autopilot/scripts/tracon_wrapper_alive.py "$_root"; then
    printf 'autoclaude: a loop is already running for %s (registry: %s).\n' \
      "$_root" "${_AUTOPILOT_LOOPS_DIR:-$HOME/.claude/autopilot-loops}" >&2
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

  # (4) Parent INT trap installed BEFORE the fork.
  trap 'trap - INT; _autoclaude_tracon_stop "${_loop:-$!}"; return 130' INT

  # `</dev/null`: a background job that reads the tty is stopped with SIGTTIN.
  _AUTOPILOT_TRACON_CHILD=1 autoclaude "$@" </dev/null >"$_ap_dir/wrapper.log" 2>&1 &
  _loop=$!
  [ "$_mset" -eq 1 ] || set +m

  # (5) Belt-and-braces: never pid-INT a live loop.
  if ! kill -0 -"$_loop" 2>/dev/null; then
    wait "$_loop" 2>/dev/null
    trap - INT
    printf 'autoclaude: loop is not a process-group leader; using the plain renderer.\n' >&2
    _AUTOPILOT_TRACON=0 autoclaude "$@"
    return $?
  fi

  uv run --quiet --no-project "$_tracon_py" --root "$_root" --wrapper-pid "$_loop"
  _rc=$?
  trap - INT

  case "$_rc" in
    130)                                   # ctrl+c inside tracon: stop the loop
      _autoclaude_tracon_stop "$_loop"
      return 130 ;;
    3)                                     # tracon says the loop ended — verify
      if ! kill -0 "$_loop" 2>/dev/null; then
        wait "$_loop"
        return $?
      fi ;;                                # still alive => a stray 3: fall through
  esac

  if kill -0 "$_loop" 2>/dev/null; then    # q (or a tracon crash): detach
    [ "$_rc" -eq 0 ] || printf 'autoclaude: tracon exited rc=%s; loop still running.\n' "$_rc" >&2
    printf 'autoclaude: detached. Loop running (pid %s) as a job of THIS shell — closing this\n' "$_loop"
    printf 'terminal ends it. Reattach:\n  uv run --no-project %s --root %s\n' "$_tracon_py" "$_root"
    return 0
  fi
  wait "$_loop"                            # already ended: surface its exit code
  return $?
}

# SIGINT to the child's process GROUP. No pid-directed fallback: a pid-directed
# INT is DEFERRED by bash until the child's foreground pipeline ends (measured)
# — that is the known-bad path and must never be added.
_autoclaude_tracon_stop() {
  kill -INT -"$1" 2>/dev/null
  wait "$1" 2>/dev/null
}

_autopilot_present() {   # the pipeline's last stage; tracon owns the screen in child mode
  if [ -n "$_AUTOPILOT_TRACON_CHILD" ]; then
    cat >/dev/null
  else
    python3 -u ~/.claude/skills/run-autopilot/scripts/render_stream.py || cat
  fi
}

autoclaude() {
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
  if [ -n "$_AUTOPILOT_TRACON_CHILD" ]; then
    if [ "$BASHPID" != "$(ps -o pgid= -p "$BASHPID" 2>/dev/null | tr -d ' ')" ]; then
      printf 'autoclaude: refusing to run a loop that cannot be stopped (not a process-group leader).\n' >&2
      return 1
    fi
  fi

  local _cap_pid=""    # session-cap sidecar pid; referenced by the INT/TERM traps
  local _reg=""         # loop-registry file path; referenced by every exit path and both traps
  local _net_retries=0 # consecutive network-death relaunches (decide branch 5)
  local _fp_prev=""    # progress fingerprint of the previous continue-branch session
  local _fp_repeats=0  # consecutive sessions with an identical fingerprint

  # Kill orphaned (PPID=1) processes tagged with our marker.
  # Uses SIGHUP so shells propagate the signal to their children.
  _autopilot_loop_cleanup() {
    local pid
    while IFS= read -r pid; do
      [ -n "$pid" ] || continue
      ps ewww -p "$pid" -o command= 2>/dev/null | grep -qE "_AUTOPILOT_LOOP=${_AUTOPILOT_LOOP}( |$)" || continue
      kill -HUP "$pid" 2>/dev/null
    done < <(pgrep -u "$USER" -P 1 2>/dev/null)
  }

  _autopilot_loop_teardown() {          # trap-safe: clears traps FIRST, then unwinds
    trap - INT TERM
    _autopilot_loop_cleanup
    kill "$_cap_pid" 2>/dev/null
    [ -n "$_reg" ] && rm -f "$_reg"
    unset _AUTOPILOT_LOOP
  }

  trap '_autopilot_loop_teardown; return 130' INT
  trap '_autopilot_loop_teardown; return 143' TERM

  while true; do
    # Memory circuit-breaker (2026-06-25): refuse to launch a session when the
    # machine is already under memory pressure. An overnight run fanned out
    # concurrent cargo/rustc builds and exhausted RAM (jetsam -> logout ->
    # ENOMEM lockout). Stopping loud beats piling another build-heavy session
    # onto a stressed box. Level: 1 normal, 2 warning, 4 critical.
    local _mem_pressure
    _mem_pressure=$(sysctl -n kern.memorystatus_vm_pressure_level 2>/dev/null)
    if [ -n "$_mem_pressure" ] && [ "$_mem_pressure" -ge 2 ] 2>/dev/null; then
      printf '\nautoclaude: memory pressure (level %s); stopping loop before launching next session. Free RAM, then re-run.\n' "$_mem_pressure" >&2
      python3 ~/.claude/hooks/notify.py --send "autopilot ⚠️ ${PWD##*/}" "Stopped: memory pressure (level $_mem_pressure). Free RAM, then re-run autoclaude." 2>/dev/null
      trap - INT TERM
      [ -n "$_reg" ] && rm -f "$_reg"
      unset _AUTOPILOT_LOOP
      return 1
    fi

    # Resolve the autopilot dir once, BEFORE launch: the pause check, the
    # session-log tee, and the post-exit state read all need it.
    local _ap_dir
    _ap_dir=$(python3 ~/.claude/skills/run-autopilot/scripts/_walk_up.py --bash 2>/dev/null)
    if [ -z "$_ap_dir" ]; then
      # Walk-up failed (python3 missing or import error). Fall back to an
      # absolute path anchored at the current dir rather than a bare
      # relative path, so the state read does not silently target the
      # wrong directory if cwd has drifted.
      printf 'autoclaude: _walk_up.py failed; falling back to %s/dev/local/autopilot\n' "$PWD" >&2
      _ap_dir="$PWD/dev/local/autopilot"
    fi
    mkdir -p "$_ap_dir" 2>/dev/null

    if [ -z "$_reg" ]; then
      local _loops_dir="${_AUTOPILOT_LOOPS_DIR:-$HOME/.claude/autopilot-loops}"
      mkdir -p "$_loops_dir" 2>/dev/null
      _reg="$_loops_dir/$BASHPID.json"
      jq -n --argjson pid "$BASHPID" \
        --arg root "${_ap_dir%/dev/local/autopilot}" \
        --arg ap_dir "$_ap_dir" \
        --arg started_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{pid:$pid, root:$root, ap_dir:$ap_dir, started_at:$started_at}' >"$_reg"
    fi

    # Operator pause (PRD 00014): `touch <ap_dir>/pause-requested` is the
    # sanctioned "let me in" signal, honored at the next session boundary.
    # The marker is consumed so a later autoclaude run starts normally.
    if [ -f "$_ap_dir/pause-requested" ]; then
      rm -f "$_ap_dir/pause-requested"
      printf '\nautoclaude: paused by operator. State intact; take over with an interactive /run-autopilot, then re-run autoclaude.\n'
      python3 ~/.claude/hooks/notify.py --send "autopilot ⏸ ${PWD##*/}" "Paused by operator at a session boundary. State intact." 2>/dev/null
      trap - INT TERM
      [ -n "$_reg" ] && rm -f "$_reg"
      unset _AUTOPILOT_LOOP
      return 0
    fi

    # Session cap: the only kill path in the headless loop.
    # _AUTOPILOT_LOOP (exported at function entry via a plain `=$BASHPID`
    # assignment in the loop's own process) is passed here, NOT a bare
    # $BASHPID: for a backgrounded simple command bash forks first and
    # expands words inside the new async subshell, so a bare "$BASHPID" at
    # this call site would evaluate to the SIDECAR's own pid, not the
    # loop's — breaking pgrep -P and silently disarming the wall-clock cap.
    _autopilot_session_cap "$_AUTOPILOT_LOOP" "${_AUTOPILOT_SESSION_MAX:-7200}" 30 60 &
    _cap_pid=$!

    # Headless launch (PRD 00014): one session = one -p turn = one process
    # that exits at turn end. No signal file, no Stop-hook choreography — the
    # decision table below reads state.json after exit. stream-json+verbose
    # keeps a live, greppable event log: `tail -f` it to watch the running
    # turn, the final result event carries usage/cost, and a usage-limit
    # banner lands in the tail where detect_usage_limit.py --log finds it.
    #
    # WARDEN_UNATTENDED: command-scoped so warden (claude's hook child) turns an
    # unanswerable `ask` into a fast `deny` instead of a forever-hang. NOT
    # exported to the shell, so interactive `claude` outside the loop still
    # prompts normally. (A subagent `chmod +x` ask deadlocked the loop 1h51m,
    # 2026-06-30.)
    local _ts_start _phase_launched _prd_launched
    _ts_start=$(date +%s)
    if [ -f "$_ap_dir/state.json" ]; then
      _phase_launched=$(jq -r '.next_phase // ""' "$_ap_dir/state.json" 2>/dev/null)
      _prd_launched=$(jq -r '.prd // ""' "$_ap_dir/state.json" 2>/dev/null)
    else
      _phase_launched=""
      _prd_launched=""
    fi

    # Per-phase launch model (PRD 00018) + effort. Safe where the old
    # _autoclaude_pick_model died: the phase comes from the SAME state.json
    # read the relaunch decision uses, not a pre-launch guess from stale
    # state. build/review stay on Opus at xhigh (the decision gate
    # classifies findings); finalize (done) is mechanical rendering —
    # Sonnet at medium. Unknown or absent phase (including the first-ever
    # launch) → Opus xhigh: fail expensive, never fail dumb.
    local _model _effort
    case "$_phase_launched" in
    build)
      _model="${_AUTOPILOT_MODEL_BUILD:-claude-opus-4-8}"
      _effort="${_AUTOPILOT_EFFORT_BUILD:-xhigh}"
      ;;
    review)
      _model="${_AUTOPILOT_MODEL_REVIEW:-claude-opus-4-8}"
      _effort="${_AUTOPILOT_EFFORT_REVIEW:-xhigh}"
      ;;
    done)
      _model="${_AUTOPILOT_MODEL_DONE:-claude-sonnet-5}"
      _effort="${_AUTOPILOT_EFFORT_DONE:-medium}"
      ;;
    *)
      _model="claude-opus-4-8"
      _effort="xhigh"
      ;;
    esac

    # --fallback-model rides out primary-model brownouts (a ConnectionRefused
    # relaunch storm killed a batch silently, 2026-07); skipped when it equals
    # the launch model. The metrics line records the REQUESTED model; the
    # result event in the raw log records what actually served the turn.
    local _fallback="${_AUTOPILOT_FALLBACK_MODEL:-claude-sonnet-5}"
    local _fallback_args=()
    [ "$_fallback" != "$_model" ] && _fallback_args=(--fallback-model "$_fallback")

    # Operator view: banner + render_stream.py turn the stream-json events
    # into one-line summaries. The raw log tee'd upstream is untouched (it
    # stays greppable for detect_usage_limit.py and the metrics parse), and
    # `|| cat` degrades to the raw view if the renderer is missing or dies —
    # a dead pipe stage would otherwise SIGPIPE-kill the session.
    printf '\n━━ %s · phase %s · prd %s · %s/%s ━━\n' \
      "$(date '+%H:%M:%S')" "${_phase_launched:-bootstrap}" "${_prd_launched:-no-prd}" "$_model" "$_effort"

    # CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0: wait indefinitely for live
    # subagents after the final result (default caps at 10 min). The review
    # Watcher subagent holds the session open while external-CLI reviewers
    # (background Bash — killed ~5s after the result by design) still run;
    # codex doubt reviews routinely exceed 10 min. The session cap above
    # stays the backstop. (2026-07-12: codex killed at turn end, loop died.)
    WARDEN_UNATTENDED=1 CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 \
      claude -p --permission-mode auto --model "$_model" --effort "$_effort" \
      "${_fallback_args[@]}" \
      --output-format stream-json --verbose "/run-autopilot" \
      </dev/null 2>&1 | tee "$_ap_dir/last-session.log" | _autopilot_present

    kill "$_cap_pid" 2>/dev/null
    wait "$_cap_pid" 2>/dev/null
    _autopilot_loop_cleanup

    # ── Decide (PRD 00014 decision table) — pure reads, no side effects
    # (the network-outage branch may block on a bounded connectivity poll,
    # but mutates nothing) ──
    # signal ∈ continue|paused|done|died; the metrics line records the branch.
    # state_touched guards branches (4)/(5): a healthy session ALWAYS writes
    # state at its hand-off, so an untouched state.json means this session
    # made no progress (limit-hit at start, crash, cap-kill) — without the
    # mtime check a mid-batch limit hit would relaunch into the same banner
    # in a tight loop, because the stale next_phase still reads as valid.
    local _state="$_ap_dir/state.json"
    local _signal="" _detail="" _next="" _phase_end="" _prd="" _batch="" _limit_wait=""
    local _state_touched=0 _mtime
    if [ -f "$_state" ]; then
      # python3 for the mtime: `stat` flags differ between BSD and GNU (and
      # homebrew coreutils shadows the BSD one on this machine).
      _mtime=$(python3 -c 'import os,sys;print(int(os.stat(sys.argv[1]).st_mtime))' "$_state" 2>/dev/null)
      [ -n "$_mtime" ] && [ "$_mtime" -ge "$_ts_start" ] 2>/dev/null && _state_touched=1
    fi
    [ "$_state_touched" -eq 1 ] && _net_retries=0 # any productive session resets the cap
    if [ -f "$_state" ] && jq -e . "$_state" >/dev/null 2>&1; then
      _prd=$(jq -r '.prd // ""' "$_state" 2>/dev/null)
      _batch=$(jq -r '.batch.id // ""' "$_state" 2>/dev/null)
      _phase_end=$(jq -r '.next_phase // ""' "$_state" 2>/dev/null)
      _next="$_phase_end"
      _detail=$(jq -r 'if .phase == "paused" or ((.pause_reason // "") != "") then ((.pause_reason.detail? // .pause_reason? // .cap_pause_reason? // "paused") | tostring) else empty end' "$_state" 2>/dev/null)
      local _stalled
      _stalled=$(jq -r '.stall_reason.stalled? // empty' "$_state" 2>/dev/null)
      if [ -n "$_detail" ]; then
        _signal="paused" # (1) needs a human
      elif [ "$_stalled" = "subagent_prompt_overrun" ]; then
        _signal="continue"
        _detail="replan" # (2) replan in place
      elif [ -z "$_next" ]; then
        _signal="done" # (3) backlog drained
      elif [ "$_state_touched" -eq 1 ]; then
        _signal="continue" # (4) next phase queued
      fi                   # untouched -> falls through to (5)
    fi
    if [ -z "$_signal" ]; then
      # (5) No progress this session (state missing, unreadable, or
      # untouched). A limit-hit -p session exits with the banner in the log
      # tail — that is scheduling, not failure. Anything else died: halt
      # loud and leave state.json in place for inspection.
      local _reset
      _reset=$(python3 ~/.claude/skills/run-autopilot/scripts/detect_usage_limit.py --log "$_ap_dir/last-session.log" "$PWD" 2>/dev/null)
      case "$_reset" in *[!0-9]*) _reset="" ;; esac
      if [ -n "$_reset" ]; then
        _limit_wait=$((_reset - $(date +%s) + 120))
        [ "$_limit_wait" -lt 60 ] && _limit_wait=60
        if [ "$_limit_wait" -le "${_AUTOPILOT_LIMIT_WAIT_MAX:-21600}" ]; then
          _signal="continue"
          _detail="usage-limit; resuming ~$(date -r "$_reset" '+%H:%M' 2>/dev/null)"
        else
          _signal="died"
          _detail="usage-limit reset beyond _AUTOPILOT_LIMIT_WAIT_MAX (${_AUTOPILOT_LIMIT_WAIT_MAX:-21600}s)"
          _limit_wait=""
        fi
      else
        # Network-outage tolerance (2026-07-12): a result event carrying a
        # connection-level failure means the session never reached the API
        # ($0, zero tokens, state untouched) — infrastructure down, not a
        # stuck loop. Poll connectivity (bounded; wall_secs absorbs the wait)
        # and relaunch. The consecutive-retry cap stops relaunch-thrash when
        # TCP works but the API keeps refusing; any session that touches
        # state resets it.
        local _api_fail=""
        _api_fail=$(jq -rR 'fromjson? | select(.type=="result" and .is_error==true) | .result // ""' "$_ap_dir/last-session.log" 2>/dev/null | tail -n 1)
        if printf '%s' "$_api_fail" | grep -qiE 'unable to connect|connection ?(refused|reset|error)|econn|etimedout|enotfound|eai_again|network is unreachable|fetch failed'; then
          if [ "$_net_retries" -lt "${_AUTOPILOT_NET_RETRIES_MAX:-3}" ]; then
            _net_retries=$((_net_retries + 1))
            local _net_max="${_AUTOPILOT_NET_WAIT_MAX:-1800}" _net_deadline _net_ok=0
            _net_deadline=$(($(date +%s) + _net_max))
            printf '\nautoclaude: API unreachable (%s). Polling connectivity, max %ss (retry %s/%s)…\n' \
              "$_api_fail" "$_net_max" "$_net_retries" "${_AUTOPILOT_NET_RETRIES_MAX:-3}" >&2
            while :; do
              if curl -m 5 -s -o /dev/null https://api.anthropic.com; then
                _net_ok=1
                break
              fi
              [ "$(date +%s)" -ge "$_net_deadline" ] && break
              sleep 30
            done
            if [ "$_net_ok" -eq 1 ]; then
              _signal="continue"
              _detail="network restored (retry $_net_retries)"
            else
              _signal="died"
              _detail="API unreachable for ${_net_max}s"
            fi
          else
            _signal="died"
            _detail="repeated API connection failures (${_AUTOPILOT_NET_RETRIES_MAX:-3} relaunches)"
          fi
        else
          _signal="died"
          if [ ! -f "$_state" ]; then
            _detail="no state.json"
          elif jq -e . "$_state" >/dev/null 2>&1; then
            _detail="session made no progress (state.json untouched)"
          else
            _detail="state.json unreadable"
          fi
        fi
      fi
    fi

    # Progress-fingerprint bound (2026-07-14): branch (4) relaunches are
    # self-healing by design, but nothing bounded a session that touches
    # state without advancing ANY progress counter — the retired pre-00014
    # thrash guard's old job. Fingerprint = the fields that must move for
    # the batch to progress; N identical fingerprints in a row = the loop
    # is burning sessions on nothing. Cap deliberately generous (the 2026-06
    # guard fired at 3 and its halts were mostly benign):
    # _AUTOPILOT_PHASE_REPEATS_MAX, default 5. Any progress resets it.
    if [ "$_signal" = "continue" ] && [ "$_state_touched" -eq 1 ] && [ "$_detail" != "replan" ]; then
      local _fp
      _fp=$(jq -r '[.prd, .next_phase, (.tasks_completed // -1), (.review_cycles // -1), (.cycle // -1), ((.cap_rotations // []) | length), (.replan_count // -1)] | map(tostring) | join("|")' "$_state" 2>/dev/null)
      if [ -n "$_fp" ] && [ "$_fp" = "$_fp_prev" ]; then
        _fp_repeats=$((_fp_repeats + 1))
        if [ "$_fp_repeats" -ge "${_AUTOPILOT_PHASE_REPEATS_MAX:-5}" ]; then
          _signal="paused"
          _detail="no measurable progress across ${_fp_repeats} consecutive sessions (fingerprint ${_fp}); inspect state.json"
        fi
      else
        _fp_repeats=0
      fi
      _fp_prev="$_fp"
    else
      _fp_repeats=0
      _fp_prev=""
    fi

    # Loop metrics (PRD 00013): append exactly one JSONL line per session,
    # after the decision and before any exit path, so every branch records
    # the line. Observation only — the append can never block or fail the
    # loop (the one sanctioned silent failure, scoped to itself).
    # PRD 00018: the line always carries "model"; "cost_usd"/"tokens_out"
    # are added only when the session log's LAST result event provides
    # them (parse failure degrades to model-only, never blocks the loop).
    # Sessions re-invoked by background-task notifications emit one result
    # event PER re-invoke, each with the cumulative conversation cost —
    # `tail -n 1` takes the final one (a multi-line match used to fail the
    # numeric test below and silently drop both keys, 2026-07-13).
    local _ts_end _wall _cost _tokens_out _mline
    _ts_end=$(date +%s)
    _wall=$((_ts_end - _ts_start))
    _cost=$(jq -rR 'fromjson? | select(.type=="result") | .total_cost_usd // empty' "$_ap_dir/last-session.log" 2>/dev/null | tail -n 1)
    _tokens_out=$(jq -rR 'fromjson? | select(.type=="result") | .usage.output_tokens // empty' "$_ap_dir/last-session.log" 2>/dev/null | tail -n 1)
    _mline=$(jq -nc \
      --argjson ts_start "$_ts_start" \
      --argjson ts_end "$_ts_end" \
      --argjson wall_secs "$_wall" \
      --arg prd "$_prd" \
      --arg batch "$_batch" \
      --arg phase_launched "$_phase_launched" \
      --arg phase_end "$_phase_end" \
      --arg signal "$_signal" \
      --arg model "$_model" \
      --arg cost "$_cost" \
      --arg tokens_out "$_tokens_out" \
      '{ts_start:$ts_start,ts_end:$ts_end,wall_secs:$wall_secs,prd:$prd,batch:$batch,phase_launched:$phase_launched,phase_end:$phase_end,signal:$signal,model:$model}
       + (if ($cost | test("^[0-9.]+$")) then {cost_usd: ($cost | tonumber)} else {} end)
       + (if ($tokens_out | test("^[0-9]+$")) then {tokens_out: ($tokens_out | tonumber)} else {} end)' \
      2>/dev/null) || _mline=""
    if [ -n "$_mline" ]; then
      printf '%s\n' "$_mline" 2>/dev/null >>"$_ap_dir/loop-metrics.jsonl" || true
      # Durable ledger (2026-07-14): purge-devlocal GC'd every repo's
      # loop-metrics at 14d before the quarter's eval could read them.
      # ledger/ is GC-exempt, so outcome data survives for tuning (00079)
      # and debriefs. Same sanctioned-silent-failure scope as above.
      { mkdir -p "$_ap_dir/ledger" &&
        printf '%s\n' "$_mline" >>"$_ap_dir/ledger/loop-metrics.jsonl"; } 2>/dev/null || true
    fi

    # ── Act on the branch ──
    case "$_signal" in
    continue)
      if [ -n "$_limit_wait" ]; then
        printf '\nautoclaude: usage limit hit; waiting %s min (%s).\n' "$((_limit_wait / 60))" "$_detail"
        python3 ~/.claude/hooks/notify.py --send "autopilot ⏳ ${PWD##*/}" "Usage limit; $_detail." 2>/dev/null
        sleep "$_limit_wait"
      elif [ "$_detail" = "replan" ]; then
        printf '\nWork task prompt overran budget; PRD will be replanned. Continuing…\n'
      else
        printf '\nContinuing (next phase: %s)…\n' "$_next"
      fi
      ;;
    paused)
      printf '\nautoclaude: session paused — %s.\n' "$_detail" >&2
      printf 'To resume (re-running autoclaude now would just pause again):\n' >&2
      printf '  1. claude            # interactive session in this repo\n' >&2
      printf '  2. /run-autopilot    # resumes from state.json; blockers become questions\n' >&2
      printf '  3. autoclaude        # after the decision, to continue unattended\n' >&2
      python3 ~/.claude/hooks/notify.py --send "autopilot ⚠️ ${PWD##*/}" "Paused: $_detail"
      trap - INT TERM
      [ -n "$_reg" ] && rm -f "$_reg"
      unset _AUTOPILOT_LOOP
      return 1
      ;;
    done)
      mkdir -p "$_ap_dir/reports" 2>/dev/null
      mv "$_state" "$_ap_dir/reports/${_batch:-$(date +%Y%m%d%H%M)}-state-final.json" 2>/dev/null
      printf '\nBacklog drained.\n'
      python3 ~/.claude/hooks/notify.py --send "autopilot ✅ ${PWD##*/}" "Backlog drained."
      python3 ~/.claude/skills/purge-devlocal/scripts/purge_devlocal.py --repo "$PWD" --apply || true
      trap - INT TERM
      [ -n "$_reg" ] && rm -f "$_reg"
      unset _AUTOPILOT_LOOP
      return
      ;;
    died)
      printf '\nautoclaude: session died (%s). Backlog NOT drained. Check %s/state.json and %s/last-session.log.\n' "$_detail" "$_ap_dir" "$_ap_dir" >&2
      python3 ~/.claude/hooks/notify.py --send "autopilot ⚠️ ${PWD##*/}" "Stopped: $_detail. Needs attention."
      trap - INT TERM
      [ -n "$_reg" ] && rm -f "$_reg"
      unset _AUTOPILOT_LOOP
      return 1
      ;;
    esac
  done
}

start_qwen() {
  llama-server \
    -hf unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL \
    --alias "unsloth/Qwen3.6-27B-MTP" \
    --spec-type draft-mtp \
    --spec-draft-n-max 2 \
    --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.00 \
    --ctx-size 131072 \
    --flash-attn on \
    --cache-type-k q8_0 --cache-type-v q8_0 \
    --jinja \
    --port 8001 \
    --no-log-timestamps 2>&1 |
    gawk '{ print strftime("%H:%M:%S"), $0; fflush() }'
}
