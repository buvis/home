# Audit Log Format

File: `dev/local/reviews/<prd-base>-audit.md`

The path is derived purely from the PRD base name so every autopilot session resolves the identical file. `<prd-base>` is the PRD filename without the `.md` extension.

**Example**: PRD `00040-prd-decision-audit-log-v1.md` -> base `00040-prd-decision-audit-log-v1` -> `dev/local/reviews/00040-prd-decision-audit-log-v1-audit.md`.

## Append Procedure

Writes are append-only: a fresh read of current content, then a write-back of the extended content (per the `dev/local/` Write-tool rule). A fresh session continues the existing file rather than starting a new one. If the file is absent at first write, it is created with a header.

Steps, in order:

1. Resolve the path from the PRD base name: `dev/local/reviews/<prd-base>-audit.md`.
2. Read current content (treat a missing file as empty).
3. If absent, start with the header (see Header below).
4. Append the new entry.
5. Write back the full extended content using the Write tool.

Never do a blind overwrite. Never use a shell redirect.

## Entry Template

```markdown
### [<PHASE>] <ISO 8601 timestamp>

**Decision**: <the decision point or question>

**Recommendation**: <the AI's recommendation>

**Choice**: <the chosen answer or action>

**Rationale**: <why this choice was made>
```

Example:

```markdown
### [planning] 2026-05-30T14:23:07Z

**Decision**: Should the parser validate UTF-8 at the boundary or inline?

**Recommendation**: Validate at the boundary - cheaper and catches errors early.

**Choice**: Validate at the boundary.

**Rationale**: The inline path adds overhead on every token; boundary validation catches the same errors with one check per input.
```

## Decision Sources

Four sources produce entries:

- `state.autonomous_decisions[]` - decisions the AI made without user input.
- `state.deferred_decisions[]` - decisions escalated to the user.
- `state.doubts[]` - findings from the doubt review.
- Planning clarifications - the Phase 2 PAUSE site, where `/plan-tasks` stops for a requirements question. This source has no `state.json` array of its own; the audit-append fires directly at the PAUSE site.

Each source maps to a `<PHASE>` label in the entry heading: `autonomous`, `deferred`, `planning`, `doubt`. This label is **always** the source category, regardless of which autopilot phase emitted the entry — a decision made during review cycle 2 still uses `autonomous` (not `review-cycle-2`), and a doubt-review finding still uses `doubt` (not `doubt-review`). Per-phase or per-cycle context belongs in the entry's **Decision** body text. Keeping the label a closed four-value set is what lets the Phase 9 `decisions.md` projection filter autonomous-source entries by `<PHASE>` label == `autonomous`.

## Header

Created once on first write. Format:

```markdown
# Decision Audit Log: <prd-base>

PRD: `<prd filename>`
Started: <ISO 8601 timestamp>
```

At Phase 9, refresh the header in place: **keep** the `Started:` line and **insert** a `Completed:` line plus a counts line immediately after it (do not delete `Started:`). The header goes from the two-line form above to:

```markdown
# Decision Audit Log: <prd-base>

PRD: `<prd filename>`
Started: <ISO 8601 timestamp>
Completed: <ISO 8601 timestamp>
Autonomous: <N>  |  Deferred: <N>  |  Doubts: <N>
```

This is the identical end state SKILL.md Phase 9 step 6a describes. Keep the counts consistent with the batch report's completion summary (see `references/batch-report-format.md` Phase 9 per-PRD section).

## Phase 9 Header Refresh Procedure

Invoked by SKILL.md Phase 9 step 6a. The counts come from state (`Autonomous = len(state.autonomous_decisions)`, `Deferred = len(state.deferred_decisions)`, `Doubts = len(state.doubts)`).

Read-then-Write; never blind-overwrite entries; never a shell redirect:

1. Read the audit file.
2. If it already exists, locate the header block (the lines from `# Decision Audit Log:` through the first blank line after `Started:`). Insert or replace `Completed:` and the counts line immediately after the `Started:` line:
   ```
   Completed: <ISO 8601 timestamp>
   Autonomous: <N>  |  Deferred: <N>  |  Doubts: <N>
   ```
   Leave everything below the header (all `###` entries) untouched.
3. Write the full content back using the Write tool.

**No-decisions edge case**: if no decisions were captured this run (all three counts are 0), the audit file may not exist yet. The contract is that "the audit file exists with a header and an explicit \"no decisions recorded\" rather than being absent or empty." Ensure the file exists: create it with the standard header (title, `PRD:` line, `Started:` line, `Completed:` line, and `Autonomous: 0  |  Deferred: 0  |  Doubts: 0`), then append a single line `no decisions recorded`. Use the Write tool. Because the file was never created during the run, no earlier `Started:` timestamp exists — use the current Phase 9 timestamp for BOTH `Started:` and `Completed:`.

## decisions.md Projection

Invoked by SKILL.md Phase 9 step 7b, and only when `dev/local/decisions.md` exists (it is an opt-in global table; when absent, the projection is skipped and `audit.md` is still written). `audit.md` is the **single source of truth** for any decision narrative; `decisions.md` is a grep-friendly projection of it, so the two cannot diverge (one writer, one source).

Procedure: read this PRD's `audit.md`, filter to non-trivial autonomous entries, and append one row per entry to `decisions.md` in this format:

```
| {YYYY-MM-DD} | {decision summary} | {rationale or research evidence} | batch-{batch_id} PRD {prd-number} |
```

An entry qualifies when BOTH hold: (a) its `<PHASE>` heading label is `autonomous`; and (b) it is non-trivial — it has a non-empty **Rationale** AND its **Choice** is an actual decision or action, not a pure status/bookkeeping note. Trivial (skip): Choice like "logged", "noted", "no action needed". Substantive (include): Choice like "Adopt library X over Y" backed by a reasoned Rationale. The criterion is parseable from the entry's `Choice`/`Rationale` fields alone.

Dedupe is preserved: grep the decision summary against `decisions.md` before appending; skip if already present.

## Handoff Safety

Because the path is derived from the PRD base name and every write reads then appends, a fresh session continues the same file automatically. No session-specific state is needed to locate or extend the file.

## Relationship to state.json

`state.json` remains the operational source of truth. The audit log is the durable, human-readable mirror.
