# Review: System Design Document Review (the framework, v5)

> **Format note**: This example predates the direct-edit workflow. It was generated when the framework still wrote a separate resolution log file. The current skill applies decisions directly to the reviewed document and does not produce a standalone review file. The findings and reasoning below are still illustrative of the framework's discipline; only the artifact shape is outdated. Regenerate on next real (non-self) application of the skill.

## Summary

**Tier applied: Tier 3 (Deep).** Justification: verification review of the new section-balance discipline (Option 4 implementation); meta-stake is whether the new technique catches what it was designed to catch.

**Success criteria check:**
- ✅ Surprise test (the new Section weight audit surfaces 4 heavy outliers and 1 light outlier in the framework itself, demonstrating the discipline works; but it also exposes that the technique as written doesn't handle container sections, which is a fresh finding)
- ⚠️ Noise-floor (reviewer-predicted; criterion remains nearly vacuous from v4)
- ✅ Proportionality (~140 lines review vs. ~750 lines framework)
- ➖ Actionability (N/A: no blockers in v5)

**Verdict:** The Option 4 implementation is operationally correct and catches the gap you flagged. Applied to the framework itself, it surfaces a real structural finding: four top-level sections (Advanced techniques, Review checklist, Lenses, Triage) are 4–8x the median weight. But the audit needs refinement to distinguish **container sections** (legitimately heavy because they hold many parallel sub-sections of balanced size) from **bloated sections** (heavy because one block of prose ran away). The discipline works; the procedure needs a small tightening.

## Adversarial signals

None.

## Cardinal sins detected

None.

## Blocking issues

None.

## Non-blocking concerns

1. **Section weight audit treats container sections as outliers.** *Cited: Advanced review techniques > Section weight audit; results applied to framework above.* The four heavy outliers (Advanced techniques at 1880w, Review checklist at 1557w, Lenses at 1210w, Triage at 1001w) are **container sections** — each holds many parallel sub-sections (18 techniques, 25 checklist items, 8 lenses, 3 tiers + signals + upgrade rule). At the sub-section level, weights are balanced (techniques ~50–150w each, lenses ~150w each, checklist items ~60w each). The audit as written produces false positives for any well-structured doc with multi-level sections. Suggested fix: "If a top-level section is a container of multiple parallel sub-sections (each at a comparable level of detail), audit at the sub-section level instead. The container's weight is structural; only its sub-sections are subject to outlier analysis."

2. **Section weight audit does not exclude code blocks.** *Cited: Section weight audit procedure; my measurement command captured `##` headings inside the Output format's code block as separate "sections," producing a 5-word reading for Output format.* When measuring with naive word counters, headings inside code blocks contaminate the count. Suggested fix: add a one-line note: "When counting, exclude content inside fenced code blocks; their `##` headings are illustrative, not structural."

3. **One genuine balance concern surfaces under the new discipline.** *Cited: Inputs section at 49 words.* The Inputs section is a light outlier (~0.2x median). On inspection, this is intentional — the section is just argument descriptions. But the audit as written would force this to be flagged or justified, and the doc does not currently justify it. Minor: either expand Inputs (likely unnecessary), or add a sentence acknowledging "Inputs is intentionally minimal because it lists arguments only."

4. **Inherited v4 concerns remain unaddressed in v5.** *Cited: v4 review.* This iteration focused on adding section-balance discipline, not on fixing the v4 set. Specifically:
   - Workflow step 1 density (v4 concern 1) — unchanged
   - Noise-floor criterion vacuity (v4 concern 2) — unchanged
   - Self-review maintenance loop cost / no convergence criterion (v4 concern 5) — unchanged
   
   These are not new; they are explicitly left for separate iteration. Worth listing so the inventory of open issues stays honest.

## Questions for the author

1. **(Container vs. bloated sections)** Should the Section weight audit be refined now to handle container sections explicitly, or is the false-positive cost acceptable because human reviewers can easily see when a heavy section is a container?

2. **(Inputs section)** Is the Inputs section's brevity intentional and worth flagging-and-justifying, or is the audit producing a noise finding here?

3. **(Convergence call)** v4 recommended declaring convergence; v5 added a new capability (Section weight audit). Was v4's convergence advice premature, or is v5 the genuine convergence point now that the user-flagged gap is closed?

4. **(External application)** Carry-over from v4: has the framework been applied to any real non-self doc yet? This remains the single most valuable unblock.

## Premortem: how this most likely fails

The Section weight audit's most likely failure mode is **false-positive fatigue**: a reviewer applies the audit to a doc with legitimate container sections (almost any production design doc has these), gets 4–6 "heavy outlier" findings, and either (a) flags all of them as concerns (over-flagging the author into dismissal) or (b) learns to ignore the audit (under-using a useful technique). The container-section gap surfaced in concern 1 is the proximate cause. The doc does not currently mitigate this; the audit reads as a mechanical procedure without the nuance that real docs have multi-level structure.

## Inverse problem: what is this v5 design actually optimized for?

The stated telos is unchanged. v5 added a new capability (section-balance discipline) rather than refining existing ones. The implicit telos shifted slightly: v1-v4 was "internal coherence and self-corrective discipline"; v5 added "user-driven gap closure" — the framework is now showing it can absorb a specific concern from outside and integrate the fix coherently. This is a different kind of validation than v1-v4's self-review loops.

## Persona walkthroughs

- **New user**: ✅ On-ramp first; unchanged from v4.
- **Reviewer under time pressure (Tier 1)**: ✅ Tier 1 still mechanical. Section weight audit is Tier 2+, so Tier 1 reviewers get the checklist #21 anchor without the full audit procedure.
- **Author receiving review**: ✅ Section-balance findings now possible; the new discipline gives a vocabulary for "your doc is structurally imbalanced."
- **Adversary**: unchanged from v4.
- **Doc author internalizing framework**: ✅ Section weight audit gives a self-check the doc author can run before submission.
- **Reviewer applying the audit to a real doc**: ⚠️ will hit the container-section false-positive issue on most non-trivial docs.

## Load-bearing assumptions

1. **Median weight is a meaningful anchor across sections of different content types.** *Cited: Section weight audit.* Plausible for prose-heavy docs; weaker for docs that mix prose, bullets, and tables.
2. **3x and 1/3x are the right outlier thresholds.** *Cited: Audit procedure.* Asserted defaults, like other thresholds in the framework. Calibration TBD.
3. **Heavy outliers are usually content imbalance, not container structure.** *Cited: implicit in the audit's framing.* False for well-structured docs; this is the v5 finding.

## Section-by-section findings (deltas from v4)

- **Standard checklist #21**: ✅ measurement anchor added; concrete and actionable.
- **Anti-pattern detection**: ✅ "Disproportionate section depth" added; connects the two existing partial anti-patterns into one balance discipline.
- **Advanced review techniques > Section weight audit**: ✅ new technique with full procedure. ⚠️ does not handle container sections or code blocks (concerns 1, 2).
- **Triage signal-driven additions**: ✅ visible imbalance → Section weight audit mapping added.

## Stress-test results

- **Time-pressure**: ✅ Tier 1 reviewer gets the lighter checklist #21 check; full audit reserved for Tier 2+.
- **Smooth-reading doc with hidden imbalance**: ✅ this is exactly what the audit is designed to catch.
- **Doc with legitimate container sections**: ⚠️ false-positive surge (the v5 finding).
- **Doc that uses code blocks heavily** (e.g., API specs): ⚠️ awk-style counters get confused by `##` inside code; reviewer must use a doc-aware counter.

## Anti-patterns spotted (in the framework itself)

- **Section weight audit produces 4 heavy outliers in the framework** — but these are container sections, not bloat. The framework's own structure exposes the audit's gap. Honest.
- **Inputs section is a light outlier** — minor case for the audit; arguably an intentional design choice that should be explicitly justified.

## Cognitive biases and blind spots

- **Confirmation in technique design**: the new audit was designed without applying it to the framework first. Doing so immediately surfaces the container-section issue. A pre-test against the framework itself would have caught this before adding the technique. This is a small instance of the broader "external application gap" — even self-application catches things internal review missed.
- **Sunk cost (v5 revisit)**: continuing investment in self-iteration. The new technique adds genuine capability rather than polish, so this round earns its place better than v4 did. But the trajectory is still toward diminishing returns past some point.

## Asymmetric risks

- **False-positive fatigue in the audit** (new in v5): downside is reviewers dismissing a useful technique; upside is catching balance issues. Currently asymmetric on the downside because the container-section gap is unresolved.
- **Regression-by-polish**: lower than v4 because this round added capability, not just refined existing.
- **External application gap**: persists. Largest unaddressed risk for any future iteration.

## What is done well

- **Three-layer reinforcement implemented cleanly**: checklist #21 measurement anchor + anti-pattern + dedicated technique + signal-driven routing. Exactly the layered defense pattern the framework uses for other high-stakes concerns.
- **The new technique self-validated**: applying it to the framework immediately produced a concrete finding (the container-section issue). The discipline works.
- **Honest about the discovered gap**: the v5 review surfaces the limitation of the just-added technique rather than hiding it. This is the framework's self-corrective discipline working as designed.
- **User-driven gap closure**: the framework absorbed a specific outside concern and integrated the fix without bloating other sections. The v5 framework grew by ~30 lines (from ~720 to ~750), and the additions are proportional to their importance.
- **Signal-driven routing works**: "Visible depth imbalance → Section weight audit" is the cleanest signal-to-technique mapping in the framework, because the signal is observable from a quick scan and the technique is the targeted response.
