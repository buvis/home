# Audit Log Format

File: `dev/local/reviews/<prd-base>-audit.md` (`<prd-base>` = PRD filename
without `.md`). The path is derived purely from the PRD base name, so every
session resolves the identical file with no session-specific state.

## Rendering (mechanic — lives in the CLI)

`autopilot render audit` (cli/render_audit.py, PRD 00107) renders the whole
file ONCE from the `state.json` decision arrays and is the ONLY writer:
header (PRD, `Started:`/`Completed:` stamps, counts line), then one
`### [<label>] <timestamp>` entry per item. A re-render preserves the
existing file's `Started:` stamp; when all three arrays are empty it writes
the header plus `no decisions recorded`. Entry field mapping and the exact
layout are pinned by `cli/golden/expected/audit.md`.

## Decision Sources

Three state arrays produce entries, each with a fixed `<PHASE>` label:

- `state.autonomous_decisions[]` → `autonomous` (includes loop-mode
  `assumed-ambiguity` records)
- `state.deferred_decisions[]` → `deferred`
- `state.doubts[]` → `doubt`

The label is **always** the source category, never the emitting phase or
cycle — the closed label set is what lets the decisions.md projection filter
autonomous entries by label. Per-phase/per-cycle context belongs in the
entry body, which means a decision worth auditing must be recorded in its
state array — a Phase 2 planning clarification is written to
`autonomous_decisions` (type `clarification` or `assumed-ambiguity`) at the
PAUSE site, or it never reaches the audit log.

## decisions.md Projection (judgment — stays with the model)

Invoked by `references/phase-done.md` Phase 9 step 7b, and only when
`dev/local/meta/decisions.md` exists (an opt-in global table; when absent, skip —
`audit.md` is still written). `audit.md` is the **single source of truth**
for decision narrative; `decisions.md` is a grep-friendly projection of it.

Read this PRD's `audit.md`, filter to non-trivial autonomous entries, and
append one row per entry:

```
| {YYYY-MM-DD} | {decision summary} | {rationale or research evidence} | batch-{batch_id} PRD {prd-number} |
```

An entry qualifies when BOTH hold: (a) its label is `autonomous`; and (b) it
is non-trivial — a non-empty **Rationale** AND a **Choice** that is an actual
decision or action, not a status note ("logged", "noted", "no action
needed" skip; "Adopt library X over Y" includes). Judging non-triviality is
the model's call; that is why this step is prose. Dedupe: grep the decision
summary against `decisions.md` before appending; skip if present.

## Relationship to state.json

`state.json` remains the operational source of truth; decisions are NOT
mirrored to `audit.md` incrementally. The audit log is the durable,
human-readable render of it, produced at Phase 9 finalize.
