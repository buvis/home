# Tracon: autopilot loop observer (fleet dashboard + loop detail)

> Name: **tracon** (Terminal Radar Approach Control) - the radar facility tracking every aircraft in its airspace; here, every autoclaude loop on the machine.

## Overview

### Problem Statement

Watching autoclaude loops today means reading a raw stream-json render in the loop terminal. Parallel reviewers interleave anonymous lines, a silent session is indistinguishable from a dead one, batch cost is invisible until sessions end, and multiple loops (four repos had parked or live loops on 2026-07-13) cannot be seen in one place. pidash, the previous dashboard, is broken against the current state schema and shows "no active PRD cycle" on every current run.

Context: a working spike exists at `dev/local/spikes/autopilot-tui/` (SPEC.md records four refine rounds of observed behavior; tui.py is the prototype). This PRD rebuilds it properly. Spike code never merges; delete the spike dir once this PRD's implementation is verified (premise: the spike dir still exists and holds no unported decisions — re-check SPEC.md at execution, port any decision not yet in this PRD's contract, then delete).

### Target Users

Solo operator running one or more autoclaude loops locally, checking progress from a second terminal (or, after PRD 00062, in the loop's own terminal).

### Success Metrics

- Discovery lists every gita-registered repo (plus `~/.claude`) that has a `dev/local/autopilot/` dir; zero false negatives against a hand-audit.
- Status column never shows a stale terminal signal while a session is in flight (the quiet-vs-died distinction, verified by the truth-table test).
- 100% of subagent log lines carry a lane tag; a 3-reviewer parallel review is attributable line-by-line.
- Detail attach on a 5 MB last-session.log renders in under 2 seconds.
- Batch cost shown includes the live session (from in-log result events), not just completed sessions.

## Functional Decomposition

### Capability: Loop discovery and status

Find every loop on the machine and classify its state truthfully.

#### Feature: Discover loops
- **Description**: Enumerate repo roots that can host a loop.
- **Inputs**: `~/.config/gita/repos.csv` (CSV, absolute repo path in column 1), plus `~/.claude`.
- **Outputs**: Ordered list of roots having a `dev/local/autopilot/` directory.
- **Behavior**: Read the registry each refresh (cheap); missing registry degrades to `~/.claude` only. No process scanning (wrapper-alive badging arrives with PRD 00062's registry file).

#### Feature: Classify loop status
- **Description**: One truthful status per loop.
- **Inputs**: `state.json`, `loop-metrics.jsonl` (batch-scoped by `batch.id`), `last-session.log` mtime.
- **Outputs**: Status label + style + sort rank: `⚠ attention`, `● live` (log younger than 20s), `◐ quiet` (log older, but strictly newer than the last metrics `ts_end` + 2s — a session is in flight but silent; the 2s slack is a truncation guard for the whole-second `ts_end` stamp, not a grace period), `■ died HH:MM`, `⏸ paused HH:MM`, `✔ drained HH:MM`, `○ idle`, `○ no state`, `○ no log`.
- **Behavior**: A terminal signal (`died`/`paused`/`done`) from the last metrics row is shown only when nothing wrote to the log after that row ended (observed failure otherwise: a Watcher-held silent session displayed last night's death). Sort rank: attention/died/paused first, then live/quiet, then idle, then drained.

### Capability: Fleet dashboard

#### Feature: Loop table
- **Description**: One row per discovered loop.
- **Inputs**: `loop_status()` of each root, refreshed every 2s.
- **Outputs**: DataTable columns: project, status, phase, prd, task, cycle, cost, sessions.
- **Behavior**: Attention-first sort (pidash's attention → active → done order); cursor position survives refresh; Enter opens the loop's detail screen; with exactly one discovered loop (or `--root`), skip straight to detail.

### Capability: Loop detail view

#### Feature: Header panel
- **Description**: The loop's vitals in 3-4 rows.
- **Inputs**: `state.json`, batch-scoped metrics, live stream aggregates.
- **Outputs**: phase, prd, task n/m, cycle, backlog/wip counts, sessions, elapsed runtime (first batch `ts_start` → now-if-live) AND active runtime (Σ `wall_secs` + live session age; the live slice only when the session began under observation — file birthtime lies, tee truncates in place), batch cost + `+$X.XX live` chip (latest in-log result event's cumulative `total_cost_usd`, shown only while live to avoid double-count), model, tokens ↑(input+cache-creation) ⤓(cache-read) ↓(output) deduped by message id, ctx (last message's input+cache totals), status dot, `⚠ needs attention` flag, guard surfacing: show `thrash_halt`, `phase_guard`, `cap_pause_reason`, `stall_reason`, and `cycle`/`rework_cap` when present (the runaway guards pidash dropped).
- **Behavior**: Rows are no-wrap with ellipsis; the agents row appears only when parallel work is live (header height adjusts).

#### Feature: Event log pane
- **Description**: Human-readable session log with scrollback.
- **Inputs**: `last-session.log` tailed with truncation detection (tee truncates in place per session: same inode, shrunken size; also handle inode swap and file absence).
- **Outputs**: RichLog lines via the same one-line renderer as the in-pipe view (`render_stream.render()` — import, do not fork); `── new session ──` marker on truncation; pre-attach content dimmed behind a `── replay: log content from before attach ──` marker (stream events carry no timestamps, so replayed lines must not masquerade as live).
- **Behavior**: Auto-follow with `f` toggle; scrollback bounded (max_lines ~5000); a line that fails to parse or render passes through raw (fail-open, same contract as render_stream).

#### Feature: Parallel-agent attribution
- **Description**: Make concurrent subagents and background reviewers readable.
- **Inputs**: Parent `tool_use` blocks named Task/Agent (label from `input.description`), subagent events (`parent_tool_use_id`), `tool_result` blocks (lane retirement), system events `task_notification` / `task_updated` / `background_tasks_changed`.
- **Outputs**: Stable colored `⟨label⟩` prefix per lane on every subagent line; an `agents` header row listing live lanes (`label ⚒LastTool×count`) and running background tasks (`summary ▷status`).
- **Behavior**: Unknown parent ids auto-register as `⟨agentN⟩`; lanes retire when their tool_result returns; background-task entries drop when status becomes stopped/killed/completed/failed. `background_tasks_changed` entries are assumed keyed `task_id` or `id` with `summary`/`status` (guess — only the empty-list shape was observed; verify against a live capture during implementation).

### Capability: Schema-current data layer

#### Feature: State parsing per current contract
- **Description**: Parse state.json against `skills/run-autopilot/references/state-schema.md`, not the pidash-era schema.
- **Inputs**: state.json files (current shape: `prd` is a bare string; `phase` ∈ build/review/done/paused, plus `stopped` written by legacy session-cleanup).
- **Outputs**: Tolerant dataclass/dict model; unknown fields ignored, missing fields defaulted; never raise on a real file.
- **Behavior**: Drive display off `phase` + `next_phase` + `phases_completed`; a phase pipeline strip (build → review → done) with pidash's spinner/checkmark idiom and attention red-tint overlay ports the two highest-value pidash visuals. Decisions/doubts/cycle-history panels are explicitly deferred to a follow-up PRD (pidash shows nothing today, so no capability is lost).

## Structural Decomposition

### Repository Structure

```
.claude/skills/run-autopilot/scripts/
├── tracon.py                     # PEP 723 entry (uv run …/tracon.py), arg parsing, --once
└── tracon/                       # Maps to: all capabilities
    ├── __init__.py
    ├── discovery.py              # Maps to: Loop discovery and status
    ├── stream.py                 # Maps to: Event log pane + Parallel-agent attribution (LogTail, SessionUsage, AgentTracker)
    ├── model.py                  # Maps to: Schema-current data layer
    ├── panels.py                 # Maps to: Header panel (build_head, formatters, phase strip)
    ├── screens.py                # Maps to: Fleet dashboard + Loop detail (Textual App/Screens)
    ├── test_discovery.py
    ├── test_stream.py
    ├── test_model.py
    └── test_panels.py
```

### Module: discovery
- **Maps to capability**: Loop discovery and status
- **Responsibility**: gita/`~/.claude` root enumeration and per-root status classification
- **Exports**: `discover_loops()`, `loop_status(root)`

### Module: stream
- **Maps to capability**: Loop detail view (log pane, attribution)
- **Responsibility**: tail -F semantics across truncations; usage/cost aggregation; lane and background-task tracking
- **Exports**: `LogTail`, `SessionUsage`, `AgentTracker`, `render_line()`

### Module: model
- **Maps to capability**: Schema-current data layer
- **Responsibility**: tolerant state.json/loop-metrics parsing per state-schema.md
- **Exports**: `read_state()`, `read_metrics()`, guard-field accessors

### Module: panels
- **Maps to capability**: Loop detail view (header)
- **Responsibility**: render header panel, phase strip, attention overlay styles, formatters
- **Exports**: `build_head()`, `phase_strip()`, `fmt_dur()`, `fmt_tok()`

### Module: screens
- **Maps to capability**: Fleet dashboard + Loop detail view
- **Responsibility**: Textual App, DashboardScreen, DetailScreen, key bindings
- **Exports**: `run_app()`

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **model**: state/metrics parsing all others consume
- **stream**: log tailing and event aggregation (depends only on render_stream import)

### Core Layer (Phase 1)
- **discovery**: Depends on [model]
- **panels**: Depends on [model, stream]

### Integration Layer (Phase 2)
- **screens**: Depends on [discovery, panels, stream]
- **tracon.py entry**: Depends on [screens]

## Implementation Phases

### Phase 0: Foundation
**Goal**: Parsing and tailing proven by tests before any UI exists.

**Tasks**:
- [ ] Build `model.py` against state-schema.md with tolerant parsing (no deps) - Acceptance: pytest passes on fixtures for current-shape state.json (prd string, each phase value), legacy `phase:"stopped"` files, malformed JSON, and missing files; guard fields exposed.
- [ ] Build `stream.py`: LogTail (in-place truncation, inode swap, absence), SessionUsage (message-id dedupe, per-re-invoke result cost), AgentTracker (lanes, retirement, background tasks) (no deps) - Acceptance: pytest covers truncation reset, fixture-driven cost/token totals matching the 00054 review-session capture, lane registration/retirement, and the multi-result-event cost case.

**Exit Criteria**: `pytest skills/run-autopilot/scripts/tracon/` green with no UI code present.

### Phase 1: Core
**Goal**: Discovery and rendering logic complete.

**Tasks**:
- [ ] Build `discovery.py` (gita repos.csv + ~/.claude; status classification with the quiet-vs-died rule) (depends on: Phase 0) - Acceptance: truth-table test covering all nine statuses, including "log newer than last metrics ts_end → quiet, never died".
- [ ] Build `panels.py` (header rows, live-cost chip, phase strip, attention styling) (depends on: Phase 0) - Acceptance: rendered-output tests for the cost chip (shown live only), active-runtime (no live slice when session start unknown), and no-wrap rows.

**Exit Criteria**: `--once` mode (plain rich, no textual import) prints fleet table + detail frame from real files.

### Phase 2: Integration
**Goal**: The Textual app, end to end.

**Tasks**:
- [ ] Build `screens.py` + `tracon.py` entry (dashboard, detail, Enter/Esc/f/q, single-loop auto-detail, PEP 723 header) (depends on: Phase 1) - Acceptance: Textual pilot (`run_test`) smoke test boots the app headless, sees dashboard rows, opens detail, toggles follow.
- [ ] Verify against a live loop and delete the spike dir (depends on: screens) - Acceptance: operator-visible run documented in the work log (dashboard + detail against a real session); `dev/local/spikes/autopilot-tui/` removed after the premise re-check described in Overview.

**Exit Criteria**: `uv run ~/.claude/skills/run-autopilot/scripts/tracon.py` shows the fleet dashboard; Enter/Esc/f/q behave as specified.

## Test Strategy

### Critical Scenarios
- **Happy path**: live loop with parallel reviewers → dashboard row `● live`; detail shows lane-tagged lines and agents row → Expected: every subagent line tagged, agents row lists lanes + background tasks.
- **Edge case**: session silent 10 minutes with in-flight Watcher; last metrics row says died → Expected: `◐ quiet`, not died.
- **Edge case**: log truncated in place mid-watch → Expected: `── new session ──` marker, usage/lanes reset, no duplicate replay.
- **Error case**: state.json malformed / absent; gita registry missing → Expected: row shows `○ no state` / discovery degrades to `~/.claude`; never a crash.

## Risks

- **Textual API drift** (spike pinned `textual>=1.0`, resolved 8.2.8): pin a floor version known to work; pilot smoke test catches breakage.
- **Schema drift recurrence** (what killed pidash): the model module is the single parse point, tested against fixture files copied from real state.json captures; state-schema.md is the named contract.
- **Stream event shape changes** (background_tasks_changed guess above): keep AgentTracker fail-open — unknown shapes degrade to untagged lines, never crash.
