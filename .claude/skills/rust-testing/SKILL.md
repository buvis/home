---
name: rust-testing
description: Use when writing or reviewing Rust tests. Covers unit, integration, async, property-based testing, mocking, and coverage. Triggers on "cargo test", "rust test", "#[test]", "test coverage".
---

# Rust Testing

Rust testing patterns following TDD methodology. Read relevant references based on the task.

## TDD Workflow

```
RED     → Write a failing test (use todo!() as placeholder)
GREEN   → Write minimal code to pass the test
REFACTOR → Improve code while keeping tests green
REPEAT  → Continue with next requirement
```

## Coverage Target: 80%+

```bash
cargo llvm-cov --fail-under-lines 80
```

## References

- `references/unit-tests.md` - Module-level tests, assertions, error/panic testing
- `references/integration-async.md` - Integration test structure, tokio::test, timeouts
- `references/parameterized.md` - rstest, fixtures, test helpers
- `references/property-mocking.md` - proptest, custom strategies, mockall
- `references/doc-tests-coverage.md` - Doc tests, cargo-llvm-cov, CI integration
- `references/benchmarking.md` - Criterion setup and usage

## Best Practices

**DO:** Write tests first (TDD), use `#[cfg(test)]` modules, test behavior not implementation, use descriptive test names, prefer `assert_eq!` over `assert!`, keep tests independent.

**DON'T:** Use `#[should_panic]` when you can test `Result::is_err()`, mock everything, ignore flaky tests, use `sleep()` in tests, skip error path testing.
