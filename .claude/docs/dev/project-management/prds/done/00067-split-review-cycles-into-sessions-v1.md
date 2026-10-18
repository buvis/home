---
design: run
rework_cap: 3
---

# Split review cycles into sessions

> Source: `dev/local/audit-results/2026-07-18-autopilot-loop-speed.md`.
> Number 00067 reuses a 2026-07-14 hole by explicit user decision
> (2026-07-18) so this PRD drains right after 00066.

## Overview

### Problem Statement

The review gate loops every review-rework cycle inside ONE session
(phase-review.md Phase 6 ends with "Loop back to Phase 4"), so a session
routinely outlives the wrapper's 7200s wall-clock cap and is SIGTERMed
mid-cycle, discarding in-flight reviewer work (external CLI reviewers
included). Measured on batch 202607120753: 5 sessions killed at ~7206s, one
more at 7852s, one 18,887s/$146 session that ran while the cap was disarmed
by a since-fixed regression; 17.4h total sat in cap-hit sessions. Concrete
waste: 00058's review cycle was killed at 2h twice, then completed in 21min
on the third session - roughly 3.7h redone on one PRD. The cap and the
session packaging are fighting each other: the cap is sized for a phase, the
session holds up to three cycles.

### Target Users

Solo operator running unattended batches; the review phase is the largest
active-time consumer (23.3h of 40.5h in the measured batch).

### Success Metrics

- Zero review sessions killed at the wall-clock cap across the next full
  batch (loop-metrics: no review row with `wall_secs` at the cap value).
- No lost reviewer work: every review cycle that starts produces its
  `dev/local/reviews/{prd}-review-{cycle}.md` file exactly once.
- Review-phase wall per PRD drops versus the 202607120753 baseline (23.3h /
  20 sessions for ~7 PRDs), measured by the same jq aggregation.

## Functional Decomposition

### Capability: Cycle-boundary handoff

#### Feature: Review-to-review handoff site
- **Description**: after rework returns and the cycle increment persists,
  hand off to a fresh session instead of looping to Phase 4 in-session.
- **Inputs**: phase-review.md Phase 6 "After /work returns" (premise,
  re-check at execution: its step 4 currently reads "Loop back to Phase 4");
  the core SKILL.md Session handoff procedure and its site table.
- **Outputs**: a new site row **review → review** (state writes:
  `phase: "review"`, `next_phase: "review"`, `phases_completed` unchanged)
  plus a cycle-handoff banner; the wrapper's continue branch relaunches.
- **Behavior**: resume needs no new logic - Phase 4 already skips a cycle
  whose review file exists and runs the current `state.cycle`; the
  fingerprint bound stays live because `cycle` is one of its fields, so a
  handoff loop that stops advancing still pauses after
  `_AUTOPILOT_PHASE_REPEATS_MAX` repeats.

#### Feature: Convergence handoff unchanged
- **Description**: the existing review → done handoff and the loop-level
  skip (`"review"` in `phases_completed`) keep working unchanged.
- **Inputs**: current phase-review.md convergence path.
- **Outputs**: no behavior change on convergence or cap-out deferral.
- **Behavior**: only the "unresolved findings remain AND cycle < cap" path
  gains the handoff; converged and capped-out paths are untouched.

### Capability: Per-phase wall-clock cap

#### Feature: Review cap knob
- **Description**: size the session cap per launch phase instead of one
  global number.
- **Inputs**: the wrapper's existing per-phase `case "$_phase_launched"`
  block (premise, re-check at execution: it currently selects model/effort
  for build/review/done) and `_autopilot_session_cap`.
- **Outputs**: `_AUTOPILOT_SESSION_MAX_REVIEW` (default 10800) applied to
  review-phase launches; every other phase keeps
  `_AUTOPILOT_SESSION_MAX` (default 7200).
- **Behavior**: a single review cycle that legitimately needs ~2h20m (the
  observed maximum) finishes; a genuinely hung review session is still
  reaped, now losing at most one cycle instead of a whole review loop.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/run-autopilot/
├── SKILL.md                         # Maps to: Review-to-review handoff site (site table + operator runbook cap line)
├── references/phase-review.md       # Maps to: Cycle-boundary handoff
└── scripts/test_autopilot_resume.py # Maps to: tests (handoff resume decision)
~/.config/bash/plugins/development.plugin.bash  # Maps to: Per-phase wall-clock cap
```

### Module: review gate handoff
- **Maps to capability**: Cycle-boundary handoff
- **Responsibility**: replace the in-session loop with the handoff procedure;
  keep convergence/cap-out paths byte-equivalent in behavior
- **Exports**: review → review row in the handoff site table

### Module: wrapper cap selection
- **Maps to capability**: Per-phase wall-clock cap
- **Responsibility**: pick the cap alongside model/effort in the existing
  per-phase case block; pass it to `_autopilot_session_cap`
- **Exports**: `_AUTOPILOT_SESSION_MAX_REVIEW` env knob (default 10800)

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **wrapper cap selection**: independent one-knob change, testable alone

### Core Layer (Phase 1)
- **review gate handoff**: Depends on [wrapper cap selection] only for the
  combined success metric (cycles must both fit the cap and hand off); the
  edit itself is independent

### Integration Layer (Phase 2)
- **docs alignment**: Depends on [review gate handoff, wrapper cap
  selection] (runbook cap sentence, dashboard note)

## Implementation Phases

### Phase 0: Foundation
**Goal**: review sessions get a cap sized for one cycle.

**Tasks**:
- [ ] Per-phase cap in the wrapper case block (no deps) - Acceptance:
  scenario test shows a review launch arms the sidecar with 10800 (or the
  env override) and a build launch keeps 7200; premise re-checked: the
  case block anchor still matches before editing.

**Exit Criteria**: wrapper scenario suite green.

### Phase 1: Core
**Goal**: one review cycle per session.

**Tasks**:
- [ ] Review → review handoff (depends on: Phase 0) - Acceptance:
  phase-review.md Phase 6 ends in the Session handoff procedure with the
  new site row; SKILL.md site table gains the row;
  `test_autopilot_resume.py` gains a case proving a fresh session with
  `phase: "review"`, an existing cycle-1 review file, and `cycle: 2`
  resumes at the cycle-2 review (no re-review of cycle 1, no skip past
  Phase 4).

**Exit Criteria**: synthetic two-cycle review resumes correctly across a
simulated relaunch.

### Phase 2: Integration
**Goal**: contracts match behavior.

**Tasks**:
- [ ] Docs alignment (depends on: Phase 1) - Acceptance: the operator
  runbook sentence naming `_AUTOPILOT_SESSION_MAX` documents the review
  override; the handoff banner is listed in Phase Banners; a note records
  that per-cycle boots are prompt-cache reads within the 1h TTL (verified
  against Claude Code docs 2026-07-18) and that 00072 shrinks the re-read
  prefix.

**Exit Criteria**: Success Metrics checkable from loop-metrics on the next
batch; no doc names the old single-cap behavior.

## Test Strategy

### Critical Scenarios
- **Happy path**: cycle 1 finds issues → rework → handoff → fresh session
  runs cycle 2 → converges → review → done handoff → Expected: two review
  files, one per cycle, `phases_completed` gains `"review"` only at
  convergence.
- **Edge case**: relaunch lands after the cycle increment but before the
  cycle-2 review starts → Expected: Phase 4 runs cycle 2 (no file exists for
  it), no duplicate cycle-1 review.
- **Error case**: review session hung at the new 10800 cap → Expected:
  SIGTERM as today; only the in-flight cycle is lost; next session resumes
  the same cycle.

## Risks

- **More sessions, more boot prefix paid**: bounded - at most 2 extra boots
  per PRD (cap 3), each a ~57K-token cache read inside the 1h TTL; 00072
  shrinks it further. The measured alternative (2h sessions redone) costs
  more in both hours and dollars.
- **Handoff relaunch loop** (cycle stops advancing): the wrapper's
  progress-fingerprint bound includes `cycle` and pauses after
  `_AUTOPILOT_PHASE_REPEATS_MAX` identical fingerprints (parks via 00066
  once that lands).
- **Longer hangs under the raised review cap**: a hung reviewer now wastes
  up to 3h instead of 2h before reaping - accepted; the Watcher's ~50min
  stall budget fails a stuck CLI reviewer far earlier, and only one cycle
  is at stake per session.
