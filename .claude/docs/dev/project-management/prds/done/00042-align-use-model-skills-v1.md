---
catchup: skip
---

# Align Use-Model Dispatch Skills

## Overview

### Problem Statement

The four external-model dispatch skills (`use-codex`, `use-gemini`, `use-qwen`, `use-sonnet`) are near-copies that drifted apart. Three concrete problems:

1. **Latent hang bug**: only `codex-run.sh` redirects child stdin (`< /dev/null`, 3 occurrences, test-locked by PRD 00040). `gemini-run.sh`, `qwen-run.sh`, and `sonnet-run.sh` have zero occurrences (verified 2026-07-07). A child CLI that waits on stdin during an unattended background dispatch hangs the autopilot loop, the exact failure class PRD 00040 fixed for codex.
2. **No tests for 3 of 4 scripts**: only `test_codex_run.sh` exists (33 asserts). The other three scripts have no regression net.
3. **Prose drift**: roughly half of each SKILL.md is a shared template (Background Dispatch and Waiting, Following Up, Error Handling, the always-use `-f` rule, the never-hand-roll-polling rule) that exists in four drifting copies; `use-qwen` lost its "Following Up" section entirely. Flag surface and error streams also differ: qwen lacks `-s/--silent`; only gemini sends "prompt file not found" to stderr.

### Target Users

Autopilot work/review phases dispatching external CLIs unattended; Bob invoking `/use-codex` etc. manually.

### Success Metrics

- `rg -c "< /dev/null"` reports at least 1 for every child CLI invocation in all four run scripts; 0 unguarded child invocations remain.
- 4 of 4 run scripts have a passing test suite; the stdin-guard tests demonstrably fail against the pre-fix scripts (fail-first evidence in task output).
- The shared prose exists exactly once (`use-codex/references/dispatch-contract.md`); each of the four SKILL.md bodies keeps only backend-specific content plus a pointer.
- Zero consumer breakage: skill names, script filenames, and script paths unchanged.

## Functional Decomposition

### Capability: Dispatch safety

Make every dispatch script safe for unattended background use.

#### Feature: Guard child stdin in run scripts

- **Description**: Redirect stdin of every external CLI child invocation to `/dev/null`.
- **Inputs**: `~/.claude/skills/use-gemini/scripts/gemini-run.sh`, `~/.claude/skills/use-qwen/scripts/qwen-run.sh`, `~/.claude/skills/use-sonnet/scripts/sonnet-run.sh`.
- **Outputs**: Same scripts; every child CLI invocation (all backends and fallbacks, including probe/preflight calls that spawn the CLI) carries `< /dev/null`, mirroring `codex-run.sh`.
- **Behavior**: Prompts already pass via argument or `-f` file, never stdin, so the guard changes no successful path; it only prevents a child from blocking on a TTY read. Write the regression test first and watch it fail against the unguarded script (mandatory fail-first). Premise (re-verify at execution): PRD 00019 (earlier by sequence) may already have guarded `qwen-run.sh` for Quinn's unattended review dispatch - fail-first evidence is required only for scripts still unguarded; record no-change-needed for any already-guarded invocation.

#### Feature: Add test suites for gemini, qwen, and sonnet scripts

- **Description**: Give the three untested scripts the same regression net codex has.
- **Inputs**: `test_codex_run.sh` as the pattern (stub binaries on a temp PATH, assert argv construction, `-f` file handling, `-o` output handling, exit-code propagation).
- **Outputs**: `test_gemini_run.sh`, `test_qwen_run.sh`, `test_sonnet_run.sh` in the respective `scripts/` dirs, executable, all passing.
- **Behavior**: Each suite must at minimum assert: (a) child argv for a plain `-f` run, (b) stdin of the child is `/dev/null` (the fail-first test for the feature above), (c) usage errors exit non-zero, (d) exit-code propagation from the child, (e) backend-specific behavior (gemini: `GEMINI_BACKEND` override and copilot-preferred order; qwen: port-probe fallback; sonnet: `claude -p` invocation shape).

### Capability: Interface parity

One flag surface and one error convention across the four scripts.

#### Feature: Accept silent flag in qwen-run

- **Description**: `qwen-run.sh` accepts `-s/--silent` as the other three do.
- **Inputs**: `qwen-run.sh` arg parser.
- **Outputs**: `-s/--silent` parsed and accepted (no-op on the native backend, same as codex/gemini/sonnet treat it).
- **Behavior**: Unknown-flag failure on `-s` disappears; covered by a test assert. Existing qwen-only flags (`-R`, `-j`, `-P`) stay.

#### Feature: Route usage errors to stderr

- **Description**: "Prompt file not found" and other usage errors go to stderr in all four scripts.
- **Inputs**: The four run scripts (today only gemini uses stderr; codex/qwen/sonnet print to stdout).
- **Outputs**: All usage/error messages on stderr, exit non-zero; stdout reserved for model output and the tee'd run log.
- **Behavior**: Update `test_codex_run.sh` expectations if they pin stdout for error text; add stderr asserts to the three new suites.

### Capability: Single-source shared prose

One canonical copy of the dispatch contract.

#### Feature: Extract shared dispatch contract reference

- **Description**: Move the shared SKILL.md sections into one reference file.
- **Inputs**: The four SKILL.md bodies; canonical wording comes from `use-codex/SKILL.md` where copies drifted.
- **Outputs**: New `~/.claude/skills/use-codex/references/dispatch-contract.md` containing: Background Dispatch and Waiting (incl. the "never hand-roll a polling loop; TaskOutput is the only wait primitive" rule), Following Up, Error Handling, and the "always use `-f` for prompts to avoid shell escaping" rule.
- **Behavior**: Each of the four SKILL.md files replaces its copy with a one-to-two-line pointer (absolute path) plus only backend-specific deltas (model/multiplier policy, flag quick-reference, prerequisites for qwen). `use-qwen` regains "Following Up" via the shared file. Wording that drifted (e.g. qwen's compressed polling-loop rule) is retired in favor of the canonical text.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/
├── use-codex/                 # Maps to: Single-source shared prose
│   ├── SKILL.md               # points to dispatch-contract.md
│   ├── references/dispatch-contract.md   # NEW canonical shared prose
│   └── scripts/{codex-run.sh, test_codex_run.sh}  # stderr alignment only
├── use-gemini/                # Maps to: Dispatch safety, Interface parity
│   ├── SKILL.md
│   └── scripts/{gemini-run.sh, test_gemini_run.sh (NEW)}
├── use-qwen/
│   ├── SKILL.md
│   └── scripts/{qwen-run.sh, test_qwen_run.sh (NEW)}
└── use-sonnet/
    ├── SKILL.md
    └── scripts/{sonnet-run.sh, test_sonnet_run.sh (NEW)}
```

### Module: use-codex

- **Maps to capability**: Single-source shared prose
- **Responsibility**: Reference implementation; owns the canonical dispatch contract
- **Exports**: `references/dispatch-contract.md`, `codex-run.sh` (behavior unchanged except error stream)

### Module: use-gemini / use-qwen / use-sonnet

- **Maps to capability**: Dispatch safety, Interface parity
- **Responsibility**: Backend-specific dispatch with guarded stdin, tested
- **Exports**: `<backend>-run.sh` (same name, same path, same flags plus qwen `-s`), `test_<backend>_run.sh`

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies; built first.

- **test harnesses**: fail-first stdin-guard tests for gemini/qwen/sonnet (they encode the target contract)

### Core Layer (Phase 1)

- **script fixes**: depends on [test harnesses] (stdin guard, `-s` parity, stderr routing make the red tests green)

### Integration Layer (Phase 2)

- **shared prose extraction**: depends on [script fixes] (the contract file documents the post-fix behavior)

## Implementation Phases

### Phase 0: Foundation

**Goal**: Red tests that pin the target contract.

**Tasks**:

- [ ] Add test suites for gemini, qwen, and sonnet scripts (no deps) - Acceptance: three executable `test_*_run.sh` files exist; stdin-guard asserts FAIL against each still-unguarded script (failure output pasted; a script already guarded by 00019 just passes - note it); all other asserts pass

**Exit Criteria**: Three new suites exist; stdin-guard asserts red, everything else green.

### Phase 1: Core

**Goal**: Scripts safe and consistent.

**Tasks**:

- [ ] Guard child stdin in run scripts (depends on: Phase 0) - Acceptance: stdin-guard tests pass; `rg -n "< /dev/null"` shows a guard on every child CLI invocation in all four scripts
- [ ] Accept silent flag in qwen-run (depends on: Phase 0) - Acceptance: `qwen-run.sh -s -f <file>` parses without error (test assert)
- [ ] Route usage errors to stderr (depends on: Phase 0) - Acceptance: all four suites assert error text on stderr and non-zero exit; `test_codex_run.sh` still fully green

**Exit Criteria**: All four test suites fully green.

### Phase 2: Integration

**Goal**: One canonical dispatch contract.

**Tasks**:

- [ ] Extract shared dispatch contract reference (depends on: Phase 1) - Acceptance: `dispatch-contract.md` exists; each use-* SKILL.md contains a pointer to it and no longer contains its own copy of the four shared sections; `rg -n "hand-roll" ~/.claude/skills/use-*/SKILL.md` matches only via the pointer file; create-skill validator passes on all four skills

**Exit Criteria**: Success metrics all hold; `bash test_codex_run.sh && bash test_gemini_run.sh && bash test_qwen_run.sh && bash test_sonnet_run.sh` all green (run as separate calls).

## Test Strategy

### Critical Scenarios

- **Happy path**: `-f prompt.md -o out.log` dispatch via stubbed backend → Expected: correct argv, child stdin is `/dev/null`, exit 0, output teed
- **Edge case**: prompt file missing → Expected: message on stderr, non-zero exit, backend never invoked
- **Edge case**: `-s` passed to qwen → Expected: accepted as no-op
- **Error case**: backend exits non-zero → Expected: exit code propagated, error visible in output file

## Risks

- **Consumer breakage**: ~18 hardcoded references to these skill/script names exist across `work`, `review-work-completion`, `review-blindly`, and autopilot tests (one asserts the literal string `sonnet-run.sh`). Mitigation: names and paths are frozen; this PRD only edits script internals and SKILL.md prose.
- **A backend that legitimately reads stdin**: none of the four do (prompts pass via arg/file; codex has run guarded since PRD 00040). If a test reveals one, keep that single invocation unguarded and document it in the contract file.
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; use explicit `--git-dir/--work-tree` git form; no CHANGELOG entries.
