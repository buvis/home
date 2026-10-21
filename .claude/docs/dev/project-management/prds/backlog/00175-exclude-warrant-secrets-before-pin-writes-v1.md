---
design: run
default_model: opus
model_tier_rationale: security-sensitive initialization ordering and preservation of existing secret-write behavior
eligibility: /usr/bin/false
---
# Exclude warrant secrets before PIN writes

Source: [Discovery 00169](../../discovery/00169-keep-warrant-secrets-out-of-backups.md). Created 2026-10-19 after the user requested the missing PRDs.

Authoring decisions: Exclude the whole warrant directory so atomic replacement does not lose protection. Preserve warning-only initialization when exclusion fails, while stating that protection failed. Live Backblaze exclusion and PIN rotation are separate host operations; no secret is read for this implementation.

Lane (backlog review 2026-10-19): hand-built in an attended session like PRDs 00163 and 00166. `eligibility: /usr/bin/false` keeps the unattended drain from picking it, because the deploy target sits outside the sandbox write allowlist. Implementation edits staged copies under `docs/dev/tmp/00175-stage/`; every path below is relative to `~/.claude` unless it starts with `~/`. Tests load the staged broker, never the installed live copy. Build acceptance is headless; the Phase 3 deploy tasks are human warrant acts, as in PRD 00166 Phase 1. Backup settings and PIN rotation stay outside this PRD: they follow the repeatable procedure it writes. Preserve all required review lenses and the fresh-session build-to-review handoff.

## Overview

### Problem Statement
The current initialization writes the PIN hash without first excluding its directory from backups. Discovery evidence shows Backblaze enumerated the files, which establishes possible exposure but does not establish upload or retention.

### Target Users
The solo developer and sandboxed agents using the local warrant and Seatbelt workflow.

### Success Metrics
- The three named contract checks below pass using isolated fixtures.
- The final regression command passes against the staged files; no live operation is counted as tested from a fixture result.
- Provide an ordered host procedure: set the directory exclusions, verify new-scan exclusion without disclosing contents, rotate locally with warrant init, and record historical retention separately. The procedure requires no PIN or secret value to be pasted into an agent conversation. Its preparation is the PRD deliverable; executing account changes and rotation is outside implementation acceptance.

## Functional Decomposition

### Capability: Backup-aware initialization
`warrant init` excludes the warrant directory from backups before any secret write.

#### Feature: Exclusion precedes every secret write
- **Description**: Set and verify the directory exclusion before creating the hash or its temporary file.
- **Inputs**: The existing Site configuration directory and successful PIN confirmation.
- **Outputs**: An excluded directory followed by the normal hash write, or a visible degraded-protection warning followed by that write.
- **Behavior**: In `set_pin`, after creating the directory and before `atomic_write`, run `/usr/bin/tmutil addexclusion DIR` with the directory as one argv element. Read the attribute back with `/usr/bin/xattr -p com.apple.metadata:com_apple_backup_excludeItem DIR`; the host interpreter has no `os.getxattr` on macOS (checked 2026-10-19). Missing command, nonzero exit, missing attribute or read-back failure emits an escaped warning that backup protection is unverified, then retains the existing initialization behavior. Never change PIN length, scrypt settings, current-secret verification or hash serialization. Premise: live `set_pin` has no exclusion call (`~/bin/warrant` lines 298-309); recheck and skip an obsolete duplicate edit if already fixed.

#### Feature: Separate current protection from old copies
- **Description**: Document the host sequence without claiming an exclusion removes historical backups.
- **Inputs**: Exclusion outcome and non-secret backup-setting observations.
- **Outputs**: A repeatable procedure and truthful automated diagnostics.
- **Behavior**: Require directory exclusion in Time Machine and explicit Backblaze folder exclusion before host rotation. Record prior remote presence and retention independently; a retained version is not proof that new exclusion failed. Rotation invalidates the previous warrant PIN; reused secrets require separate rotation. Do not read protected configuration or hash contents, alter backup accounts, delete historical backups or run live init in the implementation. No approve-time drift warning in this slice.

### Capability: Qualification and delivery
Preserve a reviewable implementation and honest operational status.

#### Feature: Reproducible validation and operational procedure
- **Description**: Deliver tests, a repeatable rotation procedure and the deployed broker.
- **Inputs**: Staged code, fixture outcomes and the source discovery's residual risks.
- **Outputs**: Passing contract checks, the procedure named below and the deployed broker.
- **Behavior**: Write the repeatable procedure `docs/dev/procedures/rotate-warrant-pin.md` from Success Metrics. It covers recurring work only: set and verify the backup exclusions, rotate the PIN with `warrant init`, and record historical retention. Re-run it whenever the PIN may have been exposed. One-time deploy steps stay in Phase 3 of this PRD. Document what was measured and what remains unverified. Recheck observed-state premises before editing; when obsolete, skip the obsolete mutation and report evidence rather than forcing it. Never weaken existing checks to satisfy new ones.

## Structural Decomposition

### Repository Structure

```text
docs/dev/tmp/00175-stage/
└── bin/
    ├── warrant                         # staged copy of ~/bin/warrant
    └── tests/
        ├── test_warrant.py             # staged copy of ~/bin/tests/test_warrant.py, unchanged regression suite
        └── test_warrant_backup.py      # new contract tests
docs/dev/procedures/rotate-warrant-pin.md
```

### Module: Implementation
- **Maps to capability**: Backup-aware initialization
- **Location**: `docs/dev/tmp/00175-stage/bin/warrant`
- **Responsibility**: Implement the behavior above in the staged copy.
- **Exports**: `set_pin`

### Module: Contract tests
- **Maps to capability**: Backup-aware initialization
- **Location**: `docs/dev/tmp/00175-stage/bin/tests/test_warrant_backup.py`, `docs/dev/tmp/00175-stage/bin/tests/test_warrant.py` (unchanged regression copy)
- **Responsibility**: Exercise fixture behavior, failure paths and integration with the staged implementation.
- **Exports**: The named unittest methods on `WarrantBackupCase`. Direct selection fails if a case is absent.
- New symbols: `WarrantBackupCase`, `test_exclusion_precedes_hash_and_temp_write`, `test_exclusion_failure_warns_and_initializes`, `test_pin_validation_and_hash_format_preserved`

### Module: Operational procedure
- **Maps to capability**: Qualification and delivery
- **Location**: `docs/dev/procedures/rotate-warrant-pin.md`
- **Responsibility**: Describe the repeatable exclusion and rotation workflow, its prerequisites, scope limits and observable outcomes.
- **Exports**: One ordered host procedure with commands, preconditions before dependent steps, and one instruction per sentence.

## Dependency Graph

### Foundation Layer (Phase 0)
No internal dependencies - staged copies of the live files are made first.
- **Implementation**: the staged broker, identical to the live one before any edit.
- **External prerequisites**: None.

### Core Layer (Phase 1)
- **Contract tests**: Depends on [Implementation]; the named cases load the staged broker, and the implementation edit lands in the same task. Re-read the actual live code; do not copy stale tuple shapes or line numbers.

### Integration Layer (Phase 2)
- **Operational procedure**: Depends on [Implementation, Contract tests].
- **Host deploy** (Phase 3): Depends on [Implementation, Contract tests, Operational procedure]; human warrant acts after the review closes.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Stage the live broker and its suite without changing them.

**Tasks**:
- [ ] Copy `~/bin/warrant` and `~/bin/tests/test_warrant.py` into the staged layout above (no deps) - Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00175-stage/bin/tests -t docs/dev/tmp/00175-stage/bin/tests -p 'test_warrant.py'` exits 0 before any edit.

**Exit Criteria**: The staged regression suite is green before any edit.

### Phase 1: Core
**Goal**: Implement the two functional features with their contract tests.

**Tasks**:
- [ ] Implement the stated behavior in `docs/dev/tmp/00175-stage/bin/warrant` and add `docs/dev/tmp/00175-stage/bin/tests/test_warrant_backup.py` (depends on: Phase 0) - Premise: live `set_pin` has no exclusion call; a failed premise means skip the obsolete edit and report with evidence. Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00175-stage/bin/tests -t docs/dev/tmp/00175-stage/bin/tests -p 'test_warrant_backup.py' -k test_exclusion_precedes_hash_and_temp_write` and the same command with `-k test_exclusion_failure_warns_and_initializes` pass; record the first case's failure against the unedited staged broker as evidence. Injected exclusion and write spies prove the ordering; use fixture PINs and directories only. Missing tmutil, refusal and absent/read-failed xattrs all warn and retain initialization; the diagnostic never claims Backblaze protection.

**Exit Criteria**: Both feature contracts pass their focused checks without modifying live host state.

### Phase 2: Integration
**Goal**: Verify edge cases and write the repeatable procedure.

**Tasks**:
- [ ] Add `test_pin_validation_and_hash_format_preserved` to `docs/dev/tmp/00175-stage/bin/tests/test_warrant_backup.py` and write `docs/dev/procedures/rotate-warrant-pin.md` (depends on: Phase 1) - Acceptance: the Phase 1 command with `-k test_pin_validation_and_hash_format_preserved` passes. Wrong current PIN and mismatched confirmation never replace the hash; an existing valid PIN still verifies after successful fixture rotation. The procedure exists, names prerequisites before commands, and distinguishes fixture results from live qualification. Check first that the procedures folder is tracked: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" check-ignore -q "$HOME/.claude/docs/dev/procedures/rotate-warrant-pin.md"` exits 1; if it exits 0, write the procedure anyway and report that `~/.gitignore` still hides the folder.

**Exit Criteria**: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00175-stage/bin/tests -t docs/dev/tmp/00175-stage/bin/tests -p 'test_*.py'` passes once against the staged files. The fresh-session review closes before Phase 3.

### Phase 3: Deploy
**Goal**: Install the reviewed broker (human on the host, or warrant requests the human approves).

**Tasks**:
- [ ] Copy the staged `bin/warrant` and `bin/tests/test_warrant_backup.py` to `~/bin/warrant` and `~/bin/tests/test_warrant_backup.py` with warrant `cp` requests, so the source is hashed (depends on: Phase 2 and its review). Acceptance: `diff` of each deployed file against its staged copy is empty; `~/bin/warrant list` passes preflight; the host suite `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'` is green.
- [ ] One commit, then push (depends on: deploy) - Acceptance: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" show --stat HEAD` lists exactly `bin/warrant`, `bin/tests/test_warrant_backup.py` and `.claude/docs/dev/procedures/rotate-warrant-pin.md`; never stage `passphrase.scrypt` or `ledger.jsonl`.

**Exit Criteria**: Host suite green, broker deployed, commit pushed. No backup setting or PIN changes until the procedure runs.

## Test Strategy

### Critical Scenarios
- **Happy path**: Injected exclusion and write spies prove the ordering; use fixture PINs and directories only.
- **Edge case**: Atomic replacement after a second fixture rotation retains the directory exclusion; account retention remains unknown unless independently observed.
- **Error case**: An exclusion failure produces a prominent warning and the documented degraded initialization behavior.

## Risks

- **Operational limits**: Warning-only behavior can still expose a new hash. Preserve that explicit design tradeoff, and never mark operational exposure closed from unit tests.
- **Concurrent repository changes**: Re-read live code and current configuration before staging; preserve unrelated work.
- **Scope drift**: No backup-account change, PIN rotation or additional discovery scope enters this PRD; the procedure owns them.
