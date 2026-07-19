# Review Gate (`phase: "review"`)

Routed here when `state.phase` is `"review"` — or a legacy `"blind"`/`"doubt"`
value from a pre-00015 state file, which maps to `review` on resume. Each review
cycle runs in its own fresh session: review (Phase 4) → decision gate (Phase 5)
→ rework (Phase 6). On convergence, Phase 5 hands off to the finalize session
(**review → done**), skipping rework; otherwise Phase 6, after rework, hands off
to a fresh session for the next cycle (**review → review**) — until convergence
or the cap. Blind and doubt scrutiny are LENSES inside every review cycle, not
separate phases. Core `SKILL.md` (always loaded) carries the shared mechanics.

## Phase 4: Review

**Skip the entire review-rework loop if:** `"review"` is in `phases_completed` — the loop already converged in a prior session and handed off (see "Hand off to the finalize session" in Phase 5). Skip Phases 4, 5, and 6, and resume directly at Phase 9 (`references/phase-done.md`).

**Skip this cycle's review if:** A review file exists in `dev/local/reviews/` for the current cycle (filename pattern `{prd-name}-review-{cycle}.md`).

Invoke `/review-work-completion` skill. Every cycle runs ALL lenses (its roster, PRD 00015): Alice (consensus), Blake (blind, PRD-only), Bob (doubt rubric R1-R5 + de-slop; Claude fallback when codex is down), Carl (UI, optional), Quinn (local qwen, advisory weight — unique findings create no tasks; optional, active only when the qwen preflight completion probe passes), plus Eve as a fifth lens when `state.doubt_reviewer == "fable"`. The skill's consolidation records `state.doubts_rubric_verdicts` from Bob's rubric lines (replaced each cycle; the final cycle's verdicts are what Phase 9 renders).

After completion, stay on `phase: "review"` and `next_phase: "review"` (the decision gate is part of the review surface).

## Phase 5: Decision Gate

### Cap check — evaluate after reading review, before rework dispatch

The cap is a gate on REWORK, not on Phase 5 itself. **First, read the review output** (see "Read the review output" further below). If it converged (no unresolved findings remain), the cap is irrelevant — proceed directly to Outcomes "No issues found" → finalize hand-off. The PRD success metric "passes review within three cycles is completely unaffected" requires this: a clean cycle-3 convergence at cap=3 must reach the finalize session, not cap-pause.

Otherwise (unresolved findings remain), before evaluating the Safety Checks table below, check whether the review-rework cycle cap has been reached.

Read `state.cycle` (starts at 1; the number of the review cycle just completed) and `state.rework_cap` (the effective cap, set by Phase 0 from PRD frontmatter — default 3; see the frontmatter parse table in `references/phase-build.md`).

**Rework is allowed while `cycle < cap`; when `cycle >= cap` AND rework would otherwise be dispatched, the gate pauses instead of reworking.**

Worked example, cap 3:

- cycle 1 review fails → `1 < 3` → rework → cycle 2.
- cycle 2 fails → `2 < 3` → rework → cycle 3.
- cycle 3 fails → `3 >= 3` → **pause, no 4th rework**.
- cycle 3 converges (0 findings) → cap irrelevant → finalize hand-off (no pause).

Cap 5 yields five review cycles before the pause (cycles 1-4 → rework, cycle 5 → pause).

When the cap is hit AND the review did not converge (`state.cycle >= state.rework_cap` AND unresolved findings remain), branch on loop mode (PRD 00017):

- **Loop mode (`$_AUTOPILOT_LOOP` set) — cap-out defers, never pauses.** Any unresolved CRITICAL finding → stall the PRD (follow `references/recovery.md` → "Loop-mode stall procedure", `site: "cap_critical"`) and continue the batch. Otherwise (all unresolved findings ≤ high): append each to `deferred_decisions` as `{"type": "cap-overflow", "issue": ..., "severity": ..., "consensus": ...}`, proceed to the finalize hand-off as converged-with-deferrals, and make the banner name the deferral count (`── cap reached: {k} findings deferred to batch end ──`). Stop polishing, not the batch.
- **Interactive — perform the Cap-pause behavior** (see below) and STOP — do NOT continue into the rest of Phase 5 (no Classification, no Outcomes).

When the cap is NOT hit (or the review converged with no findings), continue with the normal Outcomes flow below.

### Cap-pause behavior

Executed only when the Cap check above fired on the INTERACTIVE branch (`state.cycle >= state.rework_cap` AND the review did not converge AND `$_AUTOPILOT_LOOP` is unset — loop mode defers/stalls instead, per the Cap check). This sub-section is the ONLY writer of the `cap_pause_reason` state field; it is a separate top-level field from `stall_reason` (which has different shapes — `oversized_task`, `subagent_prompt_overrun`, `escalation_exhausted` — and a different lifecycle).

1. **Collect unresolved findings.** Read the current review-cycle output (the same review file Phase 4 produced) and gather every finding that has not yet been resolved by an earlier cycle. Format each finding minimally — at least `{"issue": <description>, "severity": <"critical"|"high"|"medium"|"low">, "consensus": <"N/M">}` — additional fields are allowed.

2. **Set `cap_pause_reason`** with `statectl set <state.json> cap_pause_reason '<json>'` (statectl merges — sibling fields are preserved), where `<json>` is the bare object value (NOT a `"cap_pause_reason": {...}` key/value fragment — that is invalid JSON for the value arg):
   ```json
   {
     "cycle": <state.cycle>,
     "cap": <state.rework_cap>,
     "unresolved_findings": [ ... ]
   }
   ```

3. **Set `state.phase` and `state.next_phase`.** Both become `"paused"`. The Phase 0 Cap-Pause Resume Handler (`references/phase-build.md` abort handlers → `references/recovery.md`) is what clears these on resume.

4. **Best-effort dashboard hint (optional).** MAY set `state.needs_attention = true`. This is a hint only — `needs_attention` is dashboard-only state with no automatic clearer since the pidash hooks were retired (PRD 00063; tracon owns the lifecycle per PRD 00062), and it MUST NOT be relied on as the pause indicator. The authoritative cap-pause signal is `phase == "paused"` PLUS `cap_pause_reason` being set (NOT `needs_attention`).

5. **The pause halts the loop by state alone.** Step 3 set `state.phase = "paused"`; the loop wrapper's decision table maps a paused state to "notify the user and stop the loop", leaving `state.json` intact. The user re-invokes `/run-autopilot` to handle the pause.

6. **Print the cap-pause banner:**
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── CAP PAUSE (cycle {n}/{cap}) ─────
   ── {k} unresolved findings — see state.json cap_pause_reason ───────
   ── re-invoke /run-autopilot to resume or abandon ───────────────────
   ```
   Substitute `{prd-name}` from `state.prd` (strip the `.md` extension), `{n}` from `state.cycle`, `{cap}` from `state.rework_cap`, and `{k}` from `len(unresolved_findings)`.

7. **STOP.** Do NOT proceed to Phase 6. Do NOT continue into Classification, Outcomes, or the finalize hand-off sub-section. The paused `state.json` is the durable signal that this PRD is awaiting user action; the Phase 0 Cap-Pause Resume Handler picks it up on the next `/run-autopilot` invocation.

Read the review output. Categorize each finding using `references/decision-framework.md`.

### Safety Checks — evaluate BEFORE classifying individual issues:

| Condition | Action |
|-----------|--------|
| >10 follow-up tasks from review | Interactive: PAUSE (scope alarm — ask user before proceeding). Loop mode (PRD 00017): keep the top 10 by severity, defer the rest to the batch deferred JSON as `{"type": "scope-overflow", ...}`, log one line, and continue — mirroring the doubt >5 overflow rule |
| Issue count not decreasing vs previous cycle | LOG and continue — a steady cycle is not a failure; the Phase 5 rework cap is the backstop |
| Same issue reappearing after previous fix | Route to research-then-decide Protocol B |
| A reviewer or sub-skill errored transiently during this review cycle | LOG and continue using the reviewers/sub-skills that succeeded (graceful degradation - e.g. a quota-exhausted reviewer is skipped, per the review skill). PAUSE only if the cycle cannot complete at all (no reviewer produced parseable output). A single transient error must not break an unattended run. |

### Classification (per finding):

**Auto-fix** (proceed without asking):
- Low severity, any consensus
- Medium severity, clear mechanical fix
- Medium severity, 1/3 consensus
- Any severity where fix is additive only (adds code/tests, doesn't modify signatures/types/schemas)

**Research-then-decide** (run protocol, then auto-fix or defer):
- New dependency needed -> Protocol A from `references/decision-framework.md`
- Recurring issue (appeared in previous cycle) -> Protocol B
- High + data model change -> Protocol C
- High + touches public API -> Protocol D

Execute the research protocol. If verdict is "proceed", treat as auto-fix. If verdict is "escalate", defer to batch end. Log with full `research` field in either case.

**Defer to batch end** (log, don't PAUSE):
- Critical severity, always
- Requirements ambiguity (PRD says X, code does Y)
- Research-failed items (verdict "escalate" from research protocols)

**PAUSE** (present to user, block progress) — these are blocking escalations; resolve via Outcomes "Has blocking escalation" below:
- Decision blocks subsequent tasks (e.g. API shape needed before frontend can proceed)
- Data model choice that all remaining work depends on

(**Interactive:** present via `AskUserQuestion`. **Loop mode (`$_AUTOPILOT_LOOP` set):** never call `AskUserQuestion` and never pause the batch — the Outcomes "Has blocking escalation" row routes these to the **Loop-mode stall procedure** with `site: "blocking_escalation"` and continues. Scope alarm — >10 follow-ups — is deliberately NOT in this list: the Safety Checks table above already defers-and-continues it in loop mode as a `scope-overflow` record, so it never pauses AND never stalls.)

Log every decision in the state file (`autonomous_decisions` or `deferred_decisions`); note the review cycle (`state.cycle`) in the entry's Decision text. The Phase 9 audit render reads these arrays — do not write `audit.md` here.

### Outcomes:

- **All auto-fixable, no deferrals, no blockers** → proceed to Phase 6
- **Has deferrals but no blockers** → log deferred items to `dev/local/autopilot/deferred/{batch_id}-deferred.json`, proceed to Phase 6 with auto-fixable items only
- **Has blocking escalation** →
  - **Interactive:** PAUSE. Present only the blocking issue(s) to user via `AskUserQuestion`. Wait for decision. After user responds, proceed to Phase 6.
  - **Loop mode (`$_AUTOPILOT_LOOP` set):** there is no human to answer — do NOT pause the batch. Follow the **Loop-mode stall procedure** (`references/recovery.md`) with `site: "blocking_escalation"`, recording the blocking issue(s) in the deferred JSON `detail`, and continue the batch. The parked PRD, on un-park, re-enters the build gate and the decision resurfaces interactively.
- **No issues found** → the review-rework loop has converged (all lenses, including blind and doubt, passed this cycle). Hand off to the finalize session (see below).

### Hand off to the finalize session

When the review-rework loop has converged (the "No issues found" outcome above, including loop-mode converged-with-deferrals from the cap check), do NOT continue into Phase 9 in this session. Run the **Session handoff procedure** (core `SKILL.md` § Session Loop) with the **review → done** site row — it adds `"review"` to `phases_completed` (the marker Phase 4's loop-level skip reads on resume) and sets `phase`/`next_phase` to `"done"` — and print:

```
── AUTOPILOT ── PRD: {prd-name} ── review-rework loop complete ─────
── AUTOPILOT ── handing off to finalize session ────────────────────
```

The next session runs Phase 9 (`references/phase-done.md`), skipping Phases 4-6 via the loop-level skip in Phase 4.

## Phase 6: Rework

**Session model:** Phase 6 runs in the same session as Phase 4 (the `review` surface) — one review cycle (Phase 4 → 5 → 6) per session. The per-task tier escalation in `/work` step 3 (dispatching each task as a separate Agent call at `metadata.model`) means the actual rework implementation runs at the escalated tier (haiku/sonnet/opus) regardless of the outer session. No separate *within-cycle* rework handoff is needed: the review session handles review quality; per-task dispatch handles implementation correctness. (The **review → review** handoff to the *next* cycle's session happens after `/work` returns — see "After /work returns" below.)

Two task kinds enter this phase:

- **Review-flagged original-plan tasks** (`[C{cycle}]` prefix): a task `/work` already attempted that the review phase wants re-done. These are retries — escalate the model tier per the rule below.
- **Decision gate follow-ups** (`[D{cycle}]` prefix): brand-new tasks created from decision gate resolutions. These are first-pass work, not retries — they default to `sonnet` (no escalation applies). Apply the `/plan-tasks` Tier classifier here too if you have the inputs (PRD slice, files-touched estimate); otherwise default `sonnet`.

Both prefixes use the current cycle number. Both kinds dispatch through the same rework-mode `/work` invocation — see "Dispatch rework" below for how each gets its tier set and queued.

### Hydrate before any TaskUpdate (PRD 00025)

**Run the "Hydrate TaskList from state.tasks" sub-step** (core `SKILL.md` § State Management) BEFORE the "Escalate review-flagged tasks by tier" section's `TaskUpdate` calls. The rework session almost always inherits an empty TaskList from the post-Phase-3 handoff — running escalation TaskUpdate calls against an empty tracker either errors on unknown IDs or silently no-ops, losing the status→pending transition and dashboard visibility. Hydration is the first action of Phase 6, no exceptions.

### Escalate review-flagged tasks by tier (PRD 00025)

**Escalation caveat — diagnose the failure before escalating.** The escalation ladder (`references/model-ladder.md` § Capability ladders) assumes a review failure means the model wasn't capable enough. That is often wrong. A review failure caused by a **spec-transmission gap** — the implementer built a self-consistent *wrong* thing because the task description never carried the PRD's exact contract (field names, enum values, hook kind, thresholds) — is not a capability failure. Escalating the tier costs more and does not address the cause: a stronger model fed the same thin task description can fail the same way. Before escalating, look at the cycle's review findings. If they are predominantly spec-misread (wrong schema, wrong API, missing feature, wrong artifact kind) rather than implementation-quality bugs (edge cases, perf, logic errors), the real fix is a **corrected task description** — and the review's follow-up tasks should already carry the exact contract verbatim. In that case keep the **same tier**; do not escalate. Record the decision and rationale in `autonomous_decisions` (the Phase 9 audit render reads it). Escalate the tier only when the prior attempt genuinely struggled on a correctly-specified task. (Root cause and the plan-tasks fix: `references/design-rationale.md` § Escalation diagnosis; the authoring rule is `plan-tasks/SKILL.md` step 4.)

For each review-flagged original-plan task in the current cycle's review output:

1. Look up `state.tasks[i].attempts[-1]` — the last `/work` pass's entry, written by `/work` Attempt logging.
2. If `state.tasks[i].attempts` is empty or absent (legacy-plan task with no attempt log — covered by step 3's "no prior attempt" case and the closing paragraph after step 5), skip this step entirely and proceed to step 3's next-tier computation. Otherwise, rewrite that entry's `outcome` to `"review_flagged"` (it was `"completed"` when `/work` exited; review just flagged it).
3. Compute the next tier by climbing one rung up the capability ladder (`references/model-ladder.md` § Capability ladders):
   - **no prior attempt** (`state.tasks[i].attempts` empty or absent — covers both pre-PRD-00025 legacy plans and PRD-00025 tasks that crashed before the first attempt log wrote) → treat as `"sonnet"`; next is `"opus"`. **Metric caveat**: when this branch fires for a PRD-00025 task whose actual pass ran `haiku`, it inflates the apparent sonnet→opus escalation rate vs the PRD's ≤2% target. The branch is rare (crash before first attempt-log write) and the conservative jump-to-opus is the right correctness choice; just don't read sonnet→opus telemetry without accounting for it.
   - last attempt at any other tier → next is the next rung up per `references/model-ladder.md` § Capability ladders.
   - last attempt at `"opus"` → **escalation exhausted**: `opus` is the top rung of the capability ladder, so the task cannot be reworked automatically. Do NOT continue to step 4 — **follow `references/recovery.md` → "Rework escalation exhausted"** (rewrites the last attempt's `outcome` to `"rework_failed"`, moves the PRD to `dev/local/prds/hold/`, advances to the next PRD).
4. Otherwise (chain not exhausted), persist the escalated tier in BOTH places so `/work` and the state snapshot stay in sync, then queue the task for rework:
   - `TaskUpdate(taskId="<id>", metadata={"model": "<next_tier>", "escalation_reason": "review_flag", "escalated_from": "<prev_tier>"})` — canonical source `/work` reads via `TaskGet` (see `work/SKILL.md` "Per-task model dispatch"). `<prev_tier>` is the tier step 3 escalated from. These two fields carry onto the new attempt entry `/work` writes at the escalated tier, keeping a review-driven escalation distinguishable from `/work`'s own in-loop `escalation_reason:"gate_failure"` in `attempts[]` (`references/state-schema.md`).
   - Write the same value to `state.tasks[i].model` — the snapshot the dashboard and the next review cycle read.
   - Append the task ID to `state.rework_task_ids` (create the array if absent).
5. Reset `state.tasks[i].status` back to `"pending"` via `TaskUpdate(taskId, status="pending")` so `/work` will iterate it again. **Reverse status transitions (`completed` → `pending`) are supported** — the hydration sub-step relies on the same mechanism to restore `completed` status on a fresh session, and the PostToolUse status-sync hook treats whatever `TaskUpdate` writes as the new ground truth.

The "no prior attempt" case in step 3 covers both pre-PRD-00025 legacy plans (which lack `metadata.model` and `attempts[]` entirely) and PRD-00025 tasks that crash before the first attempt log writes (rare but possible). Both are treated as `"sonnet"` for the next-tier computation, so first escalation goes to `"opus"`.

**In-loop ↔ Phase-6 composition.** Step 2's outcome rewrite (`"completed"` → `"review_flagged"`) only ever touches `attempts[-1]` — the terminal rung — which is never an `"escalated"` row (those are earlier history from `/work`'s in-loop diagnosis), so `/work`'s widened one-entry-per-rung cardinality does not corrupt this read. If the in-loop path already escalated all the way to `opus`, `attempts[-1].model == "opus"` and step 3's next-tier computation above routes straight into the "escalation exhausted" branch — no double-count, no skipped rung. Phase 6 composes cumulatively with in-loop escalation because it always reads the terminal rung's entry.

### Dispatch rework

Build the rework batch from two sources:

1. **Review-flagged `[C{cycle}]` tasks** — `state.rework_task_ids` already contains their IDs (appended in step 4 above), and their `metadata.model` + `state.tasks[i].model` already carry the escalated tier.
2. **Decision gate `[D{cycle}]` follow-ups** — for each new task created from a decision gate resolution:
   - Compute the tier: start with the `/plan-tasks` Tier classifier output if the inputs are available (PRD slice, files-touched estimate); otherwise default to `sonnet`. Then apply the `default_model` floor **exactly as `/plan-tasks` step 4.7 defines it** (the single source of truth): `final_tier = max(tier, default_model)`; re-parse the PRD frontmatter from `dev/local/prds/wip/<state.prd>` at Phase 6 runtime with the same YAML-tolerant parse Phase 0 applies; absent frontmatter or unset field → silent pass-through of the classifier tier; malformed YAML or invalid value → warn one line and pass through. `default_model` is intentionally NOT persisted to state — the PRD frontmatter is the single source of truth.
   - `TaskCreate(metadata={"model": final_tier, ...})`.
   - Append the new task's ID to `state.rework_task_ids` AND insert a merge-preserving snapshot into `state.tasks[]` carrying `{id, name, status, model}` plus any classifier-produced fields (`estimated_tokens`, `est_context_peak`) — same merge-preserving rule Phase 3 establishes for the original-plan snapshot. The dashboard sees the new task and `/work` rework mode iterates it.

Hydration already ran at the top of Phase 6 (see "Hydrate before any TaskUpdate" above) — the rework session inherits a populated TaskList by this point, so the `TaskUpdate` and `TaskCreate` calls operate on real tasks.

After both sources are merged into `rework_task_ids`, update state (the sync hook maintains the task counts). Invoke `/work` — it reads `state.rework_task_ids` and enters **rework mode** (see `work/SKILL.md` "Rework-mode task filter"), processing only the listed IDs at the tier each task carries in `metadata.model`; non-listed completed tasks are skipped.

The work skill may parallelize independent rework tasks when `superpowers:dispatching-parallel-agents` is available (see work skill's "Parallel dispatch for independent rework fixes").

### After /work returns

Apply steps 1-3 with `statectl set` (one call per field; each write is individually atomic), immediately before the banner and turn-end. The load-bearing durable write is the `cycle` increment — a single atomic `statectl set`; the `phase`/`next_phase` re-affirmations are belt-and-suspenders (both are already `"review"` throughout the review gate, so even a partial application across the three calls cannot misroute the phase or mis-apply the cap). A batch/patch verb landing all three in one write is out of scope here (owned by PRD 00051's writer boundary):

1. Clear `state.rework_task_ids` (set to `[]`).
2. **Increment `state.cycle` and persist it to `state.json` in this step** (a durable write, not an in-memory bump). The Phase 5 cap gate (`state.cycle >= state.rework_cap`) reads `state.cycle`; skipping the persisted increment blinds it — that exact miss let a loop run past its cap once (`references/design-rationale.md` § Persisted cycle increment). This write is not optional.
3. Re-affirm `phase: "review"` and `next_phase: "review"` (both are already `"review"` throughout the review gate — this re-affirms, it does not first-set). Do NOT rewrite `state.tasks` here — `/work` already wrote `attempts[]` entries directly to `state.tasks` during rework, and a bare TaskList snapshot would strip them; the sync hook keeps `tasks_total`/`tasks_completed` current.
4. **Hand off to a fresh session for the next cycle.** The loop does NOT continue in-session — a multi-cycle review session outlives the wall-clock cap and is SIGTERMed mid-cycle, discarding in-flight external-CLI reviewer work. Run the **Session handoff procedure** (core `SKILL.md` § Session Loop) with the **review → review** site row — steps 1-3 already wrote its state (`phase`/`next_phase: "review"`, incremented `cycle`, `phases_completed` untouched) — print the cycle-handoff banner below, and **STOP** (do not re-enter Phase 4 in this session). The wrapper's continue branch relaunches; the fresh session routes `phase: "review"` → Phase 4, which runs `state.cycle` (the incremented cycle; no review file exists for it yet) with no re-review of the prior cycle and no skip-to-done (`phases_completed` lacks `"review"` until convergence).

Cycle-handoff banner (`{prd-name}` = `state.prd` minus `.md`). **Cycle derivation (avoid the off-by-one):** step 4 runs AFTER step 2's durable increment, so `state.cycle` at print time is ALREADY the next cycle — `{n}` (the just-completed cycle) = `state.cycle - 1`, `{n+1}` (the cycle handed off to) = `state.cycle`:

```
── AUTOPILOT ── PRD: {prd-name} ── Cycle {n} rework complete ───────
── AUTOPILOT ── handing off to fresh session for cycle {n+1} ───────
```

Cross-references: `references/state-schema.md` (`rework_task_ids`, `tasks[].model`, `tasks[].attempts`, `stall_reason` shapes); `work/SKILL.md` Per-task model dispatch, Attempt logging, Rework-mode task filter.

## De-slop is part of the doubt lens

There is no separate between-session de-slop pass. De-slopping happens **inside every review cycle** — Bob (codex) carries the doubt + de-slop lens in the `review-work-completion` roster, with a Claude fallback when codex is unavailable, so the lens never silently drops. If you are checking how de-slop is wired, look at the review roster, not the `autoclaude` function. (Why the standalone wrapper pass was removed: `references/design-rationale.md` § De-slop.)
