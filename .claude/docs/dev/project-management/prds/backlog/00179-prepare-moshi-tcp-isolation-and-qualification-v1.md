---
design: run
default_model: opus
model_tier_rationale: listener classification, profile generation and non-vacuous safety qualification for a security boundary
eligibility: /usr/bin/false
---
# Prepare Moshi TCP isolation and qualification

Source: [Discovery 00173](../../discovery/00173-check-the-moshi-daemon-for-sandbox-escapes.md). Created 2026-10-19 after the user requested the missing PRDs.

Authoring decisions: Prepare a narrow TCP-isolation candidate and automated qualification tool, preserving the hook socket. Keep live installation and phone interaction outside implementation acceptance. Missing source evidence yields an explicit unverified report, never a claim that the socket is harmless. No gateway action routes, upstream messages or account pairing are authorized.

Lane (backlog review 2026-10-19): hand-built in an attended session like PRDs 00163 and 00166. `eligibility: /usr/bin/false` keeps the unattended drain from picking it, because the deploy targets sit outside the sandbox write allowlist. Implementation writes staged files under `docs/dev/tmp/00179-stage/`; every path below is relative to `~/.claude` unless it starts with `~/`. Tests load the staged tool, never an installed copy. Build acceptance is headless; the Phase 3 deploy tasks are human warrant acts, as in PRD 00166 Phase 1. Profile installation and phone checks stay outside this PRD: they follow the repeatable procedure it writes. Preserve all required review lenses and the fresh-session build-to-review handoff.

## Overview

### Problem Statement
The configured Moshi host daemon exposes a loopback gateway reachable from sandboxed agents. Gateway action authentication and retained Unix-socket authority are unverified, so a TCP deny cannot honestly certify the entire control boundary.

### Target Users
The solo developer and sandboxed agents using the local warrant and Seatbelt workflow.

### Success Metrics
- The three named contract checks below pass using isolated fixtures.
- The final regression command passes against the staged files; no live operation is counted as tested from a fixture result.
- Document host compilation and TCP/Unix fixture checks before any installation. Record the phone transport and end-to-end answer check as separate deployment prerequisites. If those cannot establish preserved behavior, leave the live profile unchanged. The completed PRD supplies the candidate generator, tests and truthful evidence report, not a deployed or fully closed Moshi boundary.

## Functional Decomposition

### Capability: Qualified TCP mitigation candidates
A candidate profile denies the configured Moshi TCP endpoints, and qualification states what remains unverified.

#### Feature: Inventory and candidate generation
- **Description**: Generate a profile candidate for configured gateway and proxy endpoints without installing it.
- **Inputs**: Protected base profile, installed Moshi configuration/plist and read-only listener evidence.
- **Outputs**: A candidate profile plus evidence recording version, endpoints, configuration fingerprint and unverified authority claims.
- **Behavior**: Inspect configuration precedence and enabled address families rather than assuming only default ports 24543 and 24544. Enumerate gateway and proxy listeners, including IPv6 when enabled. Reject ambiguous or unsupported endpoint evidence instead of emitting an apparently complete deny. Preserve existing write grants and herdr denial; preserve the Moshi Unix-socket path. Compare runtime listener evidence with configured endpoints and fail drift checks on added/changed addresses. Obtain hook-transport and socket-authority evidence from installed source or documented read-only material; symbols alone cannot establish authorization. Premise: the base profile has no Moshi TCP denial; recheck and avoid duplicate or obsolete rules.

#### Feature: Non-destructive qualification
- **Description**: Supply headless fixture and host checks with separate statuses.
- **Inputs**: Candidate profile, explicit endpoint evidence and disposable socket fixtures.
- **Outputs**: A check report that distinguishes candidate tests, actual host confinement and unverified phone/socket behavior.
- **Behavior**: Provide `check-moshi-boundary` with explicit --fixture and --host modes (guess): command interface. Fixture mode never calls the live gateway or uses secret paths. Host mode compiles the candidate using sandbox-exec, tests TCP connect refusal against disposable listeners at the declared endpoint shapes, and confirms an allowed disposable Unix socket. Check that `load_profile` from the live `~/bin/warrant` reports identical write roots for base and candidate. Use configured/live endpoint drift evidence read-only; never send action HTTP requests. Unsupported/nested sandbox execution fails host qualification rather than reporting success. Missing source or phone evidence stays unverified in the report. A TCP pass cannot claim phone delivery or complete daemon isolation.

### Capability: Qualification and delivery
Preserve a reviewable implementation and honest operational status.

#### Feature: Reproducible validation and operational procedure
- **Description**: Deliver tests, a repeatable qualification procedure and the deployed tool.
- **Inputs**: Staged code, fixture outcomes and the source discovery's residual risks.
- **Outputs**: Passing contract checks, the procedure named below and the deployed tool.
- **Behavior**: Write the repeatable procedure `docs/dev/procedures/qualify-moshi-boundary.md` from Success Metrics. It covers recurring work only: host compilation and the TCP/Unix checks before any profile installation, the phone transport and end-to-end answer check, and the drift re-check after a Moshi update or configuration change. One-time deploy steps stay in Phase 3 of this PRD. Document what was measured and what remains unverified. Recheck observed-state premises before editing; when obsolete, skip the obsolete mutation and report evidence rather than forcing it. Never weaken existing checks to satisfy new ones.

## Structural Decomposition

### Repository Structure

```text
docs/dev/tmp/00179-stage/
└── bin/
    ├── check-moshi-boundary             # new candidate generator and qualification command
    └── tests/test_moshi_boundary.py     # new contract tests
docs/dev/procedures/qualify-moshi-boundary.md
```

### Module: Implementation
- **Maps to capability**: Qualified TCP mitigation candidates
- **Location**: `docs/dev/tmp/00179-stage/bin/check-moshi-boundary`
- **Responsibility**: Implement the behavior above in the staged tool.
- **Exports**: The candidate-generation and qualification command defined above.

### Module: Contract tests
- **Maps to capability**: Qualified TCP mitigation candidates
- **Location**: `docs/dev/tmp/00179-stage/bin/tests/test_moshi_boundary.py`
- **Responsibility**: Exercise fixture behavior, failure paths and integration with the staged implementation.
- **Exports**: The named unittest methods on `MoshiBoundaryCase`. Direct selection fails if a case is absent.
- New symbols: `MoshiBoundaryCase`, `test_moshi_candidate_endpoint_coverage`, `test_moshi_drift_and_unknowns_fail_qualification`, `test_moshi_report_preserves_unverified_claims`

### Module: Operational procedure
- **Maps to capability**: Qualification and delivery
- **Location**: `docs/dev/procedures/qualify-moshi-boundary.md`
- **Responsibility**: Describe the repeatable qualification workflow, its prerequisites, scope limits and observable outcomes.
- **Exports**: One ordered host procedure with commands, preconditions before dependent steps, and one instruction per sentence.

## Dependency Graph

### Foundation Layer (Phase 0)
No internal dependencies - the premise is checked first.
- **Implementation**: premise check against the live profile; no file is written yet.
- **External prerequisites**: None.

### Core Layer (Phase 1)
- **Contract tests**: Depends on [Implementation]; the named cases load the staged tool, and the implementation lands in the same task. Re-read the actual live profile; do not copy stale tuple shapes or line numbers.

### Integration Layer (Phase 2)
- **Operational procedure**: Depends on [Implementation, Contract tests].
- **Host deploy** (Phase 3): Depends on [Implementation, Contract tests, Operational procedure]; human warrant acts after the review closes.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Confirm the premise before writing anything.

**Tasks**:
- [ ] Recheck that the live profile `~/.config/seatbelt/ai-agents.sb:32-40` holds the herdr deny and no Moshi rule (no deps) - Acceptance: `rg -n -i "moshi|2454[34]" ~/.config/seatbelt/ai-agents.sb` prints nothing. Any hit means a Moshi rule already exists: skip the duplicate rule and report it.

**Exit Criteria**: The premise is recorded with the command output.

### Phase 1: Core
**Goal**: Implement the two functional features with their contract tests.

**Tasks**:
- [ ] Implement the stated behavior in `docs/dev/tmp/00179-stage/bin/check-moshi-boundary` and add `docs/dev/tmp/00179-stage/bin/tests/test_moshi_boundary.py` (depends on: Phase 0) - Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00179-stage/bin/tests -t docs/dev/tmp/00179-stage/bin/tests -p 'test_moshi_boundary.py' -k test_moshi_candidate_endpoint_coverage` and the same command with `-k test_moshi_drift_and_unknowns_fail_qualification` pass. Fixture plists/configurations exercise defaults, overrides, changed ports, proxy endpoints and IPv6; rendered deny coverage is exact and the socket stays allowed. Unexpected listeners, malformed configuration, unsupported address families and unavailable host sandbox produce explicit non-passing qualification.

**Exit Criteria**: Both feature contracts pass their focused checks without modifying live host state.

### Phase 2: Integration
**Goal**: Verify edge cases and write the repeatable procedure.

**Tasks**:
- [ ] Add `test_moshi_report_preserves_unverified_claims` to `docs/dev/tmp/00179-stage/bin/tests/test_moshi_boundary.py` and write `docs/dev/procedures/qualify-moshi-boundary.md` (depends on: Phase 1) - Acceptance: the Phase 1 command with `-k test_moshi_report_preserves_unverified_claims` passes. A fixture TCP pass leaves authentication, socket control and phone workflow unverified without evidence; base/candidate writable roots are identical. The procedure exists, names prerequisites before commands, and distinguishes fixture results from live qualification. Check first that the procedures folder is tracked: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" check-ignore -q "$HOME/.claude/docs/dev/procedures/qualify-moshi-boundary.md"` exits 1; if it exits 0, write the procedure anyway and report that `~/.gitignore` still hides the folder.

**Exit Criteria**: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00179-stage/bin/tests -t docs/dev/tmp/00179-stage/bin/tests -p 'test_*.py'` passes once against the staged files. The fresh-session review closes before Phase 3.

### Phase 3: Deploy
**Goal**: Install the reviewed tool (human on the host, or warrant requests the human approves).

**Tasks**:
- [ ] Copy the staged `bin/check-moshi-boundary` and `bin/tests/test_moshi_boundary.py` to `~/bin/check-moshi-boundary` and `~/bin/tests/test_moshi_boundary.py` with warrant `cp -p` requests, so the source is hashed and the executable bit survives (depends on: Phase 2 and its review). Acceptance: `diff` of each deployed file against its staged copy is empty, and the host suite `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_moshi_boundary.py'` is green.
- [ ] One commit, then push (depends on: deploy) - Acceptance: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" show --stat HEAD` lists exactly `bin/check-moshi-boundary`, `bin/tests/test_moshi_boundary.py` and `.claude/docs/dev/procedures/qualify-moshi-boundary.md`.

**Exit Criteria**: Host suite green, tool deployed, commit pushed. The live profile stays unchanged until the procedure runs.

## Test Strategy

### Critical Scenarios
- **Happy path**: Fixture plists/configurations exercise defaults, overrides, changed ports, proxy endpoints and IPv6; rendered deny coverage is exact and the socket stays allowed.
- **Edge case**: A new proxy port or IPv6 listener fails drift qualification even when the default IPv4 port is blocked.
- **Error case**: Unverified source, unsupported endpoint or unavailable sandbox must not be rendered as a passed boundary check.

## Risks

- **Operational limits**: The retained Unix socket may expose control authority. Preserve explicit uncertainty and keep further protocol changes outside this PRD.
- **Concurrent repository changes**: Re-read the live profile and current configuration before writing; preserve unrelated work.
- **Scope drift**: No profile installation, phone check or additional discovery scope enters this PRD; the procedure owns them.
