# Live Dashboard

`tracon` (this skill's `scripts/tracon/`) is the autopilot dashboard. It
replaces the retired `pidash` (PRD 00063). `autoclaude` launches tracon as
its default front-end (PRD 00062): on a tty with `uv` available and
`_AUTOPILOT_TRACON` not `0`, the loop runs backgrounded and tracon holds the
foreground. When any of those preconditions fails, `autoclaude` falls back to
the `render_stream.py` pipe below with zero behavior change.

## Operator keys (foreground tracon)

- `q` / `Ctrl-C` — detach: tracon exits, the loop keeps running, and the
  wrapper prints the reattach command
  (`uv run --no-project scripts/tracon.py --root <root>`).
- `p` — pause: writes `<ap_dir>/pause-requested` (the sanctioned signal); the
  loop pauses at the next session boundary, exactly like `touch pause-requested`.
- `s` (twice) — stop NOW: interrupts the loop's process group with today's
  cleanup (traps fire, orphans reaped, registry entry removed).

Full key reference, status legend, and operational notes: `scripts/README.md`.

On a non-drained exit (paused, died, memory pressure) the wrapper surfaces the
tail of `<ap_dir>/wrapper.log` to the terminal, so the loop's own resume runbook
and diagnostics reach you even though tracon captured its output.

## Loop registry

`autoclaude` writes `~/.claude/autopilot-loops/<pid>.json`
(`{pid, root, ap_dir, started_at}`) at loop start and removes it on every exit
path. Tracon reads it to badge a wrapper-alive loop (`⟳`) on the fleet row and
the detail head, and to union every running loop into the fleet regardless of
gita registration. Override the directory with `_AUTOPILOT_LOOPS_DIR` (export
it — the wrapper and tracon must resolve the same path). A second `autoclaude`
in a root that already has a live registered loop refuses to start.

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

When tracon does not launch (no tty, no `uv`, or `_AUTOPILOT_TRACON=0`),
`autoclaude` pipes the headless stream through `scripts/render_stream.py`
instead. Subagent lines carry a stable per-lane `⟨label⟩` tag (label from the
spawning Task description, `⟨agentN⟩` fallback, stable color per lane), so
parallel phases stay readable without tracon. The raw `last-session.log` tee is
identical on both paths (`detect_usage_limit.py` and the metrics parse depend
on it).
