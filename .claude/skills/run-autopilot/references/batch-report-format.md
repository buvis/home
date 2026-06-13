# Batch Report Format

File: `dev/local/autopilot/reports/{batch_id}-report.md`

Created at first PRD completion, appended after each subsequent PRD. Never deleted by autopilot.

**Filename invariant:** see SKILL.md Phase 9 step 7 — `{batch_id}` is always `state.batch.id` at append time; that step verifies the target filename's id matches `state.batch.id` and never globs `reports/*.md`.

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
```

Omit empty sections (e.g. if no escalated decisions, skip that table).

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
