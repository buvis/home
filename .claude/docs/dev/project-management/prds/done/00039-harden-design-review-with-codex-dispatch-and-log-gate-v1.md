# Harden Design Review: Cross-Model Codex Dispatch and Review-Log Gate

## Overview

### Problem Statement

Evidence review of 30 autopilot PRDs across 5 repos (2026-07-04, grill-me-codex analysis) found the Phase 1.5 design review is the highest-leverage plan gate, but it failed in two verified ways:

1. **It can be skipped silently.** playground 00003 reached the work phase with an empty `## Review log` in its design doc; the skipped review let the largest plan defect in the corpus through (an incomplete style contract that cost a blind Critical plus a doubt rework round). Nothing today checks that the review actually ran.
2. **Claude reviews Claude's design (echo chamber).** jink 00023's design recorded "lossy-by-design" against the PRD's explicit "keep one" and got a 0-blocker verdict from the Claude reviewer; ddb 00161's DDL-injection design passed 2 Claude dispatches, then leaked for 3 straight review cycles and forced a cap-pause. A rival-model reviewer (codex) is structurally positioned to catch what the authoring model cannot see in itself.

Also: today the review loop ends early when dispatch 1 reports zero blockers, which is exactly the case (00023) where a second, cross-model opinion matters most.

### Target Users

The autopilot operator (solo developer). Benefit: fewer plan defects surviving to code, and a hard guarantee that no PRD reaches planning with an unreviewed design.

### Success Metrics

- A design doc whose `## Review log` contains no dispatch summary line can never reach Phase 2 (planning); the loop pauses instead.
- Every completed design review includes at least one codex (non-Claude) dispatch whenever the codex CLI is available, even when the Claude dispatch reports zero blockers.
- codex outage or hang never pauses an unattended run: the loop degrades to a Claude fallback dispatch with a loud note in `## Review log`.
- No change to design-solution's exit contract (path printed on success, non-zero exit on open cardinal sins/blockers).

## Functional Decomposition

### Capability: Cross-Model Design Review

Replace the second (all-Claude) reviewer dispatch in `/design-solution` step 4 with a mandatory codex dispatch, keeping Claude as fallback.

#### Feature: Codex adversarial dispatch

- **Description**: Dispatch 2 of the design review runs codex (read-only) instead of a second Claude subagent, and it always runs.
- **Inputs**: Current draft design doc, PRD summary, severity taxonomy (cardinal-sins file content plus the three severity definitions), findings-only instruction, structured findings format `{severity, title, evidence, suggested_fix}`.
- **Outputs**: codex findings appended to `## Review log` with reviewer identity (`dispatch 2 (codex): ...`); cardinal sins and blockers fixed in the doc.
- **Behavior**: After dispatch 1 (Claude subagent, unchanged) and its fixes, dispatch 2 runs codex via `codex-run.sh` as a background Bash call with a timed wait (never Agent-wrapped, per `review-work-completion/references/agent-invocation.md`). It runs even when dispatch 1 found zero blockers. Prompt content is the same package the Claude reviewer gets. codex is read-only and never edits files.

#### Feature: Verification dispatch (ceiling raised to 3)

- **Description**: When dispatch 2 (codex) finds cardinal sins or blockers, a third dispatch verifies the fixes; the ceiling moves from 2 to 3.
- **Inputs**: Revised design doc, the dispatch-2 findings.
- **Outputs**: Verification verdict appended to `## Review log`; exit 0 or non-zero.
- **Behavior**: Dispatch 3 runs only if dispatch 2 found cardinal sins or blockers. Reviewer: codex again (fresh call is acceptable; session resume is PRD 00040's scope and optional here). Open cardinal sins/blockers after dispatch 3 exit non-zero, exactly as today after dispatch 2.

#### Feature: Claude fallback on codex outage

- **Description**: codex unavailability degrades dispatch 2 to a fresh Claude subagent, loudly.
- **Inputs**: `codex-run.sh` missing/non-executable, codex exits non-zero, or the timed wait ceiling trips.
- **Outputs**: `dispatch 2: codex unavailable, Claude fallback` line in `## Review log`; review proceeds.
- **Behavior**: Mirrors Phase 8's codex-with-Claude-fallback rule. Never PAUSE on a codex outage; the review must complete unattended either way.

### Capability: Design-Review Execution Gate

Make "the review ran" machine-checkable and enforce it before planning.

#### Feature: Pinned dispatch summary line format

- **Description**: design-solution's per-dispatch summary line in `## Review log` gets an exact, greppable format.
- **Inputs**: Dispatch number, reviewer identity, per-severity counts.
- **Outputs**: One line per dispatch: `dispatch <n> (<claude|codex|claude-fallback>): cardinal-sin <c>, blocker <b>, non-blocker <nb>, question <q>`.
- **Behavior**: SKILL.md pins the format verbatim so the Phase 1.5 gate can match it with a single fixed pattern.

#### Feature: Empty-review-log gate in Phase 1.5

- **Description**: run-autopilot Phase 1.5 refuses to proceed to Phase 2 when the design doc's `## Review log` holds no dispatch summary line.
- **Inputs**: The design doc at `state.design_doc`.
- **Outputs**: Proceed to Phase 2, or PAUSE with `state.pause_reason = {"site": "sub_skill_fail", "detail": "design doc has empty ## Review log (review never ran)"}`.
- **Behavior**: The check runs on BOTH Phase 1.5 continue paths: after a successful `/design-solution` (exit 0) AND on the artifact-reuse skip (an existing doc from a manual or aborted run is exactly where a skipped review hides). Match: at least one line matching the pinned dispatch format inside `## Review log`. `design_mode == "skip"` bypasses the gate (no doc exists by design). The check is a deterministic grep, not a model judgment.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/
├── design-solution/
│   └── SKILL.md                          # Maps to: Cross-Model Design Review (step 4/5 rewrite, pinned summary line)
└── run-autopilot/
    ├── SKILL.md                          # Maps to: Empty-review-log gate (Phase 1.5)
    └── scripts/
        └── test_design_review_contract.py  # Maps to: both capabilities (contract test, new file)
```

### Module: design-solution skill

- **Maps to capability**: Cross-Model Design Review
- **Responsibility**: Owns the review loop: dispatch order (Claude, codex, optional verification), fallback rule, pinned summary line, 3-dispatch ceiling, exit report.
- **Exports**: The `## Review log` dispatch summary line format (consumed by the Phase 1.5 gate); the unchanged exit contract (path on stdout, non-zero on open blockers).

### Module: run-autopilot Phase 1.5

- **Maps to capability**: Design-Review Execution Gate
- **Responsibility**: Gate both continue paths on the presence of a dispatch summary line before advancing to Phase 2.
- **Exports**: The `pause_reason` detail string for the empty-log case.

### Module: contract test

- **Maps to capability**: Both
- **Responsibility**: Pin the load-bearing SKILL.md lines the same way `test_doubt_review_prompt_contract.py` does: the dispatch summary format string appears in design-solution SKILL.md; the gate instruction (both paths, exact pattern, skip-mode bypass) appears in run-autopilot SKILL.md.
- **Exports**: pytest module, runs with the existing `scripts/` suite.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **design-solution skill**: Provides the pinned dispatch summary format the gate matches on.

### Core Layer (Phase 1)

- **run-autopilot Phase 1.5**: Depends on [design-solution skill] (greps the format Phase 0 pins).

### Integration Layer (Phase 2)

- **contract test**: Depends on [design-solution skill, run-autopilot Phase 1.5] (asserts both files carry the contract lines).

## Implementation Phases

### Phase 0: Foundation

**Goal**: design-solution runs codex as the mandatory second dispatch and emits machine-checkable summary lines.

**Tasks**:

- [ ] Rewrite design-solution step 4: dispatch 1 Claude (unchanged), dispatch 2 codex via `codex-run.sh` background Bash with timed wait, always runs; dispatch 3 verification only when dispatch 2 found cardinal sins/blockers; ceiling 3 (no deps) - Acceptance: SKILL.md names the exact `codex-run.sh` invocation shape (read-only, `-f` prompt file, `-o` output file), the fallback rule, and states dispatch 2 runs even on a clean dispatch 1.
- [ ] Pin the dispatch summary line format `dispatch <n> (<claude|codex|claude-fallback>): cardinal-sin <c>, blocker <b>, non-blocker <nb>, question <q>` in step 4 and the exit report section (no deps) - Acceptance: format string appears verbatim in SKILL.md.

**Exit Criteria**: A dry read of design-solution SKILL.md yields an unambiguous three-dispatch procedure with codex mandatory and fallback defined.

### Phase 1: Core

**Goal**: Autopilot cannot advance past Phase 1.5 with an unreviewed design.

**Tasks**:

- [ ] Add the empty-review-log gate to run-autopilot Phase 1.5 on both the success path and the artifact-reuse path, with the `sub_skill_fail` pause shape and the `design_mode == "skip"` bypass (depends on: Phase 0) - Acceptance: Phase 1.5 section names the grep pattern (the pinned format), both paths, and the pause_reason detail string.

**Exit Criteria**: Phase 1.5 text contains the gate on both paths; pause path matches the existing Error Handling table shape.

### Phase 2: Integration

**Goal**: The contract cannot silently drift.

**Tasks**:

- [ ] Write `test_design_review_contract.py` asserting: design-solution SKILL.md contains the pinned format and the mandatory-codex-dispatch rule; run-autopilot SKILL.md contains the gate on both paths (depends on: Phase 1) - Acceptance: pytest passes; deleting the gate line or the format line makes it fail.

**Exit Criteria**: Full `run-autopilot/scripts/` pytest suite green.

## Test Strategy

### Critical Scenarios

- **Happy path**: design-solution completes dispatch 1 (Claude) plus dispatch 2 (codex), both summary lines land in `## Review log`, Phase 1.5 gate matches and proceeds to Phase 2. → Expected: no pause, planning starts.
- **Edge case**: Existing design doc reused on the artifact-reuse path with an empty `## Review log` (the playground 00003 shape). → Expected: PAUSE with `sub_skill_fail` and the empty-log detail; never reaches Phase 2.
- **Edge case**: dispatch 1 finds zero blockers. → Expected: dispatch 2 (codex) still runs; loop does not end at 1 dispatch.
- **Error case**: codex CLI absent or hung past the timed wait. → Expected: Claude fallback dispatch runs, `claude-fallback` summary line written, run continues unattended, no PAUSE.

## Risks

- **codex hang strands the unattended run**: Mitigated by background Bash plus timed wait (the Subagent Watchdog discipline already mandated in step 4) and by PRD 00040's stdin guard; the fallback path caps worst-case delay at the wait ceiling.
- **Gate false-positive on legacy design docs** (created before the pinned format): The gate only runs in Phase 1.5 for the current PRD; legacy docs only enter via the artifact-reuse path, where a re-run of `/design-solution` (delete the doc, let Phase 1.5 regenerate) is the documented remedy in the pause detail.
- **codex findings quality diverges from the taxonomy** (unparseable findings): The dispatch prompt pins the structured findings shape; unparseable output counts as a codex failure and triggers the Claude fallback, loudly.
- **Third dispatch inflates design-phase latency**: Dispatch 3 is conditional on dispatch 2 finding blockers; clean designs still finish in 2 dispatches.
