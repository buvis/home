# Testing Requirements

## Coverage Target: 80%

Test types (all required where applicable):
1. **Unit tests** - individual functions, utilities, components
2. **Integration tests** - API endpoints, database operations
3. **E2E tests** - critical user flows

## Test-Driven Development

Mandatory workflow for new features and bug fixes:
1. Write test first (RED) - it should FAIL
2. Write minimal implementation (GREEN) - it should PASS
3. Refactor (IMPROVE) - clean up while green
4. Verify coverage (80%+)

## Tests Verify Intent, Not Just Behavior

Tests must encode **why** behavior matters, not just **what** the code does.

- A test that can't fail when business logic changes is wrong. Rewrite it to bind to the intent.
- Snapshot/golden tests are weakest here: they catch any change, including correct ones. Reserve them for output where shape itself is the contract.
- Name tests for the rule they enforce (`rejects_negative_quantity`), not the function they call (`test_validate`).

## Troubleshooting Test Failures

1. Check test isolation - tests should not depend on each other
2. Verify mocks are correct
3. Fix implementation, not tests (unless tests are wrong)
