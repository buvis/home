# Agoge Execution Harnesses: Browser, Data, Perf, Security, Authoring

Source: `dev/local/discovery/00091-product-qa-agent-pack.md` (PRD 3 of 5; depends on gym 00099 and core pack 00100).

## Overview

### Problem Statement

After 00100 the pack orchestrates and reports, but four lanes (Judy's browser, Heidi's db probing, Peggy's measurements, Trudy's runtime probing) run on charter and gap analysis alone, and no specialist can leave durable tests behind. Without real execution harnesses the pack cannot hit its catch bar, and "unverified" dominates the report.

### Target Users

The specialists themselves (each harness is a playbook a dispatched agent follows) and the repo owner reading reports that now say verified because something actually ran.

### Success Metrics

- Full gym bar met: >=70% of all seeds caught aggregated across both fixtures AND 100% of CRITICAL seeds (`bin/score` exit 0).
- CLI fixture run shows Judy loud-skipping; web fixture run shows browser-only seeds caught.
- Headless run (claude -p) completes without orphaned servers or the ~5s background-bash kill eating a lane.

## Functional Decomposition

### Capability: Browser Harness

#### Feature: Playwright Lane
- **Description**: Judy (and Walter for web journeys) drives the real UI headlessly via the project's own Playwright setup.
- **Inputs**: Profile strategy naming the Playwright config and dev-server command.
- **Outputs**: Findings with per-journey evidence (spec output, screenshots where cheap).
- **Behavior**: Only when the project has Playwright (per discovery: browser-dependent work degrades gracefully). Doctrine from `strunk:e2e-testing` (POM, artifacts). Dev server runs as background Bash with the Watcher pattern and `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` so headless sessions do not orphan or kill it early; server torn down at lane end.

#### Feature: Interactive Browser Lane
- **Description**: claude-in-chrome as Judy's fallback surface in interactive sessions only.
- **Inputs**: Profile strategy marking the surface interactive-only.
- **Outputs**: Findings labeled interactive-run.
- **Behavior**: Never selected in unattended runs; unattended + no Playwright = loud skip naming what was not exercised.

### Capability: Data Harness

#### Feature: Live DB and Contract Probes
- **Description**: Heidi exercises db state and cross-component contracts with real calls.
- **Inputs**: Profile strategy (connection/bootstrap commands, reachable services, mocking strategy for the rest).
- **Outputs**: Findings; every probe labeled live or mocked.
- **Behavior**: Live probes run against project-provided local infra (its docker-compose, sqlite file, dev server). Unreachable externals use Olivia's assigned mocking strategy and report mocked, never verified. No credentials invented; missing access = unverified, loud.

### Capability: Perf Harness

#### Feature: Runtime Measurement
- **Description**: Peggy measures real commands and endpoints against stated budgets.
- **Inputs**: Profile strategy (targets, budgets from docs/README where stated, else observation-only).
- **Outputs**: Findings with numbers (wall time, obvious blowups); observation-only results marked as no-budget.
- **Behavior**: Measures the armed product, not microbenchmarks; a budget stated in project docs that the product misses is a finding (this is how the gym's perf seed is caught).

### Capability: Security Harness

#### Feature: Runtime Security Probes
- **Description**: Trudy probes runtime behavior: secrets in logs/output, debug endpoints, permissive defaults, injection at real boundaries.
- **Inputs**: Profile strategy with the own/authorized-project assertion.
- **Outputs**: Findings with reproduction evidence.
- **Behavior**: Refuses without the profile assertion. Own/authorized projects only; probes are runtime observations of the product's behavior, not exploit development.

### Capability: Authoring Playbook

#### Feature: Durable Test Authoring
- **Description**: A strategy Olivia can assign to any specialist: leave a passing test suite behind.
- **Inputs**: Authoring assignment in the profile (which specialist, which surface, which framework).
- **Outputs**: Test suite committed on a branch (`agoge/authored-tests-<date>`) in the target repo; branch name in the report.
- **Behavior**: Suites bind to intent per `rules/testing.md` and pass before commit. The authoring doctrine is copied INTO the playbook at build time from the Tess/Devon prompt assets (`work/references/test-author-prompt.md`, `adversarial-test-prompt.md`) and `strunk:{e2e,python,rust}-testing` - the playbook must be self-contained, with no runtime references to personal-cluster paths (extraction contract, 00103). Never commits to the target's working branch.

### Capability: Degradation Rules

#### Feature: Status Taxonomy Enforcement
- **Description**: One shared vocabulary across all lanes: verified | unverified | mocked | skipped.
- **Inputs**: Lane outcomes.
- **Outputs**: Report header counts per lane (00100 report contract, unchanged).
- **Behavior**: verified requires execution evidence; skipped names the missing surface; the master rejects a specialist result claiming verified without evidence and downgrades it to unverified with a note.

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── agents/                       # bodies gain a one-line pointer to their playbook
│   ├── judy.md                   # Maps to: Browser Harness
│   ├── heidi.md                  # Maps to: Data Harness
│   ├── peggy.md                  # Maps to: Perf Harness
│   ├── trudy.md                  # Maps to: Security Harness
│   └── walter.md                 # web-journey pointer only
└── skills/run-agoge/references/
    ├── browser-playbook.md       # Maps to: Browser Harness
    ├── data-playbook.md          # Maps to: Data Harness
    ├── perf-playbook.md          # Maps to: Perf Harness
    ├── security-playbook.md      # Maps to: Security Harness
    ├── authoring-playbook.md     # Maps to: Authoring Playbook
    └── finding-contract.md       # gains the status-taxonomy section
```

Playbooks live in the skill (extraction-clean, `${CLAUDE_SKILL_DIR}` pathing); dispatch prompts inline the relevant playbook, keeping agent bodies thin and under the 50KB prompt budget.

### Module: playbooks
- **Maps to capability**: Browser/Data/Perf/Security Harness, Authoring Playbook
- **Responsibility**: Concrete per-lane execution doctrine + degradation behavior.
- **Exports**: Five playbook references consumed by `run-agoge` dispatch prompts.

### Module: run-agoge (extended)
- **Maps to capability**: Degradation Rules
- **Responsibility**: Select playbook per strategy, enforce the status taxonomy, manage background servers headless-safely.
- **Exports**: Same `/run-agoge` entry point; no interface change.

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies within this PRD - built first (external deps: 00099 gym, 00100 pack).

- **finding-contract.md status taxonomy**: Shared vocabulary everything else reports in.

### Core Layer (Phase 1)
- **browser/data/perf/security playbooks**: Depend on [status taxonomy].

### Integration Layer (Phase 2)
- **authoring-playbook + run-agoge wiring + full-bar scoring**: Depends on [all playbooks].

## Implementation Phases

### Phase 0: Foundation
**Goal**: Taxonomy locked before lanes report in it.

**Tasks**:
- [ ] Add status taxonomy to `finding-contract.md`; master downgrades evidence-less verified claims (no deps) - Acceptance: a fabricated specialist result claiming verified without evidence lands in the report as unverified with a downgrade note.

**Exit Criteria**: Taxonomy section merged; 00099 scorer still parses reports.

### Phase 1: Core
**Goal**: Four execution lanes real.

**Tasks**:
- [ ] Browser playbook (Playwright + interactive fallback + loud skip) (depends on: Phase 0) - Acceptance: web fixture browser-only seed caught headlessly; CLI fixture Judy lane = skipped with named reason; unattended run never selects claude-in-chrome.
- [ ] Data playbook (live vs mocked) (depends on: Phase 0) - Acceptance: gym dead-integration seed caught live; an unreachable-external probe reports mocked, never verified.
- [ ] Perf playbook (depends on: Phase 0) - Acceptance: gym perf seed caught with a measured number in the finding.
- [ ] Security playbook (depends on: Phase 0) - Acceptance: gym security seed caught; run without profile authorization assertion refuses and reports skipped.

**Exit Criteria**: Each lane catches its gym seed class on the relevant fixture.

### Phase 2: Integration
**Goal**: Authoring + full bar.

**Tasks**:
- [ ] Authoring playbook + branch-commit flow (depends on: Phase 1) - Acceptance: on the web fixture with an authoring assignment, a passing Playwright suite lands on an `agoge/authored-tests-*` branch; target working branch untouched (`git -C <fixture> status` clean); playbook self-contained (no `/Users/bob`, `work/references/`, or `rules/*.md` references remain in any playbook file).
- [ ] Full scored run, both fixtures, headless (depends on: Phase 1) - Acceptance: `bin/score` exit 0 (>=70% aggregate + 100% CRITICAL); run via `claude -p` leaves no orphaned dev-server process.

**Exit Criteria**: The fixed bar met headlessly; degradation cases loud.

## Test Strategy

### Critical Scenarios
- **Happy path**: full run on web fixture → Expected: browser/data/perf/security seeds caught, statuses all evidence-backed.
- **Edge case**: CLI fixture (no browser, no db service) → Expected: Judy skipped loud, Heidi mocked-or-live per profile, score still passes CLI-share of the bar.
- **Error case**: dev server fails to boot → Expected: browser lane unverified with boot log excerpt; no hang (Watcher), no orphan.

## Risks

- **Execution flakiness** (servers, browsers, dbs): per-lane fail-loud; Watcher + `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` per the headless bg-bash lesson; one retry per lane, then unverified.
- **Playwright headless gap on projects without it**: accepted degradation (skip loud); authoring strategy is the long-term fix (Judy leaves a suite behind).
- **Trudy scope creep**: probes stay runtime-observational on own/authorized targets; the profile assertion is the gate.
- **Prompt budget blowout** (playbook inlined per dispatch): playbooks kept lean; 50KB dispatch budget asserted by run-agoge before sending.
