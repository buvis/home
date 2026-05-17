cite about-plugin
about-plugin 'functions for software development'

# start Claude Code working around the bugs
# claude() {
#   SHELL=/bin/sh GIT_PAGER=cat command claude --plugin-dir ~/.config/claude/ "$@"
# }

# Pick the Claude model for the next /run-autopilot launch by reading
# state.next_phase. Work phase -> Sonnet 4.6 (200K standard tier); every
# other phase -> Opus 4.7. Missing/empty next_phase defaults to Opus.
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
_autoclaude_pick_model() {
  local raw next_phase source model jq_rc autopilot_dir state_file
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
  case "$next_phase" in
    work) model="claude-sonnet-4-6" ;;
    *)    model="claude-opus-4-7" ;;
  esac
  printf 'autoclaude: source=%s phase=%s model=%s\n' "$source" "$next_phase" "$model" >&2
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
    local before_sha signal model_id

    before_sha=$(git rev-parse HEAD 2>/dev/null)
    model_id=$(_autoclaude_pick_model)

    claude --model "$model_id" --name "${PWD##*/}" --permission-mode acceptEdits "/run-autopilot"
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

    if [ "$(git rev-parse HEAD 2>/dev/null)" != "$before_sha" ]; then
      local report
      report=$(ls -t dev/local/autopilot/reports/*-report.md 2>/dev/null | head -1)

      CLEANUP_SINCE="$before_sha" AUTOPILOT_REPORT="$report" \
        ~/.claude/skills/use-codex/scripts/codex-run.sh -m gpt-5.5 -a \
        -f ~/.claude/skills/run-autopilot/prompts/de-sloppify.md
      _autopilot_loop_cleanup
    fi

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
