# Testing Requirements

## Tests exist to prevent regressions

Every new behavior and every bug fix ships with a test that would catch its
regression. That is the requirement. Ceremony beyond it is optional.

- Bug fix: write the regression test with the fix and watch it fail once
  against the old code. This is the one place fail-first is mandatory.
- New feature: cover the observable contract with the cheapest test that
  binds it (unit or integration, whichever encodes intent tighter).
- TDD is a technique, not a mandate. Reach for test-first when the contract
  is crisp or the logic is easy to get wrong. Skip the red-green ritual for
  glue code, config wiring, and one-liners.
- No blanket coverage target. Coverage is a lens for spotting untested
  logic, not a gate. Critical paths (money, auth, data loss) deserve
  near-full coverage; scaffolding does not.

## Tests Verify Intent, Not Just Behavior

Tests must encode **why** behavior matters, not just **what** the code does.

- A test that can't fail when business logic changes is wrong. Rewrite it to bind to the intent.
- Snapshot/golden tests are weakest here: they catch any change, including correct ones. Reserve them for output where shape itself is the contract.
- Name tests for the rule they enforce (`rejects_negative_quantity`), not the function they call (`test_validate`).

## Troubleshooting Test Failures

1. Check test isolation - tests should not depend on each other
2. Verify mocks are correct
3. Fix implementation, not tests (unless tests are wrong)
