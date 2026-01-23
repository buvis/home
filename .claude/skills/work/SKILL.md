---
name: work
description: Implement pending tasks using Codex, committing after each task
---

# Work Through Tasks

Implement pending tasks one-by-one using Codex, committing after each completion.

## Workflow

### 1. Get pending tasks

Use `TaskList` tool to see all tasks. Filter for:
- Status: `pending`
- No blockers (empty `blockedBy`)
- No owner assigned

### 2. Claim and start task

For the first available task:
1. Use `TaskUpdate` to set `status: in_progress` and claim ownership
2. Use `TaskGet` to read full task description

### 3. Invoke Codex

Use the `use-codex` skill to execute the task:
- Model: `gpt-5.1-codex-mini` (default) or user preference
- Reasoning: `medium` (default)
- Sandbox: `workspace-write` for code changes
- Prompt: task description + acceptance criteria

See `references/codex-integration.md` for prompt templates.

### 4. Handle Codex result

| Result | Action |
|--------|--------|
| Success | Continue to step 5 |
| Timeout | Split task (see below), mark original as blocked |
| Context exceeded | Split task, mark original as blocked |
| Error | Report to user, keep task in_progress |

### 5. Commit changes

```bash
git add -A && git commit -m "<type>(<scope>): <description>"
```

Commit message rules:
- Conventional commit format
- One line, no period
- Reference task ID if available

### 6. Mark complete and continue

1. Use `TaskUpdate` to set `status: completed`
2. Return to step 1 for next task
3. Stop when no pending tasks remain

## Task Splitting

When Codex can't complete a task (timeout/context), split it:

1. Analyze what Codex accomplished
2. Create 2-4 smaller tasks covering remaining work
3. Use `TaskCreate` for each subtask
4. Set dependencies with `TaskUpdate.addBlockedBy` if sequential
5. Mark original task as blocked or completed (if partially done)

### Split criteria

| Original scope | Split into |
|----------------|------------|
| Multiple files | One task per file |
| Multiple features | One task per feature |
| Large refactor | Extract → transform → cleanup |

## Reference Files

- `references/codex-integration.md` - Prompt templates and Codex interaction patterns
