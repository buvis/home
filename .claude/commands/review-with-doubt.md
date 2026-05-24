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

## Phase 1.5: Slop check

Phase 1 catches correctness doubts — gaps, edge cases, broken assumptions. Phase 1.5 catches aesthetic and structural slop that passes every functional gate. A correct-but-bloated implementation still wastes the reader's time. Answer each question on your diff:

1. **Bloat ratio**: compare your diff size (net lines added) to the acceptance-criteria word count. If your diff is 5-10x larger than the spec suggests, name the bloat as a doubt — quote the specific module/function and how much smaller it should be.
2. **Defensive impossibility**: is any error handling, validation, or guard clause responding to a state that cannot occur from the current control flow? Name each one as a doubt (file:line + the impossible state).
3. **Single-caller abstraction**: is any helper, interface, factory, builder, or layer of indirection used from exactly one call site, with no current testability or architectural justification? Name each one (the abstraction's definition + the single caller).
4. **Comment paraphrasing**: do any comments restate the code on the next line instead of explaining why? Name each one (file:line). Multi-paragraph docstrings on trivial functions count.
5. **Framework-verification tests**: do any tests verify the language/library/framework rather than your code's behavior? Mock-confirming tests (only assertion is `mock.assert_called_with(...)`), existence checks, snapshot tests where shape is not the contract — name each.

If you found fewer than 2 slop items in a non-trivial change (>30 net lines, >1 file touched), you are not looking hard enough. Re-read the diff with the lens of "what would the most minimal correct version look like?" and try again.

Slop items flow through Phase 2 classification (FIX / VERIFY / KNOWN) and Phase 3 actions like any other doubt — no separate handling.

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
