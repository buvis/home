# tracon - the autoclaude loop observer

Textual TUI over running autopilot loops. Strictly read-only: it parses
on-disk artifacts and the session log tee, never edits state, never signals a
process. The only two keys that act on a loop are `p` (writes the sanctioned
`pause-requested` marker) and `s` (sends the same SIGINT the wrapper's own
Ctrl-C handler sends). Everything else is display.

## Start, attach, detach

- `autoclaude` launches tracon automatically on a tty when `uv` is available
  and `_AUTOPILOT_TRACON` is not `0`. The loop runs as a background job of
  that terminal; tracon holds the foreground.
- Attach to a running loop from any terminal:
  `uv run --no-project ~/.claude/skills/run-autopilot/scripts/tracon.py --root ~/.claude`
- One-shot snapshot (no TUI, safe in scripts): add `--once`.
- `--preflight` just verifies rich+textual import; the wrapper uses it.
- `_AUTOPILOT_TRACON=0 autoclaude` skips tracon and pipes the session through
  `render_stream.py` instead (same log tee, plain output).

Detach with `q` (Ctrl-C inside tracon does the same): tracon exits, the loop
keeps running and keeps launching sessions. Code changes to tracon only apply
on the next attach; a running tracon keeps its loaded code.

The wrapper, not tracon, drives the loop. It lives in the terminal that ran
`autoclaude`. Closing that terminal kills the wrapper and the in-flight
session. State survives on disk; the loop just stops progressing.

## Orphans: who continues the loop

`autoclaude` registers itself at `~/.claude/autopilot-loops/<pid>.json` and
removes the entry on every exit path. Tracon classifies a loop as
`⚠ orphaned` when state.json still queues work (a `next_phase`, unfinished
tasks) but no registered wrapper pid is alive. Nothing is lost: run
`autoclaude` in that repo and it resumes from state.json. Detaching tracon
never orphans anything; a dead terminal, crash, or reboot does.

When the wrapper dies while tracon is attached, tracon shows an exit banner
with the runbook line (drained / paused / died / stopped) and exits rc=3;
the wrapper surfaces the tail of `wrapper.log` on non-drained exits.

## Keys

UI (never touch a loop):

| key | action |
|-----|--------|
| enter | open the highlighted loop's detail screen (fleet only) |
| esc | back (detail -> fleet; help/tasks/agents -> close) |
| t | task board: kanban lanes over the state.tasks snapshot |
| a | agent board: subagent and background-CLI lanes (detail only) |
| f | toggle follow (log sticks to newest lines; detail only) |
| ? | help |
| ctrl+p | command palette (theme persists in `~/.claude/tracon-theme`) |
| q / ctrl+c | detach; every loop keeps running |

Loop (act on the attached or highlighted loop):

| key | action |
|-----|--------|
| p | request pause; honored at the session boundary; resume with `autoclaude` |
| s | stop NOW (SIGINT to the loop's process group); press twice to confirm |

## Status legend

- `● live` - session wrote within the last 20s
- `◐ quiet` - session running but output stalled
- `⏳ limit-wait` - usage limit hit; wrapper sleeps until the reset
- `⏸ paused` - deliberate stop, waiting on a decision (`claude` ->
  `/run-autopilot` answers it, then `autoclaude`)
- `⚠ orphaned` - work queued, no autoclaude alive; run `autoclaude`
- `⚠ attention` - needs_attention set (usually a cap-pause)
- `■ died` - session died; check `dev/local/autopilot/last-session.log`
- `✔ drained` - backlog empty, batch archived
- `○ idle / no log` - nothing running

## Reading the detail header

Row 1: `<prd> · task 4/8 · cycle 1/3 [· guards] ▸ current task name`.
Guards appear only when present: stall, cap-pause, paused, thrash, phase.

Row 2, phase strip: `build` expands into catchup/design/plan/work sub-steps
(inferred from state artifacts); `review` expands into the active lens roster
(consensus/blind/doubt/ui/qwen/fable) stamped by the review skill; red strip
means needs_attention.

Row 3 (agents, only while lanes are live): `⟨label⟩ ⚒Tool×n` per subagent,
`label ▷status` per background CLI. Detail lives on the `a` board.

Row 4, batch progress: `batch <stamp>` scopes everything after it (sessions,
elapsed, active, cost) to the current batch, surviving interrupts and
resumes. `$/h` shows after 10 minutes of active time; `+$X.XX live` is the
in-flight session's cost, not yet in loop-metrics.

Row 5, usage: `in ↑` input + cache-creation tokens, `cache ⤓` cache reads,
`out ↓` output (`~` marks a live estimate until the session's result event
anchors the exact count), `ctx x/500.0k` last turn's context vs USAGE_CAP
(the session-rotation cap; tracon mirrors `autopilot_context_cap_hook`).

## Agent board (`a`)

Lanes come from the session log's task lifecycle events. `running` lists
live lanes, `finished` the retired ones, registration order.

- Agent lanes (Claude subagents): full description, subagent type, the live
  activity line (`↳ Reading ...`), and `⚒ tool×n · tokens · duration` off
  task_progress events.
- Bash lanes (CLI reviewers, backgrounded runners): description plus status,
  and a liveness note from statting the runner's `-o` file:
  `out 4.2k · 8s ago` once bytes land (mtime advancing means the CLI is
  alive), `no output yet · 3m` while the file is missing or still empty.
  Fidelity varies by runner: native codex writes the file only at
  completion, and even tee'd runners (gemini/copilot) may look empty for a
  while because a piped CLI block-buffers stdout. Treat the note as "alive
  and producing" evidence, not as a progress bar.

Semantics worth remembering (they bit once, see git log):

- A backgrounded Agent/Bash tool_use gets its tool_result ACK immediately at
  launch; completion arrives later via task_updated / task_notification.
  Never read a tool_result as "finished" for tracked lanes.
- task_progress events exist for agent lanes only. Bash progress has no
  stream signal; the `-o` stat note is the workaround and depends on the
  runners' `-o/--output` flag convention.
- Attaching mid-session replays only the last 512KB of log. Lanes whose
  launch fell outside that window show without notes, or not at all when
  even their task events scrolled out. Attached-from-start (the normal
  autoclaude flow) sees everything.

## On-disk sources (all under `<root>/dev/local/autopilot/`)

- `state.json` - loop state; parsed tolerantly (`tracon/model.py`), malformed
  fields degrade instead of crashing. Contract: `references/state-schema.md`.
- `loop-metrics.jsonl` - one row per session; batch-scoped by `batch` id.
- `last-session.log` - tee of the headless stream-json. Truncated in place
  per session (tracon detects truncation and inode swaps, then resets its
  per-session counters and prints `── new session ──`).
- `wrapper.log` - the wrapper's own diagnostics, surfaced on bad exits.
- `~/.claude/autopilot-loops/<pid>.json` - live-loop registry (see Orphans).

## Code map

```
tracon.py            CLI entry (uv inline deps: rich, textual)
tracon/model.py      tolerant parse: state.json, loop-metrics, cost tail
tracon/discovery.py  fleet discovery + status classification
tracon/stream.py     LogTail (follow w/ truncation), SessionUsage (tokens),
                     AgentTracker (lanes; launch-ack rules live here)
tracon/panels.py     pure rich rendering, no file I/O
tracon/screens.py    Textual app: Collector (per-tick I/O), all screens
render_stream.py     shared line renderer (also the no-tty fallback pipe)
```

Tests, one module each (`test_*.py`), plus `conftest.py` isolating the loop
registry so a live autoclaude never leaks into assertions:

```
uv run --no-project --with rich --with "textual>=1.0,<9" --with pytest \
  pytest ~/.claude/skills/run-autopilot/scripts/tracon/
```

## Troubleshooting

- Fleet row `⚠ orphaned` -> run `autoclaude` in that repo; it resumes.
- `■ died` -> read `dev/local/autopilot/last-session.log`, then `autoclaude`.
- Tracon won't launch from autoclaude -> `uv` missing or preflight failed;
  the wrapper already fell back to render_stream. Check
  `uv run --no-project tracon.py --preflight`.
- Header shows no agents while the log clearly streams subagent lines ->
  you are on a tracon loaded before the lane fixes; detach (`q`), reattach.
- UI keys documented in-app: press `?`.
