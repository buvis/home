---
catchup: skip
design: skip
---

# Simplify the Review Coverage Gate

## Overview

### Problem Statement

`review_coverage.py` is 774 lines with a 37KB test file, seven failure kinds, per-surface rubric defaults, an aggregate-merge engine, and a diff-to-file-mapping check. Its operational record is inverted: the memorialized incidents are false blocks, not caught defects - docs-only diffs need magic sentinel conventions (`files=n/a:docs only` + `tests=none`), blind/doubt remediation commits trigger `MISSING_FILES` and require hand-patching `n/a` rows into the prior surface's review file, feature keys must match PRD `#### Feature` headings verbatim including backticks, the `EMPTY_TESTS` check depends on delimiter-extraction order, and a `DIFF_ERROR` in the bare-repo home once deleted a handoff signal and reported a false "Backlog drained." Each false block either halts an unattended run or trains the model to appease the gate's format instead of reviewing the code.

After PRD 00015 there is one review surface, so the per-surface machinery (surface rubric defaults, aggregate merging across blind/doubt files, the single-coverage-block invariant) is dead weight by construction. What the gate actually needs to guarantee is small: every launched reviewer produced real output, the review reached a verdict, and tests ran during the cycle.

### Target Users

Unattended autopilot runs (no human present to un-wedge a false block); anyone maintaining the review pipeline.

### Success Metrics

- The gate is a single script under 120 lines checking exactly three things: (1) the cycle's review file exists and contains a non-empty findings-or-converged section per launched reviewer, (2) a parseable verdict line (converged / findings count), (3) a test-summary line recorded by the review skill (pass/fail/skip counts, or the literal `tests: none (docs-only)` when the diff touches no code).
- `MISSING_FILES`, `UNMAPPED_FEATURE`, `EMPTY_TESTS`, `MALFORMED_BLOCK`, surface rubric defaults, aggregate merging, and gate-side test execution are gone; the gate runs no `git diff` and no test suite.
- The docs-only sentinel convention and the remediation `n/a`-row dance are impossible by construction (nothing maps files or features anymore).
- Reviewer prompts and consolidation are updated to emit the three required elements directly.
- Old gate + tests deleted; new focused test file green.

## Functional Decomposition

### Capability: Replace the gate with an artifact-shape check

#### Feature: Write the minimal gate script

- **Description**: One script validates review-file shape; nothing else.
- **Inputs**: Current `~/.claude/skills/review-work-completion/scripts/review_coverage.py` (CLI surface only - callers pass `--reviewer-block`/`--write-aggregate` today); the review file format in `references/review-coverage-format.md`.
- **Outputs**: A new `scripts/check_review_file.py` (<120 lines): args `--review-file <path>` and `--reviewers <comma-list of launched reviewer names>`; exits 0 when each named reviewer has a non-empty section, a verdict line matches `^Verdict: (converged|(\d+) findings?)`, and a tests line matches `^Tests: (\d+ passed.*|none \(docs-only\))`; exits 1 with a one-line gap description otherwise. No git, no subprocesses, no PRD parsing.
- **Behavior**: Fails open on unreadable-file-system errors with a loud stderr note (matching the old gate's DIFF_ERROR philosophy: an infrastructure error must not masquerade as a coverage gap).

#### Feature: Make the review skill emit the checked shape

- **Description**: Consolidation writes the three elements the gate reads.
- **Inputs**: `~/.claude/skills/review-work-completion/SKILL.md` consolidation step; `references/review-coverage-format.md`.
- **Outputs**: The consolidated review file gains `Verdict:` and `Tests:` lines (the review cycle already runs the suite per the work skill's verification discipline; consolidation records the counts - it does not re-run tests). The `---review-coverage---` block format, its `files`/`features` dimensions, and the aggregate-merge instructions are removed from the format doc; per-reviewer sections keep FIX/VERIFY/KNOWN and Bob's `R{n}:` lines (PRD 00015).
- **Behavior**: Docs-only cycles write `Tests: none (docs-only)` - a first-class value, not a sentinel to memorize.

#### Feature: Rewire callers and retire the old gate

- **Description**: Every call site moves to the new check; the old engine and its conventions die.
- **Inputs**: `rg -ln "review_coverage" ~/.claude/skills ~/.claude/hooks ~/.claude/settings.json` at execution time (expected: run-autopilot SKILL.md gate invocation, review_coverage_hook.py, review-work-completion docs/scripts, tests).
- **Outputs**: run-autopilot's gate invocation calls `check_review_file.py`; `review_coverage_hook.py`'s `gate_blocks` delegates to the same check (PRD 00014 deliberately KEEPS this hook registered as the in-session quality gate - it retires only the orchestration hooks; re-verify registration at execution). `review_coverage.py`, `test_review_coverage_hook.py`'s gate-engine cases, and the coverage-block prose in run-autopilot (single-coverage-block invariant, sentinel examples) are deleted. New `test_check_review_file.py` covers the scenarios below.
- **Behavior**: No caller anywhere passes `--diff-range`, `--prd`, `--run-tests`, or `--write-aggregate`.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/review-work-completion/scripts/check_review_file.py      # new gate
~/.claude/skills/review-work-completion/scripts/test_check_review_file.py # new tests
~/.claude/skills/review-work-completion/scripts/review_coverage.py        # deleted
~/.claude/skills/review-work-completion/references/review-coverage-format.md  # slimmed
~/.claude/skills/review-work-completion/SKILL.md                          # consolidation emits Verdict/Tests
~/.claude/skills/run-autopilot/SKILL.md                                   # gate call + prose slim
~/.claude/skills/run-autopilot/scripts/review_coverage_hook.py            # delegate or delete
```

### Module: check_review_file

- **Maps to capability**: Replace the gate with an artifact-shape check
- **Responsibility**: Shape validation only
- **Exports**: exit code + one-line gap description

### Module: review-work-completion

- **Maps to capability**: Make the review skill emit the checked shape
- **Responsibility**: Verdict/Tests lines in consolidation
- **Exports**: review-file format contract

## Dependency Graph

### Foundation Layer (Phase 0)

- **new gate script + tests**: independent

### Core Layer (Phase 1)

- **format emission**: depends on [new gate script] (emits what it checks)

### Integration Layer (Phase 2)

- **caller rewire + retirement**: depends on all

## Implementation Phases

Premise rule: PRDs 00014/00015 run first by sequence; at execution re-verify which callers still exist (`rg -ln "review_coverage"`) and whether `review_coverage_hook.py` is still registered in settings.json - adapt the rewire task to what is actually present; a vanished caller is a skip-and-note, not an error.

### Phase 0: New gate

**Tasks**:

- [ ] Write check_review_file.py + tests (no deps) - Acceptance: <120 lines; the four Test Strategy scenarios covered in `test_check_review_file.py`; pytest green

### Phase 1: Emission

**Tasks**:

- [ ] Consolidation emits Verdict/Tests; slim the format doc (depends on: Phase 0) - Acceptance: format doc has no `files`/`features` dimensions, no aggregate-merge section; consolidation step records test counts from the cycle's suite run

### Phase 2: Rewire

**Tasks**:

- [ ] Rewire callers, delete the old engine (depends on: Phase 1) - Acceptance: `rg -n "review_coverage.py"` under `~/.claude` returns nothing; run-autopilot gate call uses the new script; single-coverage-block invariant prose gone; full pytest suites in both skills' `scripts/` green, counts pasted

**Exit Criteria**: Success metrics all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: review file with all reviewers' sections + `Verdict: converged` + `Tests: 34 passed, 0 failed` → Expected: exit 0
- **Edge case**: docs-only cycle, `Tests: none (docs-only)` → Expected: exit 0, no sentinel gymnastics
- **Edge case**: launched reviewer (named in `--reviewers`) has an empty section → Expected: exit 1 naming the reviewer
- **Error case**: review file missing entirely → Expected: exit 1 `missing review file <path>`; unreadable due to I/O error → exit 0 with loud stderr (fail open on infrastructure)

## Risks

- **Lost checks**: file-level diff mapping and gate-run tests go away. Accepted deliberately: four-lens consensus plus the work skill's own verification discipline cover reviewed-the-right-thing; the mapping check's documented record is false blocks (2026-06-11 DIFF_ERROR false-drain, MISSING_FILES remediation dance, docs-only sentinels), and a gate that trains format-appeasement reduces review quality rather than protecting it.
- **Mid-flight review files** in the old format: the new gate only ever runs on files the post-change skill writes; a resumed old-format cycle re-consolidates before gating (note added to the consolidation step).
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; no CHANGELOG entries.
