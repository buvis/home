# Phase 1 – Concept Extraction (Workflow $WORKFLOW_ID)

Use the mechanical scan below to identify every concrete, atomic concept worth capturing as a zettel. Treat this as a zero-draft pass: your only job is to enumerate potential zettels, not to write them.

```
$PAYLOAD
```

## Instructions
- Aggressively discard marketing fluff and vague statements; only preserve verifiable facts, procedures, metrics, or definitions.
- Track source locations exactly as provided (archive-mapped paths, not inbox paths).
- Capture potential relationships or dependencies between extracted concepts when obvious.

## Required Output (TOON)
```
concept_extraction
  summary: [short description of what was scanned]
  concepts
    [stable-key]
      title: [concise working title]
      source: [[archive/...]] or [link](url)
      rationale: [single sentence why this belongs]
      related_to:
        - [other stable-key]
      notes: |
        [Optional factual scraps that justify extraction]
```

Keep the number of concepts unlimited—if the content contains 100 atomic ideas, list all 100.*** End Patch
