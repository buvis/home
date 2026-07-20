---
name: work
description: Use when executing already-planned tasks one at a time, dispatching the implementor and committing after each. Triggers on "work on tasks", "implement tasks", "start working", "execute the plan", "do the work".
---

# Work Through Tasks

Implement pending tasks one-by-one, committing after each completion.

## Dependencies

- Personal skills: `run-autopilot` - this skill is a phase inside that loop and
  shares its state contract, `dev/local/autopilot/state.json` (see run-autopilot's
  state-schema and phase-review references).
- Files read from other skill dirs:
  - `~/.claude/skills/run-autopilot/scripts/statectl.py` - the sole `state.json`
    mutator; `/work` invokes it to append attempt entries and sync task status
    (never the Edit/Write tools)
  - `~/.claude/skills/run-autopilot/scripts/_walk_up.py` - run at every task
    start and at the handoff check
  - `~/.claude/skills/run-autopilot/prompts/de-sloppify.md` - its
    `## What to remove` section is inlined into the step-5.6 deslop dispatch
- CLIs: `git`, `python3`
- Optional (explicit fallback exists): `use-gemini` skill (UI tasks), `use-qwen`
  skill, `use-sonnet` skill (its `scripts/sonnet-run.sh` drives the step-5.7
  reviewer lane)

## CRITICAL: Never Ask the User to Run Commands

This skill runs inside an **automated autopilot loop**. The user is not watching. Do not ask the user to run tests, commands, or do anything manually. The only valid reasons to surface output to the user are:

1. A genuinely irreversible action that requires explicit confirmation (e.g. force-pushing a shared branch).
2. More than two consecutive failed attempts at the same automated step with no remaining fallback.

**When test verification is blocked** (e.g. all cargo processes were backgrounded and the build lock was contended): if the code compiles cleanly and the logic change is correct by inspection, commit and proceed — and record `verification: skipped:<cause>` in the task's attempt entry and the phase report (fail loud; a skipped check must never read as a passed one). The full-suite verification run at the end of the phase will catch regressions. Do not stop and ask the user to run anything.

**When cargo commands get backgrounded by the session**: the Bash tool may background long-running commands regardless of the `run_in_background` flag. Wait for background completions via Monitor (up to 20 minutes for full test suites). Never launch a second cargo command while one is still running — they contend on the build lock and jam the shell. If a Monitor times out, read the output file directly; if the file is empty the build lock was still held, wait longer before retrying.

## CRITICAL: One Task at a Time

**STOP.** Before dispatching ANY Agent or helper-script call, verify you are sending it EXACTLY ONE task. Batching tasks into one Agent call leaves `state.tasks` (and every dashboard reading state.json) stale for the entire duration and collapses per-task attempt logging.

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

**Per-task verification runs only the tests Tess wrote in step 2.7, not the full project suite.** The full suite runs once at the end (why: `references/design-rationale.md` § narrow verification).

If you find yourself writing an Agent prompt that mentions multiple tasks, STOP — you are about to violate this rule.

See **Subagent Dispatch Budget and Watchdog** below — every Agent dispatch must satisfy both.

## Subagent Dispatch Budget and Watchdog

**Budget:** every prompt passed to the Agent tool (Tess, Ivan, or Devon) must be **≤ 50 000 bytes**, with the abort-instruction line prepended. Measure before every dispatch; trim the lowest-priority context once, and if still oversized abort the task with cause `subagent_prompt_overrun`.

**Watchdog:** every Agent dispatch must be wrapped in a watchdog: dispatch with `run_in_background: true`, wait with `Monitor` (15-minute timeout), and on timeout `TaskStop` the agent and handle it as the **Result lost / hung** row of step 4's table (which routes to the infrastructure-failure circuit breaker, step 4.2). A foreground `Agent` call that hangs blocks this session indefinitely — never dispatch one unwatched.

See `references/subagent-dispatch.md` for the measurement procedure, the verbatim abort-instruction line, the abort-handoff steps, helper-script (`use-codex`/`use-gemini`/`use-qwen`) handling, and the three distinct deadlines (15 min / 10 min × 2 / 20 min, by mechanism). Read it before your first Agent dispatch in a session. Elsewhere in this file, "must satisfy the **Subagent Dispatch Budget**" and "**Subagent Watchdog**" mean exactly this section — the numbers are not restated at call sites.

## Per-task model dispatch

Before any Agent call for a task, read `task.metadata.model` (or equivalently `state.tasks[i].model` — `/run-autopilot` keeps the two in sync) and pass it as the Agent tool's `model` parameter.

Applies to **every** Agent call this skill dispatches, including follow-up dispatches inside compound steps: Tess and her quality-gate/adversarial-round re-dispatches (steps 2.7-2.85), Devon (2.85), and Ivan and every Ivan re-dispatch (3, 5.5, 5.7 fix, 7 regression fix). (The step-5.7 reviewer is a fixed-model helper-script dispatch via `use-sonnet`, not an Agent call — the `model` parameter does not apply to it.) If you add a new Agent call to this skill, pass `model` from `task.metadata.model` — no exceptions.

**Qwen one-shot-budget carve-out (step 5.5 only).** When the failing attempt's implementor was qwen (helper-script `use-qwen`, NOT an Agent dispatch — qwen never used `task.metadata.model`), every step-5.5 re-dispatch for that task targets **Claude Sonnet** regardless of `task.metadata.model` — never qwen again. This is the one-shot qwen attempt budget — the ladder's `qwen -> sonnet` capability edge (`run-autopilot/references/model-ladder.md` § Capability ladders and § Per-rung budgets; why: `references/design-rationale.md` § one shot): qwen gets exactly 1 dispatch, a qwen gate failure escalates to Sonnet immediately with zero qwen retries, and step 5.5's Claude-rung budget then runs entirely on Claude Sonnet — see step 5.5 below for the full diagnose/repair/escalate flow this now drives. Applies unchanged under `_AUTOPILOT_ESCALATION=legacy` (model-ladder.md § Kill-switches). All non-step-5.5 Agent calls continue to obey `task.metadata.model` with no exceptions.

Accepted values: `"haiku"`, `"sonnet"`, `"opus"`.

**Legacy plans** (created before `metadata.model` existed) have no model field. Omit the `model` parameter — subagents inherit the session model. This preserves the legacy behavior bit-for-bit.

The **Subagent Dispatch Budget** applies regardless of tier. Haiku doesn't earn a smaller cap; opus doesn't earn a larger one.

## Assumptions footer

Every Tess and Ivan dispatch prompt - initial and retry, regardless of mechanism (Agent, `use-gemini`, `use-qwen`) - must end with this instruction verbatim:

> End your report with `ASSUMPTIONS:` - one line per assumption you made where the task, tests, or listed files were silent (guessed interface, data shape, resolved ambiguity, unstated behavior). Write `ASSUMPTIONS: none` if you made none.

**Ivan** dispatch prompts (initial and retry, all mechanisms) must additionally end with this instruction verbatim:

> Also end your report with `FILES_TOUCHED:` - one line per file you created or modified, path relative to the repo root. Write `FILES_TOUCHED: none` if you changed no files.

Step 5 stages exactly the reported paths - an unreported file stays uncommitted and is surfaced by step 5's foreign-path rule, so an implementor that omits the footer fails loudly, not silently.

Collect the returned lines: step 6 appends non-`none` entries to `dev/local/assumptions.md` under a `## <task-id>: <task subject>` heading (Write/Edit tool, never shell redirects). On the first completed task of a full-plan pass, replace the file instead of appending - the ledger is per-plan. Step 7's phase report includes the ledger so the user and the review phase can examine what the implementors guessed in a 30-second read.

## Dispatch prologue

Every Tess and Ivan dispatch prompt - initial and retry, regardless of mechanism (Agent, `use-gemini`, `use-qwen`) - must also contain this line verbatim (transcript mining 2026-07-14: ~150 hook-blocked coreutils calls and ~60 Edit-before-Read failures across 90 sampled loop sessions):

> Read every file before your first Edit to it. Never call bash `head`, `tail`, `cat`, `grep`, or `find` - a hook blocks them. Use the Read tool (offset/limit), `rg`, or `rg --files` instead.

## Attempt logging

At every task exit — success in step 6, abort in step 4 (timeout / context exceeded / error after debug), or via the Subagent Dispatch Budget overrun path — append one entry to `state.tasks[i].attempts[]`. Each entry carries:

- **`implementor`** — `"claude"`, `"gemini"`, or `"qwen"`, reflecting what actually dispatched, NOT what the step-3 routing table initially picked (a qwen pick that fell back to Claude on preflight failure records `"claude"`).
- **`preflight_outcome`** — from the step-3 preflight probe. Always written explicitly — never omit the key. Qwen-eligible attempts record one of `"healthy"`, `"pi_missing"`, `"endpoint_unreachable"`, `"model_id_missing"`, `"completion_failed"`; non-qwen-eligible attempts record the literal JSON `null`.
- **`pipeline`** — the tier-gated depth this attempt ran, keyed on `task.metadata.model`: `haiku` → `"minimal"` (Tess + Ivan), `sonnet` → `"lean"` (+ step-5.7 reviewer), `opus` → `"full"` (+ Devon at step 2.85); absent/legacy is treated as `sonnet` → `"lean"`. Written at every task exit; a Phase-6 escalation to `opus` records `"full"`.

See `references/attempt-logging.md` for the full entry schema, field semantics, and the atomic write procedure.

## Implementor Selection

The **deterministic routing table in step 3** is the single source of truth for picking each task's implementor (Gemini / local qwen / Claude at tier). Do not route from memory or from this section.

**Gemini-first tasks** — the UI definition the routing table references. A task is UI/visual when it involves: color palettes/theming/contrast, layouts (page structure, spacing, visual hierarchy), UI components (buttons, forms, cards), typography, animations/transitions, responsive design, or any user-facing surface (web pages, GUI, dashboards).

For visual tasks, Gemini can also challenge the spec before implementation — see `references/gemini-integration.md` § Design Authority (trust its feedback on visual matters).

Codex (`use-codex`) is **not** an implementor. It appears only in the review path — see `references/codex-integration.md`.

## Dashboard State Sync

The dashboard (tracon; `render_stream.py` fallback) reads `dev/local/autopilot/state.json` directly. Keep `state.tasks[].status` accurate (updated in step 2 at task start and in step 6 at task end) and recompute `tasks_total`/`tasks_completed` alongside it — the pidash sync hooks are retired (PRD 00063) — and the dashboard reflects progress in real time. Apply every such change with `statectl` (`python3 ~/.claude/skills/run-autopilot/scripts/statectl.py <state.json> set|append|del ...`), not the editing tools — the sole-writer rule in `run-autopilot` SKILL.md § State Management, which also documents the one human fallback.

## Workflow

### 1. Get pending tasks

Use `TaskList` tool to see all tasks. Filter for:

- Status: `pending`
- No blockers (empty `blockedBy`)
- No owner assigned

### 1.5. Rework-mode task filter

Read `state.rework_task_ids` from `dev/local/autopilot/state.json` (walk up from cwd to find the autopilot dir, same pattern as the cap-marker reset in step 2). Two modes:

| `rework_task_ids` | Mode | Iteration source |
|-------------------|------|------------------|
| absent or `[]` | **default (full-plan)** | The pending-and-unblocked subset from step 1's `TaskList` filter, in TaskList order. This is the Phase 3 first-pass behavior. |
| non-empty array | **rework mode** | The listed task IDs read directly from `state.rework_task_ids`, in array order — **bypass step 1's status filter entirely**. Each ID is fetched via `TaskGet` regardless of current status (`pending` after Phase 6's reset, or `completed` if Phase 6's reset hasn't fired yet). Tasks NOT in the list are skipped entirely — no Tess/Ivan/Devon dispatch, no commits. |

**In rework mode, each task's status is set to `in_progress` at start** via `TaskUpdate` (overwriting whatever the prior status was — `pending` after Phase 6's reset, or `completed` on a defensive re-entry) and to `completed` at end — same lifecycle as a default-mode pass, so the dashboard reflects rework progress.

**In rework mode, the Attempt logging entry** (see "Attempt logging" above) sets `review_cycle` to the current `state.cycle` value (not null), `model` to the escalated tier read from `task.metadata.model` (set by `/run-autopilot` Phase 6), and `outcome` to `"completed"` or `"aborted"` as normal. It also **copies `task.metadata.escalation_reason` and `task.metadata.escalated_from` onto the entry when present** — Phase 6 sets them (`escalation_reason: "review_flag"`, `escalated_from: <prev_tier>`) on the review-flag escalation path, and this copy is how `review_flag` actually reaches `attempts[]` (the PRD metric "every escalation records reason in attempts[]" depends on it). Absent (a non-escalated rework re-dispatch) → omit both.

**`/work` does NOT modify `rework_task_ids` itself.** Clearing is `/run-autopilot` Phase 6's responsibility, after this `/work` invocation returns. **If `/work` aborts mid-rework** (context overrun, Subagent Dispatch Budget overrun, unrecoverable error), `rework_task_ids` survives in state — this is correct recovery behavior: the next `/run-autopilot` session resumes with the same rework batch and re-attempts the listed tasks at their already-escalated tier. Phase 6's clear runs only on the successful `/work` return.

Cross-reference: `run-autopilot/references/state-schema.md` `rework_task_ids` row; `run-autopilot/references/phase-review.md` Phase 6 (rework) tier-escalation rule.

### 2. Claim and start task

For the first available task:

1. Use `TaskUpdate` to set `status: in_progress` and claim ownership
2. **Sync state file** (see Dashboard State Sync)
3. **Reset the per-task context-cap marker** so the autopilot PostToolUse hook fires once for THIS task, not once per Work phase. The hook also self-clears when the in-progress task id in `state.json` differs from the id stored in the marker file, but the explicit clear here is a belt-and-braces backstop in case state.json's task-id snapshot lags the actual task switch. Run the shared walk-up helper in `--clear-cap` mode — it resolves symlinks, walks up to the autopilot dir, and removes `<autopilot_dir>/.cap-fired` internally:
   ```bash
   python3 ~/.claude/skills/run-autopilot/scripts/_walk_up.py --clear-cap
   ```
   No-op when no ancestor has the dir or the marker is already absent (first task of the phase); always exits 0. Use exactly this single-command form — no `d=$(...)` shell variable, so the permission matcher can resolve it.
4. Use `TaskGet` to read full task description

### 2.5. Load project context

Before dispatching the implementor, load relevant context into the prompt:

- AGENTS.md / agent_docs/ architecture docs
- Active PRD from `dev/local/prds/wip/`
- Key module interfaces relevant to the task

1M context makes this practical — richer prompts produce better first-pass results.

**Ambiguity check (Think Before Coding):** Re-read the task description. If scope, data shape, target surface, or success criteria are unclear, stop and ask the user rather than picking silently. See `references/code-quality-principles.md` §1 and `references/code-quality-examples.md` §1 for what counts as a hidden assumption worth surfacing.

**Premise check:** If the task description carries a `Premise:` line, verify each stated fact against the current tree (`ls`, `rg`, `git ls-files` as fits) BEFORE dispatching any implementor — cheap read-only probes only, never a mutation. If any fact no longer holds, do not dispatch. Interactively: stop and report which fact failed; the task stays in_progress for the user or the decision gate. In loop mode (post-00017): a failed premise is never assumed through — it takes the loop-mode stall path (`run-autopilot/references/recovery.md` "Loop-mode stall procedure"), unlike ambiguities, which 00017 resolves by simplest safe assumption. If a probe command itself errors, treat the premise as unverified and surface it as a blocker — never proceed on an unknown. Tasks without a `Premise:` line skip this check entirely (zero behavior change for legacy plans).

### 2.7. Write tests first (Tess - test author)

Dispatch a separate agent to write tests from requirements only. This agent must NOT receive implementation hints or architecture deep-dives - only what a user of the API would know.

**Tess runs as:** Claude Code subagent (Agent tool), not a helper-script implementor (`use-gemini`, `use-qwen`). It's a focused task that benefits from direct file access for reading test patterns.

**Skip for:** test-only, docs-only, or config-only tasks.

**Tess receives:**
- Task description and acceptance criteria
- The **exact file paths** the task touches and the **exact symbol names** to test, taken from the plan task — not "find the relevant file"
- Public interfaces/types relevant to the task
- Existing test patterns (one sample test file from the project)
- Test framework and conventions used

**Scope the agent explicitly.** Add to the prompt: "Read only the files listed above. If a file or symbol you need is not listed, stop and report it as a blocker — do not run broad `rg` sweeps to discover scope." Open-ended discovery is where subagents burn turns and stall.

Tess prompts also end with the **Assumptions footer** instruction (see section above) - tests are the spec in this pipeline, so a contract Tess guessed silently becomes the contract.

**Tess does NOT receive:**
- Implementation strategy or architecture docs (loaded in step 2.5 for the main session and Ivan only)
- "How to build this" context
- Access to modify non-test files

See `references/test-author-prompt.md` for the full prompt template — it embeds Simplicity/Think-Before-Coding/Surgical rules to prevent Tess from writing speculative tests or silently assuming input shape.

Tess prompts must satisfy the **Subagent Dispatch Budget**.

### 2.8. Test quality gate (main session)

Before committing Tess's tests, review them in the main session against this checklist:

1. **Behavior names?** Each test name describes a behavior ("rejects empty email"), not an implementation detail ("calls validateEmail")
2. **Real assertions?** Assertions check outputs/effects, not mock internals
3. **Edge cases?** Empty, null, boundary, error, and concurrent cases covered where relevant
4. **No tautologies?** Tests don't just restate what the code obviously does

If any check fails, dispatch Tess again with specific feedback about what's weak. Max 2 quality gate retries.

**Total Tess budget:** max 5 dispatches across the entire test authoring phase (quality gate + adversarial rounds combined). If exhausted, flag weakness in task output and proceed. Don't block the pipeline forever.

### 2.85. Adversarial validation (Devon - devil's advocate)

**Tier gate — Devon is the opus-only dispatch.** Read `task.metadata.model`:

| `task.metadata.model` | Devon (step 2.85) |
|-----------------------|-------------------|
| `opus` | dispatch Devon (below) |
| anything else — `haiku`, `sonnet`, absent/legacy or unknown (both treated as `sonnet`) | skip Devon, proceed to step 2.9 |

The step-2.8 test quality gate is **unchanged** and runs for every tier — only this Agent dispatch is conditional. A Devon dispatch obeys the **Per-task model dispatch** rule (passes `model: opus`). Escalation interplay is automatic: when the review gate escalates a review-flagged task to `opus`, the rework attempt regains Devon with no extra mechanism. (Why tier-gated: `references/design-rationale.md` § tier-gated pipeline.)

Dispatch Devon to try to write a **wrong** implementation that passes all of Tess's tests. Devon's goal is to exploit weak tests.

**Devon runs as:** Claude Code subagent (Agent tool) — it needs file write access and the project's test runner to execute its wrong implementation against the tests. **Devon receives only:** the test files from Tess, public interfaces/types (so its wrong implementation compiles), and test-runner access. No task description, no acceptance criteria, no architecture docs.

**Devon's job:** Write an implementation that is clearly wrong (hardcoded values, ignored edge cases, shortcut if/else chains), run the tests against it, and report which tests it broke through.

**Outcomes:**

| Devon result | Action |
|----------------|--------|
| Cannot break tests (tests catch all exploits) | Tests are strong. Proceed to 2.9. |
| Breaks tests with wrong impl that passes | Send Devon's exploit back to Tess: "These tests can be passed by: {wrong impl}. Strengthen them." Then re-run Devon against strengthened tests. Max 2 Tess/Devon rounds. |
| 2 A/C rounds exhausted | Flag weakness in task output, proceed anyway. |

See `references/adversarial-test-prompt.md` for the full prompt template. Devon prompts must satisfy the **Subagent Dispatch Budget**.

### 2.9. Commit tests

```bash
git add <test_files>
```
```bash
git commit -m "test(<scope>): add tests for <feature>"
```

Tests are committed separately before implementation, making the TDD boundary auditable in git history.

**Capture this task's test-commit SHA** immediately — step 5.5's ESCALATE reset resets to exactly this commit (never a prior task's):
```bash
git rev-parse HEAD
```
Hold the returned SHA in-session as `<test_commit_sha>` for this task; step 5.5's ESCALATE path reads it.

### 2.95. Red-check — watch the tests fail

Run the newly committed tests once, before any Ivan dispatch, at the narrowest scope (the same commands step 5.5 uses). Red is the point: a failure proves the tests bind behavior that does not exist yet (rules/testing.md fail-first). Implicitly skipped when step 2.7 was skipped (no new tests).

| Outcome | Action |
|---------|--------|
| ≥1 test fails | Expected red. Proceed to step 3. |
| All pass | Accidentally-green tests bind nothing. Send the run output back to Tess ("these tests pass with no implementation — strengthen them to fail against the current tree"); this consumes the **Total Tess budget** (step 2.8; on exhaustion flag and proceed per that step). Commit the strengthened tests (`test(<scope>): strengthen tests for <feature>`), re-capture `<test_commit_sha>` per step 2.9, and re-run this check. |
| Tests cannot run standalone (they import the not-yet-built feature, or the runner cannot execute them) | Record `red_check: skipped:<cause>` in the task's attempt entry and the phase report (fail loud; a skipped check must never read as a passed one), then proceed to step 3. |

### 3. Implement against tests (Ivan - implementor)

Ivan's job: make the failing tests pass. Tests ARE the spec.

**Ivan receives:** failing test file paths and their content, architecture context (AGENTS.md, interfaces, relevant modules), and existing code patterns to follow. **Ivan does NOT receive:** the task's acceptance criteria prose (tests replace this) or permission to modify test files.

**Prompt must include:**

1. "Make all failing tests pass. Do NOT modify test files."
2. The code quality rules block from `references/code-quality-principles.md` (copy the "Prompt Snippet" section verbatim). These counter the anti-patterns LLMs produce by default: speculative abstractions, drive-by refactoring, style drift, silent assumptions. Concrete before/after examples are in `references/code-quality-examples.md` if the agent needs them.
3. The abort-instruction line, with the assembled prompt measured against the **Subagent Dispatch Budget** before dispatching.
4. The **exact file paths** Ivan may read and modify, plus: "Read only the files listed. If a file or symbol you need is not listed, stop and report it as a blocker — do not run broad `rg` sweeps to discover scope."
5. The assumptions-footer instruction from the **Assumptions footer** section above, verbatim.

**If the task description is ambiguous** (multiple interpretations, unclear scope, unstated format/fields/location), stop before dispatching Ivan and surface the ambiguity to the user. See Example 1 in `references/code-quality-examples.md`. Do not dispatch with guessed-at requirements.

**Deterministic routing table.** Pick the implementor by reading the claimed task's tier (`task.metadata.model`) and qwen-eligibility flag (`task.metadata.qwen_eligible`), then cross-referencing against the "Gemini-first tasks" UI definition in **Implementor Selection** above. No re-judging here — `qwen_eligible` is computed upstream by `/plan-tasks` and already encodes backend (not UI) + `haiku`/`sonnet` tier + `<=3`-files + no public-contract edit (exported API signature, schema, wire format, hook registration shape); ineligible tasks carry `metadata.qwen_excluded_reason` (`ui`/`tier`/`files`/`contract`) for the batch-report telemetry. If the field is absent (legacy plans), treat it as `false`.

Apply the rows in this order — the first match wins (in practice `qwen_eligible == true` already excludes UI and `opus`, so the order resolves any apparent overlap deterministically):

| # | Task class | Implementor | Reference |
|---|------------|-------------|-----------|
| 1 | UI / visual task (per "Gemini-first tasks") | Gemini if available, else Claude at `task.metadata.model` | `references/gemini-integration.md` |
| 2 | Backend `opus` tier | Claude Opus (Agent dispatch) | — |
| 3 | Backend, `qwen_eligible == true`, `_AUTOPILOT_ESCALATION != "legacy"`, qwen capability breaker tripped (`qwen_breaker.tripped == true`, after the batch-scope check below) | Claude at the task's ORIGINAL tier (`haiku` → Haiku, `sonnet` → Sonnet) — **skip the preflight probe**, stamp the eventual attempt `breaker_skipped:true` | qwen capability breaker (below) |
| 4 | Backend, `qwen_eligible == true`, row 3 did not fire, healthy qwen infra | Local qwen via `use-qwen` helper | `references/qwen-integration.md` |
| 5 | Backend, `qwen_eligible == true`, row 3 did not fire, **unhealthy** qwen infra | Claude at the task's original tier (`haiku` → Haiku, `sonnet` → Sonnet) | `references/qwen-integration.md` (Preflight) |
| 6 | Backend, `qwen_eligible == false` (or absent) | Claude at the task's tier (e.g. a `>=4`-file `sonnet` task → Claude Sonnet) | — |

qwen never sees `opus`-tier or UI tasks — `task.metadata.qwen_eligible` is already `false` for those upstream.

**qwen capability breaker (routing-time consult, row 3).** Guarded by `_AUTOPILOT_ESCALATION != "legacy"` (`model-ladder.md` § Kill-switches) — under `legacy` the breaker is fully off, row 3 never fires, and rows 4-5 behave exactly as today's rows 3-4.

- **Batch-scope check, before any breaker read or write:** compute the effective batch id `(state.batch.id // "no-batch")` and compare to `qwen_breaker.batch_id`. Mismatch or field absent → new batch: reset `qwen_breaker = {tripped:false, after_task:null, failed_tasks:[], batch_id:<effective id>}` and `qwen_gate_failures_consecutive = 0`, then proceed. Match → preserve the breaker state. This is a lazy per-batch reset — no run-autopilot Phase 0/9 edit needed.
- **Consult:** row 3 fires when the table would otherwise take row 4 (qwen-eligible) AND `qwen_breaker.tripped == true`. This is the routing-time order (`model-ladder.md` § Ordering): breaker consult happens BEFORE the preflight probe, so a tripped breaker skips the probe entirely. A breaker-skipped attempt's `preflight_outcome` records `null` (the probe never ran).
- **Counter/latch update** happens later, at the step-5.5 gate — see that section.

**Re-evaluate the routing table for EVERY claimed task — no session-level memory.** The table is per-task, and so is the one-shot qwen budget: a qwen attempt on task A (success OR failure) never excludes qwen for task B. Do not generalize a fallback ("qwen was slow on the last task, route the rest to Claude") — that decision belongs to the table and the preflight, not to session memory (observed failure: `references/design-rationale.md` § no session memory). Self-check before each Ivan dispatch: if `task.metadata.qwen_eligible == true` and you are about to dispatch Claude, the attempt log MUST carry a non-`"healthy"` `preflight_outcome` justifying the fallback — if it would read `null` or `"healthy"`, you skipped the table; run it now. **Exception:** the qwen capability breaker (row 3 above) is the one deliberate, state-tracked override — it reroutes off `qwen_breaker.tripped` (durable, batch-scoped state), not ad-hoc session judgment; the self-check above only applies when row 3 did not fire (a breaker-skipped attempt's `null` `preflight_outcome` is expected, not a skipped table).

**Gemini availability check.** "Gemini if available" means the `use-gemini` helper resolves AND can run a no-op probe. Concretely: `~/.claude/skills/use-gemini/scripts/gemini-run.sh` is executable AND `mise which gemini` (or `command -v gemini`) exits 0. If either fails, fall back to Claude at `task.metadata.model` for that UI task. Treat a runtime helper-script failure (non-zero exit, no output) the same way: record the failure and re-dispatch the task to Claude at the task's tier. Cross-reference: `references/gemini-integration.md`.

`use-qwen` and `use-gemini` are Bash helper-script dispatches; Claude implementor passes are Agent dispatches at the task's tier. Both must satisfy the **Subagent Dispatch Budget** and the **Subagent Watchdog**.

**Qwen infra preflight.** When (and only when) the routing table picks qwen, run the four-check probe defined in `references/qwen-integration.md` (Preflight section) BEFORE dispatching the qwen helper — it keeps an unhealthy backend from silently hanging, returning garbage, or accepting the dispatch only to fail the worker spawn. `"healthy"` → proceed with the qwen dispatch; any other verdict (`"pi_missing"` / `"endpoint_unreachable"` / `"model_id_missing"` / `"completion_failed"`) → fall back to Claude at the task's original tier, byte-for-byte identical to a normal Claude dispatch apart from the recorded `preflight_outcome`. Record the outcome for the attempt-log entry; the dispatch decision determines `implementor`. Preflight does NOT run on Claude or Gemini dispatches.

### 4. Handle result

| Result | Action |
|--------|--------|
| Success | Continue to step 5. |
| Timeout | Append attempt-log entry (`outcome: "aborted"`, `cause: "timeout"`). Split task per `references/task-splitting.md`, mark original as blocked. |
| Context exceeded | Append attempt-log entry (`outcome: "aborted"`, `cause: "context_overrun"`). Split task per `references/task-splitting.md`, mark original as blocked. |
| Error | Invoke `debug-stuck-agent` (step 4.5). On unrecoverable error, append attempt-log entry (`outcome: "aborted"`, `cause: "error"`). Report to user. |
| Result lost / hung | The Agent result is empty, is `[Tool result missing due to internal error]`, or the Subagent Watchdog killed a hung agent. This is an infrastructure failure, not real work — apply the **infrastructure-failure circuit breaker** (step 4.2). |

### 4.2. Infrastructure-failure circuit breaker

A lost/empty Agent result or a watchdog-killed hang is an infrastructure failure, not a content failure. Do **not** silently re-dispatch in a loop — two back-to-back infrastructure failures on the same task once caused a multi-hour stall (`references/design-rationale.md` § circuit breaker).

1. Check the working tree (`git status --short`). A crashed agent may have left partial, uncommitted, **unverified** changes. Note them in the task output; do not commit them blind and do not assume they compile.
2. Re-dispatch the **same** task at most **once**. Track infrastructure re-dispatches per task — this cap is separate from the test-failure retry cap (step 5.5) and the review-cycle cap (step 5.7).
3. On the **second** infrastructure failure for the same task: stop. Append an attempt-log entry (`outcome: "aborted"`, `cause: "subagent_infra_failure"`), set `state.stall_reason` to `{"stalled": "subagent_infra_failure", "task": "<id>"}`. Escalate to the user. Do **not** advance to the next task.

### 4.5. Debug on error

If the tool returned an error, invoke the `debug-stuck-agent` skill to diagnose the root cause before reporting to the user. If debugging resolves the issue, continue to step 5. If not, report to user and keep task in_progress.

### 5. Commit changes

Stage exactly this task's files, then commit in a separate Bash call. **Never `git add -A` or `git add .`** — the worktree is live (the user edits files during dispatches), and a bulk add sweeps foreign uncommitted work into the task commit (memory: feedback_subagents_vs_live_worktree).

1. Build the stage list: the paths from Ivan's `FILES_TOUCHED:` footer (see **Assumptions footer**), plus any build-generated files this task's changes legitimately produced (lockfiles, snapshots, generated bindings) — identified from `git status --porcelain` output, never guessed.
2. Fallback when the footer is absent or `none` while the tree is dirty (legacy retry prompts, malformed report): stage the intersection of dirty paths with the exact files the plan task names; treat every other dirty path as foreign.

```bash
git add <path> [<path> ...]
```
```bash
git commit -m "<type>(<scope>): <description>"
```

Any other dirty path is **foreign**: leave it unstaged and untouched, and name it in the phase report (fail loud) — the same never-commit-foreign-work rule the step-5.5 ESCALATE reset guard enforces.

Never chain these with `&&` in a single Bash call. Commit message rules: conventional commit format, one line, no period, reference the task ID if available.

Before committing a `feat`/`fix` (or breaking) change, verify CHANGELOG.md is staged in the same commit per rules/changelog.md — repos with a declared no-changelog exception (e.g. the buvis home repo) skip this check.

**If a commit (or its `git add`) is rejected** — `aegis`'s `validate_commit_msg.py` blocks a non-conventional message (boilerplate trailer, HEREDOC, bad format — `rules/development-workflow.md`), or warden denies the `git add`/`git commit` command: read the deny reason from the blocked tool result (aegis names the format violation; warden's reason usually names the preferred command form), fix the message or the command accordingly, and **retry the commit ONCE**. Still rejected after the one repair → ESCALATE: append an attempt-log entry (`outcome: "aborted"`, `cause: "commit_rejected"`), then report to the user (interactive) or take the loop-mode stall path (`run-autopilot/references/recovery.md`, `site: "sub_skill_fail"`, `detail` = the deny reason) — never leave the task's work uncommitted-and-unrecorded, and never reach for `--no-verify` to bypass the hook. This branch applies to every commit this skill makes (step 2.9 tests, step 5 implementation, the step-5.5/5.7 re-commits, the step-5.6 deslop commit).

### 5.5. Verify THIS task's tests pass

Run **only** the specific tests Tess wrote in step 2.7. Do NOT run the full project test suite, smoke tests, integration tests, or lint here — those run once at the end of the phase (step 7).

- Target the narrowest scope that covers the new tests:
  - Rust: run `cargo check -p <crate>` first — a compile failure IS the gate failure (skip the test run, go straight to the retry path with the compiler output); then `cargo test -p <crate> --test <test_file>` or `cargo test -p <crate> <module::test_name>`
  - Python: `pytest path/to/test_file.py::test_name`
  - JS/TS: `vitest run path/to/test_file` or `jest path/to/test_file`
- Never dispatch Tess to weaken tests.
- **Retry prompts** (feedback retry, repair re-dispatch, or escalation dispatch) **must re-include the code-quality rules block** from `references/code-quality-principles.md`, plus an explicit SURGICAL instruction: "Fix only what the failing test output points to. Do not refactor passing code, adjust unrelated files, or change style."

**Do not run here:** `cargo test --workspace`, `cargo clippy --workspace`, `./tests/smoke.sh`, `./tests/integration.sh`, `cargo test-full`, or any equivalent full-suite command. These are batched into step 7.

**Gate-failure handling.** Read `_AUTOPILOT_ESCALATION` (env var; `model-ladder.md` § Kill-switches).

**`_AUTOPILOT_ESCALATION == "legacy"`** (byte-identical to pre-00065 — replaces the old same-tier retry-cap text; no diagnosis, repair, escalation, attribution stamping, or qwen capability breaker):
- If tests fail, dispatch Ivan again with the failure output.
- If the failing attempt's implementor was qwen (one-shot qwen attempt budget): the re-dispatch targets **Claude Sonnet** — never qwen again (the carve-out in "Per-task model dispatch" above). The retry budget below then applies to the Claude Sonnet re-dispatches; the qwen attempt does not consume a slot.
- Max 2 implementation retries before escalating to the user.

**Any other value / absent — diagnose→repair/escalate flow (default):**

Per-rung budgets are declared once in `model-ladder.md` § Per-rung budgets — cite, do not restate: Claude rungs (haiku/sonnet/opus) get 2 dispatches (initial + one feedback retry) before diagnosis; the qwen rung gets 1 dispatch (no feedback retry — the existing one-shot carve-out, named the ladder's `qwen -> sonnet` capability edge); repair is capped at 1 per task, total, and is Claude-rungs only (qwen never repairs).

```
gate fail #1 at current rung → feedback retry: dispatch Ivan with the failure output, SAME tier
                                (Claude rungs only — the qwen rung has no feedback retry: its single
                                gate failure goes straight to DIAGNOSE below, per the 1-dispatch budget)
gate fail #2 at current rung → DIAGNOSE:
  1. Write task.description (from TaskGet) to dev/local/tmp/diagnose-task-<id>.txt and run:
       python3 ~/.claude/skills/work/scripts/diagnose_task.py <task-file> --repo-root <project-root>
     `<project-root>` = the dir containing dev/local/, resolved by walking up from cwd (same anchor
     as _walk_up.py) — NOT state.repo_root, which differs under a bare-repo-backed project.
     verdict "spec_gap" (exit 0) → REPAIR path below, if repair unused this task AND current rung
     is a Claude rung (qwen never repairs — see budgets above)
  2. verdict "pass", OR the script errored (exit 2, shape-check inconclusive) → inline rubric
     judgment, this session, at its current tier: spec_gap | solid_spec, with a one-line
     justification, stamped as `diagnosis` on the diagnosed rung's attempt entry (see Attribution
     below). The orchestrator never overrides a deterministic spec_gap verdict from step 1.
REPAIR (spec_gap, repair not yet used this task, current rung is a Claude rung): fill the identified
  gaps (missing Contract, missing Acceptance criteria, dangling file references) from the PRD +
  design doc, rewrite the task description via TaskUpdate(taskId, description=<repaired>) — the
  canonical store /work re-reads via TaskGet — and re-dispatch Ivan at the SAME tier ONCE. Stamp
  `repair_used:true` on that rung's attempt entry. A gate failure after the repair takes the
  solid_spec path below — repair is exhausted for this task.
ESCALATE (solid_spec, OR spec_gap with repair unavailable/already used, OR any qwen-rung spec_gap):
  1. Reset guard — capture `<candidate_head>` = `git rev-parse HEAD` first, then require BOTH:
     - **uncommitted:** `git status --porcelain` is empty (no foreign/uncommitted working-tree files), AND
     - **committed range:** `git rev-list <test_commit_sha>..<candidate_head>` contains ONLY this
       task's own implementation commit(s) (the commits step 5 made after the test commit).
     Passing the guards is necessary but NOT sufficient — a foreign commit can still land between the
     check and the reset (a live worktree; project_autopilot_head_moves_midreview), and `git reset
     --hard <test_commit_sha>` would silently discard it. So move the ref ATOMICALLY, never with a
     bare `git reset --hard` off a stale check:
     - both guards pass → compare-and-swap the branch ref to the test commit, succeeding ONLY if HEAD
       is still `<candidate_head>`: `git update-ref refs/heads/<current-branch> <test_commit_sha>
       <candidate_head>` (the third arg is git's old-value guard — the CAS; `<current-branch>` from
       `git rev-parse --abbrev-ref HEAD`). Then `git reset --hard` (the ref already points at the test
       commit, so this only cleans the worktree). `<test_commit_sha>` is this task's own test commit,
       captured in-session right after step 2.9 — never a prior task's commit.
     - the CAS fails (HEAD moved — a foreign commit raced in), OR either guard failed (foreign
       uncommitted files, or a foreign commit already in `<test_commit_sha>..<candidate_head>`) → do
       NOT reset; escalate fix-forward instead (dispatch the higher rung against the current tree +
       failing tests, no reset) and log the deviation on the attempt. Never discard commits or files
       this task did not create (memory: feedback_subagents_vs_live_worktree,
       project_autopilot_head_moves_midreview). Fix-forward is the safe default whenever the reset is
       not provably this-task-only AND atomic.
  2. Stamp the LOWER rung's entry: `outcome:"escalated"`, `diagnosis:<verdict>` (+
     `qwen_gate_failed:true` if that rung's implementor was qwen, + `repair_used:true` if a repair
     ran at that rung). **If `task.metadata` carries a review-flag escalation
     (`escalation_reason:"review_flag"` + `escalated_from`, set by /run-autopilot Phase 6 when this
     rung IS the review-flagged rework rung), copy both onto THIS lower-rung entry now** — Phase 6
     escalated INTO this rung, so the `review_flag` reason belongs here; capturing it before step 3
     clears it is what keeps the review-flag source recorded when a review-flagged task ALSO escalates
     in-loop (otherwise the reason would be lost on this entry and mis-stamped on the higher rung).
  3. `TaskUpdate(taskId, metadata={model: <new tier>})` (mirrors the state-schema.md tasks[].model
     Phase-6 pattern), mirrored into `state.tasks[i].model` per Dashboard State Sync — BEFORE the
     dispatch below, so the **Per-task model dispatch** rule picks up the escalated tier for Ivan
     and every downstream read this task (step 5.6, step 5.7's tier gate). **Also clear any
     `escalation_reason`/`escalated_from` from `task.metadata` here** — point 2 already copied a
     review-flag reason onto the lower-rung entry, and the higher in-loop rung records its OWN
     `escalation_reason:"gate_failure"` at point 5. Leaving the sticky `review_flag` in `task.metadata`
     (which `TaskUpdate` merges, not replaces) would make step 6's metadata→entry copy mis-stamp
     `review_flag` onto this `gate_failure` rung.
  4. Dispatch ONE rung up (per `model-ladder.md` § Capability ladders — qwen -> sonnet skipping
     haiku, haiku -> sonnet -> opus) with a FAILURE SUMMARY: failing test names, the last
     gate-output excerpt, the diagnosis verdict, and the prior implementor + tier.
  5. Stamp the HIGHER rung's NEW attempt entry: `escalation_reason:"gate_failure"`,
     `escalated_from:<prev tier>`.
  6. At the new rung the budget resets (initial + one feedback retry, per `model-ladder.md` §
     Per-rung budgets), then this same gate-failure flow re-applies if it fails again.
  Opus-rung exhaustion (2 failures at opus) flows into the existing abort/stall machinery (PRD
  00017) — do not invent a new halt class.
```

**Attribution row ownership** (one entry per rung/dispatch-group — never lump every field onto a single entry; see `references/attempt-logging.md` § Attribution row ownership):

| Field | Row it is stamped on |
|-------|----------------------|
| `diagnosis` | the **diagnosed** (lower) rung's entry |
| `qwen_gate_failed` | the qwen (lower) rung's entry |
| `repair_used` | the entry of the same-tier attempt that ran after a repair (that rung's entry) |
| `escalation_reason:"gate_failure"` | the rung escalated **INTO** (higher)'s entry |
| `escalation_reason:"review_flag"` | the review-flagged rework rung's OWN entry (Phase 6 escalated INTO it): copied from `task.metadata` at step 6 if that rung exits there, or at ESCALATE point 2 (then cleared at point 3) if it escalates in-loop |
| `escalated_from` | the rung escalated **INTO** (higher)'s entry (both `gate_failure` and `review_flag` paths) |

**Pipeline stamping on escalation.** An in-loop escalation re-dispatches the implementor at the higher rung and re-runs the tier-appropriate post-implementor gates (step 5.7 reviewer for sonnet+, and this step-5.5 gate) — it does NOT re-run Devon (2.85; the tests are already committed). Stamp the escalated-into entry `pipeline:"lean"` (implementor + reviewer), never `"full"` — `"full"` stays reserved for a from-scratch opus task/rework that actually ran Devon.

**qwen capability breaker counter (this gate).** Guarded by `_AUTOPILOT_ESCALATION != "legacy"`, same as the routing consult in step 3. On an `implementor:"qwen"` attempt only: gate pass → reset `qwen_gate_failures_consecutive = 0`; gate fail → stamp that attempt `qwen_gate_failed:true` and increment `qwen_gate_failures_consecutive`; at 2 consecutive → latch `qwen_breaker = {tripped:true, after_task:<this task id>, failed_tasks:[<the two ids>], batch_id:<effective batch id>}` (batch-scope check as in step 3). Keys off the stored `qwen_gate_failed` field, not `outcome` (an escalated-away qwen entry reads `outcome:"escalated"`), keeping the increment jq-expressible. Rework attempts never touch the breaker — rework never routes qwen. A non-qwen task between two qwen failures leaves the counter unchanged (`run-autopilot/references/state-schema.md` `qwen_gate_failures_consecutive`).

**Deterministic precedence — two separately-scoped orderings** (`model-ladder.md` § Ordering; NOT one linear chain):
- **Routing-time** (step 3, per task): qwen breaker consult → qwen infra preflight → dispatch.
- **Failure-classification** (here, or on a lost result per step 4.2): an infra failure (preflight fail, watchdog/lost result) falls back at the SAME tier and never enters diagnosis or touches the breaker; a capability failure (a real test-gate failure, this section) enters diagnosis, where repair precedes escalate.

### 5.6. Self-deslop pre-commit pass

After step 5.5's tests pass and BEFORE the per-task code review at step 5.7, dispatch a fresh subagent to prune slop from the implementor's diff. The per-task review then runs against the leaner diff, which means review-rework cycles add defensive fixes on top of a smaller base. Best-effort: this step never blocks the task and never triggers retries.

**Skip rule.** Measure the implementor's most recent commit:

```bash
git diff --shortstat HEAD~1..HEAD
```
```bash
git diff-tree --no-commit-id --name-only -r HEAD
```

Compute `net_lines = insertions - deletions` (from `--shortstat`) and `file_count` (lines from `diff-tree`). If `net_lines < 30` OR `file_count < 2`, skip the dispatch — the cleanup overhead exceeds the slop budget for trivially small changes. Record `self_deslop: "skipped:trivial"` on the latest attempt (see "Outcome logging" below) and proceed directly to step 5.7.

**Dispatch contract.** Otherwise, dispatch a **fresh** Agent call (NOT the implementor's session — fresh context breaks the "I built this" attachment; why: `references/design-rationale.md` § fresh dispatch) at `task.metadata.model`. Same tier as the implementor keeps cost proportional. The dispatch must satisfy the **Subagent Dispatch Budget** and the **Subagent Watchdog**.

**Prompt construction.** Build the subagent prompt from `references/self-deslop-prompt.md` by substituting:

- `{{task_subject}}`, `{{task_description}}`, `{{task_acceptance_criteria}}` from `TaskGet` on the current task.
- `{{test_files}}` from the tests Tess wrote in step 2.7 (the same set step 5.5 just ran).
- `{{diff_files}}` from `git diff-tree --no-commit-id --name-only -r HEAD`.
- `{{slop_catalog}}` from the `## What to remove` section of `~/.claude/skills/run-autopilot/prompts/de-sloppify.md` — read the file at dispatch time and inline the section verbatim. This keeps the deslop prompt as the single source of truth for slop patterns; when it grows entries, the next step-5.6 dispatch picks them up without a code change here.

**Outcome logging.** Write the result to `state.tasks[i].attempts[-1].self_deslop` (the most recent attempt entry, written by step 6's Attempt logging):

| Subagent outcome | `self_deslop` value | Proceed to 5.7 against |
|------------------|---------------------|------------------------|
| Committed `chore: prune slop from ...` | `"committed:{sha}"` (full SHA from the new commit) | the pruned diff (HEAD now includes the cleanup commit) |
| Returned "no slop found", no commit | `"noop"` | the original implementor diff |
| Watchdog timeout (`TaskStop` fired) | `"timeout"` | the original implementor diff |
| Dispatch failed or subagent errored | `"errored:{short_cause}"` (e.g. `errored:dispatch_failed`, `errored:prompt_overrun`) | the original implementor diff |
| Skip rule fired | `"skipped:trivial"` (no dispatch occurred) | the original implementor diff |

In every non-committed outcome, the implementor's original commit stands and step 5.7 reviews it directly. **Do not retry self-deslop on failure** — best-effort means single attempt only.

### 5.7. Per-task code review

**Tier gate — per-task review is skipped only on haiku.** Read `task.metadata.model`:

| `task.metadata.model` | Per-task review (step 5.7) |
|-----------------------|----------------------------|
| `haiku` | skip per-task review |
| anything else — `opus`, `sonnet`, absent/legacy or unknown (both treated as `sonnet`) | review (below) |

A `haiku`-tier task commits after per-task test verification (step 5.5) with **no** review dispatch and proceeds straight to step 6 — it relies on per-task test verification plus the mandated PRD-level review lenses (consensus, blind, doubt — every review cycle reviews every task's diff regardless of tier). The reviewer is a fixed-model helper-script lane (Sonnet via `use-sonnet`) — reviewer capability is deliberately independent of the task's implementor tier. (Why tier-gated: `references/design-rationale.md` § tier-gated pipeline.)

Dispatch the reviewer after commit and verification — a native lane, no plugin dependency:

1. Get SHAs: `BASE_SHA` = the parent of this task's test commit (`<test_commit_sha>` from step 2.9), `HEAD_SHA` = current HEAD (includes the step-5.6 deslop commit when one landed).
2. Assemble the review prompt in `dev/local/tmp/review-task-<id>-prompt.md` (Write tool, never shell redirects): task subject, description, and acceptance criteria; the output of `git diff BASE_SHA..HEAD_SHA`; the **Simplification mandate** block from `references/simplification-mandate.md` verbatim; and the reporting contract — one finding per line as `SEVERITY | file:line | issue | fix` (severities CRITICAL/HIGH/MEDIUM/LOW), or the literal line `NO FINDINGS`. State that the review is read-only: report findings, change nothing. The assembled prompt must satisfy the **Subagent Dispatch Budget**.
3. Dispatch via the sonnet runner (helper-script dispatch — the **Subagent Watchdog** applies):
   ```bash
   bash ~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -f dev/local/tmp/review-task-<id>-prompt.md -o dev/local/tmp/review-task-<id>.md
   ```
   No `-a`/`-y` — the reviewer needs no write access, and a read-only dispatch must never run with bypassed permissions.
4. Read the output file and handle the result:
   - **CRITICAL or HIGH findings** — treat like a failed verification: verify each finding against the code first and discard wrong ones (the reviewer can be wrong), then dispatch Ivan with the confirmed findings, the code-quality rules block from `references/code-quality-principles.md`, and: "Apply ONLY the specific fixes listed below. Do not refactor surrounding code or address unrelated issues you notice." Re-commit (step 5), re-verify (step 5.5), re-review. Max 3 review cycles, then proceed with warning.
   - **MEDIUM/LOW only, or `NO FINDINGS`** — note them in the task output, proceed to step 6.
   - **Runner unavailable, exit nonzero, or output file missing/empty** — retry ONCE. On the second failure: record `review: failed:<cause>` in the task's attempt entry and the phase report (fail loud), then proceed to step 6 — the reviewer lane never blocks the batch; the PRD-level review lenses catch what it missed.

Skip for documentation-only or configuration-only tasks.

### 6. Mark complete and sync

1. Use `TaskUpdate` to set `status: completed`
2. **Append an entry to `state.tasks[i].attempts[]`** per the "Attempt logging" section: `outcome: "completed"`, `model` from `task.metadata.model`, `pipeline` from `task.metadata.model` (`haiku` → `"minimal"`, `sonnet`/absent/legacy → `"lean"`, `opus` → `"full"`), `cause: null`, `review_cycle: null` on a Phase-3 first pass or the current `state.cycle` on a rework pass. When `task.metadata.escalation_reason` / `task.metadata.escalated_from` are present (set by `/run-autopilot` Phase 6 for a review-flag escalation), **copy both onto the entry** so `escalation_reason: "review_flag"` reaches `attempts[]`; absent → omit both.
3. **Append `ASSUMPTIONS:` lines** from this task's Tess and Ivan reports (any entry beyond `none`) to `dev/local/assumptions.md` per the **Assumptions footer** section
4. **Sync state file** (see Dashboard State Sync) — mandatory
5. Proceed to step 6.5 (task-boundary handoff check) — it routes to the next task, a clean handoff, or final verification.

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
   d. **Write the contract card** (run-autopilot § Contract card): the current step, the active invariants, and the next gate — via statectl `set contract_card` (autopilot) or the scratch `dev/local/autopilot/contract-card.md` (interactive), so a session compacted after this boundary re-anchors instead of drifting. Then ensure `state.next_phase == "build"` (it already is during the build gate, since this is a mid-build task-boundary handoff with pending tasks remaining), then STOP — end the turn. In loop mode the wrapper reads the non-empty `next_phase: "build"` and relaunches a fresh session (the headless hand-off contract in `run-autopilot/SKILL.md` § Session Loop); the model writes no signal.

   **Do NOT return to step 1, and do NOT run step 7.** `phases_completed` stays without `"work"` (this session did not finish the phase), so `/run-autopilot` re-enters Phase 3, hydrates TaskList from `state.tasks`, and re-invokes `/work` for the pending tasks.

### 7. Final verification (once per work phase)

After all tasks in the phase are marked completed, run the project's full verification suite **once**. This is the single point where the full suite runs — per-task verification (step 5.5) only ran the new tests in isolation, so this step is mandatory and must not be skipped.

**What to run** (project-dependent — use the commands documented in `AGENTS.md` / `CLAUDE.md` / project README):

- Full workspace tests — Rust: `cargo nextest run --workspace` when nextest is installed (probe once with `cargo nextest --version`; on any nextest infra error fall back to `cargo test --workspace` — doc-tests are NOT run by nextest, so add `cargo test --workspace --doc` when the project has doc-tests); otherwise `cargo test --workspace`. Other stacks: `pytest`, `npm test`
- Lint (e.g., `cargo clippy --workspace`, `ruff check`, `eslint .`)
- Smoke tests if the project defines them (e.g., `./tests/smoke.sh`)
- Integration / e2e tests if the project defines them (e.g., `./tests/integration.sh`, `cargo test -p <crate>-e2e`)
- Any project-specific "definition of done" checks

**When the repo documents no verification commands** (no test/lint/build commands in `AGENTS.md`/`CLAUDE.md`/README): do NOT silently skip verification. Detect the stack from its manifest and improvise the standard suite — `Cargo.toml` → `cargo test --workspace` (+ `cargo clippy --workspace`); `pyproject.toml`/`setup.py` → `pytest` (+ `ruff check` if configured); `package.json` → `npm test` (only if a `test` script exists). Run the improvised set, and **state the exact improvised command set in the phase report** (fail loud — an improvised suite must not read as the project's own documented one). If no stack manifest is detectable and nothing runs, record `verification: none (no suite found)` in the phase report and surface it as a gap for the review phase — never report the phase green on an unverified tree.

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

When reporting the phase result, include the contents of `dev/local/assumptions.md` (if present) - the assumption ledger is input to the review phase and the user's 30-second examine pass.

## Reference Files

- `references/test-author-prompt.md` - Test author (Tess) prompt template
- `references/adversarial-test-prompt.md` - Adversarial validator (Devon) prompt template
- `references/codex-integration.md` - Codex review-only usage
- `references/gemini-integration.md` - Gemini prompt templates, patterns, and the Design Authority section
- `references/qwen-integration.md` - qwen dispatch + four-check preflight protocol
- `references/code-quality-principles.md` - Think/Simplicity/Surgical/Goal-driven rules to inject into Ivan prompts
- `references/code-quality-examples.md` - Before/after examples of the anti-patterns those rules prevent
- `references/subagent-dispatch.md` - Dispatch Budget + Watchdog: how to safely make an Agent call
- `references/task-splitting.md` - Splitting a timed-out or oversized task, plus the parallel-rework cap
- `references/attempt-logging.md` - `state.tasks[].attempts[]` entry schema and write procedure
- `references/self-deslop-prompt.md` - Step 5.6 prompt template (placeholders + `{{slop_catalog}}` substitution)
- `references/simplification-mandate.md` - Step 5.7 reviewer-prompt appendix (append verbatim)
- `references/design-rationale.md` - incident history behind the rules (non-normative)
