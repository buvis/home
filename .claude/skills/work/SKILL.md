---
name: work
description: Use when executing already-planned tasks one at a time, dispatching to Codex or Gemini and committing after each. Triggers on "work on tasks", "implement tasks", "start working", "execute the plan", "do the work".
---

# Work Through Tasks

Implement pending tasks one-by-one, committing after each completion.

## CRITICAL: Never Ask the User to Run Commands

This skill runs inside an **automated autopilot loop**. The user is not watching. Do not ask the user to run tests, commands, or do anything manually. The only valid reasons to surface output to the user are:

1. A genuinely irreversible action that requires explicit confirmation (e.g. force-pushing a shared branch).
2. More than two consecutive failed attempts at the same automated step with no remaining fallback.

**When test verification is blocked** (e.g. all cargo processes were backgrounded and the build lock was contended): if the code compiles cleanly and the logic change is correct by inspection, commit and proceed. The full-suite verification run at the end of the phase will catch regressions. Do not stop and ask the user to run anything.

**When cargo commands get backgrounded by the session**: the Bash tool may background long-running commands regardless of the `run_in_background` flag. Wait for background completions via Monitor (up to 20 minutes for full test suites). Never launch a second cargo command while one is still running — they contend on the build lock and jam the shell. If a Monitor times out, read the output file directly; if the file is empty the build lock was still held, wait longer before retrying.

## CRITICAL: One Task at a Time

**STOP.** Before dispatching ANY Agent/Codex/Gemini call, verify you are sending it EXACTLY ONE task. PostToolUse hooks do not fire inside subagents — batching tasks into one Agent call makes pidash show stale progress for the entire duration.

**The loop runs in YOUR session (the main session), not inside a subagent:**

```
for each pending task:
    a. TaskUpdate(in_progress) → sync state file
    b. Tess writes tests (from requirements only)
    c. test quality gate (main session)
    d. Devon tries to break tests (adversarial validation)
    e. commit tests
    f. Ivan implements against failing tests
    g. verify THIS task's tests pass (retry Ivan if needed)
    h. commit implementation
    i. TaskUpdate(completed) → sync state file

after all tasks complete:
    j. run full verification suite ONCE (see step 7 below)
```

The loop steps above are lettered on purpose — they are a conceptual
sequence, distinct from the numbered section headers (`### 1`…`### 7`)
that the rest of this skill cross-references. "step 7" always means the
section, never a loop step.

**Per-task verification runs only the tests Tess wrote in step 2.7, not the full project suite.** The full suite (workspace tests, smoke, integration, lint) runs once at the end. This is deliberate: per-task full-suite runs compound to 40+ minutes of redundant test time across a 20-task phase.

If you find yourself writing an Agent prompt that mentions multiple tasks, STOP — you are about to violate this rule.

See **Subagent Dispatch Budget** below — every Agent dispatch must satisfy it.

## Subagent Dispatch Budget

Every prompt passed to the Agent tool (Tess, Ivan, Devon, or the code reviewer) must be **≤ 50 000 bytes**, with the abort-instruction line prepended. Measure before every dispatch; trim the lowest-priority context once, and if still oversized abort the task with cause `subagent_prompt_overrun`.

See `references/subagent-dispatch.md` for the measurement procedure, the verbatim abort-instruction line, the abort-handoff steps, and the rationale. Read it before your first Agent dispatch in a session.

## Subagent Watchdog

Every Agent dispatch must be wrapped in a watchdog: dispatch with `run_in_background: true`, wait with `Monitor` (15-minute timeout), and on timeout `TaskStop` the agent and handle it as the **Result lost / hung** row of step 4's table (which routes to the infrastructure-failure circuit breaker, step 4.2). A foreground `Agent` call that hangs blocks this session indefinitely — never dispatch one unwatched.

See `references/subagent-dispatch.md` for the full dispatch protocol, helper-script (`use-codex`/`use-gemini`) handling, and the three distinct deadlines (15 min / 10 min / 20 min, by mechanism). Read it before your first Agent dispatch in a session.

## Per-task model dispatch

Before any Agent call for a task, read `task.metadata.model` (or equivalently `state.tasks[i].model` — `/run-autopilot` keeps the two in sync) and pass it as the Agent tool's `model` parameter.

Applies to **every** Agent call this skill dispatches, including follow-up dispatches inside compound steps. The list below is illustrative, not exhaustive — when the prose says "every Agent call", it means every one:

- Tess (test author, step 2.7), plus any quality-gate or Tess/Devon-round re-dispatches (step 2.8, 2.85)
- Devon (adversarial validator, step 2.85)
- Ivan (implementor, step 3)
- Ivan re-dispatches on test failure (step 5.5)
- Code reviewer (step 5.7)
- Ivan fix-on-review re-dispatch (step 5.7)
- Ivan re-dispatches on full-suite regression (step 7)

If you add a new Agent call to this skill, pass `model` from `task.metadata.model` — no exceptions.

Accepted values: `"haiku"`, `"sonnet"`, `"opus"`.

**Legacy plans** (created before PRD 00025) have no `metadata.model`. Omit the `model` parameter — subagents inherit the session model. This preserves the pre-PRD-00025 behavior bit-for-bit.

The **Subagent Dispatch Budget** (50K bytes, 100K subagent-internal cap) applies regardless of tier. Haiku doesn't earn a smaller cap; opus doesn't earn a larger one.

## Attempt logging

At every task exit — success in step 6, abort in step 4 (timeout / context exceeded / error after debug), or via the Subagent Dispatch Budget overrun path — append one entry to `state.tasks[i].attempts[]`.

See `references/attempt-logging.md` for the entry schema, field semantics, and the atomic write procedure.

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
| non-empty array | **rework mode** | The listed task IDs read directly from `state.rework_task_ids`, in array order — **bypass step 1's status filter entirely**. Each ID is fetched via `TaskGet` regardless of current status (`pending` after Phase 6's reset, or `completed` if Phase 6's reset hasn't fired yet). Tasks NOT in the list are skipped entirely — no Tess/Ivan/Devon dispatch, no commits. |

**In rework mode, each task's status is set to `in_progress` at start** via `TaskUpdate` (overwriting whatever the prior status was — `pending` after Phase 6's reset, or `completed` on a defensive re-entry) and to `completed` at end — same lifecycle as a default-mode pass, so the dashboard reflects rework progress.

**In rework mode, the Attempt logging entry** (see "Attempt logging" above) sets `review_cycle` to the current `state.cycle` value (not null), `model` to the escalated tier read from `task.metadata.model` (set by `/run-autopilot` Phase 6), and `outcome` to `"completed"` or `"aborted"` as normal.

**`/work` does NOT modify `rework_task_ids` itself.** Clearing is `/run-autopilot` Phase 6's responsibility, after this `/work` invocation returns. **If `/work` aborts mid-rework** (context overrun, Subagent Dispatch Budget overrun, unrecoverable error), `rework_task_ids` survives in state — this is correct recovery behavior: the next `/run-autopilot` session resumes with the same rework batch and re-attempts the listed tasks at their already-escalated tier. Phase 6's clear runs only on the successful `/work` return.

Cross-reference: `run-autopilot/references/state-schema.md` `rework_task_ids` row; `run-autopilot/SKILL.md` Phase 6 (rework) tier-escalation rule.

### 2. Claim and start task

For the first available task:

1. Use `TaskUpdate` to set `status: in_progress` and claim ownership
2. **Sync state file** (see Dashboard State Sync)
3. **Reset the per-task context-cap marker** so the autopilot PostToolUse hook fires once for THIS task, not once per Work phase. The hook also self-clears when the in-progress task id in `state.json` differs from the id stored in the marker file (added cycle-5+1), but the explicit Bash clear here is a belt-and-braces backstop in case state.json's task-id snapshot lags the actual task switch. Run the shared walk-up helper in `--clear-cap` mode — it resolves symlinks, walks up to the autopilot dir, and removes `<autopilot_dir>/.cap-fired` internally:
   ```bash
   python3 ~/.claude/skills/run-autopilot/scripts/_walk_up.py --clear-cap
   ```
   No-op when no ancestor has the dir or the marker is already absent (first task of the phase); always exits 0. Use exactly this single-command form — no `d=$(...)` shell variable, so the permission matcher can resolve it.
4. Use `TaskGet` to read full task description

### 2.5. Load project context

Before dispatching to Codex/Gemini, load relevant context into the prompt:

- AGENTS.md / agent_docs/ architecture docs
- Active PRD from `dev/local/prds/wip/`
- Key module interfaces relevant to the task

1M context makes this practical — richer prompts produce better first-pass results.

**Ambiguity check (Think Before Coding):** Re-read the task description. If scope, data shape, target surface, or success criteria are unclear, stop and ask the user rather than picking silently. See `references/code-quality-principles.md` §1 and `references/code-quality-examples.md` §1 for what counts as a hidden assumption worth surfacing.

### 2.7. Write tests first (Tess - test author)

Dispatch a separate agent to write tests from requirements only. This agent must NOT receive implementation hints or architecture deep-dives - only what a user of the API would know.

**Tess runs as:** Claude Code subagent (Agent tool), not Codex/Gemini. It's a focused task that benefits from direct file access for reading test patterns.

**Skip for:** test-only, docs-only, or config-only tasks.

**Tess receives:**
- Task description and acceptance criteria
- The **exact file paths** the task touches and the **exact symbol names** to test, taken from the plan task — not "find the relevant file"
- Public interfaces/types relevant to the task
- Existing test patterns (one sample test file from the project)
- Test framework and conventions used

**Scope the agent explicitly.** Add to the prompt: "Read only the files listed above. If a file or symbol you need is not listed, stop and report it as a blocker — do not run broad `rg` sweeps to discover scope." Open-ended discovery is where subagents burn turns and stall.

**Tess does NOT receive:**
- Implementation strategy or architecture docs (loaded in step 2.5 for the main session and Ivan only)
- "How to build this" context
- Access to modify non-test files

See `references/test-author-prompt.md` for the full prompt template — it now embeds Simplicity/Think-Before-Coding/Surgical rules to prevent Tess from writing speculative tests or silently assuming input shape.

Tess prompts must satisfy the **Subagent Dispatch Budget** (see section above the Workflow): ≤ 50K bytes, abort-instruction line prepended.

### 2.8. Test quality gate (main session)

Before committing Tess's tests, review them in the main session against this checklist:

1. **Behavior names?** Each test name describes a behavior ("rejects empty email"), not an implementation detail ("calls validateEmail")
2. **Real assertions?** Assertions check outputs/effects, not mock internals
3. **Edge cases?** Empty, null, boundary, error, and concurrent cases covered where relevant
4. **No tautologies?** Tests don't just restate what the code obviously does

If any check fails, dispatch Tess again with specific feedback about what's weak. Max 2 quality gate retries.

**Total Tess budget:** max 5 dispatches across the entire test authoring phase (quality gate + adversarial rounds combined). If exhausted, flag weakness in task output and proceed. Don't block the pipeline forever.

### 2.85. Adversarial validation (Devon - devil's advocate)

Dispatch Devon to try to write a **wrong** implementation that passes all of Tess's tests. Devon's goal is to exploit weak tests.

**Devon runs as:** Claude Code subagent (Agent tool). It needs file write access and the project's test runner to actually execute its wrong implementation against the tests.

**Devon receives:**
- The test files from Tess
- Public interfaces/types (so its wrong implementation compiles)
- Access to the project's test runner

**Devon receives nothing else.** No task description, no acceptance criteria, no architecture docs.

**Devon's job:** Write an implementation that is clearly wrong (hardcoded values, ignored edge cases, shortcut if/else chains), run the tests against it, and report which tests it broke through.

**Outcomes:**

| Devon result | Action |
|----------------|--------|
| Cannot break tests (tests catch all exploits) | Tests are strong. Proceed to 2.9. |
| Breaks tests with wrong impl that passes | Send Devon's exploit back to Tess: "These tests can be passed by: {wrong impl}. Strengthen them." Then re-run Devon against strengthened tests. Max 2 Tess/Devon rounds. |
| 2 A/C rounds exhausted | Flag weakness in task output, proceed anyway. |

See `references/adversarial-test-prompt.md` for the full prompt template.

Devon prompts must satisfy the **Subagent Dispatch Budget**: ≤ 50K bytes, abort-instruction line prepended.

### 2.9. Commit tests

```bash
git add <test_files>
```
```bash
git commit -m "test(<scope>): add tests for <feature>"
```

Tests are committed separately before implementation. This makes the TDD boundary auditable in git history.

### 3. Implement against tests (Ivan - implementor)

Ivan's job: make the failing tests pass. Tests ARE the spec.

**Ivan receives:**
- Failing test file paths and their content
- Architecture context (AGENTS.md, interfaces, relevant modules)
- Existing code patterns to follow

**Ivan does NOT receive:**
- The task's acceptance criteria prose (tests replace this)
- Permission to modify test files

**Prompt must include:**

1. "Make all failing tests pass. Do NOT modify test files."
2. The code quality rules block from `references/code-quality-principles.md` (copy the "Prompt Snippet" section verbatim). These counter the anti-patterns LLMs produce by default: speculative abstractions, drive-by refactoring, style drift, silent assumptions. Concrete before/after examples are in `references/code-quality-examples.md` if the agent needs them.
3. The abort-instruction line from the **Subagent Dispatch Budget** section. Measure the assembled prompt before dispatching; if > 50K bytes, trim or abort the task with cause `subagent_prompt_overrun`.
4. The **exact file paths** Ivan may read and modify, plus: "Read only the files listed. If a file or symbol you need is not listed, stop and report it as a blocker — do not run broad `rg` sweeps to discover scope."

**If the task description is ambiguous** (multiple interpretations, unclear scope, unstated format/fields/location), stop before dispatching Ivan and surface the ambiguity to the user. See Example 1 in `references/code-quality-examples.md`. Do not dispatch with guessed-at requirements.

**Determine task domain** (see Tool Selection above), then:

**For Codex tasks:**

- Model: helper default (codex's own configured default, or `gpt-5.4` on the copilot fallback) unless the user specifies `-m`
- Permissions: `-a` (auto-approve tools) for code changes
- Prompt: `-f <file>` for non-interactive runs
- See `references/codex-integration.md` (TDD implementation mode)

**For Gemini tasks:**

- Permissions: `-a` (auto-approve edit tools) for code changes
- Prompt: `-f <file>` for non-interactive runs
- See `references/gemini-integration.md` (TDD implementation mode)

### 4. Handle result

| Result | Action |
|--------|--------|
| Success | Continue to step 5. The `completed` dispatch-log append for this dispatch is performed by the Subagent Watchdog (step 3) per `references/subagent-dispatch.md` "Dispatch-log append" — no separate append is needed in this row. |
| Timeout | Append attempt-log entry per the "Attempt logging" section (`outcome: "aborted"`, `cause: "timeout"`). Dispatch-log append (`outcome: "timeout"`) per `references/subagent-dispatch.md` "Dispatch-log append". Split task (see below), mark original as blocked. |
| Context exceeded | Append attempt-log entry per the "Attempt logging" section (`outcome: "aborted"`, `cause: "context_overrun"`). Dispatch-log append (`outcome: "context_overrun"`) per `references/subagent-dispatch.md` "Dispatch-log append". Split task, mark original as blocked. |
| Error | Invoke systematic-debugging if available (see below). On unrecoverable error, append attempt-log entry per the "Attempt logging" section (`outcome: "aborted"`, `cause: "error"`). Dispatch-log append (`outcome: "error"`) per `references/subagent-dispatch.md` "Dispatch-log append". Report to user. |
| Result lost / hung | The Agent result is empty, is `[Tool result missing due to internal error]`, or the Subagent Watchdog killed a hung agent. Dispatch-log append (`outcome: "hung"`) per `references/subagent-dispatch.md` "Dispatch-log append". This is an infrastructure failure, not real work — the agent produced nothing usable. Apply the **infrastructure-failure circuit breaker** (step 4.2). |

### 4.2. Infrastructure-failure circuit breaker

A lost/empty Agent result or a watchdog-killed hang is an infrastructure failure, not a content failure. Do **not** silently re-dispatch in a loop — two back-to-back infrastructure failures on the same task was the observed cause of a multi-hour stall.

1. Check the working tree (`git status --short`). A crashed agent may have left partial, uncommitted, **unverified** changes. Note them in the task output; do not commit them blind and do not assume they compile.
2. Re-dispatch the **same** task at most **once**. Track infrastructure re-dispatches per task — this cap is separate from the test-failure retry cap (step 5.5) and the review-cycle cap (step 5.7).
3. On the **second** infrastructure failure for the same task: stop. Append an attempt-log entry (`outcome: "aborted"`, `cause: "subagent_infra_failure"`), set `state.stall_reason` to `{"stalled": "subagent_infra_failure", "task": "<id>"}`. Dispatch-log append (`outcome: "infra_failure"`) per `references/subagent-dispatch.md` "Dispatch-log append". Escalate to the user. Do **not** advance to the next task.

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

Run **only** the specific tests Tess wrote in step 2.7. Do NOT run the full project test suite, smoke tests, integration tests, or lint here — those run once at the end of the phase (step 7).

- Target the narrowest scope that covers the new tests:
  - Rust: `cargo test -p <crate> --test <test_file>` or `cargo test -p <crate> <module::test_name>`
  - Python: `pytest path/to/test_file.py::test_name`
  - JS/TS: `vitest run path/to/test_file` or `jest path/to/test_file`
- If tests fail, dispatch Ivan again with the failure output. Never dispatch Tess to weaken tests.
- **Retry prompts must re-include the code-quality rules block** from `references/code-quality-principles.md`, plus an explicit SURGICAL instruction: "Fix only what the failing test output points to. Do not refactor passing code, adjust unrelated files, or change style."
- Max 2 implementation retries before escalating to the user.
- If `superpowers:verification-before-completion` is available, invoke it for additional verification beyond tests — but keep its scope to this task's files, not the full workspace.

**Do not run here:** `cargo test --workspace`, `cargo clippy --workspace`, `./tests/smoke.sh`, `./tests/integration.sh`, `cargo test-full`, or any equivalent full-suite command. These are batched into step 7.

### 5.7. Per-task code review (if superpowers available)

If `superpowers:requesting-code-review` is in the available skills list, dispatch a code review after commit and verification:

1. Get SHAs: `BASE_SHA` = commit before this task, `HEAD_SHA` = HEAD after commit
2. Dispatch code-reviewer subagent with task subject, description, and SHA range. Append the **Simplification mandate** below to the reviewer's prompt verbatim.
3. Handle result:
   - **Critical/Important issues**: if `superpowers:receiving-code-review` is available, invoke it to evaluate feedback before acting - verify suggestions technically, push back if wrong. Then fix confirmed issues (dispatch Ivan with the code-quality rules block from `references/code-quality-principles.md` plus: "Apply ONLY the specific fixes listed below. Do not refactor surrounding code or address unrelated issues you notice."), re-commit, re-verify (step 5.5), re-review. Max 3 review cycles, then proceed with warning.
   - **Minor issues only or approved**: note minors, proceed to step 6.
   - **Reviewer failed/timed out**: log warning, proceed - Phase 4's PRD-level review catches remaining issues.

**Simplification mandate** — append verbatim to the code-reviewer prompt:

> Beyond bugs, actively hunt for simplification in the diff under review. For
> every added or changed file, ask "what would make this simpler to read
> without changing what it does?" and flag concrete behavior-preserving
> opportunities to: reduce complexity (needless indirection, dead branches,
> single-caller abstractions, nesting deeper than 4 levels, functions over 50
> lines); eliminate redundancy (logic duplicated within the diff or against
> existing code, a helper that reimplements a stdlib or existing utility);
> improve naming (names that state intent, no opaque abbreviations); and
> remove dead code. Follow CLAUDE.md / AGENTS.md conventions and the
> surrounding code's style.
>
> Classify a concrete behavior-preserving simplification as **Important**, not
> Minor — Minor findings are not fixed in this loop. Give file:line, the
> current shape, and the simpler replacement.
>
> Do not over-simplify: never propose a change that trades clarity for
> brevity, drops error handling, collapses a deliberate boundary, or removes a
> documented invariant. Simpler means easier to read and maintain, not shorter
> at any cost. If a change would alter behavior, it is out of scope — do not
> flag it.

Skip for documentation-only or configuration-only tasks.

### 6. Mark complete and sync

1. Use `TaskUpdate` to set `status: completed`
2. **Append an entry to `state.tasks[i].attempts[]`** per the "Attempt logging" section: `outcome: "completed"`, `model` from `task.metadata.model`, `cause: null`, `review_cycle: null` on a Phase-3 first pass or the current `state.cycle` on a rework pass.
3. **Sync state file** (see Dashboard State Sync) — mandatory
4. Proceed to step 6.5 (task-boundary handoff check) — it routes to the next task, a clean handoff, or final verification.

### 6.5. Task-boundary handoff check

After step 6, decide whether to finish the remaining tasks in this session or hand them to a fresh one.

The autopilot context-cap hook (`autopilot_context_cap_hook.py`) writes a `.handoff-requested` marker into the autopilot dir once this session's context crosses the **soft** threshold — below the **hard** cap that triggers the destructive abort+replan. Handing off at a task boundary, where every task through step 6 is committed and `state.tasks` is synced, is lossless: the next `/run-autopilot` session re-enters Phase 3 and `/work` resumes with the remaining pending tasks (Phase 3's skip rule only skips when *no* tasks are pending). This keeps a multi-task Work phase from ballooning into the hard cap.

1. **If no pending tasks remain**, skip this step — proceed to step 7. Final verification runs in whichever session finishes the last task.
2. Resolve the autopilot dir and check for the marker:
   ```bash
   python3 ~/.claude/skills/run-autopilot/scripts/_walk_up.py --bash
   ```
   It prints the absolute autopilot dir. Read `<dir>/.handoff-requested`. **If it is absent**, return to step 1 for the next task — no handoff.
3. **If `.handoff-requested` is present:**
   a. Confirm the working tree is clean (`git status --short` empty). Every task through step 6 commits its tests (step 2.9) and implementation (step 5), so it should be. If it is NOT clean, do not hand off — investigate and commit or resolve the uncommitted work first.
   b. Remove both `<dir>/.handoff-requested` and `<dir>/.cap-fired`, inlining the absolute paths from step 2 (no shell variable, so the permission matcher resolves the command). The fresh session re-evaluates its budget from a clean slate.
   c. Print the handoff banner:
      ```
      ── WORK ── handoff at task boundary ────────────────────────────
      ── {completed} tasks done, {pending} pending — context near soft cap
      ── fresh session resumes the remaining tasks ───────────────────
      ```
   d. Check `$_AUTOPILOT_LOOP` (`echo "${_AUTOPILOT_LOOP-}"`). If set, write `next` to the autopilot `signal` file at its absolute path, then STOP. If unset, STOP without the signal write — the user re-invokes `/run-autopilot`, which resumes via `state.json`.

   **Do NOT return to step 1, and do NOT run step 7.** `phases_completed` stays without `"work"` (this session did not finish the phase), so `/run-autopilot` re-enters Phase 3, hydrates TaskList from `state.tasks`, and re-invokes `/work` for the pending tasks.

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
3. Dispatch Ivan with the failure output to fix it. Include the code-quality rules block from `references/code-quality-principles.md` and add: "Fix only the regression identified below. Do not touch unrelated files or refactor adjacent code." Do NOT relax the failing test.
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

- `references/test-author-prompt.md` - Test author (Tess) prompt template
- `references/adversarial-test-prompt.md` - Adversarial validator (Devon) prompt template
- `references/codex-integration.md` - Codex prompt templates and patterns
- `references/gemini-integration.md` - Gemini prompt templates and patterns
- `references/code-quality-principles.md` - Think/Simplicity/Surgical/Goal-driven rules to inject into Ivan prompts
- `references/code-quality-examples.md` - Before/after examples of the anti-patterns those rules prevent
- `references/subagent-dispatch.md` - Dispatch Budget + Watchdog: how to safely make an Agent call
- `references/attempt-logging.md` - `state.tasks[].attempts[]` entry schema and write procedure
