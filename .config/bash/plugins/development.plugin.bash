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

autoclaude() {
  export _AUTOPILOT_LOOP=$$
  local _cap_pid=""    # session-cap sidecar pid; referenced by the INT/TERM traps
  local _net_retries=0 # consecutive network-death relaunches (decide branch 5)

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

  trap '_autopilot_loop_cleanup; kill "$_cap_pid" 2>/dev/null; unset _AUTOPILOT_LOOP; trap - INT; kill -INT $$' INT
  trap '_autopilot_loop_cleanup; kill "$_cap_pid" 2>/dev/null; unset _AUTOPILOT_LOOP; trap - TERM; kill -TERM $$' TERM

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

    # Operator pause (PRD 00014): `touch <ap_dir>/pause-requested` is the
    # sanctioned "let me in" signal, honored at the next session boundary.
    # The marker is consumed so a later autoclaude run starts normally.
    if [ -f "$_ap_dir/pause-requested" ]; then
      rm -f "$_ap_dir/pause-requested"
      printf '\nautoclaude: paused by operator. State intact; take over with an interactive /run-autopilot, then re-run autoclaude.\n'
      python3 ~/.claude/hooks/notify.py --send "autopilot ⏸ ${PWD##*/}" "Paused by operator at a session boundary. State intact." 2>/dev/null
      trap - INT TERM
      unset _AUTOPILOT_LOOP
      return 0
    fi

    # Session cap: the only kill path in the headless loop.
    _autopilot_session_cap "$$" "${_AUTOPILOT_SESSION_MAX:-7200}" 30 60 &
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

    # Per-phase launch model (PRD 00018). Safe where the old
    # _autoclaude_pick_model died: the phase comes from the SAME state.json
    # read the relaunch decision uses, not a pre-launch guess from stale
    # state. build/review stay on Opus (the decision gate classifies
    # findings); finalize (done) is mechanical rendering — Sonnet. Unknown
    # or absent phase (including the first-ever launch) → Opus: fail
    # expensive, never fail dumb.
    local _model
    case "$_phase_launched" in
    build) _model="${_AUTOPILOT_MODEL_BUILD:-claude-opus-4-8}" ;;
    review) _model="${_AUTOPILOT_MODEL_REVIEW:-claude-opus-4-8}" ;;
    done) _model="${_AUTOPILOT_MODEL_DONE:-claude-sonnet-5}" ;;
    *) _model="claude-opus-4-8" ;;
    esac

    # Operator view: banner + render_stream.py turn the stream-json events
    # into one-line summaries. The raw log tee'd upstream is untouched (it
    # stays greppable for detect_usage_limit.py and the metrics parse), and
    # `|| cat` degrades to the raw view if the renderer is missing or dies —
    # a dead pipe stage would otherwise SIGPIPE-kill the session.
    printf '\n━━ %s · phase %s · prd %s · %s ━━\n' \
      "$(date '+%H:%M:%S')" "${_phase_launched:-bootstrap}" "${_prd_launched:-no-prd}" "$_model"

    # CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0: wait indefinitely for live
    # subagents after the final result (default caps at 10 min). The review
    # Watcher subagent holds the session open while external-CLI reviewers
    # (background Bash — killed ~5s after the result by design) still run;
    # codex doubt reviews routinely exceed 10 min. The session cap above
    # stays the backstop. (2026-07-12: codex killed at turn end, loop died.)
    WARDEN_UNATTENDED=1 CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 \
      claude -p --permission-mode auto --model "$_model" \
      --output-format stream-json --verbose "/run-autopilot" \
      </dev/null 2>&1 | tee "$_ap_dir/last-session.log" |
      { python3 -u ~/.claude/skills/run-autopilot/scripts/render_stream.py || cat; }

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
    local _ts_end _wall _cost _tokens_out
    _ts_end=$(date +%s)
    _wall=$((_ts_end - _ts_start))
    _cost=$(jq -rR 'fromjson? | select(.type=="result") | .total_cost_usd // empty' "$_ap_dir/last-session.log" 2>/dev/null | tail -n 1)
    _tokens_out=$(jq -rR 'fromjson? | select(.type=="result") | .usage.output_tokens // empty' "$_ap_dir/last-session.log" 2>/dev/null | tail -n 1)
    jq -nc \
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
      2>/dev/null >>"$_ap_dir/loop-metrics.jsonl" || true

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
      unset _AUTOPILOT_LOOP
      return
      ;;
    died)
      printf '\nautoclaude: session died (%s). Backlog NOT drained. Check %s/state.json and %s/last-session.log.\n' "$_detail" "$_ap_dir" "$_ap_dir" >&2
      python3 ~/.claude/hooks/notify.py --send "autopilot ⚠️ ${PWD##*/}" "Stopped: $_detail. Needs attention."
      trap - INT TERM
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
    --port 8001
}
