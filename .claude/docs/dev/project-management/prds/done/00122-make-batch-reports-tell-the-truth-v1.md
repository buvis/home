---
design: skip
catchup: skip
---

# Make autopilot batch reports report what the batch actually did

## Problem

`dev/local/autopilot/reports/202608162223-report.md` is the record of a batch that
ran 2 review cycles, took 6 autonomous decisions, seeded 7 tasks and cost $141.
Its own Batch Summary reads:

```
- PRDs completed: 1
- Total cycles: 0
- Autonomous decisions: 0
- Escalated decisions: 0
```

and its per-PRD line reads `Tasks: 0/0`. Every one of those numbers is wrong, none
of them is marked as missing, and the same report's own tables directly contradict
them two screens above. A record that quietly reports zero is worse than one that
reports nothing: the batch reads as trivial when it was the most expensive PRD of
the month.

Five distinct defects, each verified in the code:

1. **The summary counters can only ever be zero.** `state-schema.md:206` documents
   `batch.completed_prds` as `object[]` carrying `filename`, `cycles`,
   `autonomous_decisions`, `escalated_decisions`. `phase-done.md:18` says only
   "Append completed PRD to `batch.completed_prds`", so the model appends a bare
   string — `202608162223-state-final.json` holds
   `["00120-migrate-task-tracking-to-statectl-v1.md"]`. `schema.py:133` validates
   only that the field is a **list**, so the wrong shape passes.
   `render_report.batch_summary` then filters `isinstance(p, dict)`, gets an empty
   set, and sums to 0. Three layers each behave reasonably; the result is a
   silent zero.

2. **`Tasks: n/n` reads fields that are wiped before the report renders.**
   `render_report.prd_section` (`:284`) reads `state["tasks_completed"]` /
   `state["tasks_total"]`. `records.reset_prd_fields` sets both to 0 (and drops
   `tasks`) at the PRD transition, so the archived state shows `0`/`0` while the
   real task array had 7 entries. The `'?'` default never fires, because the keys
   are present and zero.

3. **`Started:` is stamped with the finish time.** `__main__.py:652` calls
   `render_report.header(batch_id, now)`. The report says
   `Started: 2026-08-16T22:30:10Z`, which is when the file was written; the batch
   began at 20:21:59Z. The same file's Duration line (`20:21:59Z to 22:29:16Z`,
   computed from real metrics rows) contradicts the header three sections later.

4. **The Deferred table's Reason column is structurally always empty.**
   `_deferred_to_batch_end` (`:126`) reads `d.get("reason")`; the deferred records
   carry `disposition`. All four rows in the live report have a blank Reason while
   the ledger JSON holds a full paragraph for each.

5. **`_autonomous` renders blank rows and blank columns.** It reads `cycle`,
   `issue`, `severity`, `reason` (`:78-96`); the decisions written in practice
   carry `action` and sometimes `cycle`. Two rows in the live report are entirely
   empty — a record of a decision with no content at all.

## Requirements

- **R1.** No report number is derived from live state that gets reset after the
  report is written.
- **R2.** A field the renderer cannot resolve prints as `?` or is omitted — never
  as `0` and never as a blank cell in a row that claims to be a record.
- **R3.** `batch.completed_prds` has one shape, enforced where it is written.
- **R4.** `Started:` is the batch's start.
- **R5.** A batch that ran cycles and decisions cannot render a report claiming
  zero of either — bind that as a test, not as care.

## Phases

### Phase 1 — one writer for the batch record

1. Add a statectl verb that appends the documented **object** to
   `batch.completed_prds` (filename, cycles, autonomous_decisions,
   escalated_decisions), computing the counts from the state it is closing rather
   than trusting a caller to pass them. Point `phase-done.md:18` at that verb
   instead of at prose. (R1, R3)
2. Extend `schema.py`'s `batch.completed_prds` check to validate element shape,
   so a bare string is a loud SchemaError at the next write. Decide explicitly
   whether legacy bare-string entries are migrated or tolerated-with-a-warning;
   `render_report`'s docstring currently calls them "live legacy state", and
   `status.py:28` and `tracon/model.py:334` both count the same list. (R3)

*Acceptance:* a batch that completes two PRDs renders non-zero cycle and decision
sums; the same state with a bare-string entry fails validation with a message
naming the field.

### Phase 2 — the renderer stops rendering zeros

3. `prd_section` derives task counts from the closing batch record (Phase 1) or
   from `len(state["tasks"])`, and prints `?` when neither is available. (R1, R2)
4. `header()` takes the batch start: the first metrics row's `ts_start` (the
   value `batch_summary` already computes for its Duration line) or `batch.id`,
   which is itself a `yyyymmddHHMM` stamp. Not `now`. (R4)
5. `_deferred_to_batch_end` reads `disposition`, falling back to `reason`. (R2)
6. `_autonomous` falls back across the keys decisions actually carry, and drops
   any row whose every cell is empty rather than printing a blank record. (R2)

*Acceptance:* rendering the archived `202608162223` state produces cycles 2,
decisions 6, tasks 7, a `Started:` of 20:21:59Z (min ts_start over the batch's
metrics rows, per R4), populated Reason cells and no blank
rows. Use that state as the fixture — it is the batch that exposed all five.

### Phase 3 — bind it

7. A test that renders a state with cycles and decisions and **fails if any
   summary counter is 0**. The existing golden files
   (`cli/golden/expected/report-summary.md`) pass today with the bug in place, so
   a golden alone is not the check. (R5)

## Remaining work — unparked 2026-08-23 after cap-park

**Phases 1-3 above are SHIPPED (grounded at HEAD `477560c9`, 2026-08-25) - plan-tasks must
not plan them.** Evidence: `complete-prd` verb `cli/statectl.py:346` (commits `0144503a`,
`4dbe58cc`, `3a5d55f4`) and `phase-done.md:18-19`; schema element validation
`cli/schema.py:102-131` with a deliberate tolerate-bare-strings-with-warning carve-out
(`7e85d7dd`, `cc046fcd`); `prd_section` `?/?` at `render_report.py:301-314`; `batch_started`
at `render_report.py:344-358` (`37e55084`, `96cb77b7`); `disposition` fallback
`render_report.py:148`; `_autonomous` row filter `render_report.py:99-111` (`6b46a262`);
non-zero binding test `cli/test_render.py:680-730` (`6f18896f`). Only the items below are open.

Cycle 2 of cap 2 (batch `202608180438`) did not converge. Most of the PRD shipped; do NOT
rebuild from scratch. Close only the open findings, full text in
`dev/local/reviews/00122-make-batch-reports-tell-the-truth-v1-review-2.md` and the batch
deferred ledger (`dev/local/autopilot/deferred/202608180438-deferred.json`):

1. **CRITICAL**: `batch_summary` still renders `0` not `?` for bare-string
   `batch.completed_prds` entries (reproduced live on batch 202608180438's own 00029 entry).
2. **HIGH**: the Phase 2 fixture `cli/golden/state-batch-202608162223.json` was hand-migrated
   to the fixed dict shape, so tests cannot catch the bare-string regression; restore the real
   archived shape.
3. **HIGH**: the Phase 3 binding test (`cli/test_render.py:745-759`) asserts the prohibited
   zeros as correct for bare-string entries; invert it.
4. **HIGH**: `complete-prd` counts `assumed-ambiguity` decisions that `_autonomous` excludes,
   so the summary counter can exceed the table.
5. **MEDIUM tail**: `do_complete_prd` 69 lines (`cli/statectl.py:346-414`, 30 of them
   docstring); stale `state-schema.md:208` (says `len(autonomous_decisions)`, code counts only
   renderable entries); `Started:` PRD number corrected to the code's derivation
   (`min(ts_start)` = 20:21:59Z); `read_text` without
   encoding at `scripts/test_statectl_complete_prd.py:36` and `:394`.
6. **Docstrings that bless the zero** (found by the 2026-08-25 grounding, not in the review):
   `cli/render_report.py:19-20` and `:366-368` describe bare-string entries as "count toward
   the PRD total only" - rewrite them with item 1 so the module does not document the defect
   as a feature.

## Out of scope

- The report's Loop Metrics and Implementor Mix sections; they read real metrics
  rows and were correct in the live report (the blank `launch phase` cell for the
  bootstrap row is cosmetic and stays).
- Any change to what the batch report *contains*. This PRD makes the existing
  fields true, it does not add fields.
