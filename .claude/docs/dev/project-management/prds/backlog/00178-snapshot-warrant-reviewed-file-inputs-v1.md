---
design: run
default_model: opus
model_tier_rationale: immutable input capture, timeout and descendant lifetime, protected storage and concurrent recovery
eligibility: /usr/bin/false
---
# Snapshot warrant reviewed file inputs

Source: [Discovery 00172](../../discovery/00172-snapshot-agent-writable-file-arguments.md). Created 2026-10-19 after the user requested the missing PRDs.

Authoring decisions: Adopt the discovery recommendation: automatic snapshots for direct interpreter script operands and explicit repeated --snapshot N for other whole file operands. Use protected warrant storage, a 16 MiB cap on total captured bytes per request (guess): initial cap, and no directory snapshots. Path-based commands remain unchanged unless explicitly opted in.

Lane (backlog review 2026-10-19): hand-built in an attended session like PRDs 00163 and 00166. `eligibility: /usr/bin/false` keeps the unattended drain from picking it, because the deploy target sits outside the sandbox write allowlist. Lands after: PRDs 00175, 00176 and 00177, deployed. Implementation edits staged copies under `docs/dev/tmp/00178-stage/`; every path below is relative to `~/.claude` unless it starts with `~/`. Tests load the staged broker, never the installed live copy. Build acceptance is headless; the Phase 3 deploy tasks are human warrant acts, as in PRD 00166 Phase 1. Recovery of retained copies follows the repeatable procedure this PRD writes. Preserve all required review lenses and the fresh-session build-to-review handoff.

## Overview

### Problem Statement
Rehashing immediately before spawn cannot stop later changes before a child reads a script, including lazy shell reads. Request-time copies in the writable spool do not establish integrity.

### Target Users
The solo developer and sandboxed agents using the local warrant and Seatbelt workflow.

### Success Metrics
- The three named contract checks below pass using isolated fixtures.
- The final regression command passes against the staged files; no live operation is counted as tested from a fixture result.
- Document the direct-script grammar, changed script location and sibling-import implications, explicit data indices and indirect-input boundary in the warrant module docstring, and retained-copy recovery as a repeatable procedure. Use fixture scripts only; no live approval or protected snapshot storage is created by implementation tests.

## Functional Decomposition

### Capability: Execution of reviewed bytes
The child runs the exact bytes the human reviewed, held by the host side in protected storage.

#### Feature: Capture and bind snapshots
- **Description**: Hold exactly the bytes reviewed and use protected copies for execution.
- **Inputs**: Normalized argv, eligible agent-writable regular files and optional snapshot indices.
- **Outputs**: Immutable captured bytes with hash/head, effective argv mapping and protected copy metadata.
- **Behavior**: Automatically select argv[1] only when the resolved executable is bash, sh, zsh, dash or python3 with an optional numeric version suffix, and that operand is a writable regular file. Interpreter options, -c and -m do not gain automatic coverage. Explicit indices select eligible whole-file content operands only; glued forms from 00176 remain inspected but are not copied. Reject duplicate or out-of-range indices and inputs exceeding the aggregate cap; never silently fall back. Read bounded bytes once in review, derive the hash and displayed head from them, and never reopen snapshot originals. After approval write exclusive 0600 copies in protected 0700 request directories under ~/.config/warrant; reject writable or symlinked storage. Recheck held bytes/copy integrity, rewrite argv and preserve non-copied candidate rechecks. Preserve input ordering and stdin behavior.

#### Feature: Report scope and preserve live consumers
- **Description**: Expose the actual copied paths and clean only proven unused snapshots.
- **Inputs**: Captured mapping, process ownership, request locks and execution outcome.
- **Outputs**: Escaped snapshot rows, ledger mapping and safely removed or explicitly retained copies.
- **Behavior**: Show original index/path, hash and copy destination; record the same metadata without content in terminal history. Mark unpinned writable arguments and indirect absolute-path hints as incomplete coverage. Never copy cp destinations or git add operands automatically. Run snapshot consumers under an owned process group; terminate and reap that group on timeout before routine cleanup. Detached or unprovable survivors do not justify deletion. On broker crash or uncertain ownership retain protected copies and report them for later qualification; a free lock or absent parent PID alone is insufficient proof. Recovery removes only copies whose consumer termination and ownership are established, without touching live approvals. Conservative retention when proof is unavailable is a deliberate refinement of the discovery cleanup claim. Premise: `execute` uses `subprocess.run` without descendant ownership (`~/bin/warrant` lines 425-437 before PRD 00166); recheck after prerequisites.

### Capability: Qualification and delivery
Preserve a reviewable implementation and honest operational status.

#### Feature: Reproducible validation and operational procedure
- **Description**: Deliver tests, the documented snapshot grammar, a repeatable recovery procedure and the deployed broker.
- **Inputs**: Staged code, fixture outcomes and the source discovery's residual risks.
- **Outputs**: Passing contract checks, the updated module docstring, the procedure named below and the deployed broker.
- **Behavior**: Document the direct-script grammar, changed script location and sibling-import implications, explicit `--snapshot N` indices and the indirect-input boundary in the staged broker's module docstring; this is reference material. Write the repeatable procedure `docs/dev/procedures/recover-warrant-snapshots.md`; it covers recurring work only: finding protected copies a crash or uncertain consumer left behind, establishing consumer termination and ownership, and removing only those copies. One-time deploy steps stay in Phase 3 of this PRD. Document what was measured and what remains unverified. Recheck observed-state premises before editing; when obsolete, skip the obsolete mutation and report evidence rather than forcing it. Never weaken existing checks to satisfy new ones.

## Structural Decomposition

### Repository Structure

```text
docs/dev/tmp/00178-stage/
└── bin/
    ├── warrant                          # staged copy of ~/bin/warrant after PRDs 00175-00177; snapshots and module docstring
    └── tests/
        ├── test_warrant.py              # staged copy of ~/bin/tests/test_warrant.py, unchanged regression suite
        └── test_warrant_snapshots.py    # new contract tests
docs/dev/procedures/recover-warrant-snapshots.md
```

### Module: Implementation
- **Maps to capability**: Execution of reviewed bytes; Qualification and delivery (module docstring)
- **Location**: `docs/dev/tmp/00178-stage/bin/warrant`
- **Responsibility**: Implement the behavior above in the staged copy, including the module docstring.
- **Exports**: `Op`, `inspect_file`, `review`, `show`, `execute`, `launch`, `preflight`

### Module: Contract tests
- **Maps to capability**: Execution of reviewed bytes
- **Location**: `docs/dev/tmp/00178-stage/bin/tests/test_warrant_snapshots.py`, `docs/dev/tmp/00178-stage/bin/tests/test_warrant.py` (unchanged regression copy)
- **Responsibility**: Exercise fixture behavior, failure paths and integration with the staged implementation.
- **Exports**: The named unittest methods on `WarrantSnapshotsCase`. Direct selection fails if a case is absent.
- New symbols: `WarrantSnapshotsCase`, `test_snapshot_executes_captured_script_bytes`, `test_snapshot_selection_and_path_semantics`, `test_snapshot_timeout_and_recovery_ownership`

### Module: Operational procedure
- **Maps to capability**: Qualification and delivery
- **Location**: `docs/dev/procedures/recover-warrant-snapshots.md`
- **Responsibility**: Describe the repeatable retained-copy recovery workflow, its prerequisites, scope limits and observable outcomes.
- **Exports**: One ordered host procedure with commands, preconditions before dependent steps, and one instruction per sentence.

## Dependency Graph

### Foundation Layer (Phase 0)
No internal dependencies - staged copies of the live files are made first.
- **Implementation**: the staged broker, identical to the live one before any edit.
- **External prerequisites**: 00175-exclude-warrant-secrets-before-pin-writes-v1.md; 00176-inspect-warrant-glued-file-arguments-v1.md; 00177-show-warrant-history-and-settle-expired-requests-v1.md; all deployed.

### Core Layer (Phase 1)
- **Contract tests**: Depends on [Implementation]; the named cases load the staged broker, and the implementation edits land in the same task. Re-read the actual prerequisite code; do not copy stale tuple shapes or line numbers.

### Integration Layer (Phase 2)
- **Operational procedure**: Depends on [Implementation, Contract tests].
- **Host deploy** (Phase 3): Depends on [Implementation, Contract tests, Operational procedure]; human warrant acts after the review closes.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Stage the live broker after its prerequisites.

**Tasks**:
- [ ] Copy `~/bin/warrant` and `~/bin/tests/test_warrant.py` into the staged layout above (no deps) - Acceptance: `test -f docs/dev/project-management/prds/done/00175-exclude-warrant-secrets-before-pin-writes-v1.md`, `test -f docs/dev/project-management/prds/done/00176-inspect-warrant-glued-file-arguments-v1.md` and `test -f docs/dev/project-management/prds/done/00177-show-warrant-history-and-settle-expired-requests-v1.md` each exit 0 (link-ok: future done paths); `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00178-stage/bin/tests -t docs/dev/tmp/00178-stage/bin/tests -p 'test_warrant.py'` exits 0 before any edit.

**Exit Criteria**: The prerequisites are confirmed and the staged regression suite is green before any edit.

### Phase 1: Core
**Goal**: Implement the two functional features with their contract tests.

**Tasks**:
- [ ] Implement the stated behavior in `docs/dev/tmp/00178-stage/bin/warrant` and add `docs/dev/tmp/00178-stage/bin/tests/test_warrant_snapshots.py` (depends on: Phase 0) - Premise: the staged `execute` runs consumers without descendant ownership; a failed premise means skip the obsolete edit and report with evidence. Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00178-stage/bin/tests -t docs/dev/tmp/00178-stage/bin/tests -p 'test_warrant_snapshots.py' -k test_snapshot_executes_captured_script_bytes` and the same command with `-k test_snapshot_selection_and_path_semantics` pass; record the first case's failure against the unedited staged broker as evidence. Rewrite/delete the original after capture and append during a bash run; only reviewed bytes execute, while unsnapshotted input changes still refuse. Exercise explicit patch data, plain cp/git paths, option-bearing interpreters, invalid indices, cap refusal, symlinked storage and protected mapping output.

**Exit Criteria**: Both feature contracts pass their focused checks without modifying live host state.

### Phase 2: Integration
**Goal**: Verify edge cases, document the grammar and write the repeatable procedure.

**Tasks**:
- [ ] Add `test_snapshot_timeout_and_recovery_ownership` to `docs/dev/tmp/00178-stage/bin/tests/test_warrant_snapshots.py`, update the module docstring of `docs/dev/tmp/00178-stage/bin/warrant`, and write `docs/dev/procedures/recover-warrant-snapshots.md` (depends on: Phase 1) - Acceptance: the Phase 1 command with `-k test_snapshot_timeout_and_recovery_ownership` passes. Concurrent approvals, group timeout, broker-crash fixtures and detached-consumer uncertainty never delete another live consumer input; known terminated groups clean up and uncertain copies remain reported. `/opt/homebrew/bin/python3 docs/dev/tmp/00178-stage/bin/warrant --help` prints the `--snapshot N` option and the direct-script rule. The procedure exists, names prerequisites before commands, and distinguishes fixture results from live qualification. Check first that the procedures folder is tracked: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" check-ignore -q "$HOME/.claude/docs/dev/procedures/recover-warrant-snapshots.md"` exits 1; if it exits 0, write the procedure anyway and report that `~/.gitignore` still hides the folder.

**Exit Criteria**: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00178-stage/bin/tests -t docs/dev/tmp/00178-stage/bin/tests -p 'test_*.py'` passes once against the staged files. The fresh-session review closes before Phase 3.

### Phase 3: Deploy
**Goal**: Install the reviewed broker (human on the host, or warrant requests the human approves).

**Tasks**:
- [ ] Copy the staged `bin/warrant` and `bin/tests/test_warrant_snapshots.py` to `~/bin/warrant` and `~/bin/tests/test_warrant_snapshots.py` with warrant `cp` requests, so the source is hashed (depends on: Phase 2 and its review). Acceptance: `diff` of each deployed file against its staged copy is empty; `~/bin/warrant log --last 1` passes preflight without touching the spool; the host suite `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'` is green.
- [ ] One commit, then push (depends on: deploy) - Acceptance: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" show --stat HEAD` lists exactly `bin/warrant`, `bin/tests/test_warrant_snapshots.py` and `.claude/docs/dev/procedures/recover-warrant-snapshots.md`; never stage `passphrase.scrypt` or `ledger.jsonl`.

**Exit Criteria**: Host suite green, broker deployed, commit pushed.

## Test Strategy

### Critical Scenarios
- **Happy path**: Rewrite/delete the original after capture and append during a bash run; only reviewed bytes execute, while unsnapshotted input changes still refuse.
- **Edge case**: A copied script locating siblings through its own path may fail; the changed path is displayed and directory snapshots remain deferred.
- **Error case**: Oversize input or unsafe storage refuses before execution; timeout never deletes data still potentially in use.

## Risks

- **Operational limits**: General descendants can detach and outlive a broker. Prefer protected retained bytes over an unsupported cleanup guarantee; no general claim closes indirect reads.
- **Concurrent repository changes**: Re-read prerequisite code and current configuration before staging; preserve unrelated work.
- **Scope drift**: No live snapshot recovery or additional discovery scope enters this PRD's acceptance.
