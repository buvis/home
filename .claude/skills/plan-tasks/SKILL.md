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

1. Read it. The file lists completed-work entries (tasks already done, code already shipped — do NOT re-plan these), an aborted task (the trigger), and a `Budget:` line.
2. Read the `Budget: {n} tokens per task` line from the file. Use that value as the per-task budget for the rest of this invocation — treat it as the hard threshold in step 4.6's split logic, not 150K. If the line is absent, fall back to 75 000.
3. Treat the PRD scope as "everything the PRD asks for **minus** the completed-work entries." When analyzing the PRD in step 3 and decomposing in step 4, skip capabilities already listed under "Completed work" in `replan-context.md`.
4. After all `TaskCreate` calls in step 4 succeed (planning completes without stalling), delete `replan-context.md` — it's consumed. Do NOT delete on stall.

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

Contract (verbatim from PRD — copy exact names, do NOT paraphrase):
- {every exact field name, enum value, type shape, API signature, file/hook
   kind, and threshold the PRD specifies for this task}

Details:
- {specific requirement 1}
- {specific requirement 2}

Acceptance criteria:
- {the PRD's per-task "Acceptance:" clause(s), copied verbatim}

Verify: {how to confirm it's done}
```

**The `Contract` and `Acceptance criteria` sections are mandatory and must be
copied verbatim from the PRD — never paraphrased, never summarized.** `/work`
hands each task to a test author (Tess) who writes tests *from the task
description alone*, having never seen the PRD. If the task says "write the
atlas JSON" instead of naming the exact keys (`head_sha`, `surveyed_at`,
`error_style`, …), Tess invents a plausible-but-wrong schema, the implementer
builds to those tests, and TDD locks in the wrong contract — a self-consistent
failure that only surfaces at the PRD-level review, after every task is "done".
When the PRD pins a name, an enum value, a type, a file kind ("Stop hook" vs
"PostToolUse hook"), or a numeric threshold, that exact string goes into the
task. This is what the "Unambiguous" and "Self-contained" task qualities above
mean in practice. If the PRD itself is vague on a contract the task needs,
surface it in step 6 as an ambiguity — do not let the implementer guess.

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

**Threshold:** 150 000 tokens normally; in replan mode, the value from `replan-context.md`'s `Budget:` line (step 2.5). `est_context_peak = estimated_tokens + 20000` (20K headroom for response generation).

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

### 4.6. Split tasks (context + eligibility)

Step 4.6 has **two independent split triggers**. The existing context-budget trigger is unchanged; the eligibility trigger is new (PRD 00032) and pushes separable backend work toward the `<=2`-file shape that `/work` can route to qwen.

- **Context-budget trigger** (always active): when `estimated_tokens > THRESHOLD` (150K normally; replan-context.md budget in replan mode), the task is too big for a single context window.
- **Eligibility trigger** (infra-gated, see the qwen infra preflight subsection below): a **backend** task touching `>=3` files is split toward `<=2`-file pieces so each subtask can route to qwen. The split is valid only when **cleanly separable** — judged from the PRD's Functional Decomposition and Dependency Graph, with each resulting piece required to independently compile and carry its own passing tests (no piece depends on a symbol another piece introduces). **A trait definition cannot be split from its implementations.**

When **both** triggers apply to the same task, a **single split pass** satisfies both — do not run two passes. After splitting, each subtask is re-estimated per step 4.5 and re-classified per step 4.7 (so `qwen_eligible` reflects the new file count).

**Qwen infra preflight (gates the eligibility trigger only):**

Before applying the eligibility split trigger, `plan-tasks` runs the qwen infra preflight — the three-check probe (`pi` on PATH, llama.cpp `/v1/models` reachable, configured qwen model id present) defined in `~/.claude/skills/work/references/qwen-integration.md` (PRD 00031). The probe is fast; it exists so the eligibility split is only paid for when qwen can actually consume the result.

- **Healthy** → the eligibility trigger is active for this PRD's tasks.
- **Unhealthy, or the probe is unavailable because PRD 00031 has not yet landed** (e.g. `~/.claude/skills/work/references/qwen-integration.md` is absent, `pi` is missing, the llama.cpp endpoint is unreachable, or the configured model id is absent from the served list) → the eligibility trigger is **skipped entirely**; tasks keep their original shape and route to Claude.

The **context-budget trigger is not gated** by the preflight and remains active regardless of qwen's status. The **step-4.7 `qwen_eligible` computation is not gated** either — it is always computed and persisted on every task (staying inert until `work` reads it).

**Opus-signal exemption (skips the eligibility trigger only):**

A task whose text carries an opus signal is **not split for eligibility**. The opus-signal set is **not redefined here** — step 4.6 reuses the exact signal list **defined by step 4.7 Rule 1**, as a single source of truth: if Rule 1's signal list changes, step 4.6 inherits the change automatically because it references rather than copies it.

This check is a **plain text scan** of the task title + description against Rule 1's signal phrases (lowercased, per Rule 1's case-insensitivity note); it does **not** require running the full step-4.7 classifier. A match short-circuits the eligibility trigger and the task keeps its original shape. The context-budget trigger is unaffected — an opus-signal task that also exceeds the context budget is still split for that reason.

The existing context-budget split mechanics, the one-split-attempt rule, and the stall behavior below are **unchanged** by the eligibility trigger — both triggers share them:

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

**`qwen_eligible` computation**

After Rules 1-3 produce a tier and the PRD frontmatter override (above) settles `final_tier`, compute the `qwen_eligible` boolean that `/work` (PRD 00031) reads to decide qwen routing. The formula is:

```
qwen_eligible = model in {haiku, sonnet} AND files_touched <= 2 AND task is backend (not UI)
```

- `model` is the tier produced by Rules 1-3 + override (the same value persisted as `metadata.model`).
- `files_touched` is the per-task file count already used in step 4.5 / Rule 1 / Rule 2.
- **UI** = the task matches the **"Gemini-first tasks"** list in `~/.claude/skills/work/SKILL.md`. Anything not matching that list is **backend**. Reuse `work`'s list as the single source of truth so producer and consumer agree by construction — do not restate the list here; if it changes in `work`, this rule inherits the change.

Each of the following yields `qwen_eligible = false` independently:

- `model == "opus"` (opus tier is never qwen-eligible).
- `files_touched >= 3` (qwen under-covers multi-file tasks).
- The task matches the UI list (Gemini's domain, not qwen's).

The flag is computed **from** the classifier output; it does **not** alter the classifier. Rules 1-3 above are unchanged.

**Persist** the tier and the `qwen_eligible` flag alongside the existing token estimate in `TaskCreate(metadata={...})`, e.g.:

```json
{"estimated_tokens": 72000, "est_context_peak": 92000, "model": "sonnet", "qwen_eligible": true}
```

`qwen_eligible` is persisted on **every** task `plan-tasks` creates. `/work` reads the field directly and does no re-judging — it routes per `qwen_eligible` + its own qwen infra preflight (see `~/.claude/skills/work/SKILL.md`).

On legacy plans created before PRD 00025, `metadata.model` is simply absent — `/work` falls back to omitting the Agent `model` parameter so subagents inherit the session model (backwards-compatible). Likewise, on legacy plans created before PRD 00032, `metadata.qwen_eligible` is absent and `/work` treats it as `false` (routes to Claude at the task's tier).

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
- **Irreducible-coupling reports**: for every `>=3`-file backend task kept whole because step 4.6's eligibility trigger judged it not cleanly separable, report the task and the coupling. The task will route to Claude (not qwen) at its tier — surface why so the planner sees the routing consequence rather than the task being silently kept whole.

## Granularity Guide

| Too coarse | Properly granular |
|------------|-------------------|
| "Add user authentication" | "Create User model with email, passwordHash in src/models/" |
| "Build the API" | "Add POST /users endpoint accepting {email, password}, return 201" |
| "Handle errors" | "Add try/catch in UserService.create(), throw ServiceError on failure" |

See `references/task-examples.md` for more examples.

## Reference Files

- `references/task-examples.md` - Good vs bad task examples
