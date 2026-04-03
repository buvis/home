---
name: check-python-compat
description: Check Python code for version compatibility issues targeting 3.10+. Triggers on "check python compat", "python version issues", "python 3.10 compatible", "does this work on 3.10".
---

# Check Python Version Compatibility

Reference for writing Python code that works across 3.10–3.12. Consult `references/compat-table.md` for the full list.

## Workflow

### 1. Determine target version

Check `pyproject.toml` for `requires-python`. If not specified, ask.

### 2. Scan for incompatible patterns

Review code against the compatibility table in `references/compat-table.md`. Focus on:

- **Imports** — modules that don't exist in target version
- **Syntax** — features unavailable in target version
- **Behavioral differences** — same code, different results
- **Typing** — annotations that fail at runtime on older versions

### 3. Report findings

For each issue found:
- What the code does
- Which version it requires
- What the fix is for the target version

## Quick reference — most common traps

| Trap | Requires | Fix for 3.10 |
|------|----------|-------------|
| `tomllib` | 3.11+ | `try: import tomllib except: import tomli` |
| `datetime.UTC` | 3.11+ | `datetime.timezone.utc` |
| `datetime.fromisoformat("...+0530")` | 3.11+ | `strptime` with `%z` |
| `isinstance(list[X], type)` returns False | 3.12+ | check `get_origin()` first |
| `Self` type | 3.11+ | `from __future__ import annotations` + `TypeVar` |
| `type X = ...` statement | 3.12+ | `TypeAlias` annotation |
| `ExceptionGroup` | 3.11+ | `exceptiongroup` backport |
| `TaskGroup` | 3.11+ | `taskgroup` backport or `anyio` |
| `f"{x:{"y"}}"` nested quotes | 3.12+ | avoid quote reuse in f-strings |
| `distutils` | removed 3.12 | `setuptools` |
| Pydantic locally-defined models | 3.10 | define models at module level |
