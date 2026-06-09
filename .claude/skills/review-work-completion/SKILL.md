---
name: review-work-completion
description: Use after all tasks are completed to validate implementation against PRD requirements via multi-agent consensus review. Triggers on "review work", "check completed work", "validate implementation", "are we done".
---

# Review Work Completion

## What This Does

Validates completed implementation work against PRD requirements using independent AI reviewers (tools may change in the future). Each reviewer analyzes the code changes and PRD criteria separately, then findings are consolidated by consensus - issues flagged by multiple reviewers get higher priority. Creates follow-up tasks for any gaps found.

**Why multiple reviewers:** Different models catch different issues. Consensus scoring surfaces real problems while filtering noise from single-model false positives.

> **Note for anyone reviewing/auditing this skill:** See `references/design-rationale.md` for settled design decisions
> before suggesting changes. This doesn't apply to skill users, as it doesn't add any useful information
> to perform the skill.

## Reviewers

- **Alice** → Claude subagent (direct, not nested CLI)
- **Bob** → Codex
- **Carl** → Gemini (frontend & design specialist; skipped when the Gemini CLI is unavailable)
- **Diana** → Sonnet 4.6 via copilot CLI

## Workflow

### 1. Validate prerequisites

Check these exist:

1. `~/.claude/skills/use-codex/scripts/codex-run.sh` - executable
2. `~/.claude/skills/use-sonnet/scripts/sonnet-run.sh` - executable
3. `dev/local/prds/wip/` contains at least one `.txt` or `.md` file

**Optional - Carl (Gemini):** check `~/.claude/skills/use-gemini/scripts/gemini-run.sh` is executable AND the Gemini CLI resolves (`mise which gemini` or `command -v gemini` succeeds). If both pass, Carl is active. If either fails, skip Carl and proceed with the three remaining reviewers - this is graceful degradation, not a failure. Note in the final review file which reviewers ran.

Create if missing: `dev/local/tmp/`, `dev/local/reviews/`

**Path convention:** All `dev/local/` paths in this skill are relative to the project root. When passing file paths to subagents or external scripts, always use absolute paths (e.g. `$PWD/dev/local/tmp/...`) so they resolve correctly regardless of the subagent's working directory.

**If CLI/script check fails, STOP and report:**

```text
Cannot proceed: {missing prerequisite}
```

### 2. Check task status

Use `TaskList`.

**If no tasks exist:** If `catchup` skill is available, invoke it to populate tasks from branch history, then return here. If `catchup` is unavailable, proceed without task context.

**If ANY task is `in_progress`:** STOP and report:

```text
Cannot review: {N} task(s) still in progress
- Task {id}: {subject}
```

**If ALL tasks are `pending`:** STOP and report:

```text
Cannot review: no completed tasks found. Complete tasks first.
```

### 3. Gather context

Read all PRDs from `dev/local/prds/wip/`. Extract success criteria, acceptance criteria, required features.

Load architecture docs: AGENTS.md, agent_docs/, and any `dev/local/` architecture notes. Reviewers benefit from seeing invariants and boundaries.

Build markdown of completed tasks with descriptions. **One row per task — never merge rows.** If a task was implemented in the same commit as another task (folded), it still gets its own row; note the shared commit SHA and the companion task IDs in the row's description so the cycle-N task→commit table stays unambiguous.

Write tasks markdown to `dev/local/tmp/review-tasks-{id}.md` and PRD summary to `dev/local/tmp/review-prd-{id}.md` using the **Write tool** (not bash).

**Determine review scope (full vs incremental).** With `Glob`, list existing review files for this PRD: `dev/local/reviews/<prd-name>-review-*.md` (PRD filename without the `.md` extension).

- **No prior review file** → cycle 1, a **full review**. Run `gather-context.sh` without `--since`.
- **A prior review file exists** → this is a rework cycle, an **incremental review**. Read the highest-numbered prior file's `head_sha` frontmatter field.
  - `head_sha` present → pass `--since <head_sha>` to `gather-context.sh`. The diff then covers only the rework commits since that cycle, not the whole PRD branch — the prior cycle already reviewed the full diff. Also read that file's consolidated findings; step 4 hands them to the reviewers to verify.
  - `head_sha` absent (file predates this field) → fall back to a full review (omit `--since`).

Capture the current HEAD now — `git rev-parse HEAD` — and hold it; step 8 stamps it into this cycle's review file as `head_sha`.

Also capture the diff range for the coverage gate (used in step 6). For an **incremental review** the diff range is `<prior-cycle-head-sha>` (the same SHA passed to `gather-context.sh --since`). For a **full review** compute it via `git merge-base HEAD origin/HEAD` (fallback: `git merge-base HEAD master`, then `git merge-base HEAD develop`). Store this as `COVERAGE_DIFF_RANGE`.

Run `gather-context.sh` (from project root). Full review:

```bash
~/.claude/skills/review-work-completion/scripts/gather-context.sh dev/local/tmp/review-tasks-{id}.md dev/local/tmp/review-prd-{id}.md
```

Incremental review (rework cycle) — prepend `--since <prior-cycle-head-sha>`:

```bash
~/.claude/skills/review-work-completion/scripts/gather-context.sh --since <prior-cycle-head-sha> dev/local/tmp/review-tasks-{id}.md dev/local/tmp/review-prd-{id}.md
```

Both positional args are optional — omit if no tasks/PRD available. Outputs context file and diff file paths to `dev/local/tmp/`.

### 4. Prepare agent prompts

Create prompt files in `dev/local/tmp/`:

For each active agent, use the **Write tool** (not bash heredocs) to create `dev/local/tmp/{agent}-prompt-{unique-id}.md` (use timestamp or UUID). **Use absolute paths** (e.g. `/full/path/to/project/dev/local/tmp/...`) when writing and when referencing these files in agent prompts - relative `dev/local/` paths get misresolved as `~/dev/local/` by subagents. See `references/agent-prompts.md` for prompt template structure.

**Create each prompt independently.** Do NOT create one prompt and copy/sed it into another - this triggers bash permission warnings (quote characters in comments desync quote tracking). Diana and Alice share the same template; Bob gets the sandbox constraints appendix. Build each from the template directly.

> **Why Write tool:** Prompt templates contain patterns like `{path or "N/A"}` that trigger bash permission checks ("brace with quote character - expansion obfuscation"). The Write tool bypasses this entirely since it doesn't go through the shell.

With 1M context, agent prompts can include more background — full PRD, architecture summary, relevant module interfaces — rather than compressed summaries. Richer context produces better reviews.

**For an incremental review** (step 3 found a prior cycle): add to each agent prompt the prior cycle's consolidated findings, plus this instruction:

> This is an **incremental review** of the rework done since the previous review cycle — the diff is scoped to changes since then. Two jobs: (1) for each prior finding listed below, verify it is now resolved in the code; (2) review the scoped diff for any regression the rework introduced. You need not re-review unchanged code; the previous cycle already reviewed the full implementation.

### 5. Run agent review

**Launch ALL active agents in a SINGLE message with parallel Task tool calls.**

Active agents: Alice, Bob, Diana, and Carl. Include Carl only if the optional Gemini check in step 1 passed; otherwise run the three remaining reviewers.

Read these before proceeding:

- `references/agent-invocation.md` - invocation commands for each agent
- `references/retry-policy.md` - retry and format compliance rules

### 6. Consolidate findings

Save each active agent's output to `dev/local/tmp/{agent}-output-{id}.txt`, then run:

```bash
~/.claude/skills/review-work-completion/scripts/consolidate-findings.sh \
  --surface work-completion \
  --prd $PWD/dev/local/prds/wip/<prd-filename> \
  --diff-range <COVERAGE_DIFF_RANGE captured in step 3> \
  --rubric ~/.claude/skills/review-work-completion/references/rubric.md \
  --repo $PWD \
  --run-tests \
  --write-aggregate $PWD/dev/local/tmp/coverage-{id}.md \
  ALICE:$PWD/dev/local/tmp/alice-output-{id}.txt \
  BOB:$PWD/dev/local/tmp/bob-output-{id}.txt \
  CARL:$PWD/dev/local/tmp/carl-output-{id}.txt \
  DIANA:$PWD/dev/local/tmp/diana-output-{id}.txt
```

Pass only agents that produced output (omit the `CARL:` pair when Carl was skipped). The script computes consensus dynamically from the number of agent pairs provided.

**If the coverage gate fails** (non-zero exit), stop and report the gap named in stderr. Do not proceed to step 7.

If coverage passes, `dev/local/tmp/coverage-{id}.md` now contains the aggregate coverage block. Step 8 appends it to the review file.

Outputs consolidated issues sorted by consensus then severity. See `references/output-formats.md` for output format details.

### 7. Create follow-up tasks

**If no issues found:** Skip task creation. Report clean review to user.

**If issues found:** Use `TaskCreate`, prioritizing multi-agent consensus:

- Process 🔴 → 🟠 → 🟡 order
- Max 25 tasks (batch overflow into "Misc fixes")
- Group by theme
- Tag complexity: `(S)` small, `(M)` medium, `(L)` large

See `references/output-formats.md` for task description format.

### 8. Save review file

Create at `dev/local/reviews/`.

See `references/output-formats.md` for filename convention, frontmatter, and content format.

Stamp the `head_sha` frontmatter field with the HEAD sha captured in step 3 — the next rework cycle reads it to scope its diff via `--since`.

Include all findings even if zero issues.

**Append the aggregate coverage block** from `dev/local/tmp/coverage-{id}.md` (written by step 6's coverage gate) at the end of the review file, after all findings. Use the **Write tool** to build the complete file content including the block.
