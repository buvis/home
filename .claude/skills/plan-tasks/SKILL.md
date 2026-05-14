---
name: plan-tasks
description: Use when breaking a PRD into granular, sequenced implementation tasks ready for the work skill. Triggers on "plan tasks", "create tasks from PRD", "implement PRD", "break down the spec".
---

# Plan Tasks from PRD

Create implementation tasks from PRD documents.

## Workflow

### 1. List available PRDs

```bash
~/.claude/skills/plan-tasks/scripts/list-prds.sh
```

Or manually, use `Glob` to check for PRDs:
```
Glob("dev/local/prds/wip/*.md")
Glob("dev/local/prds/backlog/*.md")
```

If no PRDs found, inform user and stop.

### 2. Select PRD

- **1 PRD in wip** → auto-select it, don't ask
- **0 PRDs in wip** → present backlog list, ask user to pick
- **2+ PRDs in wip** → present list (wip + backlog), ask user to pick

### 3. Analyze PRD

Read the full PRD. Also load existing codebase architecture context (AGENTS.md, agent_docs/, `dev/local/` architecture notes) to cross-reference. Identify reusable existing code before creating tasks.

Extract:
- Capabilities and features
- Module structure
- Dependency graph
- Implementation phases
- Existing patterns/utilities that implementers should reuse

### 4. Create tasks

Use `TaskCreate` for each task. Follow these rules:

**Task qualities**:
- **Atomic**: Single focused change
- **Self-contained**: All context in description
- **Sequenced**: Dependencies explicit
- **Unambiguous**: No decisions left to implementer

**Task description format**:
```
{What to do}

Location: {file paths or how to find them}

Reuse: {existing patterns, utilities, or modules to build on — if any}

Details:
- {specific requirement 1}
- {specific requirement 2}

Verify: {how to confirm it's done}
```

### 4.5. Estimate per-task context budget

For each task, compute an estimate so `/work` stays under Sonnet 4.6's 200K standard-tier ceiling.

**Formula:**

```
estimated_tokens = sum(file_bytes/4 for file in task.files_touched)
                 + prd_slice_bytes/4
                 + plan_text_bytes/4
                 + 30000
```

- `file_bytes/4`: ~4 chars per token, accurate within ±20% for code (less accurate for prose-heavy markdown; round up when in doubt).
- `prd_slice_bytes`: bytes of the PRD section(s) this task references.
- `plan_text_bytes`: bytes of the task's own description/details.
- `30000`: overhead constant for system prompt + tool defs + skill texts at Sonnet 4.6.

**Threshold:** 150 000 tokens. `est_context_peak = estimated_tokens + 20000` (20K headroom for response generation).

**Persist** both values in the task's `TaskCreate(metadata={...})` field:

```json
{"estimated_tokens": 87000, "est_context_peak": 107000}
```

**Worked example:** a task touches three files (80KB, 40KB, 20KB) with a 25KB PRD slice and a 3KB plan text.

```
sum(file_bytes/4)   = (80000 + 40000 + 20000) / 4 = 35 000
prd_slice_bytes/4   = 25000 / 4                   =  6 250
plan_text_bytes/4   = 3000 / 4                    =    750
overhead            =                              30 000
                                                  ───────
estimated_tokens    =                              72 000
est_context_peak    = 72 000 + 20 000           =  92 000
```

Below the 150K threshold → task ships as-is.

### 4.6. Split oversized tasks

When `estimated_tokens > 150000`, split:

1. **File boundary first.** Split into one task per file. The PRD slice prorates equally; the 30K overhead applies once per task. Re-estimate each subtask.
2. **Capability boundary second.** If a task touches only one file and still exceeds 150K, split along capability boundaries inside the PRD's Functional Decomposition section.
3. **One split attempt only.** If a task still exceeds 150K after splitting, mark the PRD as stalled.

**Stall behavior:**

When unable to split below 150K, **merge** a `stall_reason` key into the existing `dev/local/autopilot/state.json` (do NOT replace the file — the existing `phase`, `phases_completed`, `tasks`, `batch`, etc. must be preserved). Read the file, set the new key, write it back atomically:

```json
{
  ...all existing state...,
  "stall_reason": {
    "stalled": "oversized_task",
    "task": "<task-id>",
    "estimated_tokens": <int>
  }
}
```

**Then delete every task you already created** via `TaskCreate` for this PRD: query `TaskList`, call `TaskUpdate(status: "deleted")` on each. `/plan-tasks` calls `TaskCreate` before the per-task budget check, so by the time the stall fires there are orphan tasks in the tracker. Cleaning up here makes the stall self-contained: any caller (not just `/run-autopilot`) gets the same post-stall state. `/run-autopilot` Phase 2 also performs this cleanup as a backstop.

After both writes succeed, exit non-zero so `/run-autopilot` Phase 2 detects the stall, moves the PRD from `dev/local/prds/wip/` to `dev/local/prds/stalled/` (creating the directory if missing), clears the stall key from state, and proceeds to the next backlog item without user prompt. See `/run-autopilot` Phase 2 for the consumer-side contract.

### Estimator caveats

The bytes/4 heuristic is accurate within ±20% for source code, less accurate for prose-heavy markdown. When the largest input is markdown (PRD prose, docs), round up. When estimates land within 10% of 150K, prefer splitting — the runtime context cap hook (Phase 2 of PRD 00024) will abort tasks that overrun anyway, and a planned split is cheaper than a runtime abort.

### 5. Set dependencies

Use `TaskUpdate` with `addBlockedBy` to link dependent tasks.

Follow PRD's dependency graph:
- Phase 0 tasks: no blockers
- Phase 1 tasks: blocked by Phase 0
- etc.

### 6. Report summary

Output:
- Total tasks created
- Execution order (phases)
- Any PRD ambiguities needing clarification

## Granularity Guide

| Too coarse | Properly granular |
|------------|-------------------|
| "Add user authentication" | "Create User model with email, passwordHash in src/models/" |
| "Build the API" | "Add POST /users endpoint accepting {email, password}, return 201" |
| "Handle errors" | "Add try/catch in UserService.create(), throw ServiceError on failure" |

See `references/task-examples.md` for more examples.

## Reference Files

- `references/task-examples.md` - Good vs bad task examples
