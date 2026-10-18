# Decay Escalations When Signals Clear

> Renumbered 00078 → 00111 on 2026-08-01 (backlog tail resequence; mapping in memory `project_backlog_renumber_2026_08`).
> Source: `dev/local/discovery/00065-deepen-model-escalation.md` (requirement
> 10; F6). PRD F of the escalation initiative. Requires 00065 (ladder file)
> and 00076 (session promotion) done.

## Overview

### Problem Statement

Escalation without decay is a ratchet. A build session promoted to Opus would
stay Opus for every remaining session of that PRD even after the promoting
cause has passed, and a task tier bumped during rework could leak into the
routing of unrelated tasks or the next PRD. Every silent ratchet refunds the
savings the cheaper defaults earned. Escalations must return to baseline when
the escalating condition clears, by deterministic rules declared in one place.

### Target Users

Unattended autoclaude batches running multi-session PRDs; the cost line
audit-routing tracks.

### Success Metrics

- A promoted build session returns to the default model on the next relaunch
  when no live promotion signal holds.
- A rework-escalated task tier never changes the dispatch tier of any other
  task or PRD.
- Decay rules are deterministic, live only in model-ladder.md, and are
  jq-expressible (portable into the 00051/00106/00107 orchestrator rewrite, ex-00051-00053).
- Audit-routing can see promotion episodes end (relaunch model visible per
  session in loop-metrics).

## Functional Decomposition

### Capability: Session promotion decay

The wrapper recomputes, never remembers.

#### Feature: Fresh-signal recomputation

- **Description**: Launch model derives from current state at every relaunch;
  no stored promotion latch is consulted.
- **Inputs**: The 00076 promotion signals as they read at relaunch time;
  decay rules from model-ladder.md.
- **Outputs**: The build launch model for each relaunch.
- **Behavior**: Each signal is classified in the ladder file as live
  (re-evaluated, can clear) or sticky for the PRD's lifetime; exactly which
  conditions clear a promotion (e.g. does `replan_count > 0` ever stop
  promoting within the same PRD; does a resolved stall stop counting) is
  settled in design - open question below. Whatever the classification, the
  wrapper evaluates signals fresh each relaunch and a signal-free state
  launches Sonnet. `_AUTOPILOT_MODEL_BUILD` override still wins (kill-switch
  unchanged).

### Capability: Task-tier decay

Escalated tiers are scoped, not global.

#### Feature: Escalation scope containment

- **Description**: A task's escalated tier lives and dies with that task.
- **Inputs**: attempts[] stamps (`escalated_from`, final model) from 00065;
  `task.metadata.model` of all tasks.
- **Outputs**: Containment rules in work SKILL.md and the ladder file: an
  escalation updates dispatch for the escalated task only; every other task
  enters at its classified `metadata.model`; nothing escalation-related
  survives into the next PRD's state.
- **Behavior**: The rule is verified, not just stated: a fixture walkthrough
  proves a task escalated to opus is followed by an unrelated haiku task
  dispatching at haiku, and a fresh PRD state carries no escalation residue.

## Structural Decomposition

### Repository Structure

```
~/.config/bash/plugins/
└── development.plugin.bash        # relaunch model recomputation (decay-aware)
                                   # (pre-cutover seam; post-00106 (ex-00052) it is
                                   # run-autopilot/cli/routing.py)
~/.claude/skills/
├── run-autopilot/references/
│   └── model-ladder.md            # decay section: live vs sticky per signal
└── work/
    └── SKILL.md                   # containment rule in the routing table
```

### Module: ladder decay section

- **Maps to capability**: Session promotion decay
- **Responsibility**: The only statement of live-vs-sticky classification and
  clearing conditions per signal (replaces the 00065 no-decay-yet note).
- **Exports**: model-ladder.md decay rows.

### Module: wrapper recomputation

- **Maps to capability**: Session promotion decay
- **Responsibility**: Relaunch-time evaluation honoring decay rows; no stored
  latch.
- **Exports**: the build branch of the wrapper's model decision.

### Module: containment prose

- **Maps to capability**: Task-tier decay
- **Responsibility**: Scope rule at dispatch time.
- **Exports**: work SKILL.md routing table text.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies inside this PRD - built first. External: 00065 and 00076 in
`dev/local/prds/done/`.

- **ladder decay section**: the rules both consumers cite.

### Core Layer (Phase 1)

- **wrapper recomputation**: Depends on [ladder decay section].

### Integration Layer (Phase 2)

- **containment prose**: Depends on [ladder decay section] (cites the same
  scope rules).

## Implementation Phases

### Phase 0: Foundation

**Goal**: Decay rules exist as declared facts.

**Tasks**:

- [ ] Verify premises and write the decay section into model-ladder.md
  (no deps) - Premise: 00065 and 00076 in done/; the ladder file's
  no-decay-yet note still present (else record drift). Acceptance: on premise
  failure, defer/stall per 00017; on success, every 00076 promotion signal
  has a live/sticky row with its clearing condition, and the no-decay-yet
  note is gone.

**Exit Criteria**: Ladder file states a decay rule for every promotion
signal.

### Phase 1: Core

**Goal**: The wrapper forgets what no longer holds.

**Tasks**:

- [ ] Make the wrapper's build-model decision decay-aware (depends on: Phase
  0) - Premise: re-locate the build-model decision by content (bash case
  block pre-cutover; run-autopilot/cli/routing.py if the 00051/00106 (ex-00052) cutover
  has landed; record which). Acceptance: wrapper tests cover
  promote-then-clear (Opus this relaunch, Sonnet next when the signal is
  live and cleared), sticky signals persisting for the PRD, and the env
  override winning; no promotion latch field exists in state.

**Exit Criteria**: Wrapper tests green including the promote-then-clear
sequence.

### Phase 2: Integration

**Goal**: Task-tier containment is stated and proven.

**Tasks**:

- [ ] Add the containment rule to work's routing table and run the fixture
  walkthrough (depends on: Phase 0) - Acceptance: walkthrough shows an
  opus-escalated task followed by an unrelated task dispatching at its own
  classified tier, and a fresh-PRD state free of escalation residue;
  transcript attached to the task report.

**Exit Criteria**: Containment walkthrough green; all decay behavior traceable
to ladder rows.

## Test Strategy

### Critical Scenarios

- **Happy path**: PRD promoted by a live signal, signal clears → next
  relaunch launches Sonnet.
- **Edge case**: sticky signal (per ladder classification) → promotion holds
  for the PRD's remaining sessions and the report shows why.
- **Edge case**: escalated task completes at opus; next task in the same PRD
  dispatches at its classified haiku tier.
- **Error case**: ladder decay section missing at relaunch time → wrapper
  falls back to 00076 behavior (promotion without decay) and logs it loudly.

## Risks

- **Eager decay re-burns rework cycles**: clearing conditions are per-signal
  and declared, not global; audit-routing's re-promotion visibility shows if
  decay thrashes, and the env override pins a model instantly.
- **Wrapper complexity creep**: decay stays a pure function of state fields
  (jq-expressible), ready for the 00051/00106/00107 (ex-00051-00053) port.
- **Signal semantics drift between 00076 and this PRD**: the ladder file is
  the single home for both; the premise task re-reads it before editing.

## Open Questions

- Exact clearing conditions per signal: which of the 00076 promotion signals
  are live vs sticky, and what observable state change clears each? (Design
  phase; must stay derivable from state.json alone.)
