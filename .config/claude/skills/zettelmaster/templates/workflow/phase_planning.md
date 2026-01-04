# Phase 2 – Atomization Planning (Workflow $WORKFLOW_ID)

Using the extraction results below, design the end-to-end atomization plan. Focus on grouping concepts into coherent zettels, TOCs, or hubs while preserving strict single-idea constraints.

```
$PAYLOAD
```

## Instructions
- Convert extracted concepts into planned deliverables:
  - `zettels`: atomic notes with title, target tags, and the source concepts that feed them.
  - `tocs`: tables of contents when a cluster has 3+ tightly-related zettels.
  - `hubs`: only when 2+ TOCs share a higher-level theme.
- Record explicit rationales for grouping/splitting decisions, including why certain concepts defer to existing zettels.
- Flag any concepts that appear redundant with the existing library (include suspected target IDs if visible in context).

## Required Output (TOON)
```
atomization_plan
  overview: [short narrative of the batch]
  zettels
    - id: plan-1
      title: [working title]
      tags:
        - domain/subdomain
      concepts:
        - [extracted concept key]
      notes: [constraints or open questions]
  tocs
    - title: [toc label]
      covers:
        - plan-1
        - plan-3
      rationale: [why these belong together]
  hubs
    - title: [hub name]
      connects:
        - [toc title]
      rationale: [why hub is needed]
  risks
    - [optional integration or dependency risk]
```

This plan becomes the contract for creation—be exhaustive and precise.*** End Patch
