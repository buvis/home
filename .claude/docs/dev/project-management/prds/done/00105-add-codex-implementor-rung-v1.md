# Add codex Implementor Rung

> Renumbered 00077 → 00105 on 2026-08-01 (backlog tail resequence; mapping in memory `project_backlog_renumber_2026_08`). Historical artifacts keep the old number: `dev/local/reviews/00077-*`, `ledger/00077-assumptions-parked.md`, the batch-202607202320 deferred stall record, and its design doc — RENAMED to `designs/00105-add-codex-implementor-rung-v1-design.md` so the Phase 1.5 artifact skip resolves.
> Source: `dev/local/discovery/00065-deepen-model-escalation.md` (requirement
> 9; Q9/F6). PRD E of the escalation initiative. The review-only policy for
> codex is lifted deliberately here. Requires 00065 (ladder file) done.

## Status (CLOSED 2026-08-07, fast-track item 11)

All four PRD tasks verified complete at HEAD. Full record in
`dev/local/prds/FASTTRACK-PLAN-v5.md` § Session log, item 11.

**The parked-status numbers below were both wrong** and are kept only as a
record of what the loop believed. "23 of 28" and "rework tasks 20-28" both
count the loop's own 28-task `/plan-tasks` expansion, not this PRD's four
tasks. Derive scope from the tree, never from these numbers.

Closed by: § Implementor-mode divergence added to
`use-codex/references/dispatch-contract.md` (the one HIGH the batch never
closed — dispatch departed from the authoritative contract while claiming to
reuse it unchanged), plus the exit-4 ownership correction and its regression
guard. Commit `5455a046`.

**Non-convergence diagnosed, and it was not the review gate re-opening rework.**
The terminal halt was the wrapper's park-marker staleness bound (7200s) being
narrower than the review-phase cap (10800s) — fixed 2026-07-30 in `bc00bf235`,
that class cannot recur. The remaining causes are review-gate noise (36 findings
classified `scope-overflow` at 1/5-2/5 consensus) and a consensus scorer that
merges only exact string matches. Both belong to PRDs **00094** and **00095**,
now queued ahead of 00106.

### Original parked note (2026-07-28, superseded)

Parked by the operator, not abandoned. Batch 202607202320 ran this PRD for 15
sessions / 21.5h / $351 and never converged: the wrapper parked it twice, three
sessions were killed by the 10800s wall-clock cap, and the loop halted systemic
on 2026-07-27 04:18.

- **Implementation is largely on master**: 23 of 28 tasks committed (see
  `git log --grep=codex` around 2026-07-22 and 2026-07-26 in `~/.buvis`).
- **Open**: rework tasks 20-28 at review cycle 2. All five lenses reported
  `done` and every doubt rubric rule passed, yet the gate kept re-opening
  rework - that non-convergence is the defect to diagnose before resuming.
- **Resume**: move back to `wip/`, re-plan from HEAD (the old task list was
  cleared from `state.json`), and run the review interactively rather than in
  the loop.

## Overview

### Problem Statement

The ladder jumps from free-but-narrow qwen straight to paid Claude tiers.
codex already runs in this loop as a reviewer under the shared dispatch
contract; as an implementor it could absorb eligible backend attempts that
today go directly to Claude at tier. A mid rung between qwen and
Claude-at-tier lowers the average cost per attempt without touching the
review safety net - provided codex never ends up reviewing its own
implementation with no other doubt voice (Bob self-review bias).

### Target Users

Unattended autoclaude batches with backend-heavy task mixes; the operator's
per-token bill.

### Success Metrics

- Eligible backend tasks dispatch codex between qwen and Claude-at-tier,
  behind fences declared in model-ladder.md and a kill-switch toggle.
- Every codex attempt is attributable (`implementor: codex` in attempts[]);
  audit-routing can report per-rung success for the codex rung.
- No PRD containing codex-implemented tasks is doubt-reviewed by codex alone.
- Dispatch reuses the existing contract verbatim (background Bash, prompt
  file, output file, watchdog); zero new halt classes.

## Functional Decomposition

### Capability: Rung declaration

The ladder file gains an active codex rung with fences and budget (M8 owns
the facts; this PRD flips them on).

#### Feature: Ladder entry and fences

- **Description**: Declare position, eligibility, budget, and toggle for the
  codex rung.
- **Inputs**: model-ladder.md (00065); reviewer-era codex behavior notes;
  fence decision from the design phase (open question below).
- **Outputs**: Ladder rows: rung position (between qwen and Claude-at-tier in
  dispatch order), eligibility fences (backend task shapes only; UI stays
  gemini), per-rung budget (initial + one feedback retry, same as every
  rung), kill-switch toggle name (e.g. `_WORK_CODEX_RUNG=off`), activation
  status flipped to active.
- **Behavior**: Fences and position live only in the ladder file; work cites
  them. Capability failure at codex escalates per the ladder (next rung:
  Claude at the task's tier); infra failure falls back to Claude at tier
  without an escalation stamp (same asymmetry doctrine as qwen).

### Capability: Dispatch integration

codex implements under the same contract it reviews under.

#### Feature: codex implementor dispatch

- **Description**: Route eligible tasks to a codex CLI run that edits the
  tree.
- **Inputs**: An eligible task at dispatch time;
  `use-codex/references/dispatch-contract.md`.
- **Outputs**: A background Bash codex invocation (`-f` prompt file, `-o`
  output file, TaskOutput watchdog, edit-enabled sandbox); an attempt entry
  stamped `implementor: codex`.
- **Behavior**: Never Agent-wrapped (era invariant). Completion is judged by
  the output file plus the step-5.5 test gate, not by exit code alone (the
  review harness's exit-4 false-positive taught that lesson). Preflight
  equivalent: a cheap CLI health probe before first dispatch of a batch;
  unhealthy → Claude at tier, infra semantics. The 00065 escalation flow,
  budgets, and diagnosis apply to the codex rung unchanged.

### Capability: Review-roster constraint

A codex-implemented task is never doubt-reviewed by codex alone.

#### Feature: Doubt-roster guard

- **Description**: Review assembly checks implementor attribution before
  picking the doubt leg.
- **Inputs**: `state.tasks[].attempts[]` implementor fields; the review
  roster assembly in phase-review; the 00036-00038 fable doubt-leg machinery.
- **Outputs**: A deterministic roster rule: if any completed task in the PRD
  carries `implementor: codex`, the doubt review must include a non-codex
  voice (fable leg or equivalent); the chosen enforcement point is settled in
  design (open question below).
- **Behavior**: The rule is checkable from state alone (jq-expressible); the
  review file records which rule fired so the constraint is auditable.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/
├── run-autopilot/references/
│   ├── model-ladder.md            # codex rung row: position, fences, budget,
│   │                              # toggle, status active
│   └── phase-review.md            # doubt-roster guard rule
├── work/
│   └── SKILL.md                   # routing table: codex rung + health probe
└── use-codex/references/
    └── dispatch-contract.md       # implementor-mode notes (only if the
                                   # contract needs them; premise-checked)
```

### Module: ladder rung row

- **Maps to capability**: Rung declaration
- **Responsibility**: The only statement of codex fences, position, budget,
  and toggle.
- **Exports**: model-ladder.md codex rows.

### Module: work codex routing

- **Maps to capability**: Dispatch integration
- **Responsibility**: Rung consult in the routing table, health probe, contract
  invocation, attribution stamping.
- **Exports**: work SKILL.md routing table text.

### Module: doubt-roster guard

- **Maps to capability**: Review-roster constraint
- **Responsibility**: Deterministic non-codex-doubt rule at review assembly.
- **Exports**: phase-review.md roster rule.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies inside this PRD - built first. External: 00065 in
`dev/local/prds/done/` (ladder file + escalation net).

- **ladder rung row**: the declared facts the other modules cite.

### Core Layer (Phase 1)

- **work codex routing**: Depends on [ladder rung row].

### Integration Layer (Phase 2)

- **doubt-roster guard**: Depends on [work codex routing] (guards what the
  rung produces).

## Implementation Phases

### Phase 0: Foundation

**Goal**: Premises verified; the rung is declared before it routes.

**Tasks**:

- [ ] Verify premises (no deps) - Premise: 00065 in done/ (ladder file
  exists); codex CLI passes a live health probe; dispatch-contract.md still
  matches how reviewers invoke codex today (re-read, note drift). Acceptance:
  on premise failure, defer/stall per 00017 and run nothing else; on success,
  the probe command and contract status land in the task report.
- [ ] Write the codex rung rows into model-ladder.md (depends on: premise
  task) - Acceptance: position, fences (from the design decision), budget,
  toggle name, and escalation/infra semantics stated; no fence text
  duplicated anywhere else.

**Exit Criteria**: Ladder declares the rung; premises verified this run.

### Phase 1: Core

**Goal**: Eligible tasks actually dispatch codex.

**Tasks**:

- [ ] Wire the codex rung into work's routing table with health probe,
  contract invocation, attribution stamping, and the toggle bypass (depends
  on: Phase 0) - Acceptance: routing prose cites the ladder for every fence
  and budget; completion judged by output file + test gate (exit code alone
  never passes a task); `_WORK_CODEX_RUNG=off` short-circuits the rung; infra
  failure routes Claude-at-tier with no escalation stamp.

**Exit Criteria**: Routing table carries the rung; a fixture walkthrough
shows dispatch, infra fallback, and toggle-off paths.

### Phase 2: Integration

**Goal**: The self-review hole is closed.

**Tasks**:

- [ ] Implement the doubt-roster guard in phase-review.md (depends on: Phase
  1) - Acceptance: fixture with a codex-implemented task yields a doubt
  roster containing a non-codex voice; fixture without codex attempts leaves
  today's roster untouched; the review file records the fired rule.

**Exit Criteria**: Guard verified on both fixtures; all walkthroughs green.

## Test Strategy

### Critical Scenarios

- **Happy path**: eligible backend task, healthy probe → codex dispatch,
  gate pass, attempt stamped `implementor: codex`.
- **Edge case**: codex CLI dies mid-run → watchdog + missing output file →
  infra fallback to Claude at tier, no escalation stamp, batch continues.
- **Edge case**: toggle off → rung skipped entirely; routing identical to
  pre-PRD behavior.
- **Error case**: codex-implemented task reaches review with a codex-only
  doubt roster in the fixture → guard rewrites the roster and records it.

## Risks

- **Self-review bias**: the doubt-roster guard is deterministic over
  attempts[]; review files make it auditable.
- **codex CLI flakiness**: watchdog + output-file check + infra fallback;
  health probe before first dispatch; known exit-code false positives never
  decide success.
- **Fences too wide**: per-rung success lands in audit-routing; the toggle
  reverts in one env var.
- **Contract drift between reviewer and implementor use**: premise task
  re-reads the dispatch contract and notes divergence before any edit.

## Open Questions

- Eligibility fences: which task shapes enter at codex (file-count, language,
  novelty bounds)? UI stays gemini. (Design phase, informed by reviewer-era
  codex behavior.)
- Enforcement point for the doubt guard: roster assembly rule in phase-review
  vs a check in the review-coverage gate? (Design phase.)
