# Discovery: Autopilot Review-Loop Productivity

## Classification

Depth: comprehensive | Date: 2026-08-02 | Sequence: 00116

Source: live observation of the engram batch `202608012229` while it was still
running.

## Problem

The `autoclaude` headless loop drains PRDs unattended, but its wall clock per
PRD is far above what the output justifies. The engram run measured here spent
~9 hours and $208 across 10 sessions on one "core v1" PRD and was still not
done, with roughly the same again budgeted before the cap. The review-rework
loop is the specific offender: it converges only at **zero findings**, and
reviewers whose job is to produce findings will always produce some at Low
severity, so the loop runs to `rework_cap` by construction on every PRD. That
is already measured behaviour, not a prediction - the 2026-07-28 loop eval
recorded 13 of 14 tasks hitting cap 3. Left alone, every PRD keeps paying two to
four review cycles for findings that this run showed to be type hints, a
redundant assert, and a `sys.exit` that should be a `return`.

## Evidence (measured, engram batch 202608012229)

Sources: `dev/local/autopilot/loop-metrics.jsonl`, `wrapper.log`, `state.json`,
`dev/local/reviews/00001-engram-core-v1-review-{1,2}.md`, git log.

### Wall clock and spend

| Window | Sessions | Wall | Cost |
|---|---|---|---|
| Bootstrap + design (22:28-23:20) | 1 | 52m | $18.73 |
| Build, tasks 1-10 (23:20-04:56) | 6 | 5h36m | $110.12 |
| Review cycle 1 + rework (04:56-07:39) | 3 | 2h43m | $79.33 |
| Review cycle 2 + rework (07:39-) | 1, in flight | 1h45m+ | not yet booked |
| **Total booked** | **10** | **~9h** | **$208.18** |

Build is ~62% of the clock; the review-rework loop is the rest and is the part
that scales with `rework_cap`.

### Review cost rises as the diff shrinks

- Cycle 1 review: 2 sessions, ~$18.85, reviewed the **full** 10-task diff.
- Cycle 2 review: 1 session, **$54.48**, reviewed a **13-commit incremental**
  diff of cycle-1 fixes.

A 4x smaller diff cost 3x more to review.

### Output-token efficiency is very low

Session 3 spent $28.11 for 7,015 output tokens over 1h35m; session 11 spent
$54.48 for 13,267. Cost is dominated by input, cache reads and subagent fan-out,
not by produced work - consistent with the 2026-07-14 triage finding that 78% of
spend is cache read/write.

### The review loop is a polish machine

Finding count per cycle, the full run:

| Cycle | Findings | CRITICAL |
|---|---|---|
| 1 | 35 | 0 |
| 2 | 26 | 0 |
| 3 | 9 | 0 |
| 4 | **14** | 0 |

**Cycle 4 found MORE than cycle 3.** The loop does not converge, it oscillates -
and cycle 4's findings are about work cycle 3's rework created: a test fixture at
69 lines against its own `<50` acceptance criterion, and task-20's fix never
applied to `_run_query`. Four cycles and ~$300+ to arrive at a fixture's line
count. 140 tests green throughout.

This is the single strongest argument for the severity-based bar: the extra
cycles are not finding residual risk, they are finding the debris of the previous
cycle's fixes.

- Cycle 1: 35 findings, **zero CRITICAL**, zero security.
- Cycle 2: 26 findings, **zero CRITICAL**, zero security, zero blockers.
- Cycle-2 rework list in full: validate response items are mappings; tighten a
  return type; scope a warning to `--corpus`; `sys.exit(1)` -> `return 1`; drop
  `assert callable(main)`.
- Review generated 9 of the 19 tasks in `state.json` (D1 x6, D2 x3) - nearly as
  many as the entire original build plan (10).

### Half-fixed findings buy extra cycles

Cycle 2's one actionable HIGH exists because cycle 1's fix was incomplete. D1
task 11 was "cli.py: status/index fail loud + surface missing corpus dirs";
cycle 2 found `_run_status` still swallowing `FileNotFoundError` and exiting 0
while `engram index` died with an uncaught traceback on the same condition. The
task's own step-5.7 review returned `5findings_0C0H4M1L; fixed 3M+1L inline` -
it reviewed the fix as code and never asked whether the finding that requested
it was resolved.

### Rework introduces regressions

Cycle 2's `_print_missing` finding - `index --corpus prd` printing missing-dir
warnings for every corpus - was **created by cycle-1 rework**. This is the
evidence that kept one verification pass in scope rather than ending the loop
after a single review.

### Churn: findings resurrected across cycles

`-k sys.exit(1)` was raised in cycle 1, **discarded** by the gate as "correct per
the SystemExit test", then re-raised in cycle 2 by 3 of 4 reviewers and is being
fixed now. Nothing carries a cycle-1 discard forward into cycle-2 reviewer
prompts. Separately, Blake re-raised the same three **settled deferrals**
(goldset decision corpus, extra CLI flags, Phase-2 four-corpus acceptance) as
fresh R1/R7/R16 rubric failures in both cycles.

### Consensus scoring does not work

Every row in the cycle-2 consolidated table reads `[1/4]`.
`consolidate-findings.sh` matches findings by exact string, so semantically
identical findings from four reviewers never merge. The orchestrator compensates
by hand-writing a "Consensus themes" prose section - model tokens doing a
script's job. The real consensus (3/4 on three themes) exists but the tool
cannot see it.

### Reviewer noise the orchestrator pays to refute

Carl (gemini) failed rubric R12 claiming `_heading_delimited_chunks` is 58 lines;
it is 44. The orchestrator spent a "Verified facts" pass proving the reviewer
wrong. Line counts are mechanically checkable and should never be a model
assertion.

### Quinn (qwen) is a no-op lens

`review-work-completion/SKILL.md:43` gives Quinn "advisory weight - findings
unique to Quinn create no tasks", so a Quinn-only finding is discarded by
design. Its only remaining lever is raising another reviewer's consensus count,
and `phase-review.md` Classification auto-fixes Medium at 1/3 consensus and Low
at **any** consensus - so the count changes no routing decision. Quinn cannot
alter an outcome even when healthy. It is also broken: preflight passes on
provider `llamacpp8001` (port 8001) while the `pi` review agent dispatches to
`localhost:8080` and gets `fetch failed`, identically in both cycles, costing up
to ~2 min of foreground preflight each time.

### Other observed friction (not in scope, recorded)

- Two `memory pressure (level 2)` stalls during the review window.
- The codex implementor rung was declined by the gate because its batch health
  probe is fragile on this host.
- 5 of 10 build tasks routed to qwen; the orchestrator then hand-corrected
  qwen's task-10 output four separate times.

## Requirements

The work splits into two sequenced PRDs (Q10). PRD A is the wall-clock win and
must drain first; PRD B is review-quality plumbing that the combined A+B
metric depends on.

### PRD A - Loop exit (must have)

- **Convergence bar becomes severity-based.** The Phase 5 gate ends the
  review-rework loop when no unresolved CRITICAL or HIGH finding remains,
  instead of at zero findings. Medium and Low do not block convergence. The
  doubt-roster constraint-gate certification (the second convergence
  condition, `check_review_file.py --assert-constraint-met`) is unchanged -
  this bar replaces only the zero-findings half of the convergence test.
- **The Medium/Low tail is swept, not dropped.** On convergence, the outstanding
  Medium and Low findings become **one rework task** dispatched through the
  normal `/work` pipeline - tests first, step 5.5 pass gate, step 5.6
  self-deslop, step 5.7 per-task review - then the PRD finalizes. Oversized
  tails split per `work/references/task-splitting.md`.
- **Quinn leaves the reviewer roster.** Remove the lens, its preflight probe, its
  failure-handling prose, and its per-cycle "graceful degradation" note - and
  every other Quinn-specific surface: the step-6 advisory-weighting split, the
  step-7 advisory-skip rule, output-formats' "Advisory bucket (Quinn)", the
  `qwen` key in `state.review_lenses`, phase-review.md's Phase 4 roster
  mention, and `~/.claude/agents/quinn.md`. Acceptance: a case-insensitive
  grep for "quinn" over the review surface returns nothing. Qwen keeps its
  build-phase implementor rung, untouched.
- **Convergence emits the metric.** At convergence, before the tail sweep is
  dispatched, the gate appends `{prd, cycles_to_converge}` to
  `loop-metrics.jsonl`; the success metric reads these lines instead of
  parsing archived state files.

### PRD B - Review fidelity (must have)

- **Rework tasks carry their finding verbatim as acceptance criteria**, so the
  step 5.5 gate and step 5.7 review check closure against the original finding,
  not just code quality. Transcription fidelity is a requirement, not an
  assumption - the orchestrator currently paraphrases and merges findings (five
  cycle-2 consensus themes collapsed into three D2 tasks).
- **Consensus matching becomes semantic.** `consolidate-findings.sh` must merge
  findings that describe the same defect from different reviewers, so the
  consensus column reports reality instead of `[1/4]` on every row.
- **A settled-decisions ledger feeds the next cycle's reviewer prompts.** Both
  deferrals the gate settled and findings the gate discarded (with its reason)
  are carried forward, so reviewers stop re-litigating closed calls.
  Prompt-feeding applies to the implementation-aware reviewers only: Blake
  stays blind (his PRD-only prompt is untouched), and the pipeline instead
  auto-dismisses any Blake finding that matches a ledger entry - reusing this
  PRD's semantic matcher - before it reaches the consolidated table or
  creates a task, at zero model cost.
- **Mechanical claims are script-checked, not asserted.** Rubric checks with a
  countable answer - line counts first - are computed rather than stated by a
  model, removing the orchestrator's refutation pass.

### Nice to have

- (none - the metric-emission item was promoted into PRD A's must-haves)

### Out of scope

- **Build-phase parallelism.** Lifting `work/references/task-splitting.md`'s
  "Never parallelize original plan tasks" for disjoint file slices is the
  largest remaining lever (5h36m of the ~9h) and is deliberately deferred - it
  needs its own safety design, since that rule protects `state.tasks` accuracy
  and attempt logging, and an uncapped fan-out once locked the machine. Still
  open after PRD 00117.
- **Trimming the per-task pipeline.** Skipping the step-5.7 per-task review when
  the gate and de-slop both came back clean - deferred for the same reason: it
  may just move findings downstream where they cost more.

**Build-phase follow-up, since taken up.** The build phase was analysed
separately after this discovery closed:
`dev/local/audit-results/2026-08-02-autopilot-build-phase-analysis.md`. Its
clerical-overhead findings (F1-F5, F7) became **PRD 00117**
(`cut-build-phase-clerical-overhead`). Build parallelism (F9) remains out of
scope everywhere.
- **Session-count reduction.** Fewer, longer sessions reopens the SIGTERM class
  that PRD 00067 closed.
- **Cost per PRD, human-intervention rate, and output quality** as optimization
  axes. Wall clock was chosen; the others are explicitly not targeted.
- **Removing qwen as an implementor.**
- The ten parked autopilot PRDs in `hold/`. None of them change the convergence
  criterion or the per-cycle review cost, so none is a prerequisite here.

## Constraints

- **One verification pass over each rework batch is mandatory.** Rework
  demonstrably introduces bugs (the cycle-2 `_print_missing` regression), so the
  loop may not end immediately after fixing without re-reviewing.
- **No new human-facing work.** Sweeping the tail into the deferred JSON for
  `/run-autopilot review-batch` was rejected precisely because it converts saved
  machine time into an interactive session - the opposite of the system's
  purpose.
- **Loop mode has no human.** All changes must behave under
  `$_AUTOPILOT_LOOP` with no `AskUserQuestion` and no pause.
- **Reuse the existing pipeline.** The tail sweep runs through `/work` as a
  normal rework task; no new verification machinery is to be built.
- **Changes are to the review surface only** - `phase-review.md`,
  `review-work-completion`, `work` - not to the build phase.

## Codebase Context

- **Relevant code**:
  - `~/.claude/skills/run-autopilot/references/phase-review.md` - Phase 5 gate,
    convergence test, cap check, Classification table, `rework_cap` semantics.
  - `~/.claude/skills/review-work-completion/SKILL.md` - reviewer roster
    (Alice/Blake/Bob/Carl/Quinn/Eve), preflight rules, consensus engine
    resolution.
  - `~/.claude/skills/review-work-completion/scripts/consolidate-findings.sh` -
    the exact-string matcher.
  - `~/.claude/skills/work/SKILL.md` steps 2.7-5.7 - tests-first, pass gate,
    self-deslop, per-task review.
  - `~/.claude/skills/work/references/self-deslop-prompt.md` - already enforces
    per-removal test re-runs and forbids behaviour change.
  - `~/.claude/skills/work/references/task-splitting.md` - the never-parallelize
    rule and the 2-agent rework cap.
  - `~/.claude/skills/run-autopilot/scripts/statectl.py` - the state write
    boundary all field edits go through.
- **Conventions**: hooks and scripts are Python only; state edits route through
  `statectl`; skills reference helpers via `${CLAUDE_SKILL_DIR}/scripts/`.
- **Integration points**: the Phase 5 Outcomes block and Cap check in
  `phase-review.md`; the roster list and step-1 preflight block in
  `review-work-completion/SKILL.md`; `consolidate-findings.sh`; the rework
  dispatch section of `phase-review.md` Phase 6 where D-tasks are created.
- **Similar implementations**: `self-deslop-prompt.md` is the closest existing
  pattern for the tail sweep - a scoped, test-verified, deletion-only pass with
  an explicit "do not change behaviour" contract.

## Approach

- **Chosen**: relax the loop-exit condition from "zero findings" to "no
  CRITICAL/HIGH", sweep the remaining tail through one normal `/work` rework
  task, drop the lens that cannot affect outcomes, then in a second PRD make
  each cycle's findings land accurately enough that fewer cycles are needed.
- **Why**: the convergence test is the single line that guarantees every PRD
  runs to its cap, and changing it is a small edit to a decision table rather
  than new machinery. Everything else in scope either removes provable waste
  (Quinn, exact-string consensus, re-litigated deferrals, model-asserted line
  counts) or reduces cycle count at its cause (half-fixed findings). Nothing
  here requires new infrastructure.
- **Rejected alternatives**:
  - **Parallelize the build phase**: bigger prize but needs its own safety
    design; deferred rather than dismissed.
  - **Review once, fix, ship**: the largest wall-clock cut available, rejected
    because this run proves a rework batch can introduce new bugs and nothing
    would catch them.
  - **Lower `rework_cap` to 2 and change nothing else**: caps the symptom, still
    runs the full cap every time, and would defer a genuine CRITICAL found at
    cycle 2.
  - **Adding a Medium-with-2+-reviewers consensus floor**: correct in principle
    but un-evaluable until consensus matching is fixed; PRD B removes that
    blocker, so it can be reconsidered afterwards.
  - **Defer the tail to `/run-autopilot review-batch`**: converts machine time
    into human time.
  - **Auto-file a nits PRD**: pays full pipeline overhead - design, plan, build,
    review, finalize - for a docstring.
  - **Giving Quinn task-creating weight**: a weak model on a fragile local stack
    that has never completed a cycle here would feed more low-quality findings
    into the loop being shortened.
  - **One combined PRD**: `hold/` holds ten parked autopilot PRDs; large ones do
    not drain.

## Success Criteria

- **PRD A+B combined: median cycles-to-converge <= 2** across the next batch,
  measured from the `cycles_to_converge` lines PRD A emits into
  `loop-metrics.jsonl`. Baseline is 3 - essentially every
  PRD runs to its cap today (2026-07-28 loop eval: 13 of 14 tasks hit cap 3).
- **PRD A alone: every review cycle that ends with no unresolved CRITICAL or
  HIGH finalizes the PRD in that cycle** - no further full review cycle -
  verified per-PRD from review files on the first post-A batch. Expected
  median 2-3, non-binding: PRD A cannot be held to the median-2 target,
  because the fix-closure change it depends on lands in PRD B; the binding
  productivity gate is the A+B median above.
- **Guard: zero escaped CRITICAL/HIGH.** No PRD finalized via the new
  convergence path is later found to carry a CRITICAL- or HIGH-severity defect
  that the final cycle's reviews rated Medium/Low, or that the tail sweep
  introduced. Cap-out deferrals are pre-existing behaviour and excluded. This
  is a safety guard on relaxing the bar, not a productivity measure, and is
  evaluated retrospectively.
- **Quinn appears nowhere** in a review file produced after PRD A lands - no
  roster line, no skip note, no preflight.
- **The consensus column reports real agreement** after PRD B: at least one
  finding in a multi-reviewer cycle shows a consensus above 1/N.
- **Settled stays settled** after PRD B: no consolidated findings table in the
  measurement batch carries a ledger-settled item (Blake may still re-raise;
  the pipeline filter absorbs it before consolidation).
- **Countable claims are computed** after PRD B: rubric checks with countable
  answers cite script output, and no cycle needs an orchestrator refutation
  pass on a mechanical claim.

## Risks

- **Severity inflation becomes load-bearing.** With HIGH as the gate, a reviewer
  that overcalls severity can drag the loop for extra cycles - the exact failure
  the change is meant to prevent. *Mitigation*: PRD B's script-checked
  mechanical claims and semantic consensus both attack miscalibration; watch the
  HIGH count per cycle across the first batch.
- **The deferred tail silently rots.** Medium and Low stop being fixed
  automatically if the sweep is skipped or the split path is taken later.
  *Mitigation*: the sweep is a must-have in PRD A, not an option, and runs
  through `/work` so it is committed and reviewed like any other task.
- **One rework task carrying ~25 findings is a large diff.** *Mitigation*: the
  existing task-splitting rule is the relief valve; the PRD must name the
  threshold at which the sweep splits.
- **Finding-to-task transcription is already lossy.** PRD B's acceptance-criteria
  change assumes faithful transcription, and this run shows paraphrasing and
  merging. *Mitigation*: treat verbatim transcription as its own testable
  requirement rather than a side effect.
- **Changing the review loop while the review loop reviews the change.** PRD A
  and B alter `phase-review.md`, which governs their own review cycles.
  *Mitigation*: sequence them, and take the first measurement from a batch of
  unrelated PRDs.
- **Measurement contamination.** `rework_cap` on the live engram run was lowered
  from 5 to 3 during this session (see below), so that PRD is not a clean
  baseline.

## Actions already taken

- **`rework_cap` 5 -> 3 on the live engram batch** (`statectl set`, verified).
  Cycle was at 2 with rework in flight; when it lands, cycle becomes 3 and the
  next Phase 5 gate reads `3 >= 3`, takes the loop-mode cap-out branch, defers
  everything below CRITICAL and finalizes. This reproduces the intended new
  behaviour today with no code change, at the cost of also deferring any genuine
  HIGH found in cycle 3 - which the real bar would have fixed.

## Open Questions

- **What severity does the sweep task itself get if its own step-5.7 review finds
  a HIGH?** The loop has already converged at that point. Does a HIGH in the
  sweep reopen the loop, or land in the deferred JSON?
- **What is the split threshold for the tail sweep** - number of findings, net
  lines, or files touched?
- **Does "no unresolved CRITICAL/HIGH" count findings the gate classifies as
  settled deferrals?** Cycle 2 carried three oranges of which two were settled
  deferrals; counting those would have blocked convergence for no reason.
- **Should the severity bar be per-PRD configurable** via frontmatter, the way
  `rework_cap` and `doubt_reviewer` already are?
- **Semantic consensus matching needs a mechanism** - embedding similarity, an
  LLM merge pass, or normalized keys. A model call per cycle reintroduces cost;
  a deterministic key is cheaper but weaker. Unresolved.
- **Where does the settled-decisions ledger live** so it survives batch end?
  `state.json` is archived to `reports/{batch_id}-state-final.json` when the
  batch closes.

## Discovery Log

### Q1: Which axis is the real target for "more productive"?

**Answer**: **Wall clock per PRD.** Optimize hours-to-done; the same spend is
acceptable if it finishes faster. Cost per PRD, human-intervention rate, and
output quality were offered and not chosen.

### Q2: Where should the wall-clock savings come from first?

**Answer**: **End the review loop on severity.** Converge when no CRITICAL/HIGH
remains instead of at zero findings; sweep the Low/Medium tail to deferred.
Rejected: parallelizing the build phase, cutting per-cycle review latency,
collapsing the session count.

Context: wall clock splits ~5h36m build (6 sessions, 10 tasks, strictly
sequential per `work/references/task-splitting.md` "Never parallelize original
plan tasks") and ~4h30m+ review/rework (one cycle per session, up to
`rework_cap: 5`).

### Q3: What happens to qwen in the loop?

**Answer**: **Drop the review lens, keep the implementor rung.** Rejected:
dropping qwen entirely, giving Quinn task-creating weight, fixing the port bug
and deciding later.

Established during the question: Quinn is a no-op by construction, independent
of being broken - advisory weight means unique findings create no tasks, and the
Classification table auto-fixes Medium at 1/3 and Low at any consensus, so the
only thing Quinn can influence changes no routing decision. Qwen-as-implementor
is a separate question and keeps its rung (5 of 10 build tasks this run, though
task 10 needed four orchestrator corrections).

### Q4: What exactly counts as "converged"?

**Answer**: **No unresolved CRITICAL or HIGH.** Medium and Low sweep to
deferred. Rejected: review-once-fix-ship, adding a 2+ reviewer Medium consensus
floor, keeping zero-findings convergence with `rework_cap` lowered to 2.

Correction recorded during this question: an earlier claim that a severity bar
would have converged this run at cycle 1 was wrong. Cycle 1 carried 4 HIGH
findings and cycle 2 carries 1 actionable HIGH, so the chosen bar converges at
cycle 3, saving ~2 cycles rather than 4.

The 2+ consensus floor was rejected as un-evaluable today because
`consolidate-findings.sh` matches by exact string.

### Q5: How should the batched Medium/Low tail be built and verified?

**Answer**: **One rework task through `/work`**, which already contains the
double-check - tests written first, step 5.5 gate, step 5.6 self-deslop, step
5.7 per-task review. Rejected: sweep-then-narrow-diff-review, splitting the tail
by species, sweep verified by full suite only.

User framing: "batch low/medium findings into a single deslop run, but double
check after it is done that no regressions were introduced."

Established during the question: (1) the existing self-deslop pass is already
self-verifying for deletions - it re-runs tests after each individual removal and
restores any that fails, and forbids behaviour change, refactoring and test
edits; (2) the tail is not all de-slop - this cycle's D2 list mixes genuine slop
with small behavioural fixes that need a test written first, which a post-hoc
regression check cannot supply.

### Q6: Does this work stop at the review loop, or reach into the build phase?

**Answer**: **Review loop only.** Rejected for this scope: build parallelism, a
leaner per-task pipeline, a single build+review overhaul. Accepted consequence:
~62% of the wall clock stays untouched, available as follow-on work.

### Q7: What measurement decides whether this worked?

**Answer**: **Median cycles-to-converge <= 2** across the next batch, from
`state.cycle`, no new instrumentation. Rejected: review-loop share of PRD wall
clock (improves if build slows - wrong incentive), zero escaped CRITICAL/HIGH
(retained as a secondary guard rather than the primary metric), absolute wall
clock per PRD (varies too much with PRD size).

### Q8: How do we stop half-fixed findings from buying an extra cycle?

**Answer**: **Rework tasks carry their finding verbatim as acceptance
criteria.** Rejected: a separate post-rework closure check, recording discard
reasons alone, accepting median 3.

### Q9: Which adjacent defects should this PRD also fix?

**Answer**: **All four** - broken consensus matching, settled deferrals
re-litigated every cycle, discarded findings coming back, and reviewer miscounts
costing a refutation pass. Two of them collapse into one mechanism (a
settled-decisions ledger fed into reviewer prompts), leaving six features total.

### Q10: One PRD or split?

**Answer**: **Split in two, loop-exit first.** PRD A: convergence bar, tail
sweep, drop Quinn. PRD B: consensus matching, settled-decisions ledger,
findings-as-acceptance-criteria, script-checked mechanical claims. Rejected: one
sequenced PRD, pairing closure with the bar, splitting in three.

Consequence accepted by the user after being stated: PRD A alone will likely
still measure median 3, because the fix-closure change its metric depends on
lands in PRD B. Resolved without a further question by giving PRD A its own
criterion (strictly below 3) and keeping median <= 2 as the A+B criterion.

### Q11: What do we do with the batch running right now?

**Answer**: **Set `rework_cap` to 3 now.** Applied and verified via `statectl`
during this session. Rejected: letting it run to cap 5 for a clean baseline,
stopping after cycle 3 by hand, killing and finalizing immediately.
