# A truncated metrics line eats the next row, and cost rows mean the opposite of what they look like

Source: agoge product-QA run, `dev/local/audit-results/agoge-2026-08-17.md`, findings 19 and 20
(both MEDIUM), accepted as one cluster in the 2026-08-17 walkthrough. Found by heidi against the
real hooks.

## Overview

### Problem Statement

**Truncation spreads.** `track_cost.py` and `track_skills.py` each append a JSONL row without
checking the file ends in a newline. A crash-truncated last line therefore gets the next row
glued onto it, and both are lost. `track_skills.py` is worse: one truncated row made the whole
file unparseable, and its `_already_recorded` dedup — which skips unparseable lines — then
re-appended an invocation it had already recorded.

**Cost rows are cumulative, and nothing says so.** Each row restates the session's running total
rather than an increment. Summing them, which is the obvious thing to do, overstates spend: three
real stops for one session id gave 0.0015, 0.00225, 0.003 — naive sum 0.00675 against correct
max 0.003, a 2.25x overstatement on three rows. Memory
`reference_cache_read_dominates_spend.md` records a real **4.5x** overstatement for August from
exactly this mistake. Neither the module docstring ("appends a single JSONL row") nor
`metrics/PRICING-NOTE.md` states the semantics, and there is no in-repo reader to enforce them.

Left alone: metrics you cannot trust, corrupting quietly, with the one rule that makes them
readable living only in a memory file — one forgotten session from being rediscovered the
expensive way.

### Target Users

Anyone analysing spend or skill usage, including future sessions doing cost triage.

### Success Metrics

- Appending to a metrics file whose last line lacks a trailing newline leaves **both** rows
  parseable.
- `track_skills`' dedup does not re-append an invocation because of an unparseable neighbour.
- Every cost row carries a field marking it cumulative, and both the docstring and
  `PRICING-NOTE.md` state the max-by-`sid` rule.

## Functional Decomposition

### Capability: an append cannot corrupt its neighbour (finding 19)

Accepted option: seek to the end and write a leading `\n` when the file is non-empty and does not
end in one, in **both** writers. Self-healing on the next append.

Atomic rewrite was considered and rejected: it rewrites the whole file per append, which at
1.3 MB and one append per turn is a real cost, and it races parallel sessions.

### Capability: a reader cannot sum by mistake (finding 20)

Accepted option: emit `"cumulative": true` on each cost row **and** document the rule in both
places — `track_cost.py`'s docstring and `metrics/PRICING-NOTE.md`: rows are cumulative per
`sid`; aggregate with max-by-`sid`, never sum.

Writing increments instead was considered and rejected: a partial write or a missed stop would
lose that increment permanently, where today's totals are self-healing, and it would break every
existing analysis tuned to max-by-`sid`.

## Structural Decomposition

- `hooks/track_cost.py` — the append, the docstring, the new field
- `hooks/track_skills.py` — the append and `_already_recorded`
- `metrics/PRICING-NOTE.md` — the aggregation rule

## Implementation Phases

### Phase 1: both changes with their regression tests

1. Newline guard in both writers.
2. `"cumulative": true` on the cost row; the rule stated in the docstring and the note.
3. Regression tests below, each demonstrated failing first.

*Acceptance:* a file ending mid-row yields two parseable lines after one append, and the dedup
does not double-record.

## Test Strategy

Verbatim evidence — both are reproductions against the real hooks:

```
BEFORE: '{"ts": "t0", ...}\n{"ts": "t1", "sid": "sid-TRUNC", "cost_u'
hook rc= 0
AFTER:  '...{"ts": "t1", "sid": "sid-TRUNC", "cost_u{"ts":"...","sid":"sid-NEW",...}\n'
parseable lines: 1  unparseable: 1
(track_skills.py: parseable: 0 — whole file unparseable, and _already_recorded then
 re-appended an already-recorded invocation)
```

```
ROW {"sid": "sid-A", "in": 200, "out": 20, "cost_usd": 0.0015}
ROW {"sid": "sid-A", "in": 300, "out": 30, "cost_usd": 0.00225}
ROW {"sid": "sid-A", "in": 400, "out": 40, "cost_usd": 0.003}
naive SUM  = 0.00675
correct MAX = 0.003
```

## Risks

- **The newline guard contains the corruption, it does not repair it.** The truncated record stays
  permanently unparseable, so data lost to the original crash is still lost.
- **A `cumulative` flag still relies on a reader noticing a key they were not looking for.** Only
  writing increments makes the naive operation correct, and that trade was rejected deliberately.
- **The new field changes the row shape**, so a strict schema consumer would need to tolerate it.
  None was found in-repo.
- Both writers run at every session end, so a mistake here is paid every session.
