# Cartographer Phase 6 — Forecast Extensibility (Optional Lens)

> Source discovery: `dev/local/discovery/00008-cartographer-forecast-extensibility.md`
> Parent architecture: `dev/local/discovery/00001-cartographer-architecture.md`
> Depends on PRDs: `00009-cartographer-foundation-v1.md`, `00011-cartographer-survey-atlas-v1.md`, `00013-cartographer-architect-v1-deferred.md` (plan persistence; optional grounding)
>
> **Status: DEFERRED.** Pure pre-commit checklist; deferral driven by demand signal, not infrastructure cost. Tracking PRD: `00019-cartographer-evaluate-phase-4-6-reactivation-v1.md`.
>
> **Revision 2026-07-07: SUPERSEDED as a standalone skill.** Spirit folded into `design-solution`'s template: "Alternatives considered" now requires a smallest-diff option (section 2 of the forecast), and "Risks & edge cases" now names the likely next changes and what the design boxes in (sections 1 and 3). The persistence + audit schema + pytest ceremony is dropped - it would have tested LLM prose shape, which pytest cannot bind. Doubt review already probes the same lens at the end of the pipeline.
>
> **Re-verified 2026-08-23: implementable but redundant, stay cancelled.** Nothing structurally blocks this PRD; it died to redundancy, not infeasibility. The fold-in verified in `design-solution/SKILL.md`: "Alternatives considered" mandates a smallest-diff option, "Risks & edge cases" requires the 2-3 likely next changes. If a reactivation criterion fires, sharpen the `design-solution` template - do not resurrect this PRD.

## Reactivation Criteria

This PRD un-defers when ANY hold:

- User reports ≥3 "wish I'd thought about the next change" incidents in the last month.
- `audit-echo` fire rate has flatlined (system steady-state — Echo + Atlas + Recon Brief aren't surfacing new patterns; time to look forward).
- User explicitly requests it on demand.

Reassess monthly via `00019`.

### Decision Log

(populated by `00019` evaluations: `YYYY-MM-DD: <verdict> (<rationale>)`)

- 2026-07-07: superseded (folded into `design-solution` template sections "Alternatives considered" and "Risks & edge cases")
- 2026-08-23: stay cancelled (fold-in verified in design-solution SKILL.md; on reactivation signal, sharpen design-solution instead)

## Overview

### Problem Statement

Even after discovery is enforced (Phases 1–5), agents tend to write code that's optimal for the immediate task but hostile to the next 3 likely changes. `/forecast-extensibility` is an on-demand checklist that surfaces this before commit: what comes next, what does this change make harder, what's the smallest-diff version of the same idea. Counters both over-engineering (designing for hypothetical futures) and under-engineering (boxing future work into a corner).

### Target Users

The user (manually invokes before commit or end of plan) and `/architect` (mentions it as a suggested next step).

### Success Metrics

- Manual: spot-check 5 forecasts for non-trivial signal (avoid generic "add more tests" outputs).
- Skill is self-contained — invocation requires no setup beyond Atlas existing.
- Output references atlas-derived extension points and concrete `file:line` locations (not generic statements).
- Optional persistence saves forecast to `cartographer/projects/<hash>/forecasts/<slug>-<date>.md` for retrospective comparison.
- audit-cartographer (post-MVP) tracks invocation rate via audit log.

## Functional Decomposition

### Capability: Atlas-Grounded Forecast

Skill emits a structured checklist grounded in `atlas.md`.

#### Feature: Skill entry (`/forecast-extensibility`)

- **Description**: Markdown skill at `~/.claude/skills/forecast-extensibility/SKILL.md` (action-verb name per coding-style.md, renamed from `/foresight` per Q8).
- **Inputs**: optional task description (skill argument); optional `--no-save` flag; optional `--from-plan <slug>` flag.
- **Outputs**: structured markdown with three sections.
- **Behavior**: Resolve project hash; read `atlas.md`; if a plan slug is provided, also read `cartographer/projects/<hash>/plans/<slug>.md`; render the three-section template grounded in atlas.

#### Feature: Three-section structured output

- **Description**: Fixed output shape so audit-cartographer (post-MVP) can compare predicted next-changes against actual subsequent commits.
- **Inputs**: atlas.md, optional plan body, current change context.
- **Outputs**: markdown with sections:
  1. **Likely next changes (3)**: numbered list, each item references atlas-derived extension points or recently-touched layers.
  2. **Smallest-diff version**: 2–4 sentences describing the same idea with minimal code change (challenges current implementation if larger than needed).
  3. **Extensibility blockers**: list of decisions in the current change that constrain the 3 likely next changes (each with `file:line` location when possible).
- **Behavior**: Skill prompt enforces specificity — must reference atlas-derived extension points (no generic "add more tests, refactor later"); when grounding is weak, output disclaimer.

#### Feature: Atlas-missing graceful degradation

- **Description**: When `atlas.md` is absent, the skill still runs but with reduced grounding and an explicit disclaimer.
- **Inputs**: atlas presence check.
- **Outputs**: markdown with leading "*atlas missing — output is less grounded; consider /survey first*" disclaimer; audit `event:forecast-skipped-no-atlas` (informational; skill still produces output).
- **Behavior**: Don't block; emit the three sections but flag reduced confidence.

### Capability: Optional Persistence

Save forecasts to disk for retrospective audit-cartographer comparison.

#### Feature: Persistence to `cartographer/projects/<hash>/forecasts/<slug>-<date>.md`

- **Description**: Default-on; user can opt out per invocation with `--no-save`.
- **Inputs**: forecast body, slug, project hash, current date (UTC).
- **Outputs**: markdown file written.
- **Behavior**: Slug = lowercase kebab of task summary; filename `<slug>-<YYYY-MM-DD>.md`; collision suffix `-N` on same-day repeat. Atomic write.

### Capability: Audit Emission

Per Cartographer's pattern — every invocation logged.

#### Feature: Audit-log emission

- **Description**: Append events with `phase: "forecast"`.
- **Inputs**: event type, repo_hash, task_slug, atlas_present, output_path.
- **Outputs**: side effect — JSONL line.
- **Behavior**: Schema fields: `ts`, `session`, `phase: "forecast"`, `event` ∈ {forecast-invoked, forecast-skipped-no-atlas}, `repo_hash`, `task_slug` (invoked only), `atlas_present` (bool), `output_path` (invoked only when persistence enabled).

### Capability: `/architect` Cross-Reference

`/architect` mentions `/forecast-extensibility` as a suggested final step.

#### Feature: SKILL.md cross-link

- **Description**: Edit `~/.claude/skills/architect/SKILL.md` (Phase 4) to mention `/forecast-extensibility` in its closing section.
- **Inputs**: skill markdown edit.
- **Outputs**: text update only.
- **Behavior**: One-line "Consider running `/forecast-extensibility` after this plan" suggestion. No auto-invocation in v1 (per discovery Q's recommendation).

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── skills/
│   ├── forecast-extensibility/
│   │   └── SKILL.md                                # Skill entry
│   └── architect/
│       └── SKILL.md                                # Edited: mention /forecast-extensibility
├── hooks/
│   └── tests/
│       └── test_forecast_extensibility.py
└── cartographer/projects/<hash>/forecasts/         # per-task persisted markdown
    └── <slug>-<YYYY-MM-DD>.md
```

### Module: `skills/forecast-extensibility/SKILL.md`

- **Maps to capability**: All — atlas-grounded forecast, three-section template, persistence, audit, atlas-missing handling.
- **Responsibility**: Markdown is the entire implementation; no scripts in v1.

### Module: `skills/architect/SKILL.md` (edited, not new)

- **Maps to capability**: `/architect` Cross-Reference.
- **Responsibility**: Append a one-liner suggesting `/forecast-extensibility`.

### Module: `tests/test_forecast_extensibility.py`

- **Maps to capability**: Output structure validation, atlas-missing path, persistence, slug collision, audit emission.

## Dependency Graph

### Upstream (required)

- Phase 0 (`00009`): `_lib_cartographer.py` (project_hash, atlas_dir, append_audit).
- Phase 2 (`00011`): atlas.md grounding source. Phase 6 degrades gracefully when missing.

### Upstream (optional)

- Phase 4 (`00013`): plan persistence to `cartographer/projects/<hash>/plans/<slug>.md`. When `--from-plan <slug>` flag is used, the forecast is grounded against that plan.

### Phase 6 (this PRD)

- **`SKILL.md`** depends on Phase 0 + Phase 2.
- **`architect/SKILL.md` edit** depends on Phase 4 SKILL.md existing.
- **Tests** depend on the above.

### Downstream (out of scope here)

- audit-cartographer post-MVP compares predicted next-changes against actual subsequent commits.

## Implementation Phases

### Phase 6a: Skill skeleton + three-section template

**Goal**: `/forecast-extensibility` produces structured output grounded in atlas.

**Tasks**:

- [ ] Author `~/.claude/skills/forecast-extensibility/SKILL.md` with arg parsing (`--no-save`, `--from-plan <slug>`), atlas resolution, three-section template prompt enforcing specificity. (depends on: Phase 0 + Phase 2) — Acceptance: manual invocation against a fixture repo with atlas produces well-formed output naming concrete `file:line` items.
- [ ] Atlas-missing path: emit disclaimer ("*atlas missing — output is less grounded; consider /survey first*") + still produce three sections; audit `event:forecast-skipped-no-atlas`. (depends on: above) — Acceptance: manual run on no-atlas repo behaves as documented.

**Exit Criteria**: Skill callable; output matches three-section shape on both atlas-present and atlas-missing paths.

### Phase 6b: Persistence + slug collision

**Goal**: Forecasts persist by default for retrospective comparison.

**Tasks**:

- [ ] Write output to `~/.claude/cartographer/projects/<hash>/forecasts/<slug>-<YYYY-MM-DD>.md` by default; honor `--no-save`. (depends on: 6a) — Acceptance: file present after invocation; missing when `--no-save` set.
- [ ] Same-day collision suffix `-N`. (depends on: above) — Acceptance: pytest covers second invocation same day same slug → `-2` suffix.

**Exit Criteria**: Persistence works as documented; downstream audit-cartographer can find these files.

### Phase 6c: Plan-grounded forecast

**Goal**: `--from-plan <slug>` integrates Phase 4 plan output as additional grounding.

**Tasks**:

- [ ] When `--from-plan <slug>` is set, read `cartographer/projects/<hash>/plans/<slug>.md` and incorporate into prompt context. (depends on: 6a + Phase 4) — Acceptance: forecasts reference plan items by name; missing plan path emits warning + falls back to atlas-only.

**Exit Criteria**: Plan-grounded forecasts produce more specific output than atlas-only.

### Phase 6d: `/architect` cross-link + audit + tests

**Goal**: Lock cross-skill UX; lock behavior with pytest.

**Tasks**:

- [ ] Edit `~/.claude/skills/architect/SKILL.md` to mention `/forecast-extensibility` as a suggested next step at the end of the plan. (depends on: Phase 4) — Acceptance: manual `/architect` output ends with the suggestion line.
- [ ] Emit audit events with full schema. (depends on: 6a–6c) — Acceptance: invocations produce `forecast-invoked` events; missing-atlas runs produce `forecast-skipped-no-atlas`.
- [ ] Write `tests/test_forecast_extensibility.py` covering: output shape, atlas-missing, `--no-save`, `--from-plan`, slug collision, audit emission. (depends on: above) — Acceptance: pytest green; coverage >80%.

**Exit Criteria**: All tests green; cross-link visible.

## Test Strategy

### Critical Scenarios

- **Happy path — atlas present**: invoke `/forecast-extensibility "extract auth into a service"` on repo with atlas; output contains numbered "Likely next changes (3)", "Smallest-diff version", "Extensibility blockers"; each next-change names an atlas extension point or layer; blockers cite `file:line`.
- **Happy path — `--from-plan`**: existing plan at `cartographer/projects/<hash>/plans/<slug>.md`; invocation references plan items by name in next-changes section.
- **Edge case — atlas missing**: skill still produces three sections, with leading disclaimer; audit `event:forecast-skipped-no-atlas`.
- **Edge case — `--no-save`**: file not written; audit event still emitted with `output_path: null`.
- **Edge case — slug collision**: two invocations same day same task → second saves with `-2` suffix.
- **Edge case — generic output detection**: skill prompt enforces specificity; manual review checks output isn't "add more tests, refactor later".
- **Error case — corrupt atlas.md**: skill still attempts; falls back to disclaimer + three sections from inferred context; no crash.
- **Error case — invalid `--from-plan` slug**: skill warns, falls back to atlas-only, audit notes the missing plan.

## Risks

- **Output becomes generic**: skill prompt enforces specificity (must reference atlas-derived extension points and concrete file:line locations). *Mitigation*: prompt gating + manual spot-check after first 5 invocations.
- **User doesn't invoke**: fine — skill is opt-in by design.
- **Atlas missing**: skill works but with reduced grounding; output disclaimer makes degradation explicit.
- **Forecast files accumulate**: out of scope here; audit-cartographer post-MVP comparison gives the files purpose; cleanup deferred.
- **Audit comparison post-MVP requires stable schema**: lock the three-section output shape now so comparison stays viable later.

## Open Questions

Carried from discovery doc:

- **Output shape**: confirmed — structured (numbered next-changes + smallest-diff + blockers).
- **`/architect` auto-runs `/forecast-extensibility`**: deferred; v1 ships as user-invoked only; `/architect` mentions it as suggested next step.
- **Save outputs to disk**: confirmed — yes, default-on; opt out with `--no-save`.
