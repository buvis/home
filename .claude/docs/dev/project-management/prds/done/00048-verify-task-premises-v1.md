---
catchup: skip
design: skip
---

# Verify Task Premises at Execution Time

## Overview

### Problem Statement

PRDs are authored from observed repo state, then executed later by autopilot against a tree that may have moved. The gap is real: during the 2026-07-07 skill audit, `brief-portfolio` went from TODO scaffold to live skill between audit read and PRD write, and only a lucky mid-session refresh stopped a queued task from archiving a skill the user was actively building. Today nothing in the PRD-to-task pipeline requires a task to re-check the facts it rests on: `create-prd` has no authoring rule for it, `plan-tasks` has no field to carry it, and `work` dispatches implementors without a premise gate. PRDs 00041/00046/00047 carry hand-written premise clauses; the convention should be systemic, not per-PRD heroics.

### Target Users

Every future PRD authored by `create-prd`, planned by `plan-tasks`, and executed by `work` (autopilot or manual).

### Success Metrics

- `create-prd` instructs authors to state a premise plus execution-time re-check on every task that deletes, moves, overwrites, or edits content based on observed repo state.
- `plan-tasks` carries an optional `Premise:` field verbatim into task descriptions, with skip-and-report semantics defined.
- `work` verifies a task's `Premise:` before dispatching any implementor and treats a failed premise as a blocker, not a go.
- Tasks without a `Premise:` line behave exactly as today (legacy plans unaffected).
- create-skill validator clean on all three touched skills.

## Functional Decomposition

### Capability: Author premises into PRDs

#### Feature: Add premise authoring rule to create-prd

- **Description**: PRD authors must bake premise re-verification into observed-state tasks.
- **Inputs**: `~/.claude/skills/create-prd/SKILL.md` step 3 (Format as PRD).
- **Outputs**: A new authoring rule appended to step 3, stating: any task whose action deletes, moves, overwrites, or edits content justified by observed repo state MUST (a) state that premise in its Feature or task text and (b) include an execution-time re-check in its acceptance criteria, with a failed premise meaning skip and report, never force.
- **Behavior**: Templates in `assets/` stay unchanged (the rule is authoring guidance, not structure; the heading gate must not change). The rule cites the brief-portfolio near-miss in one sentence as rationale.

#### Feature: Add Premise field to plan-tasks

- **Description**: The task description format carries the premise verbatim.
- **Inputs**: `~/.claude/skills/plan-tasks/SKILL.md` step 4 (task description format block and its verbatim-copy rules).
- **Outputs**: The format block gains an optional line between `Reuse:` and `Contract`: `Premise: {observed-state facts this task depends on; re-verify before acting}`. A short paragraph after the Contract-verbatim rule states: when the PRD states a premise for a task, copy it verbatim (same discipline as `Contract`); the implementor must re-verify it first and treat a false premise as a blocker (stop, report, do not proceed - in loop mode this feeds 00017's stall path; a premise failure is never resolved by assumption).
- **Behavior**: Absent `Premise:` means no new behavior; nothing is inferred or invented for tasks whose PRD states none.

### Capability: Enforce premises at dispatch

#### Feature: Gate work dispatch on the premise

- **Description**: `work` checks the premise before spending an implementor dispatch.
- **Inputs**: `~/.claude/skills/work/SKILL.md` step 2.5 (Load project context, which already carries the Ambiguity check).
- **Outputs**: One paragraph added beside the Ambiguity check: if the task description carries a `Premise:` line, verify each stated fact against the current tree (`ls`, `rg`, `git ls-files` as fits) BEFORE dispatching Tess or Ivan; if any fact no longer holds, do not dispatch. Interactively: stop and report which fact failed, leaving the task in_progress for the user or the decision gate. In loop mode (post-00017): a failed premise is never assumed through - it takes the loop-mode stall path (recovery.md stall procedure), unlike ambiguities, which 00017 resolves by simplest safe assumption.
- **Behavior**: Tasks without a `Premise:` line skip the check entirely (zero behavior change for legacy plans). The check is a cheap read-only probe, never a mutation.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/
├── create-prd/SKILL.md      # Maps to: Author premises into PRDs (step 3 rule)
├── plan-tasks/SKILL.md      # Maps to: Author premises into PRDs (Premise field)
└── work/SKILL.md            # Maps to: Enforce premises at dispatch (step 2.5 gate)
```

### Module: create-prd

- **Maps to capability**: Author premises into PRDs
- **Responsibility**: Authoring rule that puts premises into PRDs at creation time
- **Exports**: step 3 premise rule

### Module: plan-tasks

- **Maps to capability**: Author premises into PRDs
- **Responsibility**: Verbatim transport of premises from PRD into task descriptions
- **Exports**: `Premise:` field in the task description format

### Module: work

- **Maps to capability**: Enforce premises at dispatch
- **Responsibility**: Pre-dispatch premise verification with blocker semantics
- **Exports**: step 2.5 premise gate

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies; built first.

- **create-prd rule**: independent edit
- **plan-tasks field**: independent edit (defines the field the gate reads)

### Core Layer (Phase 1)

- **work gate**: depends on [plan-tasks field] (the gate reads the field the format defines)

### Integration Layer (Phase 2)

- **verification**: depends on all

## Implementation Phases

Execution-time premise rule: this PRD's own edits follow the convention it introduces; re-verify each anchor section still exists as described before editing (PRDs 00017 and 00044 edit run-autopilot references and plan-tasks/work earlier in this backlog; anchor by section name, not line number).

### Phase 0: Foundation

**Goal**: Authoring and planning sides carry the convention.

**Tasks**:

- [ ] Add premise authoring rule to create-prd (no deps) - Acceptance: step 3 contains the rule covering delete/move/overwrite/observed-state edits with skip-and-report semantics; `assets/` templates byte-unchanged
- [ ] Add Premise field to plan-tasks (no deps) - Acceptance: format block shows the optional `Premise:` line between `Reuse:` and `Contract`; verbatim-copy and blocker semantics stated; no change to `Contract`/`Acceptance criteria` rules

**Exit Criteria**: Both edits in place with acceptance checks green.

### Phase 1: Core

**Goal**: Execution side enforces it.

**Tasks**:

- [ ] Gate work dispatch on the premise (depends on: Phase 0) - Acceptance: step 2.5 contains the premise gate with read-only verification and blocker semantics; explicit statement that tasks without `Premise:` are unaffected

**Exit Criteria**: Gate paragraph present beside the Ambiguity check.

### Phase 2: Integration

**Goal**: Proof.

**Tasks**:

- [ ] Verification (depends on: all) - Acceptance: create-skill validator clean on create-prd, plan-tasks, work; `rg -n "Premise:" ~/.claude/skills/{create-prd,plan-tasks,work}/SKILL.md` shows the convention in all three; counts pasted

**Exit Criteria**: Success metrics all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: a future PRD task says `Premise: path X is untracked` and X is still untracked → Expected: work verifies, dispatches normally
- **Edge case**: the premise fails at execution (X became tracked or a live skill) → Expected: no dispatch, task surfaced as blocker naming the failed fact
- **Edge case**: task has no `Premise:` line (all legacy plans) → Expected: byte-identical behavior to today
- **Error case**: premise verification itself errors (probe command fails) → Expected: treat as unverified premise, surface as blocker; never proceed on an unknown

Docs-only PRD; verification is the validator plus the rg checks above.

## Risks

- **Ordering with PRD 00044**: both touch plan-tasks and work; 00044 runs first by sequence, and this PRD anchors edits by section name so the slimmed files still match.
- **Convention ignored by authors**: mitigated at two layers (plan-tasks copies it verbatim when present; work refuses dispatch on failed premises), so even a PRD without premises degrades to today's behavior, never worse.
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; no CHANGELOG entries.
