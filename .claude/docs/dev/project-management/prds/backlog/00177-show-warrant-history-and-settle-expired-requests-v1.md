---
design: run
default_model: opus
model_tier_rationale: concurrent settlement, replay protection and destructive pruning governed by protected ledger time
eligibility: /usr/bin/false
---
# Show warrant history and settle expired requests

Source: [Discovery 00171](../../discovery/00171-add-warrant-log-and-purge-old-spool-entries.md). Created 2026-10-19 after the user requested the missing PRDs.

Authoring decisions: Keep the proposed configurable result retention of 86400 seconds. Run settlement on host list/approve. Retain the ledger indefinitely. No new daemon, authenticated result transport or agent-side deletion is included. Backlog review 2026-10-19 (user decision): this PRD lands before the resident service of PRD 00181 and uses today's per-request lock; PRD 00181 reuses the same settle pass on its poll and owns the rule that a claimed request is never settled.

Lane (backlog review 2026-10-19): hand-built in an attended session like PRDs 00163 and 00166. `eligibility: /usr/bin/false` keeps the unattended drain from picking it, because the deploy target sits outside the sandbox write allowlist. Implementation edits staged copies under `docs/dev/tmp/00177-stage/`; every path below is relative to `~/.claude` unless it starts with `~/`. Tests load the staged broker, never the installed live copy. Build acceptance is headless; the Phase 3 deploy tasks are human warrant acts, as in PRD 00166 Phase 1. Recovery after lost output follows the repeatable procedure this PRD writes. Preserve all required review lenses and the fresh-session build-to-review handoff.

## Overview

### Problem Statement
History is available only as raw ledger text, expired pending requests are not settled by list, and spool retention is left to the OS. Raw agent text can manipulate terminal output. Cleanup must preserve replay prevention and concurrent approval.

### Target Users
The solo developer and sandboxed agents using the local warrant and Seatbelt workflow.

### Success Metrics
- The three named contract checks below pass using isolated fixtures.
- The final regression command passes against the staged files; no live operation is counted as tested from a fixture result.
- Document host-only maintenance and re-attachment retention. After output loss, inspect authoritative history and actual effects before retrying; never repeat a non-idempotent action solely to recover output. Historical stranded request IDs are examples, never live fixtures. No actual spool entry is settled or pruned by this PRD's build or acceptance.

## Functional Decomposition

### Capability: Safe history and lifecycle maintenance
The human side shows escaped history and settles expired requests before pruning old results.

#### Feature: Escaped ledger history
- **Description**: Add warrant log without a tty or PIN.
- **Inputs**: Protected ledger and --id PREFIX, --since YYYY-MM-DD, repeated --decision NAME, and --last N filters.
- **Outputs**: Oldest-first matching rows, limited to the newest N matches with default 50.
- **Behavior**: Display local timestamp, short ID, decision, exit/reason, shell-quoted argv and cwd, plus escaped unknown fields. Apply guard/visible to every field. A malformed ledger line prints INVALID line N and does not abort listing. Reject malformed filters; the date starts at local midnight. Read only the ledger; optional result-body display and reason/agent ledger enrichment are deferred. Premise: no log subcommand exists (`main`, `~/bin/warrant` lines 623-666); recheck before adding it.

#### Feature: Settle before pruning
- **Description**: Maintain spool delivery without rewriting authoritative history.
- **Inputs**: Current protected TTLs, protected ledger terminal time, direct request/result files and the per-request lock approve takes.
- **Outputs**: Refused expired requests, retained active/fresh/unknown entries and a pruned-count summary.
- **Behavior**: One helper, `settle_expired(site, now)`, runs at the start of list and approve. It takes the same nonblocking per-request `flock` that `approve_one` takes and skips busy requests. Validate canonical lowercase 32-hex filename IDs, reject symlinks and revalidate file identity under lock. Expired requests settle using the existing refusal path; a malformed body or mismatched embedded ID never settles another identity. Invalid filenames are reported without new ledger IDs. Never overwrite an existing terminal record. Prune only direct regular results with a terminal ledger settlement older than result_ttl_sec, using that protected time, never mtime. Unknown or corrupt history retains files with diagnostics. Missing spool directories are tolerated. PRD 00181's service poll will call this same pass; list/approve alone never promise autonomous expiry. Premise: `list_requests` neither settles nor prunes (`~/bin/warrant` lines 587-603); recheck before editing.

### Capability: Qualification and delivery
Preserve a reviewable implementation and honest operational status.

#### Feature: Reproducible validation and operational procedure
- **Description**: Deliver tests, a repeatable recovery procedure and the deployed broker.
- **Inputs**: Staged code, fixture outcomes and the source discovery's residual risks.
- **Outputs**: Passing contract checks, the procedure named below and the deployed broker.
- **Behavior**: Write the repeatable procedure `docs/dev/procedures/recover-lost-warrant-output.md` from Success Metrics. It covers recurring work only: reading `warrant log`, re-attaching within the result retention, and, after output loss, inspecting authoritative history and actual effects before any retry. One-time deploy steps stay in Phase 3 of this PRD. Document what was measured and what remains unverified. Recheck observed-state premises before editing; when obsolete, skip the obsolete mutation and report evidence rather than forcing it. Never weaken existing checks to satisfy new ones.

## Structural Decomposition

### Repository Structure

```text
docs/dev/tmp/00177-stage/
└── bin/
    ├── warrant                         # staged copy of ~/bin/warrant
    └── tests/
        ├── test_warrant.py             # staged copy of ~/bin/tests/test_warrant.py, unchanged regression suite
        └── test_warrant_history.py     # new contract tests
docs/dev/procedures/recover-lost-warrant-output.md
```

### Module: Implementation
- **Maps to capability**: Safe history and lifecycle maintenance
- **Location**: `docs/dev/tmp/00177-stage/bin/warrant`
- **Responsibility**: Implement the behavior above in the staged copy.
- **Exports**: `record`, `refuse`, `list_requests`, `main`, `settle_expired`
- New symbols: `settle_expired`

### Module: Contract tests
- **Maps to capability**: Safe history and lifecycle maintenance
- **Location**: `docs/dev/tmp/00177-stage/bin/tests/test_warrant_history.py`, `docs/dev/tmp/00177-stage/bin/tests/test_warrant.py` (unchanged regression copy)
- **Responsibility**: Exercise fixture behavior, failure paths and integration with the staged implementation.
- **Exports**: The named unittest methods on `WarrantHistoryCase`. Direct selection fails if a case is absent.
- New symbols: `WarrantHistoryCase`, `test_history_filters_and_terminal_escaping`, `test_expiry_respects_locks_and_terminal_history`, `test_prune_uses_ledger_age_and_safe_identity`

### Module: Operational procedure
- **Maps to capability**: Qualification and delivery
- **Location**: `docs/dev/procedures/recover-lost-warrant-output.md`
- **Responsibility**: Describe the repeatable history and recovery workflow, its prerequisites, scope limits and observable outcomes.
- **Exports**: One ordered host procedure with commands, preconditions before dependent steps, and one instruction per sentence.

## Dependency Graph

### Foundation Layer (Phase 0)
No internal dependencies - staged copies of the live files are made first.
- **Implementation**: the staged broker, identical to the live one before any edit.
- **External prerequisites**: None. PRD 00181 builds on this PRD's settle pass.

### Core Layer (Phase 1)
- **Contract tests**: Depends on [Implementation]; the named cases load the staged broker, and the implementation edits land in the same task. Re-read the actual live code; do not copy stale tuple shapes or line numbers.

### Integration Layer (Phase 2)
- **Operational procedure**: Depends on [Implementation, Contract tests].
- **Host deploy** (Phase 3): Depends on [Implementation, Contract tests, Operational procedure]; human warrant acts after the review closes.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Stage the live broker and its suite without changing them.

**Tasks**:
- [ ] Copy `~/bin/warrant` and `~/bin/tests/test_warrant.py` into the staged layout above (no deps) - Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00177-stage/bin/tests -t docs/dev/tmp/00177-stage/bin/tests -p 'test_warrant.py'` exits 0 before any edit.

**Exit Criteria**: The staged regression suite is green before any edit.

### Phase 1: Core
**Goal**: Implement the two functional features with their contract tests.

**Tasks**:
- [ ] Implement the stated behavior in `docs/dev/tmp/00177-stage/bin/warrant` and add `docs/dev/tmp/00177-stage/bin/tests/test_warrant_history.py` (depends on: Phase 0) - Premise: the staged `main` has no `log` subcommand and `list_requests` neither settles nor prunes; a failed premise means skip the obsolete edit and report with evidence. Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00177-stage/bin/tests -t docs/dev/tmp/00177-stage/bin/tests -p 'test_warrant_history.py' -k test_history_filters_and_terminal_escaping` and the same command with `-k test_expiry_respects_locks_and_terminal_history` pass; record the first case's failure against the unedited staged broker as evidence. Exercise filters, default limit, ordering, invalid lines and terminal-control text with fixture ledger records. Expired requests produce refused results and wait exit 126; fresh, locked and already terminal requests survive unchanged.

**Exit Criteria**: Both feature contracts pass their focused checks without modifying live host state.

### Phase 2: Integration
**Goal**: Verify edge cases and write the repeatable procedure.

**Tasks**:
- [ ] Add `test_prune_uses_ledger_age_and_safe_identity` to `docs/dev/tmp/00177-stage/bin/tests/test_warrant_history.py` and write `docs/dev/procedures/recover-lost-warrant-output.md` (depends on: Phase 1) - Acceptance: the Phase 1 command with `-k test_prune_uses_ledger_age_and_safe_identity` passes. Prune only ledger-aged results; mtime forgery, symlink paths, invalid IDs, unknown entries and concurrent replacement never redirect cleanup or erase fresh output. The procedure exists, names prerequisites before commands, and distinguishes fixture results from live qualification. Check first that the procedures folder is tracked: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" check-ignore -q "$HOME/.claude/docs/dev/procedures/recover-lost-warrant-output.md"` exits 1; if it exits 0, write the procedure anyway and report that `~/.gitignore` still hides the folder.

**Exit Criteria**: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00177-stage/bin/tests -t docs/dev/tmp/00177-stage/bin/tests -p 'test_*.py'` passes once against the staged files. The fresh-session review closes before Phase 3.

### Phase 3: Deploy
**Goal**: Install the reviewed broker (human on the host, or warrant requests the human approves).

**Tasks**:
- [ ] Copy the staged `bin/warrant` and `bin/tests/test_warrant_history.py` to `~/bin/warrant` and `~/bin/tests/test_warrant_history.py` with warrant `cp` requests, so the source is hashed (depends on: Phase 2 and its review). Acceptance: `diff` of each deployed file against its staged copy is empty; `~/bin/warrant log --last 1` passes preflight without touching the spool; the host suite `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'` is green.
- [ ] One commit, then push (depends on: deploy) - Acceptance: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" show --stat HEAD` lists exactly `bin/warrant`, `bin/tests/test_warrant_history.py` and `.claude/docs/dev/procedures/recover-lost-warrant-output.md`; never stage `passphrase.scrypt` or `ledger.jsonl`.

**Exit Criteria**: Host suite green, broker deployed, commit pushed. The first host `list` or `approve` after deploy settles expired requests as normal operation, not as PRD acceptance.

## Test Strategy

### Critical Scenarios
- **Happy path**: Exercise filters, default limit, ordering, invalid lines and terminal-control text with fixture ledger records.
- **Edge case**: OS tmp cleanup removes a directory or result during a pass; recreated paths do not gain authority from their filename alone.
- **Error case**: Unreadable or corrupt authoritative history prevents cleanup of affected identities and produces a diagnostic.

## Risks

- **Operational limits**: Ledger membership does not authenticate result bytes. Keep the untrusted spool boundary explicit and preserve unrelated terminal and lockout records.
- **Later automatic claims**: PRD 00181 adds durable automatic-execution claims that outlive the per-request lock. Until it extends this pass to skip claimed requests, no claim exists to protect; after it lands, its tests own that rule.
- **Concurrent repository changes**: Re-read live code and current configuration before staging; preserve unrelated work.
- **Scope drift**: No live spool cleanup or additional discovery scope enters this PRD's acceptance.
