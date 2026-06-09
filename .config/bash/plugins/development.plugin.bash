cite about-plugin
about-plugin 'functions for software development'

# start Claude Code working around the bugs
# claude() {
#   SHELL=/bin/sh GIT_PAGER=cat command claude --plugin-dir ~/.config/claude/ "$@"
# }

# Pick the Claude model for the next /run-autopilot launch, phase-based:
# judgment phases (catchup, planning, reviews) launch on Opus 4.8 1M; the
# work phase launches on plain Sonnet 4.6 (200K window, subscription-billed
# — the [1m] variant bills API credits, never use it here). Work-session
# coordination is mechanical and per-task implementor dispatch inside /work
# tiers the heavy lifting. The 200K window means the context cap hook sizes
# a ~150K cap; that is intentional — replan-on-overrun (task_aborted →
# Phase 0 replan with the tighter per-task budget) handles overruns, and a
# replan escalates the relaunch to Opus via state.launch_model.
# state.launch_model (haiku|sonnet|opus) overrides the work-phase pick —
# the Phase 2→3 handoff writes it: "opus" for PRD default_model: opus or
# post-replan escalation, "sonnet" otherwise. It is ignored for non-work
# phases so a stale value can never demote a review session.
# The stderr log prints the source label separately from the resolved
# phase so debugging "why did this launch on opus" is unambiguous. The
# source is the literal next_phase value, or one of "<missing>" (no
# state.json found in cwd or any ancestor), "<empty>" (key absent, null,
# or explicit empty string "" — /run-autopilot writes next_phase: "" at
# batch end), or "<parse-error>" (jq failed on an existing file).
#
# state.json is located via the shared walk-up helper (_walk_up.py) so the
# model dispatch survives autoclaude being invoked from a subdirectory. The
# hook (autopilot_context_cap_hook.py) uses the same helper; without the
# walk-up here the entire model-dispatch feature silently no-ops when
# cwd != project root.
#
# It also records the picked model's context window in state.json
# (context_window) so the cap hook can size its per-task cap to the
# window (200K-window -> ~150K cap; 1M-window -> 500K cap).
_autoclaude_pick_model() {
  local raw next_phase source model window launch_override jq_rc autopilot_dir state_file
  state_file=""
  autopilot_dir=$(python3 ~/.claude/skills/run-autopilot/scripts/_walk_up.py --bash)
  if [ -n "$autopilot_dir" ] && [ -f "$autopilot_dir/state.json" ]; then
    state_file="$autopilot_dir/state.json"
  fi
  if [ -z "$state_file" ]; then
    raw=""
    source="<missing>"
  elif ! command -v jq >/dev/null 2>&1; then
    printf 'autoclaude: jq not found in PATH; defaulting to Opus\n' >&2
    source="<jq-missing>"
    raw=""
  else
    raw=$(jq -r '.next_phase // ""' "$state_file" 2>/dev/null)
    jq_rc=$?
    if [ "$jq_rc" -ne 0 ]; then
      source="<parse-error>"
      raw=""
    elif [ -z "$raw" ] || [ "$raw" = "null" ]; then
      # jq -r prints the literal string "null" for JSON-null values when no
      # // fallback is in the query; // "" already coerces null → empty, so
      # this "null" check is defensive for future query simplifications.
      source="<empty>"
      raw=""
    else
      source="$raw"
    fi
  fi
  next_phase="${raw:-catchup}"
  model="claude-opus-4-8"
  window=1000000
  if [ "$next_phase" = "work" ]; then
    launch_override=""
    if [ -n "$state_file" ] && command -v jq >/dev/null 2>&1; then
      launch_override=$(jq -r '.launch_model // ""' "$state_file" 2>/dev/null) || launch_override=""
      [ "$launch_override" = "null" ] && launch_override=""
    fi
    case "$launch_override" in
    opus)
      model="claude-opus-4-8"
      window=1000000
      ;;
    haiku)
      model="claude-haiku-4-5-20251001"
      window=200000
      ;;
    sonnet | "")
      model="claude-sonnet-4-6"
      window=200000
      ;;
    *)
      printf 'autoclaude: invalid launch_model %s; using sonnet\n' "$launch_override" >&2
      model="claude-sonnet-4-6"
      window=200000
      ;;
    esac
  fi
  # Record the launched model's context window in state.json so the
  # Work-phase context cap hook (autopilot_context_cap_hook.py) can size
  # its cap: a 200K-window model is capped below native auto-compact
  # (~165K), a 1M-window model gets a higher cost-bounded cap. The hook
  # cannot read the window from the transcript (the plain model id is
  # recorded, never the [1m] variant), so the launcher records it here.
  if [ -n "$state_file" ] && command -v jq >/dev/null 2>&1; then
    local cw_tmp
    cw_tmp="${state_file}.cwtmp"
    if jq --argjson cw "$window" '.context_window = $cw' "$state_file" >"$cw_tmp" 2>/dev/null; then
      command mv -f -- "$cw_tmp" "$state_file"
    else
      rm -f "$cw_tmp"
      printf 'autoclaude: failed to write context_window to state.json\n' >&2
    fi
  fi
  printf 'autoclaude: source=%s phase=%s launch_model=%s model=%s window=%s\n' "$source" "$next_phase" "${launch_override:-<unset>}" "$model" "$window" >&2
  printf '%s\n' "$model"
}

autoclaude() {
  export _AUTOPILOT_LOOP=$$

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

  trap '_autopilot_loop_cleanup; unset _AUTOPILOT_LOOP; trap - INT; kill -INT $$' INT
  trap '_autopilot_loop_cleanup; unset _AUTOPILOT_LOOP; trap - TERM; kill -TERM $$' TERM

  while true; do
    local signal model_id

    model_id=$(_autoclaude_pick_model)

    claude --model "$model_id" --name "${PWD##*/}" --permission-mode bypassPermissions "/run-autopilot"
    _autopilot_loop_cleanup

    local _ap_dir
    _ap_dir=$(python3 ~/.claude/skills/run-autopilot/scripts/_walk_up.py --bash 2>/dev/null)
    if [ -z "$_ap_dir" ]; then
      # Walk-up failed (python3 missing or import error). Fall back to an
      # absolute path anchored at the current dir rather than a bare
      # relative path, so the signal read/delete does not silently target
      # the wrong directory if cwd has drifted.
      printf 'autoclaude: _walk_up.py failed; falling back to %s/dev/local/autopilot\n' "$PWD" >&2
      _ap_dir="$PWD/dev/local/autopilot"
    fi
    signal=$(cat "$_ap_dir/signal" 2>/dev/null)
    rm -f "$_ap_dir/signal"

    case "$signal" in
    next)
      printf '\nStarting next PRD…\n'
      ;;
    task_aborted)
      # Work-phase context cap fired. The hook has already set
      # stall_reason and appended to task_aborts; /run-autopilot Phase 0
      # in the next session will replan the PRD in place (PRD stays in
      # dev/local/prds/wip/) and resume. Treat as continue-loop.
      printf '\nWork task hit context cap; PRD will be replanned. Continuing…\n'
      ;;
    *)
      printf '\nBacklog drained.\n'
      trap - INT TERM
      unset _AUTOPILOT_LOOP
      return
      ;;
    esac
  done
}
