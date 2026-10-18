---
catchup: skip
default_model: opus
---

# Merge Review Surfaces into One Phase

## Overview

### Problem Statement

Autopilot runs three separate review surfaces (Phase 4 consensus, Phase 7 blind, Phase 8 doubt), each in its own fresh session with its own hand-off, skip logic, coverage gate call, and task-bolt-on machinery (`[BLIND]`/`[DOUBT]` tasks with their own hydration rules). The cost is structural: two extra session hand-offs per PRD (the loop's most failure-prone moments - the strand/thrash saga lived almost entirely in review-gated phases), duplicated review-input assembly, and a state machine (`build|review|blind|doubt|done`) whose blind/doubt legs exist only to grant reviewers a clean context window.

That rationale confuses the orchestrator's context with the reviewer's. Reviewers already run in isolated contexts by construction: a subagent sees only its prompt; codex is a separate process. A blind review is a *prompt discipline* (PRD-only input), not a session property. Meanwhile the evidence says the extra legs converge on trivia: recent batch reports show blind/doubt outcomes of "0 critical, 2 minors deferred", R1-R5 all-pass across PRDs, and findings like comment casing and docstring gaps - at the price of two fresh sessions, two catch-up re-reads, and two more chances to strand the loop.

This PRD keeps all three review *lenses* - consensus, blind, doubt - and runs them as parallel reviewers inside the single review phase, every cycle. Nothing is skipped; the lenses actually run MORE often (every cycle instead of once post-convergence), and their findings enter the normal rework loop instead of bespoke bolt-on paths.

### Target Users

Every autopilot PRD run; the user's wall-clock and quota.

### Success Metrics

- Phase enum shrinks to `build | review | done` (plus `paused`); Phases 7 and 8 and their hand-offs, skip rules, and `[BLIND]`/`[DOUBT]` task machinery are deleted from `run-autopilot/SKILL.md`.
- One review cycle dispatches four lenses in one parallel batch: Alice (Claude, implementation-aware), Blake (Claude subagent, PRD-only blind lens), Bob (codex, doubt rubric R1-R5 + de-slop lens), Carl (Gemini, optional, UI). Diana is unchanged by this PRD (PRD 00019 owns her replacement).
- Sessions per PRD drop from ≥4 to ≤2 in `loop-metrics.jsonl` (build; review through done).
- `~/.claude/CLAUDE.md` workflow bullets are rewritten to mandate the three lenses per cycle instead of three phases - the mandate's intent (never skip blind/doubt scrutiny) survives verbatim in lens form.
- `state.doubts_rubric_verdicts` and the batch-report rubric table keep rendering (sourced from Bob's per-cycle output, final cycle wins).
- Full run-autopilot pytest suite adapted and green.

## Functional Decomposition

### Capability: Fold blind and doubt into the review roster

#### Feature: Add the blind lens reviewer

- **Description**: A PRD-only reviewer joins every review cycle.
- **Inputs**: `~/.claude/skills/review-work-completion/SKILL.md` (roster, step that launches reviewers in a single message), `references/agent-invocation.md`; the prompt content of `~/.claude/skills/review-blindly/SKILL.md`.
- **Outputs**: A new roster entry **Blake** → native Claude Task subagent whose prompt contains ONLY the PRD content plus the blind-review instructions (ported from review-blindly into `references/blind-lens-prompt.md`); no diff, no file list, no review history, no design doc (preserving the existing "blind stays PRD-only" rule). Blake's findings enter consolidation like any reviewer's.
- **Behavior**: `review-blindly` remains as a standalone skill for manual use; autopilot no longer invokes it. Blake launches in the same single message as Alice/Bob/Carl (Task call alongside the background-Bash CLIs, per the existing MUST).

#### Feature: Give Bob the doubt rubric and de-slop lens

- **Description**: The codex reviewer carries Phase 8's rubric duties every cycle.
- **Inputs**: `review-work-completion` reviewer prompt assembly for Bob; `run-autopilot/prompts/doubt-review.md`; `references/doubt-review-rubric.md`.
- **Outputs**: Bob's prompt gains the doubt rubric (R1-R5, one `R{n}: pass|fail` line each) and the de-slop lens (over-engineering, dead code, single-caller abstractions) from the Phase 8 prompt. Consolidation parses Bob's `R{n}:` lines into `state.doubts_rubric_verdicts` (replace per cycle; final cycle's verdicts are the durable ones).
- **Behavior**: When codex is unavailable (exit 3/4 from `codex_review_run.py` semantics), the existing Claude-fallback rule applies: a Claude subagent runs the same doubt+de-slop prompt so the lens never silently drops. `review-with-doubt` remains for manual use.

### Capability: Collapse the phase machine

#### Feature: Delete Phases 7 and 8 from run-autopilot

- **Description**: The review-rework loop (Phases 4-6) becomes the only review structure; convergence hands off to Phase 9 directly.
- **Inputs**: `~/.claude/skills/run-autopilot/SKILL.md` Phases 7, 8, their hand-off sub-sections, the Phase 4/5 skip rules that reference `blind`/`doubt`, the Invariant paragraph (five gates), Phase 9, `references/state-schema.md`, `scripts/resume_target.py` + `scripts/test_autopilot_resume.py`, `scripts/review_coverage_hook.py` phase list, lifecycle tests.
- **Outputs**: Phase 5's "No issues found" outcome hands off to Phase 9 (`phase: "done"`, `next_phase: "done"`) instead of `blind`. All `[BLIND]`/`[DOUBT]` task rules, the doubt-prompt assembly step, the Eve dual-reviewer sequencing block, and both hand-off sub-sections are removed (Eve's `doubt_reviewer: fable` option is re-pointed: when set, Eve joins the review batch as a fifth lens with the same prompt rules). `phases_completed` values shrink to `review`. `resume_target.py` maps the new enum; state-schema documents it; `review_coverage_hook.gate_blocks` phase awareness updated to `review`/`done`.
- **Behavior**: Doubt-review input scoping (`work_start_sha..HEAD` diff) moves into the shared review-input assembly so Bob sees the same range Phase 8 gave him. The rework cap, decision gate classification, and cap-pause behavior are untouched - they now govern the only loop.

#### Feature: Rewrite the standing review mandate

- **Description**: The user-level rule that mandates phases 4/7/8 must mandate the lenses instead, or every future session re-derives the old structure.
- **Inputs**: `~/.claude/CLAUDE.md` Workflow bullets 3-4 ("Never skip review phases..." and "Always run review phases in a fresh session...").
- **Outputs**: Replaced by: "Never skip or thin the review phase: every review cycle runs all lenses - consensus (Alice), blind/PRD-only (Blake), doubt+de-slop with rubric R1-R5 (Bob) - regardless of how small the PRD looks. Reviewers get isolated contexts by construction (subagent prompts, external CLIs); the review phase itself runs in a fresh session after the build hand-off."
- **Behavior**: The build→review fresh-session hand-off stays (one hand-off, not three). This edit is the PRD's deliberate policy change and is called out in the batch report's autonomous-decision log.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/run-autopilot/SKILL.md                         # Maps to: Collapse the phase machine
~/.claude/skills/run-autopilot/references/state-schema.md       # Maps to: enum shrink
~/.claude/skills/run-autopilot/scripts/{resume_target.py,review_coverage_hook.py,test_*}  # Maps to: enum shrink
~/.claude/skills/review-work-completion/SKILL.md                # Maps to: roster (Blake, Bob lens)
~/.claude/skills/review-work-completion/references/blind-lens-prompt.md  # Maps to: Blake prompt (new)
~/.claude/CLAUDE.md                                             # Maps to: mandate rewrite
```

### Module: review-work-completion

- **Maps to capability**: Fold blind and doubt into the review roster
- **Responsibility**: Four-lens parallel dispatch, consolidation incl. R1-R5 parse
- **Exports**: roster contract (Alice, Blake, Bob+rubric, Carl, optional Eve)

### Module: run-autopilot

- **Maps to capability**: Collapse the phase machine
- **Responsibility**: Three-gate state machine; convergence → done
- **Exports**: `build|review|done|paused` enum

### Module: CLAUDE.md

- **Maps to capability**: Rewrite the standing review mandate
- **Responsibility**: Lens mandate replaces phase mandate
- **Exports**: workflow bullets

## Dependency Graph

### Foundation Layer (Phase 0)

- **Blake lens**: independent
- **Bob rubric lens**: independent

### Core Layer (Phase 1)

- **phase-machine collapse**: depends on [Blake lens, Bob rubric lens] (lenses must exist before the phases that carried them die)

### Integration Layer (Phase 2)

- **mandate rewrite**: depends on [phase-machine collapse]
- **verification**: depends on all

## Implementation Phases

Premise rule: PRD 00014 (headless loop) runs first by sequence; re-verify before editing whether `autopilot_stop_hook.py` still exists - if it does (00014 stalled), extend this PRD's enum edits to its decision table and tests; if deleted, skip that anchor. Re-verify Phase 7/8 sections still exist as described (`rg -n "Phase 7: Blind Review|Phase 8: Doubt Review" skills/run-autopilot/SKILL.md`).

### Phase 0: Lenses

**Tasks**:

- [ ] Add Blake (blind lens) to the roster (no deps) - Acceptance: roster lists Blake with PRD-only prompt sourced from `references/blind-lens-prompt.md`; single-message launch rule covers him; review-blindly SKILL untouched
- [ ] Add rubric + de-slop to Bob's prompt (no deps) - Acceptance: Bob's prompt assembly includes R1-R5 and de-slop instructions; consolidation step parses `R{n}:` lines into `state.doubts_rubric_verdicts`; Claude-fallback rule stated

**Exit Criteria**: One review cycle produces four lens outputs and rubric verdicts.

### Phase 1: Collapse

**Tasks**:

- [ ] Delete Phases 7/8 and shrink the enum (depends on: Phase 0) - Acceptance: SKILL.md has no Phase 7/8 sections, no `[BLIND]`/`[DOUBT]` rules, no blind/doubt hand-offs; Phase 5 convergence → done; `rg -n '"blind"|"doubt"' skills/run-autopilot/SKILL.md` returns only the doubt_reviewer/Eve lens option and rubric-verdict prose
- [ ] Adapt scripts and tests to the new enum (depends on: collapse) - Acceptance: resume_target.py, review_coverage_hook.py, state-schema.md updated; full pytest suite under `skills/run-autopilot/scripts/` green, count pasted

**Exit Criteria**: State machine is `build|review|done|paused`; suite green.

### Phase 2: Mandate and proof

**Tasks**:

- [ ] Rewrite CLAUDE.md review mandate (depends on: Phase 1) - Acceptance: bullets 3-4 replaced by the lens mandate; no reference to Phases 7/8 anywhere in CLAUDE.md
- [ ] End-to-end run (depends on: all) - Acceptance: one scratch PRD drains with ≤2 sessions in `loop-metrics.jsonl`; review file lists all four lenses; batch report renders the rubric table; evidence pasted

**Exit Criteria**: Success metrics all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: cycle 1 converges → Expected: one review session, four lens outputs, rubric verdicts recorded, straight to done
- **Edge case**: blind lens finds a Critical in cycle 1 → Expected: it becomes a normal `[C1]` rework task (not a `[BLIND]` bolt-on), fixed in cycle 2, re-checked by all lenses
- **Edge case**: codex unavailable → Expected: Claude fallback runs the doubt+de-slop prompt; rubric lines still parsed; review never silently thinner
- **Edge case**: `doubt_reviewer: fable` frontmatter → Expected: Eve joins the batch as a fifth lens; single-reviewer path byte-unchanged otherwise
- **Error case**: resumed old-state run with `phase: "blind"` in state.json → Expected: resume maps legacy `blind`/`doubt` values to `review` (documented in state-schema) instead of crashing

## Risks

- **Policy change**: this deliberately amends the user's standing 4/7/8 mandate; the lens mandate preserves its intent (blind + doubt scrutiny on every PRD, isolated reviewer contexts). Called out in the batch report; the user can veto by dropping this PRD.
- **Lens dilution**: blind/doubt now run every cycle instead of post-convergence; that is strictly more scrutiny, and consolidation consensus already filters single-reviewer noise.
- **Legacy state mid-flight**: a batch paused at `blind`/`doubt` when this lands resumes via the legacy-value mapping above.
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; no CHANGELOG entries.
