# Phase 4 – Organization Building (Workflow $WORKFLOW_ID)

Use the freshly created zettels below to design TOCs, hubs, and navigation aids. Emphasize abstraction: TOCs should read like ranked guides; hubs should describe domains, not specific implementations.

```
$PAYLOAD
```

## Instructions
- Group related zettels into TOCs when there is a natural progression, lifecycle, or taxonomy.
- Create hubs only when two or more TOCs need an umbrella explanation.
- Weave in relevant resource embeds (images, diagrams) when they materially aid navigation.
- Add cross-references between zettels/TOCs/hubs where helpful, but keep actual relation markup inside the reference sections of the target zettels.

## Required Output (TOON)
```
organization
  tocs
    - title: [toc name]
      description: [high-level overview]
      entries:
        - rank: 1
          zettel: [[zettel/ID]]
          note: [why it belongs here]
  hubs
    - title: [hub name]
      overview: [abstract domain description]
      sections:
        - label: [theme]
          links:
            - [[toc/title-or-zettel]]
  embeds
    - target: [toc or hub]
      resource: [[resources/...]]
      reason: [why the embed belongs]
```

Surface any structural risks (missing middle TOC, unclear hierarchy) under `organization.issues`.*** End Patch
