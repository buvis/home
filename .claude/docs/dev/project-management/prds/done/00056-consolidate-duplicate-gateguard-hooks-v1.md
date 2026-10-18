# Consolidate Duplicate Gateguard Hooks

> Source: full-config audit remediation 2026-07-10 — a live probe revealed BOTH gateguard copies run on every Edit/Write/Bash: the personal `~/.claude/hooks/gateguard-fact-force.py` (settings.json PreToolUse) and the aegis plugin's `hooks/gateguard_fact_force.py` (plugin hooks.json). The shared default state dir (`~/.claude/cache/gateguard`) masks the duplication: the first denial marks the target checked for both, so behavior looks like one gate. This is the exact failure mode recorded in memory `feedback_hook_discovery_scope`.
> Target: `~/.claude/hooks/` + settings.json (buvis) and the **claude-aegis** repo.

## Overview

### Problem Statement

Two diverged implementations of the same gate run in series:

- Personal copy: has `is_read_only_git` (ungated read-only git introspection); simpler destructive-Bash regex.
- Aegis copy (0.3.0 installed + source): stronger destructive-Bash detection (denylist `is_destructive` with shlex-parsed `bash -c` payloads, `dd if=`, path-qualified shells), fails open on malformed payloads, MultiEdit fix — but no read-only-git allowance.

Every fix must now land twice (the 2026-07-10 scratchpad exemption did), and any future state-dir or session-key divergence would double-gate every file (two denials per target instead of one). One implementation must own the gate.

### Target Users

The solo operator; every agent session pays the double-execution cost (~2 subprocess spawns per Edit/Write/Bash call for the same decision).

### Success Metrics

- Exactly one gateguard implementation is registered across settings.json + all plugin hooks.json files.
- The surviving copy contains the union of behaviors: read-only-git allowance AND the aegis-grade destructive-Bash detection, MultiEdit handling, fail-open hardening, temp/scratch exemptions.
- The retired copy's tests migrate (union of both suites, deduplicated); full suite green.
- A fresh-session probe shows one denial then one pass for a new gated file (never two denials).

### Non-Goals

- Changing gate policy (what gets gated) beyond merging existing behaviors.
- Extracting gateguard into its own plugin (project_next_plugins_to_ship lists a future gateguard plugin; if that lands later it inherits the consolidated copy — this PRD just kills the duplicate).

## Functional Decomposition

### Capability: Single-owner gate

#### Feature: Behavior diff and union
- **Description**: line-level diff of the two hooks; enumerate behaviors unique to each.
- **Inputs**: `~/.claude/hooks/gateguard-fact-force.py`, aegis `hooks/gateguard_fact_force.py`, both test suites.
- **Outputs**: a table (behavior → present-in → survives?) in the design doc; expected uniques at minimum: read-only-git (personal), bash -c destructive payloads + fail-open + MultiEdit top-level payload (aegis).
- **Behavior**: aegis is the recommended survivor (released, versioned, tested in CI).

#### Feature: Port personal-only behaviors into aegis
- **Description**: add `is_read_only_git` (and any other personal-only wins) to the aegis hook with the personal suite's tests.
- **Inputs**: the union table.
- **Outputs**: aegis release (minor) whose CHANGELOG names each ported behavior.
- **Behavior**: gate decisions for every payload in both old suites are preserved or consciously changed (named in CHANGELOG).

#### Feature: Retire the personal copy
- **Description**: remove the two settings.json PreToolUse registrations of `gateguard-fact-force.py`; delete the hook + its test file.
- **Inputs**: settings.json hooks block; `~/.claude/hooks/`.
- **Outputs**: buvis commit; `rg gateguard ~/.claude/settings.json` matches nothing.
- **Behavior**: only after the aegis release from the previous feature is installed locally.

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── hooks/gateguard-fact-force.py             # Maps to: Retire the personal copy (deleted)
├── hooks/tests/test_gateguard_fact_force.py  # Maps to: Retire the personal copy (tests migrate to aegis, then deleted)
└── settings.json                             # Maps to: Retire the personal copy (2 PreToolUse registrations removed)

~/git/src/github.com/buvis/claude-aegis/
├── hooks/gateguard_fact_force.py             # Maps to: Port personal-only behaviors (survivor)
└── hooks/tests/                              # Maps to: Port personal-only behaviors (union suite)
```

### Module: aegis gateguard (survivor)
- **Maps to capability**: Single-owner gate
- **Responsibility**: the one gateguard implementation — union of aegis 0.3.0 detection (denylist `is_destructive`, `bash -c` payloads, MultiEdit, fail-open) plus the personal copy's `is_read_only_git` allowance and temp/scratch exemptions.
- **Exports**: `hooks/gateguard_fact_force.py` (plugin hooks.json registration), released as an aegis minor version.

### Module: personal gateguard (retired)
- **Maps to capability**: Single-owner gate (removal side)
- **Responsibility**: none after Phase 1 — files deleted, settings.json registrations removed.
- **Exports**: none (retirement).

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **behavior-union table + aegis port/release**: source-of-truth diff of both copies.

### Core Layer (Phase 1)
- **local aegis install upgrade + live probe**: depends on [aegis port/release].
- **personal copy retirement (settings.json + files)**: depends on [live probe].

## Implementation Phases

### Phase 0: Diff and port
**Tasks**:
- [ ] Produce the behavior-union table (no deps). Acceptance: every function present in either file appears in the table with a survivor decision.
- [ ] Port personal-only behaviors + tests into aegis; release minor (depends on: table). Acceptance: aegis suite green including migrated tests; release published; CHANGELOG lists ported behaviors.

### Phase 1: Retire duplicate
**Tasks**:
- [ ] Update local aegis install to the new release; verify with a live probe that gating still works (depends on: Phase 0). Acceptance: fresh session, new file → exactly one deny, retry passes.
- [ ] Remove personal registrations + files; buvis commit (depends on: probe). Acceptance: settings.json has no gateguard entries; a gated Edit still denies once (aegis), temp/scratch stays exempt.

**Exit Criteria**: one implementation, union behavior, live probe clean.

## Test Strategy

- The union table drives test migration: every test from the personal suite either exists in aegis's suite or is consciously dropped with a reason.
- Live probes (fail-first at the system level): before Phase 1 removal, demonstrate the double-execution (two hook spawns per call via hook logs or a counter); after, one.

## Risks

- **Silent behavior loss in the merge**: mitigated by the union table + migrated tests.
- **Window where neither gate runs**: do the settings.json removal only after the upgraded aegis install is verified live (Phase 1 ordering).

## Outcome (2026-07-14, closed without the aegis port)

- Behavior-union diff ran (personal vs aegis 0.3.0). Result: the union table collapses — `is_read_only_git` is a no-op in BOTH copies (each gates only commands matching the destructive regex; read-only git never matches, so the allowance never changes a decision). Scratch/working-doc/settings exemptions exist in both. Aegis is otherwise strictly stronger (`shlex`-parsed `<shell> -c` payload detection, `dd if=\S`, exempt globs, robustness guards, `_common.read_input`).
- Therefore no aegis port or release was needed. Personal copy + its test retired directly (buvis `0ef7b9ee0`, 1,111 deletions); both settings.json registrations removed.
- Personal test suite disposition: aegis repo carries its own `hooks/tests/test_gateguard_fact_force.py`; the personal suite's only unique subject (the no-op `is_read_only_git`) is consciously dropped.
- `test_lib_cartographer.py::test_resolve_session_key_parity_with_gateguard` repointed at the installed aegis copy (mtime-newest version under plugins/cache), anchored via `HOOKS_DIR` so fake-home fixtures cannot miss the real cache. 81/81 green.
- Live gate verified same-session: the aegis gateguard fact-forced an `rm -rf` and two first-touch Edits during this very work — one deny, facts presented, retry passed.
