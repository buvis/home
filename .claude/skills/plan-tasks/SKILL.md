---
name: plan-tasks
description: Use when breaking a PRD into granular, sequenced implementation tasks ready for the work skill. Triggers on "plan tasks", "create tasks from PRD", "implement PRD", "break down the spec".
---

# Plan Tasks from PRD

Create implementation tasks from PRD documents.

## Dependencies

- Personal skills (files read at runtime): `work` - its `SKILL.md` "Gemini-first tasks" list is the single source of truth for the UI/backend split that sets `qwen_eligible`, and `references/qwen-integration.md` carries the qwen infra preflight (absent: qwen counts as unavailable and the eligibility trigger is skipped)
- Harness tools: `TaskCreate`, `TaskUpdate`, `TaskList`
- State contract with `run-autopilot`: `dev/local/autopilot/state.json`, `dev/local/autopilot/replan-context.md`
- Optional: `pi` binary plus a reachable llama.cpp endpoint (gated by the preflight, never fatal)

## Workflow

### 1. List available PRDs

```bash
~/.claude/skills/plan-tasks/scripts/list-prds.sh
```

Or manually list PRDs (the native `Glob` tool is absent in this build; see rules/tools.md):
```bash
ls dev/local/prds/wip
ls dev/local/prds/backlog
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

**Design doc (when present).** Check `state.design_doc` in `dev/local/autopilot/state.json`; if it is unset, fall back to the glob `dev/local/designs/<prd-stem>-design.md` (`<prd-stem>` = the selected PRD's filename minus `.md`). When a design doc exists, read it — it refines the PRD with the implementation design (the HOW): `## Interfaces & contracts` (exact signatures/types/enums), `## Module placement` (file targets), and `## Reuse inventory` (existing helpers). These seed the task `Contract`, `Location`, and `Reuse:` fields in step 4. When no design doc exists, plan from the PRD alone, as today. This detection works unchanged in replan mode.

Extract:
- Capabilities and features
- Module structure
- Dependency graph
- Implementation phases
- Existing patterns/utilities that implementers should reuse

**When the PRD has no Functional Decomposition or Dependency Graph section** (many PRDs state only `## Requirements` + `## Acceptance`): do NOT treat the split (step 4.6) and dependency (step 5) inputs as undefined. **Derive** both from the Requirements — treat each requirement (R1, R2, …) as a decomposition unit, and infer ordering from explicit `depends on`/`after`/`blocked by` wording and from data-flow (a requirement that consumes another's output sequences after it); default to no dependency when none is stated. Steps 4.6 and 5 then use this derived structure exactly as they would a stated one. **Note the derivation in the step-6 planning summary** so the reviewer knows the sequencing is inferred, not PRD-pinned.

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

Premise: {observed-state facts this task depends on; re-verify before acting}

Contract (verbatim — from the design doc's `## Interfaces & contracts` when a design doc exists, else from the PRD; copy exact names, do NOT paraphrase):
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

**The `Premise:` line is optional and PRD-owned.** When the PRD states a
premise for a task (observed-state facts its action rests on), copy it
**verbatim** into the `Premise:` line — same discipline as `Contract`, never
paraphrased. The implementor must re-verify the premise before acting and treat
a false premise as a blocker: stop, report, do not proceed. In loop mode this
feeds PRD 00017's stall path (`run-autopilot/references/recovery.md`
"Loop-mode stall procedure") — a premise failure is never resolved by
assumption. When the PRD states no premise, omit the line entirely: no new
behavior, nothing inferred or invented.

**Contract source when a design doc exists.** When a design doc is present
(detected in step 3), the task `Contract` is copied **verbatim from the design
doc's `## Interfaces & contracts`** entries — byte-identical, not paraphrased —
because the design doc is the architecturally-vetted refinement of the PRD's
contract. `Acceptance criteria` is **ALWAYS** copied verbatim from the **PRD**;
the design doc never owns acceptance criteria — those stay PRD-owned. Seed each
task's file placement / `Location` from the design doc's `## Module placement`
and its `Reuse:` lines from `## Reuse inventory`. When NO design doc exists, the
`Contract` comes from the PRD as described above. **On a PRD-vs-design contract
conflict, the design doc wins** (it refines the PRD): use the design doc's
contract and log the conflict in the step-6 planning summary. This rule works
unchanged in replan mode.

**If a `TaskCreate` call fails mid-plan** (harness error, task tool unavailable — NOT the oversize stall handled in step 4.6): stop creating tasks and **roll back cleanly**. Query `TaskList` and `TaskUpdate(status: "deleted")` every task created this invocation (same cleanup as the oversize stall below) so no orphan tasks survive to make the next PRD's Phase 2 skip planning. Then record the cause via statectl — `set stall_reason '{"stalled": "taskcreate_failed", "detail": "<the TaskCreate error>"}'` — and report the failure. `/run-autopilot` Phase 2 reads a non-`oversized_task` stall as a plan-tasks failure (PAUSE interactive; loop mode re-invokes once, then stalls the PRD `sub_skill_fail`); the rollback guarantees the retry starts from a clean tracker. Do NOT move the PRD to `hold/` — a transient `TaskCreate` failure is not an un-splittable PRD.

**On successful completion of all `TaskCreate` calls, clear a stale failure marker:** `statectl get stall_reason` → if it reads `"taskcreate_failed"` (a prior attempt failed and this retry succeeded), `statectl del stall_reason`. Otherwise leave it untouched — an `oversized_task` marker is owned by step 4.6, and a fresh plan usually has no marker (do NOT blind-`del`; statectl errors on an absent key).

### 4.5. Estimate per-task context budget

For each task, compute an estimate so `/work` stays under the work-tier model's standard context ceiling (200K on the current tiers).

**Formula:**

```
estimated_tokens = sum(file_bytes/4 for file in task.files_touched)
                 + prd_slice_bytes/4
                 + plan_text_bytes/4
                 + 55000
```

- `file_bytes/4`: ~4 chars per token, accurate within ±20% for code (less accurate for prose-heavy markdown; round up when in doubt).
- `prd_slice_bytes`: bytes of the PRD section(s) this task references.
- `plan_text_bytes`: bytes of the task's own description/details.
- `55000`: overhead constant for system prompt + tool defs + skill texts on the current work-tier model (see "Overhead re-derivation" under Estimator caveats for provenance).

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
overhead            =                              55 000
                                                  ───────
estimated_tokens    =                              97 000
est_context_peak    = 97 000 + 20 000           = 117 000
```

Below the 150K threshold → task ships as-is.

### 4.6. Split tasks (context + eligibility)

Step 4.6 has **two independent split triggers**. The existing context-budget trigger is unchanged; the eligibility trigger is new (PRD 00032, widened by PRD 00019) and pushes separable backend work toward the `<=3`-file shape that `/work` can route to qwen.

- **Context-budget trigger** (always active): when `estimated_tokens > THRESHOLD` (150K normally; replan-context.md budget in replan mode), the task is too big for a single context window.
- **Eligibility trigger** (infra-gated, see the qwen infra preflight subsection below): a **backend** task (UI/backend definition: see step 4.7 — UI matches the "Gemini-first tasks" list in `~/.claude/skills/work/SKILL.md`, everything else is backend) touching `>=4` files is split toward `<=3`-file pieces so each subtask can route to qwen. The split is valid only when **cleanly separable** — judged from the PRD's Functional Decomposition and Dependency Graph, with each resulting piece required to independently compile and carry its own passing tests (no piece depends on a symbol another piece introduces). **A trait definition cannot be split from its implementations.**

When **both** triggers apply to the same task, a **single split pass** satisfies both — do not run two passes. After splitting, each subtask is re-estimated per step 4.5 and re-classified per step 4.7 (so `qwen_eligible` reflects the new file count).

**Qwen infra preflight (gates the eligibility trigger only):**

Before applying the eligibility split trigger, `plan-tasks` runs the qwen infra preflight defined in `~/.claude/skills/work/references/qwen-integration.md` (PRD 00031) — `pi` on PATH, the llama.cpp endpoint reachable, the configured model id present, and a real 1-token completion succeeding (the only check that proves the inference worker actually spawns). It is cheap on the common path; it exists so the eligibility split is only paid for when qwen can actually consume the result — a backend that lists the model but can't serve a token (`completion_failed`) skips the split rather than marking tasks qwen-eligible that would only fall back at dispatch.

- **Healthy** → the eligibility trigger is active for this PRD's tasks.
- **Unhealthy, or the probe is unavailable** (any failure mode reported by the probe — see `~/.claude/skills/work/references/qwen-integration.md` for the current check list; absence of that file itself, e.g. before PRD 00031 has landed, also counts as unavailable) → the eligibility trigger is **skipped entirely**; tasks keep their original shape and route to Claude.

The **context-budget trigger is not gated** by the preflight and remains active regardless of qwen's status. The **step-4.7 `qwen_eligible` computation is not gated** either — it is always computed and persisted on every task (staying inert until `work` reads it).

**Opus-signal exemption (skips the eligibility trigger only):**

A task whose text carries an opus signal is **not split for eligibility**. The opus-signal set is **not redefined here** — step 4.6 reuses the exact signal list **defined by step 4.7 Rule 1**, as a single source of truth: if Rule 1's signal list changes, step 4.6 inherits the change automatically because it references rather than copies it.

This check is a **plain text scan** of the task title + description against Rule 1's signal phrases (lowercased, per Rule 1's case-insensitivity note); it does **not** require running the full step-4.7 classifier. A match short-circuits the eligibility trigger and the task keeps its original shape. The context-budget trigger is unaffected — an opus-signal task that also exceeds the context budget is still split for that reason.

The existing context-budget split mechanics, the one-split-attempt rule, and the stall behavior below are **unchanged** by the eligibility trigger — both triggers share them:

1. **File boundary first.** Split into one task per file. The PRD slice prorates equally; the 55K overhead applies once per task. Re-estimate each subtask.
2. **Capability boundary second.** If a task touches only one file and still exceeds the threshold, split along capability boundaries inside the PRD's Functional Decomposition section (or the decomposition derived from the Requirements in step 3 when the PRD states none).
3. **One split attempt only.** If a task still exceeds the threshold after splitting, mark the PRD as stalled (use the threshold value in the stall_reason).

**Stall behavior:**

When unable to split below the threshold (150K standard, 75K in replan mode), **merge** a `stall_reason` key into the existing `dev/local/autopilot/state.json` via statectl — the sole writer for state.json (never hand-edit with Read/Write/Edit; see `/run-autopilot`):

```bash
python3 ~/.claude/skills/run-autopilot/scripts/statectl.py dev/local/autopilot/state.json set stall_reason '{"stalled": "oversized_task", "task": "<task-id>", "estimated_tokens": <int>}'
```

statectl merges the key and preserves the existing `phase`, `phases_completed`, `tasks`, `batch`, etc.

**Then delete every task you already created** via `TaskCreate` for this PRD: query `TaskList`, call `TaskUpdate(status: "deleted")` on each. `/plan-tasks` calls `TaskCreate` before the per-task budget check, so by the time the stall fires there are orphan tasks in the tracker. Cleaning up here makes the stall self-contained: any caller (not just `/run-autopilot`) gets the same post-stall state. `/run-autopilot` Phase 2 also performs this cleanup as a backstop.

After both writes succeed, end the session's work with the stall recorded (the `stall_reason` key in state.json IS the observable stall signal — a model-followed skill has no exit code); `/run-autopilot` Phase 2 reads it, detects the stall, moves the PRD from `dev/local/prds/wip/` to `dev/local/prds/hold/` (creating the directory if missing), clears the stall key from state, and proceeds to the next backlog item without user prompt. See `/run-autopilot` Phase 2 for the consumer-side contract.

### Estimator caveats

The bytes/4 heuristic is accurate within ±20% for source code, less accurate for prose-heavy markdown. When the largest input is markdown (PRD prose, docs), round up. When estimates land within 10% of the threshold (150K standard / 75K replan), prefer splitting — the runtime context cap hook (Phase 2 of PRD 00024) will abort tasks that overrun anyway, and a planned split is cheaper than a runtime abort.

**Overhead re-derivation:** The constant is measured by reading `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` from the first `message.usage` line in a fresh Work-phase transcript on the current work-tier model (zero task context loaded — just the system prompt, tool defs, and active skills). Re-derive when upgrading the model or adding/removing skills: start an empty `/work` session, read the first usage line from `~/.claude/projects/<hash>/<session>.jsonl`, sum the three token fields. Update the constant and the worked example if the new value differs by more than 5K. Provenance of the current 55K (2026-07-11): five fresh headless opus-4.8 work-phase transcripts measured 74,560-74,809 (~74.7K), minus PRD 00043's measured always-loaded reduction (run-autopilot SKILL.md 33.0K → 7.3K core, +5.4K gate file read back in ≈ −20K net) ≈ 55K, rounded. Those transcripts predate the 00043 restructure; re-measure directly at the next batch and correct if the fresh number moves more than 5K.

**Pending re-derivation (PRD 00084 R3, BLOCKED):** the 55K/150K constants are measured on `opus-4.8` — still the autopilot **build**-phase model (`autoclaude` hardcodes `_AUTOPILOT_MODEL_BUILD=claude-opus-4-8`), so they remain current. If the build phase moves to Fable 5, re-derive per the mandate above on real Fable build transcripts. This is deliberately deferred until a few Fable build batches exist — do NOT re-derive from a single ad-hoc session or a non-build transcript.

### 4.7. Assign per-task model tier

For each task, classify a model tier and persist it as `metadata.model: "haiku"|"sonnet"|"opus"` so `/work` can dispatch each subagent at the right tier (PRD 00025).

**Inputs:** task title + description (string), `files_touched` count, estimated lines-changed (rough — pull from the task plan or estimate from the file slice), the `estimated_tokens` computed in step 4.5, and the active PRD body (for novelty signals).

**Rules** (evaluated top-down, first match wins):

| Rule | Tier | Trigger |
|------|------|---------|
| 1 | `opus` | PRD or task text contains any of: `design`, `architect`, `introduce`, `novel algorithm`, `concurrency`, `migrate`, `refactor across` — OR `files_touched > 8` — OR `estimated_tokens > 120000` |
| 2 | `haiku` | `files_touched ≤ 2` AND est. lines-changed `≤ 50` AND task text matches a mechanical-pattern signal (`add log`, `rename`, `add test for`, `port`, `mirror`, `inline`, `extract constant`, `update import`, `bump version`) AND no Rule 1 keywords present |
| 3 | default | `sonnet`, unless PRD frontmatter `default_model:` is set (see override below) |

**Rule 2 signal list: widening attempted and WITHDRAWN (PRD 00075).** The evidence pass (`dev/local/audit-results/00075-task-mix-evidence.md`) proposed adding `wire`, `disable`, `permission`, `restore`, `complete` and `pin`. Every one was withdrawn under adversarial review, and the signal list above is byte-identical to its pre-00075 state. The reason is structural, and it is recorded here so the next attempt does not repeat it: **the proposed signals are generic English verbs, and the "mechanical" quality of the tasks they were derived from lived in their SIZE, not their verb.** Size is already gated by `files_touched ≤ 2` AND lines-changed `≤ 50` — and every counterexample below satisfies that gate, so the signal is what decides, and a common verb cannot carry that decision. Concretely: `disable` matches "Disable the vulnerable legacy password-reset endpoint that leaks account existence via timing" (1 file, ~15 lines); `restore` matches "Restore the customer records purged by the retention-job bug by replaying the backup snapshot" (1 file, ~40 lines); `wire`, even restricted to whole-word matching, matches "Wire the new webhook HMAC signature check into the payment-provider callback handler" (2 files, ~35 lines); `permission` matches "Add role-based permission checks to the billing API" (2 files, ~45 lines). Each would route security-critical or data-recovery work to `haiku` — which is the thinnest pipeline in `/work`: `haiku` skips the step-5.7 per-task code review, and Devon's adversarial test-validation is opus-only, so such a task ships on Tess's tests alone. `complete` and `pin` fail differently: `complete the <X>` is generic English for "finish X", and bare `pin` collides with `mapping`/`opinion`/`spinning`. Bindings tight enough to exclude the counterexamples matched only the historical instances they were derived from — over-fitting, not a rule. **A future widening must move a different axis than the verb** (edit shape or target artifact, e.g. "adds one entry to a config file"), and must be tested against adversarial counterexamples before shipping, not only against the instances it was derived from.

**Row selection (`_PLAN_TASKS_FLOOR`).** An optional `_PLAN_TASKS_FLOOR` value selects which Rule 2 row the classifier applies for this run. It does not compose into the `final_tier = max(...)` formula in "PRD frontmatter override" below — that formula and section are unchanged.

| `_PLAN_TASKS_FLOOR` | Rule 2 row applied |
|---|---|
| `legacy` | The pre-00075 row verbatim: `files_touched ≤ 2` AND est. lines-changed `≤ 50` AND task text matches one of exactly these nine signals — `add log`, `rename`, `add test for`, `port`, `mirror`, `inline`, `extract constant`, `update import`, `bump version` — AND no Rule 1 keywords present |
| `sonnet` | Alias for `legacy` |
| absent, empty, or any other value | The current Rule 2 row above. An invalid non-empty value logs one warning line before falling back to it |

**The knob is currently a no-op, deliberately.** Because the widening was withdrawn (above), the `legacy` row and the current Rule 2 row are identical, so every `_PLAN_TASKS_FLOOR` value selects the same behavior. It ships anyway as the kill-switch the next widening attempt will need: the moment a defensible widened row lands in Rule 2, `_PLAN_TASKS_FLOOR=legacy` reverts to the nine signals above without editing rules. Do not delete it as dead config, and do not assume it is exercised — it has no behavioral test until a widening exists to revert.

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

After Rules 1-3 produce a tier and the PRD frontmatter override (above) settles `final_tier`, compute the `qwen_eligible` boolean that `/work` (PRD 00031) reads to decide qwen routing. The formula (widened by PRD 00019) is:

```
qwen_eligible = task is backend (not UI) AND model in {haiku, sonnet} AND files_touched <= 3 AND task edits no public contract
```

- `model` is the tier produced by Rules 1-3 + override (the same value persisted as `metadata.model`).
- `files_touched` is the per-task file count already used in step 4.5 / Rule 1 / Rule 2.
- **UI** = the task matches the **"Gemini-first tasks"** list in `~/.claude/skills/work/SKILL.md`. Anything not matching that list is **backend**. Reuse `work`'s list as the single source of truth so producer and consumer agree by construction — do not restate the list here; if it changes in `work`, this rule inherits the change.
- **Public contract** = the task's planned edits touch an exported API signature, a schema, a wire format, or a hook registration shape (judge from the task's file slice, its `Contract`, and the PRD's Functional Decomposition). Purely internal changes — private helpers, implementation bodies, tests, docs — edit no public contract.

Each of the following yields `qwen_eligible = false` independently, with the named `qwen_excluded_reason` code:

- The task matches the UI list (Gemini's domain, not qwen's) → `ui`.
- `model == "opus"` (opus tier is never qwen-eligible) → `tier`.
- `files_touched >= 4` (qwen under-covers wide multi-file tasks) → `files`.
- The task edits a public contract (exported API signature, schema, wire format, hook registration shape) → `contract`.

**`qwen_excluded_reason`**: on **every** ineligible task, also persist `qwen_excluded_reason` — one of `ui` / `tier` / `files` / `contract`. When several conditions fail, record the FIRST failing one in the order above (`ui` → `tier` → `files` → `contract`). Eligible tasks omit the key. This makes under-routing auditable per batch: the Phase 9 Implementor Mix render counts exclusions by reason (PRD 00019).

The flag is computed **from** the classifier output; it does **not** alter the classifier. Rules 1-3 above are unchanged.

**Persist** the tier, the `qwen_eligible` flag, and (on ineligible tasks) the `qwen_excluded_reason` alongside the existing token estimate in `TaskCreate(metadata={...})`, e.g.:

```json
{"estimated_tokens": 72000, "est_context_peak": 92000, "model": "sonnet", "qwen_eligible": true}
```

```json
{"estimated_tokens": 90000, "est_context_peak": 110000, "model": "sonnet", "qwen_eligible": false, "qwen_excluded_reason": "files"}
```

`qwen_eligible` is persisted on **every** task `plan-tasks` creates. `/work` reads the field directly and does no re-judging — it routes per `qwen_eligible` + its own qwen infra preflight (see `~/.claude/skills/work/SKILL.md`).

On legacy plans created before PRD 00025, `metadata.model` is simply absent — `/work` falls back to omitting the Agent `model` parameter so subagents inherit the session model (backwards-compatible). Likewise, on legacy plans created before PRD 00032, `metadata.qwen_eligible` is absent and `/work` treats it as `false` (routes to Claude at the task's tier); plans created before PRD 00019 lack `qwen_excluded_reason`, which readers treat as `unknown` — never an error.

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
- **Derived-structure note**: when step 3 derived the Functional Decomposition or Dependency Graph from the Requirements (the PRD stated neither), say so — one line naming what was derived, so the reviewer treats the sequencing as inferred rather than PRD-pinned.
- **Irreducible-coupling reports**: for every `>=4`-file backend task kept whole because step 4.6's eligibility trigger judged it not cleanly separable, report the task and the coupling. The task will route to Claude (not qwen) at its tier — surface why so the planner sees the routing consequence rather than the task being silently kept whole.
- **PRD-vs-design contract conflicts**: when a design doc was consumed (step 3) and any task's `Contract` was taken from the design doc over a conflicting PRD statement, list each conflict (the PRD's version vs the design doc's, and which task). The design doc won; surface the divergence so the planner can confirm the design's refinement was intended.

## Granularity Guide

| Too coarse | Properly granular |
|------------|-------------------|
| "Add user authentication" | "Create User model with email, passwordHash in src/models/" |
| "Build the API" | "Add POST /users endpoint accepting {email, password}, return 201" |
| "Handle errors" | "Add try/catch in UserService.create(), throw ServiceError on failure" |

See `references/task-examples.md` for more examples.

## Reference Files

- `references/task-examples.md` - Good vs bad task examples
