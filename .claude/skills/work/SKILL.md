---
name: work
description: Use when executing already-planned tasks one at a time, dispatching to Codex or Gemini and committing after each. Triggers on "work on tasks", "implement tasks", "start working", "execute the plan", "do the work".
---

# Work Through Tasks

Implement pending tasks one-by-one, committing after each completion.

## CRITICAL: One Task at a Time

**STOP.** Before dispatching ANY Agent/Codex/Gemini call, verify you are sending it EXACTLY ONE task. PostToolUse hooks do not fire inside subagents — batching tasks into one Agent call makes pidash show stale progress for the entire duration.

**The loop runs in YOUR session (the main session), not inside a subagent:**

```
for each pending task:
    1. TaskUpdate(in_progress) → sync state file
    2. Agent A writes tests (from requirements only)
    3. test quality gate (main session)
    4. Agent C tries to break tests (adversarial validation)
    5. commit tests
    6. Agent B implements against failing tests
    7. verify THIS task's tests pass (retry Agent B if needed)
    8. commit implementation
    9. TaskUpdate(completed) → sync state file

after all tasks complete:
    10. run full verification suite ONCE (see step 7)
```

**Per-task verification runs only the tests Agent A wrote in step 2.7, not the full project suite.** The full suite (workspace tests, smoke, integration, lint) runs once at the end. This is deliberate: per-task full-suite runs compound to 40+ minutes of redundant test time across a 20-task phase.

If you find yourself writing an Agent prompt that mentions multiple tasks, STOP — you are about to violate this rule.

See **Subagent Dispatch Budget** below — every Agent dispatch must satisfy it.

## Subagent Dispatch Budget

Every prompt passed to the Agent tool (Agent A test author, Agent B implementor, Agent C adversary, or code reviewer) must be **≤ 50 000 bytes**.

PostToolUse hooks do not fire inside subagents (see "CRITICAL: One Task at a Time" above), so the runtime context cap from PRD 00024 cannot abort a subagent that grows past 200K. The bound must be enforced at dispatch time, before the Agent call.

**Procedure before every Agent dispatch:**

1. Assemble the prompt string (task description + relevant file paths + test patterns + code-quality rules block + abort instruction).
2. Measure: write the assembled prompt to `/tmp/dispatch-prompt-<task-id>.txt` (per-task filename — a fixed name collides when independent rework tasks dispatch in parallel), then check size with `wc -c /tmp/dispatch-prompt-<task-id>.txt` (pass the path as an argument — no `<` redirect).
3. If the prompt exceeds 50 000 bytes:
   - Trim by removing the lowest-priority context first (large example files, full architecture docs). Re-measure.
   - If still oversized after one trim pass, abort the task. Wire the abort
     through the same handoff the runtime context-cap hook uses, so
     `/run-autopilot` Phase 0 of the next session replans the PRD in place
     (PRD stays in `wip/`; see Phase 0 step 1's replan procedure — parallel
     to `context_overrun`):
     1. Append to `state.task_aborts[]`:
        ```json
        {"task_id": "<id>", "turn": -1, "total_input_tokens": <prompt-bytes/4>, "cause": "subagent_prompt_overrun"}
        ```
     2. Set `state.stall_reason`:
        ```json
        {"stalled": "subagent_prompt_overrun", "task": "<id>", "prompt_bytes": <prompt-bytes>}
        ```
     3. **Only if `$_AUTOPILOT_LOOP` is set** (per `/run-autopilot` "Loop
        Detection" — manual sessions have no shell wrapper to restart on
        SIGINT), write `task_aborted` to the autopilot signal file. Use
        walk-up discipline to find the autopilot dir from cwd, then write
        to `<autopilot_dir>/signal`. Skip the signal write when
        `$_AUTOPILOT_LOOP` is unset; the next manual `/run-autopilot`
        invocation will resume via `state.stall_reason`.
     4. Append an attempt-log entry per the "Attempt logging" section:
        `outcome: "aborted"`, `cause: "subagent_prompt_overrun"`,
        `model` from `task.metadata.model`,
        `review_cycle: null` (Phase 3) or current `state.cycle` (rework).
     5. Report cause `subagent_prompt_overrun` and stop work on this task.
4. Prepend the abort-instruction line verbatim to the prompt:
   ```
   Abort and report if you read more than 100K of total input. Return the partial result and an abort_reason: context_overrun field.
   ```

**Rationale:** soft enforcement — the subagent honors the instruction — but `/plan-tasks`'s 150K per-task budget bounds how much context `/work` can plausibly hand off anyway. Combined, the 50K dispatch cap, the 100K subagent-internal cap, and the 150K per-task cap keep subagent contexts well under Sonnet 4.6's 200K standard-tier ceiling.

## Per-task model dispatch

Before any Agent call for a task, read `task.metadata.model` (or equivalently `state.tasks[i].model` — `/run-autopilot` keeps the two in sync) and pass it as the Agent tool's `model` parameter.

Applies to **every** Agent call this skill dispatches, including follow-up dispatches inside compound steps. The list below is illustrative, not exhaustive — when the prose says "every Agent call", it means every one:

- Agent A (test author, step 2.7), plus any quality-gate or A/C-round re-dispatches (step 2.8, 2.85)
- Agent C (adversarial validator, step 2.85)
- Agent B (implementor, step 3)
- Agent B re-dispatches on test failure (step 5.5)
- Code reviewer (step 5.7)
- Agent B fix-on-review re-dispatch (step 5.7)
- Agent B re-dispatches on full-suite regression (step 7)

If you add a new Agent call to this skill, pass `model` from `task.metadata.model` — no exceptions.

Accepted values: `"haiku"`, `"sonnet"`, `"opus"`.

**Legacy plans** (created before PRD 00025) have no `metadata.model`. Omit the `model` parameter — subagents inherit the session model. This preserves the pre-PRD-00025 behavior bit-for-bit.

The **Subagent Dispatch Budget** (50K bytes, 100K subagent-internal cap) applies regardless of tier. Haiku doesn't earn a smaller cap; opus doesn't earn a larger one.

## Attempt logging

At every task exit — success in step 6, abort in step 4 (timeout / context exceeded / error after debug) or via the Subagent Dispatch Budget overrun path — append one entry to `state.tasks[i].attempts[]`:

```json
{
  "attempt": <len(existing attempts) + 1>,
  "model": "<tier>",
  "outcome": "completed" | "aborted",
  "review_cycle": <int | null>,
  "cause": "<string | null>"
}
```

**Field semantics**:

- `attempt`: 1-indexed; `len(existing) + 1`.
- `model`: the tier `/work` used for this pass. Read from `task.metadata.model` when set. On legacy plans where `metadata.model` is absent, record the effective session-inherited tier as a string (e.g. `"sonnet"` for a Work-phase Sonnet 4.6 launch). Always a string — never `null`.
- `outcome`: `/work` writes only `"completed"` or `"aborted"`. Later phases upgrade earlier entries — `/run-autopilot` Phase 6 (Rework) step 2 rewrites a `"completed"` entry's outcome to `"review_flagged"` at the start of escalation, then later rewrites a flagged entry's outcome to `"rework_failed"` when the rework pass also fails at the top of the chain.
- `review_cycle`: `null` on a first/Phase-3 attempt; set to the current `state.cycle` integer when the pass is a rework re-dispatch (see step 1.5 "Rework-mode task filter (PRD 00025)").
- `cause`: `null` on success; on abort, the reason — `"context_overrun"`, `"subagent_prompt_overrun"`, `"timeout"`, `"error"`.

**Write procedure**: read `state.json`, append to `tasks[i].attempts[]` (create the array if absent), write back atomically. Merge — do not replace siblings. Walk up from the resolved physical cwd to find the autopilot dir, same pattern as the cap-marker reset in step 2.

Cross-reference: `references/state-schema.md` `tasks[].attempts` row defines the canonical shape.

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

## Dashboard State Sync

`pidash` watches `dev/local/autopilot/state.json` automatically via PostToolUse hooks on `TaskUpdate` and `Agent` calls — no manual sync required from `/work`. Keep `state.tasks[].status` accurate (updated in step 2 at task start and in step 6 at task end) and the dashboard reflects progress in real time.

## Workflow

### 1. Get pending tasks

Use `TaskList` tool to see all tasks. Filter for:

- Status: `pending`
- No blockers (empty `blockedBy`)
- No owner assigned


### 1.5. Rework-mode task filter (PRD 00025)

Read `state.rework_task_ids` from `dev/local/autopilot/state.json` (walk up from cwd to find the autopilot dir, same pattern as the cap-marker reset in step 2). Two modes:

| `rework_task_ids` | Mode | Iteration source |
|-------------------|------|------------------|
| absent or `[]` | **default (full-plan)** | The pending-and-unblocked subset from step 1's `TaskList` filter, in TaskList order. This is the Phase 3 first-pass behavior. |
| non-empty array | **rework mode** | The listed task IDs read directly from `state.rework_task_ids`, in array order — **bypass step 1's status filter entirely**. Each ID is fetched via `TaskGet` regardless of current status (`pending` after Phase 6's reset, or `completed` if Phase 6's reset hasn't fired yet). Tasks NOT in the list are skipped entirely — no Agent A/B/C dispatch, no commits. |

**In rework mode, each task's status is set to `in_progress` at start** via `TaskUpdate` (overwriting whatever the prior status was — `pending` after Phase 6's reset, or `completed` on a defensive re-entry) and to `completed` at end — same lifecycle as a default-mode pass, so the dashboard reflects rework progress.

**In rework mode, the Attempt logging entry** (see "Attempt logging" above) sets `review_cycle` to the current `state.cycle` value (not null), `model` to the escalated tier read from `task.metadata.model` (set by `/run-autopilot` Phase 6), and `outcome` to `"completed"` or `"aborted"` as normal.

**`/work` does NOT modify `rework_task_ids` itself.** Clearing is `/run-autopilot` Phase 6's responsibility, after this `/work` invocation returns. **If `/work` aborts mid-rework** (context overrun, Subagent Dispatch Budget overrun, unrecoverable error), `rework_task_ids` survives in state — this is correct recovery behavior: the next `/run-autopilot` session resumes with the same rework batch and re-attempts the listed tasks at their already-escalated tier. Phase 6's clear runs only on the successful `/work` return.

Cross-reference: `references/state-schema.md` `rework_task_ids` row; `run-autopilot/SKILL.md` Phase 6 (rework) tier-escalation rule.

### 2. Claim and start task

For the first available task:

1. Use `TaskUpdate` to set `status: in_progress` and claim ownership
2. **Sync state file** (see Dashboard State Sync)
3. **Reset the per-task context-cap marker** so the autopilot PostToolUse hook fires once for THIS task, not once per Work phase. The hook also self-clears when the in-progress task id in `state.json` differs from the id stored in the marker file (added cycle-5+1), but the explicit Bash clear here is a belt-and-braces backstop in case state.json's task-id snapshot lags the actual task switch. Use the shared walk-up helper (`_walk_up.py --bash`, which resolves symlinks and walks up to find the autopilot dir) to locate the dir, then remove the marker inside it:
   ```bash
   d=$(python3 ~/.claude/skills/run-autopilot/scripts/_walk_up.py --bash) && rm -f "$d/.cap-fired"
   ```
   No-op when no ancestor has the dir (`--bash` exits non-zero, so the `&&` skips the `rm`) or the marker is already absent (first task of the phase).
4. Use `TaskGet` to read full task description

### 2.5. Load project context

Before dispatching to Codex/Gemini, load relevant context into the prompt:

- AGENTS.md / agent_docs/ architecture docs
- Active PRD from `dev/local/prds/wip/`
- Key module interfaces relevant to the task

1M context makes this practical — richer prompts produce better first-pass results.

**Ambiguity check (Think Before Coding):** Re-read the task description. If scope, data shape, target surface, or success criteria are unclear, stop and ask the user rather than picking silently. See `references/code-quality-principles.md` §1 and `references/code-quality-examples.md` §1 for what counts as a hidden assumption worth surfacing.

### 2.7. Write tests first (Agent A - test author)

Dispatch a separate agent to write tests from requirements only. This agent must NOT receive implementation hints or architecture deep-dives - only what a user of the API would know.

**Agent A runs as:** Claude Code subagent (Agent tool), not Codex/Gemini. It's a focused task that benefits from direct file access for reading test patterns.

**Skip for:** test-only, docs-only, or config-only tasks.

**Agent A receives:**
- Task description and acceptance criteria
- Public interfaces/types relevant to the task
- Existing test patterns (one sample test file from the project)
- Test framework and conventions used

**Agent A does NOT receive:**
- Implementation strategy or architecture docs (loaded in step 2.5 for the main session and Agent B only)
- "How to build this" context
- Access to modify non-test files

See `references/test-author-prompt.md` for the full prompt template — it now embeds Simplicity/Think-Before-Coding/Surgical rules to prevent Agent A from writing speculative tests or silently assuming input shape.

Agent A prompts must satisfy the **Subagent Dispatch Budget** (see section above the Workflow): ≤ 50K bytes, abort-instruction line prepended.

### 2.8. Test quality gate (main session)

Before committing Agent A's tests, review them in the main session against this checklist:

1. **Behavior names?** Each test name describes a behavior ("rejects empty email"), not an implementation detail ("calls validateEmail")
2. **Real assertions?** Assertions check outputs/effects, not mock internals
3. **Edge cases?** Empty, null, boundary, error, and concurrent cases covered where relevant
4. **No tautologies?** Tests don't just restate what the code obviously does

If any check fails, dispatch Agent A again with specific feedback about what's weak. Max 2 quality gate retries.

**Total Agent A budget:** max 5 dispatches across the entire test authoring phase (quality gate + adversarial rounds combined). If exhausted, flag weakness in task output and proceed. Don't block the pipeline forever.

### 2.85. Adversarial validation (Agent C - devil's advocate)

Dispatch Agent C to try to write a **wrong** implementation that passes all of Agent A's tests. Agent C's goal is to exploit weak tests.

**Agent C runs as:** Claude Code subagent (Agent tool). It needs file write access and the project's test runner to actually execute its wrong implementation against the tests.

**Agent C receives:**
- The test files from Agent A
- Public interfaces/types (so its wrong implementation compiles)
- Access to the project's test runner

**Agent C receives nothing else.** No task description, no acceptance criteria, no architecture docs.

**Agent C's job:** Write an implementation that is clearly wrong (hardcoded values, ignored edge cases, shortcut if/else chains), run the tests against it, and report which tests it broke through.

**Outcomes:**

| Agent C result | Action |
|----------------|--------|
| Cannot break tests (tests catch all exploits) | Tests are strong. Proceed to 2.9. |
| Breaks tests with wrong impl that passes | Send Agent C's exploit back to Agent A: "These tests can be passed by: {wrong impl}. Strengthen them." Then re-run Agent C against strengthened tests. Max 2 A/C rounds. |
| 2 A/C rounds exhausted | Flag weakness in task output, proceed anyway. |

See `references/adversarial-test-prompt.md` for the full prompt template.

Agent C prompts must satisfy the **Subagent Dispatch Budget**: ≤ 50K bytes, abort-instruction line prepended.

### 2.9. Commit tests

```bash
git add <test_files>
```
```bash
git commit -m "test(<scope>): add tests for <feature>"
```

Tests are committed separately before implementation. This makes the TDD boundary auditable in git history.

### 3. Implement against tests (Agent B - implementor)

Agent B's job: make the failing tests pass. Tests ARE the spec.

**Agent B receives:**
- Failing test file paths and their content
- Architecture context (AGENTS.md, interfaces, relevant modules)
- Existing code patterns to follow

**Agent B does NOT receive:**
- The task's acceptance criteria prose (tests replace this)
- Permission to modify test files

**Prompt must include:**

1. "Make all failing tests pass. Do NOT modify test files."
2. The code quality rules block from `references/code-quality-principles.md` (copy the "Prompt Snippet" section verbatim). These counter the anti-patterns LLMs produce by default: speculative abstractions, drive-by refactoring, style drift, silent assumptions. Concrete before/after examples are in `references/code-quality-examples.md` if the agent needs them.
3. The abort-instruction line from the **Subagent Dispatch Budget** section. Measure the assembled prompt before dispatching; if > 50K bytes, trim or abort the task with cause `subagent_prompt_overrun`.

**If the task description is ambiguous** (multiple interpretations, unclear scope, unstated format/fields/location), stop before dispatching Agent B and surface the ambiguity to the user. See Example 1 in `references/code-quality-examples.md`. Do not dispatch with guessed-at requirements.

**Determine task domain** (see Tool Selection above), then:

**For Codex tasks:**

- Model: `gpt-5.2-codex` (default) or user preference
- Sandbox: `workspace-write` for code changes
- See `references/codex-integration.md` (TDD implementation mode)

**For Gemini tasks:**

- Permissions: `--allow-all-tools` for code changes
- Mode: `-p` for non-interactive
- See `references/gemini-integration.md` (TDD implementation mode)

### 4. Handle result

| Result | Action |
|--------|--------|
| Success | Continue to step 5 |
| Timeout | Append attempt-log entry per the "Attempt logging" section (`outcome: "aborted"`, `cause: "timeout"`). Split task (see below), mark original as blocked. |
| Context exceeded | Append attempt-log entry per the "Attempt logging" section (`outcome: "aborted"`, `cause: "context_overrun"`). Split task, mark original as blocked. |
| Error | Invoke systematic-debugging if available (see below). On unrecoverable error, append attempt-log entry per the "Attempt logging" section (`outcome: "aborted"`, `cause: "error"`) and report to user. |

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

### 5.5. Verify THIS task's tests pass

Run **only** the specific tests Agent A wrote in step 2.7. Do NOT run the full project test suite, smoke tests, integration tests, or lint here — those run once at the end of the phase (step 7).

- Target the narrowest scope that covers the new tests:
  - Rust: `cargo test -p <crate> --test <test_file>` or `cargo test -p <crate> <module::test_name>`
  - Python: `pytest path/to/test_file.py::test_name`
  - JS/TS: `vitest run path/to/test_file` or `jest path/to/test_file`
- If tests fail, dispatch Agent B again with the failure output. Never dispatch Agent A to weaken tests.
- **Retry prompts must re-include the code-quality rules block** from `references/code-quality-principles.md`, plus an explicit SURGICAL instruction: "Fix only what the failing test output points to. Do not refactor passing code, adjust unrelated files, or change style."
- Max 2 implementation retries before escalating to the user.
- If `superpowers:verification-before-completion` is available, invoke it for additional verification beyond tests — but keep its scope to this task's files, not the full workspace.

**Do not run here:** `cargo test --workspace`, `cargo clippy --workspace`, `./tests/smoke.sh`, `./tests/integration.sh`, `cargo test-full`, or any equivalent full-suite command. These are batched into step 7.

### 5.7. Per-task code review (if superpowers available)

If `superpowers:requesting-code-review` is in the available skills list, dispatch a code review after commit and verification:

1. Get SHAs: `BASE_SHA` = commit before this task, `HEAD_SHA` = HEAD after commit
2. Dispatch code-reviewer subagent with task subject, description, and SHA range
3. Handle result:
   - **Critical/Important issues**: if `superpowers:receiving-code-review` is available, invoke it to evaluate feedback before acting - verify suggestions technically, push back if wrong. Then fix confirmed issues (dispatch Agent B with the code-quality rules block from `references/code-quality-principles.md` plus: "Apply ONLY the specific fixes listed below. Do not refactor surrounding code or address unrelated issues you notice."), re-commit, re-verify (step 5.5), re-review. Max 3 review cycles, then proceed with warning.
   - **Minor issues only or approved**: note minors, proceed to step 6.
   - **Reviewer failed/timed out**: log warning, proceed - Phase 4's PRD-level review catches remaining issues.

Skip for documentation-only or configuration-only tasks.

### 6. Mark complete and sync

1. Use `TaskUpdate` to set `status: completed`
2. **Append an entry to `state.tasks[i].attempts[]`** per the "Attempt logging" section: `outcome: "completed"`, `model` from `task.metadata.model`, `cause: null`, `review_cycle: null` on a Phase-3 first pass or the current `state.cycle` on a rework pass.
3. **Sync state file** (see Dashboard State Sync) — mandatory
4. Return to step 1 for next task
5. When no pending tasks remain, proceed to step 7 (do NOT stop here)

### 7. Final verification (once per work phase)

After all tasks in the phase are marked completed, run the project's full verification suite **once**. This is the single point where the full suite runs — per-task verification (step 5.5) only ran the new tests in isolation, so this step is mandatory and must not be skipped.

**What to run** (project-dependent — use the commands documented in `AGENTS.md` / `CLAUDE.md` / project README):

- Full workspace tests (e.g., `cargo test --workspace`, `pytest`, `npm test`)
- Lint (e.g., `cargo clippy --workspace`, `ruff check`, `eslint .`)
- Smoke tests if the project defines them (e.g., `./tests/smoke.sh`)
- Integration / e2e tests if the project defines them (e.g., `./tests/integration.sh`, `cargo test -p <crate>-e2e`)
- Any project-specific "definition of done" checks

Run each as a separate Bash call. Do not chain with `&&`.

**Handling failures at this step:**

1. Identify which task(s) introduced the regression. The failing test output usually points at a specific module; cross-reference against the task commits.
2. Re-open the offending task via `TaskUpdate(status: in_progress)` and sync state file.
3. Dispatch Agent B with the failure output to fix it. Include the code-quality rules block from `references/code-quality-principles.md` and add: "Fix only the regression identified below. Do not touch unrelated files or refactor adjacent code." Do NOT relax the failing test.
4. After the fix commits, re-run **only** the previously failing commands from step 7 (not the whole suite again) to confirm the fix.
5. Mark the task completed and re-sync.
6. Repeat until the full suite is green.

Max 3 fix cycles at this step before escalating to the user — regressions clustering here usually indicate a design issue that needs human input.

Only stop the work phase once step 7 is fully green.

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

### Parallel dispatch for independent rework fixes

If `superpowers:dispatching-parallel-agents` is in the available skills list and the current batch contains 2+ tasks that:
- Touch completely different files (no overlap)
- Have no `blockedBy` dependencies on each other
- Are all tagged `[C{n}]` or `[D{n}]` (rework tasks, not original plan tasks)

Then dispatch them in parallel using the dispatching-parallel-agents pattern.

**Never parallelize original plan tasks** - the one-at-a-time rule remains for all non-rework tasks due to pidash sync requirements.

## Reference Files

- `references/test-author-prompt.md` - Test author (Agent A) prompt template
- `references/adversarial-test-prompt.md` - Adversarial validator (Agent C) prompt template
- `references/codex-integration.md` - Codex prompt templates and patterns
- `references/gemini-integration.md` - Gemini prompt templates and patterns
- `references/code-quality-principles.md` - Think/Simplicity/Surgical/Goal-driven rules to inject into Agent B prompts
- `references/code-quality-examples.md` - Before/after examples of the anti-patterns those rules prevent
