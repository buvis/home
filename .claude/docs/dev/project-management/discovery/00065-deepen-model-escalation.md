# Discovery: Deepen Model Escalation in the Autopilot Loop

## Classification
Depth: comprehensive | Date: 2026-07-13

## Problem
Autopilot already routes work by tier, but defaults are expensive and escalation is
slow: build/review sessions run Opus wall-to-wall, task tiers default to Sonnet,
qwen fires at most once per PRD, and a struggling task escalates only after burning
a full Opus review cycle. One recent PRD spent $11.14 (build) + $12.68 (review)
across 9 Opus sessions. Goal: apply escalation principles consistently — cheapest
plausible model first (local qwen at the bottom, free), fast deterministic
escalation on struggle — and cut cost_usd per PRD without weakening the review
safety net. Separately, the hardest tasks exhaust the ladder at Opus and stall to
the human; each stall freezes a PRD and spends the scarcest resource, attention —
a gated top rung that converts some stalls into completions is part of the same
economics.

## Requirements

### Must have
1. **In-loop diagnose-then-escalate in `/work`** (absorbs backlog 00060).
   Trigger: 2nd test-gate failure at a tier. Deterministic spec shape-checks first
   (Contract/Acceptance present, referenced files exist); inline orchestrator
   judgment only on top. Thin spec → repair the task description, one same-tier
   retry (max one repair per task). Solid spec → reset impl to the test commit,
   re-dispatch one rung up with a failure summary. Bounded per rung: initial
   attempt + one feedback retry — the 2nd failure triggers diagnosis; the repair
   retry happens at most once per task in total. Worst case per task: 2 dispatches
   per rung + 1 repair dispatch. Never loop a weak model. Ladder: qwen→sonnet
   (existing asymmetry, skips haiku), haiku→sonnet→opus. Infra failure ≠ capability
   failure: infra falls back at the same tier (existing behavior).
2. **Cheaper task defaults** in plan-tasks. Classifier floor shifts down: routine
   mechanical work → haiku + qwen-eligible; sonnet becomes the middle, not the
   default floor; opus novelty rules unchanged. Drop qwen's one-shot-per-PRD
   budget; eligibility fences stay (non-UI ∧ tier∈{haiku,sonnet} ∧ ≤3 files ∧ no
   public-contract edits). Hard prerequisite: 00058 (pin qwen engine to
   eval-approved models). Dispatch path gains a memory-pressure check.
3. **Sonnet-first build sessions** in the autoclaude wrapper. Build launches on
   Sonnet; deterministic promotion to Opus (jq on state.json + PRD frontmatter):
   `default_model: opus`, `replan_count > 0`, prior stall for this PRD, or repeat
   build session for the same PRD. Review stays Opus, done stays Sonnet.
4. **Human-gated Fable rescue** at `escalation_exhausted`: the loop writes a
   structured justification (problem, attempt history, impact of not escalating)
   into state, notifies via ntfy, and stalls the PRD (batch continues, 00017
   semantics). Explicit approval → one Fable-tier task retry; rejection → normal
   stall. Max one request per PRD. Never a session model, never autonomous.
5. **`audit-routing` skill in the claude-checkup plugin** (absorbs backlog 00059),
   wired into the global checkup orchestrator. Reads loop-metrics.jsonl + autopilot
   state across repos; reports median cost_usd/PRD vs baseline, review-cycles/PRD,
   stall rate, per-rung escalation success, cheap-share (incl. qwen utilization and
   exclusion reasons). Because dev/local/autopilot/ is GC'd at 14 days, the skill
   accumulates metrics and per-PRD outcomes into a durable store under the checkup
   plugin's data dir on every run, and freezes the pre-change baseline (median
   cost_usd/PRD across PRDs completed before PRD-A lands) on its first run.
6. **Kill-switch**: every new routing behavior sits behind the existing env/config
   overrides; one setting (e.g. `_AUTOPILOT_MODEL_BUILD=claude-opus-4-8`, a
   classifier floor knob) restores today's behavior.
7. **Attribution logging**: escalations record reason + diagnosis outcome in
   `state.tasks[].attempts[]` (extend existing fields) so the audit skill can
   attribute churn to routing, not guess.
8. **Canonical ladder declaration**: the full ladder (qwen → codex → claude tiers
   → human-gated Fable), tier→backend mapping, per-rung attempt budgets, and
   decay rules are declared in exactly one reference file; plan-tasks, /work,
   phase-review, and the wrapper cite it rather than restating it.
9. **codex implementor rung** (review-only policy lifted): eligible backend tasks
   may dispatch codex as a mid rung between qwen and Claude-at-tier, behind the
   existing dispatch contract (edit-enabled sandbox, background Bash, `-o`
   output). Eligibility fences and exact rung position live in the ladder file
   (M8). Constraint: a codex-implemented task is never doubt-reviewed by codex
   alone (Bob self-review bias).
10. **De-escalation**: escalations decay when the escalating condition clears —
    a promoted build session returns to the default model on the next relaunch
    without live promotion signals; a rework-escalated task tier does not bleed
    into other tasks or PRDs. Decay rules are deterministic and live in the
    ladder file (M8).
11. **Adaptive routing**: classifier thresholds and rung eligibility are tuned
    from recorded outcomes (attempts[], diagnosis results, per-rung success rates
    in the audit store), not only by hand. Tuning changes are visible diffs
    guarded by the M6 kill-switch; auto-apply vs. propose-only is an open design
    question. Sequenced last — it consumes the data M5/M7 produce.

### Nice to have
- Routing section in the per-batch autopilot report (checkup audit is the primary
  surface per Q3).
- Memory-pressure check folded into the qwen preflight itself (vs the work routing
  step).
- Per-task cost attribution in loop-metrics (today cost is session-granular).

### Out of scope
- Reviewer roster tiers — review stays the untouched safety net (Q1).
- Automated quality breaker / auto-reverting aggressiveness (Q3). Adaptive routing
  (M11) tunes rules from data, but quality reversion stays manual: the M6
  kill-switch is never pulled by code.
- Autonomous Fable spend in any form (Q6).

## Constraints
- Routing decisions are deterministic code on structured fields
  (`rules/ai-app-design.md`): wrapper `case`/jq on state.json; classifier rules in
  plan-tasks. Model judgment only for the fuzzy spec-gap call, inline, rubric-led.
- External CLI implementors/reviewers dispatch per the shared contract
  (`use-codex/references/dispatch-contract.md`): direct background Bash, `-f`
  prompt file, `-o` output file, TaskOutput watchdog — never Agent-wrapped.
- Sequencing: 00058 → A (net) → B (aggression); C anytime; D after A/B; E (codex
  rung) after A + the M8 ladder file; F (de-escalation) after A; G (adaptive
  routing) last — it consumes D's data. Closing phase: unpark 00051-00053. The
  escalation net must exist before defaults get cheaper.
- Wrapper logic stays portable (pure state-field decisions, no bash-only
  cleverness): the 00051-00053 rewrite is this initiative's closing phase and
  absorbs the wrapper's routing logic into the Python orchestrator.
- Spec-gap principle preserved: a thin task description never triggers a tier bump
  (evidence: 2026-06-29 batch — most Phase-6 non-escalations were spec gaps).
- RAM: 48GB machine, cargo OOM history; qwen server (30B Q4, 131K ctx) competes
  with parallel builds — pressure check before qwen dispatch.
- New stall variants must flow through the existing stall/defer machinery (00017);
  no new pause paths, no new Stop-hook-era guards.

## Codebase Context (brownfield scan, 2026-07-13)

### What already exists (extend, don't rebuild)
- **Per-task tier classifier**: `plan-tasks/SKILL.md` step 4.7 (:224-267) assigns
  `metadata.model: haiku|sonnet|opus` (novelty keywords / >8 files / >120K → opus;
  ≤2 files ≤50 lines mechanical → haiku; default sonnet; PRD `default_model` floor)
  plus `qwen_eligible` + `qwen_excluded_reason` (:269-289).
- **Per-task dispatch**: `work/SKILL.md` :62-74 passes `task.metadata.model` as the
  Agent `model` param; deterministic routing table :259-271 (gemini for UI, qwen
  when eligible+healthy, else Claude at tier); tier-gated pipeline depth :90
  (haiku=Tess+Ivan, sonnet=+reviewer, opus=+Devon); qwen one-shot budget :68, :324;
  same-tier retry cap :315-326 (the seam requirement 1 replaces).
- **Review-driven escalation**: `run-autopilot/references/phase-review.md` :153-172
  (haiku→sonnet→opus on review-flag; `escalation_exhausted`; escalation-diagnosis
  caveat :155).
- **Per-phase session models (PRD 00018)**: `autoclaude()` in
  `~/.config/bash/plugins/development.plugin.bash` :148-154 (build/review→opus,
  done→sonnet, env overrides `_AUTOPILOT_MODEL_BUILD/REVIEW/DONE`); launch line
  :170-174; relaunch decision table :180-280; loop-metrics writer :282-313
  (`cost_usd`, `tokens_out`, `model`, `phase_launched`, `signal` per session).
- **qwen lane (PRD 00019)**: honest 4-check preflight ending in a real 1-token
  completion (`work/references/qwen-integration.md`); eval 5/6 sonnet-tier Rust
  tasks; failure modes: multi-file under-coverage, over-claimed completeness.
- **Struggle signals recorded**: `state.tasks[].attempts[]` (outcome, cause,
  implementor, model, preflight_outcome, pipeline), `cap_rotations[]`,
  `task_aborts[]`, `replan_count`, `cycle`, `review_cycles[]`, `stall_reason` —
  `run-autopilot/references/state-schema.md` :155-182.
- **checkup plugin**: audit-* skill convention + global orchestrator at
  `/Users/bob/git/src/github.com/buvis/claude-checkup` (target home for
  requirement 5).

### Conventions
- Skill names start with an action verb (`audit-routing`).
- All hooks Python; wrapper is bash but decisions must be jq-expressible.
- Tests ship with each change; bug-fix regressions fail-first.

### Integration points
- `plan-tasks/SKILL.md` step 4.7 (classifier rules, qwen budget removal).
- `work/SKILL.md` step 5.5 + routing table (diagnose-then-escalate, pressure check).
- `development.plugin.bash` :141-154 case block (sonnet-first + promotion).
- `phase-review.md` escalation section + `state-schema.md` (Fable request fields,
  attempt attribution fields).
- claude-checkup orchestrator (new audit-routing skill).
- Backlog reconciliation: 00060 absorbed by PRD-A, 00059 by PRD-D; 00058 stays and
  gates PRD-B.

## Approach
- **Chosen**: extend the existing routing seams in place (plan-tasks classifier,
  `/work` step 5.5, wrapper case block) plus one new checkup audit skill; this
  discovery is an epic cut into session-sized PRDs by lever — A: in-loop
  escalation (absorbs 00060), B: cheaper defaults + qwen bottom rung, C: wrapper
  session routing + Fable gate, D: audit-routing (absorbs 00059), E: codex
  implementor rung, F: de-escalation, G: adaptive routing — closing with the
  unparked 00051-00053 orchestrator rewrite absorbing the wrapper logic.
- **Why**: the machinery already exists end-to-end (tiers, dispatch, review
  escalation, metrics); the gaps are policy and speed, not architecture. Small
  PRDs keep each autopilot run inside session budgets and land the net before the
  aggression.
- **Rejected alternatives**:
  - New model-dispatch plugin/router service: adds a fifth surface and new seams to
    a system whose failures have all come from seams; the "model-dispatch plugin"
    exists only as a memory note.
  - Automated quality breaker: every automated guard added to this loop has caused
    its own halt saga; monitoring via checkup + manual kill-switch instead.
  - One mega PRD / two by repo: crosses repo boundaries autopilot can't span, or
    triples normal session scope (cap-rotation bait).
  - Session-per-subphase splitting (cheap catchup session, opus planning session):
    belongs to the 00051-00053 orchestrator rewrite — this initiative's closing
    phase, not its opening move.

## Success Criteria
- Median `cost_usd` per completed PRD drops vs the frozen baseline in
  audit-routing's durable store (median across PRDs completed before PRD-A
  lands); target −40%, judged softly at first (Q3).
- Review-cycles/PRD and stall rate visibly tracked by `audit-routing`; soft
  tolerance initially, manual revert via kill-switch if they climb.
- qwen/haiku share of completed tasks rises (reported, not targeted — Goodhart).
- Zero new loop-halt classes attributable to routing changes.

## Risks
- **Sonnet build poisons planning**: bad decompositions surface as rework cycles.
  Mitigation: deterministic promotion signals, audit visibility, one-env revert.
- **Diagnosis judged at session tier** (Sonnet on unpromoted builds): the rubric
  is deterministic-first (shape checks decide whenever they can) and M7 logs each
  diagnosis outcome so audit-routing surfaces mis-diagnosis rates.
- **Escalation churn eats savings**: bounded attempts per rung, diagnose step
  filters spec gaps, audit attributes churn per rung.
- **qwen thrash on widened lane**: fences intact, 00060 breaker absorbed into
  PRD-A, test gate + untouched review roster catch under-coverage.
- **Un-evaled local model serving**: 00058 is a hard gate before PRD-B.
- **New stall variant mishandled by wrapper**: Fable-request reuses the 00017
  stall path verbatim + wrapper tests; no new pause semantics.
- **RAM contention** (qwen server + parallel builds): pressure check before qwen
  dispatch; wrapper memory breaker stays.
- **Fable request spam**: hard cap of one request per PRD.

## Open Questions
- Adaptive routing (M11) apply-mode: auto-apply tuned thresholds, or land them as
  audit-routing proposals accepted with one command?
- codex rung eligibility fences (which task shapes enter at codex; UI stays
  gemini) and how the Bob self-review constraint is enforced in the roster.
- De-escalation decay signals: exactly which conditions clear a session promotion
  (design-solution).
- Exact classifier rule changes for the floor shift (which thresholds/keywords move
  a task from sonnet-default to haiku+qwen) — needs a pass over recent batches'
  task mix.
- Fable approval UX: ntfy action, `autoclaude approve-fable <prd>` subcommand, or
  manual state edit? (Design phase; must work while the batch keeps draining.)
- Final promotion-signal set for sonnet-first builds (is repeat-build-session
  detectable purely from state today, or does it need a new counter?).
- Does `audit-routing` alert (ntfy) on regression or stay pull-only in checkup runs?

## Discovery Log

### Q1: Which cost centers should this initiative attack?
**Answer**: In-loop escalation + cheaper task defaults + session-model routing.
Reviewer roster tiers explicitly excluded — review stays the untouched safety net
that makes cheap-first implementors safe.

### Q2: What is the primary success metric?
**Answer**: cost_usd per completed PRD (median, from loop-metrics.jsonl) drops
materially vs the pre-change baseline. Chosen over usage-limit stalls (confounded),
cheap-share (Goodhart proxy), and a combined dashboard (bookkeeping).

### Q3: How should quality regressions from cheaper routing be guarded?
**Answer**: Monitor + manual revert, with soft tolerance at first. Monitoring is
delivered as a new audit skill in the claude-checkup plugin
(`/Users/bob/git/src/github.com/buvis/claude-checkup`), wired into its global
orchestrator — the user runs checkup regularly, which solves the
"forgot-to-read-the-report" failure of a batch-report-only guardrail. No automated
breaker. Implication: reconcile with backlog 00059 (audit-qwen report card) —
absorbed into this routing audit skill.

### Q4: When does a task escalate tier inside /work?
**Answer**: Diagnose, then escalate. On the 2nd test-gate failure at a tier, run the
spec-gap diagnosis first (thin contract/acceptance → repair the task description and
retry same tier; solid spec → reset impl to the test commit and re-dispatch one rung
up with a failure summary). Extends the Phase-6 escalation-diagnosis principle into
the loop. Design note: diagnosis is an inline rubric judgment by the /work
orchestrator (no extra dispatch); deterministic shape-checks (Contract/Acceptance
present, files exist) come first, fuzzy judgment only on top.

### Q5: What session-model policy for build sessions?
**Answer**: Sonnet-first + promote. Build starts on Sonnet; the wrapper's existing
case block promotes to Opus on deterministic signals: PRD frontmatter
`default_model: opus`, `replan_count > 0`, prior stall for this PRD, or repeat build
session for the same PRD. Review stays Opus (Q1 exclusion), done stays Sonnet.
Implementor tiers are unaffected (Agent `model` param overrides session model).

### Q6: What is the top of the escalation ladder?
**Answer** (user's own): Fable escalation is allowed but **human-gated**. The loop
must produce a well-justified escalation request (problem description + impact of
not escalating), then pause/stall that PRD until the human approves or rejects.
Fits existing machinery: stall variant (00017 semantics — PRD parks, batch
continues) with a structured justification payload in state + ntfy notification;
approval unblocks a Fable-tier retry. No autonomous Fable spend, ever.

### Q7: How far does qwen's lane widen?
**Answer**: qwen = bottom rung. Drop the one-shot-per-PRD budget; every eligible
task (existing fences intact: non-UI, tier∈{haiku,sonnet}, ≤3 files, no
public-contract edits) tries qwen first when preflight is healthy. Claude at tier
is the infra fallback, Q4 escalation the capability net, 00060's circuit breaker
the bad-day stop. Hard prerequisite: 00058 (pin engine to eval-approved models —
an un-evaled model is de-facto serving today). Constraint: dispatch path gains a
memory-pressure check (qwen server vs parallel builds, OOM history).

### Q8: How is the initiative cut into PRDs?
**Answer**: Four by lever. A: in-loop diagnose+escalate in /work (absorbs backlog
00060). B: cheaper defaults — plan-tasks classifier shift + qwen bottom rung.
C: wrapper sonnet-first builds + human-gated Fable rescue. D: audit-routing skill
in claude-checkup (absorbs backlog 00059). Sequencing: 00058 → A → B; C anytime;
D last. Net lands before defaults get aggressive.

### Q9: Confirm remaining out-of-scope items
**Answer**: Initially dismissed; resolved during /review-discovery-doc (finding
F6): ALL FOUR are IN scope — codex implementor rung (M9), de-escalation (M10),
adaptive routing (M11), and the 00051-00053 rewrite as the initiative's closing
phase. Follow-up clarification: routing levers land in the wrapper first (savings
start immediately); the epic unparks last and absorbs the wrapper's routing logic.
