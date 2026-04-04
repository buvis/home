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

## Troubleshooting Test Failures

1. Check test isolation - tests should not depend on each other
2. Verify mocks are correct
3. Fix implementation, not tests (unless tests are wrong)
