---
consensus_engine: shadow
---

> **CANCELLED 2026-08-23** (operator decision, hold-triage session): the ephemeral-map
> reformulation retires audit-atlas entirely (survey stops storing atlases; see the
> retirement PRD filed the same day), so fixing its report.py is dead work. The findings
> below stay for the record; if audit-atlas ever returns, they still reproduce.

# audit-atlas report.py: two schema-guard bugs silently zero its headline metrics

Source: `00029-cartographer-evaluate-phase-4-6-reactivation-v1.md` Decision Trail and
`00114-cartographer-conformance-v1-deferred.md` Decision Log, both 2026-08-18 entries
(autopilot batch 202608180438 evaluation run). Confirmed independently by two reviewers
reading the live `~/.claude/skills/audit-atlas/scripts/report.py` against the real
on-disk schemas, and reconfirmed here by running the script directly.

## Overview

### Problem Statement

`report.py`'s two headline aggregates are each guarded by an `isinstance` check written
against a schema that does not exist on disk. Neither guard ever raises: each just makes
its metric read as zero, silently, on every run.

**Bug 1 — `active_fresh_pct` is always `n/a`.** `load_active_hashes` (lines 71-84) does:

```python
for entry in entries if isinstance(entries, list) else []:      # line 78
    ts = _parse_ts(entry.get("last_active"))                    # line 79
    ...
        active.add(str(entry.get("hash")))                      # line 83
```

The real `~/.claude/instincts/projects.json` is a **dict keyed by project hash**, each
value carrying a `last_seen` field — not a list of `{hash, last_active}` objects. Every
one of its 10 non-`global` entries (verified: `gems`, `engram`, `cli`, `agoge-gym`,
`klyreon`, `ddb`, `claude-plugins`, `clusters`, `home`, `zettelkasten`) is invisible to
this function. `isinstance(entries, list)` is always `False` against the real file, so
the loop body never runs and `load_active_hashes` always returns the empty set. Running
the script confirms it: `active repos: 0 (no instincts data); active_fresh_pct: n/a`,
even though the file plainly has 10 active, non-global entries.

**Bug 2 — layer population always reads `0/N (0%)`.** The loop in `main` (lines 144-151)
does:

```python
populated = sum(1 for v in layers.values()
                if isinstance(v, dict) and v.get("files"))       # lines 147-148
```

Every real `atlas.json` `layers` value is a **flat list of file path strings**, keyed by
layer name — never a `{"files": [...]}` dict. `isinstance(v, dict)` is always `False`
against the real shape, so `populated` is always `0` regardless of content. Verified
directly against `~/.claude/cartographer/projects/3f951e987a4f/atlas.json` (repo `ddb`):
its `layers` object has 11 keys (`ddb-server`, `ddb`, `tests`, `docs`, `examples`,
`ddb-cli`, `ddb-core`, `dev`, `ddb-uniffi-bindgen`, `reference`, `agent_docs`), every one
a non-empty list of real file paths (e.g. `ddb-server` alone lists 38 files). Running the
script against it prints `3f951e987a4f: 0/11 layers populated (0%) <-- under 80%` — for
an atlas that is, by inspection, 100% populated. All 7 atlases on disk show the same
`0/N (0%)` regardless of their real content.

**Both failures are silent.** Neither guard raises, logs, or exits non-zero on the real
schema — the script just prints a confidently wrong number (`n/a`, `0%`) and returns 0.
That silence is what makes them dangerous: nothing distinguishes "the aggregate is
genuinely zero" from "the aggregate could never be anything but zero." Any fix has to
remove that silence, not just correct the arithmetic underneath it.

**Both prior evaluations of the `00029` runbook survived only by working around the
bug.** The 2026-08-10 and 2026-08-18 evaluations both needed `active_fresh_pct` and
layer-population numbers to score `00114`'s Reactivation Criteria. Both hand-computed
the numbers directly from `instincts/projects.json` and each `atlas.json` instead of
trusting `report.py`'s own printed aggregate — because reading the aggregate at face
value gives `n/a` and `0%` on every repo, always, independent of the real data. Anyone
who trusts the script's printed output today, rather than re-deriving it by hand as both
of those evaluations did, gets misled.

### Target Users

Anyone running `audit-atlas` for real signal: the `00029` reactivation runbook (reads
`active_fresh_pct` and layer population to score Reactivation Criterion 1), and any
future `/audit-claude-config code-quality` sweep that includes `audit-atlas`.

### Success Metrics

- `active_fresh_pct` reflects the real `instincts/projects.json` dict-of-hash schema
  (key = hash, `last_seen` = timestamp), not the list schema the code currently assumes.
- Layer population reflects the real `atlas.json` `layers` schema (layer name -> flat
  list of file paths), not the `{"files": [...]}` dict schema the code currently assumes.
- A regression test exists per metric, each bound to a fixture built from the true
  on-disk schema, so the same class of mismatch cannot silently return the next time
  either schema moves.

## Functional Decomposition

### Capability: `active_fresh_pct` reads the real instincts schema

- **Description**: `load_active_hashes` must treat `instincts/projects.json` as a dict
  keyed by project hash, each value carrying `last_seen`, and skip the synthetic
  `global` key (it has no atlas to be "active" against).
- **Inputs**: `instincts/projects.json` (dict[str, dict]).
- **Outputs**: `set[str]` of hashes active within `ACTIVE_WINDOW_DAYS`.
- **Behavior**: iterate `entries.items()` when `entries` is a `dict`; parse `last_seen`
  (not `last_active`) per value; use the dict key (not a `"hash"` field) as the hash.
  Non-dict top-level JSON (missing file, malformed file) keeps returning the empty set,
  matching the module's existing "malformed input is counted, not fatal" contract.

Accepted option: fix the guard and field names in place (`isinstance(entries, dict)`,
`entries.items()`, `value.get("last_seen")`). The list-shaped branch it replaces never
matched any file that has existed on disk; there is nothing to keep dual-supporting.

Rejected alternative: keep both the old list-parsing branch and a new dict-parsing
branch, for schema tolerance. Rejected — the list shape is not a legacy format, it is a
shape nobody ever wrote; carrying it forward doubles the surface this function has to be
tested against for a schema that is confirmed dead.

### Capability: layer population reads the real atlas.json schema

- **Description**: the layer-population loop must treat each `layers` value as a flat
  list of file paths, not a `{"files": [...]}` dict.
- **Inputs**: `atlas.json` `layers` (dict[str, list[str]]).
- **Outputs**: `populated` / `total` counts per atlas.
- **Behavior**: `populated = sum(1 for v in layers.values() if isinstance(v, list) and v)`
  — a layer counts as populated when its value is a non-empty list.

Accepted option: fix the guard to match the real list shape, in `report.py` only.

Rejected alternative: normalize `atlas.json` layer values to `{"files": [...]}` at write
time instead (in whatever code produces `atlas.json`). Rejected — out of scope (that
writer is outside `report.py`, and `~/.claude/skills/` code changes beyond this file are
not what this PRD is chartered to do), and it would leave every `atlas.json` already on
disk unreadable by the *current* reader until each one is rewritten.

## Structural Decomposition

- `~/.claude/skills/audit-atlas/scripts/report.py` — `load_active_hashes` (lines 71-84);
  the layer-population loop inside `main` (lines 144-151).
- A regression test file for `report.py` (new; exact path and harness left to the
  implementer, following whatever test convention this repo already uses for skill
  scripts) — two fixtures: an `instincts/projects.json`-shaped dict fixture and an
  `atlas.json`-shaped `layers` fixture, each mirroring the real files inspected above,
  not a shape the old code happened to accept.

## Implementation Phases

### Phase 1: fix both guards with their regression tests

1. Fix `load_active_hashes` to iterate the real dict-of-hash shape and read `last_seen`.
2. Fix the layer-population loop to count non-empty lists instead of `{"files": [...]}`
   dicts.
3. Regression tests, each demonstrated failing against the current code first (bug-fix
   rule): one fixture-driven test asserting `active_fresh_pct` is computed (not `n/a`)
   against a dict-of-hash `instincts` fixture with a `last_seen` field; one asserting
   layer population counts a flat non-empty list as populated against an `atlas.json`
   fixture shaped like a real one.

*Acceptance:* running `report.py` against the real `~/.claude/instincts/projects.json`
and a real `atlas.json` (e.g. `3f951e987a4f`/ddb) prints a non-`n/a` `active_fresh_pct`
and a layer-population count that matches the atlas's real non-empty layer count, not
`0/N (0%)`.

## Test Strategy

Verbatim evidence, both reproduced against the live, unmodified script:

```
$ python3 ~/.claude/skills/audit-atlas/scripts/report.py
...
active repos: 0 (no instincts data); active_fresh_pct: n/a
...
  3f951e987a4f: 0/11 layers populated (0%) <-- under 80%
```

Ground truth against the same two files:

```
~/.claude/instincts/projects.json: 10 non-global entries, each carrying "last_seen"
  (e.g. "3f951e987a4f": {"name": "ddb", ..., "last_seen": "2026-08-17"})
~/.claude/cartographer/projects/3f951e987a4f/atlas.json: "layers" has 11 keys, every
  value a non-empty list of real file paths (e.g. "ddb-server": [...38 entries...])
```

The fix is verified when the script's own printed aggregate stops disagreeing with this
ground truth — not when the numbers merely change.

## Risks

- **Fixing the reader does not fix already-misread history.** Both `00029` decision
  trail entries (2026-08-10, 2026-08-18) that hand-computed these numbers stay correct;
  this PRD does not retroactively touch them.
- **A regression test bound to today's fixture can still drift if either schema moves
  again.** The test binds to the *shape*, not just today's values, which is the
  intended defense — but a third schema revision would still need its own fix.
- **Scope boundary**: this PRD touches only `report.py`'s two guards and its tests. It
  does not touch whatever code writes `instincts/projects.json` or `atlas.json`, and it
  does not re-run or re-score the `00029`/`00114` evaluations.
