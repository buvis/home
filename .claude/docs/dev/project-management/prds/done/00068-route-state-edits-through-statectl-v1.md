---
design: skip
---

# Route State Edits Through statectl

> Boundary note (2026-07-18 backlog review): the 00051 state-machine core
> (staged to land next batch) claims a schema-validated sole-writer boundary
> for state.json. statectl is the shared low-level atomic writer beneath it:
> 00051's boundary calls or absorbs statectl (its design decides which), and
> statectl keeps owning generic field mutations (attempts[] appends) that
> 00051's records do not cover. Neither PRD rips out the other's writer path.

## Overview

### Problem Statement

state.json is edited by the model 100-150 times per batch (transcript mining
2026-07-14: Edit/Write x108 ddb, x153 jink, x137 playground in 40-session
samples) while hooks write the same file. The two dominant edit-error classes
concentrate on it ("File has not been read yet" ~60, "File has been modified
since read" ~50 across the samples), each error costing a full round-trip,
and every successful Edit round-trips state.json content through context.
rules/ai-app-design.md is explicit: deterministic transforms belong in code,
not the model. Evidence file:
`dev/local/discovery/inbox/workflow-opportunities-2026-07-14.md`.

### Target Users

Unattended autoclaude batches (fewer error retries, fewer tokens); anyone
reading state.json (writes become atomic and always-valid JSON).

### Success Metrics

- Zero prose instructions in work/run-autopilot telling the model to Edit or
  Write state.json (one documented human-fallback note allowed).
- state.json is valid JSON after every mutation, including concurrent ones.
- Future transcript mining shows the two error classes vanish for state.json.

## Functional Decomposition

### Capability: statectl CLI

One small deterministic owner for state.json mutations.

#### Feature: Read and write operations
- **Description**: `statectl.py <state-path> get|set|append|del <json-path> [value]`.
- **Inputs**: path to a state.json, a dot/bracket JSON path (e.g. `tasks[3].attempts`), a JSON-encoded value for set/append.
- **Outputs**: get prints the value as JSON; mutations print nothing on success; exit 0 success, 1 usage error, 2 missing/corrupt state with a clear stderr line.
- **Behavior**: stdlib-only python3. Mutations parse the whole file, apply the change, and write via tmp-file + `os.replace` (atomic). Before the first mutation of an invocation, copy the current file to `state.json.bak` (one rotating backup). Corrupt input never gets overwritten: exit 2 and leave the file for forensics.

#### Feature: attempts[] append contract
- **Description**: `append` implements the atomic write procedure that `references/attempt-logging.md` documents in prose.
- **Inputs**: an attempt entry as JSON.
- **Outputs**: entry appended; the prose procedure replaced by a citation to statectl.
- **Behavior**: Premise, re-checked at execution: read `~/.claude/skills/work/references/attempt-logging.md` (it lives under work/, not run-autopilot/) and `run-autopilot/references/state-schema.md` first; the documented procedure is the spec, statectl the implementation. Any mismatch between the two is reported before editing either.

### Capability: Skill rewiring

#### Feature: Prose migration to statectl calls
- **Description**: every instruction in work SKILL.md, run-autopilot SKILL.md, and run-autopilot references/ that tells the model to Edit/Write state.json becomes a `python3 .../statectl.py` Bash invocation.
- **Inputs**: rg enumeration of edit sites (`rg -n 'state.json' <those files>`), recorded before editing.
- **Outputs**: rewritten instructions; each file's site count reported (before/after).
- **Behavior**: Premise, re-checked at execution: enumerate first, report the count; an instruction that cannot be expressed as get/set/append/del is reported, not forced. Hook writers (e.g. autopilot_context_cap_hook.py) are out of scope except a premise re-check that their write is atomic; if it trivially is not, align it, else report. The PostToolUse validator `run-autopilot/scripts/validate_state_json_hook.py` guards model edits of state.json and stays in place - it is an ally, not an Edit-instruction site; do not rewire or remove it.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/run-autopilot/
├── scripts/
│   ├── statectl.py                # Maps to: statectl CLI (new)
│   └── test_statectl.py           # Maps to: statectl CLI tests (new)
├── SKILL.md                       # Maps to: Skill rewiring
└── references/
    └── state-schema.md            # Maps to: append contract (unchanged shapes)
~/.claude/skills/work/
├── SKILL.md                       # Maps to: Skill rewiring
└── references/
    └── attempt-logging.md         # Maps to: append contract (cites statectl)
```

### Module: statectl
- **Maps to capability**: statectl CLI
- **Responsibility**: the only writer path the model uses for state.json; atomic, validated, backed up.
- **Exports**: `get/set/append/del` CLI verbs; exit codes 0/1/2.

### Module: skill prose
- **Maps to capability**: Skill rewiring
- **Responsibility**: instructions that dispatch statectl instead of Edit.
- **Exports**: rewritten state-mutation steps in both SKILL.md files and attempt-logging.md.

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **statectl**: CLI + tests, contract pinned before any prose changes.

### Core Layer (Phase 1)
- **skill prose**: Depends on [statectl] (instructions reference a working tool).

### Integration Layer (Phase 2)
- **verification + commit**: Depends on [statectl, skill prose].

## Implementation Phases

### Phase 0: Foundation
**Goal**: A trustworthy state mutator exists.

**Tasks**:
- [ ] Read attempt-logging.md and state-schema.md; record the documented atomic procedure and field shapes (no deps) - Acceptance: task report quotes the procedure and confirms statectl's design matches or names the mismatch.
- [ ] Implement statectl.py + test_statectl.py (no deps) - Acceptance: tests cover get/set/append/del happy paths, concurrent mutations (two parallel appends both land, file valid JSON), missing file exit 2, corrupt file exit 2 without overwrite, backup file written before first mutation.

**Exit Criteria**: test suite green; corrupt-input fixture provably untouched.

### Phase 1: Core
**Goal**: The model stops editing state.json.

**Tasks**:
- [ ] Enumerate and rewrite every Edit/Write-state.json instruction in work SKILL.md, run-autopilot SKILL.md, references/ (depends on: Phase 0) - Acceptance: before/after site counts reported; `rg -n 'Edit.*state\.json|Write.*state\.json'` over those files returns only the documented human-fallback note; attempt-logging.md cites statectl instead of restating the procedure.

**Exit Criteria**: prose sweep clean; skills' `## Dependencies` sections name statectl.

### Phase 2: Integration
**Goal**: Landed safely around the live loop.

**Tasks**:
- [ ] Verify hook-writer atomicity premise (autopilot_context_cap_hook.py) (depends on: Phase 1) - Acceptance: report states atomic yes/no and what was done.
- [ ] Commit statectl, tests, and skill prose to the buvis bare repo by absolute pathspec, never `-a` (no CHANGELOG; dotfiles exemption) (depends on: all) - Acceptance: `git --git-dir=$HOME/.buvis --work-tree=$HOME log -1 --stat` lists the files.

**Exit Criteria**: all tests green; next batch session loads statectl-based prose.

## Test Strategy

### Critical Scenarios
- **Happy path**: append an attempts[] entry → file valid, entry last, backup exists.
- **Edge case**: two concurrent appends → both entries present after both exit, file valid JSON throughout (tmp+replace).
- **Error case**: corrupt state.json → exit 2, stderr names the parse error, file byte-identical afterwards.

## Risks

- **Prose change lands mid-batch**: sessions load skills at start, so the change activates at the next relaunch boundary; additive and backward-compatible (Edit still physically works for humans).
- **statectl bug corrupts state**: tmp+replace plus the rotating .bak plus the corrupt-input refusal bound the damage to one recoverable step.
- **JSON-path ambiguity**: keep the path grammar minimal (dots + [index]); anything fancier is reported as unsupported rather than guessed.
