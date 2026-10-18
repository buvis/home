---
catchup: skip
design: skip
---

# Flip Interactive Default Model After Fable Access Ends

> **CLOSED 2026-07-14 - OVERTAKEN BY THE OPERATOR, NOT IMPLEMENTED.** Mid-session
> the operator set the interactive default to `opus[1m]` by hand (settings.json
> `model`), which is the decision this PRD existed to make. Nothing here was
> executed: the Sonnet-first solution below was NOT applied and must not be -
> it would overwrite a fresh, deliberate choice. The one surviving mechanical
> item (strip the `[1m]` suffix so the 1M window is per-session opt-in) lives in
> PRD 00073, whose premise now keys on the suffix rather than the model name.
> The open cost question - whether an Opus/xhigh interactive default is worth it
> versus Sonnet-first with manual escalation - is NOT tracked by any PRD; raise
> it deliberately if you want it answered. Decided in the 2026-07-14 setup-review
> walkthrough (finding 10).

## Problem

The interactive default is `claude-fable-5` (with `[1m]` until PRD 00073 lands)
at max effort: every casual turn runs the most expensive configuration
available. Fable access is expected to end around 2026-07-15. Headless
autopilot already pins per-phase models in the autoclaude wrapper and PRDs
00075-00079 tier the task-level routing; the interactive default is the
remaining leg and must not duplicate those PRDs.

## Solution

Once Fable is actually unavailable, set the interactive default to
`claude-sonnet-5` with `effortLevel: high`, escalating per session by hand
(`/model claude-opus-4-8` or stronger when a session warrants it).
Sonnet-first matches the direction the user already chose in PRD 00076
(route-builds-sonnet-first-with-fable-rescue); opus-as-default was rejected
because escalation is a one-line session command while de-escalation never
happens in practice.

## Requirements

### Must have

- Execution-time premise gate: run `claude -p --model claude-fable-5 "reply ok"`;
  if it succeeds AND today is before 2026-07-16, Fable is still available -
  skip the flip entirely and report (autopilot parks this PRD, never forces).
- `settings.json`: `model` = `claude-sonnet-5`, `effortLevel` = `high`.
- Headless verification: run `claude -p "reply ok"` in `~/.claude`, parse the
  fresh transcript, assert the assistant message `model` field starts with
  `claude-sonnet-5`.
- Commit `settings.json` to the buvis bare repo by absolute pathspec, never
  `-a` (no CHANGELOG entry; dotfiles repo exemption).

### Nice to have

- One line in AGENTS.md Toolchain noting the default and the escalation habit.

## Implementation

### Module: settings-flip
- **Location**: `~/.claude/settings.json`
- **Responsibility**: Default model and effort for all new interactive sessions.
- **Exports**: `model`, `effortLevel` values.

### Dependencies

- settings-flip: No dependencies (foundation). Interacts with PRD 00073 (which
  drops `[1m]` earlier); whichever runs second simply overwrites `model`, both
  end states are compatible. Does not touch PRDs 00075-00079 scope (task-tier
  routing inside work/autopilot).

## Tasks

### Phase 0: Foundation
- [ ] Premise gate: Fable probe + date check; on "still available" skip all
  remaining tasks and report the probe output - both branches print evidence.
- [ ] Edit settings.json (`model`, `effortLevel`) - acceptance:
  `python3 -c "import json;s=json.load(open('/Users/bob/.claude/settings.json'));print(s['model'],s['effortLevel'])"`
  prints `claude-sonnet-5 high`.

### Phase 1: Core
- [ ] Verify live default (depends on: Phase 0) - acceptance: fresh `claude -p`
  transcript's assistant `model` starts with `claude-sonnet-5`; output pasted.
- [ ] Buvis commit of settings.json (+ AGENTS.md if the nice-to-have line was
  added) (depends on: Phase 0) - acceptance:
  `git --git-dir=$HOME/.buvis --work-tree=$HOME log -1 --stat` lists the files.

## Success Criteria

- New interactive sessions start on claude-sonnet-5 at high effort once Fable
  access has ended, with zero effect before that (premise-gated skip).
- Escalation path documented and unchanged: per-session `/model`.
