# Diagnose Then Escalate in the Work Loop

> Source: `dev/local/discovery/00065-deepen-model-escalation.md` (requirements
> 1, 6, 7, 8; absorbs backlog PRD 00060). PRD A of the escalation initiative
> (00065 + 00075-00079 + claude-checkup audit-routing; tiering PRDs renumbered
> from 00066-00070 on 2026-07-14 to enforce drain order).

## Overview

### Problem Statement

A struggling task today burns a full Opus review cycle before anyone reacts:
/work retries at the same tier under the retry cap, review flags the mess, and
only phase-review escalates. One recent PRD spent $11.14 (build) + $12.68
(review) across 9 Opus sessions this way. The loop also re-proves qwen
incapacity task after task: the one-shot budget protects a single task, nothing
learns across tasks. Struggle handling belongs in the loop: diagnose why the
gate failed, repair thin specs at the same tier, escalate solid ones one rung
up, and stop dispatching a local model that keeps failing.

### Target Users

Unattended autoclaude batches (cost and wall-clock budgets); the solo operator
reading batch reports afterwards.

### Success Metrics

- A task failing its test gate twice at a tier is diagnosed and either repaired
  or escalated inside the same build session; no review cycle needed to trigger
  the bump.
- Worst case per task: 2 dispatches per rung + 1 repair dispatch, never more.
- Every escalation records reason and diagnosis outcome in
  `state.tasks[].attempts[]`.
- Two consecutive failed qwen attempts stop qwen dispatch for the rest of the
  batch, visible in the batch report (00060 semantics).
- Zero new loop-halt classes; one env knob restores today's behavior.

## Functional Decomposition

### Capability: Canonical ladder declaration

One reference file declares the escalation ladder; consumers cite it instead of
restating it (discovery M8).

#### Feature: model-ladder.md

- **Description**: Single source of truth for rungs, budgets, and switches.
- **Inputs**: Discovery decisions Q4-Q7; existing tier rules in plan-tasks,
  work, phase-review, and the wrapper.
- **Outputs**: `skills/run-autopilot/references/model-ladder.md` declaring: the
  full ladder (qwen → codex → claude haiku/sonnet/opus → human-gated Fable),
  tier→backend mapping, per-rung attempt budgets (initial + one feedback
  retry), capability ladders (qwen→sonnet skipping haiku; haiku→sonnet→opus),
  the infra-vs-capability asymmetry, kill-switch knob names, per-rung
  activation status (codex rung and Fable gate are declared here, activated by
  PRDs 00077 and 00076), and a decay section stating today's behavior (no
  decay rules yet; PRD 00078 defines them).
- **Behavior**: plan-tasks, work, and phase-review cite this file (out-of-dir
  deps go in each skill's `## Dependencies` section); restated ladder text in
  those files is replaced by citations as their PRDs touch them. Wrapper knobs
  are documented here, implemented in their own PRDs.

#### Feature: Attempt attribution fields

- **Description**: attempts[] entries carry escalation and diagnosis facts
  (discovery M7).
- **Inputs**: Existing attempt fields (outcome, cause, implementor, model,
  preflight_outcome, pipeline) in state-schema.md.
- **Outputs**: state-schema.md gains, on attempt entries: `escalation_reason`
  (gate_failure | review_flag), `escalated_from` (tier), `diagnosis` (spec_gap
  | solid_spec), `repair_used` (bool), `breaker_skipped` (bool). Names follow
  the existing snake_case; absent fields mean legacy attempts.
- **Behavior**: /work stamps them when it diagnoses, repairs, or escalates;
  phase-review stamps `escalation_reason: review_flag` on its existing path so
  the two escalation sources stay distinguishable. audit-routing (claude-checkup
  PRD) consumes them; absence is tolerated everywhere.

### Capability: Struggle diagnosis

On the 2nd test-gate failure at a tier, decide spec gap vs capability gap
before spending anything bigger (Q4).

#### Feature: Deterministic spec shape-check

- **Description**: Script-checkable spec-gap signals run first.
- **Inputs**: The task description (Contract and Acceptance sections,
  referenced paths) and the repo tree.
- **Outputs**: JSON verdict: `spec_gap` with named gaps (missing Contract,
  missing Acceptance, referenced file absent) or `pass` (shape checks cannot
  call the spec thin).
- **Behavior**: `skills/work/scripts/diagnose_task.py`, stdlib-only, unit
  tested. Deterministic checks decide whenever they can
  (rules/ai-app-design.md); the orchestrator never overrides a deterministic
  spec_gap.

#### Feature: Inline rubric judgment

- **Description**: The fuzzy call when shape checks pass: is the spec still
  thin?
- **Inputs**: Shape-check output, task text, both gate-failure outputs.
- **Outputs**: `spec_gap` or `solid_spec` plus a one-line justification,
  stamped into the attempt entry.
- **Behavior**: Judged inline by the /work orchestrator session (no extra
  dispatch), rubric-led; the rubric lives in work SKILL.md. It runs at the
  session's model tier; mis-diagnosis risk is accepted and measured via the
  attribution fields.

#### Feature: Task-description repair

- **Description**: Thin spec means fix the task, not the model.
- **Inputs**: spec_gap verdict with named gaps; the PRD and design doc.
- **Outputs**: Repaired task description (gaps filled from source docs) and one
  same-tier re-dispatch.
- **Behavior**: Max one repair per task in total; a gate failure after the
  repair takes the solid-spec path. A thin spec never triggers a tier bump
  (2026-06-29 batch evidence: most non-escalations were spec gaps).

### Capability: In-loop tier escalation

Solid spec plus repeated failure means the next rung, with context.

#### Feature: Rung escalation dispatch

- **Description**: Reset and re-dispatch one rung up.
- **Inputs**: The failed attempts, task tier, model-ladder.md.
- **Outputs**: Implementation reset to the task's test commit; a fresh dispatch
  one rung up whose prompt carries a failure summary (failing test names, last
  gate output excerpt, diagnosis verdict, prior implementor and tier).
- **Behavior**: Budgets per the ladder file: initial + one feedback retry per
  rung; a 2nd failure at the new rung re-enters diagnosis (repair unavailable
  if already used). Ladders: qwen→sonnet (skips haiku), haiku→sonnet→opus.
  Infra failure is not capability failure: infra falls back at the same tier
  (existing behavior, unchanged). Deterministic precedence: infra fallback >
  breaker > repair > escalate. Opus exhaustion flows into the existing
  abort/stall machinery (00017); the Fable rescue (00076) hooks that seam
  later. Kill-switch: `_AUTOPILOT_ESCALATION=legacy` (name recorded in the
  ladder file) restores today's same-tier retry cap.

#### Feature: qwen capability breaker

- **Description**: Stop re-proving qwen incapacity across tasks (absorbs
  00060).
- **Inputs**: qwen attempt outcomes at the step-5.5 test gate.
- **Outputs**: state.json fields `qwen_gate_failures_consecutive` (int) and
  `qwen_breaker {tripped, after_task, failed_tasks[]}`; one line in the batch
  report's `### Implementor Mix` section (`capability breaker: not tripped` or
  `tripped after <task> (2 consecutive gate failures: <id>, <id>); N tasks
  rerouted`).
- **Behavior**: Reset at batch start and on any qwen gate pass; increment per
  qwen gate failure; latch at 2 consecutive. Rework attempts never touch it
  (rework never routes qwen). Tripped: every later qwen-eligible task routes to
  Claude at its ORIGINAL tier, no preflight probe, attempt stamped
  `breaker_skipped: true`; Quinn (review voice) unaffected. 00060's hard
  premise gate (wait for the orchestrator package) is superseded by discovery
  Q9: the breaker lands in skill prose + state.json now; the 00051-00053
  rewrite absorbs it later. Premise: 00060 sits in `dev/local/prds/hold/` as a
  merge-absorbed original; re-check at execution and stop and report if it is
  back in backlog/ or wip/ (double implementation risk).

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── skills/run-autopilot/references/
│   ├── model-ladder.md            # NEW - Canonical ladder declaration
│   ├── state-schema.md            # attempts[] attribution + breaker fields
│   └── phase-review.md            # ladder text replaced by citation
└── skills/work/
    ├── SKILL.md                   # step 5.5: diagnose → repair/escalate; breaker
    └── scripts/
        ├── diagnose_task.py       # NEW - deterministic spec shape-check
        └── test_diagnose_task.py  # NEW - its tests
```

### Module: model-ladder reference

- **Maps to capability**: Canonical ladder declaration
- **Responsibility**: Declare rungs, budgets, capability ladders, switches, and
  activation status; the only place these are stated.
- **Exports**: `model-ladder.md` (cited by plan-tasks, work, phase-review,
  wrapper docs).

### Module: state schema extension

- **Maps to capability**: Canonical ladder declaration
- **Responsibility**: Field contract for attribution stamps and breaker state.
- **Exports**: state-schema.md definitions for the five attribution fields and
  two breaker fields, with legacy-absence semantics.

### Module: diagnose script

- **Maps to capability**: Struggle diagnosis
- **Responsibility**: Deterministic shape checks with named gaps.
- **Exports**: `diagnose_task.py` CLI (task file path in, JSON verdict out).

### Module: work routing prose

- **Maps to capability**: Struggle diagnosis, In-loop tier escalation
- **Responsibility**: step 5.5 flow (gate failure → budget check → diagnosis →
  repair or escalate), breaker consult in the routing table, attribution
  stamping.
- **Exports**: work/SKILL.md step 5.5 and routing table text.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **model-ladder reference**: the declared rules everything else cites.
- **state schema extension**: field contract for stamps and breaker.
- **diagnose script**: deterministic verdicts, independently testable.

### Core Layer (Phase 1)

- **work routing prose**: Depends on [model-ladder reference, state schema
  extension, diagnose script].

### Integration Layer (Phase 2)

- **phase-review citation + breaker report line**: Depends on [work routing
  prose] (the line renders fields Phase 1 writes; phase-review cites the
  ladder).

## Implementation Phases

### Phase 0: Foundation

**Goal**: Contracts exist and the deterministic core is tested.

**Tasks**:

- [ ] Re-locate the seams by content, not line numbers: work SKILL.md
  same-tier retry cap and routing table, phase-review escalation section,
  state-schema attempts[] (no deps) - Premise: the 2026-07-13 discovery
  anchors (work :62-74, :259-271, :315-326; phase-review :153-172) still
  describe the tree; on drift, record actual anchors before editing.
  Acceptance: all seams named with current headings/step numbers in the task
  report.
- [ ] Write model-ladder.md (no deps) - Acceptance: declares the full ladder,
  tier→backend map, per-rung budgets, both capability ladders, the asymmetry
  rule, kill-switch knob names, activation status, and the no-decay-yet note;
  no other file needs to restate a budget to be understood.
- [ ] Extend state-schema.md with attribution + breaker fields (no deps) -
  Acceptance: five attribution fields and two breaker fields defined with
  types and legacy-absence semantics.
- [ ] Implement diagnose_task.py with tests (no deps) - Acceptance: tests
  cover missing Contract, missing Acceptance, dangling file reference, and
  all-present pass; stdlib-only; verdict shape documented in the docstring.

**Exit Criteria**: Ladder file and schema merged; diagnose tests green.

### Phase 1: Core

**Goal**: /work diagnoses and escalates instead of looping a weak model.

**Tasks**:

- [ ] Rewrite work step 5.5 and the routing table: per-rung budgets, diagnosis
  call, repair path, escalation dispatch with failure summary, breaker counter
  and reroute, attribution stamping, `_AUTOPILOT_ESCALATION=legacy` bypass
  (depends on: Phase 0) - Acceptance: prose cites the ladder file for every
  number; the deterministic precedence (infra fallback > breaker > repair >
  escalate) appears as a table; the legacy knob path is described; the
  same-tier retry cap text is replaced, not duplicated.

**Exit Criteria**: work/SKILL.md carries the new flow with zero restated
ladder constants.

### Phase 2: Integration

**Goal**: The rest of the family cites, renders, and survives the change.

**Tasks**:

- [ ] Replace phase-review's restated ladder with a citation and stamp
  `escalation_reason: review_flag` on its path (depends on: Phase 1) -
  Acceptance: phase-review contains no rung list of its own; its escalation
  semantics are unchanged.
- [ ] Add the breaker line to batch-report-format.md and its render rules
  (depends on: Phase 1) - Acceptance: absent fields render `not tripped`
  (legacy batches safe).
- [ ] Dry-run the flow on a synthetic state fixture (depends on: Phase 1) -
  Acceptance: a scripted walkthrough (fixture state + simulated gate failures)
  exercises repair-once, escalate, breaker trip, and legacy-knob paths;
  transcript attached to the task report.

**Exit Criteria**: All tests green; the walkthrough shows all four paths; the
batch report renders the breaker line.

## Test Strategy

### Critical Scenarios

- **Happy path**: solid spec, 2 gate failures at haiku → reset to test commit,
  sonnet dispatch with failure summary, attempt stamped
  `escalation_reason: gate_failure`, `escalated_from: haiku`.
- **Edge case**: thin spec (missing Acceptance) at 2nd failure → repair + one
  same-tier retry; a later failure escalates without a second repair;
  `repair_used: true` stamped.
- **Edge case**: qwen fail, pass, fail → breaker never trips (consecutive
  means consecutive).
- **Error case**: `_AUTOPILOT_ESCALATION=legacy` → today's same-tier retry cap
  behavior; no diagnosis, no new fields written.

## Risks

- **Diagnosis judged at session tier** (Sonnet once 00076 lands): deterministic
  checks decide whenever they can; every diagnosis outcome is stamped, so
  audit-routing surfaces mis-diagnosis rates; revert lives in the knob.
- **Escalation churn eats savings**: budgets bounded per rung, repair capped at
  one, diagnosis filters spec gaps before any bump.
- **Breaker masks a fixable infra fault**: the report line names the failing
  tasks; the preflight (infra) path never increments the capability counter.
- **Orchestrator rewrite (00051-00053) re-lands this in Python**: keep every
  decision jq-expressible over state fields, no prose-only state; the ladder
  file is the spec the rewrite ports.
