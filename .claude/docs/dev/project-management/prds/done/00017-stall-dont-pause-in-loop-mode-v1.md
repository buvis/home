---
catchup: skip
design: skip
---

# Stall, Don't Pause, in Loop Mode

## Overview

### Problem Statement

The user's top complaint: the loop "often asks for user intervention or ends prematurely." The pause inventory confirms it. Loop-mode runs can stop for: cap-pause (unresolved findings at the rework cap), scope alarm (>10 follow-ups), requirements clarification, blocking escalation, sub-skill failure, reviewer failure, and mv-verify failure. Every one halts the whole batch until a human returns - on an unattended overnight run that is dead hours (31 min and 145 min stranded on 2026-06-15 before the AskUserQuestion ban; usage-limit idles blocked whole nights before 3f760d622). The design is also inconsistent with itself: a CRITICAL review finding defers to batch end and the loop keeps going, but leftover MEDIUM findings at the cap PAUSE everything.

The fix is a policy, applied uniformly in loop mode: **a single PRD may stall; the batch never stops to ask a question.** A PRD that cannot proceed autonomously moves to `dev/local/prds/stalled/` with its reason recorded, the loop advances to the next PRD, and every stall and deferral is presented once at batch end (which PRD 00014 already made a notify-then-interactive-review flow). Interactive (non-loop) behavior keeps today's PAUSE semantics - a present human should be asked.

### Target Users

Unattended `autoclaude` batches; the user's sleep.

### Success Metrics

- In loop mode, zero mid-batch turn-ending PAUSEs remain except two: a security-critical finding (exposed secret / vulnerability being shipped) and detected data-loss risk. Everything else stalls the PRD or defers and continues.
- A scripted batch containing (a) a PRD that hits the rework cap unresolved and (b) a PRD with a requirements ambiguity drains to batch end unattended, with both surfaced in the batch-end review.
- The stalled path is uniform: PRD file moved to `stalled/`, `stall_reason` recorded in the deferred JSON with site + detail, loop continues, batch-end lists it with resume instructions.
- Interactive-mode PAUSE behavior byte-unchanged.

## Functional Decomposition

### Capability: Convert loop-mode pauses to stall-or-defer

#### Feature: Cap-out defers instead of pausing

- **Description**: Hitting the rework cap with unresolved findings stops polishing, not the batch.
- **Inputs**: `~/.claude/skills/run-autopilot/SKILL.md` Phase 5 "Cap check" + "Cap-pause behavior".
- **Outputs**: In loop mode (`$_AUTOPILOT_LOOP` set): unresolved findings of severity ≤ high are appended to `deferred_decisions` (type `cap-overflow`), the PRD proceeds to Phase 9 as converged-with-deferrals, and the banner names the deferral count. Any unresolved CRITICAL instead stalls the PRD (move to `stalled/`, record, continue batch). Outside the loop: current cap-pause behavior unchanged (`cap_pause_reason` + paused + resume handler).
- **Behavior**: The Phase 0 Cap-Pause Resume Handler and `cap_pause_reason` field stay - they now serve only interactive runs.

#### Feature: Ambiguity resolves by simplest safe assumption

- **Description**: Plan-time clarification questions stop blocking unattended batches.
- **Inputs**: SKILL.md Phase 2 PAUSE site, Error Handling table loop-mode paragraph, `references/decision-framework.md` "Autonomy in loop mode".
- **Outputs**: In loop mode, a requirements ambiguity is resolved by the simplest safe assumption (the user's own global rule), logged to `autonomous_decisions` with the assumption stated and type `assumed-ambiguity`, and mirrored into the deferred JSON so batch-end review shows it. A PRD may force the old behavior with frontmatter `pause_on_ambiguity: true` (then loop mode stalls the PRD instead of guessing - never pauses the batch).
- **Behavior**: Phase 0 parses the new frontmatter key with the same tolerant YAML rules as `catchup:` (absent/malformed → false).

#### Feature: Failures stall the PRD, not the batch

- **Description**: Sub-skill, reviewer, scope-alarm, and mv-verify failures get retry-then-stall semantics.
- **Inputs**: Error Handling table rows (sub-skill fails, review unparseable, all reviewers fail), Phase 5 Safety Checks scope alarm, the two mv-verify sites (Phase 0, Phase 9), `references/recovery.md`.
- **Outputs**: In loop mode: each site retries once where a retry is meaningful (mv after re-`mkdir -p`; sub-skill/reviewer re-invoke once), then moves the PRD to `stalled/` with `stall_reason.site` + detail in the deferred JSON and continues the batch. Scope alarm (>10 follow-ups) keeps the top 10 by severity, defers the rest (type `scope-overflow`), and continues - mirroring the existing doubt >5 overflow rule. recovery.md gains one "Loop-mode stall procedure" section all sites reference (move, record, banner, continue).
- **Behavior**: Outside the loop, all sites keep today's PAUSE-and-report behavior. The two loop-mode PAUSEs that remain (security-critical, data-loss) are written into the Error Handling table explicitly so future edits don't re-grow the list.

#### Feature: Batch-end surfaces stalls first

- **Description**: The human reviews everything the loop decided alone, stalls first.
- **Inputs**: SKILL.md Phase 9 batch-end review section (post-00014: the `review-batch` interactive entry), `references/batch-report-format.md`.
- **Outputs**: Batch-end presentation gains a leading `STALLED PRDS` chunk (PRD, site, detail, "resume: move back to wip/ and re-run") and renders `assumed-ambiguity` items under a visible "assumptions made" heading. The final ntfy message includes counts: `N done, M stalled, K deferred`.
- **Behavior**: No stalls and no deferrals → sections omitted, message stays short.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/run-autopilot/SKILL.md              # Phase 5 cap, Phase 2 ambiguity, Error Handling, Phase 9 batch-end
~/.claude/skills/run-autopilot/references/decision-framework.md  # loop-mode autonomy rules
~/.claude/skills/run-autopilot/references/recovery.md            # loop-mode stall procedure
~/.claude/skills/run-autopilot/references/batch-report-format.md # stalled/assumptions sections
```

### Module: run-autopilot

- **Maps to capability**: Convert loop-mode pauses to stall-or-defer
- **Responsibility**: One uniform stall procedure; two sanctioned loop pauses
- **Exports**: `stalled/` + deferred-JSON contract; `pause_on_ambiguity` frontmatter

## Dependency Graph

### Foundation Layer (Phase 0)

- **stall procedure in recovery.md**: independent (all sites reference it)

### Core Layer (Phase 1)

- **cap-out defer**: depends on [stall procedure]
- **ambiguity assumption**: depends on [stall procedure]
- **failure sites retry-then-stall**: depends on [stall procedure]

### Integration Layer (Phase 2)

- **batch-end surfacing**: depends on Core
- **verification**: depends on all

## Implementation Phases

Premise rule: PRDs 00014-00016 run first by sequence; re-verify each anchor section by name before editing (`rg -n "Cap-pause behavior|Safety Checks|Error Handling" skills/run-autopilot/SKILL.md`) - if 00015 collapsed the phases, the cap section lives in the single review phase; anchor by heading, not phase number.

### Phase 0: Procedure

**Tasks**:

- [ ] Write the loop-mode stall procedure in recovery.md (no deps) - Acceptance: one section: verified mv to `stalled/`, deferred-JSON record shape `{type: "stall", site, detail, prd}`, banner format, continue semantics; an explicit note that this deferred-JSON record is distinct from `state.stall_reason` (the wrapper's context-cap replan signal, branch (2) of 00014's decision table) - the stall procedure never writes `state.stall_reason`

### Phase 1: Sites

**Tasks**:

- [ ] Cap-out defers / CRITICAL stalls in loop mode (depends on: Phase 0) - Acceptance: Phase 5 branches on `$_AUTOPILOT_LOOP`; interactive path byte-unchanged; cap-overflow entries carry severity
- [ ] Ambiguity assumption + pause_on_ambiguity frontmatter (depends on: Phase 0) - Acceptance: Phase 2 loop path never ends the batch; frontmatter parsed with tolerant-YAML rules; assumption logging specified
- [ ] Retry-then-stall for failure sites + scope overflow (depends on: Phase 0) - Acceptance: Error Handling table has loop-mode column/rows; exactly two loop-mode PAUSE rows remain (security, data-loss); scope alarm defers beyond top 10

### Phase 2: Surfacing

**Tasks**:

- [ ] Batch-end stalls/assumptions sections + ntfy counts (depends on: Phase 1) - Acceptance: presentation order stalls-first; ntfy format documented
- [ ] Unattended drain proof (depends on: all) - Acceptance: scratch batch with one cap-out PRD and one ambiguous PRD drains with zero mid-batch input; batch-end lists both; evidence pasted

**Exit Criteria**: Success metrics all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: clean PRDs → Expected: no behavior change at all
- **Edge case**: cap hit, 3 medium findings left → Expected: deferred as cap-overflow, PRD completes, batch continues, items at batch end
- **Edge case**: cap hit with 1 CRITICAL left → Expected: PRD stalled, batch continues, stall listed first at batch end
- **Edge case**: ambiguity + `pause_on_ambiguity: true` → Expected: PRD stalls (no guess), batch continues
- **Error case**: mv to stalled/ itself fails after retry → Expected: the one legitimate loud stop - notify ⚠️ and halt (cannot safely continue past a filesystem that refuses moves)

## Risks

- **Wrong assumptions ship**: bounded by batch-end visibility (every assumption listed), PRD-level opt-out, and the unchanged review lenses; the alternative (dead batch) costs more than reviewing an assumption after the fact.
- **Stall pile-up**: a systemic breakage (e.g. reviewer CLI down) stalls several PRDs instead of halting on the first; acceptable - batch end names them all and each retry happened; add nothing until this is observed in practice.
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; no CHANGELOG entries.
