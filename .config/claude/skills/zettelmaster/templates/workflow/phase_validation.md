# Phase 6 – Validation & Write Instructions (Workflow $WORKFLOW_ID)

Perform the final QA pass on the proposed zettels using the integration summary and the drafted content below. Confirm structural compliance before we run the mechanical validator.

```
$PAYLOAD
```

## Instructions
- Check every zettel against structural rules:
  - YAML frontmatter complete (id, title, date, tags, type, publish, processed, synthetic).
  - Body starts with `# Title`, remains atomic, and avoids relationship lists.
  - References section uses `key:: value` for metadata and `+relation:: [[zettel/id]]` for semantics.
- Ensure all source references point to `archive/` paths (never `inbox/`).
- Verify each relation targets an existing or newly-created zettel ID; flag unresolved references.
- Summarize any blockers that require human action before writing to disk.

## Required Output (TOON)
```
validation
  ready
    - [[zettel/ID]]
  fixes_required
    - zettel: [[zettel/ID]]
      issues:
        - [description of violation]
      suggested_fix: [concise fix]
  blockers
    - [anything that must be resolved before file_manager write]
```

Mark only structurally sound zettels as `ready`. Others must list precise corrective actions.*** End Patch
