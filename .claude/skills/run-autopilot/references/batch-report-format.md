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

### Deferred to Batch End

| Issue | Severity | Reason |
|-------|----------|--------|
| Cross-PRD API consistency check | high | needs context from multiple PRDs |
```

Omit empty sections (e.g. if no escalated decisions, skip that table).

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
