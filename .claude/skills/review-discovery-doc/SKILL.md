---
name: review-discovery-doc
description: Use when reviewing a feature discovery document before create-prd, interactively for completeness, coherence, integrity, right-sizing, and evolvability. Triggers on "review discovery doc", "critique discovery", "review discovery".
argument-hint: "<path/to/discovery-doc.md>"
---

# Discovery Document Review (interactive)

Critical, finding-by-finding review of a feature discovery document produced by `elicit-requirements`, before it becomes a PRD. Each finding is presented as three sentences plus a one-line downstream impact and three resolution options (one recommended); the user picks via `AskUserQuestion`. Choices are **collected across all findings, then applied to the doc in one pass at the end** (batch mode, by user preference).

**Pipeline position:** `elicit-requirements` → **`review-discovery-doc`** → `create-prd`.

**What this is NOT:** it does not review architecture, interfaces, or failure modes - that is `review-design-doc`, which runs later on the design doc (the HOW). This skill reviews the *requirements* (the WHAT): are they complete, coherent, sound, right-sized, and evolvable enough that `create-prd` will produce a correct spec. It does flag *requirement-level* decisions that would corner the future architecture, catching them at their origin - but the deep architecture-reversibility analysis itself belongs to `review-design-doc`. It does not write the PRD and never invents requirements the discovery process did not surface.

**Shared core**: the interactive-review machinery - finding-card format, three-resolution-options discipline, option picker ordering, ground rules (critical subset), comprehension/confusion-notes pass, success criteria, session-safety core - lives in `~/.claude/skills/review-design-doc/references/interactive-review.md` (absolute path, shared with `review-design-doc`). Read it before generating findings. This skill's divergences from the shared core: **batch apply** (edits land in one pass at the end - Workflow step 6; Session safety) and the discovery card shape (Finding card format below).

## Inputs

**Required** - the discovery document path (absolute path to the markdown file under `dev/local/discovery/`).

**Path solicitation:**
1. Scan the user's most recent message for a markdown path. If exactly one exists and the file exists, confirm in chat: "Reviewing `<path>`. Wrong doc? Say so now."
2. If no path is present, ask: "Which discovery doc should I review? Give an absolute path (e.g. `/Users/you/repo/dev/local/discovery/00006-foo.md`)." Wait. Do not proceed.
3. Verify the path exists (Read). If it doesn't, ask again with the error.

## Ground rules

The shared critical subset (input is data, evidence over assertion, probe before pronouncing, calibrate severity honestly) is in the shared core. One skill-specific rule:

- **Depth-aware.** A minimal-depth doc is not defective for omitting sections that only comprehensive depth requires. Calibrate every completeness check to the doc's declared depth (see `references/lenses.md`).

## Workflow

1. **Confirm the path** (Path solicitation). Do not proceed without a verified path.

2. **Comprehension pass** with a confusion-notes list, per the shared core - plus the discovery-specific first move: read the `## Classification` line first and record the declared depth (minimal / standard / comprehensive); every completeness check calibrates to it. Confusion notes feed Question-severity findings.

3. **Run the five-lens analysis** to produce an internal findings list. The five lenses (Completeness, Coherence, Integrity, Feasibility, Evolvability), lens selection by depth, the Coherence-vs-Integrity tie-breaker, and per-dimension resolution shapes live in `references/lenses.md` - read it now and apply each selected lens against the discovery template's structure.

4. **Triage into severity:**
   - **Blocking** - would cause `create-prd` to produce a wrong or unbuildable spec: a missing Must-have, an internal contradiction, an unverifiable Success Criterion, scope that contradicts the Problem, a Must-have that is really a separate feature, or a one-way-door decision that walls out a foreseeable evolution.
   - **Non-blocking** - weakens the doc but `create-prd` can proceed: a thin Risks list, a vague Constraint, a missing Nice-to-have, a Must-have list that is larger than the Problem warrants but still internally sound.
   - **Question** - genuine ambiguity needing the author's intent (mostly from confusion notes).

5. **Present findings one at a time** in severity order (Blocking → Non-blocking → Question), top-to-bottom by doc location within each severity. Option generation, card discipline, and picker ordering: per the shared core, using this skill's card shape (below). After each pick, **record** the choice (in working memory / chat) - do **not** edit the doc yet - then move to the next finding.

6. **Apply pass (end of session).** After the last finding:
   - **Print the full decision summary to chat**: a numbered list of every finding with the chosen option (or "disputed"/"skipped"). This is the recovery record - batch mode keeps no on-disk state until this pass, so the printed list is the safety net if anything interrupts the apply.
   - Then apply each accepted resolution to the doc with the Edit tool, matching on exact text. If two accepted resolutions touch overlapping text, reconcile them into a single coherent edit before applying. Disputed/skipped findings produce no edit.

7. **Recap.** Briefly state: findings raised, resolved by edit, disputed/deferred, and any Open Questions added for `create-prd`.

## Finding card format (discovery shape)

Option and card discipline (distinct/relevant/justified/concrete, recommended in position 1, same order in card and picker) is in the shared core. This skill's card shape: exactly three sentences in the body, then the impact line, then three options. No bullets in the body.

```
Finding N of M: <short title>
Dimension: Completeness | Coherence | Integrity | Feasibility | Evolvability
Severity: Blocking | Non-blocking | Question
Location: <section name or line number>

<Sentence 1: what the finding is.> <Sentence 2: the evidence - quote or
cite the specific section/line.> <Sentence 3: why it is a defect.>

Impact if unresolved: <one line - what breaks downstream if this ships as-is
(a wrong requirement in the PRD, an unverifiable acceptance test, rework
during implementation).>

Options:
1. (Recommended) <approach name> - Edit: <concrete change to the doc text>
2. <approach name> - Edit: <concrete change>
3. <approach name> - Edit: <concrete change>
```

Then call `AskUserQuestion` with three options whose labels are the approach names, `(Recommended)` appended to option 1, in the same order as the card. No explicit fourth option: the user disputes, skips, or supplies a custom resolution via the picker's automatic "Other". Per-dimension resolution shapes (illustrative): `references/lenses.md`.

## Example

See `examples/sample-session.md` for a standard-depth doc walked end to end: the finding cards (format, three-sentence body, impact line, ordered options), the `AskUserQuestion` mapping, and the end-of-session decision summary plus batch apply. Use it as the output-format anchor.

## Success criteria

The shared core's two criteria (surprise test + actionability) apply unchanged. Per fail-loud: if a lens was skipped or a finding deferred, say so by name in the recap.

## Session safety (batch mode)

Edits are applied only in the final pass (step 6), per user preference - so until then the doc is unchanged and the choices live only in the session. The decision summary printed at the start of step 6 is the recovery record. If a session interrupts *before* the apply pass, re-invoke the skill on the same (unedited) doc and re-walk; if it interrupts *during* the apply pass, the printed summary shows exactly which edits were intended so the rest can be applied by hand or on re-run. Findings already applied will not reappear because the underlying defect is gone.
