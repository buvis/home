---
name: work
description: Implement pending tasks using Codex or Gemini, committing after each task. Use when ready to execute planned work. Triggers on "work on tasks", "implement tasks", "start working", "execute the plan", "do the work".
---

# Work Through Tasks

Implement pending tasks one-by-one, committing after each completion.

## Tool Selection

Choose the right tool based on task domain:

| Domain | Tool | Rationale |
|--------|------|-----------|
| Backend, APIs, business logic | Codex | Strong at algorithms, data flow, system design |
| Frontend, UI, visual design | Gemini | Better aesthetic judgment, visual coherence |
| Mixed (e.g., full-stack feature) | Split task or use both sequentially |  |

### Gemini-first tasks

Use `use-gemini` skill when the task involves:

- **Color palettes** - selection, theming, contrast
- **Layouts** - page structure, spacing, visual hierarchy
- **Components** - buttons, forms, cards, any UI elements
- **Typography** - font choices, sizing, readability
- **Animations/transitions** - motion design, timing
- **Responsive design** - breakpoints, mobile adaptation
- **Any user-facing surface** - web pages, GUI, dashboards

### Gemini as design authority

For visual tasks, Gemini can challenge existing specs:

1. Share the planned design/spec with Gemini
2. Ask for critical review before implementation
3. **Trust Gemini's feedback** on visual matters - it has better taste
4. Adjust the plan based on its recommendations
5. Then proceed with implementation

Example prompt addition for visual tasks:

```text
Before implementing, critically review this design spec.
Suggest improvements to colors, spacing, typography, or layout.
Challenge anything that feels generic or could be more distinctive.
```

### Codex-first tasks

Use `use-codex` skill when the task involves:

- Database schemas, migrations
- API endpoints, business logic
- Authentication, authorization
- Data processing, algorithms
- Testing, CI/CD configuration
- Backend infrastructure

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

### 2.5. Load project context

Before dispatching to Codex/Gemini, load relevant context into the prompt:

- AGENTS.md / agent_docs/ architecture docs
- Active PRD from `.local/prds/wip/`
- Key module interfaces relevant to the task

1M context makes this practical — richer prompts produce better first-pass results.

### 2.7. Write tests first (if superpowers available)

If `superpowers:test-driven-development` is in the available skills list, invoke it before dispatching. Write failing tests for the task's acceptance criteria, commit them, then proceed to dispatch. The external tool implements against the failing tests.

Skip if the task is test-only, documentation-only, or configuration-only.

### 3. Select and invoke tool

**Determine task domain** (see Tool Selection above), then:

**For Codex tasks:**

- Model: `gpt-5.2-codex` (default) or user preference
- Sandbox: `workspace-write` for code changes
- See `references/codex-integration.md`

**For Gemini tasks:**

- Permissions: `--allow-all-tools` for code changes
- Mode: `-p` for non-interactive
- See `references/gemini-integration.md`

### 4. Handle result

| Result | Action |
|--------|--------|
| Success | Continue to step 5 |
| Timeout | Split task (see below), mark original as blocked |
| Context exceeded | Split task, mark original as blocked |
| Error | Invoke systematic-debugging if available (see below), otherwise report to user |

### 4.5. Debug on error (if superpowers available)

If the tool returned an error and `superpowers:systematic-debugging` is in the available skills list, invoke it to diagnose the root cause before reporting to the user. If debugging resolves the issue, continue to step 5. If not, report to user and keep task in_progress.

### 5. Commit changes

Stage changed files, then commit in a separate Bash call:
```bash
git add -A
```
```bash
git commit -m "<type>(<scope>): <description>"
```

Never chain these with `&&` in a single Bash call.

Commit message rules:

- Conventional commit format
- One line, no period
- Reference task ID if available

### 5.5. Verify before marking done (if superpowers available)

If `superpowers:verification-before-completion` is in the available skills list, invoke it. Run the project's test suite and any relevant verification commands. Only proceed to step 6 if verification passes. If it fails, return to step 4.5 for debugging.

### 6. Mark complete and update dashboard

1. Use `TaskUpdate` to set `status: completed`
2. If `.local/prd-cycle.json` exists, query `TaskList` and update the state file:
   - `tasks_completed`: count of completed tasks
   - `tasks_total`: total task count
   - `tasks`: array of `{"name": "<task title>", "status": "pending|in_progress|completed"}` for each task
   This keeps the pidash dashboard task list and progress bar accurate in real time.
3. Return to step 1 for next task
4. Stop when no pending tasks remain

## Task Splitting

**Note:** With 1M context, context-exceeded failures are rare. Split primarily for timeout or task complexity, not context limits.

When a tool can't complete a task (timeout/complexity), split it:

1. Analyze what was accomplished
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
| Full-stack feature | Backend task (Codex) → Frontend task (Gemini) |

## Reference Files

- `references/codex-integration.md` - Codex prompt templates and patterns
- `references/gemini-integration.md` - Gemini prompt templates and patterns
