# Batch Report Format

File: `dev/local/autopilot/reports/{batch_id}-report.md`

Created at first PRD completion, appended after each subsequent PRD. Never deleted by autopilot.

## Template

On first creation, write the header:

```markdown
# Autopilot Batch Report {batch_id}

Started: {ISO 8601 timestamp}
```

After each PRD, append a section:

```markdown
## {prd_filename}

- Completed: {ISO 8601 timestamp}
- Cycles: {n}
- Tasks: {completed}/{total}
- Regroup: {one of the five Regroup Outcome lines documented below}

### Autonomous Decisions

| Cycle | Issue | Severity | Action | Reason |
|-------|-------|----------|--------|--------|
| 1 | Missing null check in parser | medium | auto-fix | mechanical fix, additive only |
| 2 | New dependency: zod | high | auto-fix | research-passed: MIT, active, no CVEs, 4.2M downloads |

### Escalated Decisions

| Cycle | Issue | Severity | Resolution | User Decision |
|-------|-------|----------|------------|---------------|
| 2 | API signature change | high | approved | proceed with v2 naming |

### Doubt Review Findings

| Issue | Severity | Status |
|-------|----------|--------|
| Edge case in token refresh | medium | resolved |

### Doubt Rubric Verdicts

| Rule | Verdict |
|------|---------|
| R1 | pass |
| R2 | fail |

One row per rule in `skills/run-autopilot/references/doubt-review-rubric.md`. Source: `state.doubts_rubric_verdicts`, written by Phase 8 step 5 from the doubt-review subagent output. This table is the autopilot-internal summary; PRD 00038's `review_coverage.py` parses the raw doubt-review output directly. Omit this section if `doubts_rubric_verdicts` is absent or empty for the PRD.

### Deferred to Batch End

| Issue | Severity | Reason |
|-------|----------|--------|
| Cross-PRD API consistency check | high | needs context from multiple PRDs |

### Bloat metric

- Net lines added: 432
- Acceptance criteria items: 5
- Lines per AC: 86.4
- Median across last 5 PRDs: 38.0
- Status: HIGH (2.3x median)
```

Omit empty sections (e.g. if no escalated decisions, skip that table).

## Bloat Metric

The `### Bloat metric` block is appended to each PRD's section at Phase 9 step 9
by `scripts/slop_metrics.py`. It reports diff size relative to the rolling
median across recent PRDs — informational only, no auto-trigger.

Fields:

- **Net lines added** — `insertions - deletions` from
  `git diff --shortstat <work_start_sha>..HEAD`.
- **Acceptance criteria items** — count of `- [ ]` checkbox tasks under the
  PRD's `## Implementation Phases` section.
- **Lines per AC** — `net_lines / max(1, ac_count)`.
- **Median across last 5 PRDs** — median of up to the 5 most-recent
  `Lines per AC` values found in this batch report and any older
  `*-report.md` files. `n/a` when fewer than 3 prior values exist.
- **Status** — one of:
  - `LOW` — ratio < 1.5x median
  - `NORMAL` — 1.5x ≤ ratio ≤ 2.5x
  - `HIGH` — ratio > 2.5x
  - `INSUFFICIENT_DATA` — fewer than 3 prior values; ratio not computed

When NORMAL, LOW, or HIGH, the status line includes the ratio in parentheses
(e.g. `HIGH (2.3x median)`).

The metric is a tripwire for inspection, not a gate. A HIGH status invites the
operator to read the diff with a slop-checking eye; it does not block the
batch or auto-trigger an extra deslop pass.

## Regroup Outcome

Phase 9 step 1 emits exactly **one** of the following lines per PRD as the
`- Regroup:` bullet in the per-PRD section. Use the exact strings verbatim —
do not paraphrase or change punctuation:

```
regrouped: N -> M commits
skipped: commits already well-grouped
skipped: remote guard (commits already on remote)
skipped: cherry-pick conflict, history left untouched
skipped: work_start_sha missing
skipped: not in a git working directory
```

- `regrouped: N -> M commits` — granularity assessment produced a regroup plan
  and the cherry-pick rewrite completed successfully. `N` is the original
  commit count in `work_start_sha..HEAD`; `M` is the new commit count.
- `skipped: commits already well-grouped` — granularity assessment decided
  no-op; history unchanged.
- `skipped: remote guard (commits already on remote)` — the range included a
  commit already on a remote-tracking branch; no rewrite attempted.
- `skipped: cherry-pick conflict, history left untouched` — a cherry-pick
  conflict triggered the conflict-safe abort; the backup branch restored the
  original `HEAD`.
- `skipped: work_start_sha missing` — `state.work_start_sha` was absent or
  empty (legacy state.json from before the field existed, or a session that
  crashed before Phase 3 wrote it). The presence guard at the top of Phase 9
  step 1 skipped all sub-behaviors to avoid expanding the range to "all
  reachable commits".
- `skipped: not in a git working directory` — `git rev-parse
  --is-inside-work-tree` exited non-zero in the cwd. The bare-repo dotfile
  case (e.g. `~/.buvis` work-tree at `$HOME`) is the canonical example: the
  repo exists but bare `git` commands fail without `--git-dir=<bare>
  --work-tree=<dir>` prefixes. The preflight check at the top of Phase 9
  step 1 skipped all sub-behaviors.

At batch completion, append:

```markdown
## Batch Summary

- PRDs completed: {n}
- Total cycles: {sum}
- Autonomous decisions: {sum}
- Escalated decisions: {sum}
- Deferred items: {count}
- Duration: {first PRD start} to {last PRD end}
```
