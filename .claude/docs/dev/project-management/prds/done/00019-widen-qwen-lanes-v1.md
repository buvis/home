---
catchup: skip
design: skip
---

# Widen Qwen Lanes

## Overview

### Problem Statement

A Qwen3.6-35B-A3B with 131K context is served locally for free (`start_qwen` / llama-server), and the routing plumbing exists (`qwen_eligible` flag from plan-tasks, preflight, one-shot attempt budget in `/work`). Yet utilization is near zero: eligibility is fenced to backend AND ≤2 files AND haiku/sonnet tier, so typical plans qualify nothing (the current wip PRD planned 3/3 sonnet tasks, none qwen-eligible). Meanwhile Diana - a *cloud* Sonnet reviewer via `sonnet-run.sh` - burns paid quota on every review cycle doing a job a free local model can attempt, and a known preflight defect ("false healthy": the endpoint lists the model with HTTP 200 while completions 500) can burn qwen's one-shot budget on an infrastructure failure, mis-recording model capability.

Three widenings, all bounded by the existing safety rails (one-shot budget, test-gated tasks, consensus filtering): honest preflight, wider task eligibility, and qwen as the fourth review voice replacing cloud-Sonnet Diana.

### Target Users

Unattended batches on this machine (quota savings, more parallel free work); qwen capability telemetry.

### Success Metrics

- Preflight cannot report healthy without a real 1-token completion succeeding against the served model.
- `qwen_eligible` widens to: non-UI AND tier ∈ {haiku, sonnet} AND ≤3 files AND no cross-module contract change (no public API/schema/signature edits) - and plan-tasks records WHY a task was excluded (`qwen_excluded_reason`), making under-routing auditable per batch.
- The review roster's fourth voice is **Quinn** (local qwen via `qwen-run.sh`, advisory weight) instead of Diana (cloud sonnet); `sonnet-run.sh` stays for manual `/use-sonnet` but no autopilot surface dispatches it.
- Quinn's findings are advisory: they enter consolidation only when at least one other reviewer concurs (consensus ≥2 including Quinn) - local-model noise cannot create rework tasks alone.
- The batch report renders an implementor histogram (qwen/claude/gemini dispatch counts + preflight outcomes) from `state.tasks[].attempts`, so utilization is a number, not a feeling.
- llama-server down → everything degrades to today's behavior (Claude tiers, Quinn skipped) with a one-line note; never a failure.

## Functional Decomposition

### Capability: Make preflight honest

#### Feature: Probe with a real completion

- **Description**: Preflight passes only when a completion actually works.
- **Inputs**: The qwen preflight implementation - locate at execution via `rg -ln "preflight" ~/.claude/skills/use-qwen ~/.claude/skills/work/references/qwen-integration.md` (memory records the false-healthy incident: model listed via `/v1/models` 200, worker spawn 500).
- **Outputs**: Preflight's health check sends a 1-token completion request to the served model (max_tokens=1, short timeout) and treats any non-2xx or timeout as `endpoint_unreachable`; the `/v1/models` listing check may remain as a faster pre-check but can no longer be the deciding signal. `preflight_outcome` values in the attempt log unchanged.
- **Behavior**: A failed probe routes to Claude at the task's tier (existing fallback), does NOT consume the one-shot qwen budget (no qwen attempt happened), and is recorded as the preflight outcome.

### Capability: Widen task eligibility

#### Feature: Relax the qwen_eligible classifier

- **Description**: More mechanical tasks qualify; exclusions become auditable.
- **Inputs**: `~/.claude/skills/plan-tasks/SKILL.md` tier/eligibility classifier (the step that computes `qwen_eligible`, companion of PRD 00032); `~/.claude/skills/work/SKILL.md` routing table + `references/qwen-integration.md`.
- **Outputs**: Eligibility rule becomes: non-UI AND tier ∈ {haiku, sonnet} AND estimated ≤3 files AND the task edits no public contract (exported API signature, schema, wire format, hook registration shape). plan-tasks writes `qwen_excluded_reason` metadata (one of `ui|tier|files|contract`) on every ineligible task. The work skill's routing table text updates to the same rule; the one-shot budget, step-5.5 sonnet-escalation carve-out, and opus exclusion stay verbatim.
- **Behavior**: Legacy plans without the new metadata behave exactly as today (absent → `false`).

### Capability: Local fourth review voice

#### Feature: Replace Diana with Quinn

- **Description**: The optional fourth reviewer becomes free and local.
- **Inputs**: `~/.claude/skills/review-work-completion/SKILL.md` roster + prerequisites + single-message launch rule; `~/.claude/skills/use-qwen/scripts/qwen-run.sh` (background-Bash dispatch with `-o` output file, same pattern as Bob/Carl - never Agent-wrapped, per the codex-hang lesson).
- **Outputs**: Roster: Diana's entry replaced by **Quinn** → local qwen via `qwen-run.sh` (optional; active when the preflight probe from this PRD passes; skipped otherwise with a note). Consolidation gains the advisory rule: findings unique to Quinn are listed under `advisory (local model, unconfirmed)` and create no tasks; findings where Quinn concurs count toward consensus normally. Blind/doubt lens prompts (PRD 00015) are NOT given to Quinn - he runs the standard implementation-aware review prompt.
- **Behavior**: `use-sonnet` skill and `sonnet-run.sh` remain untouched for manual use. Review-file "which reviewers ran" note now names Quinn/skip reason. Precondition (re-verify at execution): every child CLI invocation in `qwen-run.sh` guards stdin with `< /dev/null`. PRD 00042 (later by sequence) owns the full guard+test sweep across all four dispatch scripts; if `qwen-run.sh` is still unguarded when Quinn goes live, add the guard to its child invocations as part of this swap - an unguarded child CLI in an unattended review batch is the PRD-00040 hang class.

### Capability: Utilization telemetry

#### Feature: Implementor histogram in the batch report

- **Description**: Every batch states who did the work.
- **Inputs**: `state.tasks[].attempts[]` (`implementor`, `preflight_outcome` fields already logged by `/work`); Phase 9 batch report render; `references/batch-report-format.md`.
- **Outputs**: A `### Implementor Mix` subsection per batch: counts of attempts by implementor (claude/qwen/gemini), qwen preflight outcomes, and count of tasks excluded per `qwen_excluded_reason`.
- **Behavior**: Absent fields (legacy tasks) count as `unknown`; render never fails the report.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/use-qwen/                        # preflight probe fix (locate exact file at execution)
~/.claude/skills/work/references/qwen-integration.md   # preflight contract + routing text
~/.claude/skills/work/SKILL.md                    # routing table rule text
~/.claude/skills/plan-tasks/SKILL.md              # eligibility + qwen_excluded_reason
~/.claude/skills/review-work-completion/SKILL.md  # Quinn roster + advisory rule
~/.claude/skills/run-autopilot/SKILL.md + references/batch-report-format.md  # histogram render
```

### Module: use-qwen

- **Maps to capability**: Make preflight honest
- **Responsibility**: 1-token completion probe as the health signal
- **Exports**: preflight outcomes consumed by /work routing

### Module: plan-tasks + work

- **Maps to capability**: Widen task eligibility
- **Responsibility**: Eligibility rule + exclusion reasons; routing unchanged otherwise
- **Exports**: `qwen_eligible`, `qwen_excluded_reason` metadata

### Module: review-work-completion

- **Maps to capability**: Local fourth review voice
- **Responsibility**: Quinn dispatch + advisory consolidation rule
- **Exports**: roster contract

### Module: run-autopilot

- **Maps to capability**: Utilization telemetry
- **Responsibility**: Implementor Mix render
- **Exports**: batch-report subsection

## Dependency Graph

### Foundation Layer (Phase 0)

- **preflight probe**: independent; everything routes through it

### Core Layer (Phase 1)

- **eligibility widening**: depends on [preflight probe] (wider routing needs honest health)
- **Quinn swap**: depends on [preflight probe] (Quinn's active-check uses it)

### Integration Layer (Phase 2)

- **telemetry**: depends on Core (renders what the widened routing produces)
- **verification**: depends on all

## Implementation Phases

Premise rule: PRD 00015 runs first by sequence (roster shape includes Blake); re-verify the roster section and Diana's entry exist as described before the swap (`rg -n "Diana" skills/review-work-completion/SKILL.md`). Re-verify whether the preflight already sends a completion (the false-healthy fix may have landed since authoring) - if it does, record `no change needed` for that task and proceed.

### Phase 0: Preflight

**Tasks**:

- [ ] 1-token completion probe (no deps) - Acceptance: health = completion 2xx; `/v1/models` alone can no longer pass; failed probe → `endpoint_unreachable`, no budget burn; existing preflight tests adapted + a false-healthy regression test (models-200/completion-500 → unhealthy), watched fail against old code

### Phase 1: Routing and roster

**Tasks**:

- [ ] Widen eligibility + exclusion reasons (depends on: Phase 0) - Acceptance: plan-tasks rule text matches the spec; `qwen_excluded_reason` written for ineligible tasks; work routing text consistent; one-shot budget text verbatim-unchanged
- [ ] Swap Diana → Quinn with advisory rule (depends on: Phase 0) - Acceptance: roster names Quinn (qwen-run.sh, background Bash, `-o` file); advisory consolidation rule present; `rg -n "sonnet-run.sh" skills/review-work-completion/` returns nothing; use-sonnet skill untouched; qwen-run.sh child stdin guarded (add if missing, per Behavior); any test asserting the literal `sonnet-run.sh`/Diana roster adapted (00042's audit records one such assert)

### Phase 2: Telemetry and proof

**Tasks**:

- [ ] Implementor Mix in the batch report (depends on: Phase 1) - Acceptance: render instruction + format documented with unknown-field fallback
- [ ] Live verification (depends on: all) - Acceptance: with llama-server up, a scratch review cycle lists Quinn's output and a qwen-eligible scratch task dispatches qwen (attempt log pasted); with the server down, both degrade with skip notes; evidence pasted

**Exit Criteria**: Success metrics all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: server up, 2-file sonnet backend task → Expected: qwen implements, tests gate it, attempt logged `implementor: qwen`
- **Edge case**: models endpoint 200 but completion 500 → Expected: preflight unhealthy, Claude fallback, no qwen budget burn (regression test)
- **Edge case**: Quinn alone flags an issue → Expected: listed as advisory, zero tasks created; Quinn + Alice flag it → normal consensus finding
- **Edge case**: server down entirely → Expected: today's behavior + skip notes; batch drains
- **Error case**: qwen produces a failing implementation → Expected: existing one-shot budget escalates to Sonnet, no qwen retry (unchanged rule)

## Risks

- **Local-model review noise**: contained by advisory weighting; if Quinn proves consistently concurring over a few batches, promote to full weight then (data via Implementor Mix + review files).
- **Wider eligibility ships worse first drafts**: contained by the unchanged one-shot budget + per-task tests + review lenses; the failure cost is one wasted local attempt, which is the cheap kind.
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; no CHANGELOG entries.
