# Route Builds Sonnet-First with Fable Rescue

> Source: `dev/local/discovery/00065-deepen-model-escalation.md` (requirements
> 3, 4, 6, 7; Q5, Q6). PRD C of the escalation initiative. Extends the 00018
> wrapper routing; reuses 00017 stall semantics verbatim.

## Overview

### Problem Statement

Build sessions run Opus wall-to-wall regardless of need: 00018 routed models
by phase, not by evidence of difficulty, so a routine build pays Opus prices
end to end. At the other extreme, the hardest tasks exhaust the ladder at
Opus and stall to the human; each stall freezes a PRD and spends the scarcest
resource, attention. Both ends need the same fix: deterministic signals decide
when a session deserves Opus, and a human-gated Fable retry converts some
exhaustion stalls into completions.

### Target Users

Unattended autoclaude batches; the operator who wants fewer stalls and a
smaller bill without touching the review safety net.

### Success Metrics

- Build sessions launch on Sonnet by default; promotions to Opus happen only
  on the declared signals and are visible in loop-metrics (`model` +
  `phase_launched` already recorded per session).
- Review sessions stay Opus, done sessions stay Sonnet (Q1 exclusion intact).
- An `escalation_exhausted` PRD can produce at most one Fable rescue request,
  ever; approval yields exactly one Fable-tier task retry; zero autonomous
  Fable spend.
- `_AUTOPILOT_MODEL_BUILD` still overrides everything (kill-switch, existing
  since 00018).
- Batch keeps draining while a rescue request waits (00017 semantics).

## Functional Decomposition

### Capability: Session-model routing

The wrapper decides the build model from state, deterministically (jq on
state.json + PRD frontmatter).

#### Feature: Sonnet-first build launch

- **Description**: Build launches on Sonnet unless a promotion signal holds.
- **Inputs**: state.json, the PRD's frontmatter, loop-metrics tail for the
  running batch.
- **Outputs**: The model string passed on the wrapper's launch line for build
  sessions.
- **Behavior**: Promotion signals (any one promotes to Opus): PRD frontmatter
  `default_model: opus`; `replan_count > 0`; a prior stall for this PRD; a
  repeat build session for the same PRD. Signals are evaluated fresh at every
  relaunch (no stored promotion latch; 00078 owns decay rules). How
  prior-stall and repeat-build are detected (existing state fields, metrics
  tail, or a new per-PRD counter) is settled in design - open question below.
  Review stays Opus, done stays Sonnet. Precedence: `_AUTOPILOT_MODEL_BUILD`
  env override > promotion signals > sonnet default. Implementor tiers are
  unaffected (Agent `model` param overrides session model).

#### Feature: loop-metrics PRD stamping

- **Description**: Metrics lines identify the PRD so audit-routing can compute
  per-PRD cost medians.
- **Inputs**: The metrics writer in the wrapper (anchors :282-313 as of the
  2026-07-13 scan); state.json's current PRD.
- **Outputs**: A `prd` field on each loop-metrics line.
- **Behavior**: Verified 2026-07-18: the writer ALREADY stamps `prd`
  unconditionally (development.plugin.bash :601/:609) - this feature is a
  verify-only no-op; confirm at execution and record. Legacy lines without
  the field stay parseable.

### Capability: Human-gated Fable rescue

The top rung exists but only a human unlocks it (Q6).

#### Feature: Justification and stall

- **Description**: At escalation exhaustion the loop writes its case and
  parks the PRD.
- **Inputs**: escalation exhaustion (phase-review.md delegates at :164 to
  recovery.md "Rework escalation exhausted" - the procedure lives there; edit
  both as needed), the blocked task's attempt history from state.
- **Outputs**: state gains `fable_request {status, task_id, requested_at,
  justification {problem, attempts, impact}}` (exact field shape finalized in
  state-schema.md); an ntfy notification via the existing notify.py path; the
  PRD stalls per 00017 (PRD parks, batch continues).
- **Behavior**: Written by the review session that hits exhaustion. Max one
  request per PRD ever: any existing `fable_request` (whatever its status)
  blocks a new one. Rejection leaves a normal stall for human disposition.

#### Feature: Approval consumption

- **Description**: Explicit approval buys exactly one Fable-tier retry.
- **Inputs**: The human decision via `autoclaude approve-fable <prd>` /
  `autoclaude reject-fable <prd>` wrapper subcommands (decided 2026-07-18
  backlog review) that atomically set `fable_request.status`; a manual state
  edit stays the documented fallback. Works while the batch keeps draining.
- **Outputs**: On approval: status `approved`; the next build session for that
  PRD dispatches ONE retry of the blocked task with Agent `model: fable`,
  then status `consumed` regardless of outcome. On rejection: status
  `rejected`, normal stall handling.
- **Behavior**: Never a session model, never autonomous. A failed Fable retry
  returns to the normal stall path; the latch prevents a second request. The
  wrapper treats the parked/approved states purely through existing stall and
  relaunch decisions (no new pause path).

## Structural Decomposition

### Repository Structure

```
~/.config/bash/plugins/
└── development.plugin.bash        # case block: sonnet-first + promotion;
                                   # approve/reject-fable subcommands;
                                   # approved-request relaunch (metrics prd
                                   # field already present - verify only).
                                   # Pre-cutover seam; post-00052 it is
                                   # run-autopilot/cli/routing.py
~/.claude/skills/run-autopilot/references/
├── phase-review.md                # exhaustion → justification + request
├── state-schema.md                # fable_request + promotion-signal fields
└── model-ladder.md                # Fable rung status: active (human-gated)
~/.claude/skills/work/
└── SKILL.md                       # approved-request: single fable-tier dispatch
```

### Module: wrapper session routing

- **Maps to capability**: Session-model routing
- **Responsibility**: Launch-model decision per phase from state signals;
  metrics stamping; portable jq-expressible logic only.
- **Exports**: the build branch of the wrapper's model case block; metrics
  writer field.

### Module: rescue state contract

- **Maps to capability**: Human-gated Fable rescue
- **Responsibility**: fable_request lifecycle (requested → approved/rejected →
  consumed) and promotion-signal fields.
- **Exports**: state-schema.md definitions.

### Module: rescue flow prose

- **Maps to capability**: Human-gated Fable rescue
- **Responsibility**: phase-review writes the justification and stalls; work
  dispatches the single approved retry.
- **Exports**: phase-review.md exhaustion section; work SKILL.md dispatch
  note.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies inside this PRD - built first. External: 00065 done (ladder
file exists for the Fable rung row; numeric drain order guarantees it).

- **rescue state contract**: field shapes everything else writes and reads.

### Core Layer (Phase 1)

- **wrapper session routing**: Depends on [rescue state contract] (promotion
  signals live in state).

### Integration Layer (Phase 2)

- **rescue flow prose**: Depends on [rescue state contract, wrapper session
  routing] (the parked/approved lifecycle rides existing relaunch decisions).

## Implementation Phases

### Phase 0: Foundation

**Goal**: Contracts defined, seams located.

**Tasks**:

- [ ] Re-locate wrapper seams by content: model case block (:398-415 as of
  2026-07-18), launch line, relaunch decision table, metrics writer
  (:601-609); locate the wrapper's existing test harness (no deps) - Premise:
  anchors drift; record actual locations before editing. If the 00051/00052
  CLI cutover has landed by execution time, the build-model seam is
  `run-autopilot/cli/routing.py` instead of the bash case block - record
  which world holds. Acceptance: seams + test harness named in the task
  report; if no wrapper test harness exists, say so and name where the new
  tests will live.
- [ ] Define fable_request and promotion-signal fields in state-schema.md
  (no deps) - Acceptance: lifecycle states enumerated (requested, approved,
  rejected, consumed); one-request-per-PRD latch semantics stated;
  justification payload fields (problem, attempts, impact) defined;
  legacy-absence tolerated.

**Exit Criteria**: Schema merged; every seam pinned to current content.

### Phase 1: Core

**Goal**: Builds launch cheap and promote deterministically.

**Tasks**:

- [ ] Implement sonnet-first + promotion signals in the wrapper case block,
  and stamp `prd` on metrics lines (depends on: Phase 0) - Premise: metrics
  writer may already stamp the PRD (then no-op that part). Acceptance: each
  signal has a test (jq fixture states → expected model); env override wins
  in a test; review/done branches byte-identical; metrics line carries prd.

**Exit Criteria**: Wrapper tests green; a signal-free fixture launches build
on Sonnet, each signal fixture launches Opus.

### Phase 2: Integration

**Goal**: Exhaustion converts to a gated rescue instead of a dead stall.

**Tasks**:

- [ ] Write the justification + stall flow into phase-review.md (depends on:
  Phase 1) - Acceptance: request written only at escalation_exhausted; latch
  respected (fixture with an existing rejected request produces no new one);
  ntfy message content specified; stall recorded via the 00017 path, no new
  pause semantics.
- [ ] Wire approval consumption: `autoclaude approve-fable <prd>` /
  `reject-fable <prd>` subcommands atomically set `fable_request.status`;
  work dispatches one `model: fable` retry for an approved request, then
  marks consumed; wrapper relaunch honors the approved state (depends on:
  Phase 1) - Acceptance: fixture walkthrough covers approve → single fable
  dispatch → consumed (on both retry outcomes) and reject → normal stall; no
  path dispatches fable twice; manual state edit documented as fallback.
- [ ] Update model-ladder.md: Fable rung active (human-gated), knobs and
  latch documented (depends on: Phase 1) - Acceptance: ladder row states the
  gate, the one-per-PRD cap, and that Fable is never a session model. Also:
  plan-tasks' `default_model` invalid-value warning names the gate ("fable is
  human-gated - use the rescue flow, 00076") instead of a bare rejection, so
  the enum staying `haiku|sonnet|opus` reads as policy, not omission
  (2026-07-19 second-pass audit, decision-12 item redirected here).

**Exit Criteria**: Fixture walkthroughs green; ladder file current; batch
drain behavior unchanged while a request waits.

## Test Strategy

### Critical Scenarios

- **Happy path**: no promotion signals → build launches Sonnet; same PRD with
  `replan_count: 1` → next build launches Opus; loop-metrics shows both with
  prd stamped.
- **Edge case**: second exhaustion on a PRD with `fable_request.status:
  rejected` → no new request, normal stall.
- **Edge case**: approval lands while another PRD is mid-build → parked PRD
  resumes with exactly one fable-tier dispatch on its next build session.
- **Error case**: `_AUTOPILOT_MODEL_BUILD=claude-opus-4-8` set → every build
  launches Opus regardless of signals (kill-switch verified).

## Risks

- **Sonnet build poisons planning**: bad decompositions surface as rework;
  mitigations: deterministic promotion signals, audit-routing visibility, and
  the one-env revert.
- **New stall variant mishandled by the wrapper**: the rescue reuses the 00017
  stall path verbatim and ships wrapper tests; no new pause paths, no
  Stop-hook-era guards.
- **Fable request spam**: hard latch, one request per PRD ever.
- **Approval UX friction**: the approve/reject-fable subcommands are usable
  mid-drain; a manual state edit remains the documented fallback.
- **Wrapper complexity creep**: decisions stay jq-expressible; the 00051-00053
  rewrite absorbs this logic later (closing phase of the initiative).

## Open Questions

- Promotion-signal detection: are prior-stall and repeat-build-session
  derivable purely from today's state/metrics, or does one need a new
  counter? (Design phase.)
- (Approval UX resolved 2026-07-18: `autoclaude approve-fable` /
  `reject-fable` subcommands; manual state edit as fallback.)
