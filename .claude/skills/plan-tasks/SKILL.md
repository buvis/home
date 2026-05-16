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

### 2.5. Detect replan mode

Before reading the PRD, check for `dev/local/autopilot/replan-context.md`. If present, this invocation is a **replan** triggered by `/run-autopilot` Phase 0's abort handler — the prior Work session aborted on a too-big task and autopilot wants the remaining scope re-split into smaller chunks.

When `replan-context.md` exists:

1. Read it. The file lists completed-work entries (tasks already done, code already shipped — do NOT re-plan these) and an aborted task (the trigger).
2. Use a **per-task budget of 75 000 tokens** (half the standard 150K) for the rest of this invocation. Treat 75K as the hard threshold in step 4.6's split logic, not 150K.
3. Treat the PRD scope as "everything the PRD asks for **minus** the completed-work entries." When analyzing the PRD in step 3 and decomposing in step 4, skip capabilities already listed under "Completed work" in `replan-context.md`.
4. After all `TaskCreate` calls in step 4 succeed (planning completes without stalling), delete `replan-context.md` — it's consumed. Do NOT delete on stall — autopilot's loop guard relies on the file being present to recognize the second-attempt replan as a retry of the same recovery.

When `replan-context.md` is absent → normal first-pass planning. Use the 150K threshold.

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

**Threshold:** 150 000 tokens (or 75 000 in replan mode — see step 2.5). `est_context_peak = estimated_tokens + 20000` (20K headroom for response generation).

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

When `estimated_tokens > THRESHOLD` (150K normally, 75K in replan mode per step 2.5), split:

1. **File boundary first.** Split into one task per file. The PRD slice prorates equally; the 30K overhead applies once per task. Re-estimate each subtask.
2. **Capability boundary second.** If a task touches only one file and still exceeds the threshold, split along capability boundaries inside the PRD's Functional Decomposition section.
3. **One split attempt only.** If a task still exceeds the threshold after splitting, mark the PRD as stalled (use the threshold value in the stall_reason).

**Stall behavior:**

When unable to split below the threshold (150K standard, 75K in replan mode), **merge** a `stall_reason` key into the existing `dev/local/autopilot/state.json` (do NOT replace the file — the existing `phase`, `phases_completed`, `tasks`, `batch`, etc. must be preserved). Read the file, set the new key, write it back atomically:

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

The bytes/4 heuristic is accurate within ±20% for source code, less accurate for prose-heavy markdown. When the largest input is markdown (PRD prose, docs), round up. When estimates land within 10% of the threshold (150K standard / 75K replan), prefer splitting — the runtime context cap hook (Phase 2 of PRD 00024) will abort tasks that overrun anyway, and a planned split is cheaper than a runtime abort.

**30K overhead re-derivation:** The constant was measured by reading `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` from the first `message.usage` line in a fresh Sonnet 4.6 Work-phase transcript (zero task context loaded — just the system prompt, tool defs, and active skills). Re-derive when upgrading the model or adding/removing skills: start an empty `/work` session, read the first usage line from `~/.claude/projects/<hash>/<session>.jsonl`, sum the three token fields. Update the constant and the worked example if the new value differs by more than 5K.

### 4.7. Assign per-task model tier

For each task, classify a model tier and persist it as `metadata.model: "haiku"|"sonnet"|"opus"` so `/work` can dispatch each subagent at the right tier (PRD 00025).

**Inputs:** task title + description (string), `files_touched` count, estimated lines-changed (rough — pull from the task plan or estimate from the file slice), the `estimated_tokens` computed in step 4.5, and the active PRD body (for novelty signals).

**Rules** (evaluated top-down, first match wins):

| Rule | Tier | Trigger |
|------|------|---------|
| 1 | `opus` | PRD or task text contains any of: `design`, `architect`, `introduce`, `novel algorithm`, `concurrency`, `migrate`, `refactor across` — OR `files_touched > 8` — OR `estimated_tokens > 120000` |
| 2 | `haiku` | `files_touched ≤ 2` AND est. lines-changed `≤ 50` AND task text matches a mechanical-pattern signal (`add log`, `rename`, `add test for`, `port`, `mirror`, `inline`, `extract constant`, `update import`, `bump version`) AND no Rule 1 keywords present |
| 3 | default | `sonnet`, unless PRD frontmatter `default_model:` is set (see override below) |

**Keyword matching is case-insensitive** for both Rule 1's novelty signals and Rule 2's mechanical-pattern signals — match `Rename module X` the same as `rename module x`, `DESIGN cache layer` the same as `design cache layer`. The signal phrases are stored lowercase; lowercase the task/PRD text before scanning.

**Comparand choice for Rule 1's 120K clause**: the threshold compares `estimated_tokens` (raw input budget from step 4.5), not `est_context_peak` (which adds the 20K headroom). Rationale: the 20K headroom is the cap-hook's safety margin, not user-visible work — escalating to opus only when the raw work itself is large keeps the rule's intent ("the task itself is big") aligned with the field that measures it. The effective `est_context_peak` at this threshold lands at ~140K, which is the "close to the 150K cap" the PRD describes.

**Examples**:

- "rename `foo` to `bar` in `module/x.rs`" (1 file, ~10 lines) → matches Rule 2 → `haiku`.
- "design new caching layer with concurrency guarantees" (touches `cache`, `keys`, `invalidation`, `metrics` — 4 files, ~300 lines) → matches Rule 1 via the `design` and `concurrency` keywords (any one keyword fires the rule; the `files_touched > 8` clause does not need to be met) → `opus`.
- "add POST /users endpoint with email validation" (3 files, 80 lines) → no Rule 1 or 2 match → `sonnet`.

**PRD frontmatter override**

PRD frontmatter accepts an optional `default_model: haiku|sonnet|opus` field that acts as a **floor** on the classifier output — never a demotion. Parse it from the YAML block at the top of the PRD using the same approach `/run-autopilot` Phase 0 uses for `catchup:` (look for `---` delimiters, parse the YAML, accept `haiku`/`sonnet`/`opus`). Behavior:

- **Absent frontmatter or unset `default_model:`** → no override (silent; the classifier output from Rules 1–3 passes through unchanged). This is what keeps Rule 2's `haiku` reachable without requiring every PRD to opt in explicitly — and matches `/run-autopilot` Phase 6's `[D]` follow-up behavior.
- **Malformed frontmatter or invalid `default_model:` value** → no override AND log a one-line warning. The classifier output passes through.
- **Valid value (`haiku`/`sonnet`/`opus`)** → apply the floor below.

Apply the override AFTER Rules 1-3 produce a classifier tier, by taking the maximum across the precedence `haiku < sonnet < opus` (only when `default_model` is a valid value):

```
final_tier = max(classifier_tier, default_model)
```

This guarantees:

- `default_model: opus` raises every task to `opus` — Rule 2's `haiku` is clamped up to `opus`; Rule 3's `sonnet` becomes `opus`; Rule 1's `opus` stands. Matches PRD 00025's Critical Scenarios "PRD frontmatter override" test.
- `default_model: sonnet` clamps Rule 2's `haiku` up to `sonnet`; Rule 3 yields `sonnet`; Rule 1's `opus` stands.
- `default_model: haiku` is a no-op (`haiku` is already the floor of the precedence; classifier output stands as-is).
- Rule 1's `opus` escalations are never demoted by any `default_model` value.

**Persist** the tier alongside the existing token estimate in `TaskCreate(metadata={...})`:

```json
{"estimated_tokens": 87000, "est_context_peak": 107000, "model": "sonnet"}
```

On legacy plans created before PRD 00025, `metadata.model` is simply absent — `/work` falls back to omitting the Agent `model` parameter so subagents inherit the session model (backwards-compatible).

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
