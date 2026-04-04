---
name: review-work-completion
description: Multi-agent review of completed work against PRD requirements. Use after all tasks are completed to validate implementation quality. Triggers on "review work", "check completed work", "validate implementation", "are we done".
---

# Review Work Completion

## What This Does

Validates completed implementation work against PRD requirements using independent AI reviewers (tools may change in the future). Each reviewer analyzes the code changes and PRD criteria separately, then findings are consolidated by consensus - issues flagged by multiple reviewers get higher priority. Creates follow-up tasks for any gaps found.

**Why three reviewers:** Different models catch different issues. Consensus scoring surfaces real problems while filtering noise from single-model false positives.

> **Note for anyone reviewing/auditing this skill:** See `references/design-rationale.md` for settled design decisions
> before suggesting changes. This doesn't apply to skill users, as it doesn't add any useful information
> to perform the skill.

## Reviewers

- **Alice** → Claude subagent (direct, not nested CLI)
- **Bob** → Codex
- ~~**Carl** → Gemini~~ (disabled - GitHub removed Gemini from copilot model routing)
- **Diana** → Sonnet 4.6 via copilot CLI

## Workflow

### 1. Validate prerequisites

Check these exist:

1. `~/.claude/skills/use-codex/scripts/codex-run.sh` - executable
2. `~/.claude/skills/use-sonnet/scripts/sonnet-run.sh` - executable
3. `dev/local/prds/wip/` contains at least one `.txt` or `.md` file

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

Build markdown of completed tasks with descriptions.

Write tasks markdown to `dev/local/tmp/review-tasks-{id}.md` and PRD summary to `dev/local/tmp/review-prd-{id}.md` using the **Write tool** (not bash). Then run (from project root):

```bash
~/.claude/skills/review-work-completion/scripts/gather-context.sh dev/local/tmp/review-tasks-{id}.md dev/local/tmp/review-prd-{id}.md
```

Both args are optional — omit if no tasks/PRD available. Outputs context file and diff file paths to `dev/local/tmp/`.

### 4. Prepare agent prompts

Create prompt files in `dev/local/tmp/`:

For each active agent, use the **Write tool** (not bash heredocs) to create `dev/local/tmp/{agent}-prompt-{unique-id}.md` (use timestamp or UUID). **Use absolute paths** (e.g. `/full/path/to/project/dev/local/tmp/...`) when writing and when referencing these files in agent prompts - relative `dev/local/` paths get misresolved as `~/dev/local/` by subagents. See `references/agent-prompts.md` for prompt template structure.

**Create each prompt independently.** Do NOT create one prompt and copy/sed it into another - this triggers bash permission warnings (quote characters in comments desync quote tracking). Diana and Alice share the same template; Bob gets the sandbox constraints appendix. Build each from the template directly.

> **Why Write tool:** Prompt templates contain patterns like `{path or "N/A"}` that trigger bash permission checks ("brace with quote character - expansion obfuscation"). The Write tool bypasses this entirely since it doesn't go through the shell.

With 1M context, agent prompts can include more background — full PRD, architecture summary, relevant module interfaces — rather than compressed summaries. Richer context produces better reviews.

### 5. Run agent review

**Launch ALL active agents in a SINGLE message with parallel Task tool calls.**

Active agents: Alice, Bob, Diana (Carl is disabled).

Read these before proceeding:

- `references/agent-invocation.md` - invocation commands for each agent
- `references/retry-policy.md` - retry and format compliance rules

### 6. Consolidate findings

Save each active agent's output to `dev/local/tmp/{agent}-output-{id}.txt`, then run:

```bash
~/.claude/skills/review-work-completion/scripts/consolidate-findings.sh \
  ALICE:dev/local/tmp/alice-output-{id}.txt \
  BOB:dev/local/tmp/bob-output-{id}.txt \
  DIANA:dev/local/tmp/diana-output-{id}.txt
```

Pass only agents that produced output. The script computes consensus dynamically from the number of agent pairs provided.

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

Include all findings even if zero issues.
