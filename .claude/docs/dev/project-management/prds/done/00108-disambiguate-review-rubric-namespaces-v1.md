---
consensus_engine: shadow
design: skip
---

# Disambiguate Review Rubric Namespaces

> Renumbered 00093 → 00108 on 2026-08-01 (backlog tail resequence; mapping in memory `project_backlog_renumber_2026_08`).

## Problem

Three review rubrics share the `R{n}` id namespace: consensus (R1-R13, 12 rules,
R5 retired), blind/Blake (R1-R19), and doubt (R1-R5). Cross-references must
carry prose disclaimers ("not review-blindly's same-named R1-R19 rubric",
review-work-completion/SKILL.md step 8), and the upcoming agent registry
(00109, ex-00094) will embed rubric ids inside agent files, where an ambiguous `R3`
becomes a latent misroute. Source: discovery 00092, must-have 6 (B rider).

## Solution

Rename the doubt set to `D1-D5` and the blind set to `B1-B19`; the consensus
set keeps `R1-R13` as the canonical R namespace. Update every emitter, parser,
test, and golden fixture in the same change so verdict lines stay in sync.
Historical review files under `dev/local/` keep their old ids untouched.

## Requirements

### Must have
- Doubt rubric ids become `D1-D5` in rule source, prompt, emit-verbatim block,
  docs, state schema docs, tests, and goldens.
- Blind rubric ids become `B1-B19` in rule source, skill, assembly prompt,
  and contract tests.
- Consensus `R1-R13` unchanged (rubric.md, workflow `RUBRIC_IDS`, schemas,
  tests).
- Generic `R{n}`-shaped contract text (retry-policy.md verdict-line regex,
  output-formats.md examples) generalized to accept `R|D|B` prefixes.
- Obsolete collision-disclaimer prose removed where the collision no longer
  exists.
- Rule ids stay stable within each set (rename prefix only, never renumber).

### Nice to have
- None.

## Implementation

Premise: the three sets and their reference sites are as inventoried on
2026-07-31 (recon of discovery 00092). At execution, re-locate each site by
content (`rg 'R[0-9]'` per tree), not by the line numbers below; a site that
no longer exists is skipped and reported, never forced.

### Module: doubt-rubric (D1-D5)
- **Location**: `skills/run-autopilot/`
- **Responsibility**: doubt lens rule source and all its consumers.
- **Files**: `references/doubt-review-rubric.md`, `prompts/doubt-review.md`
  (rules + emit-verbatim block), `SKILL.md`, `references/phase-review.md`,
  `references/phase-done.md`, `references/batch-report-format.md`,
  `references/state-schema.md` (`doubts_rubric_verdicts`),
  `scripts/test_review_prompt_contracts.py` (id-set assertion → `{D1..D5}`),
  `scripts/golden/review-converged.md`, `scripts/test_codex_review_run.py`,
  `cli/test_records.py`.

### Module: doubt-cross-refs
- **Location**: `skills/review-work-completion/`
- **Responsibility**: consensus-side references to the doubt lens.
- **Files**: `SKILL.md` (roster, assembly, step 8),
  `references/agent-invocation.md`, `references/agent-prompts.md` (Bob
  doubt-lens appendix), `references/review-coverage-format.md`.

### Module: blind-rubric (B1-B19)
- **Location**: `skills/review-blindly/` + `skills/review-work-completion/`
- **Responsibility**: blind lens rule source and consumers.
- **Files**: `review-blindly/references/rubric.md`, `review-blindly/SKILL.md`,
  `review-work-completion/references/blind-lens-prompt.md`,
  `review-work-completion/SKILL.md` (reference list + step 8 disclaimer),
  `run-autopilot/scripts/test_review_prompt_contracts.py` (blind verdict-line
  contract).

### Module: id-shape-generalization
- **Location**: `skills/review-work-completion/references/`
- **Responsibility**: set-agnostic verdict-line shape.
- **Files**: `retry-policy.md` (verdict-line pattern), `output-formats.md`
  (rubric-line examples).

### Dependencies
- doubt-rubric: no dependencies (foundation).
- doubt-cross-refs: depends on [doubt-rubric].
- blind-rubric: no dependencies (foundation).
- id-shape-generalization: depends on [doubt-rubric, blind-rubric].

## Tasks

### Phase 0: Rule sources
- [ ] Rename doubt ids R1-R5 → D1-D5 in `doubt-review-rubric.md` and
  `prompts/doubt-review.md` - Acceptance: `rg -c 'D[1-5]'` matches in both;
  `rg 'R[0-9]'` in both returns nothing.
- [ ] Rename blind ids R1-R19 → B1-B19 in `review-blindly/references/rubric.md`
  and `review-blindly/SKILL.md` - Acceptance: same rg pattern pair on that
  tree.

### Phase 1: Consumers and contracts
- [ ] Update all doubt-rubric consumers and doubt-cross-refs files (list
  above), including tests and goldens (depends on: Phase 0) - Acceptance:
  `uv run pytest skills/run-autopilot/scripts/ skills/run-autopilot/cli/`
  green; `rg 'R[0-9]' skills/run-autopilot` reports no rubric-id references.
- [ ] Update blind consumers (`blind-lens-prompt.md`, reference list,
  blind contract test) (depends on: Phase 0) - Acceptance: contract tests
  green; `rg 'R[0-9]' skills/review-blindly` reports nothing.
- [ ] Generalize `R{n}` shape in `retry-policy.md` and `output-formats.md` to
  `[RDB]{n}`; drop obsolete collision disclaimers (depends on: prior two) -
  Acceptance: `uv run pytest skills/review-work-completion/scripts/` green.

## Success Criteria

- `rg '\bR[0-9]+\b'` across `skills/run-autopilot`, `skills/review-blindly`
  finds zero rubric-id references; consensus set intact in
  `skills/review-work-completion/references/rubric.md` and
  `workflows/review-fanout.workflow.js`.
- All python contract suites and `node --test workflows/*.test.mjs` green.
- No file renumbers a rule; prefixes only.
