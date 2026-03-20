# Python 3.10–3.12 Compatibility Table

## Added in 3.11 (unavailable on 3.10)

### New modules
| Module | Purpose | 3.10 alternative |
|--------|---------|-----------------|
| `tomllib` | TOML parsing | `tomli` (pip install) |
| `wsgiref.types` | WSGI type hints | define manually |

### New builtins/constants
| Feature | 3.10 alternative |
|---------|-----------------|
| `datetime.UTC` | `datetime.timezone.utc` |
| `ExceptionGroup` / `BaseExceptionGroup` | `exceptiongroup` backport |
| `except*` syntax | not available; use sequential except |
| `TaskGroup` (asyncio) | `anyio.create_task_group()` or backport |
| `asyncio.Runner` | `asyncio.run()` or manual loop |
| `asyncio.Barrier` | `anyio` or manual |

### datetime behavior changes
| Feature | 3.10 behavior | 3.11+ behavior |
|---------|--------------|----------------|
| `fromisoformat()` | rejects many ISO 8601 formats | accepts most ISO 8601 |
| `fromisoformat("...+0530")` | raises ValueError (no colon) | works |
| **Fix**: use `strptime(s, "%Y-%m-%dT%H:%M:%S%z")` on 3.10 |

### Typing additions
| Feature | 3.10 alternative |
|---------|-----------------|
| `Self` (PEP 673) | `TypeVar('T', bound='ClassName')` |
| `LiteralString` (PEP 675) | not available |
| `TypeVarTuple` (PEP 646) | `typing_extensions` |
| `Required`/`NotRequired` (PEP 655) | `typing_extensions` |
| `@dataclass_transform()` (PEP 681) | `typing_extensions` |

### Behavioral differences
| Behavior | 3.10 | 3.11+ |
|----------|------|-------|
| Context manager without protocol | `AttributeError` | `TypeError` |
| `int("1"*5000)` | works | `ValueError` (4300 digit limit) |
| `math.pow(0.0, -inf)` | `ValueError` | returns `inf` |
| Flag enum composites | canonical values | treated as aliases |

## Added in 3.12 (unavailable on 3.10, 3.11)

### New syntax
| Feature | 3.10/3.11 alternative |
|---------|----------------------|
| `type X = int` (PEP 695) | `X: TypeAlias = int` |
| `def foo[T](x: T)` (PEP 695) | explicit `TypeVar` |
| `class Foo[T]:` (PEP 695) | explicit `TypeVar` + `Generic[T]` |
| f-string quote reuse: `f"{','.join(x)}"` | use different quotes or variables |
| f-string backslashes: `f"{'\n'.join(x)}"` | assign to variable first |
| f-string nesting: `f"{f"{x}"}"` | avoid nesting |
| f-string comments in multiline | not allowed |

### Removed modules (existed in 3.10/3.11, gone in 3.12)
| Module | Alternative |
|--------|------------|
| `distutils` | `setuptools` |
| `asynchat` | `asyncio` |
| `asyncore` | `asyncio` |
| `imp` | `importlib` |
| `smtpd` | `aiosmtpd` |
| `lib2to3` / `2to3` | manual migration |

### Deprecated in 3.12 (still works but warns)
| Feature | Alternative |
|---------|------------|
| `datetime.utcnow()` | `datetime.now(tz=UTC)` |
| `datetime.utcfromtimestamp()` | `datetime.fromtimestamp(tz=UTC)` |
| `typing.Hashable` | `collections.abc.Hashable` |
| `typing.Sized` | `collections.abc.Sized` |
| `typing.ByteString` | `bytes \| bytearray` |
| `sys.last_type/value/traceback` | `sys.last_exc` |
| `calendar.January/February` | `calendar.JANUARY/FEBRUARY` |
| `~True` (bitwise invert bool) | `not True` |
| `gen.throw(typ, val, tb)` 3-arg | `gen.throw(exception)` |
| `shutil.rmtree(onerror=...)` | `shutil.rmtree(onexc=...)` |
| `tarfile.extract()` without filter | specify `filter='data'` |

### Behavioral differences
| Behavior | 3.10/3.11 | 3.12 |
|----------|-----------|------|
| `isinstance(list[int], type)` | `True` | `False` |
| `isinstance()` with runtime protocols | calls `hasattr`/descriptors | uses `getattr_static` |
| Comprehension in traceback | separate frame | inlined |
| `locals()` in comprehension | only comprehension vars | includes outer scope |
| `__set_name__` exception | wrapped in `RuntimeError` | propagates directly |
| Invalid escape `"\d"` | `DeprecationWarning` | `SyntaxWarning` |

### Pydantic-specific (3.10)
| Issue | Details |
|-------|---------|
| Locally-defined models | Pydantic can't resolve forward refs for models defined inside functions on 3.10. Define at module level. |
| `list[X]` as type | `isinstance(list[X], type)` differs across versions. Always use `get_origin()` to check parameterized generics. |

## Modules deprecated in 3.11, removed in 3.13
These work on 3.11/3.12 but emit warnings:
`aifc`, `audioop`, `cgi`, `cgitb`, `chunk`, `crypt`, `imghdr`, `mailcap`, `msilib`, `nis`, `nntplib`, `ossaudiodev`, `pipes`, `sndhdr`, `spwd`, `sunau`, `telnetlib`, `uu`, `xdrlib`

## Safe patterns across 3.10–3.12

```python
# TOML parsing
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

# UTC timezone
from datetime import timezone
UTC = timezone.utc  # works everywhere

# ISO format parsing
from datetime import datetime
def parse_iso(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")

# Type checking parameterized generics
from typing import get_origin
def is_generic(tp) -> bool:
    return get_origin(tp) is not None

# Self type (with future annotations)
from __future__ import annotations
from typing import TypeVar
T = TypeVar('T', bound='MyClass')
class MyClass:
    def method(self: T) -> T: ...
```
