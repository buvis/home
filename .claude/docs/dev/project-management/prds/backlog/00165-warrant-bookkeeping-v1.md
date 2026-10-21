---
default_model: opus
model_tier_rationale: security boundary, protected dependency closure and fail-closed policy contracts
design: run
lane: full
eligibility: /usr/bin/false
---

# Warrant bookkeeping, part 1: protected automatic authority

Source: [Discovery 00161](../../discovery/00161-auto-approve-bounded-warrant-requests.md), current Requirements and final review entry, 2026-10-17. This is part 1 of PRD A; PRD B (the judge) remains unready. Split on 2026-10-19 (backlog review, user decision): part 2 is PRD 00180 (Git seeds and agent identity), part 3 is PRD 00181 (resident service, audit, rate caps and the documented request form).

Traceability: discovery Must-haves 1, 6 and 9, and the envelope and backstop tests of Must-have 10, map here. Must-have 2 and the per-rule tests of 10 map to PRD 00180; 5, 7 and the resident approver of 8 map to PRD 00181. Must-haves 3/4 and judge-specific parts of 5/7/8/10 belong to B. Final review corrections 1–7 are retained; correction 8 is B's prerequisite.

PRD review (2026-10-17, before build) added three requirements the discovery did not carry: the fixed-cwd rule lands here, the agent Git identity in PRD 00180 and the documented request form in PRD 00181. The Git seeds pin cwd to the worktree root, because the per-session `_PROJECT_DIR` makes a general cwd predicate unprovable.

Lane (backlog review 2026-10-19): hand-built in an attended session like PRDs 00163 and 00166. `eligibility: /usr/bin/false` keeps the unattended drain from picking it, because every deploy target sits outside the sandbox write allowlist. Implementation edits staged copies under `docs/dev/tmp/00165-stage/`; every path below is relative to `~/.claude` unless it starts with `~/`. Deploy is a human warrant act (Phase 2).

## Overview

### Problem Statement
Routine dotfiles bookkeeping repeatedly requires a PIN. Automatic host execution is safe only when code bounds the command, selected paths and every executable dependency. The current protected pre-commit hook loads agent-writable glean code and cannot qualify.

### Target Users
The solo developer and sandboxed agents using the existing warrant request/wait interface against the bare buvis repository.

### Success Metrics
- Invalid, unknown or unproven policy, profile and dependency inputs leave every request pending for the PIN, and no existing broker refusal becomes eligible for PIN fallback.
- Named tests selected by `-k auto_policy`, `-k auto_envelope` and `-k auto_dependencies` pass in the staged suite; an always-yes stub cannot bypass bounds.
- The protected glean runtime preserves every required glean exclusion, and the buvis pre-commit hook loads no agent-writable code. No allow rule is active after this PRD, and no judge process or automatic launch runs.

## Functional Decomposition

### Capability: Protected automatic authority
Only protected policy and code can authorize execution; inspected agent material remains data.

#### Feature: Strict policy and small matcher
- **Description**: Load a separate protected rules policy with warden-compatible matching syntax and warrant-specific bounds.
- **Inputs**: Broker configuration, profile, protected rules file, schema-validated request and existing reviewed operation.
- **Outputs**: One allow match or a pending request with an escaped diagnostic; invalid policy authorizes nothing.
- **Behavior**: Require schema version, unique rule IDs, boundedness descriptions, command, argPatterns/match/decision and explicit envelope predicates; reject unknown keys/types, unsupported matcher forms, ambiguous multiple matches and untrusted command resolutions. Support only the warden matcher subset the three Git seeds of PRD 00180 need, with positive and negative compatibility fixtures. No shared warden policy or executable dependency. In A, only allow decisions execute; judge decisions remain pending without a call. Missing/unreadable/invalid policy and engine exceptions preserve human approval. This PRD ships `rules.json` with no active allow rule; PRD 00180 adds the seeds. Policy schema details are design work (guess), constrained by these fields and fail-closed behavior.

#### Feature: Profile envelope and boundary backstop
- **Description**: Bound cwd, actual selected paths and protected execution inputs before every automatic launch.
- **Inputs**: Profile-derived grant candidates, explicit write denies, warrant protected paths, rule grammar, canonical paths, each rule's fixed cwd and the launcher's HOME refusal.
- **Outputs**: Proven permission or pending/PIN; the profile is unchanged.
- **Behavior**: Require trusted resolved executables. `_PROJECT_DIR` and `_TMPDIR` are per-session values the broker cannot see, so a general "cwd outside every agent-writable root" predicate is unprovable and does not ship in A. Each rule instead names its one permitted cwd, compared after resolution; the Git seeds of PRD 00180 name the resolved worktree root, `$HOME`. Proof that `$HOME` is never agent-writable: no static grant covers it, `_TMPDIR` resolves under the static `/private/var/folders` grant, and run-agent refuses to sandbox HOME as the project dir (`~/bin/run-agent` lines 42-45). Pin that refusal the way `test_live_profile_path_matches_run_agent` pins the profile path: the broker rereads the launcher at qualification and deactivates every rule whose fixed cwd is `$HOME` when the refusal text is absent. In the permissive direction (selected paths must lie under an agent-writable root) an unknown runtime root grants nothing. Apply explicit denies before grants, including literal, subtree, regex and project-relative forms. Unknown forms never grant authority; fail the affected evaluation closed. Include warrant code, interpreter, policy, ledger, locks and configuration in the backstop. Check lexical and resolved aliases, deleted paths, symlinks, parent traversal and directory expansion. Do not treat the union of project-root grants as universal permission. Read request files only as untrusted data; never import or execute their contents. Revalidate selection, configuration and dependency identity immediately before launch; changed proof leaves pending without executing.

#### Feature: Protected execution dependency closure
- **Description**: Preserve glean and required Git checks using a protected execution bundle.
- **Inputs**: Current hook, resolved glean source, Python/import paths, Git configuration and helpers, SSH/credential/signing/filter hooks and environment.
- **Outputs**: Protected dependency manifest and qualifying execution profile, or a disabled rule with a diagnostic.
- **Behavior**: Premise: the current hook calls glean through an agent-writable skill link (`~/.config/buvis/hooks/pre-commit` runs `~/.agents/skills/glean/scripts/glean.py`). Recheck before changes; if false, skip the obsolete migration and report, then independently qualify the actual chain. Copy the required glean check into protected warrant storage; never edit the skill link farm or disable checks. Use an absolute protected interpreter in isolated mode and protected helper paths; preserve the check's credential, plaintext, encrypted-blob, local-path and never-ledger exclusions. Treat ledgers/mappings as data; pin authoritative gate configuration and prevent agent edits from weakening mandatory exclusions or redirecting repository/helper execution. Preserve effective-index handling for selected commits. Enumerate and protect all executable/configuration dependencies, including global/system/includes, repository config, hooks, filters, transports, credentials, signing and dynamic interpreter imports. Unknown dependencies, config-discovery paths or writable components disable the affected rule before any helper runs. Protected copies require explicit refresh and renewed qualification after source updates. Do not claim a general-purpose dependency scanner proves arbitrary programs safe.

## Structural Decomposition

### Repository Structure

```text
docs/dev/tmp/00165-stage/
├── bin/
│   ├── warrant                         # staged copy of ~/bin/warrant; loader, matcher, envelope, dependency qualification
│   └── tests/test_warrant.py           # staged copy of ~/bin/tests/test_warrant.py; new auto_* tests
└── .config/
    ├── buvis/hooks/pre-commit          # staged copy of ~/.config/buvis/hooks/pre-commit; calls the protected glean copy
    └── warrant/
        ├── rules.json                  # new protected policy; schema and limits, no active allow rule
        └── runtime/
            ├── glean.py                # protected copy of the glean check
            ├── glean-policy.json       # protected gate configuration/data bounds
            └── dependencies.json       # qualified dependency identities
```

Deploy targets mirror the staged paths under `~/`.

### Module: Authority
- **Maps to capability**: Protected automatic authority (Strict policy and small matcher; Profile envelope and boundary backstop)
- **Location**: `docs/dev/tmp/00165-stage/bin/warrant`, `docs/dev/tmp/00165-stage/.config/warrant/rules.json`
- **Responsibility**: Strict loader, matcher, deny-aware envelope and dependency qualification in the staged broker, plus the protected policy. Reuse `review` (`~/bin/warrant` lines 370-393), `resolve_exe` (lines 325-339) and the existing profile/trust helpers (lines 187-247).
- **Exports**: Internal broker policy evaluation; no new public Python API required.

### Module: Protected runtime
- **Maps to capability**: Protected automatic authority (Protected execution dependency closure)
- **Location**: `docs/dev/tmp/00165-stage/.config/warrant/runtime/glean.py`, `docs/dev/tmp/00165-stage/.config/warrant/runtime/glean-policy.json`, `docs/dev/tmp/00165-stage/.config/warrant/runtime/dependencies.json`, `docs/dev/tmp/00165-stage/.config/buvis/hooks/pre-commit`
- **Responsibility**: The protected glean copy, its gate configuration, the qualified dependency manifest, and the buvis pre-commit hook pointed at the protected copy.
- **Exports**: The protected execution profile the Git seeds of PRD 00180 qualify against.

### Module: Verification
- **Maps to capability**: Protected automatic authority
- **Location**: `docs/dev/tmp/00165-stage/bin/tests/test_warrant.py`
- **Responsibility**: Extend the staged test file and `ProfileCase` with fake protected sites, hostile inputs and planted-dependency markers. Tests do not change live policy, contact the real origin or execute hostile helpers.
- **Exports**: Headless unittest cases selected by the filters below; no separate mirror test file.

## Dependency Graph

### Foundation Layer (Phase 0)
- **Authority**: No new module dependencies; builds on the staged broker and profile parser.
- **Verification**: No new dependencies; extends the existing unittest fake site.

### Core Layer (Phase 1)
- **Protected runtime**: Depends on [Authority, Verification]; the Git seeds of PRD 00180 require its qualification.

### Integration Layer (Phase 2)
- **Host deploy**: Depends on [Authority, Protected runtime, Verification]; a human warrant act after the staged suite passes and the review closes.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Establish automatic authority without enabling unproven execution.

**Tasks**:
- [ ] Copy `~/bin/warrant`, `~/bin/tests/test_warrant.py` and `~/.config/buvis/hooks/pre-commit` into the staged layout above (no deps). Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00165-stage/bin/tests -t docs/dev/tmp/00165-stage/bin/tests -p 'test_warrant.py'` exits 0 before any edit.
- [ ] Implement strict rules loading/matching in `docs/dev/tmp/00165-stage/bin/warrant` and the disabled-by-default policy at `docs/dev/tmp/00165-stage/.config/warrant/rules.json` (depends on: staging task). Acceptance: tests selected by `-k auto_policy` in the staged test file pass for valid rules, unknown keys, unsupported syntax, ambiguous matches and untrusted executable resolution; no model process is launched.
- [ ] Add deny-aware envelope and protected dependency qualification in `docs/dev/tmp/00165-stage/bin/warrant` (depends on: preceding task). Acceptance: tests selected by `-k auto_envelope` in the staged test file cover every supported deny form, the per-rule fixed cwd (the worktree root passes; the agent's project dir and every static root pend), the launcher HOME-refusal pin (present qualifies, absent deactivates every rule whose fixed cwd is `$HOME`), symlink swaps, warrant backstop and exception fallback; an always-yes stub cannot bypass bounds.

**Exit Criteria**: Invalid/unproven policy or dependencies produce pending work, with existing hard refusals preserved.

### Phase 1: Core
**Goal**: Qualify the protected dependency chain while retaining required checks.

**Tasks**:
- [ ] Prepare the protected glean runtime and manifest at `docs/dev/tmp/00165-stage/.config/warrant/runtime/glean.py`, `docs/dev/tmp/00165-stage/.config/warrant/runtime/glean-policy.json` and `docs/dev/tmp/00165-stage/.config/warrant/runtime/dependencies.json`; update `docs/dev/tmp/00165-stage/.config/buvis/hooks/pre-commit` and the staged broker's qualification (depends on: Phase 0). Acceptance: `-k auto_dependencies` rechecks the migration premise, proves required glean exclusions and prospective-index behavior, and leaves planted import/hook/helper markers absent. Unknown or writable dependencies keep rules inactive; no skill source or profile is edited.

**Exit Criteria**: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00165-stage/bin/tests -t docs/dev/tmp/00165-stage/bin/tests -p 'test_warrant*.py'` passes, including existing PIN/refusal tests. No automatic launch or model call occurs. Run the fresh-session review on the staged files before Phase 2; no acceptance criterion requires manual testing or approval as evidence of correctness.

### Phase 2: Integration
**Goal**: Deploy the reviewed staged files (human on the host, or warrant requests the human approves).

**Tasks**:
- [ ] Copy each staged file to its live path with a warrant `cp` request, so the source is hashed (depends on: Phase 1 and its review). Acceptance: `diff` of `~/bin/warrant`, `~/bin/tests/test_warrant.py` and `~/.config/buvis/hooks/pre-commit` against their staged copies is empty; the human confirms the same for the `~/.config/warrant` files, which agents cannot read; `~/bin/warrant list` passes preflight.
- [ ] Run the host suite (depends on: deploy). Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'` is green on the host.
- [ ] One commit, then push (depends on: host suite green). Acceptance: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" show --stat HEAD` lists exactly `bin/warrant`, `bin/tests/test_warrant.py`, `.config/buvis/hooks/pre-commit` and `.config/warrant/rules.json`. PRDs 00180 and 00181 stage the policy from this commit. The runtime copies stay untracked and are regenerated by a deliberate refresh; never stage `passphrase.scrypt` or `ledger.jsonl`.

**Exit Criteria**: Host suite green, live hook loads only protected code, commit pushed.

## Test Strategy

### Critical Scenarios
- **Happy path**: Protected dependencies qualify; a fixture allow rule inside the envelope evaluates to allow; glean checks the exact prospective commit tree through the protected copy.
- **Edge case**: A boundary filename appears only in reason/file contents → deterministic verdict stays governed by actual paths; text does not authorize or veto a rule. Replays touching the Seatbelt profile or warrant config → pending, not allow. A request from the agent's project cwd stays pending.
- **Error case**: Invalid policy, unsupported profile/config dependency or mutated proof → pending with no launch; existing broker hard refusals remain terminal.

## Risks

- **Git indirect execution**: Configuration and helpers create hidden authority. Qualify a narrow protected execution profile and test planted dependencies; leave unsupported live configurations on PIN rather than bypassing glean or required checks.
- **Protected copy drift**: Glean source remains maintained in agent-skills. Pin the copied version and dependency manifest; refresh deliberately through warrant and requalify before activation.
- **Deployment boundary**: Protected destinations and bare-repository writes require human warrant approval. Prepare recoverable artifacts and automated fixture evidence first; never approve requests or work around denials.
- **Deferred prerequisites**: PRD B requires a useful in-envelope judged operation, explicit yes/no rubric and benign/hostile examples (discovery question 8), then backend isolation/model/login and numerical fixture decisions. Mise requires demonstrated installer/reshim dependency and effect bounds (question 7). None is an unresolved implementation decision for A; no hard credit-spend claim is made.
- **Launcher pin**: The fixed-cwd proof rests on text in `~/bin/run-agent`. A refactor that keeps the HOME refusal but rewords it deactivates the `$HOME` rules until the pin is updated; that is the intended failure direction. PRD 00174 keeps the text unchanged for this reason.
