---
design: run
default_model: opus
model_tier_rationale: candidate identity, fingerprint representation and review-to-launch equivalence across concurrent file mutation
eligibility: /usr/bin/false
---
# Inspect warrant glued file arguments

Source: [Discovery 00170](../../discovery/00170-hash-file-paths-inside-flag-arguments.md). Created 2026-10-19 after the user requested the missing PRDs.

Authoring decisions: Include dashless KEY=value and agent-writable directory warnings. Land after root-command PRD 00166 so one representation retains its fingerprint and sudo normalization semantics. Pin direct argv candidates only; shell programs, Git pathspec magic and indirect reads remain outside scope.

Lane (backlog review 2026-10-19): hand-built in an attended session like PRDs 00163 and 00166. `eligibility: /usr/bin/false` keeps the unattended drain from picking it, because the deploy target sits outside the sandbox write allowlist. Lands after: PRD 00166, deployed. Implementation edits staged copies under `docs/dev/tmp/00176-stage/`; every path below is relative to `~/.claude` unless it starts with `~/`. Tests load the staged broker, never the installed live copy. Build acceptance is headless; the Phase 3 deploy tasks are human warrant acts, as in PRD 00166 Phase 1. Preserve all required review lenses and the fresh-session build-to-review handoff.

## Overview

### Problem Statement
The broker inspects only whole argv entries that name files. Files supplied through --name=value, -fPATH or KEY=value receive no content display or launch-time recheck.

### Target Users
The solo developer and sandboxed agents using the local warrant and Seatbelt workflow.

### Success Metrics
- The three named contract checks below pass using isolated fixtures.
- The final regression command passes against the staged files; no live operation is counted as tested from a fixture result.
- Document examples of covered argv forms and the remaining shell, pathspec and indirect-input boundary in the warrant module docstring, which `warrant --help` prints. Run consumers only on temporary data; no real root operation is part of acceptance.

## Functional Decomposition

### Capability: Consistent argv inspection
Review and launch inspect the same file candidates, including values glued to flags.

#### Feature: One candidate grammar
- **Description**: Extract the same candidate identities during review and launch.
- **Inputs**: The normalized command argv and fixed resolved cwd.
- **Outputs**: Candidate identities containing argv index, form and original substring, with resolved file or directory evidence.
- **Behavior**: For each eligible argv entry consider the whole token; for --name=value consider text after the first equals; for single-dash tokens longer than two characters consider text after the first two characters; for dashless KEY=value consider text after the first equals. Do not interpret double-dash tokens as short flags. Apply the existing regular-file predicate and filesystem resolution. Preserve all distinct matched forms when one token has multiple matches. Keep the immutable reviewed argv, and reuse the same extractor for launch checks. Honor PRD 00166 command normalization and stat-only fingerprints for unreadable trusted inputs. Premise: whole-token-only `file_args` exists today (`~/bin/warrant` lines 357-367); recheck after the prerequisite and adapt its actual representation.

#### Feature: Display and enforce reviewed candidates
- **Description**: Extend existing file review and mutation refusal to every candidate.
- **Inputs**: Candidate identities, original fingerprints, heads and current filesystem state.
- **Outputs**: Escaped form-labelled file rows, directory warnings, or existing refusal results.
- **Behavior**: Show argv index and matched form beside the resolved path and fingerprint; apply the existing UTF-8 and head-size limits. Refuse a changed path, retargeted symlink, changed fingerprint, disappeared reviewed file or previously absent candidate that becomes a regular file. Track appeared checks by candidate identity, not just argv index. Warn on agent-writable directory candidates without claiming to hash a tree. Ordinary strings only match when an actual fixture file exists; accepted false positives fail toward additional review.

### Capability: Qualification and delivery
Preserve a reviewable implementation and honest operational status.

#### Feature: Reproducible validation and boundary documentation
- **Description**: Deliver tests, the documented argv boundary and the deployed broker.
- **Inputs**: Staged code, fixture outcomes and the source discovery's residual risks.
- **Outputs**: Passing contract checks, the updated module docstring and the deployed broker.
- **Behavior**: Document the covered argv forms with examples and the remaining shell, pathspec and indirect-input boundary in the staged broker's module docstring, and replace the `ponytail:` note in `file_args` that says only whole arguments are inspected. This is reference material, not recurring work, so no procedure file is written. One-time deploy steps stay in Phase 3 of this PRD. Document what was measured and what remains unverified. Recheck observed-state premises before editing; when obsolete, skip the obsolete mutation and report evidence rather than forcing it. Never weaken existing checks to satisfy new ones.

## Structural Decomposition

### Repository Structure

```text
docs/dev/tmp/00176-stage/
└── bin/
    ├── warrant                          # staged copy of ~/bin/warrant after PRD 00166; candidate grammar and module docstring
    └── tests/
        ├── test_warrant.py              # staged copy of ~/bin/tests/test_warrant.py, unchanged regression suite
        └── test_warrant_arguments.py    # new contract tests
```

### Module: Implementation
- **Maps to capability**: Consistent argv inspection; Qualification and delivery (module docstring)
- **Location**: `docs/dev/tmp/00176-stage/bin/warrant`
- **Responsibility**: Implement the behavior above in the staged copy, including the module docstring.
- **Exports**: `file_args`, `review`, `show`, `launch`

### Module: Contract tests
- **Maps to capability**: Consistent argv inspection; Qualification and delivery
- **Location**: `docs/dev/tmp/00176-stage/bin/tests/test_warrant_arguments.py`, `docs/dev/tmp/00176-stage/bin/tests/test_warrant.py` (unchanged regression copy)
- **Responsibility**: Exercise fixture behavior, failure paths and integration with the staged implementation.
- **Exports**: The named unittest methods on `WarrantArgumentsCase`. Direct selection fails if a case is absent.
- New symbols: `WarrantArgumentsCase`, `test_glued_candidates_match_consumer`, `test_glued_candidates_change_or_appear_refuse`, `test_candidate_identity_and_directory_warnings`

## Dependency Graph

### Foundation Layer (Phase 0)
No internal dependencies - staged copies of the live files are made first.
- **Implementation**: the staged broker, identical to the live one before any edit.
- **External prerequisites**: 00166-broker-root-commands-through-warrant-v1.md, deployed.

### Core Layer (Phase 1)
- **Contract tests**: Depends on [Implementation]; the named cases load the staged broker, and the implementation edits land in the same task. Re-read the actual prerequisite code; do not copy stale tuple shapes or line numbers.

### Integration Layer (Phase 2)
- **Implementation** (module docstring) and **Contract tests** (integration cases): depend on the Phase 1 work of both modules.
- **Host deploy** (Phase 3): Depends on [Implementation, Contract tests]; human warrant acts after the review closes.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Stage the live broker after its prerequisite.

**Tasks**:
- [ ] Copy `~/bin/warrant` and `~/bin/tests/test_warrant.py` into the staged layout above (no deps) - Acceptance: `test -f docs/dev/project-management/prds/done/00166-broker-root-commands-through-warrant-v1.md` exits 0 and `rg -n "def fingerprint" docs/dev/tmp/00176-stage/bin/warrant` prints one line, so PRD 00166 is done and deployed (link-ok: future done path); `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00176-stage/bin/tests -t docs/dev/tmp/00176-stage/bin/tests -p 'test_warrant.py'` exits 0 before any edit.

**Exit Criteria**: The prerequisite is confirmed and the staged regression suite is green before any edit.

### Phase 1: Core
**Goal**: Implement the two functional features with their contract tests.

**Tasks**:
- [ ] Implement the stated behavior in `docs/dev/tmp/00176-stage/bin/warrant` and add `docs/dev/tmp/00176-stage/bin/tests/test_warrant_arguments.py` (depends on: Phase 0) - Premise: the staged `file_args` inspects whole argv entries only; a failed premise means skip the obsolete edit and report with evidence. Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00176-stage/bin/tests -t docs/dev/tmp/00176-stage/bin/tests -p 'test_warrant_arguments.py' -k test_glued_candidates_match_consumer` and the same command with `-k test_glued_candidates_change_or_appear_refuse` pass; record the first case's failure against the unedited staged broker as evidence. A fake executable consumes each supported glued form and receives unchanged reviewed data; controlled cwd avoids accidental literal-file matches. PIN callbacks mutate, create, remove or retarget each candidate; all affected launches refuse and no consumer marker is written.

**Exit Criteria**: Both feature contracts pass their focused checks without modifying live host state.

### Phase 2: Integration
**Goal**: Verify edge cases and document the argv boundary.

**Tasks**:
- [ ] Add `test_candidate_identity_and_directory_warnings` to `docs/dev/tmp/00176-stage/bin/tests/test_warrant_arguments.py` and update the module docstring of `docs/dev/tmp/00176-stage/bin/warrant` (depends on: Phase 1) - Acceptance: the Phase 1 command with `-k test_candidate_identity_and_directory_warnings` passes. Exercise multiple candidates at one argv index, ordinary literals, a real file named 5, directory warnings and root-command normalization. `/opt/homebrew/bin/python3 docs/dev/tmp/00176-stage/bin/warrant --help` prints the covered argv forms and names `sh -c` strings, Git pathspec magic and indirect reads as uncovered; the `ponytail:` note about whole arguments is gone from `file_args`.

**Exit Criteria**: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00176-stage/bin/tests -t docs/dev/tmp/00176-stage/bin/tests -p 'test_*.py'` passes once against the staged files. The fresh-session review closes before Phase 3.

### Phase 3: Deploy
**Goal**: Install the reviewed broker (human on the host, or warrant requests the human approves).

**Tasks**:
- [ ] Copy the staged `bin/warrant` and `bin/tests/test_warrant_arguments.py` to `~/bin/warrant` and `~/bin/tests/test_warrant_arguments.py` with warrant `cp` requests, so the source is hashed (depends on: Phase 2 and its review). Acceptance: `diff` of each deployed file against its staged copy is empty; `~/bin/warrant list` passes preflight; the host suite `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'` is green.
- [ ] One commit, then push (depends on: deploy) - Acceptance: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" show --stat HEAD` lists exactly `bin/warrant` and `bin/tests/test_warrant_arguments.py`; never stage `passphrase.scrypt` or `ledger.jsonl`.

**Exit Criteria**: Host suite green, broker deployed, commit pushed.

## Test Strategy

### Critical Scenarios
- **Happy path**: A fake executable consumes each supported glued form and receives unchanged reviewed data; controlled cwd avoids accidental literal-file matches.
- **Edge case**: A literal -n5 with an existing fixture file named 5 is inspected; multiple candidate forms cannot suppress an appeared-file check.
- **Error case**: Any changed or newly appeared regular-file candidate refuses through the existing broker result path.

## Risks

- **Operational limits**: A heuristic cannot reproduce each tool grammar; retain conservative false positives and explicit indirect-input limits.
- **Concurrent repository changes**: Re-read prerequisite code and current configuration before staging; preserve unrelated work.
- **Scope drift**: No additional discovery scope enters this PRD.
