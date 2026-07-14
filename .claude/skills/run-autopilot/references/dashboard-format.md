# Live Dashboard

`tracon` (this skill's `scripts/tracon/`) is the autopilot dashboard. It
replaces the retired `pidash` (PRD 00063). PRD 00062 (wip) wires tracon as
the default `autoclaude` front-end; until it lands, the loop terminal shows
the fallback renderer below.

## What tracon shows

- Reads `dev/local/autopilot/state.json` via the tolerant parser in
  `scripts/tracon/model.py` (missing or malformed fields degrade, never crash)
- Phase, cycle vs rework cap, task counts, guard flags (stall, cap-pause)
- Batch progress from the `batch` field; session cost from the raw log tail

## State contract

- Keep `dev/local/autopilot/state.json` updated at phase transitions.
- When writing the `tasks` snapshot, recompute `tasks_total` and
  `tasks_completed` in the same write. The retired pidash PostToolUse sync
  hook no longer does this for you.
- `batch` needs no extra action - readers pick it up from state.

## Fallback: render_stream

`autoclaude` pipes the headless stream through `scripts/render_stream.py`.
Subagent lines carry a stable per-lane `⟨label⟩` tag (label from the spawning
Task description, `⟨agentN⟩` fallback, stable color per lane), so parallel
phases stay readable without tracon.
