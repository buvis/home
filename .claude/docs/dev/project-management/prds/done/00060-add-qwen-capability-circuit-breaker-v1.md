---
catchup: force
---

# Add Qwen Capability Circuit Breaker

> **OVERTAKEN — closed 2026-07-31 triage (verified, not assumed).** The
> escalation initiative (PRD 00065 era) shipped this PRD's entire surface
> while it sat parked: `qwen_gate_failures_consecutive` + `qwen_breaker`
> {tripped, after_task, failed_tasks, batch_id} with trip-at-2 / reset-on-pass
> / rework-never-touches semantics (`skills/work/SKILL.md` step 5.5 counter +
> routing row 3, batch-scoped lazy reset — no Phase 0 edit needed), reroute to
> Claude at the task's ORIGINAL tier with no escalation stamp, ~10 dedicated
> cases in `scripts/test_work_routing.py`, and the batch report's "Capability
> breaker line" rendering exactly this PRD's visibility metric (tripped-after,
> the two failed tasks, N rerouted). The one unbuilt nuance — hosting the
> breaker inside the cli/ state-machine package — is PRD 00089/00052 scope by
> definition. Nothing remains to build.

> **DEFERRED - HARD PREMISE GATE (user decision, 2026-07-12).** Implement
> only after BOTH successor PRDs of the discovery doc
> `dev/local/discovery/00050-autopilot-cli.md` (the state-machine core and
> the loop-ownership PRD, formerly numbered 00051/00052) sit in
> `dev/local/prds/done/`. Those PRDs are parked in `dev/local/prds/hold/` as
> 00051 (state-machine core) and 00052 (loop ownership; 00053 is part 3 of
> the same discovery doc) - match them by their discovery-doc reference in
> case they are renumbered. If this PRD is auto-picked before
> the premise holds, do not implement: record a defer/stall (PRD 00017
> mechanics), leave the tree untouched, and let the loop take the next PRD.
> Rationale: the breaker belongs in the tested Python routing code those
> PRDs create, not in skill prose that they would immediately rewrite.

> Source: `dev/local/qwen-leverage-assessment-2026-07-12.md` (gap G2).

## Overview

### Problem Statement

The qwen lane has an infrastructure breaker (preflight) but no capability
breaker. When qwen keeps producing code that fails the step-5.5 test gate,
each eligible task still pays a full qwen attempt (local inference is slow)
plus the Sonnet redo, task after task, all batch long. One qwen-hostile repo
(heavy macros, unusual conventions) can burn unattended hours re-proving the
same incapacity. The one-shot budget protects a single task; nothing learns
across tasks within a batch.

### Target Users

Unattended autoclaude batches; the wall-clock budget of overnight drains.

### Success Metrics

- At most 2 consecutive failed qwen attempts per batch; every later
  qwen-eligible task in that batch routes to Claude at its original tier.
- The trip is visible in the batch report (which tasks tripped it, how many
  tasks were rerouted).
- Zero behavior change for batches where qwen passes its gates (counter
  resets on success).

## Functional Decomposition

### Capability: Breaker state

Track consecutive capability failures inside the batch state machine.

#### Feature: Consecutive-failure counter

- **Description**: A per-batch counter with trip latch.
- **Inputs**: Task attempt outcomes from the work phase (a qwen attempt that
  fails the step-5.5 test gate).
- **Outputs**: State fields owned by the state-machine package:
  `qwen_gate_failures_consecutive` (int) and, once tripped,
  `qwen_breaker: {tripped: true, after_task: <id>, failed_tasks: [<ids>]}`.
- **Behavior**: Reset to 0 at batch start and on any qwen attempt that
  passes its gate; increment on each qwen gate failure; latch tripped at 2.
  Rework-mode attempts never touch the counter (rework never routes qwen).
  Premise: field names and write path follow the state schema the
  discovery-00050 successors establish; adopt their conventions at
  implementation time.

### Capability: Routing integration

The routing decision consults the breaker.

#### Feature: Breaker check in implementor routing

- **Description**: Tripped breaker reroutes eligible tasks to Claude.
- **Inputs**: `task.metadata.qwen_eligible`, breaker state.
- **Outputs**: Implementor pick: Claude at the task's ORIGINAL tier (haiku
  stays haiku, sonnet stays sonnet).
- **Behavior**: Mirrors the preflight-failure recovery, not the gate-failure
  escalation: the rerouted task was never attempted, so nothing says it is
  harder than planned (same asymmetry doctrine as
  `work/references/qwen-integration.md`). No preflight probe runs for a
  breaker-skipped pick (no wasted warm-up). The attempt entry records
  `implementor: "claude"` plus `breaker_skipped: true`. The breaker scopes
  to the implementor lane only - Quinn (review voice) is unaffected. The
  one-shot budget and its Sonnet escalation stay verbatim for the two
  attempts that happen before the trip.

### Capability: Visibility

The trip is a reported fact, not a buried state bit.

#### Feature: Implementor Mix breaker line

- **Description**: The batch report states the breaker outcome.
- **Inputs**: Breaker state at report render time.
- **Outputs**: One line in the `### Implementor Mix` section: either
  `capability breaker: not tripped` or `capability breaker: tripped after
  <task-id> (2 consecutive gate failures: <id>, <id>); N tasks rerouted to
  Claude`.
- **Behavior**: Renders from state only; absent fields (legacy batches)
  render `not tripped`. The audit-qwen report card (companion PRD) already
  tolerates the field.

## Structural Decomposition

### Repository Structure

```
<state-machine package created by the discovery-00050 successors>
├── <routing module>        # Maps to: Routing integration (breaker check)
├── <state schema module>   # Maps to: Breaker state (fields + reset/trip)
├── <report render module>  # Maps to: Visibility (Implementor Mix line)
└── <its test suite>        # Maps to: all breaker tests
```

Exact paths follow the package layout those PRDs ship; task 1 resolves them
before any edit.

### Module: breaker state

- **Maps to capability**: Breaker state
- **Responsibility**: Counter lifecycle (reset, increment, latch) as pure
  functions over the state schema.
- **Exports**: state fields `qwen_gate_failures_consecutive`,
  `qwen_breaker`; transition helpers per the package's idiom.

### Module: breaker routing

- **Maps to capability**: Routing integration
- **Responsibility**: Consult the latch before any qwen pick; reroute at
  original tier; stamp `breaker_skipped`.
- **Exports**: the amended routing decision function.

### Module: breaker reporting

- **Maps to capability**: Visibility
- **Responsibility**: Render the breaker line into Implementor Mix.
- **Exports**: report fragment renderer.

## Dependency Graph

### Foundation Layer (Phase 0)

- **External precondition**: discovery-00050 successor PRDs (state-machine
  core + loop ownership) in `dev/local/prds/done/`. Nothing in this PRD
  builds before this holds.

### Core Layer (Phase 1)

- **breaker state**: Depends on [external precondition] (schema home).
- **breaker routing**: Depends on [breaker state].

### Integration Layer (Phase 2)

- **breaker reporting**: Depends on [breaker state].

## Implementation Phases

### Phase 0: Foundation

**Goal**: Premise verified; landing zone located.

**Tasks**:

- [ ] Verify the premise and locate the routing/state/report modules in the
  shipped state-machine package (no deps) - Premise: both discovery-00050
  successor PRDs are in `dev/local/prds/done/` (match by discovery
  reference in their headers). Acceptance: on failure, defer/stall recorded
  per PRD 00017 mechanics and NO further task runs; on success, the three
  module paths are named in the task report.

**Exit Criteria**: Premise verified (or a clean defer recorded and the PRD
exits untouched).

### Phase 1: Core

**Goal**: Counter and routing behave under test.

**Tasks**:

- [ ] Implement counter lifecycle + trip latch with unit tests (depends on:
  Phase 0) - Premise: Phase 0 succeeded this run. Acceptance: tests prove
  reset at batch start, reset on gate pass (fail, pass, fail does NOT
  trip), latch at exactly 2 consecutive, rework attempts ignored.
- [ ] Wire the breaker check into implementor routing (depends on: counter)
  - Acceptance: tests prove tripped state reroutes an eligible task to
  Claude at original tier, skips the preflight probe, stamps
  `breaker_skipped: true`, and leaves Quinn dispatch logic untouched.

**Exit Criteria**: Counter and routing tests green.

### Phase 2: Integration

**Goal**: The trip is visible.

**Tasks**:

- [ ] Render the breaker line in the Implementor Mix section (depends on:
  Phase 1) - Acceptance: render tests cover not-tripped, tripped (with task
  ids and reroute count), and legacy state without the fields.

**Exit Criteria**: All tests green in the state-machine package's suite; a
simulated batch with two consecutive qwen gate failures reroutes the rest
and reports it.

## Test Strategy

### Critical Scenarios

- **Happy path**: qwen passes gates all batch → counter stays 0, routing
  unchanged, report says `not tripped`.
- **Edge case**: fail, pass, fail sequence → never trips (consecutive means
  consecutive).
- **Error case**: two straight gate failures → third eligible task routes
  to Claude at its original tier with `breaker_skipped: true`; report names
  both failing tasks.

## Risks

- **Masking a fixable infra fault**: a degraded-but-preflight-healthy
  backend looks like incapacity and trips the breaker. Mitigation: the
  report line names the two failing tasks so audit-qwen and the operator
  can distinguish repo-hostility from backend sickness before widening or
  narrowing anything.
- **Successor package shape differs from assumptions**: Mitigation: this
  PRD names no concrete paths; task 1 resolves them, and every task carries
  the premise re-check, so a mismatch defers instead of forcing.
