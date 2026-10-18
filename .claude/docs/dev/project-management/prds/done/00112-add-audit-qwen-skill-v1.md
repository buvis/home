---
catchup: skip
---

# Add audit-qwen Report Card Skill

> Renumbered 00059 → 00112 on 2026-08-01 (backlog tail resequence; mapping in memory `project_backlog_renumber_2026_08`).
> Source: `dev/local/qwen-leverage-assessment-2026-07-12.md` (gap G3).

## Overview

### Problem Statement

PRD 00019 made qwen utilization measurable: batch reports carry an
`### Implementor Mix` section, plan-tasks stamps `qwen_excluded_reason` on
every ineligible task, and review files record Quinn's advisory-vs-concurred
findings. Nothing reads any of it back. The eligibility fences (non-UI,
tier, file count, contract edits) and Quinn's advisory weight can therefore
never move on evidence; tuning stays a feeling. The telemetry is write-only.

### Target Users

The solo operator deciding whether to widen, narrow, or hold the qwen fences
and Quinn's weight; future PRDs that need utilization numbers in their
problem statements.

### Success Metrics

- One command produces per-batch and aggregate numbers: qwen dispatch rate,
  preflight outcome histogram, test-gate pass rate, Quinn concurrence
  precision, exclusion-reason histogram.
- Every number comes from a deterministic Python parse; the model only
  narrates (no LLM-derived figures).
- With fewer than 10 qwen attempts on record the verdict is HOLD
  (insufficient data), stated plainly - data starvation is an expected early
  answer, not a failure.

## Functional Decomposition

### Capability: Telemetry sweep

Find and parse every qwen telemetry artifact across repos.

#### Feature: Repo and artifact discovery

- **Description**: Enumerate repos and collect their telemetry files.
- **Inputs**: `gita ls` output (the registered-repo set, same source
  brief-portfolio uses) plus `~/.claude`; each repo's `dev/local/` (resolve
  symlinks).
- **Outputs**: Per repo: batch reports
  (`dev/local/autopilot/reports/*-report.md`), archived state snapshots
  (`dev/local/autopilot/reports/*state*archived*.json`), live
  `dev/local/autopilot/state.json` when present, review files
  (`dev/local/reviews/*-review-*.md`).
- **Behavior**: Missing dirs or a repo without autopilot artifacts skip
  silently into a per-repo "no data" row; unreadable files are listed under
  an UNPARSED heading, never dropped without trace.

#### Feature: Deterministic parser

- **Description**: Extract counts from the three artifact kinds.
- **Inputs**: The discovered files.
- **Outputs**: Per batch: attempts by implementor, qwen preflight outcomes,
  exclusion-reason counts, breaker trips (tolerated if the field exists,
  absent counts as none). Per state snapshot: `tasks[].attempts[]` chains
  (`implementor`, `preflight_outcome`, `outcome`, `review_cycle`). Per
  review file: `reviewers:` frontmatter, row count under
  `### Advisory (local model, unconfirmed)`, consolidated-table rows whose
  finder set includes quinn.
- **Behavior**: stdlib-only Python; regexes pinned to the formats defined in
  `run-autopilot/references/batch-report-format.md`,
  `review-work-completion/references/output-formats.md` (Advisory section),
  and `review-work-completion/references/review-coverage-format.md`
  (`reviewers:` frontmatter). Premise: re-read
  the format references at implementation time and pin regexes to the text
  as it exists then (formats may have drifted since 2026-07-12); the parser
  prints a per-file parse status so format drift shows up as UNPARSED, not
  as silent zeros.

### Capability: Report card

Turn counts into rates and a bounded recommendation.

#### Feature: Rates

- **Description**: The utilization numbers.
- **Inputs**: Parser output.
- **Outputs**: qwen dispatch rate (qwen attempts / qwen-eligible tasks
  observed), preflight outcome histogram, gate pass rate (a qwen attempt
  counts as failed when the same task carries a later claude attempt within
  the same non-rework pass, per the one-shot carve-out), Quinn precision
  (concurred / (concurred + advisory-only)), exclusion histogram by reason.
- **Behavior**: Aggregate plus per-batch; batches predating the telemetry
  render as `legacy (no mix data)`.

#### Feature: Recommendation

- **Description**: A deterministic widen/narrow/hold verdict.
- **Inputs**: The rates.
- **Outputs**: One verdict line plus supporting rows.
- **Behavior**: Fixed thresholds, stated in the output: fewer than 10 qwen
  attempts → HOLD (insufficient data); pass rate at or above 0.8 across at
  least 10 attempts → WIDEN, listing fence candidates ranked by exclusion
  histogram (the fence excluding the most tasks first); pass rate below 0.5
  across at least 6 attempts → NARROW, pointing at the engine/eval question
  first; anything else → HOLD. Quinn precision is reported but drives no
  automatic verdict (his weight change stays a human call).

### Capability: Skill wrapper

Expose the script as a skill in the audit family.

#### Feature: audit-qwen SKILL.md

- **Description**: Trigger-led skill that runs the script and narrates.
- **Inputs**: `scripts/audit_qwen.py` output.
- **Outputs**: `~/.claude/skills/audit-qwen/SKILL.md` (triggers: "audit
  qwen", "qwen report card", "qwen utilization").
- **Behavior**: The model runs the script, shows its numbers verbatim, and
  may add prose interpretation clearly separated from the computed section.
  It never computes or adjusts figures itself (deterministic work stays in
  code).

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/audit-qwen/
├── SKILL.md                    # Maps to: Skill wrapper
└── scripts/
    ├── audit_qwen.py           # Maps to: Telemetry sweep + Report card
    ├── test_audit_qwen.py      # Maps to: parser/rate tests (fixtures)
    └── fixtures/               # Synthetic report/state/review samples
```

### Module: audit_qwen script

- **Maps to capability**: Telemetry sweep, Report card
- **Responsibility**: Discover artifacts, parse deterministically, compute
  rates, print the markdown report card.
- **Exports**: `audit_qwen.py` CLI (`--output FILE` optional, default
  stdout; `--repo PATH` repeatable to override discovery).

### Module: audit-qwen skill

- **Maps to capability**: Skill wrapper
- **Responsibility**: Trigger routing and narration rules.
- **Exports**: SKILL.md.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **audit_qwen script (parser + fixtures)**: file discovery and parsing.

### Core Layer (Phase 1)

- **audit_qwen script (rates + recommendation)**: Depends on [parser].

### Integration Layer (Phase 2)

- **audit-qwen skill**: Depends on [script] (narrates its output).

## Implementation Phases

### Phase 0: Foundation

**Goal**: Artifacts parse deterministically with visible failure modes.

**Tasks**:

- [ ] Re-read `batch-report-format.md` and `output-formats.md`, pin parse
  regexes, and build synthetic fixtures for all three artifact kinds
  (no deps) - Acceptance: fixtures include one legacy report without an
  Implementor Mix section and one malformed file; premise re-check of both
  format references recorded.
- [ ] Implement discovery + parser in `audit_qwen.py` with per-file parse
  status (no deps) - Acceptance: `test_audit_qwen.py` passes: correct counts
  on fixtures, legacy file → `legacy` row, malformed file → UNPARSED list,
  missing dirs → "no data" row without a crash.

**Exit Criteria**: Parser tests green on all fixtures.

### Phase 1: Core

**Goal**: Numbers become rates and a verdict.

**Tasks**:

- [ ] Implement rates and the threshold recommendation (depends on:
  Phase 0) - Acceptance: tests cover HOLD under 10 attempts, WIDEN at 0.8+
  over 10+ with exclusion ranking, NARROW under 0.5 over 6+, gate-failure
  attribution from an attempts-chain fixture (qwen attempt then claude
  attempt, same task, non-rework).

**Exit Criteria**: Rate and verdict tests green.

### Phase 2: Integration

**Goal**: Usable as `/audit-qwen`.

**Tasks**:

- [ ] Write SKILL.md and run it once against the real tree (depends on:
  Phase 1) - Acceptance: `validate_skill.py` 0 errors; a live run completes
  and today's expected verdict is HOLD (insufficient data) unless real
  batches have accumulated by execution time.

**Exit Criteria**: One command yields the report card; all tests green.

## Test Strategy

### Critical Scenarios

- **Happy path**: fixtures with 12 qwen attempts, 10 gate passes → WIDEN
  with fences ranked by exclusion counts. Expected: verdict line + ranking.
- **Edge case**: zero post-00019 artifacts anywhere → every repo shows "no
  data", verdict HOLD. Expected: exit 0, honest starvation message.
- **Error case**: a report with a renamed Implementor Mix heading →
  UNPARSED listing names the file. Expected: no silent zero.

## Risks

- **Format drift**: report or review formats change and counts quietly
  shrink. Mitigation: per-file parse status plus UNPARSED listing makes
  drift loud; regexes live in one constants block for cheap re-pinning.
- **Data starvation**: early runs say HOLD for weeks. Mitigation: by
  design; the skill states the attempt count needed before any verdict
  changes.

## Implementation deviations (2026-08-14, recorded at build time)

- **Quinn precision dropped, not computed.** PRD 00094 (2026-08-09) retired
  Quinn, deleted the `### Advisory (local model, unconfirmed)` bucket from
  `output-formats.md`, and the historical review files carrying either were
  GC'd (2 files left in `dev/local/reviews/`). The metric can neither be
  computed for future cycles nor reconstructed for past ones. The card states
  this instead of printing a silent zero; the verdict was never driven by it.
- **Review files are not parsed at all.** All three review-file inputs this
  PRD names (`reviewers:` frontmatter, Advisory row count, quinn finder rows)
  existed only to feed Quinn precision. With the metric dead, parsing them is
  dead weight.
- **Gate-failure attribution uses PRD 00065's signals** (`qwen_gate_failed`,
  `outcome: escalated`) instead of this PRD's "later claude attempt within
  the same non-rework pass" heuristic. The heuristic predates 00065 and
  cannot work on pre-00065 chains anyway (one entry per task; a gate-failure
  fallback rewrote `implementor` to claude, so the qwen attempt is invisible).
  The card discloses that pre-00065 chains can only ever read as passes, and
  a WIDEN with zero recorded failures carries an unfalsifiability caveat.
- **Archived state snapshots**: the `*state*archived*.json` glob is live but
  the wrapper writes no such files today (verified: no archiving code in
  `development.plugin.bash`); `batch-report-format.md`'s claim describes
  intent, not behavior. The card notes it.
- **Expected-HOLD did not hold**: 23 qwen attempts were already on record
  (10 state chains, 13 in ddb's 202607161128 report), so the live run took
  the PRD's own "unless real batches have accumulated" branch and returned
  WIDEN (rate 1.00 across 10 classifiable, caveated as above).
