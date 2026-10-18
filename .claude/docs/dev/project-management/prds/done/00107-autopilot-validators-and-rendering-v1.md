# Autopilot Validators and Rendering Absorption

> Renumbered 00053 → 00107 on 2026-08-01 (backlog tail resequence; mapping in memory `project_backlog_renumber_2026_08`).
> Source discovery: `dev/local/discovery/00050-autopilot-cli.md` (PRD 3 of 3).
> Depends on: 00051 (state-machine core). Coexists with 00106 (ex-00052); no hard ordering
> against it beyond the shared 00051 base.

## Overview

### Problem Statement
Deterministic gating and rendering are scattered across scripts
(`check_review_file.py`, `review_coverage_hook.py`) and SKILL.md/reference prose
(`dashboard-format.md`). This PRD absorbs the review-file gate, audit render,
batch report, metrics render, and a plain status surface into the CLI, so all
deterministic gating and rendering live in one tested codebase and the
references carry judgment only.

### Target Users
Review-gated phases, batch-end notification, and anyone reading autopilot
status.

### Success Metrics
- The review-file gate is a single CLI subcommand with tests; the docs-only
  sentinel convention is preserved.
- Audit, batch report, metrics, and status rendering move from prose to code.
- Prose diet met: zero orchestration mechanics remain in run-autopilot
  SKILL.md/references, judged by the mechanic-vs-judgment test (a behavior is a
  mechanic → CLI if the same input must always produce the same output; it
  stays judgment/prose if a rubric can't fully capture the call); concrete
  before/after line and token numbers reported.

## Functional Decomposition

### Capability: Gates
The deterministic pass/fail checks the review phases depend on.

#### Feature: Review-file gate
- **Description**: Validate a review file's coverage as a CLI subcommand.
- **Inputs**: The review file, the current diff's changed files.
- **Outputs**: Pass, or a block naming the missing files/tests.
- **Behavior**: Absorbs the <120-line `check_review_file.py` gate (00016); preserves the docs-only sentinel convention (files=n/a:docs only + tests=none); feature keys match the PRD `#### Feature:` headings verbatim.

### Capability: Rendering
The deterministic render surfaces that currently live in prose or scripts.

#### Feature: Audit render
- **Description**: Render `audit.md` from state and records.
- **Inputs**: `state.json`, stall/defer records.
- **Outputs**: A rendered `audit.md`.
- **Behavior**: Pure function of on-disk state; no session prose.

#### Feature: Batch report
- **Description**: Render the batch-drain report.
- **Inputs**: Batch state, per-PRD outcomes.
- **Outputs**: A rendered batch report.
- **Behavior**: Deterministic layout from state; replaces the prose report recipe.

#### Feature: Metrics render
- **Description**: Render loop-metrics rows into a readable summary.
- **Inputs**: `loop-metrics.jsonl` (per-PRD session count, token, cost from 00013/00018).
- **Outputs**: A rendered metrics summary.
- **Behavior**: Renders existing fields; enrichment beyond 00013/00018 fields is additive, not a baseline change.

#### Feature: Status surface
- **Description**: Plain-text `autopilot status`.
- **Inputs**: Current `state.json`, batch state.
- **Outputs**: A plain-text status view (moves `dashboard-format.md` render to code).
- **Behavior**: Plain status only; a watch/dashboard mode stays out of scope for this PRD (open question in the discovery).

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/run-autopilot/cli/
├── gate.py            # Maps to: Review-file gate (absorbs check_review_file.py)
├── render_audit.py    # Maps to: Audit render
├── render_report.py   # Maps to: Batch report
├── render_metrics.py  # Maps to: Metrics render
├── status.py          # Maps to: Status surface
└── test_*.py
```

Plus subcommands wired into the `__main__` dispatch from 00051: `autopilot
gate`, `autopilot render {audit|report|metrics}`, `autopilot status`.

### Module: gate
- **Maps to capability**: Gates
- **Responsibility**: The review-file coverage gate as a single tested subcommand.
- **Exports**:
  - `check(review_file, changed_files)` - pass or block-with-reason

### Module: render
- **Maps to capability**: Rendering
- **Responsibility**: Deterministic audit / batch-report / metrics rendering from on-disk state.
- **Exports**:
  - `render_audit(state, records)` - `audit.md` text
  - `render_report(batch)` - batch report text
  - `render_metrics(metrics_rows)` - metrics summary text

### Module: status
- **Maps to capability**: Rendering (status surface)
- **Responsibility**: Plain-text status view and subcommand wiring for gate/render/status.
- **Exports**:
  - `render_status(state)` - plain-text status
  - dispatch entries for `gate | render | status`

## Dependency Graph

### Foundation Layer (Phase 0)
Depends on 00051 core (external prerequisite).

- **gate**: the review-file gate over the current diff.

### Core Layer (Phase 1)
- **render**: Depends on [00051 core]

### Integration Layer (Phase 2)
- **status**: Depends on [00051 core, render] and the prose-diet cutover.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Move the review-file gate into the CLI.

**Tasks**:
- [ ] Implement `gate.py` porting `check_review_file.py` + its tests (depends on: 00051) - Acceptance: a well-formed review file passes; a docs-only diff passes via the sentinel; a missing-files case blocks with a clear reason.

**Exit Criteria**: The review-file gate is a CLI subcommand with parity tests.

### Phase 1: Core
**Goal**: Absorb the render surfaces.

**Tasks**:
- [ ] Implement `render_audit.py`, `render_report.py`, `render_metrics.py` (depends on: Phase 0) - Acceptance: each render matches a golden fixture built from real state; metrics render reads existing 00013/00018 fields.

**Exit Criteria**: Audit, report, and metrics render from code, golden-tested.

### Phase 2: Integration
**Goal**: Ship status and complete the prose diet.

**Tasks**:
- [ ] Implement `status.py` + wire `gate`/`render`/`status` subcommands (depends on: Phase 1) - Acceptance: `autopilot status` prints a plain-text view from state.
- [ ] Strip rendering and gate mechanics from run-autopilot SKILL.md/references and report before/after line + token numbers (depends on: subcommands) - Acceptance: zero orchestration mechanics remain per the mechanic-vs-judgment test; before/after numbers recorded.

**Exit Criteria**: References carry judgment only; all deterministic gating/rendering runs through the CLI.

## Test Strategy

### Critical Scenarios
- **Happy path**: gate a well-formed review file; render audit/report/metrics → Expected: pass and golden-matching output.
- **Edge case**: a docs-only diff → Expected: the sentinel passes the gate.
- **Error case**: a review file missing required files → Expected: blocked with a clear, specific reason.

## Risks

- **Rendering parity drift**: Golden fixtures built from real state pin each render.
- **Prose diet incomplete**: The mechanic-vs-judgment test gates completeness; before/after numbers make it falsifiable.
- **Gate regression**: Port `check_review_file.py` tests wholesale, including the docs-only sentinel path.
