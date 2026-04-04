---
name: python-testing
description: Use when writing or reviewing Python tests. Covers pytest, TDD workflow, fixtures, mocking, and parametrization. Triggers on "pytest", "python test", "test coverage", "TDD".
---

# Python Testing

pytest-based testing patterns following TDD methodology. Read relevant references based on the task.

## TDD Workflow

```
RED     → Write a failing test first
GREEN   → Write minimal code to pass the test
REFACTOR → Improve code while keeping tests green
REPEAT  → Continue with next requirement
```

## Coverage Target: 80%+

```bash
pytest --cov=mypackage --cov-report=term-missing --cov-report=html
```

## References

- `references/pytest-basics.md` - Test structure, assertions, exception testing, running tests
- `references/fixtures.md` - Basic, scopes, params, conftest, autouse
- `references/parametrize.md` - Parametrization, markers, test selection
- `references/mocking.md` - patch, return values, exceptions, autospec, properties
- `references/async-testing.md` - pytest-asyncio, async fixtures, async mocks
- `references/patterns.md` - Side effects, API testing, DB testing, test organization
- `references/configuration.md` - pytest.ini, pyproject.toml setup

## Quick Reference

| Pattern | Usage |
|---------|-------|
| `pytest.raises()` | Test expected exceptions |
| `@pytest.fixture()` | Create reusable test fixtures |
| `@pytest.mark.parametrize()` | Run tests with multiple inputs |
| `@pytest.mark.slow` | Mark slow tests |
| `@patch()` | Mock functions and classes |
| `tmp_path` fixture | Automatic temp directory |
| `pytest --cov` | Generate coverage report |
