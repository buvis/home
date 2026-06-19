# Code Quality Examples

Before/after examples of the anti-patterns the four rules in
`code-quality-principles.md` prevent. Referenced from `/work` steps 2.5 and 3.

## 1. Hidden assumptions worth surfacing

A "hidden assumption" is any point where the task description leaves a real
choice and the implementor would have to pick silently. When the main session
spots one at step 2.5, or Ivan spots one at dispatch time, the task is
ambiguous - stop and ask the user rather than guessing.

What counts:

- **Data shape unstated** - task says "store the result" but not as what:
  a string, a struct, a row, a cache entry.
- **Target surface unclear** - "add a flag" without saying CLI, config file,
  or env var.
- **Success criteria fuzzy** - "make it faster" with no threshold or baseline.
- **Format or location unspecified** - "write a report" without path or format.
- **Edge behavior undefined** - what happens on empty input, on conflict, on
  the second call.

What does NOT count (decide silently, per the "simplest safe assumption" rule):

- Naming of a private local variable.
- Which of two equivalent stdlib calls to use.
- Ordering of independent statements.

### Example 1 - ambiguous task description

**Task:** "Add caching to the exchange-rate lookup."

This is ambiguous on at least three axes:

- **Cache key** - per currency pair, or the whole rate table?
- **Invalidation** - TTL, manual, or never?
- **Storage** - in-process map, or the existing Redis layer?

Each choice produces a different implementation, different tests, and
different operational behavior. Ivan cannot pick correctly by reading code.

**Wrong:** dispatch Ivan with the task as-is. Ivan picks an in-process map
with a 60s TTL because that is the common default - and the reviewer later
flags it because the project standard is Redis-backed caching.

**Right:** at step 2.5, stop and ask the user: "Cache key per currency pair or
whole table? TTL or manual invalidation? In-process or the existing Redis
layer?" Dispatch Ivan only once the answers are in the task.

## 2. Speculative abstraction (Simplicity)

**Before** - a generic registry for one caller:

```python
class RateProviderRegistry:
    def __init__(self):
        self._providers = {}

    def register(self, name, provider):
        self._providers[name] = provider

    def get(self, name):
        return self._providers[name]

registry = RateProviderRegistry()
registry.register("ecb", EcbProvider())
rate = registry.get("ecb").fetch(pair)
```

**After** - the task has one provider; use it:

```python
rate = EcbProvider().fetch(pair)
```

The registry earns its place when a second provider exists and selection is
dynamic. Until then it is indirection with no payoff.

## 3. Drive-by refactoring (Surgical)

**Task:** fix a null-pointer bug in `parse_amount`.

**Wrong diff:** the bug fix, plus reformatting the whole file, renaming three
unrelated variables, and "tidying" an adjacent function. The reviewer now has
to separate the fix from the noise, and any of the unrelated edits could
regress.

**Right diff:** the two lines that fix the null check. If the adjacent
function genuinely needs work, mention it in the task output - do not fold it
into this diff.

## 4. Style drift (Goal-driven)

**Before** - the surrounding file uses `snake_case` and early returns:

```python
def find_user(user_id):
    if not user_id:
        return None
    return db.get(user_id)
```

**Wrong addition** - new function in the same file, different style:

```python
def findUserByEmail(emailAddress):
    result = None
    if emailAddress:
        result = db.getByEmail(emailAddress)
    return result
```

**Right addition** - match the file:

```python
def find_user_by_email(email):
    if not email:
        return None
    return db.get_by_email(email)
```
