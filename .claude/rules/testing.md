# Testing Requirements

Every new behavior and every bug fix ships with a test that would catch its
regression. Ceremony beyond that is optional.

- Bug fix: write the regression test with the fix, watch it fail once
  against the old code. This is the one place fail-first is mandatory.
- TDD is a technique, not a mandate.
- No blanket coverage target. Coverage is a lens for spotting untested
  logic, not a gate. Critical paths (money, auth, data loss) deserve
  near-full coverage; scaffolding does not.

Tests must bind to intent, not just behavior. A test that can't fail when
business logic changes is wrong. Name tests for the rule they enforce
(`rejects_negative_quantity`), not the function they call (`test_validate`).

Snapshot and golden tests catch any change, including correct ones. Reserve
them for output where shape itself is the contract.
