# Lower Task Tier Defaults

> Source: `dev/local/discovery/00065-deepen-model-escalation.md` (requirements
> 2, 6; Q7). PRD B of the escalation initiative. Hard gates: 00058 (pinned
> qwen engine) and 00065 (the escalation net) must be done first.

> ## OUTCOME (2026-07-21): HEADLINE CAPABILITY DID NOT SHIP. METRICS NEED RE-BASELINING.
>
> **Shipped:** the `_PLAN_TASKS_FLOOR` knob (`plan-tasks/SKILL.md` step 4.7; a no-op today, since the row it would revert to is unchanged), the memory-pressure gate (`work/SKILL.md` step 3 routing row 4, backed by `check_memory_pressure.py`), the one-shot qwen budget prose fix, and the exclusion-line render delta across the report and schema docs.
>
> **Did not ship:** the Rule 2 signal widening, the PRD's headline capability. It was built, then withdrawn under adversarial review; the reasoning lives in `plan-tasks/references/design-rationale.md`, section "Rule 2 signal widening was attempted and withdrawn (PRD 00075)" (the proposed signals were generic verbs like `wire` and `restore` that also matched security-critical and data-recovery tasks passing the same size gate). Rule 2 is byte-identical to its pre-00075 state.
>
> **Success Metrics below are unmeetable as written.** Haiku share cannot move: the classifier is unchanged. Qwen share was never reachable by this PRD: `qwen_eligible` already accepted both haiku and sonnet before 00075, and the pressure gate can only remove qwen dispatches, never add them. Both halves need operator re-baselining.

## Overview

### Problem Statement

The plan-tasks classifier treats sonnet as the floor: routine mechanical work
that haiku or local qwen would handle pays sonnet prices by default. qwen,
despite passing 5/6 sonnet-tier Rust tasks in eval, is capped at one shot per
PRD, so the free bottom rung idles. With the escalation net (00065) live,
cheap-first is safe: a wrong cheap pick costs one bounded attempt, not a
quality hole - the test gate and the untouched review roster still catch
everything. Defaults should be as cheap as the net allows.

### Target Users

Unattended autoclaude batches; the operator paying per-token for work a local
model could do.

### Success Metrics

- haiku + qwen share of completed tasks rises (reported by audit-routing, not
  targeted - Goodhart).
- Opus classification rules stay byte-identical; PRD `default_model` floor
  still wins.
- No task loops on a weak model: every dropped-floor task is covered by the
  00065 budgets and breaker.
- One knob restores today's sonnet floor.

## Functional Decomposition

### Capability: Classifier floor shift

plan-tasks step 4.7 classifies routine mechanical work down to haiku +
qwen-eligible; sonnet becomes the middle, not the default floor.

#### Feature: Task-mix evidence pass

- **Description**: Derive the new haiku rules from recent real batches, not
  vibes (resolves the discovery's open question on exact thresholds).
- **Inputs**: At least 2 recent batches' reports and archived states: task
  descriptions, assigned tiers, attempt outcomes.
- **Outputs**: A rule diff for step 4.7: which shapes (keywords, file counts,
  line budgets) move from sonnet-default to haiku, each backed by task ids
  that would have flipped and how they actually fared.
- **Behavior**: Deterministic queries over the artifacts; if fewer than 2
  batches carry usable data, restrict the shift to unambiguous mechanical
  shapes and say so in the task report (fail loud, not wide).

#### Feature: Floor rules edit

- **Description**: Apply the evidence-backed rule diff to the classifier.
- **Inputs**: The rule diff; plan-tasks SKILL.md step 4.7 (anchors :224-267,
  :269-289 as of the 2026-07-13 scan).
- **Outputs**: Edited step 4.7: haiku rules first, sonnet as middle default,
  opus novelty rules untouched; tier lists cited from model-ladder.md instead
  of restated.
- **Behavior**: PRD `default_model` floor keeps precedence. Kill-switch: a
  floor knob (name recorded in model-ladder.md, e.g.
  `_PLAN_TASKS_FLOOR=sonnet`) restores today's floor without editing rules.

### Capability: qwen bottom rung

Every eligible task tries qwen first when preflight is healthy (Q7).

#### Feature: One-shot budget removal

- **Description**: Drop qwen's one-shot-per-PRD budget; fences stay.
- **Inputs**: work SKILL.md budget text (anchors :68, :324) and routing table;
  `work/references/qwen-integration.md`.
- **Outputs**: Routing table says eligible + healthy → qwen, no per-PRD cap;
  budget text removed, not contradicted elsewhere.
- **Behavior**: Eligibility fences verbatim (non-UI ∧ tier ∈ {haiku, sonnet} ∧
  ≤3 files ∧ no public-contract edits) plus `qwen_excluded_reason` stamping
  unchanged. The 00065 capability breaker is the bad-day stop; Claude at tier
  stays the infra fallback; the qwen→sonnet capability ladder stays the
  quality net.

#### Feature: Memory-pressure gate

- **Description**: qwen dispatch checks RAM headroom first (48GB box, cargo
  OOM lockout history; the server is 30B Q4 with 131K ctx).
- **Inputs**: Host memory stats at dispatch time; threshold from
  model-ladder.md.
- **Outputs**: Dispatch decision; under pressure the task routes to Claude at
  its tier with `qwen_excluded_reason: memory_pressure` stamped.
- **Behavior**: `skills/work/scripts/check_memory_pressure.py`, stdlib-only,
  deterministic threshold, exit code drives the routing step. Unreadable
  stats fail toward Claude (safe) with the exclusion reason stamped. Folding
  the check into the qwen preflight itself stays a nice-to-have, out of scope
  here.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/
├── plan-tasks/
│   └── SKILL.md                         # step 4.7 floor rules + ladder citation
├── work/
│   ├── SKILL.md                         # budget removal; pressure gate in routing
│   └── scripts/
│       ├── check_memory_pressure.py     # NEW - Memory-pressure gate
│       └── test_check_memory_pressure.py# NEW - its tests
└── run-autopilot/references/
    └── model-ladder.md                  # floor knob + pressure threshold rows
```

### Module: classifier rules

- **Maps to capability**: Classifier floor shift
- **Responsibility**: Tier assignment rules with haiku floor for mechanical
  shapes; precedence of PRD default_model and the floor knob.
- **Exports**: plan-tasks SKILL.md step 4.7 text.

### Module: qwen lane routing

- **Maps to capability**: qwen bottom rung
- **Responsibility**: Uncapped eligible-task dispatch with fences, breaker
  consult (00065), and the pressure gate ahead of any qwen pick.
- **Exports**: work SKILL.md routing table text.

### Module: pressure script

- **Maps to capability**: qwen bottom rung
- **Responsibility**: Deterministic RAM headroom verdict.
- **Exports**: `check_memory_pressure.py` CLI (threshold in, exit code +
  one-line reason out).

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies inside this PRD - built first. External gates: 00058 and
00065 in `dev/local/prds/done/`.

- **task-mix evidence pass**: the data the rule diff stands on.
- **pressure script**: independently testable verdict.

### Core Layer (Phase 1)

- **classifier rules**: Depends on [task-mix evidence pass].
- **qwen lane routing**: Depends on [pressure script] (gate wired into the
  same routing table edit).

### Integration Layer (Phase 2)

- **ladder knob rows + visibility**: Depends on [classifier rules, qwen lane
  routing].

## Implementation Phases

### Phase 0: Foundation

**Goal**: Gates verified, evidence gathered, deterministic core tested.

**Tasks**:

- [ ] Verify the external gates (no deps) - Premise: 00058 AND 00065 sit in
  `dev/local/prds/done/`; an un-evaled engine or a missing escalation net
  makes this PRD unsafe. Acceptance: on failure, record a defer/stall per
  00017 mechanics and run nothing else; on success, name both done files in
  the task report.
- [ ] Task-mix evidence pass over recent batches (no deps) - Acceptance: rule
  diff lists each proposed shape move with supporting task ids and outcomes;
  under-data fallback (unambiguous shapes only) applied and stated when it
  bites.
- [ ] Implement check_memory_pressure.py with tests (no deps) - Acceptance:
  tests cover headroom-ok, under-pressure, and unreadable-stats (fails toward
  Claude with reason); stdlib-only.

**Exit Criteria**: Gates verified; rule diff written; pressure tests green.

### Phase 1: Core

**Goal**: Cheaper defaults live in both skills.

**Tasks**:

- [ ] Edit plan-tasks step 4.7 per the rule diff (depends on: Phase 0) -
  Acceptance: opus rules byte-identical (diff shown in task report); haiku
  rules cite their evidence; default_model and floor-knob precedence stated;
  tier lists cite model-ladder.md.
- [ ] Remove the qwen one-shot budget and wire the pressure gate into the
  routing table (depends on: Phase 0) - Premise: re-locate budget text by
  content (anchors :68, :324 may have drifted). Acceptance: fences verbatim;
  breaker consult cited; pressure gate ordered before preflight; no other
  text still claims a one-shot budget.

**Exit Criteria**: Both skills carry the new defaults with zero contradictory
leftovers.

### Phase 2: Integration

**Goal**: Knobs documented, behavior visible.

**Tasks**:

- [ ] Add floor-knob and pressure-threshold rows to model-ladder.md and
  verify exclusion visibility (depends on: Phase 1) - Acceptance: knob name +
  legacy value documented; `memory_pressure` listed among exclusion reasons
  wherever they are enumerated (state-schema/report format).

**Exit Criteria**: One knob restores the sonnet floor; exclusions render in
reports.

## Test Strategy

### Critical Scenarios

- **Happy path**: mechanical 2-file task → classified haiku + qwen_eligible;
  healthy preflight + headroom → qwen dispatch (no one-shot cap on the second
  such task).
- **Edge case**: RAM under threshold → Claude at tier,
  `qwen_excluded_reason: memory_pressure`, no preflight probe run.
- **Edge case**: floor knob set to sonnet → classifier output matches today's
  tiers on the same fixture PRD.
- **Error case**: gates not done (00058 or 00065 missing) → defer/stall
  recorded, tree untouched.

## Risks

- **qwen thrash on the widened lane**: fences intact, 00065 breaker stops bad
  days, test gate + untouched review roster catch under-coverage.
- **Floor too aggressive**: escalation churn shows up in audit-routing per-rung
  stats; the knob reverts without a code change.
- **Evidence pass finds thin data**: restricted shift + loud note instead of
  guessy thresholds.
- **RAM contention despite the gate**: wrapper memory breaker stays as the
  backstop; threshold tunable in one place (ladder file).
