# Phase 5 – Integration & Gap Analysis (Workflow $WORKFLOW_ID)

Compare the newly organized batch against the existing library sample plus prior-phase outputs. Decide what to keep, merge, or enhance.

```
$PAYLOAD
```

## Instructions
- For every new zettel, classify it as:
  - `new`: no overlap with existing material.
  - `duplicate`: already exists (reference existing ID).
  - `enhance`: append to an existing zettel (describe plan).
- Recommend relations that should be added before finalization (broader/narrower, develops, supports, etc.).
- Highlight orphans (too few relations) and over-linked notes ( >8 relations) with guidance.
- Suggest additional research only when a blocker cannot be resolved with current material.

## Required Output (TOON)
```
integration_review
  decisions
    - zettel: [[zettel/ID-or-plan-id]]
      status: new|duplicate|enhance
      action: [description or target id]
      reason: [short justification]
  relation_recommendations
    - from: [[zettel/ID]]
      type: broader-than
      to: [[zettel/ID]]
      confidence: high|medium|low
      rationale: [evidence]
  research_requests
    - priority: high|medium|low
      query: [what to investigate]
```

Keep reasoning tight—this output becomes the checklist for the final validation phase.*** End Patch
