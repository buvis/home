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

Each source maps to a `<PHASE>` label in the entry heading: `autonomous`, `deferred`, `planning`, `doubt`.

## Header

Created once on first write. Format:

```markdown
# Decision Audit Log: <prd-base>

PRD: `<prd filename>`
Started: <ISO 8601 timestamp>
```

At Phase 9, refresh the header by replacing the `Started:` line with a summary block:

```markdown
# Decision Audit Log: <prd-base>

PRD: `<prd filename>`
Started: <ISO 8601 timestamp>
Completed: <ISO 8601 timestamp>
Autonomous: <N>  |  Deferred: <N>  |  Doubts: <N>
```

Keep the counts consistent with the batch report's completion summary (see `references/batch-report-format.md` Phase 9 per-PRD section).

## Handoff Safety

Because the path is derived from the PRD base name and every write reads then appends, a fresh session continues the same file automatically. No session-specific state is needed to locate or extend the file.

## Relationship to state.json

`state.json` remains the operational source of truth. The audit log is the durable, human-readable mirror.
