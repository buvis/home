# Rationalizations Catalog

Common excuses agents (and humans) use to skip discovery, reuse, and tests. Each entry: the excuse, why it's wrong, the counter-action, and its trigger terms. Echo's deny messages cite the first entry (file order) whose trigger substring-matches a duplicate symbol name; no match, no citation. Terms match as plain substrings, so keep them distinctive - a term like `fix` also fires inside `prefix`. An entry without a **Triggers** bullet is never auto-cited. Also surfaced in `/architect` planning prompts.

## Excuses

### "Quick fix, skip the map"

- **Why it's wrong**: speed without context creates parallel implementations of code that already exists. The "quick" fix becomes a long-term tax on every future reader.
- **Counter-action**: run `/survey` for a codebase brief before any edit. Wanting to skip it is the signal to slow down, not to skip.
- **Triggers**: quick, hotfix, workaround, stopgap

### "Couldn't find existing helper"

- **Why it's wrong**: most "couldn't find" is "didn't grep enough." Names diverge across codebases (`format_date`, `to_iso`, `serialize_date`, `date_str` all show up).
- **Counter-action**: name 2-3 plausible synonyms before writing new code, and grep each. For utilities, search the verb (`format`, `serialize`, `render`) and the noun (`date`, `timestamp`, `iso`). For types, search the domain term and its abbreviations. See **Synonyms-to-grep** below.
- **Triggers**: format, parse, validate, normalize, serialize, transform, decode, encode, stringify, render

### "Existing pattern is overkill"

- **Why it's wrong**: a parallel-implementation rationalization. Patterns feel heavy until you discover they encode invariants (error handling, ordering, retries) that the "lighter" version silently drops.
- **Counter-action**: use the existing pattern even if it feels heavy. If it's genuinely wrong for this case, open a refactor PRD and propose a replacement that updates every call site at once.
- **Triggers**: simple, lite, basic, mini, naive

### "I'll add tests later"

- **Why it's wrong**: later never arrives. The next session has different context, the bug surfaces in production, and the test that would have caught it never gets written.
- **Counter-action**: ship the regression test with the change (`rules/testing.md`); for bug fixes, watch it fail once against the old code. The test takes minutes; the regression it prevents takes hours.
- **Triggers**: test, fixture, mock, stub, fake

### "File is short, I'll just rewrite"

- **Why it's wrong**: short files often encode invariants in their structure (error messages other code matches against, exact return shapes consumers depend on, side effects in a specific order). A rewrite drops them silently.
- **Counter-action**: edit in place. If the file is genuinely wrong, open a refactor PRD with the diff plan. Never rewrite as a side effect of a feature task.
- **Triggers**: rewrite, v2, copy, clone

## Synonyms-to-grep

When you suspect a helper exists but the obvious name returns nothing, expand the search:

- **Verbs**: `format` ↔ `render` ↔ `serialize` ↔ `to_*` ↔ `as_*` ↔ `stringify`
- **Parsers**: `parse` ↔ `from_*` ↔ `decode` ↔ `load` ↔ `read`
- **Validators**: `validate` ↔ `check` ↔ `assert_*` ↔ `is_valid` ↔ `verify`
- **Builders**: `build` ↔ `create` ↔ `make` ↔ `new_*` ↔ `init`
- **Lookups**: `get` ↔ `find` ↔ `lookup` ↔ `resolve` ↔ `select`

Grep both the verb and the noun. If neither hits, grep the verb alone (utilities are sometimes named purely by action).

If after this you still find nothing, the helper genuinely doesn't exist; write it once, in the layer where its consumers live.
