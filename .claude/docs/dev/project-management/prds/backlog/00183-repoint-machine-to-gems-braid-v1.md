---
eligibility: test -x "$HOME/.local/share/mise/installs/pipx-buvis-gems/latest/bin/braid"
design: skip
default_model: opus
model_tier_rationale: destructive blast radius - moves buvis-tracked config and removes a tracked link outside ~/.claude; every step carries a premise re-check
---

# Repoint this machine to the gems braid

Source: [Discovery 00182](../../discovery/00182-layer-agent-rules-across-hosts.md) (phase 1, machine step). Runs once buvis/gems PRD 00115 is released and the `pipx:buvis-gems` mise tool is upgraded; the `eligibility` check holds it until then. Companion of buvis/agent-skills PRD 00159.

Before launching: `export _AUTOPILOT_WRITE_SCOPE_EXTRA="$HOME/.config/bash:$HOME/.codex:$HOME/.local/bin:$HOME/.config/braid:$HOME/.config/agent-skills:$HOME/.agents"` (the write-scope fence denies these roots otherwise).

## Overview

### Problem Statement

The gems braid reads `~/.config/braid/sources.d` and never falls back to
`~/.config/agent-skills` (discovery 00182 decision). This machine's only source
file is the buvis-tracked `~/.config/agent-skills/sources.d/personal`, and
instructions still name the old launcher link `~/.agents/bin/braid`, which
agent-skills PRD 00159 leaves dangling.

### Target Users

The user on this machine; every agent session that runs `braid --check`.

### Success Metrics

- `braid --check` (the gems binary on PATH) exits 0.
- `rg -n "agents/bin/braid|config/agent-skills" ~/.agents/README.md ~/.claude/rules/memory.md ~/.claude/AGENTS.md` finds nothing.

## Functional Decomposition

### Capability: Move the machine configuration

#### Feature: Relocate sources.d
- **Description**: `~/.config/agent-skills/sources.d/personal` moves to `~/.config/braid/sources.d/personal` with the same content.
- **Inputs**: The old file.
- **Outputs**: The new file; the old directory removed once empty.
- **Behavior**: Premise: the old file exists, holds exactly the line `~/git/src/github.com/buvis/agent-skills`, and `~/.config/braid` does not exist. Re-check at execution; if any part fails, skip this feature and report what was found. No other file under `~/.config/agent-skills` may exist; if one does, stop and report it rather than delete it. In buvis, the commit records the move by explicit `:(top)` pathspecs (`.config/agent-skills/sources.d/personal` removed, `.config/braid/sources.d/personal` added); if the buvis index is not writable in the sandbox, file the staging through `~/bin/warrant request --no-wait` and report the request id.

#### Feature: Remove the old launcher link
- **Description**: Delete the tracked symlink `~/.agents/bin/braid` and the then-empty `~/.agents/bin`.
- **Inputs**: The link.
- **Outputs**: Link gone.
- **Behavior**: Premise: `~/.agents/bin/braid` is a symlink into `~/git/src/github.com/buvis/agent-skills/bin/`, and `~/.agents/bin` holds nothing else. Re-check; on failure skip and report.

### Capability: Verify and document

#### Feature: Check the composition
- **Description**: The gems braid sees the same union.
- **Inputs**: Relocated config, existing `~/.agents/.braid-state.json`.
- **Outputs**: `braid --check` result.
- **Behavior**: Run `braid --check`. Exit 0 is success. On drift, run `braid --dry-run`, paste its output into the report, and do not run a sync: a drift here means the port changed behavior, which is a gems defect to report, not to repair here.

#### Feature: Update instructions
- **Description**: Text names the gems braid and the new path.
- **Inputs**: `~/.agents/README.md`, `~/.claude/rules/memory.md`.
- **Outputs**: Edited text.
- **Behavior**: In `~/.agents/README.md`, replace the paragraph starting `One source today:` with `One source today: ~/git/src/github.com/buvis/agent-skills, recorded in ~/.config/braid/sources.d/personal. Every entry in ~/.agents/skills is a symlink into it. braid itself ships in buvis-gems (mise tool pipx:buvis-gems). Add a work-machine-only sources.d/work file when a private employer checkout exists.` (keep the path names in backticks as the file does today). In `~/.claude/rules/memory.md`, replace `as a second hop laid by `~/.agents/bin/braid`` with `as a second hop laid by `braid` (buvis-gems)`.

## Structural Decomposition

### Repository Structure

```text
~/.config/agent-skills/sources.d/personal   # moved (buvis-tracked)
~/.config/braid/sources.d/personal          # new location (buvis-tracked)
~/.agents/bin/braid                         # removed (buvis-tracked link)
~/.agents/README.md                         # edited
~/.claude/rules/memory.md                   # edited
```

### Module: machine configuration
- **Maps to capability**: Move the machine configuration, Verify and document
- **Responsibility**: Point this machine at the gems braid.
- **Location**: `~/.config/braid/sources.d/personal`, `~/.agents/README.md`, `~/.claude/rules/memory.md`
- **Exports**: none

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **machine configuration**: move, remove, verify, document.

### Core Layer (Phase 1)
- none

### Integration Layer (Phase 2)
- none

## Implementation Phases

### Phase 0: Foundation
**Goal**: This machine runs the gems braid with no drift.

**Tasks**:
- [ ] Re-check the premises, relocate `sources.d/personal`, remove `~/.agents/bin/braid` and `~/.agents/bin` (no deps) - Acceptance: `test -f ~/.config/braid/sources.d/personal && test ! -e ~/.config/agent-skills && test ! -e ~/.agents/bin`.
- [ ] Run `braid --check` as specified (depends on: first task) - Acceptance: `braid --check` exits 0, or the report carries the `--dry-run` output and the PRD stops here.
- [ ] Edit `~/.agents/README.md` and `~/.claude/rules/memory.md` as specified (depends on: second task) - Acceptance: `rg -n "agents/bin/braid|config/agent-skills" ~/.agents/README.md ~/.claude/rules/memory.md` finds nothing; `rg -n "buvis-gems" ~/.agents/README.md ~/.claude/rules/memory.md` hits both files.

**Exit Criteria**: `braid --check` exits 0 and `git --git-dir=$HOME/.buvis --work-tree=$HOME ls-files ':(top).config/braid/sources.d/personal'` prints the path (or the warrant request id is in the report).

## Test Strategy

### Critical Scenarios
- **Happy path**: move, remove, `braid --check` exit 0, docs updated.
- **Edge case**: an extra file under `~/.config/agent-skills` → stop and report, nothing deleted.
- **Error case**: `braid --check` drifts → report the dry-run output, no sync.

## Risks

- **Old braid still runs from an open shell**: it reads the old path and finds no sources; it exits 2 without writing.
- **Shared buvis index**: the user's live sessions may have staged files; stage by explicit path and check `git diff --cached --stat` before the commit.
