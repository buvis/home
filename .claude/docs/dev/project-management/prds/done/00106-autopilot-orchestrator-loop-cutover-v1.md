---
rework_cap: 5
---

# Autopilot Orchestrator Loop Cutover

> Renumbered 00052 → 00106 on 2026-08-01 (backlog tail resequence; mapping in memory `project_backlog_renumber_2026_08`).
> Source discovery: `dev/local/discovery/00050-autopilot-cli.md` (PRD 2 of 3).
> Depends on: 00051 (state-machine core). Cutover happens **between batches
> only**; the bash loop and the CLI core coexist for up to two batches.

## Overview

### Problem Statement
The bash `autoclaude()` loop and `_autopilot_loop_watchdog()` currently own
orchestration - spawning phase sessions, wall-clock cap, usage-limit wait,
pause file, notifications, model routing - across bash plus prose. That is the
surface that produced the loop-halt and thrash classes. This PRD moves loop
ownership into the CLI: it spawns the routed phase runner, reads state through
the 00051 core, and drives the loop, replacing the bash wrapper loop.

### Target Users
The unattended autopilot operator, plus interactive `/run-autopilot` users who
must see identical single-phase behavior.

### Success Metrics
- Consecutive real batches (target 3) drain with zero loop-halt/thrash
  notifications and zero manual un-wedging.
- Cost/latency at or below the pre-CLI baseline, where the compared fields
  (per-PRD session count, token, cost) are emitted by 00018 pre-cutover and the
  baseline is loop-metrics rows dated before this cutover.
- Interactive single-phase runs behave identically (loop ownership stays with
  the human; only the loop-mode driver changes).

## Functional Decomposition

### Capability: Loop ownership
The CLI-driven replacement for the bash loop.

#### Feature: Phase runner spawn
- **Description**: Spawn the routed phase runner for one phase and capture its output.
- **Inputs**: Phase, routed runner + model, wall-clock cap.
- **Outputs**: Runner exit status, tee'd output file.
- **Behavior**: Default runner is `claude -p`; runner selection is an extension point (a routed non-claude runner can be added without a spawn-layer redesign). Tee output; enforce the cap via TERM then KILL.

#### Feature: Loop driver
- **Description**: The read-state / decide / spawn-next loop.
- **Inputs**: State (via 00051 core), pause file, usage-limit signal.
- **Outputs**: The next spawned phase, or loop exit at batch drain / pause.
- **Behavior**: Replaces the bash 5-branch state read with a decision over the 00051 core; no inference, no prose drift.

#### Feature: Per-phase model routing
- **Description**: Choose the model (and runner) per phase.
- **Inputs**: Phase, the 00018 routing contract.
- **Outputs**: The runner + model for the next spawn.
- **Behavior**: Encodes the on-disk 00018 routing table; unknown phase falls back to the default runner/model.

### Capability: Operator controls
The safety and hand-off surfaces that kept the loop alive.

#### Feature: Wall-clock cap
- **Description**: Terminate a phase session that exceeds the cap.
- **Inputs**: Runner PID, cap duration.
- **Outputs**: A killed session and a stall record (via 00051).
- **Behavior**: TERM, grace, then KILL; ports the `test_autoclaude_watchdog` contract.

#### Feature: Usage-limit wait
- **Description**: Detect a usage-limit banner, wait until reset, continue.
- **Inputs**: Session output, `_AUTOPILOT_LIMIT_WAIT_MAX`.
- **Outputs**: A resumed loop after the reset, or an abort if the wait cap is exceeded.
- **Behavior**: Absorbs the `detect_usage_limit.py` contract; sidecar reaped; wait is capped.

#### Feature: Pause file
- **Description**: Honor an operator pause / take-over file.
- **Inputs**: Pause file presence.
- **Outputs**: A cleanly paused loop that yields to the operator.
- **Behavior**: Stall-not-pause policy (00017); the loop stops spawning without wedging.

#### Feature: Notifications
- **Description**: Notify once at real loop exit / batch drain.
- **Inputs**: Loop-exit reason, batch state.
- **Outputs**: A single notification.
- **Behavior**: Self-contained (no import from `hooks/`); never per-phase mis-fire (the notify race class).

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/run-autopilot/cli/
├── loop.py            # Maps to: Loop driver
├── runner.py          # Maps to: Phase runner spawn (routed, default claude -p)
├── routing.py         # Maps to: Per-phase model routing
├── watchdog.py        # Maps to: Wall-clock cap
├── usage_limit.py     # Maps to: Usage-limit wait (absorbs detect_usage_limit.py)
├── pause.py           # Maps to: Pause file
├── notify_out.py      # Maps to: Notifications (self-contained)
└── test_*.py
```

Plus the bash plugin change: `autoclaude()` loop body becomes an `autopilot
loop` invocation (the alias from 00051); the old 5-branch state read is deleted.

### Module: runner
- **Maps to capability**: Loop ownership
- **Responsibility**: Spawn one routed phase runner, tee output, enforce the cap.
- **Exports**:
  - `spawn(phase, runner, model, cap)` - run a phase, return status + output path
  - `route(phase)` - resolve runner + model from the 00018 table

### Module: controls
- **Maps to capability**: Operator controls
- **Responsibility**: Wall-clock cap, usage-limit wait, pause file, and single-shot notification.
- **Exports**:
  - `enforce_cap(pid, cap)` - TERM then KILL
  - `wait_for_reset(output, max_wait)` - usage-limit sleep/continue
  - `is_paused()` - pause-file check
  - `notify_exit(reason)` - one notification at loop exit

### Module: loop
- **Maps to capability**: Loop ownership (driver)
- **Responsibility**: Drive read-state / decide / spawn-next until drain or pause; the bash-loop replacement.
- **Exports**:
  - `run()` - the loop entry invoked by `autopilot loop`

## Dependency Graph

### Foundation Layer (Phase 0)
Depends on 00051 core (external prerequisite).

- **runner / routing**: spawn a routed phase and resolve its model.

### Core Layer (Phase 1)
- **controls**: Depends on [runner]

### Integration Layer (Phase 2)
- **loop**: Depends on [runner, controls, 00051 core] and cuts the bash `autoclaude()` loop over.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Port the subprocess contracts into the CLI suite before any bash path is deleted.

**Tasks**:
- [x] Parity inventory of the on-disk `autoclaude()` (no deps) - Premise:
  external gate first - 00051 in `dev/local/prds/done/`, else defer/stall per
  00017 and run nothing else. The wrapper has accreted behaviors since this
  PRD was written 2026-07-08 (died-retry + park marker (00066), per-phase
  session caps (00067), memory breaker, net-retries, progress-fingerprint
  bound, tracon launch, usage-limit sidecar reap, and promotion/decay/rescue
  relaunch if 00076/00111 (ex-00078) landed). Acceptance: an enumerated behavior list
  derived from the wrapper source at execution time, each row mapped to a CLI
  module + test; this PRD's feature list is a floor, not the spec - any
  wrapper behavior without a port row blocks the Phase 2 bash deletion.
- [x] Port `test_autoclaude_watchdog` and `detect_usage_limit` contracts into the CLI test suite (depends on: 00051) - Acceptance: both contracts pass against the new modules.
- [x] Implement `runner.py` (spawn, tee, cap hook) + `routing.py` (depends on: 00051) - Acceptance: a phase spawns via `claude -p` by default and via an injected alternate runner without code change to the driver.

**Exit Criteria**: A single phase runs under the CLI with routing and cap, contracts green.

### Phase 1: Core
**Goal**: Reimplement the operator-control surfaces.

**Tasks**:
- [x] Implement `watchdog.py`, `usage_limit.py`, `pause.py`, `notify_out.py` (depends on: Phase 0) - Acceptance: cap TERM→KILLs a runaway; usage-limit waits then continues within the wait cap; pause file cleanly stops spawning; exactly one notification fires at loop exit.

**Exit Criteria**: All control contracts pass without importing from `hooks/`.

### Phase 2: Integration
**Goal**: Drive the loop from the CLI and retire the bash loop.

**Tasks**:
- [x] Implement `loop.py` driver over the 00051 core (depends on: Phase 1) - Acceptance: a full batch drains via `autopilot loop` with zero halt/thrash.
- [x] Cut `autoclaude()` over to `autopilot loop` and delete the bash wrapper decision-table read (branch count per the parity inventory); between-batches only (depends on: loop driver) - Acceptance: every parity-inventory row's test is green before the bash deletion; old batch state carries a schema version so a resumed pre-cutover batch is detected; interactive single-phase runs unchanged.

**Exit Criteria**: The bash wrapper no longer contains loop logic; the CLI owns loop-mode orchestration.

## Test Strategy

### Critical Scenarios
- **Happy path**: a real batch drains end to end under `autopilot loop` → Expected: zero halt/thrash notifications.
- **Edge case**: usage-limit banner mid-batch → Expected: wait until reset (within the cap), then resume the same batch.
- **Error case**: a phase exceeds the wall-clock cap → Expected: TERM→KILL, stall recorded, loop continues; interactive single-phase run is unaffected.

## Risks

- **Subprocess management regressions** (tee, TERM→KILL cap, usage-limit wait): Port the watchdog and usage-limit contracts before deleting the bash paths.
- **Mid-batch cutover corruption**: Between-batches-only cutover plus the 00051 schema version stamp; a resumed pre-cutover batch is detected.
- **Notify mis-fire**: `notify_out` is self-contained and fires once at real loop exit, never per phase.
- **Interactive regression**: Loop ownership stays with the human in manual mode; only the loop-mode driver changes.

## Sequencing decision (2026-08-15, operator)

**Cutover BEFORE the next batch; measure 00094/00095 on the CLI loop.** The
fast-track v5 wrap-up put the ordering question to the operator (batch-first
was recommended for single-variable debugging; cutover-first was chosen so
the measurement covers the orchestrator that will actually run long-term).
Consequences for whoever works this PRD:

- The CLI loop's first real batch is the evidence source for THREE open
  items at once: 00094/00095's binding metric (median `cycles_to_converge`
  <= 2, from the `review_converged` rows in `loop-metrics.jsonl`), 00110's
  3 shadow cycles (parked on that evidence), and this PRD's own two-batch
  coexistence window.
- Known cost, accepted at decision time: if that batch does not converge,
  gate and orchestrator must be debugged together - item 11's two-place
  entanglement. Budget for it.
- The premise still gates: between batches only, no batch live on any repo,
  and 00118 out of `wip/` first. A fresh session takes this PRD; do not
  start it at the tail of a long one (house compaction rule).
