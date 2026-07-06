# Output Formats

## Contents

- [Agent Output Format](#agent-output-format-single-source-of-truth)
- [Per-Rule Verdict Format](#per-rule-verdict-format)
- [Consolidation Rules](#consolidation-rules)
- [Consolidated Findings Table](#consolidated-findings-table)
- [Issue Documentation Format](#issue-documentation-format)
- [Task Description Format](#task-description-format)
- [Review Summary Format](#review-summary-format)
- [Zero Issues Handling](#zero-issues-handling)
- [Review File Format](#review-file-format)

## Agent Output Format (Single Source of Truth)

Each agent outputs issues in this exact format:

```
[{AGENT_NAME}] {emoji} {description} | File: {path or "N/A"} | Task: {id or "general"}
```

**Severity emojis:** 🔴 Critical, 🟠 High, 🟡 Medium, ⚪ Low

**Rules:**
- One issue per line
- Use "N/A" for file if issue is architectural/cross-cutting
- Use "general" for task if issue spans multiple tasks or is a PRD gap
- If zero issues found: `[{AGENT_NAME}] ✅ No issues found`

**Examples:**
```
[ALICE] 🔴 SQL injection in query builder | File: src/db/query.ts | Task: 3
[BOB] 🟠 Missing error handling strategy | File: N/A | Task: general
[DIANA] 🟡 PRD section 2.3 not implemented | File: N/A | Task: 5
```

## Per-Rule Verdict Format

In addition to issue lines, every reviewer emits one verdict line per rule in the
numbered rubric inlined into their prompt (see `references/rubric.md` for
`review-work-completion`; analogous files exist for `review-blindly` and the
`run-autopilot` Phase 8 doubt-review).

Exact line shape — one rule per line, no other text on the line, no rationale:

```
R1: pass
R2: fail
R3: pass
```

Rule IDs (`R{n}`) are stable. Reviewers MUST answer every rule. A rule the
reviewer cannot evaluate (insufficient context, blocked by sandbox, etc.)
counts as a `fail` — never omit the line.

> **Note:** `consolidate-findings.sh` parses only lines matching the
> `[{AGENT}] {emoji} ... | File: ... | Task: ...` issue format and silently
> drops everything else. So `R{n}: pass|fail` lines do NOT survive
> consolidation into the findings table — they live only in the raw
> per-agent output files at `dev/local/tmp/{agent}-output-{id}.txt` (the
> location SKILL.md step 6 saves them to). The downstream coverage parser
> (PRD 00038's `review_coverage.py`) reads verdicts from those raw outputs,
> not from the consolidated table.

## Consolidation Rules

Parse agent outputs and merge:

1. **Normalize** - Match similar issues by file+description
2. **Score by consensus** (scales with active agent count N):
   - `[N/N]` Full Consensus - all agents agree, highest priority
   - `[>N/2]/N` Majority Consensus - more than half agree, high priority
   - `[<=N/2]/N` Minority - half or fewer, normal priority
3. **Deduplicate** - Keep best description, note which agents found it

## Consolidated Findings Table

| Consensus | Severity | Issue | File | Found By |
|-----------|----------|-------|------|----------|
| [3/3] | 🔴 Critical | XSS in input handler | src/input.ts | Alice, Bob, Diana |
| [2/3] | 🟠 High | Missing null check | src/api.ts | Alice, Bob |
| [1/3] | 🟡 Medium | No test coverage | src/utils.ts | Diana |

## Issue Documentation Format

```
- {severity emoji} {description}
  - File: {path}
  - Task: {task ID}
  - PRD ref: {section if applicable}
  - Found by: {agent list}
```

## Task Description Format

```
Fix: {issue summary}

Issues addressed:
- {issue 1}
- {issue 2}

Found by: {agents}
Severity: {🔴/🟠/🟡/⚪}

Acceptance criteria:
- [ ] {criterion 1}
- [ ] {criterion 2}
```

## Review Summary Format

```
## Review Summary

Reviewed: {N} completed tasks
PRDs checked: {list}

### Agent Status
{for each configured agent, one of:}
- {Name}: ✅ Available
- {Name}: ⚠️ Unavailable: {reason}
- {Name}: ⏸️ Disabled: {reason}

## Consolidated Findings

### Full Consensus (N/N)
- [N/N] 🔴 {issue} | {file} | Found by: {agents}

### Majority Consensus (>50%)
- [M/N] 🟠 {issue} | {file} | Found by: {agents}

### Minority (<=50%)
- [1/N] 🟡 {issue} | {file} | Found by: {agent}

## Follow-up Tasks Created

1. {task title} (S/M/L) - 🔴 consensus - addresses X, Y
2. {task title} (S/M/L) - 🟠 consensus - addresses Z

_If no issues found: "✅ No follow-up tasks needed. All reviewers passed the implementation."_
```

## Zero Issues Handling

When consolidation yields no issues:
- Skip task creation entirely (don't create empty/placeholder tasks)
- In review summary, note: "✅ All agents passed - no issues found"
- Still save the review file (documents the clean review)
- Report success to user with agent consensus on passing

## Review File Format

Location: `dev/local/reviews/<prd-filename-without-ext>-review-<NN>.md`

Example: PRD `00004-exchanger-web-ui-v1.md` → review `00004-exchanger-web-ui-v1-review-01.md`

```yaml
---
prd: dev/local/prds/wip/<prd-filename>
review: 1
date: YYYY-MM-DD
head_sha: <git HEAD sha at review time>
codex_thread_id: <codex session thread id, optional>
agents:
  alice: available
  bob: available
  carl: available
  diana: available
---

Agent states: `available` (ran successfully), `unavailable` (failed after retries), `disabled` (not invoked).

`head_sha`: the `git rev-parse HEAD` value captured when this review ran. The next rework cycle reads it and passes `--since <head_sha>` to `gather-context.sh`, scoping that cycle's diff to the rework commits. Absent on review files created before this field existed — consumers fall back to a full-branch diff.

`codex_thread_id`: the codex session thread id captured on cycle 1 via `codex-run.sh --emit-thread-id` (Bob/Codex reviewer). The next rework cycle reads it and passes `--resume-thread <codex_thread_id>` so Bob resumes his prior session instead of re-reviewing from zero. Omitted when Bob was skipped this cycle or thread-id capture failed — consumers then run Bob fresh.

# Review: <prd-name>

{review summary content}
```
