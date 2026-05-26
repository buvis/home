# Review Coverage Format

Every reviewer emits a machine-readable coverage block at the end of its output.
`review_coverage.py` parses these blocks to gate the review verdict. A consolidation
step merges per-reviewer blocks into a single aggregate block written to the review
file. Three surfaces use this format: `review-work-completion`, `review-blindly`,
and `run-autopilot` Phase 8 doubt-review.

The block is the sole source of truth for coverage. Prose summaries are not parsed.

## Block Delimiters

```text
---review-coverage---
...dimensions...
---end-review-coverage---
```

These exact strings open and close the block. No leading spaces. No trailing text on
the delimiter lines. Everything between them is parsed line by line.

## Dimensions

Each dimension is a named section inside the block. Sections appear in this fixed
order: `files`, `tests`, `features`, `rubric`. Each entry is one line:

```text
<key>: <value>
```

### files

Which diff paths were reviewed.

**Values:** `reviewed` or `n/a:<reason>`

- `reviewed` - the reviewer inspected this file and it is in scope.
- `n/a:<reason>` - the reviewer judges this file out of scope; `<reason>` is free
  text after the colon explaining why (e.g. `generated file`, `docs only`, `vendor`).

**Example:**

```text
files:
  src/review_coverage.py: reviewed
  src/review_coverage_hook.py: reviewed
  docs/adr-042.md: n/a:docs only, no code logic
```

### tests

Test command results: pass, fail, and skip counts.

**This dimension is NOT filled by individual reviewers.** Reviewers leave it empty
(or write the sentinel `pending: filled by consolidation`). The consolidation step
(or `review_coverage.py` on single-reviewer surfaces) runs the project test command
once and writes the actual counts. This prevents hearsay counts from different
reviewers disagreeing.

**Values:** one line per test command run, in the form:

```text
  <command>: pass=<N> fail=<N> skip=<N>
```

When the diff is docs-only and no test command applies, write the single line:

```text
  none: diff touches no code
```

**Example (aggregate only):**

```text
tests:
  pytest: pass=142 fail=0 skip=3
```

**Example (docs-only diff, aggregate):**

```text
tests:
  none: diff touches no code
```

### features

Which PRD features were verified.

**Values:** `verified` / `reviewed` / `failed`

- `verified` - feature was exercised end-to-end (tests ran against it).
- `reviewed` - feature was inspected in code but not exercised by a test run.
- `failed` - feature is missing, incomplete, or behaving incorrectly.

**Example:**

```text
features:
  coverage block parsing: verified
  aggregate block write: verified
  gate verdict on fail count: reviewed
```

### rubric

One verdict per rule ID from the surface's rubric (see `rubric.md`).

**Values:** `pass` / `fail`

A rule the reviewer cannot evaluate counts as `fail`; never omit the line.
Rule IDs are stable - new rules get new IDs; existing IDs are never renumbered.

**Example:**

```text
rubric:
  R1: pass
  R2: pass
  R3: fail
  R4: pass
```

## Per-Reviewer Block Example

Individual reviewers fill `files`, `features`, and `rubric`. They leave `tests`
empty (write only the dimension header, or the sentinel line). The parser expects
either an empty section or the sentinel `pending: filled by consolidation`.

```text
---review-coverage---
files:
  src/review_coverage.py: reviewed
  src/review_coverage_hook.py: reviewed
  docs/adr-042.md: n/a:docs only
tests:
  pending: filled by consolidation
features:
  coverage block parsing: verified
  aggregate block write: reviewed
  gate verdict on fail count: reviewed
rubric:
  R1: pass
  R2: pass
  R3: pass
  R4: pass
  R9: pass
  R10: pass
  R11: pass
  R12: pass
  R13: pass
---end-review-coverage---
```

## Aggregate Block Example

After consolidation (or direct-call on single-reviewer surfaces), `review_coverage.py`
writes one aggregate block into the review file. All four dimensions are filled.
This is the block the gate verdict reads.

```text
---review-coverage---
files:
  src/review_coverage.py: reviewed
  src/review_coverage_hook.py: reviewed
  docs/adr-042.md: n/a:docs only
tests:
  pytest: pass=142 fail=0 skip=3
features:
  coverage block parsing: verified
  aggregate block write: verified
  gate verdict on fail count: reviewed
rubric:
  R1: pass
  R2: pass
  R3: pass
  R4: pass
  R9: pass
  R10: pass
  R11: pass
  R12: pass
  R13: pass
---end-review-coverage---
```

## Why Python Parser, Not Bash

`consolidate-findings.sh` uses line-by-line string slicing tuned for the issue
format defined in `output-formats.md`. Extending it to parse a structured
multi-section block would make the script fragile and untestable. PRD 00038 (Risks
section) mandates a standalone `review_coverage.py` that fails loud on malformed
blocks - missing dimensions, unknown values, out-of-order sections - rather than
silently producing a wrong gate verdict. Bash string slicing cannot provide that
signal.

## Rule ID Stability

Rule IDs (`R{n}`) are stable per PRD 00037. Once assigned, an ID never changes
meaning and is never renumbered. Adding a new rule appends a new ID at the end of
the relevant group. This ensures coverage blocks in review files remain valid across
rubric updates - an old `R4: pass` is never silently reinterpreted as a new rule.
