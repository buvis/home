---
catchup: skip
---

# Reconcile Autopilot Family Contracts

## Overview

### Problem Statement

The autopilot family (work, plan-tasks, review-work-completion, review-blindly, run-autopilot) carries contract drift and staleness that past incidents show is dangerous:

1. `work/SKILL.md` is 602 lines (validator warns at 500) and restates its own rules: the by-domain Tool Selection table duplicates the step-3 routing table (the file itself names step 3 as source of truth), the Subagent Dispatch Budget recap repeats ~6 times, the step-4 table repeats dispatch-log boilerplate per row, and PRD-number archaeology (00025/00031/00032/00044, dated stories) pads normative sections.
2. `review-work-completion/references/retry-policy.md` contradicts itself: the opening says "Retry up to 3 times / after 3 failures" while the same file later fixes the budget at one retry per agent, and every caller (autopilot review-phase handling, the Eve retry) uses one.
3. The reviewer roster in `review-work-completion/SKILL.md` lags `references/agent-invocation.md` (which defines Eve, the Fable 5 doubt reviewer shipped in PRDs 00036-00038) - and PRDs 00015/00019 (earlier by sequence) reshape the roster again (Blake added, Diana replaced by Quinn, Eve re-pointed to an opt-in extra lens). Roster and invocation reference must agree on the set in force at execution.
4. The review-coverage block schema was physically triplicated (canonical `references/review-coverage-format.md`, plus copies in `references/agent-prompts.md` and `review-blindly/SKILL.md`) with a duplicated gap-kind list. PRD 00016 (earlier by sequence) retires that block format outright; what remains here is sweeping any stale copies 00016's caller rewire missed.
5. `plan-tasks/SKILL.md` calibrates its budget formula to "Sonnet 4.6's 200K standard-tier ceiling" with a 30K overhead constant "measured at Sonnet 4.6", a retired model line.
6. `run-autopilot`'s Phase 6 restates plan-tasks step 4.7's `default_model` floor algorithm nearly verbatim instead of pointing at it.

### Target Users

Autopilot sessions (work and review phases); Bob when tuning dispatch budgets.

### Success Metrics

- `work/SKILL.md` at most 500 lines with every normative rule preserved (migration map proves it); validator length warning gone.
- Zero contradictory retry counts: `rg -n "3 times|three failures" ~/.claude/skills/review-work-completion/` returns nothing after reconciliation.
- Roster and invocation reference agree on the full reviewer set in force at execution (post-00015/00019: Alice, Blake, Bob, Carl, Quinn, plus opt-in Eve).
- Zero copies of the retired review-coverage block format or its gap-kind list survive in `agent-prompts.md`, `review-blindly/SKILL.md`, or run-autopilot prose (post-00016 sweep).
- No "Sonnet 4.6" references remain in plan-tasks; the overhead constant is re-derived against the current work-session model per the file's own procedure.

## Functional Decomposition

### Capability: Slim work skill

#### Feature: Deduplicate work SKILL.md

- **Description**: Remove internal restatements from `~/.claude/skills/work/SKILL.md`; keep every rule.
- **Inputs**: Current SKILL.md (602 lines).
- **Outputs**: At most 500 lines. Specifically: the "Tool Selection" by-domain section collapses to a short pointer at the step-3 routing table (which stays complete); repeated "must satisfy the Subagent Dispatch Budget (50K, abort line)" recaps become one-line pointers to the Budget section; the step-4 result table's repeated "Dispatch-log append ... per references/subagent-dispatch.md" phrasing collapses to one footnote line under the table; PRD-number rationale and dated incident stories (2026-06-09 qwen routing, 2026-06-25 RAM lockout) move to a new `~/.claude/skills/work/references/design-rationale.md` with one-line pointers, rules staying inline.
- **Behavior**: Same migration-map discipline as PRD 00043: `dev/local/tmp/00044-work-migration-map.md` maps every heading and normative rule to its new location. No semantic change; `references/` files other than the new design-rationale.md unchanged.

### Capability: Reconcile review contracts

#### Feature: Fix retry-policy contradiction

- **Description**: One retry budget, stated once.
- **Inputs**: `~/.claude/skills/review-work-completion/references/retry-policy.md` (opening "up to 3 times" vs later "total retry budget per agent is one retry").
- **Outputs**: The file states the one-retry-per-agent budget consistently; the "3 times" opening is rewritten.
- **Behavior**: Before editing, `rg -n "retry" ~/.claude/skills/review-work-completion ~/.claude/skills/run-autopilot` to confirm no caller depends on the 3-count (autopilot Phase 8 "retry once Alice-style" is the expected pattern). Report the sweep result.

#### Feature: Add Eve to the reviewer roster

- **Description**: The roster matches the invocation reference.
- **Inputs**: `review-work-completion/SKILL.md` roster; `references/agent-invocation.md` (defines Eve).
- **Outputs**: Roster lists Eve with her role as of execution (post-00015: Claude Fable 5 doubt lens, joining the single review batch as an optional extra reviewer when PRD frontmatter sets `doubt_reviewer: fable`; the separate Phase 8 leg no longer exists).
- **Behavior**: One roster entry plus pointer to agent-invocation.md; no dispatch-behavior change. Premise: if 00015's collapse already added Eve to the roster, record no-change-needed.

#### Feature: Sweep stale coverage-format copies

- **Description**: PRD 00016 retired the `---review-coverage---` block format and the gap-kind list; delete or update any copy its caller rewire missed. (The originally planned byte-sync test is superseded: the surviving contract is three regex-checked lines owned by `check_review_file.py`, too small to drift-guard.)
- **Inputs**: `rg -n "review-coverage|gap-kind|MISSING_FILES|UNMAPPED_FEATURE" ~/.claude/skills/review-work-completion ~/.claude/skills/review-blindly ~/.claude/skills/run-autopilot` at execution.
- **Outputs**: Every surviving copy of the retired format deleted; prompt-shipped reviewer instructions in `agent-prompts.md` state the post-00016 contract (per-reviewer section plus `Verdict:`/`Tests:` lines) instead. Zero hits for the retired block delimiters afterwards.
- **Behavior**: If 00016 stalled and the old gate is still live at execution, skip this sweep and report (never delete a format a live gate still parses).

### Capability: Refresh calibration and pointers

#### Feature: Re-derive plan-tasks budget calibration

- **Description**: Remove retired-model references; refresh the constant.
- **Inputs**: `plan-tasks/SKILL.md` step 4.5 (formula, "Sonnet 4.6's 200K standard-tier ceiling", 30K overhead constant) and the "30K overhead re-derivation" procedure in the same file.
- **Outputs**: Model-agnostic wording ("the work-tier model's standard context ceiling"), a re-derived overhead constant following the file's own procedure (read the first `message.usage` line of a fresh work-phase transcript), and an updated worked example if the constant moved more than 5K.
- **Behavior**: The 150K/75K thresholds stay unless the re-derivation forces a change; if changed, update every mention in the file (steps 2.5, 4.5, 4.6, Estimator caveats) and report old vs new.

#### Feature: Point Phase 6 at the plan-tasks floor rule

- **Description**: Stop restating the `default_model` floor algorithm in run-autopilot.
- **Inputs**: The Phase 6 "[D{cycle}] follow-ups" tier text (after PRD 00043 it lives in `run-autopilot/references/phase-review.md`; if 00043 did not land, edit `run-autopilot/SKILL.md` Phase 6 instead).
- **Outputs**: The restated algorithm becomes: "apply the `default_model` floor exactly as `/plan-tasks` step 4.7 defines it (max of classifier tier and `default_model`; re-parse PRD frontmatter at Phase 6 runtime; absent -> pass-through, invalid -> warn and pass through)". Behavior described stays identical.
- **Behavior**: One-directional pointer; plan-tasks remains the single source of truth.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/
├── work/
│   ├── SKILL.md                          # Maps to: Slim work skill (<=500 lines)
│   └── references/design-rationale.md    # NEW rationale home
├── review-work-completion/
│   ├── SKILL.md                          # roster + Eve
│   ├── references/retry-policy.md        # contradiction fixed
│   ├── references/agent-prompts.md       # post-00016 contract wording
│   └── (no new scripts; the planned sync test is superseded by 00016's gate rewrite)
├── review-blindly/SKILL.md               # stale coverage-format copy removed
├── plan-tasks/SKILL.md                   # calibration refresh
└── run-autopilot/references/phase-review.md # Phase 6 pointer (or SKILL.md if 00043 absent)
```

### Module: work

- **Maps to capability**: Slim work skill
- **Responsibility**: Task-execution contract, deduplicated
- **Exports**: routing table (single copy), Budget section (single copy), `references/design-rationale.md`

### Module: review-work-completion

- **Maps to capability**: Reconcile review contracts
- **Responsibility**: Reviewer roster, retry policy, post-00016 review-file contract wording
- **Exports**: reconciled `retry-policy.md`, roster entry for Eve

### Module: plan-tasks

- **Maps to capability**: Refresh calibration and pointers
- **Responsibility**: Budget formula calibrated to the current model; single owner of the `default_model` floor
- **Exports**: step 4.5 formula, step 4.7 floor rule

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies; built first.

- **retry-policy fix, Eve roster entry, plan-tasks calibration**: independent single-file edits

### Core Layer (Phase 1)

- **stale coverage-format sweep**: depends on [retry-policy fix] only for shared-file churn avoidance (same skill dir); technically independent
- **work SKILL.md dedup**: independent, placed here for review-load balance

### Integration Layer (Phase 2)

- **Phase 6 pointer**: depends on PRD 00043's layout when present (falls back to SKILL.md edit)
- **verification**: depends on all

## Implementation Phases

### Phase 0: Foundation

**Goal**: The three independent one-file fixes.

**Tasks**:

- [ ] Fix retry-policy contradiction (no deps) - Acceptance: `rg -n "3 times|three failures" ~/.claude/skills/review-work-completion/` empty; one-retry budget stated; caller sweep pasted
- [ ] Add Eve to the reviewer roster (no deps) - Acceptance: roster names five reviewers; Eve entry says Phase-8-only, `doubt_reviewer: fable` opt-in
- [ ] Re-derive plan-tasks budget calibration (no deps) - Acceptance: `rg -n "Sonnet 4.6" ~/.claude/skills/plan-tasks/` empty; re-derivation evidence (usage line values) pasted; worked example consistent with the constant

**Exit Criteria**: The three one-file fixes committed with their acceptance evidence.

### Phase 1: Core

**Goal**: Drift guard and the work slim-down.

**Tasks**:

- [ ] Sweep stale coverage-format copies (depends on: Phase 0) - Acceptance: rg sweep output pasted; zero surviving copies of the retired block format or gap-kind list; agent-prompts.md states the post-00016 Verdict/Tests contract; skip-and-report if 00016 stalled
- [ ] Deduplicate work SKILL.md (depends on: Phase 0) - Acceptance: at most 500 lines; `dev/local/tmp/00044-work-migration-map.md` complete; validator length warning gone; routing table and Budget section each appear exactly once

**Exit Criteria**: Sweep clean; work migration map complete.

### Phase 2: Integration

**Goal**: Cross-skill pointer and proof.

**Tasks**:

- [ ] Point Phase 6 at the plan-tasks floor rule (depends on: Phase 1) - Acceptance: the floor algorithm text appears in exactly one skill (plan-tasks); Phase 6 text is a pointer with identical described behavior
- [ ] Verification (depends on: all) - Acceptance: full pytest over review-work-completion/scripts/ and run-autopilot/scripts/ green (counts pasted); create-skill validator clean on work, plan-tasks, review-work-completion, review-blindly

**Exit Criteria**: Success metrics all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: post-00016 tree → Expected: coverage-format sweep finds nothing; agent-prompts.md already states the Verdict/Tests contract
- **Edge case**: a stale `---review-coverage---` copy survives in review-blindly → Expected: sweep finds and removes it (the drift class 00016 retired)
- **Edge case**: PRD 00043 not yet landed when this PRD runs → Expected: Phase 6 pointer edit targets `run-autopilot/SKILL.md` Phase 6; all acceptance criteria unchanged
- **Error case**: retry sweep reveals a real 3-retry caller → Expected: stop, surface it, do not force the one-retry rewrite

## Risks

- **Over-compression of work/SKILL.md**: mitigated by the migration map and the 500-line target (not a minimal target; keep clarity).
- **Perturbing dispatched prompts**: agent-prompts.md text ships verbatim to external reviewers; keep contract-wording changes minimal and consistent with the post-00016 format.
- **Ordering**: run after PRD 00043 (sequence numbering already enforces this in a drained backlog).
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; no CHANGELOG entries.
