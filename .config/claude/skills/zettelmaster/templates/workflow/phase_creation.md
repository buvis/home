# Phase 3 – Parallel Zettel Creation (Workflow $WORKFLOW_ID)

Produce finalized TOON zettel drafts for every planned deliverable below. Each output must be self-contained, paraphrased, and include interpretation—never copy source text verbatim.

```
$PAYLOAD
```

## Instructions
- Work through each planned zettel independently (parallelizable). Respect the specified tags and rationale.
- Body rules:
  - Start with `# Title`.
  - Explain the concept in your own words.
  - Include interpretation, implications, or evaluation—do not just restate a quote.
- Reference rules:
  - All source references must target archive paths or markdown links.
  - Relationships go only in the reference section using `+relation:: [[zettel/id]]`.
- Produce TOCs/Hubs inline if the plan requires them.

## Required Output (TOON)
```
zettel_batch
  zettels
    - id: [timestamp or placeholder]
      title: [...]
      tags:
        - domain/topic
      body: |
        [markdown body]
      references:
        source:: [[archive/...]]
      relations:
        +develops:: [[zettel/123]]
  issues
    - [optional blocker or clarification needed]
```

Return only high-quality drafts—flag anything that still feels ambiguous under `issues`.*** End Patch
