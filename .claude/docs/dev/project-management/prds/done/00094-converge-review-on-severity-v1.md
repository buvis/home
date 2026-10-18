# Converge Review on Severity

Source discovery: `dev/local/discovery/00116-autopilot-loop-productivity.md` (PRD A of the
two-PRD split decided at Q10). PRD B is `00095-sharpen-review-finding-fidelity-v1.md`; this
PRD drains first. (Renumbered 00118 → 00094 at backlog review 2026-08-03 to drain ahead of
the agoge chain.)

## Overview

### Problem Statement

The autopilot review-rework loop converges only at zero findings, and reviewers always
produce Low-severity findings, so every PRD runs to `rework_cap` by construction (2026-07-28
eval: 13 of 14 tasks hit cap 3; engram batch 202608012229: ~9h/$208 with review-rework as
~38% of wall clock, buying type hints and a `sys.exit` style fix). The loop needs a
severity-based exit: converge when no CRITICAL/HIGH remains, sweep the Medium/Low tail
through one normal `/work` task, and drop the Quinn lens that cannot affect outcomes.

### Target Users

The unattended `autoclaude` loop (primary; no human, `$_AUTOPILOT_LOOP` set) and interactive
`/run-autopilot` runs (same gate, same bar).

### Success Metrics

- Every review cycle ending with no unresolved CRITICAL/HIGH finalizes the PRD in that cycle
  (no further full review cycle), verified per-PRD from review files on the first post-A
  batch. Binding for this PRD: median `cycles_to_converge` strictly below 3 across that
  batch, read from the `review_converged` lines (baseline 3). The median <= 2 target remains
  the A+B combined criterion measured after PRD 00095.
- Guard: zero escaped CRITICAL/HIGH — no PRD finalized via the new path later carries a
  C/H defect the final cycle rated Medium/Low or that the sweep introduced (cap-out
  deferrals excluded; evaluated retrospectively).
- Quinn appears nowhere in a review file produced after this PRD lands.
- `dev/local/autopilot/loop-metrics.jsonl` carries a `cycles_to_converge` line for every PRD
  the review gate finalizes.

## Functional Decomposition

### Capability: Severity-Based Convergence
The Phase 5 decision gate in `phase-review.md` exits the loop on severity, not on zero
findings.

#### Feature: Severity convergence test
- **Description**: Replace the "no unresolved findings remain" half of the convergence test
  with "no unresolved CRITICAL or HIGH finding remains".
- **Inputs**: The cycle's consolidated review file; the gate's per-finding classification;
  `state.deferred_decisions`; the constraint-gate result.
- **Outputs**: Converged / not-converged decision for the cycle.
- **Behavior**: Convergence requires BOTH: (a) no unresolved CRITICAL/HIGH finding, and
  (b) the doubt-roster constraint gate certifies (`check_review_file.py --require-codex-guard
  --assert-constraint-met` — unchanged; verified: it checks the constraint line only, so a
  converging cycle may carry `Verdict: N findings`). "Unresolved" excludes findings the gate
  discarded this cycle with a verified reason, and settled deferrals — C/H findings matching
  an entry already in `deferred_decisions` or a prior cycle's recorded deferral (discovery
  evidence: 2 of cycle 2's 3 oranges were settled deferrals; counting them blocks
  convergence for no reason). **Narrowed at implementation to HIGH only (2026-08-09):**
  Classification routes "Critical severity, always" to Defer-to-batch-end, so a CRITICAL
  lands in `deferred_decisions` the cycle it is raised; excluding CRITICALs would make one
  raised in cycle 1 "settled" by cycle 2 and converge, defeating both the `cap_critical`
  stall and this PRD's own zero-escaped-C/H guard. The discovery evidence and the Test
  Strategy edge case below are both HIGH, so nothing this PRD asked for is lost. Until 00095's deterministic matcher lands, matching a finding
  to a settled deferral is the gate's judgment call on issue text + file. Medium/Low never block. Non-converged cycles are unchanged:
  Classification and rework still process all severities; only the exit test changes. The
  loop-mode cap-out branch (CRITICAL stalls, <=HIGH defers) and interactive cap-pause are
  unchanged; with the new bar they can only fire while C/H persists. The bar is fixed at
  CRITICAL/HIGH for every PRD — deliberately NOT per-PRD configurable via frontmatter the way
  `rework_cap` and `doubt_reviewer` are (discovery 00116 open question, decided 2026-08-03): a
  per-PRD bar would let a PRD opt back into the polish loop this PRD removes, and no PRD has
  needed a different bar.

#### Feature: Convergence metric emission
- **Description**: The gate appends a cycles-to-converge record to
  `dev/local/autopilot/loop-metrics.jsonl` whenever it finalizes a PRD.
- **Inputs**: `state.prd`, `state.cycle`, batch id, the finalize path taken.
- **Outputs**: One JSON line: `{"event": "review_converged", "prd": <state.prd>, "batch":
  <batch_id>, "cycles_to_converge": <state.cycle>, "outcome": "converged"|"cap_deferred",
  "ts": <epoch seconds>}`.
- **Behavior**: Emitted at convergence, before the tail sweep is dispatched, AND on the
  loop-mode cap-out finalize path with `outcome: "cap_deferred"` — cap-outs are the baseline
  failures, so a median computed only from clean convergences would be biased. Existing
  wrapper lines carry no `event` key; consumers filter on it. The success metric reads these
  lines instead of parsing archived state files.

### Capability: Medium/Low Tail Sweep
On convergence, outstanding Medium/Low findings are fixed by one normal `/work` rework task,
then the PRD finalizes. Swept, not dropped; no new verification machinery.

#### Feature: Sweep task creation
- **Description**: The converging cycle's actionable Medium/Low findings become one
  `[D{cycle}]` task dispatched through Phase 6's existing Dispatch-rework mechanics.
- **Inputs**: The converging cycle's consolidated findings table.
- **Outputs**: One `[D{cycle}]` sweep task (tier: sonnet default with the `default_model`
  floor, exactly as Phase 6 D-tasks compute it) in `rework_task_ids` + `state.tasks`; or 2-4
  tasks when split.
- **Behavior**: Only actionable Medium/Low findings are swept — settled deferrals, gate
  discards, and already-deferred items are excluded. The task description lists every swept
  finding verbatim (severity, text, file — the transcription contract PRD 00095 tightens).
  Split rule: more than 10 findings → split into 2-4 tasks grouped by file/theme per
  `work/references/task-splitting.md` (10 matches the existing Phase 5 scope-alarm
  constant); the existing max-2-parallel rework rule applies unchanged. Zero actionable
  Medium/Low → skip the sweep and finalize directly (today's clean path).

#### Feature: Sweep-then-finalize routing
- **Description**: After the sweep's `/work` returns, the gate finalizes instead of starting
  another review cycle.
- **Inputs**: `/work` completion of the sweep task(s).
- **Outputs**: Finalize hand-off (**review → done**) with a banner naming the sweep, e.g.
  `── converged (cycle {n}): {k} medium/low findings swept ──`.
- **Behavior**: No `state.cycle` increment, no review → review hand-off, no further full
  review cycle. The mandatory one-verification-pass constraint is satisfied by `/work`'s own
  pipeline (tests-first 2.7 for behavioral fixes, 5.5 gate, 5.6 self-deslop, 5.7 per-task
  review) — the Q5 decision. A CRITICAL/HIGH raised by the sweep's own step-5.7 review is
  handled inside step 5.7 as today (verify, fix inline, max 3 review cycles); one that
  survives that cap is appended to the batch deferred JSON as `{"type": "sweep-escape",
  "issue": ..., "severity": ...}` and the PRD still finalizes — the Phase 5 loop never
  reopens after convergence (reopening would rebuild the polish loop this PRD removes; the
  deferred JSON keeps the escape visible at batch end). Guard reading ratified at backlog
  review 2026-08-03: the discovery's zero-escaped-C/H guard is measured net of recorded
  `sweep-escape` entries.

### Capability: Quinn Removal
Quinn is a no-op lens by construction: advisory weight means unique findings create no
tasks, and Classification auto-fixes Medium at 1/3 and Low at any consensus, so his
concurrence changes no routing decision. He is also broken (preflight passes port 8001, the
`pi` agent dispatches to 8080) and costs up to ~2 min of foreground preflight per cycle.

#### Feature: Remove Quinn from the review surface
- **Description**: Delete every Quinn-specific surface from the review pipeline; qwen keeps
  its build-phase implementor rung untouched.
- **Inputs**: `review-work-completion/` (SKILL.md + references), `phase-review.md`,
  `~/.claude/agents/quinn.md`.
- **Outputs**: A review surface with no Quinn references.
- **Behavior**: Premise: Quinn's lens is advisory-weight and cannot alter outcomes
  (discovery Q3); re-check at execution time that `agents/quinn.md` and the roster mentions
  still exist as documented — if the surface has already changed, skip the missing pieces
  and report, never force. Remove: the roster entry and step-1 qwen preflight in
  `review-work-completion/SKILL.md`; the step-5 dispatch line, Watcher mention if any, and
  the `qwen` key from the `state.review_lenses` stamp; step-6 advisory weighting and the
  `QUINN:` consolidation example pair; the step-7 advisory-skip rule; the Advisory bucket in
  `references/output-formats.md`; Quinn rows in `references/agent-invocation.md`,
  `references/agent-registry.md`, and `references/retry-policy.md` (where present); the
  Phase 4 roster mention in `phase-review.md`; `~/.claude/agents/quinn.md` (delete the
  file). Also (surfaces verified at backlog review 2026-08-03): the `qwen` (Quinn) key row
  in `run-autopilot/references/state-schema.md`; the Quinn active-check sentence in
  `work/references/qwen-integration.md`; the "Advisory Fourth Voice" section in
  `references/design-rationale.md`; the Quinn row in `references/review-coverage-format.md`;
  and `scripts/test_agent_registry.py` (drop `quinn` from its roster tuples - a code+test
  change; run that suite after). `use-qwen`, the implementor rung, and `qwen-run.sh` are
  untouched. Removing the `qwen` lens key is safe for tracon — it renders whatever keys exist.

## Structural Decomposition

### Repository Structure

```
skills/run-autopilot/references/
└── phase-review.md            # Maps to: Severity-Based Convergence, Medium/Low Tail Sweep
skills/review-work-completion/
├── SKILL.md                   # Maps to: Quinn Removal (roster, preflight, dispatch, weighting)
└── references/
    ├── agent-invocation.md    # Maps to: Quinn Removal
    ├── agent-registry.md      # Maps to: Quinn Removal
    ├── output-formats.md      # Maps to: Quinn Removal (Advisory bucket)
    └── retry-policy.md        # Maps to: Quinn Removal (where present)
agents/
└── quinn.md                   # Maps to: Quinn Removal (deleted)
dev/local/autopilot/
└── loop-metrics.jsonl         # Maps to: Convergence metric emission (runtime data, not code)
```

### Module: phase-review
- **Maps to capability**: Severity-Based Convergence, Medium/Low Tail Sweep
- **Responsibility**: Phase 5 convergence test, metric emission, sweep dispatch and
  finalize routing; Phase 4 roster line loses Quinn.
- **Exports**: The reworded Cap-check convergence paragraph; the renamed Outcomes row
  "Converged (no unresolved CRITICAL/HIGH)"; a "Tail sweep" sub-section reusing Phase 6
  Dispatch-rework mechanics.

### Module: review-work-completion
- **Maps to capability**: Quinn Removal
- **Responsibility**: Reviewer roster, preflight, dispatch, consolidation, and output
  formats with Quinn excised.
- **Exports**: A 4-5 reviewer roster (Alice, Blake, Bob, Carl, Eve-when-active).

### Module: agent registry
- **Maps to capability**: Quinn Removal
- **Responsibility**: `agents/quinn.md` deletion.
- **Exports**: (none — file removed)

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **phase-review (convergence test)**: The new exit condition everything else keys on.
- **review-work-completion + agent registry (Quinn removal)**: Independent deletion.

### Core Layer (Phase 1)
- **phase-review (tail sweep)**: Depends on [convergence test] — the sweep triggers on the
  new converged-with-tail outcome.

### Integration Layer (Phase 2)
- **phase-review (metric emission)**: Depends on [convergence test, tail sweep] — emits at
  the convergence determination point, before sweep dispatch.

## Implementation Phases

### Phase 0: Foundation
**Goal**: The severity bar exists and Quinn is gone.

**Tasks**:
- [ ] Rewrite the Phase 5 convergence test in `phase-review.md` (Cap check + Outcomes) to
  the severity bar, defining "unresolved" as above (no deps) - Acceptance: `rg -n "no
  unresolved CRITICAL" skills/run-autopilot/references/phase-review.md` matches in both the
  Cap check and Outcomes; `rg -n "no unresolved findings remain"` returns nothing.
- [ ] Remove Quinn from the review surface and delete `agents/quinn.md` (no deps; premise
  re-check per Behavior) - Acceptance: `rg -ni quinn skills/review-work-completion/
  skills/run-autopilot/references/ skills/work/references/qwen-integration.md agents/`
  returns nothing; `agents/quinn.md` absent; the `test_agent_registry.py` suite passes after
  the roster-tuple edit; `rg -n "qwen-run.sh" skills/work/` still matches (implementor rung
  untouched).

**Exit Criteria**: Both greps pass; the review surface names a 4-5 reviewer roster.

### Phase 1: Core
**Goal**: The Medium/Low tail is swept and the PRD finalizes in the converging cycle.

**Tasks**:
- [ ] Add the "Tail sweep" sub-section to `phase-review.md`: sweep task creation via Phase 6
  Dispatch-rework mechanics, verbatim finding listing, >10-findings split rule,
  sweep-then-finalize routing, sweep-escape deferral (depends on: Phase 0) - Acceptance:
  `rg -n "sweep-escape" skills/run-autopilot/references/phase-review.md` matches; the
  section mandates no cycle increment and review → done hand-off after the sweep.

**Exit Criteria**: A converged-with-tail cycle's documented path runs review → sweep →
finalize with no second full review cycle.

### Phase 2: Integration
**Goal**: Convergence is measured.

**Tasks**:
- [ ] Add metric emission to both finalize paths (converged and loop-mode cap-deferred)
  (depends on: Phase 1) - Acceptance: `rg -n "review_converged"
  skills/run-autopilot/references/phase-review.md` matches on both paths; the specified JSON
  line schema appears verbatim.

**Exit Criteria**: The gate's documented finalize paths both append the metric line.

## Test Strategy

### Critical Scenarios
- **Happy path**: Cycle ends with 0 CRITICAL/HIGH and 8 Medium/Low → Expected: documented
  path dispatches one sweep task, finalizes review → done, emits `outcome: "converged"`
  with `cycles_to_converge = state.cycle`. (Prose-mandated; verified by the acceptance greps
  above plus the first post-A batch's review files — this PRD edits skill prose, so
  `Tests: none (docs-only)` applies to its own review.)
- **Edge case**: Cycle ends with 1 HIGH that matches a recorded settled deferral and 3 Low →
  Expected: the HIGH does not block; converge and sweep the 3 Low.
- **Edge case**: 14 Medium/Low at convergence → Expected: split into 2-4 sweep tasks per
  task-splitting.md; max-2-parallel rule holds.
- **Error case**: Sweep's step-5.7 review caps out with an unresolved HIGH → Expected:
  `sweep-escape` entry in the batch deferred JSON, PRD still finalizes, loop does not
  reopen.
- **Error case**: `agents/quinn.md` already absent at execution → Expected: skip that
  deletion, report it, continue the remaining removals.

## Risks

- **Severity inflation becomes load-bearing**: a reviewer overcalling HIGH drags extra
  cycles. Mitigation: PRD 00095's script-checked claims and semantic consensus attack
  miscalibration; watch the per-cycle HIGH count across the first post-A batch.
- **Sweep diff too large**: ~25 findings in one task is a big diff. Mitigation: the
  >10-findings split rule plus the existing 2-agent rework cap.
- **Sweep escapes ship defects**: a HIGH surviving the sweep's own review cap finalizes
  anyway. Mitigation: `sweep-escape` records are visible in the batch deferred JSON and
  counted by the zero-escaped-C/H guard.
- **Self-review recursion**: this PRD edits the gate that reviews it. Mitigation: sequenced
  before 00095; first measurement taken from the agoge PRDs that follow in this batch.
