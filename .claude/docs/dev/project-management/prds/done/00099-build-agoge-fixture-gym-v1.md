# Agoge Fixture Gym: Seeded-Defect Eval

Source: `dev/local/discovery/00091-product-qa-agent-pack.md` (PRD 1 of 5 in the agoge sequence: gym, core pack 00100, harnesses 00101, autopilot hook 00102, extraction 00103).

## Overview

### Problem Statement

The agoge product-QA pack (discovery 00091) needs ground truth before it exists: without repos containing known product-behavior defects, its catch rate is unmeasurable and "the pack works" is a feeling, not a number. This is fail-first at product level: plant defects, prove each is observable, then build the pack against them.

### Target Users

The agoge pack itself (PRDs 00100-00101 score against this gym) and its author, who reads catch-rate numbers to decide whether the pack is trustworthy.

### Success Metrics

- Both fixtures arm deterministically and every planted seed is observable (verify-seeds exits 0).
- Scorer exists and enforces the fixed bar: >=70% of all seeds caught aggregated across both fixtures AND 100% of CRITICAL seeds caught. The bar gates PRD 00101, not this PRD.
- No manifest content leaks into an armed fixture (armed repos are clean of eval metadata).

## Functional Decomposition

### Capability: Fixture Definition

Two working apps with planted product-behavior defects, defined as source trees plus scripted git history.

#### Feature: CLI Python Fixture
- **Description**: A small working Python CLI app with >=6 planted seeds.
- **Inputs**: None (static source tree in the gym repo).
- **Outputs**: Source tree plus a history script the arm step replays.
- **Behavior**: Seeds span >=5 of the domains {journey, integration, release, performance, security} (no browser surface by design, so the UX lane must loud-skip here); >=2 seeds are CRITICAL. Seed classes per discovery: broken journey, lying changelog, dead integration, runtime perf seed, security seed. Exact seed implementations are design-phase work.

#### Feature: Web SvelteKit Fixture
- **Description**: A small working SvelteKit app with >=6 planted seeds, including browser-observable ones.
- **Inputs**: None (static source tree in the gym repo).
- **Outputs**: Source tree plus history script; includes a Playwright setup so browser seeds are observable headlessly.
- **Behavior**: Seeds span >=5 of {journey, integration, ux, release, performance, security}; >=2 CRITICAL; at least one seed observable only through the browser (exercises the UX lane for real).

#### Feature: Seed Manifests
- **Description**: Machine-readable ground truth per fixture, stored outside the armed fixture so the pack cannot read it.
- **Inputs**: Seed definitions authored with the fixtures.
- **Outputs**: `manifests/cli.json`, `manifests/web.json`.
- **Behavior**: One entry per seed: `{id, domain, severity (CRITICAL|HIGH|MEDIUM|LOW), summary, evidence: {paths, symptom}, repro}`. `repro` is a headlessly runnable command (or Playwright spec for browser seeds). `evidence.paths` are repo-relative; the scorer matches findings on them.

### Capability: Arming

#### Feature: Arm Script
- **Description**: Materialize a fixture into a throwaway git repo the pack can be pointed at.
- **Inputs**: Fixture name (`cli` | `web`), target directory (default under the gym's gitignored `armed/`).
- **Outputs**: A standalone git repo with working tree, scripted commit history, tags, and a changelog (the lying-changelog seed needs real history to lie about).
- **Behavior**: Copy source tree, `git init`, replay the history script with fixed `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` values so arming is deterministic. Never copies `manifests/` or any eval metadata. Re-arming deletes and rebuilds; armed repos are disposable.

### Capability: Scoring

#### Feature: Seed Verifier
- **Description**: Prove every planted defect is observable (product-level fail-first).
- **Inputs**: Armed fixture path plus its manifest.
- **Outputs**: Per-seed observable/not-observable table; exit 0 only if all observable.
- **Behavior**: Runs each seed's `repro`; a seed passes verification when its symptom reproduces. Also asserts the armed repo contains no manifest or eval-metadata files.

#### Feature: Catch-Rate Scorer
- **Description**: Score an agoge findings report against the manifests and enforce the bar.
- **Inputs**: One or more agoge report files (the `dev/local/audit-results/` report contract from PRD 00100: findings carry repo-relative paths, domain, severity), manifest(s).
- **Outputs**: JSON breakdown (per-seed caught/missed, per-fixture and aggregate rates, CRITICAL coverage) plus exit 0/1 against the bar (>=70% aggregate AND 100% CRITICAL).
- **Behavior**: A seed counts as caught when a finding matches on any `evidence.paths` entry and the seed's domain. Malformed or path-less reports fail loud, never score as zero silently.

## Structural Decomposition

### Repository Structure

```
~/git/src/github.com/buvis/agoge-gym/
├── fixtures/
│   ├── cli/            # Maps to: Fixture Definition (CLI Python Fixture)
│   │   ├── src/        # app source tree
│   │   └── history.py  # scripted commits + tags for arming
│   └── web/            # Maps to: Fixture Definition (Web SvelteKit Fixture)
│       ├── src/
│       └── history.py
├── manifests/          # Maps to: Fixture Definition (Seed Manifests)
│   ├── cli.json
│   └── web.json
├── bin/
│   ├── arm             # Maps to: Arming
│   ├── verify-seeds    # Maps to: Scoring (Seed Verifier)
│   └── score           # Maps to: Scoring (Catch-Rate Scorer)
├── armed/              # gitignored; throwaway armed repos
└── README.md           # what the gym is, how to arm/verify/score
```

### Module: fixtures
- **Maps to capability**: Fixture Definition
- **Responsibility**: Working app sources with planted, documented defects and scripted history.
- **Exports**: `fixtures/cli/`, `fixtures/web/` trees consumed by `bin/arm`.

### Module: manifests
- **Maps to capability**: Fixture Definition (Seed Manifests)
- **Responsibility**: Ground truth, kept out of armed repos.
- **Exports**: `manifests/cli.json`, `manifests/web.json` schema above.

### Module: bin
- **Maps to capability**: Arming, Scoring
- **Responsibility**: Deterministic arming, seed verification, catch-rate scoring. Python scripts (house rule: no bash logic beyond trivial wrappers).
- **Exports**: `bin/arm <fixture>`, `bin/verify-seeds <fixture>`, `bin/score <report>... --manifest <m>...`.

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **fixtures**: App sources plus seed definitions.
- **manifests**: Written together with the seeds they describe.

### Core Layer (Phase 1)
- **bin/arm**: Depends on [fixtures].

### Integration Layer (Phase 2)
- **bin/verify-seeds**, **bin/score**: Depend on [bin/arm, manifests].

## Implementation Phases

### Phase 0: Foundation
**Goal**: Both fixture apps exist, work, and carry documented seeds.

**Tasks**:
- [ ] Create `buvis/agoge-gym` repo skeleton (no deps) - Acceptance: repo exists at the path above with README and layout.
- [ ] Build CLI Python fixture app + seeds + `manifests/cli.json` (no deps) - Acceptance: app's happy path runs; manifest validates against the schema; >=6 seeds, >=2 CRITICAL, >=5 domains.
- [ ] Build web SvelteKit fixture app + Playwright setup + seeds + `manifests/web.json` (no deps) - Acceptance: app builds and serves; Playwright smoke spec runs headlessly; manifest constraints as above plus >=1 browser-only seed.

**Exit Criteria**: Both fixtures runnable from their source trees; manifests complete.

### Phase 1: Core
**Goal**: Deterministic arming.

**Tasks**:
- [ ] Implement `bin/arm` with scripted history replay (depends on: Phase 0) - Acceptance: arming `cli` twice produces identical `git log --format=%H` output; armed repo contains no `manifests/` content; changelog and tags present.

**Exit Criteria**: Both fixtures arm into standalone throwaway repos.

### Phase 2: Integration
**Goal**: Fail-first proof and the scoring gate.

**Tasks**:
- [ ] Implement `bin/verify-seeds` (depends on: Phase 1) - Acceptance: exits 0 on both armed fixtures with every seed observable; flipping any seed's fix back makes it exit 1.
- [ ] Implement `bin/score` with the fixed bar (depends on: Phase 1) - Acceptance: a synthetic report covering 70%+all-CRITICAL exits 0; dropping one CRITICAL exits 1; dropping to 60% overall exits 1; malformed report exits with a distinct loud error.

**Exit Criteria**: `verify-seeds` green on both fixtures; `score` enforces >=70% aggregate + 100% CRITICAL.

## Test Strategy

### Critical Scenarios
- **Happy path**: `bin/arm cli && bin/verify-seeds cli` → Expected: exit 0, all seeds observable, no manifest leakage.
- **Edge case**: re-arm over an existing `armed/cli` → Expected: clean rebuild, identical history hashes.
- **Error case**: `bin/score` on a report without file paths → Expected: loud failure naming the report defect, not a 0% score.

## Risks

- **Seeds easier than wild defects**: Accepted in discovery Q8; the gym is a floor, not proof. Mitigation: seed classes mirror the defect classes autopilot actually shipped past review.
- **Scorer matching too fuzzy or too strict**: Mitigation: match on evidence paths + domain only; scorer emits per-seed rationale so misscores are auditable; report shape may force a scorer adjustment once PRD 00100's report contract settles (rework accepted in discovery Q11).
- **Manifest leakage poisons the eval**: Mitigation: verify-seeds asserts armed repos are metadata-clean; failure is a hard stop.
