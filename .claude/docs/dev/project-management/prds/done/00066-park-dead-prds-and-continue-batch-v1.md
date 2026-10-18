---
design: run
design_gate: user
rework_cap: 3
---

# Park dead PRDs and continue the batch

> Source: `dev/local/audit-results/2026-07-18-autopilot-loop-speed.md`.
> Number 00066 reuses a 2026-07-14 hole by explicit user decision (2026-07-18)
> so this PRD drains first. The 00051-00053 trilogy later absorbs this logic
> (same absorption note as PRD 00076); this PRD is the stopgap that keeps
> batches draining until the cutover lands.

## Overview

### Problem Statement

The autoclaude wrapper halts the ENTIRE batch when one PRD's session dies or
hits a pause site. Measured on batch 202607120753 (2026-07-12 → 07-17): 75.7h
idle after 4 died halts and 16.2h after 3 pauses, versus 40.5h of total
compute. One sick PRD costs every healthy PRD behind it a night (or a
weekend) of drain time. The loop already knows how to sideline a sick PRD
mid-session (the recovery.md "Loop-mode stall procedure" moves it to hold/
and continues), but the wrapper's died and paused branches predate that
mechanism and still stop the world.

### Target Users

Solo operator running unattended `autoclaude` batches who wants healthy PRDs
to keep draining while a sick one waits for them.

### Success Metrics

- A scenario-tested batch of two PRDs where PRD 1 keeps dying drains PRD 2 to
  done and exits `Backlog drained`, with PRD 1 in `dev/local/prds/hold/`.
- Whole-batch halts occur ONLY from the sanctioned list: security-critical
  finding, data-loss risk, mv-verify exhaustion, sustained memory pressure,
  usage-limit beyond `_AUTOPILOT_LIMIT_WAIT_MAX`, net-retries exhausted,
  operator pause, and a died bootstrap session (no PRD selected yet - nothing
  to park).
- Next real batch's loop-metrics gap analysis (the jq recipe in the source
  report) shows zero multi-hour died-idle gaps attributable to parkable
  classes.

## Functional Decomposition

### Capability: Wrapper self-healing (died branch)

The wrapper's decision table branch (5) today notifies and halts on the first
died session. A fresh session self-heals by artifact, so one relaunch is
cheap; repeated deaths mean the PRD (or its phase) is sick and should be
parked, not block the batch.

#### Feature: Died-retry
- **Description**: retry the relaunch once before treating a PRD as sick.
- **Inputs**: the existing died classification (state missing/unreadable/
  untouched, not usage-limit, not network); `_AUTOPILOT_DIED_RETRIES_MAX`
  (default 1). Premise (re-check at execution): the died branch is the
  `died)` case of the wrapper's `case "$_signal"` block and currently
  returns 1 unconditionally.
- **Outputs**: one more session launch; counter reset on any session that
  touches state (mirror the `_net_retries` reset pattern).
- **Behavior**: consecutive died sessions increment the counter; while
  counter <= max, notify one line and continue the loop instead of halting.

#### Feature: Park hand-off marker
- **Description**: on retry exhaustion, hand the sick PRD to the next
  session for parking instead of halting the loop.
- **Inputs**: died-retry exhaustion, or the progress-fingerprint bound firing
  (`_AUTOPILOT_PHASE_REPEATS_MAX` identical fingerprints - today it pauses).
  Both require a selected PRD (`state.prd` non-empty); a died bootstrap
  session still halts loud.
- **Outputs**: `dev/local/autopilot/park-requested` containing at minimum the
  PRD filename and a one-line reason (exact shape finalized in design), then
  a relaunch.
- **Behavior**: the wrapper never edits `state.json` (state surgery stays
  in-skill); the marker is the entire wrapper-to-skill hand-off, symmetric
  with the existing `pause-requested` operator marker.

### Capability: Skill-side parking (build gate)

#### Feature: Phase 0 park handler
- **Description**: consume the marker and park the named PRD via the existing
  stall machinery, then continue selection.
- **Inputs**: `dev/local/autopilot/park-requested`; the recovery.md
  "Loop-mode stall procedure". Premise (re-check at execution): that
  procedure exists under that heading and moves the PRD to hold/ with a
  recorded stall reason, continuing the batch.
- **Outputs**: PRD in `dev/local/prds/hold/` (verified move), stall recorded
  with new site slug `wrapper_died`, marker deleted, selection proceeds to
  the next PRD.
- **Behavior**: first check in the Phase 0 abort handlers, before existing
  stall_reason checks; a marker naming a PRD that is not in wip/ is consumed
  and logged, never crashes selection.

#### Feature: Pause-site conversion
- **Description**: loop-mode pause-by-state sites that are per-PRD decisions
  stall the PRD instead of halting the batch.
- **Inputs**: the two loop-mode turn-ending PAUSE sites `blocking_escalation`
  and `scope_alarm` (SKILL.md Error Handling closing rule: "Loop mode has
  exactly two turn-ending PAUSEs"), plus the Phase 1.5 design gate in loop
  mode. Premise (re-check at execution): blocking_escalation and scope_alarm
  write `phase: "paused"` + `pause_reason` and end the turn, which the
  wrapper maps to a batch halt. The design gate has NO pause_reason site slug
  today (verified 2026-07-18): interactive mode uses a mid-turn
  AskUserQuestion; loop-mode text only says "pause by state" without a slug.
  This PRD defines that mechanism rather than converting an existing one.
- **Outputs**: the PRD stalls to hold/ with its decision recorded in
  `deferred_decisions` (batch-end review presents it; for the design gate the
  deferred decision records the design doc path); the batch continues. New
  stall site slug `design_gate` added to the site enum.
- **Behavior**: conversion scope is exactly three sites: `blocking_escalation`,
  `scope_alarm` (keep their slugs, now stall instead of pause), and the
  loop-mode design gate (new `design_gate` stall slug). Nothing else changes:
  every other `pause_reason.site` keeps its current semantics, and the
  wrapper-side batch-halt list stays exactly the Success Metrics list. The
  core SKILL.md Error Handling closing rule forbids GROWING the loop-mode
  PAUSE list; this change empties it (expected: zero loop-mode turn-ending
  PAUSEs after conversion; verify the remainder at execution) - shrinking is
  allowed and must be reflected in that rule's wording.

## Structural Decomposition

### Repository Structure

```
~/.config/bash/plugins/development.plugin.bash   # Maps to: Wrapper self-healing
~/.claude/skills/run-autopilot/
├── SKILL.md                                     # Maps to: Pause-site conversion (Error Handling table)
├── references/phase-build.md                    # Maps to: Phase 0 park handler
├── references/recovery.md                       # Maps to: Phase 0 park handler (site slug wrapper_died)
├── references/state-schema.md                   # Maps to: Park hand-off marker (documented)
└── scripts/test_autopilot_resume.py             # Maps to: tests (park handler resume decision)
~/.claude/skills/run-autopilot/scripts/tests/    # Maps to: tests (wrapper scenarios; actual layout per repo)
```

### Module: wrapper died branch
- **Maps to capability**: Wrapper self-healing (died branch)
- **Responsibility**: retry once, then write the park marker and relaunch;
  never halt for a parkable PRD
- **Exports**: `_AUTOPILOT_DIED_RETRIES_MAX` env knob (default 1)

### Module: build-gate park handler
- **Maps to capability**: Skill-side parking (build gate)
- **Responsibility**: marker consumption, verified hold/ move via the stall
  procedure, selection continues
- **Exports**: `wrapper_died` stall site slug (recovery.md)

### Module: contracts and docs
- **Maps to capability**: both
- **Responsibility**: Error Handling table rows, state-schema marker entry,
  operator runbook line for un-parking
- **Exports**: updated sanctioned-halt list

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **wrapper died branch**: retry + marker write, scenario-testable alone

### Core Layer (Phase 1)
- **build-gate park handler**: Depends on [wrapper died branch] (consumes its
  marker)

### Integration Layer (Phase 2)
- **contracts and docs**: Depends on [build-gate park handler, wrapper died
  branch] (documents the shrunken halt list and the marker contract)

## Implementation Phases

### Phase 0: Foundation
**Goal**: the wrapper retries and parks instead of halting.

**Tasks**:
- [ ] Died-retry counter + park-marker write in the died branch (no deps) -
  Acceptance: scenario tests cover (a) one died session then recovery
  continues the batch with counter reset, (b) exhaustion writes the marker
  naming `state.prd` and relaunches, (c) died with no `state.prd` still
  halts loud. Premise re-checked: the `died)` case anchor still matches
  before editing.

**Exit Criteria**: wrapper scenario suite green; no halt on parkable deaths.

### Phase 1: Core
**Goal**: the next session parks the PRD and keeps draining.

**Tasks**:
- [ ] Phase 0 park handler + `wrapper_died` slug (depends on: Phase 0) -
  Acceptance: `test_autopilot_resume.py` gains a case where the marker is
  present and resume routes through the stall procedure; a synthetic
  two-PRD batch run parks PRD 1 to hold/ (verified move) and completes
  PRD 2; marker consumed exactly once.

**Exit Criteria**: end-to-end park path proven on the synthetic batch.

### Phase 2: Integration
**Goal**: contracts match behavior.

**Tasks**:
- [ ] Pause-site conversion (blocking_escalation, scope_alarm, design_gate in
  loop mode) (depends on: Phase 1) - Acceptance: blocking_escalation and
  scope_alarm gate text routes to the stall procedure keeping their slugs;
  the loop-mode design gate routes to the stall procedure with the new
  `design_gate` slug; grep shows no loop-mode `phase: "paused"` writer left.
- [ ] Error Handling table + state-schema + operator runbook updates
  (depends on: Phase 1) - Acceptance: SKILL.md closing rule states the
  post-conversion loop-mode turn-ending PAUSE list (expected empty; verified
  at execution) and the wrapper-side sanctioned batch-halt list matches the
  Success Metrics list verbatim; state-schema.md documents `park-requested`
  and the `design_gate` stall slug; runbook documents un-parking (`mv` back
  from hold/).

**Exit Criteria**: Success Metrics all verifiably true on the scenario suite.

## Test Strategy

### Critical Scenarios
- **Happy path**: PRD 1 dies twice, marker written, next session parks it,
  PRD 2 drains → Expected: batch exits `Backlog drained`, PRD 1 in hold/
  with `wrapper_died` stall recorded.
- **Edge case**: died on the bootstrap session (no PRD selected) → Expected:
  loud halt exactly as today.
- **Edge case**: fingerprint bound fires (thrash without death) → Expected:
  park marker path, not a batch halt.
- **Error case**: marker names a PRD absent from wip/ → Expected: marker
  consumed, one warning line, selection continues; no crash.

## Risks

- **Masking a systemic failure as per-PRD sickness** (e.g. a broken hook
  kills every PRD): successive parks would drain the batch into hold/.
  Mitigation: if two consecutive PRDs park via `wrapper_died`, halt loud
  (systemic breaker) - scenario-tested.
- **Park loop (marker never consumed)**: wrapper relaunches forever.
  Mitigation: marker age check - a marker older than one session cycle
  triggers the loud halt path; plus the existing fingerprint bound.
- **Batch-end review misses parked PRDs**: parked work silently forgotten.
  Mitigation: stall procedure already records to state; batch report lists
  stalled PRDs (verify the render includes `wrapper_died` entries).
