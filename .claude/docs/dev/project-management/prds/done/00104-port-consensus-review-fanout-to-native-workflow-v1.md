---
consensus_engine: shadow
---

# Port Consensus Review Fan-Out to a Native Workflow

> Renumbered 00057 → 00104 on 2026-08-01 (backlog tail resequence; mapping in memory `project_backlog_renumber_2026_08`).
> Source: ECC catchup 2026-07-10 (upstream commits 1031d31, 914a58a: `orch-review` native Workflow pilot) + session analysis in `dev/local/tmp/ecc-report-2026-07-10.md`.
> Related: done 00015 (merge-review-surfaces); the autopilot CLI stream — 00051 (wip), 00106 (orchestrator cutover, ex-00052), 00107 (validators, ex-00053). This PRD is independent of that queue; the 00106 orchestrator inherits whichever engine the flag selects.

## Overview

### Problem Statement

The review phase hand-rolls its multi-agent mechanics. The consensus (Alice) lens fans out reviewer subagents with prose contracts: findings come back as free text (parse drift), the same defect reported by two reviewers counts twice, nothing adversarially verifies a finding before it forces a rework cycle, and the strand/hang saga (memories: blind-thrash, review-batch-strand, orphan-reviewer deadlock) all traces to hand-managed background dispatches. The native Workflow tool provides deterministic fan-out, concurrency caps, schema-forced structured output, journaling, and resume - the exact machinery those patches approximated.

ECC ported this same segment upstream: dimension reviewers in parallel, dedup keyed on the normalized `evidence` snippet (11 raw findings collapsed to 4 unique in their testing), then an adversarial verifier per CRITICAL/HIGH that defaults to refuted on uncertainty; the gate fails closed on invalid input or a failed dimension.

Out of scope, as hard boundaries: external CLI reviewers (codex, gemini) stay direct background Bash (PRD 00034; Agent-wrapped CLIs hang); the blind (Blake) and doubt (Bob) lenses are untouched; all three lenses still run every cycle per the standing workflow rule.

### Target Users

The solo operator's autopilot review phase and interactive `/review-work-completion` runs.

### Success Metrics

- Zero findings-parse failures across the fixture suite and the Phase 2 shadow cycle (schema makes the failure class impossible); 3 consecutive clean opt-in cycles remain the default-flip criterion, owned by the follow-on PRD.
- Journal stats show dedup collapsing duplicates (raw > unique) on multi-reviewer cycles.
- No unproven blocker: every CHANGES_REQUESTED finding carries `evidence` and `proof` and survived adversarial verification.
- A killed or paused review run resumes via `resumeFromRunId` with cached results instead of re-running reviewers (no new watchdog code).

## Functional Decomposition

### Capability: Consensus review as a workflow

The autonomous fan-out segment of the consensus lens, between the phase gates. The gated outer loop stays in the review session.

#### Feature: Review fan-out script

- **Description**: Workflow script running the consensus lens's review dimensions in parallel with schema-forced findings, dedup, and adversarial verification.
- **Inputs**: `args` object: `diff` (unified diff text, required), `prd_path`, `changed_files[]`; internal dimension list (correctness/quality always; tests-coverage always; security only when the diff or paths match the security trigger).
- **Outputs**: `{ verdict: APPROVE|CHANGES_REQUESTED, blocking[], advisory[], incomplete, failedDimensions[], stats: {dimensions, raw, unique, confirmed, refuted}, review_markdown }`.
- **Behavior**: parallel dimension agents → dedup barrier keyed on normalized `evidence` snippet (strictest severity survives; reporting dimensions recorded) → adversarial verify each unique CRITICAL/HIGH with refuted-as-default-on-uncertainty; MEDIUM/LOW pass through as advisory. Missing/empty `diff` throws (fail closed, never silently approve). Any dimension that fails to run sets `incomplete: true` which forces CHANGES_REQUESTED.

#### Feature: Findings schema

- **Description**: JSON Schema all reviewer agents must satisfy via structured output; blockers cannot arrive unsupported.
- **Inputs**: reviewer agent output (Workflow `schema` option).
- **Outputs**: validated finding objects `{title, severity, file, line?, evidence, proof?, fix?}`.
- **Behavior**: schema `if/then` requires `proof` when severity is CRITICAL/HIGH; validation and retry happen at the tool layer, so no prose parsing anywhere in the pipeline.

### Capability: Review-phase integration

#### Feature: Review-file renderer

- **Description**: final workflow stage rendering the structured result into the review-file contract the coverage gate parses (the PRD-00016 shape checked by `check_review_file.py`).
- **Inputs**: structured result; the reviewer roster for the `reviewers:` frontmatter line.
- **Outputs**: `review_markdown` matching the live contract per `review-work-completion/references/review-coverage-format.md`: `reviewers:` frontmatter, a non-empty `## <Name>` section per launched reviewer, a `Verdict: converged` / `Verdict: N findings` line, and a `Tests: N passed ...` line (docs-only diffs render `Tests: none (docs-only)`).
- **Behavior**: blocking findings render inside the reviewer section and drive the `Verdict: N findings` count; advisory findings render as notes; the review session writes the file unchanged, so `check_review_file.py` and `review_coverage_hook.py` need no modification.

#### Feature: consensus_engine frontmatter flag

- **Description**: per-PRD opt-in selecting the workflow engine for the consensus leg (same pattern as `doubt_reviewer`, PRD 00037).
- **Inputs**: PRD frontmatter `consensus_engine: workflow | legacy` (absent = legacy).
- **Outputs**: review phase dispatches the consensus leg to the Workflow tool or the legacy subagent fan-out.
- **Behavior**: invalid values fall back to legacy with a one-line logged warning. Default flips to workflow only in a follow-on PRD after 3 clean opt-in cycles.

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── workflows/                            # Maps to: Consensus review as a workflow
│   └── review-fanout.workflow.js         # Maps to: Review fan-out script, Findings schema, Review-file renderer
└── skills/
    ├── review-work-completion/SKILL.md   # Maps to: consensus_engine flag dispatch (interactive surface)
    └── run-autopilot/references/         # Maps to: consensus_engine flag dispatch (loop surface:
        ├── phase-build.md                #   Phase 0 flag table, alongside doubt_reviewer)
        └── state-schema.md               #   state field documentation
```

### Module: workflows/review-fanout

- **Maps to capability**: Consensus review as a workflow (and hosts the Review-file renderer feature)
- **Responsibility**: deterministic review fan-out: dimensions → dedup → adversarial verify → structured result + rendered review markdown. No side effects; pure args-in/result-out.
- **Exports**:
  - workflow meta `review-fanout` - invocable via `Workflow({scriptPath|name, args})`
  - return value `{verdict, blocking, advisory, incomplete, failedDimensions, stats, review_markdown}`

### Module: review-skill dispatch

- **Maps to capability**: Review-phase integration
- **Responsibility**: parse `consensus_engine` from PRD frontmatter (loop surface: the Phase 0 flag table in `run-autopilot/references/phase-build.md` plus `references/state-schema.md`, alongside `doubt_reviewer`), invoke the workflow, write `review_markdown` to the consensus review file, surface `incomplete`/thrown errors loudly, leave legacy path untouched when flag absent.
- **Exports**:
  - dispatch instructions in `review-work-completion` and `run-autopilot` SKILL.md (prose contract; no new scripts)

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **workflows/review-fanout**: script, schemas, dimension prompts, dedup + verify pipeline.

### Core Layer (Phase 1)

- **renderer stage (inside review-fanout)**: Depends on [workflows/review-fanout].

### Integration Layer (Phase 2)

- **review-skill dispatch**: Depends on [workflows/review-fanout, renderer stage].

## Implementation Phases

### Phase 0: Foundation

**Goal**: A runnable workflow that reviews a fixture diff end-to-end with structured findings.

**Tasks**:
- [ ] Write `review-fanout.workflow.js`: meta, findings schema (proof required on CRITICAL/HIGH), dimension prompts, security trigger, dedup barrier, adversarial verify stage (no deps) - Acceptance: dry run over a fixture diff with a planted real bug and a planted plausible-but-false finding: journal shows raw > unique > confirmed; the false finding is refuted; empty `diff` arg throws.
- [ ] Fail-closed paths (no deps) - Acceptance: killing one dimension agent mid-run yields `incomplete: true` and CHANGES_REQUESTED, never APPROVE.

**Exit Criteria**: fixture dry-run produces a correct structured result; invalid input cannot produce APPROVE.

### Phase 1: Core

**Goal**: Workflow output is consumable by the existing coverage gate unchanged.

**Tasks**:
- [ ] Renderer stage producing `review_markdown` in the consensus review-file contract (depends on: Phase 0) - Acceptance: rendered file for a fixture PRD passes `check_review_file.py` (reviewers: frontmatter, per-reviewer `## <Name>` section, `Verdict:` + `Tests:` lines); docs-only fixture renders `Tests: none (docs-only)` and passes.

**Exit Criteria**: gate accepts rendered output for both code and docs-only fixtures with zero gate modifications.

### Phase 2: Integration

**Goal**: Opt-in live use from both review surfaces.

**Tasks**:
- [ ] `consensus_engine` flag parsing + dispatch in `review-work-completion` and `run-autopilot` (depends on: Phase 1) - Acceptance: flag absent → legacy path byte-identical behavior; `workflow` → consensus leg runs via Workflow; invalid value → legacy + one-line warning.
- [ ] Live probe: shadow-review this PRD's own diff (depends on: dispatch) - Acceptance: during this PRD's (00104, ex-00057) review cycle the workflow engine runs once against the PRD's real diff as a non-gating shadow beside the legacy consensus leg that gates it; the shadow's rendered file passes `check_review_file.py`, stats (raw/unique/confirmed/refuted) land in the review log, and any verdict divergence from the legacy leg is recorded as an observation, not a block.

**Exit Criteria**: one clean shadow cycle on the workflow engine against a real diff; legacy default provably untouched.

## Test Strategy

### Critical Scenarios

- **Happy path**: fixture diff with a planted off-by-one → Expected: blocking finding with evidence + proof survives verify; verdict CHANGES_REQUESTED; rendered file passes the gate.
- **Edge case**: docs-only fixture diff → Expected: APPROVE, advisory-only, `Tests: none (docs-only)` rendered, gate passes.
- **Error case**: empty `diff` / dead dimension agent → Expected: throw or `incomplete: true` + CHANGES_REQUESTED; the review session reports the failure loudly; no silent approve.

## Risks

- **CLI-in-agent hang class regression**: mitigated by the hard boundary - codex/gemini never move into the workflow; this PRD touches only the Claude-side consensus leg.
- **Coverage-gate contract drift**: mitigated by Phase 1 acceptance running the real `check_review_file.py` against rendered fixtures before any live use.
- **Refuted-by-default kills real findings**: mitigated by scoping verification to CRITICAL/HIGH only (MEDIUM/LOW always pass as advisory) and journaling confirmed/refuted stats for tuning before the default flips.
- **Workflow engine unavailable in a given session type**: mitigated by the legacy default; the flag flips only after clean opt-in cycles.
