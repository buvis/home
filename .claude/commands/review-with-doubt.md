Before finalizing your work, perform a skeptical self-review. Assume your current solution is incomplete, flawed, or based on weak assumptions.

## Phase 1: Find doubts

Answer each question honestly. Do not defend earlier work. Silence on a question is not allowed - every question must produce at least one concrete doubt or an explicit "checked X, Y, Z and found nothing."

1. What parts of your solution are you least confident about?
2. What assumptions did you make, and which might be wrong? Check each assumption against the actual code or docs.
3. Is the task fully complete? Re-read the original request and diff every requirement against what was delivered.
4. What could fail in practice - edge cases, integration issues, hidden constraints, race conditions, error paths?
5. In retrospect, would you approach anything differently? If not, justify why the current approach survived scrutiny.
6. What tests, checks, or validations are missing or incomplete?

If you found fewer than 3 doubts total, you are not looking hard enough. Go back and scrutinize more carefully.

## Phase 2: Classify each doubt

For every doubt surfaced above, classify it:

| Category | Meaning | Required action |
|----------|---------|-----------------|
| **FIX** | Can be resolved now with reasonable effort | Fix it immediately before proceeding |
| **VERIFY** | Uncertain whether it's actually a problem | Run a test, read the code, or check the behavior to confirm or dismiss |
| **KNOWN** | Real limitation that genuinely cannot be fixed in this scope | Document it explicitly with a clear reason why it's out of scope |

Rules:
- Default to FIX. The burden of proof is on NOT fixing.
- "It's probably fine" is not a classification. Prove it's fine (VERIFY) or fix it (FIX).
- KNOWN requires a concrete reason why fixing is impossible or out of scope. Inconvenience is not a reason.
- Small doubts still get classified. A 2-minute fix is still a fix. Ignoring small issues is how bugs ship.

## Phase 3: Act on every doubt

Work through your classified list. No exceptions, no skipping.

1. **FIX items**: Make the changes now. Show what you changed.
2. **VERIFY items**: Run the actual check - execute a test, read the code path, reproduce the scenario. If the doubt is confirmed, reclassify as FIX and fix it. If dismissed, state exactly what you checked and what you observed.
3. **KNOWN items**: List them so the user can decide whether to accept or address them.

## Phase 4: Report

After acting on all items, report:
- Total doubts found
- Fixed (with summary of each change)
- Verified and dismissed (with evidence for each)
- Known limitations remaining (with justification for each)

Do not report a confidence score. Confidence is subjective and unreliable. The work speaks through the actions taken above.

## Iteration

If Phase 3 produced any FIX actions, run one more pass: return to Phase 1 and review the fixes themselves. New code can introduce new doubts.

Maximum 2 passes total. After the second pass, report any remaining doubts as KNOWN limitations and stop. Perfectionism is its own bug.
