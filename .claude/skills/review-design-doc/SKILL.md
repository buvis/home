---
name: review-design-doc
description: Use when reviewing a system design document interactively (provide doc path). Walks findings one-at-a-time with three resolution options each; edits applied directly to the doc. Triggers on "review design doc", "critique design", "design review".
argument-hint: "<path/to/design-doc.md> [related-context-path] [related-codebase-path]"
---

# System Design Document Review (interactive)

Interactive, finding-by-finding review of a system design document. Each finding is presented with a one-paragraph explanation and three resolution options (one recommended); the user picks via AskUserQuestion. The session writes a resolution log to disk at the end.

This skill replaces the older one-shot review-document approach. Findings drive a workflow, not a report.

**Shared core**: the interactive-review machinery — finding-card format, three-resolution-options discipline, option picker ordering, ground rules (critical subset), comprehension/confusion-notes pass, success criteria, session-safety core — lives in `references/interactive-review.md` (shared with `review-discovery-doc`). Read it before generating findings. This skill's divergence from the shared core: **edits apply immediately, per finding** (Workflow step 8; Session safety).

## Inputs

**Required**:
- **Design document path** — an absolute path to the markdown design doc that will be reviewed and edited.

**Optional** (do not block on these; ask only if the doc references them or the user mentions them):
- **Related context path** — ADRs, prior designs, ticket, RFC, brainstorming notes
- **Related codebase path** — for "design vs. reality" spot-checks (sample, do not audit)

**Path solicitation**: a skill invocation rarely carries CLI-style args. At session start:

1. Scan the user's most recent message for a markdown file path. If exactly one is present and it exists, treat it as the design doc and confirm in chat: "Reviewing `<path>`. If that's the wrong doc, say so now."
2. If no path is present, ask plainly: "Which design document should I review? Provide an absolute path (e.g., `/Users/you/dev/foo/design.md`)." Wait for the answer; do not proceed.
3. Verify the path exists (Read or Bash `ls`). If it doesn't, ask again with the error.
4. Only ask about optional inputs if the design doc explicitly references external context the user hasn't given you, or the user volunteers them.

## Workflow

1. **Confirm the design doc path** (apply the Path solicitation steps in the Inputs section). Do not proceed until you have a verified path.

   Then perform the **comprehension pass, keeping a confusion-notes list**, exactly as specified in `references/interactive-review.md`. Confusion notes feed Question-severity findings in step 8.
2. **Absorb related context** if provided. Do not review the context itself.
3. **Identify domain and maturity** (web service, data pipeline, ML system, etc.; exploratory / RFC / production).
4. **Pick a tier mechanically.** Check Tier 3 conditions first; if any apply, run Tier 3. Else Tier 2. Else Tier 1. See `references/triage.md` for the observable conditions per tier.
5. **Scan for signals** that route to additional techniques (vague qualifiers, binary framings, authority appeals, etc.). See `references/triage.md`.
6. **Run the quantitative scripts** on the doc (the three listed in the Scripts section below) and capture their output as evidence in findings.
7. **Run the tier's analytical content** to produce an internal findings list:
   - Standard checklist (`references/checklist.md`) — 25 dimensional items
   - Cardinal sins (`references/cardinal-sins.md`) — fast-veto blockers
   - Premortem — most likely failure mode in 18 months
   - Tier-specific additions: anti-patterns, advanced techniques, stress tests, philosophical lenses (`references/*.md`)
8. **Present findings one at a time** in severity order, following `references/interactive-review.md` for option generation, card format, and picker ordering. For each finding, in strict sequence:
   - **a.** Generate the three approaches with the recommended in position 1, present the finding card, and call AskUserQuestion with the four options in the same order as the card — all per the shared core.
   - **b.** **Immediately apply** the chosen resolution. 1/2/3: use the Edit tool to apply that option's specific edit. 4 (no edit): capture the reasoning briefly in chat. Other (free-form): apply as a custom edit, or record as reasoning if the user said "skip."
   - **c.** Only after the Edit tool returns (or after recording the no-edit reasoning) move to the next finding.

   Do **not** batch decisions. Do **not** collect choices and apply at the end. The Edit must complete before the next card is presented. This makes the design document the single source of truth and makes session interruption safe (see Session safety).
9. **At session end**, briefly recap in chat: how many findings were addressed by edit, how many were disputed/deferred, and any open questions. Confirm the Success criteria conversationally.

## Interaction order

Strict severity order, top-to-bottom by doc location within each severity:

1. **Cardinal sins** (one at a time; all must be walked before proceeding)
2. **Blocking issues** (one at a time)
3. **Non-blocking concerns** (one at a time)
4. **Questions for the author** (one at a time)

The user may stop at any point. Cardinal sins and blockers should be fully walked before stopping; non-blockers and questions may be partially walked.

## Tier selection

Full conditions, reasoning, and signals per tier: `references/triage.md`. Pick mechanically per Workflow step 4. If reviewer and author disagree on tier, default up. Tier disagreement is itself a finding.

## Scripts

Standalone tools in `scripts/`. Run during the analysis phase (Workflow step 6) and cite their output as evidence in findings.

- `python3 ${CLAUDE_SKILL_DIR}/scripts/section_weight_audit.py <doc>` — flags sections >3x or <1/3 median weight; handles container sections and code blocks
- `python3 ${CLAUDE_SKILL_DIR}/scripts/claim_ladder_scan.py <doc>` — finds compressed qualifiers ("scalable", "robust", "fast", etc.) with their locations
- `python3 ${CLAUDE_SKILL_DIR}/scripts/adversarial_signal_scan.py <doc>` — finds imperatives, role-changes, framing language; distinguishes adversarial from framing per the calibration heuristic

Scripts are advisory; the reviewer makes the judgment call on whether a flagged item becomes a finding.

## Ground rules

Critical subset: `references/interactive-review.md`. Full set: `references/ground-rules.md`.

## Success criteria

The shared core's two criteria (surprise test + actionability) apply unchanged; assess both conversationally at session end.

## Session safety

Edits apply per-finding, immediately, by design: the design document always reflects exactly the decisions taken so far, so interruption is safe and there is no side state to recover. Resumption and long-session splitting: see the session-safety core in `references/interactive-review.md`.

**Never** batch decisions and apply at session end. Batching converts a safe-by-default workflow into an all-or-nothing transaction where partial completion means lost decisions. If you discover mid-session that batching is happening (no edits visible on the doc after the first few decisions), stop and ask Claude to flush pending decisions to the doc before continuing.

## Maintenance

**Self-review regeneration contract**: when SKILL.md or any file in `references/` changes materially (new section added, technique consolidated, criteria modified, scripts changed), regenerate `examples/self-review-vN.md` by applying this skill to itself. A stale self-review is itself a finding the next reviewer of this skill should flag.

**Convergence criterion** (when to stop self-iterating): stop self-iteration when a self-review round produces:
- 0 cardinal sins, AND
- 0 blocking issues, AND
- fewer than 5 non-blocking concerns, AND
- the skill has been applied to ≥1 real (non-self) design doc since the last self-review

Until the external-application condition is met, further self-iteration risks regression-by-polish: each fix could introduce a new issue. The maintenance contract still applies when the external application surfaces a real concern.

## Limitations

The framework's discipline is asserted (by structure) and self-tested (by the example in `examples/`), not validated by external measurement against a corpus. See `references/triage.md` for tier-specific tradeoffs. Apply with these limits in mind: a finding from this skill is a claim that the discipline was applied, not that the finding is empirically validated as correct.
