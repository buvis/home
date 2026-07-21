# Batch Report Format

File: `dev/local/autopilot/reports/{batch_id}-report.md`

Created at first PRD completion, appended after each subsequent PRD. Never deleted by autopilot.

**Filename invariant:** see `references/phase-done.md` Phase 9 step 7 (pinned in core SKILL.md § "Phase 9 invariants") — `{batch_id}` is always `state.batch.id` at append time; that step verifies the target filename's id matches `state.batch.id` and never globs `reports/*.md`.

## Template

On first creation, write the header:

```markdown
# Autopilot Batch Report {batch_id}

Started: {ISO 8601 timestamp}
```

After each PRD, append a section. A STALLED PRD (PRD 00017 loop-mode stall
procedure) appends this short form instead of the full section:

```markdown
## {prd_filename} — STALLED ({site})

- Stalled: {ISO 8601 timestamp}
- Detail: {stall detail}
- Resume: move back to dev/local/prds/wip/ and re-run
```

Loop-mode `assumed-ambiguity` records render inside their PRD's section under
an `### Assumptions Made` heading (one row per assumption: question →
assumption taken); omit the heading when there are none. The batch-end ntfy
message carries the counts: `{n} done, {m} stalled, {k} deferred`.

Completed-PRD section:

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

One row per rule in `skills/run-autopilot/references/doubt-review-rubric.md`. Source: `state.doubts_rubric_verdicts`, written by the review phase's consolidation from the doubt lens's `R{n}:` lines (replaced each cycle; the final cycle's verdicts render here). Omit this section if `doubts_rubric_verdicts` is absent or empty for the PRD.

**Source-tagged rendering (PRD 00038).** When `state.doubts_rubric_verdicts` entries carry a `source` field (a dual-reviewer `doubt_reviewer: fable` run — one entry per rule per reviewer), combine both reviewers into one row per rule, tagging each verdict with its source:

| Rule | Verdict |
|------|---------|
| R1 | pass (codex) / pass (fable) |
| R3 | pass (codex) / fail (fable) |

A per-reviewer `fail` still surfaces (as shown for R3). When no entry carries `source` (single-reviewer or legacy state), render UNCHANGED — one verdict per rule, no source suffix (`| R1 | pass |`).

### Loop Metrics

| Launch phase | Sessions | Wall secs | Model | Cost USD |
|--------------|----------|-----------|-------|----------|
| build | 1 | 412 | claude-fable-5[1m] | 13.90 |
| review | 2 | 337 | claude-fable-5[1m] | 13.26 |
| done | 1 | 120 | claude-sonnet-5 | 0.84 |
| **Total** | 4 | 869 | | 28.00 |

Source: `dev/local/autopilot/loop-metrics.jsonl` lines where `prd` matches the PRD and `batch` matches `state.batch.id` (PRD 00013). One row per distinct `phase_launched` value, plus a **Total** row (session count and summed `wall_secs`/`cost_usd`). The `Model` and `Cost USD` columns (PRD 00018) render from the lines' `model` and `cost_usd` fields; when a line lacks `cost_usd` leave that cell blank (the wrapper omits the key when the session output carried no usage payload — never fake zeros). Legacy lines without `model` render a blank Model cell. When the metrics file is missing or has no matching lines (a manual run outside the loop), render `no loop metrics (manual run)` instead of the table — never fail the report.

### Implementor Mix

| Implementor | Attempts |
|-------------|----------|
| claude | 4 |
| qwen | 2 |
| gemini | 1 |
| unknown | 1 |

Qwen preflight outcomes: healthy 2, completion_failed 1
Excluded from qwen: files 2, contract 1, unknown 1
capability breaker: not tripped

Source: `state.tasks[]` (PRD 00019). **Attempts row(s):** count `attempts[].implementor` values across all tasks (`claude`/`qwen`/`gemini`); an attempt row without the field (pre-PRD-00031 legacy) counts as `unknown`; omit zero-count rows. **Preflight line:** count non-null `attempts[].preflight_outcome` values per value; omit the line when there are none. **Exclusion line:** for every task whose `qwen_eligible` is `false` or absent, bucket by `qwen_excluded_reason` (`ui`/`tier`/`files`/`contract`); a missing reason (legacy plan) counts as `unknown`; omit the line when no tasks were excluded. Additionally bucket, as `memory_pressure` and `memory_probe_failed`, every task with **at least one** attempt carrying that `qwen_excluded_reason` (PRD 00075) — **deduplicated by task id**, so every bucket counts tasks, not attempts (a task the memory gate hit on two separate attempts still contributes 1, not 2). **Semantic widening:** these two buckets do NOT partition the plan-time-ineligible set the other four buckets draw from — a memory-pressure task has `qwen_eligible == true` and was never plan-time-ineligible; it was routed off qwen at dispatch time, not excluded at plan time. Read the line as two populations sharing one table, not one partition. Absent fields never fail the render — when `state.tasks[]` itself is missing or empty, render `no implementor data` instead of the table. **Capability breaker line (PRD 00065):** render `capability breaker: not tripped` when the top-level `qwen_breaker` field is absent or `tripped:false`; otherwise `capability breaker: tripped after <qwen_breaker.after_task> (2 consecutive gate failures: <qwen_breaker.failed_tasks[0]>, <qwen_breaker.failed_tasks[1]>); N tasks rerouted`, where `N` = count of `attempts[].breaker_skipped == true` across this PRD's `state.tasks[]`. The breaker is batch-scoped, so a later PRD's section may name an `after_task` from an earlier PRD — render it as-is. Absent `qwen_breaker` always renders `not tripped` (legacy batches safe).

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
