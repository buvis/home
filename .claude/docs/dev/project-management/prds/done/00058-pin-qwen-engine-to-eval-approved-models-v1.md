---
catchup: skip
design: skip
---

# Pin Qwen Engine to Eval-Approved Models

> Source: `dev/local/qwen-leverage-assessment-2026-07-12.md` (gap G1).

## Overview

### Problem Statement

`qwen-run.sh` auto-detects its engine by probing pi providers in ascending
port order and taking the first live server. Today :8001 serves
Qwen3.6-35B-A3B (Q5, never eval'd) and outranks :8080, which hosts
Qwen3-Coder-30B-A3B-Instruct Q4_K_M, the only checkpoint that passed the
6-task agentic eval (5/6 sonnet-tier Rust tasks). use-qwen SKILL.md itself
forbids swapping models without re-running the eval (the gemma4 precedent:
wrong code plus a false "tests pass" claim). Every autopilot surface (the
`/work` implementor lane, the plan-tasks preflight, the Quinn reviewer)
therefore runs on an unqualified engine whenever :8001 is up, which risks
exactly the silent-rework waste the qwen lane was fenced against and poisons
the first Implementor Mix telemetry batches.

### Target Users

Unattended autopilot batches on this machine; anyone reading qwen telemetry
to tune the eligibility fences.

### Success Metrics

- No autopilot surface can dispatch a model id absent from the approved
  registry (proven by tests, not by convention).
- Default manual `qwen-run.sh` behavior (no new flag) stays byte-identical.
- A documented, repeatable qualification procedure exists, so Qwen3.6-35B can
  be approved after one manual eval session.

## Functional Decomposition

### Capability: Approved-model gating

The dispatch script can restrict itself to eval-qualified model ids.

#### Feature: Approved-models registry

- **Description**: A plain-text allowlist of eval-qualified model ids.
- **Inputs**: Eval results (runbook below).
- **Outputs**: `~/.claude/skills/use-qwen/scripts/approved-models.txt`, one
  model id per line, `#` comments and blank lines ignored. Initial content:
  `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q4_K_M` with a comment citing
  the 5/6 eval. The Q8_0 quant and Qwen3.6-35B are NOT listed (unqualified
  checkpoints; approval is per exact id).
- **Behavior**: Read only by `qwen-run.sh` when `--approved-only` is passed.

#### Feature: --approved-only flag in qwen-run.sh

- **Description**: Restrict provider/model resolution to registry ids.
- **Inputs**: The registry file; existing `-P`/`-m` overrides; the provider
  probe loop (models.json, ascending port order).
- **Outputs**: Same dispatch/preflight paths as today, engine guaranteed
  approved; on failure a nonzero exit whose message names the failing check
  and the registry path.
- **Behavior**: Auto-detect skips any live provider whose served id is not in
  the registry and keeps probing (so an unapproved :8001 no longer shadows an
  approved :8080). With `-m` or `-P` resolving to an unapproved id, refuse.
  Both refusals report the existing `model_id_missing` outcome class (the
  approved id is not live) so the preflight enum in
  `work/references/qwen-integration.md` and `/work` attempt logging need no
  changes. Without the flag, behavior is unchanged, including the ascending
  port rule. `--preflight --approved-only` composes: the 1-token completion
  probe runs against the approved candidate only.

### Capability: Autopilot surfaces pinned

Every autonomous qwen invocation carries the flag.

#### Feature: Call-site updates

- **Description**: Autopilot command lines gain `--approved-only`; manual use
  stays free.
- **Inputs**: `~/.claude/skills/work/references/qwen-integration.md`
  (preflight command and the dispatch prompt-template invocation),
  `~/.claude/skills/review-work-completion/SKILL.md` (step-1 Quinn preflight,
  the Reviewers-roster Quinn entry), `~/.claude/skills/use-qwen/SKILL.md`
  (docs only).
- **Outputs**: Updated command lines; use-qwen SKILL.md documents the flag in
  the options list and Quick Reference; a note that autopilot surfaces always
  pass it.
- **Behavior**: plan-tasks reaches qwen only through qwen-integration.md's
  probe definition, so it inherits the pin. Premise: verify with
  `rg -n 'qwen-run.sh' ~/.claude/skills/plan-tasks/SKILL.md` that plan-tasks
  still has no direct invocation; if one appeared since 2026-07-12, update it
  identically instead of skipping.

### Capability: Qualification path

A checkpoint can earn its way into the registry.

#### Feature: Eval runbook

- **Description**: The repeatable procedure that qualifies a candidate model.
- **Inputs**: A candidate model id served locally; recent done-PRD task
  ledgers as the task source.
- **Outputs**: `~/.claude/skills/use-qwen/references/eval-runbook.md`.
- **Behavior**: The runbook specifies: pick 6 representative tasks
  (single-file, test-gated, backend, drawn from recent completed PRD task
  ledgers); run each via `qwen-run.sh -m <candidate> -f <prompt>`; verify
  against the real test gate, never the model's self-report; pass bar is at
  least 5/6 gate-passing with zero false success claims; on pass, append the
  exact id to approved-models.txt with date and a one-line evidence pointer.
  Running the Qwen3.6-35B eval itself is manual follow-up, not a task of
  this PRD.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/
├── use-qwen/
│   ├── SKILL.md                      # Maps to: Call-site updates (docs)
│   ├── references/
│   │   └── eval-runbook.md           # Maps to: Eval runbook (new)
│   └── scripts/
│       ├── qwen-run.sh               # Maps to: --approved-only flag
│       ├── approved-models.txt       # Maps to: Approved-models registry (new)
│       └── test_qwen_run.sh          # Maps to: gating tests (extend, 16 asserts today)
├── work/references/
│   └── qwen-integration.md           # Maps to: Call-site updates
└── review-work-completion/
    └── SKILL.md                      # Maps to: Call-site updates (Quinn)
```

### Module: use-qwen scripts

- **Maps to capability**: Approved-model gating
- **Responsibility**: Resolve and health-check an engine, now optionally
  restricted to approved ids.
- **Exports**: `qwen-run.sh --approved-only` (flag), `approved-models.txt`
  (registry format: one id per line, `#` comments).

### Module: use-qwen docs

- **Maps to capability**: Qualification path
- **Responsibility**: Document the flag and the qualification procedure.
- **Exports**: `references/eval-runbook.md`, updated SKILL.md sections.

### Module: autopilot call sites

- **Maps to capability**: Autopilot surfaces pinned
- **Responsibility**: Guarantee autonomous dispatches carry the flag.
- **Exports**: Updated command lines in qwen-integration.md and
  review-work-completion SKILL.md.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **use-qwen scripts**: registry file + flag + tests.

### Core Layer (Phase 1)

- **autopilot call sites**: Depends on [use-qwen scripts] (the flag must
  exist before command lines reference it).

### Integration Layer (Phase 2)

- **use-qwen docs**: Depends on [use-qwen scripts] (documents shipped
  behavior).

## Implementation Phases

### Phase 0: Foundation

**Goal**: The flag works and is test-proven.

**Tasks**:

- [ ] Create `approved-models.txt` with the single evaled id plus provenance
  comment (no deps) - Acceptance: file exists; `qwen-run.sh` without the flag
  ignores it (existing 16 asserts still pass unchanged).
- [ ] Implement `--approved-only` in `qwen-run.sh` (auto-detect filtering,
  `-m`/`-P` refusal, preflight composition, `model_id_missing` wording) (no
  deps) - Acceptance: new asserts in `test_qwen_run.sh` cover: unapproved
  lower port + approved higher port resolves to the approved one; only
  unapproved live exits nonzero naming `model_id_missing` and the registry
  path; `-m` unapproved refused; default no-flag run byte-identical on the
  approved-path fixture.

**Exit Criteria**: `test_qwen_run.sh` fully green (old 16 asserts + new
gating asserts).

### Phase 1: Core

**Goal**: Autopilot can no longer reach an unapproved engine.

**Tasks**:

- [ ] Add `--approved-only` to every qwen command line in
  `work/references/qwen-integration.md` and the two Quinn sites in
  `review-work-completion/SKILL.md`; verify plan-tasks has no direct call
  site (depends on: Phase 0) - Acceptance:
  `rg -n 'qwen-run.sh' ~/.claude/skills` shows every autopilot-surface
  invocation carrying the flag and manual/use-qwen examples without it;
  premise re-check recorded.

**Exit Criteria**: The acceptance rg is clean.

### Phase 2: Integration

**Goal**: The path to approving new checkpoints is documented.

**Tasks**:

- [ ] Write `references/eval-runbook.md` and update use-qwen SKILL.md (flag
  docs + Quick Reference row + autopilot note) (depends on: Phase 1) -
  Acceptance: `validate_skill.py` passes with 0 errors on use-qwen, work,
  and review-work-completion; runbook states task source, pass bar, and the
  registry append step.

**Exit Criteria**: All acceptance checks above green; no autopilot surface
can dispatch an unlisted model id.

## Test Strategy

### Critical Scenarios

- **Happy path**: :8080 serves the approved id, :8001 serves an unapproved
  id, `--approved-only` auto-detect → picks :8080's engine. Expected:
  provider llamacpp, model Q4_K_M id, preflight healthy.
- **Edge case**: flag absent → ascending-port behavior identical to today
  (unapproved :8001 wins). Expected: existing asserts unchanged.
- **Error case**: only unapproved servers live under `--approved-only`.
  Expected: nonzero exit, message names `model_id_missing` and
  `approved-models.txt`.

## Risks

- **Registry/config drift**: models.json ids change and the registry goes
  stale, silently darkening the qwen lane (preflight fails, tasks fall back
  to Claude). Mitigation: the error message names the registry path; the
  audit-qwen report card (companion PRD) surfaces a zero-dispatch batch.
- **Flag omitted at a future call site**: a new autopilot surface forgets
  `--approved-only`. Mitigation: use-qwen SKILL.md states the rule; the
  Phase 1 acceptance rg doubles as the audit command for later sweeps.
