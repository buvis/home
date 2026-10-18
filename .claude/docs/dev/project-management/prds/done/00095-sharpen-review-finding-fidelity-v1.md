---
catchup: force
---

# Sharpen Review Finding Fidelity

Source discovery: `dev/local/discovery/00116-autopilot-loop-productivity.md` (PRD B of the
two-PRD split decided at Q10). Sequenced after `00094-converge-review-on-severity-v1.md`;
the binding A+B success metric (median cycles-to-converge <= 2) is measured only once both
have landed. (Renumbered 00119 → 00095 at backlog review 2026-08-03; `catchup: force`
because 00093/00094 edit the same files this PRD grounds against.)

## Overview

### Problem Statement

Each review cycle loses information, which buys extra cycles. Measured on engram batch
202608012229: the orchestrator paraphrased five consensus themes into three rework tasks and
a half-fixed finding bought cycle 2's only actionable HIGH; `consolidate-findings.sh`
matches findings by exact string so every consensus reads [1/4] while real 3/4 agreement
exists; settled deferrals and gate-discarded findings are re-raised every cycle (the
`sys.exit(1)` finding was discarded in cycle 1 and re-raised by 3 of 4 reviewers in cycle
2); and a reviewer's wrong line count (58 claimed, 44 actual) cost an orchestrator
refutation pass. Fix all four so each cycle's findings land accurately enough that fewer
cycles are needed.

### Target Users

The autopilot review-rework loop (loop and interactive) and standalone
`/review-work-completion` runs.

### Success Metrics

- A+B combined: median cycles-to-converge <= 2 across the next batch, read from the
  `review_converged` lines PRD 00094 emits into `loop-metrics.jsonl` (baseline 3).
- The consensus column reports real agreement: at least one finding in a multi-reviewer
  cycle shows consensus above 1/N.
- Settled stays settled: no consolidated findings table in the measurement batch carries a
  ledger-settled item (Blake may still re-raise; the filter absorbs it before consolidation).
- Countable claims are computed: rubric checks with countable answers cite the facts block,
  and no cycle needs an orchestrator refutation pass on a mechanical claim.

## Functional Decomposition

### Capability: Finding-Faithful Rework
Rework tasks carry their findings verbatim, and closure is checked against the original
finding, not just code quality.

#### Feature: Verbatim finding transcription
- **Description**: Every rework task created from findings embeds each source finding
  verbatim as acceptance criteria.
- **Inputs**: The cycle's consolidated findings table (Phase 6 D-tasks; PRD 00094's sweep
  task uses the same block).
- **Outputs**: Task descriptions containing a `### Findings (verbatim)` block: one line per
  finding, quoted exactly as consolidated (severity, text, file, consensus) — no
  paraphrase, no merging of findings into themes.
- **Behavior**: Transcription fidelity is the requirement, not an assumption: N findings
  routed into a task produce N verbatim lines in its block, and the task's acceptance
  criterion is "every quoted finding no longer reproduces". Because `/work` step 2.7 (Tess)
  writes tests from the task description, tests now bind to the finding text with no work
  skill change to step 2.7 itself.

#### Feature: Closure check in per-task review
- **Description**: `/work` step 5.7's reviewer verifies each quoted finding is resolved, not
  just that the diff is clean code.
- **Inputs**: A rework task whose description carries a `### Findings (verbatim)` block; the
  task's committed diff.
- **Outputs**: A per-finding `resolved` / `unresolved` verdict with one line of evidence,
  in the step-5.7 review output.
- **Behavior**: When the block is present, the step-5.7 reviewer prompt includes it and
  requires the per-finding verdicts. Any `unresolved` verdict is treated as a HIGH finding
  in step 5.7's existing loop (verify against the code, re-dispatch Ivan with the confirmed
  gap, max 3 review cycles). This closes the measured failure where D1 task 11's review
  returned "fixed inline" while `_run_status` still swallowed `FileNotFoundError`. The
  findings block reaches the reviewer via the Pat persona's placeholder mapping per
  `agent-registry.md` conventions (00093 moves step-5.7 prompts to rendered personas).
  Step-5.5 closure is carried by construction: the finding-bound tests from verbatim
  transcription must pass at 5.5; findings that produced no test close solely via these
  5.7 verdicts.

### Capability: Semantic Consensus
Findings describing the same defect merge across reviewers, deterministically.

#### Feature: Python consolidator with token matcher
- **Description**: `consolidate_findings.py` replaces `consolidate-findings.sh` with
  deterministic near-match merging (decision 2026-08-02: deterministic Python, no model
  call).
- **Inputs**: The same CLI contract: `NAME:FILE` pairs of reviewer output files in the
  existing `[AGENT] {emoji} {desc} | File: {path} | Task: {id}` line format; optional
  `--ledger PATH --ledger-dismiss AGENT` (next capability).
- **Outputs**: The same consolidated markdown table (consensus, severity, issue, file,
  task, found-by) sorted by consensus then severity; the same `No issues found` sentinel;
  merged rows keep the most severe severity, the first-seen description, and all finders.
- **Behavior**: Two findings merge when their normalized file paths match (strip
  line-number suffixes, compare path tails) AND the token-set Jaccard of their normalized
  descriptions (lowercase, punctuation stripped, stopwords dropped) >= 0.4 (guess — pinned
  constant; the fixture suite is the behavioral contract, and the threshold may be adjusted
  only until the fixtures pass). Merging is transitive within a file group. Exposes
  `match(finding_a, finding_b) -> bool` importable by the ledger filter. Unit tests use
  fixtures derived from the engram cycle-2 four-reviewer outputs: real paraphrase
  duplicates (e.g. the `sys.exit(1)` finding as three reviewers worded it) must merge;
  distinct defects in the same file must not.

#### Feature: Caller migration
- **Description**: The review skill invokes the Python consolidator; the bash script is
  deleted.
- **Inputs**: `review-work-completion/SKILL.md` step 6.
- **Outputs**: Step 6 invokes `python3 ${CLAUDE_SKILL_DIR}/scripts/consolidate_findings.py`
  with the same NAME:FILE pairs; `consolidate-findings.sh` removed; the model-side fallback
  paragraph updated to name the new script.
- **Behavior**: Output format is unchanged, so `check_review_file.py`, the review-file
  format, and downstream consumers need no edits.

### Capability: Settled-Decisions Ledger
Closed calls stay closed across cycles.

#### Feature: Ledger writes at the gate
- **Description**: The Phase 5 gate records every settled deferral and every discard in a
  per-PRD ledger file.
- **Inputs**: Gate classification events (defer with reason, discard with verified reason).
- **Outputs**: `dev/local/reviews/{prd-stem}-ledger.json` — a JSON array, created on first
  write, appended per event: `{"cycle": N, "disposition": "settled-deferral"|"discarded",
  "severity": ..., "issue": <verbatim finding text>, "file": ..., "reason": ...}`.
- **Behavior**: Lives beside the review files so it survives batch end and parked-PRD
  resumes (state.json is archived at batch close), and dies with the PRD like other review
  satellites. The gate appends on every deferral/discard, including facts-block discards
  (below).

#### Feature: Ledger feeds implementation-aware prompts
- **Description**: Reviewers see what is already settled before they review.
- **Inputs**: The ledger file, at `review-work-completion` step 4 prompt assembly.
- **Outputs**: A "Settled decisions — do not re-raise" section (entries with disposition
  and reason) appended to Alice, Bob, Carl, and Eve prompts.
- **Behavior**: Implementation-aware reviewers only. Blake stays blind — his PRD-only
  prompt is untouched by design.

#### Feature: Blake auto-dismiss filter
- **Description**: Blake findings that match a ledger entry are dismissed before
  consolidation, at zero model cost.
- **Inputs**: Blake's output file plus the ledger, via `consolidate_findings.py --ledger
  PATH --ledger-dismiss BLAKE`.
- **Outputs**: Matching Blake findings excluded from the consolidated table and from task
  creation, emitted instead under a trailing `### Auto-dismissed (ledger)` section naming
  the matched entry's reason; the review file records that section.
- **Behavior**: Reuses `match()` against each ledger entry's `issue`/`file`. Blake-only
  (per the discovery): an implementation-aware reviewer re-raising despite the prompt feed
  stays visible as signal. This absorbs the measured failure of Blake re-raising the same
  three settled deferrals as rubric failures in both cycles.

### Capability: Script-Checked Mechanical Claims
Countable rubric claims are computed, never asserted.

#### Feature: Mechanical facts computation
- **Description**: A script computes function line counts for the changed Python files;
  reviewers cite it instead of counting.
- **Inputs**: `compute_mech_facts.py <file>...` — the changed-file list from step 3's
  gathered context.
- **Outputs**: A markdown facts block to stdout: per file, each function/method's qualified
  name, start line, and line count (Python `ast`); non-Python files listed as
  `skipped (non-python)`.
- **Behavior**: Line counts first, per the discovery; a file that fails to parse is listed
  as `skipped (parse error)`, never a crash. `review-work-completion` step 3 appends the
  block to the context file after `gather-context.sh` runs, so every implementation-aware
  prompt carries it. (ponytail: Python-only via ast; extend per-language when a non-Python
  PRD actually needs it.)

#### Feature: Facts bind reviewer claims
- **Description**: Reviewer prompts require citing the facts block for countable claims,
  and the gate auto-discards contradicted claims.
- **Inputs**: The facts block in the context file; findings whose text asserts a countable
  value about an entity the block covers.
- **Outputs**: Prompt instruction ("countable claims must cite the mechanical-facts
  block"); gate rule: a finding contradicting the block is discarded with reason
  "contradicts computed facts" and logged to the ledger.
- **Behavior**: Removes the orchestrator's refutation pass (Carl's 58-vs-44 line claim is
  the fixture case). Discards flow into the ledger, so the same wrong claim cannot return
  next cycle.

## Structural Decomposition

### Repository Structure

```
skills/review-work-completion/
├── SKILL.md                          # Maps to: Caller migration, Ledger prompts, Facts block wiring
└── scripts/
    ├── consolidate_findings.py       # Maps to: Python consolidator, Blake auto-dismiss (NEW)
    ├── test_consolidate_findings.py  # Maps to: Python consolidator (NEW)
    ├── compute_mech_facts.py         # Maps to: Mechanical facts computation (NEW)
    ├── test_compute_mech_facts.py    # Maps to: Mechanical facts computation (NEW)
    └── consolidate-findings.sh       # DELETED
skills/run-autopilot/references/
└── phase-review.md                   # Maps to: Verbatim transcription, Ledger writes, Facts discard rule
skills/work/
└── SKILL.md                          # Maps to: Closure check (step 5.7)
dev/local/reviews/
└── {prd-stem}-ledger.json            # Maps to: Ledger writes (runtime data, not code)
```

### Module: consolidation scripts
- **Maps to capability**: Semantic Consensus, Settled-Decisions Ledger (filter half)
- **Responsibility**: Deterministic finding parsing, merging, consensus counting, and
  ledger-based dismissal.
- **Exports**: `consolidate_findings.py` CLI (NAME:FILE pairs, `--ledger`,
  `--ledger-dismiss`); `match(finding_a, finding_b) -> bool`.

### Module: mech facts script
- **Maps to capability**: Script-Checked Mechanical Claims
- **Responsibility**: ast-derived function line counts as a markdown facts block.
- **Exports**: `compute_mech_facts.py` CLI.

### Module: review skill doc
- **Maps to capability**: Semantic Consensus (caller), Settled-Decisions Ledger (prompt
  feed), Script-Checked Mechanical Claims (context wiring)
- **Responsibility**: Steps 3, 4, and 6 wiring for facts block, ledger feed, and the Python
  consolidator.
- **Exports**: Updated step prose.

### Module: phase-review doc
- **Maps to capability**: Finding-Faithful Rework (transcription), Settled-Decisions Ledger
  (writes), Script-Checked Mechanical Claims (discard rule)
- **Responsibility**: Phase 5 ledger writes and facts-discard rule; Phase 6 D-task verbatim
  block mandate.
- **Exports**: Updated gate prose.

### Module: work skill doc
- **Maps to capability**: Finding-Faithful Rework (closure check)
- **Responsibility**: Step 5.7 per-finding closure verdicts for rework tasks.
- **Exports**: Updated step 5.7 prose.

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **consolidation scripts**: Matcher + consolidator + tests.
- **mech facts script**: Facts block + tests.

### Core Layer (Phase 1)
- **review skill doc (caller migration)**: Depends on [consolidation scripts].
- **phase-review doc (verbatim transcription, ledger writes)**: No script dependency;
  sequenced here to keep the gate edits in one task wave.

### Integration Layer (Phase 2)
- **review skill doc (ledger prompt feed + facts wiring)**: Depends on [ledger writes,
  mech facts script].
- **consolidation scripts usage (Blake filter)**: Depends on [consolidation scripts,
  ledger writes].
- **work skill doc (closure check)**: Depends on [verbatim transcription].
- **phase-review doc (facts discard rule)**: Depends on [mech facts script, ledger writes].

## Implementation Phases

### Phase 0: Foundation
**Goal**: Both scripts exist, tested, with the engram fixtures pinned.

**Tasks**:
- [ ] Write `consolidate_findings.py` + `test_consolidate_findings.py` (no deps) -
  Acceptance: pytest passes; fixtures prove a three-way paraphrase duplicate merges to
  consensus 3/N and two distinct same-file defects stay separate; output table
  byte-compatible with the current format on a single-reviewer input.
- [ ] Write `compute_mech_facts.py` + `test_compute_mech_facts.py` (no deps) - Acceptance:
  pytest passes; a fixture module reports correct per-function line counts; a non-Python
  and an unparseable file are reported as skipped, exit 0.

**Exit Criteria**: Both test files pass headlessly via `uv run --with pytest pytest <file>`.

### Phase 1: Core
**Goal**: The pipeline uses the new consolidator; the gate writes the ledger; rework tasks
carry findings verbatim.

**Tasks**:
- [ ] Migrate `review-work-completion/SKILL.md` step 6 to the Python consolidator and
  delete `consolidate-findings.sh` (depends on: Phase 0) - Acceptance: `rg -n
  "consolidate_findings.py" skills/review-work-completion/SKILL.md` matches; the `.sh` file
  is absent; no file under `skills/` references it.
- [ ] Add ledger writes and the verbatim-transcription mandate to `phase-review.md`
  (depends on: Phase 0, order only) - Acceptance: `rg -n "ledger.json"
  skills/run-autopilot/references/phase-review.md` matches in Phase 5; `rg -n "Findings
  \(verbatim\)"` matches in Phase 6 D-task creation.

**Exit Criteria**: Greps pass; the documented D-task format embeds findings verbatim.

### Phase 2: Integration
**Goal**: Ledger and facts reach the prompts; closure is checked; Blake leakage is filtered.

**Tasks**:
- [ ] Wire ledger prompt feed (step 4), facts-block append (step 3), and the Blake
  `--ledger-dismiss` invocation (step 6) into `review-work-completion/SKILL.md` (depends
  on: Phase 1) - Acceptance: `rg -n "do not re-raise|ledger-dismiss|compute_mech_facts"
  skills/review-work-completion/SKILL.md` yields all three; Blake's step-4 row still says
  PRD-only.
- [ ] Add the step-5.7 closure check to `skills/work/SKILL.md` and the facts-discard rule
  to `phase-review.md` Phase 5 (depends on: Phase 1) - Acceptance: `rg -n "resolved.*unresolved"
  skills/work/SKILL.md` matches in step 5.7; `rg -n "contradicts computed facts"
  skills/run-autopilot/references/phase-review.md` matches.

**Exit Criteria**: All acceptance greps pass; pytest suites still green.

## Test Strategy

### Critical Scenarios
- **Happy path**: Four reviewer files each wording the same `sys.exit(1)` defect
  differently → Expected: one consolidated row, consensus 4/4, most severe severity kept.
- **Edge case**: Two genuinely distinct findings in the same file with overlapping
  vocabulary → Expected: two rows (fixture pins the non-merge).
- **Edge case**: Blake re-raises a ledger-settled deferral → Expected: dismissed to the
  Auto-dismissed section, absent from the table, no task created.
- **Error case**: Ledger file malformed JSON → Expected: consolidator warns one line,
  proceeds without dismissal (never drops reviewer findings).
- **Error case**: A changed file fails to `ast.parse` → Expected: listed as skipped, facts
  block still produced, exit 0.

## Risks

- **Threshold miscalibration**: 0.4 Jaccard merges too much or too little. Mitigation:
  deterministic and fixture-pinned — adjust the constant against the fixture suite, not in
  production; misses only undercount consensus (the pre-B status quo), never drop findings.
- **Ledger over-suppression**: a legitimate new finding resembling a settled one gets
  dismissed. Mitigation: filter applies to Blake only; every dismissal is printed in the
  review file with the matched reason, so a wrong dismissal is visible, not silent.
- **Verbatim blocks bloat task descriptions**: ~10 findings per task is ~10 lines — within
  task-description norms; PRD 00094's split rule caps the sweep case.
- **Facts block scope creep**: only line counts are computed; other countable claims still
  rest on reviewers. Accepted: the discovery names line counts first; extend when another
  claim class recurs.
