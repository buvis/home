---
name: python-patterns
description: Use when writing, reviewing, or refactoring Python code. Triggers on Python file edits, "pythonic", "PEP 8", "python best practices", "python idioms".
---

# Python Patterns

Idiomatic Python patterns and best practices. Read relevant references based on the task.

## References

- `references/idioms.md` - Core idioms: EAFP, comprehensions, generators, context managers
- `references/type-hints.md` - Type annotations, Protocol, TypeVar, modern syntax (3.9+)
- `references/error-handling.md` - Exception hierarchy, chaining, specific catches
- `references/data-modeling.md` - Dataclasses, NamedTuple, __slots__, performance
- `references/concurrency.md` - Threading, multiprocessing, async/await
- `references/decorators.md` - Function, parameterized, and class-based decorators
- `references/project-structure.md` - Package layout, imports, pyproject.toml, tooling

## Quick Reference

| Idiom | Description |
|-------|-------------|
| EAFP | Try/except over if/else checks |
| Context managers | `with` for resource management |
| List comprehensions | For simple transformations |
| Generators | For lazy evaluation and large datasets |
| Type hints | Annotate function signatures |
| Dataclasses | For data containers with auto-generated methods |
| `__slots__` | For memory optimization |
| f-strings | For string formatting (3.6+) |
| `pathlib.Path` | For path operations (3.4+) |
| `enumerate` | For index-element pairs in loops |

## Anti-Patterns

```python
# Mutable default arguments
def bad(items=[]):  # shared across calls
def good(items=None):
    items = items if items is not None else []

# Bare except
try: ...
except: pass  # catches SystemExit, KeyboardInterrupt
# Fix: except SpecificError as e:

# Comparing to None with ==
if value == None:  # use: if value is None:

# from module import *  — use explicit imports

# type() instead of isinstance()
```
