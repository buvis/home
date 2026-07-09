# Sample session: review-discovery-doc

A standard-depth discovery doc walked end to end. This anchors the output format: the finding card, the three-sentence body, the impact line, the ordered options, the `AskUserQuestion` mapping, and the end-of-session decision summary plus batch apply. It is illustrative, not a transcript to copy verbatim.

## The doc under review

`dev/local/discovery/00007-notification-digest.md` (excerpt):

```markdown
# Discovery: Notification Digest

## Classification
Depth: standard | Date: 2026-06-28

## Problem
Users get one email per event. The volume is overwhelming, so they mute
notifications entirely and then miss the ones that matter.

## Requirements
### Must have
- Batch events into a periodic digest email.
- Send the digest via SendGrid.
- Let users pick digest frequency: hourly, daily, or weekly.
- Group events by project and by type in the digest.
### Nice to have
- Per-project frequency overrides.
### Out of scope
- (none listed)

## Success Criteria
- Digest emails are well received by users.

## Risks
- A digest could itself become noisy if a project is very active.

## Open Questions
- Should muted projects still appear in the digest?

## Discovery Log
### Q1: How do users control volume today?
**Answer**: Only an all-or-nothing global mute.
```

Declared depth is **standard**, so all five lenses run as full passes.

## Findings, presented one at a time

Severity order: Blocking, then Non-blocking, then Question. Top-to-bottom by doc location within each severity. Choices are recorded, not applied yet.

---

```
Finding 1 of 3: Vendor named as a requirement
Dimension: Integrity
Severity: Blocking
Location: Requirements > Must have, bullet 2

This Must-have states "Send the digest via SendGrid", which is a HOW, not a
WHAT. The need is "deliver the digest by email"; SendGrid is one
implementation of it, and that choice belongs to design-solution. Pinning a
vendor at discovery both mis-states the requirement and bakes in a one-way
door (it also trips Evolvability, but the root defect is the requirement's
form, so it is filed under Integrity to avoid double-flagging).

Impact if unresolved: the PRD inherits a vendor lock-in as a hard
requirement, and switching providers later reads as a scope change rather
than an implementation detail.

Options:
1. (Recommended) State the need - Edit: replace bullet with "Deliver the
   digest by email."
2. Demote to Constraint - Edit: remove the bullet; add under Constraints
   "Email delivery uses SendGrid (existing account)" with a one-line reason.
3. Defer - Edit: remove the bullet; add under Open Questions "Which email
   provider? Decide in design."
```

`AskUserQuestion`: option 1 `State the need (Recommended)`, option 2 `Demote to Constraint`, option 3 `Defer`. ("Other" = dispute or custom.)

**Recorded:** option 1.

---

```
Finding 2 of 3: Success criterion is not measurable
Dimension: Integrity
Severity: Blocking
Location: Success Criteria, bullet 1

"Digest emails are well received by users" is not falsifiable - there is no
metric and no threshold. "Well received" cannot be tested, so no acceptance
check can be written against it. The Problem already names the real outcome:
fewer people mute notifications, which is measurable.

Impact if unresolved: create-prd has no acceptance bar, so the PRD ships with
an untestable success criterion and "done" becomes a matter of opinion.

Options:
1. (Recommended) Tie to the Problem metric - Edit: replace with "Global mute
   rate drops by at least 30% within 60 days of launch."
2. Use an engagement metric - Edit: replace with "Digest open rate is at
   least 40%."
3. Open question - Edit: replace with an Open Questions entry "What is the
   target mute-rate reduction? Set the number before PRD."
```

`AskUserQuestion`: option 1 `Tie to Problem metric (Recommended)`, option 2 `Engagement metric`, option 3 `Open question`.

**Recorded:** option 3 (user wants to set the number during create-prd).

---

```
Finding 3 of 3: Frequency is a closed list
Dimension: Evolvability
Severity: Non-blocking
Location: Requirements > Must have, bullet 3

Frequency is fixed to exactly hourly, daily, or weekly, yet the Nice-to-have
"per-project frequency overrides" signals that frequency will get more
flexible, not less. A hardcoded three-value enum has no seam for custom
schedules, so adding one later means reworking the data model rather than
extending it. This is an evidence-backed lock-in (the Nice-to-have is the
named, foreseeable evolution), not speculation.

Impact if unresolved: the override feature later forces a migration of every
stored frequency value, turning an additive change into a redesign.

Options:
1. (Recommended) Model as an open schedule - Edit: replace with "Let users
   set digest frequency from an extensible schedule (presets hourly, daily,
   weekly to start)."
2. Default plus path - Edit: append to the bullet "; store frequency as a
   value that can later accept custom schedules."
3. Force the seam in design - Edit: add under Open Questions "Will frequency
   need custom schedules? If so, design must avoid a fixed enum."
```

`AskUserQuestion`: option 1 `Open schedule (Recommended)`, option 2 `Default plus path`, option 3 `Force seam in design`.

**Recorded:** option 1.

## End of session: decision summary, then batch apply

Per batch mode, the summary is printed to chat first (the recovery record), then the edits are applied.

```
Decision summary (3 findings):
1. Vendor named as a requirement (Integrity, Blocking) -> option 1: state the need
2. Success criterion not measurable (Integrity, Blocking) -> option 3: open question
3. Frequency is a closed list (Evolvability, Non-blocking) -> option 1: open schedule
Disputed/skipped: none.
```

Then the Edit tool applies each accepted resolution, matching exact text:

- Bullet 2 of Must-have -> "Deliver the digest by email."
- Success Criteria bullet 1 -> removed; Open Questions gains "What is the target mute-rate reduction? Set the number before PRD."
- Bullet 3 of Must-have -> "Let users set digest frequency from an extensible schedule (presets hourly, daily, weekly to start)."

Two of these touch the Must-have list but different bullets, so no reconciliation is needed. If two accepted resolutions had edited the same bullet, they would be merged into one coherent edit before applying.

## Recap

3 findings raised (2 Blocking, 1 Non-blocking), all resolved by edit, none disputed. One Open Question added for create-prd (the mute-rate target). Surprise test met: the vendor-as-requirement lock-in was not on the author's radar. Empty Out-of-scope was noted but judged Non-blocking at standard depth and left for a later pass.
