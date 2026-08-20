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

Invoke `/review-work-completion` skill. Every cycle runs ALL lenses (its roster, PRD 00015): Alice (consensus), Blake (blind, PRD-only), Bob (doubt rubric D1-D5 + de-slop; Claude fallback when codex is down), Carl (UI, optional), plus Eve as a fifth lens when that skill's step 1 doubt-reviewer resolution rule activates her. That rule is the single home of the Codex doubt-roster guard; this phase only invokes it. The skill's consolidation records `state.doubts_rubric_verdicts` from Bob's rubric lines (replaced each cycle; the final cycle's verdicts are what Phase 9 renders).

After completion, stay on `phase: "review"` and `next_phase: "review"` (the decision gate is part of the review surface).

## Phase 5: Decision Gate

### Cap check — evaluate after reading review, before rework dispatch

The cap is a gate on REWORK, not on Phase 5 itself. **First, read the review output** (see "Read the review output" further below). Convergence requires BOTH conditions: **no unresolved CRITICAL or HIGH finding remains**, AND the doubt-roster constraint gate certifies (the exact command lives in Outcomes "Converged (no unresolved CRITICAL/HIGH)" below — run it now when no CRITICAL/HIGH is left). If both hold, the cap is irrelevant — proceed directly to Outcomes "Converged (no unresolved CRITICAL/HIGH)" → tail sweep → finalize hand-off. The PRD success metric "passes review within three cycles is completely unaffected" requires this: a clean cycle-3 convergence at cap=3 must reach the finalize session, not cap-pause.

**"Unresolved" excludes** (PRD 00094): findings this cycle's gate discarded with a verified reason, and **settled deferrals** — a HIGH matching an entry already in `state.deferred_decisions` or recorded as deferred by a prior cycle. Counting a settled deferral blocks convergence for a decision already taken (2 of 3 oranges in the 00105 batch's cycle 2 were exactly this). Until PRD 00095's deterministic matcher lands, matching a finding to a settled deferral is this gate's judgment call on issue text plus file.

**A CRITICAL is never a settled deferral.** Classification below routes "Critical severity, always" to Defer-to-batch-end, so every CRITICAL lands in `deferred_decisions` the cycle it is raised. If the exclusion covered CRITICALs, one raised in cycle 1 would be "settled" by cycle 2 and converge — turning the cap-out branch's `site: "cap_critical"` stall into a path that ships an open CRITICAL. **Deliberate narrowing of PRD 00094**, whose text says "C/H" here but whose guard metric is zero escaped CRITICAL/HIGH, whose cap-out prose assumes C/H persists across cycles, and whose own worked test case is a HIGH. A CRITICAL blocks until it is fixed or the cap-out branch stalls the PRD.

**Medium and Low findings never block convergence.** They are swept, not dropped — see "Tail sweep" below. Nothing else about non-converged cycles changes: Classification and rework still process every severity; only the exit test moved.

If no CRITICAL/HIGH remains but the constraint gate exits 2 (unmet), this is NOT convergence — the Outcomes "Converged (no unresolved CRITICAL/HIGH)" exit-2 branch routes it forward (below cap / at cap) directly, without re-entering this Cap check.

Otherwise (an unresolved CRITICAL/HIGH remains), before evaluating the Safety Checks table below, check whether the review-rework cycle cap has been reached.

Read `state.cycle` (starts at 1; the number of the review cycle just completed) and `state.rework_cap` (the effective cap, written by Phase 0's `autopilot frontmatter` call from the PRD frontmatter — default 2; `cli/frontmatter.py` defines the accepted values, `references/phase-build.md` § Frontmatter parse shows the call).

**Rework is allowed while `cycle < cap`; when `cycle >= cap` AND rework would otherwise be dispatched, the gate pauses instead of reworking.**

Worked example, cap 3:

- cycle 1 review fails → `1 < 3` → rework → cycle 2.
- cycle 2 fails → `2 < 3` → rework → cycle 3.
- cycle 3 fails → `3 >= 3` → **pause, no 4th rework**.
- cycle 3 converges (no unresolved CRITICAL/HIGH) → cap irrelevant → sweep, then finalize hand-off (no pause).

Cap 5 yields five review cycles before the pause (cycles 1-4 → rework, cycle 5 → pause).

When the cap is hit AND the review did not converge (`state.cycle >= state.rework_cap` AND an unresolved CRITICAL/HIGH remains), branch on loop mode (PRD 00017). Under the severity bar these branches can only fire while a CRITICAL/HIGH persists; they are otherwise unchanged:

- **Loop mode (`$_AUTOPILOT_LOOP` set) — cap-out defers, never pauses.** Any unresolved CRITICAL finding → stall the PRD (follow `references/recovery.md` → "Loop-mode stall procedure", `site: "cap_critical"`) and continue the batch. Otherwise (all unresolved findings ≤ high): append each to `deferred_decisions` as `{"type": "cap-overflow", "issue": ..., "severity": ..., "consensus": ...}`, append the `review_converged` line from **Convergence metric** below with `outcome: "cap_deferred"`, proceed to the finalize hand-off as converged-with-deferrals, and make the banner name the deferral count (`── cap reached: {k} findings deferred to batch end ──`). Stop polishing, not the batch.
- **Interactive — perform the Cap-pause behavior** (see below) and STOP — do NOT continue into the rest of Phase 5 (no Classification, no Outcomes).

When the cap is NOT hit (or the review converged), continue with the normal Outcomes flow below.

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

5. **The pause halts the loop by state alone.** Step 3 set `state.phase = "paused"`; the loop driver's decision table (`cli/loop.py`) maps a paused state to "notify the user and stop the loop", leaving `state.json` intact. The user re-invokes `/run-autopilot` to handle the pause.

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

**Discard — contradicts computed facts** (PRD 00095): a finding asserting a countable value about an entity the cycle's mechanical-facts block covers, where the block says otherwise (a claimed 58-line function the block computes at 44), is **discarded, not researched**. The block is computed from `ast`; the reviewer is guessing. Record the discard in the ledger with reason `contradicts computed facts`, which is also what stops the same wrong claim returning next cycle. This applies only to values the block actually covers — a countable claim about anything else is judged normally.

**Defer to batch end** (log, don't PAUSE):
- Critical severity, always
- Requirements ambiguity (PRD says X, code does Y)
- Research-failed items (verdict "escalate" from research protocols)

**PAUSE** (present to user, block progress) — these are blocking escalations; resolve via Outcomes "Has blocking escalation" below:
- Decision blocks subsequent tasks (e.g. API shape needed before frontend can proceed)
- Data model choice that all remaining work depends on

(**Interactive:** present via `AskUserQuestion`. **Loop mode (`$_AUTOPILOT_LOOP` set):** never call `AskUserQuestion` and never pause the batch — the Outcomes "Has blocking escalation" row routes these to the **Loop-mode stall procedure** with `site: "blocking_escalation"` and continues. Scope alarm — >10 follow-ups — is deliberately NOT in this list: the Safety Checks table above already defers-and-continues it in loop mode as a `scope-overflow` record, so it never pauses AND never stalls.)

Log every decision in the state file (`autonomous_decisions` or `deferred_decisions`); note the review cycle (`state.cycle`) in the entry's Decision text. The Phase 9 audit render reads these arrays — do not write `audit.md` here.

### Settled-decisions ledger (PRD 00095)

**Every deferral and every discard also appends to `dev/local/reviews/{prd-stem}-ledger.json`**, a JSON array created on first write (`{prd-stem}` = `state.prd` minus `.md`). It lives beside the review files rather than in `state.json` so it survives batch end and parked-PRD resumes, and dies with the PRD like the other review satellites.

```json
{"cycle": <state.cycle>, "disposition": "settled-deferral"|"discarded", "severity": ..., "issue": "<the finding text, verbatim>", "file": ..., "reason": "<why it was settled>"}
```

`issue` is the finding's own words, not a summary — the matcher in `consolidate_findings.py` compares against it. Write it with the Write tool (read the existing array, append, write back); a ledger that fails to write is logged and does not block the cycle.

The ledger is what stops a settled call from being re-argued every cycle. It is read in three places: `review-work-completion` step 4 appends it to the implementation-aware prompts, step 6 passes it as `--ledger` so Blake's re-raises are auto-dismissed, and the Cap check's settled-deferral exclusion above is decided from it.

### Outcomes:

The first three rows describe a cycle that did NOT converge — the Cap check above already routed a converged cycle to the last row. A cycle whose only survivors are Medium/Low has converged; it does not "proceed to Phase 6" for another cycle.

- **All auto-fixable, no deferrals, no blockers** → proceed to Phase 6
- **Has deferrals but no blockers** → run `autopilot defer --prd <filename> --batch <batch_id> --json '<record>'` for each deferred item, proceed to Phase 6 with auto-fixable items only
- **Has blocking escalation** →
  - **Interactive:** PAUSE. Present only the blocking issue(s) to user via `AskUserQuestion`. Wait for decision. After user responds, proceed to Phase 6.
  - **Loop mode (`$_AUTOPILOT_LOOP` set):** there is no human to answer — do NOT pause the batch. Follow the **Loop-mode stall procedure** (`references/recovery.md`) with `site: "blocking_escalation"`, recording the blocking issue(s) in the deferred JSON `detail`, and continue the batch. The parked PRD, on un-park, re-enters the build gate and the decision resurfaces interactively.
- **Converged (no unresolved CRITICAL/HIGH)** → before treating the cycle as converged, run `autopilot gate --review-file <this cycle's review file> --require-codex-guard --assert-constraint-met` (flag semantics: `cli/gate.py` module docstring; PRD 00107 absorbed the old `check_review_file.py` path, which survives as a shim). It checks the constraint line only, so a converging cycle may legitimately carry `Verdict: N findings`. Exit 0 → the doubt-roster constraint certified; the review-rework loop has converged (all lenses, including blind and doubt, passed this cycle). Append the `review_converged` line from **Convergence metric** below with `outcome: "converged"`, run the **Tail sweep** below, then hand off to the finalize session (see below). Exit 2 → the constraint did NOT hold; do NOT converge this cycle. Do NOT re-run the Cap check above — its own convergence test already needs this same gate (see "Cap check" above), so re-entering it only recreates this same bullet. Instead, classify the unmet constraint as one unresolved CRITICAL finding and route forward directly on `state.cycle` vs `state.rework_cap`: below cap → continue to Phase 6 for another review cycle; at cap → the existing cap-out machinery applies with no new mechanism — **loop mode**: the "Any unresolved CRITICAL finding" branch above (stall via `references/recovery.md` → Loop-mode stall procedure, `site: "cap_critical"`; the batch continues); **interactive**: the Cap-pause behavior above (include the constraint among the collected `unresolved_findings`). The batch keeps draining either way; this does not create a new batch-halt class.

### Convergence metric

Both finalize paths append ONE line to `dev/local/autopilot/loop-metrics.jsonl` — the converged path (below, before the tail sweep is dispatched) and the loop-mode cap-out path (Cap check above). Cap-outs are the baseline failures, so a median computed only from clean convergences would flatter the gate:

```json
{"event": "review_converged", "prd": <state.prd>, "batch": <state.batch.id>, "cycles_to_converge": <state.cycle>, "outcome": "converged"|"cap_deferred", "ts": <epoch seconds>}
```

`outcome` is `"converged"` on the converged path and `"cap_deferred"` on the cap-out path. Append it, then mirror it into the GC-exempt ledger the same way the wrapper mirrors its own rows (`loop-metrics.jsonl` is trashed at 14 days; `ledger/` is not):

```bash
printf '%s\n' '<the json line>' >>dev/local/autopilot/loop-metrics.jsonl
mkdir -p dev/local/autopilot/ledger
printf '%s\n' '<the json line>' >>dev/local/autopilot/ledger/loop-metrics.jsonl
```

The `mkdir -p` is not optional: `ledger/` is created lazily by whichever writer gets there first, and on a repo whose batch has not yet mirrored a session row the second append fails without it.

Existing wrapper rows carry no `event` key and are one-per-session; these rows are one-per-PRD and carry no `wall_secs`/`cost_usd`. Consumers filter on `event` — `cli/render_metrics.load_rows` already drops any row that has one, so these never inflate a session count. Read the metric back with `rg '"event":"review_converged"'` over either file; nothing renders it.

### Tail sweep

Runs once, on the converged outcome above, after the metric is emitted and before the finalize hand-off. The Medium/Low tail is **swept, not dropped**: one normal `/work` task fixes it, then the PRD finalizes. No new verification machinery.

**1. Select.** Take the converging cycle's actionable Medium/Low findings. Exclude settled deferrals, findings this gate discarded, and anything already in `deferred_decisions` — a decision already taken is not swept again. **Zero actionable Medium/Low → skip the sweep entirely** and go straight to the finalize hand-off (today's clean path, unchanged).

**2. Create.** Build ONE `[D{cycle}]` task through Phase 6's "Dispatch rework" mechanics for decision-gate follow-ups: tier from the `/plan-tasks` classifier when its inputs are available, otherwise `sonnet`, then the `default_model` floor exactly as that section computes it; `task-add`, then append the printed id to `state.rework_task_ids` — no separate snapshot insert needed, `task-add` already wrote the `state.tasks[]` entry. **The task description carries the same `### Findings (verbatim)` block** Phase 6 D-tasks use (PRD 00095) — one line per swept finding, severity, text, file, consensus — never a summary or a count.

**Split rule:** more than 10 findings → split into 2-4 tasks grouped by file or theme per `work/references/task-splitting.md` (10 is the same constant the Phase 5 scope alarm uses). The existing max-2-parallel rework rule applies unchanged.

**3. Dispatch.** Invoke `/work` in rework mode exactly as Phase 6 does. The mandatory one-verification-pass constraint is satisfied by `/work`'s own pipeline — tests-first 2.7 for behavioral fixes, the 5.5 gate, 5.6 self-deslop, 5.7 per-task review. Nothing extra runs here.

**4. Finalize.** When `/work` returns, go to the finalize hand-off below. **Do NOT increment `state.cycle`, do NOT hand off review → review, and do NOT run another review cycle.** Phase 5 never reopens after convergence — reopening rebuilds the polish loop this gate exists to remove. Print, before the hand-off banner:

```
── converged (cycle {n}): {k} medium/low findings swept ────────────
```

`{n}` is `state.cycle` (unchanged by the sweep) and `{k}` the number of findings swept, not the number of tasks.

**Sweep escapes.** A CRITICAL/HIGH raised by the sweep's own step-5.7 review is handled inside step 5.7 as today (verify, fix inline, max 3 review cycles). One that survives that cap is recorded via `autopilot defer --prd <filename> --batch <batch_id> --json '{"type": "sweep-escape", "issue": ..., "severity": ...}'` and **the PRD still finalizes**. The deferred record is what keeps the escape visible at batch end; the zero-escaped-C/H guard is measured net of these entries.

### Hand off to the finalize session

When the review-rework loop has converged (the "Converged (no unresolved CRITICAL/HIGH)" outcome above, including loop-mode converged-with-deferrals from the cap check), do NOT continue into Phase 9 in this session. Run the **Session handoff procedure** (core `SKILL.md` § Session Loop) with the **review → done** site row — one `autopilot phase-done --outcome converged` call, which sets `phase`/`next_phase` to `"done"` and appends `"review"` to `phases_completed` (the marker Phase 4's loop-level skip reads on resume) in the same commit. The marker lands because this is convergence; there is no flag to pass and none to forget. Then print:

```
── AUTOPILOT ── PRD: {prd-name} ── review-rework loop complete ─────
── AUTOPILOT ── handing off to finalize session ────────────────────
```

The next session runs Phase 9 (`references/phase-done.md`), skipping Phases 4-6 via the loop-level skip in Phase 4.

## Phase 6: Rework

**Session model:** Phase 6 runs in the same session as Phase 4 (the `review` surface) — one review cycle (Phase 4 → 5 → 6) per session. The per-task tier escalation in `/work` step 3 (dispatching each task as a separate Agent call at `state.tasks[i].model`) means the actual rework implementation runs at the escalated tier (haiku/sonnet/opus) regardless of the outer session. No separate *within-cycle* rework handoff is needed: the review session handles review quality; per-task dispatch handles implementation correctness. (The **review → review** handoff to the *next* cycle's session happens after `/work` returns — see "After /work returns" below.)

Two task kinds enter this phase:

- **Review-flagged original-plan tasks** (`[C{cycle}]` prefix): a task `/work` already attempted that the review phase wants re-done. These are retries — escalate the model tier per the rule below.
- **Decision gate follow-ups** (`[D{cycle}]` prefix): brand-new tasks created from decision gate resolutions. These are first-pass work, not retries — they default to `sonnet` (no escalation applies). Apply the `/plan-tasks` Tier classifier here too if you have the inputs (PRD slice, files-touched estimate); otherwise default `sonnet`.

Both prefixes use the current cycle number. Both kinds dispatch through the same rework-mode `/work` invocation — see "Dispatch rework" below for how each gets its tier set and queued.

### Escalate review-flagged tasks by tier (PRD 00025)

**Escalation caveat — diagnose the failure before escalating.** The escalation ladder (`references/model-ladder.md` § Capability ladders) assumes a review failure means the model wasn't capable enough. That is often wrong. A review failure caused by a **spec-transmission gap** — the implementer built a self-consistent *wrong* thing because the task description never carried the PRD's exact contract (field names, enum values, hook kind, thresholds) — is not a capability failure. Escalating the tier costs more and does not address the cause: a stronger model fed the same thin task description can fail the same way. Before escalating, look at the cycle's review findings. If they are predominantly spec-misread (wrong schema, wrong API, missing feature, wrong artifact kind) rather than implementation-quality bugs (edge cases, perf, logic errors), the real fix is a **corrected task description** — and the review's follow-up tasks should already carry the exact contract verbatim. In that case keep the **same tier**; do not escalate. Record the decision and rationale in `autonomous_decisions` (the Phase 9 audit render reads it). Escalate the tier only when the prior attempt genuinely struggled on a correctly-specified task. (Root cause and the plan-tasks fix: `references/design-rationale.md` § Escalation diagnosis; the authoring rule is `plan-tasks/SKILL.md` step 4.)

For each review-flagged original-plan task in the current cycle's review output:

1. Look up `state.tasks[i].attempts[-1]` — the last `/work` pass's entry, written by `/work` Attempt logging.
2. If `state.tasks[i].attempts` is empty or absent (legacy-plan task with no attempt log — covered by step 3's "no prior attempt" case and the closing paragraph after step 5), skip this step entirely and proceed to step 3's next-tier computation. Otherwise, rewrite that entry's `outcome` to `"review_flagged"` (it was `"completed"` when `/work` exited; review just flagged it).
3. Compute the next tier by climbing one rung up the capability ladder (`references/model-ladder.md` § Capability ladders):
   - terminal attempt with `implementor: "codex"` → re-dispatch Claude at the task's same tier; do not climb the tier. This branch takes precedence over the tier-only branches below: the codex rung's capability edge is codex → Claude at the task's own tier, so Claude-at-tier is the rung above codex.
   - **no prior attempt** (`state.tasks[i].attempts` empty or absent — covers both pre-PRD-00025 legacy plans and PRD-00025 tasks that crashed before the first attempt log wrote) → treat as `"sonnet"`; next is `"opus"`. **Metric caveat**: when this branch fires for a PRD-00025 task whose actual pass ran `haiku`, it inflates the apparent sonnet→opus escalation rate vs the PRD's ≤2% target. The branch is rare (crash before first attempt-log write) and the conservative jump-to-opus is the right correctness choice; just don't read sonnet→opus telemetry without accounting for it.
   - last attempt at any other tier → next is the next rung up per `references/model-ladder.md` § Capability ladders.
   - last attempt at `"opus"` or `"fable"` → **escalation exhausted**: `opus` is the top rung of the capability ladder and `"fable"` means the human-gated rescue rung above it was already spent (`references/model-ladder.md` § Rungs), so the task cannot be reworked automatically. Do NOT continue to step 4 — **follow `references/recovery.md` → "Rework escalation exhausted"** (rewrites the last attempt's `outcome` to `"rework_failed"`, moves the PRD to `dev/local/prds/hold/`, advances to the next PRD). That handler runs its **Fable rescue gate** first: on a human-approved ledger entry it queues one `fable` retry through step 4's requeue mechanics and returns here to "Dispatch rework" instead of stalling.
4. Otherwise (chain not exhausted), persist the escalated tier, then queue the task for rework:
   - `task-set-meta <task-id> <meta-json-file>` with payload `{"model": "<next_tier>", "escalation_reason": "review_flag", "escalated_from": "<prev_tier>"}` — canonical source `/work` reads directly from `state.tasks[i]` (see `work/SKILL.md` "Per-task model dispatch"). `<prev_tier>` is the tier step 3 escalated from. These two fields carry onto the new attempt entry `/work` writes at the escalated tier, keeping a review-driven escalation distinguishable from `/work`'s own in-loop `escalation_reason:"gate_failure"` in `attempts[]` (`references/state-schema.md`). `task-set-meta` writes `state.tasks[i].model` in the same call — there is no separate mirror write.
   - Append the task ID to `state.rework_task_ids` (create the array if absent).
5. Reset `state.tasks[i].status` back to `"pending"` via `task-set-status <task-id> pending` so `/work` will iterate it again. **Reverse status transitions (`completed` → `pending`) are supported** — `task-set-status` writes `state.tasks[i].status` directly; the ground truth is simply whatever `statectl` wrote (the PostToolUse status-sync hook this line used to cite was retired by PRD 00063 and no longer exists).

The "no prior attempt" case in step 3 covers both pre-PRD-00025 legacy plans (which lack `state.tasks[i].model` and `attempts[]` entirely) and PRD-00025 tasks that crash before the first attempt log writes (rare but possible). Both are treated as `"sonnet"` for the next-tier computation, so first escalation goes to `"opus"`.

**In-loop ↔ Phase-6 composition.** Step 2's outcome rewrite (`"completed"` → `"review_flagged"`) only ever touches `attempts[-1]` — the terminal rung — which is never an `"escalated"` row (those are earlier history from `/work`'s in-loop diagnosis), so `/work`'s widened one-entry-per-rung cardinality does not corrupt this read. If the in-loop path already escalated all the way to `opus`, `attempts[-1].model == "opus"` and step 3's next-tier computation above routes straight into the "escalation exhausted" branch — no double-count, no skipped rung. Phase 6 composes cumulatively with in-loop escalation because it always reads the terminal rung's entry.

### Dispatch rework

Build the rework batch from two sources:

1. **Review-flagged `[C{cycle}]` tasks** — `state.rework_task_ids` already contains their IDs (appended in step 4 above), and their `state.tasks[i].model` already carries the escalated tier.
2. **Decision gate `[D{cycle}]` follow-ups** — for each new task created from a decision gate resolution:
   - **Transcribe the findings verbatim (PRD 00095).** The task description carries a `### Findings (verbatim)` block: one line per source finding, quoted exactly as consolidated — severity, text, file, consensus. N findings routed into a task produce N lines. **No paraphrase, no merging findings into a theme**, and the task's acceptance criterion is "every quoted finding no longer reproduces". This is the whole point: the measured failure was an orchestrator compressing five consensus themes into three tasks, after which the finding that survived was the one nobody had written down. It also costs nothing downstream — `/work` step 2.7 writes tests from the task description, so the tests bind to the finding's own words with no change to step 2.7, and step 5.7 checks closure against the same block.
   - Compute the tier: start with the `/plan-tasks` Tier classifier output if the inputs are available (PRD slice, files-touched estimate); otherwise default to `sonnet`. Then apply the `default_model` floor **exactly as `/plan-tasks` step 4.7 defines it** (the single source of truth): `final_tier = max(tier, default_model)`; re-parse the PRD frontmatter from `dev/local/prds/wip/<state.prd>` at Phase 6 runtime, tolerating the same flat `key: value` block Phase 0 reads; absent frontmatter or unset field → silent pass-through of the classifier tier; malformed YAML or invalid value → warn one line and pass through. Read `default_model` yourself here — `autopilot frontmatter` deliberately does NOT recognize it, because Phase 0 must never write it to state (the PRD frontmatter is the single source of truth for this field). `default_model` is intentionally NOT persisted to state — the PRD frontmatter is the single source of truth.
   - `task-add <task-json-file>` with a payload carrying `{"name": ..., "model": final_tier, ...}` plus any classifier-produced fields (`estimated_tokens`, `est_context_peak`) — this creates the `state.tasks[]` entry directly with `status: "pending"`. Append the printed id to `state.rework_task_ids`. The dashboard sees the new task and `/work` rework mode iterates it.

After both sources are merged into `rework_task_ids`, update state (the sync hook maintains the task counts). Invoke `/work` — it reads `state.rework_task_ids` and enters **rework mode** (see `work/SKILL.md` "Rework-mode task filter"), processing only the listed IDs at the tier each task carries in `state.tasks[i].model`; non-listed completed tasks are skipped.

The work skill may parallelize independent rework tasks when `superpowers:dispatching-parallel-agents` is available (see work skill's "Parallel dispatch for independent rework fixes").

### After /work returns

Apply the whole advance with ONE call, immediately before the banner and turn-end:

```bash
autopilot phase-done --outcome rework
```

It commits all of it together: `rework_task_ids` cleared, `state.cycle` incremented, `phase`/`next_phase` re-affirmed as `"review"`. **The crash window this closes was real.** These used to be four separate `statectl set` calls whose ORDER mattered: the load-bearing one is the `cycle` increment, because the Phase 5 cap gate (`state.cycle >= state.rework_cap`) reads it, and skipping the persisted increment blinds that gate — that exact miss let a loop run past its cap once (`references/design-rationale.md` § Persisted cycle increment). A crash between the clear and the increment left the fresh session re-entering the *same* un-incremented cycle. One transaction means either every effect lands or none does; PRD 00089 closed it on 00051's writer boundary.

Do NOT rewrite `state.tasks` here — `/work` already wrote `attempts[]` entries directly to `state.tasks` during rework; the sync hook keeps `tasks_total`/`tasks_completed` current. `phase-done` does not touch `state.tasks` at all, which is why the snapshot cannot be lost by advancing the cycle.
**Then hand off to a fresh session for the next cycle.** The loop does NOT continue in-session — a multi-cycle review session outlives the wall-clock cap and is SIGTERMed mid-cycle, discarding in-flight external-CLI reviewer work. Run the **Session handoff procedure** (core `SKILL.md` § Session Loop) with the **review → review** site row — the `phase-done` call above IS that row's state write (`phase`/`next_phase: "review"`, incremented `cycle`, `rework_task_ids` cleared, `phases_completed` untouched) — print the cycle-handoff banner below, and **STOP** (do not re-enter Phase 4 in this session). The wrapper's continue branch relaunches; the fresh session routes `phase: "review"` → Phase 4, which runs `state.cycle` (the incremented cycle; no review file exists for it yet) with no re-review of the prior cycle and no skip-to-done (`phases_completed` lacks `"review"` until convergence).

Cycle-handoff banner (`{prd-name}` = `state.prd` minus `.md`). **Cycle derivation (avoid the off-by-one):** the banner prints AFTER `phase-done` committed the increment, so `state.cycle` at print time is ALREADY the next cycle — `{n}` (the just-completed cycle) = `state.cycle - 1`, `{n+1}` (the cycle handed off to) = `state.cycle`. `phase-done` echoes the committed `phase`/`next_phase` as JSON, not the cycle; read `state.cycle` if you need the number:

```
── AUTOPILOT ── PRD: {prd-name} ── Cycle {n} rework complete ───────
── AUTOPILOT ── handing off to fresh session for cycle {n+1} ───────
```

Cross-references: `references/state-schema.md` (`rework_task_ids`, `tasks[].model`, `tasks[].attempts`, `stall_reason` shapes); `work/SKILL.md` Per-task model dispatch, Attempt logging, Rework-mode task filter.

## De-slop is part of the doubt lens

There is no separate between-session de-slop pass. De-slopping happens **inside every review cycle** — Bob (codex) carries the doubt + de-slop lens in the `review-work-completion` roster, with a Claude fallback when codex is unavailable, so the lens never silently drops. If you are checking how de-slop is wired, look at the review roster, not the `autoclaude` function. (Why the standalone wrapper pass was removed: `references/design-rationale.md` § De-slop.)
