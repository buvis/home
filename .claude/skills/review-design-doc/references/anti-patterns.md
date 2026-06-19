# Anti-pattern detection


Flag any of these explicitly when you see them:

- Vague qualifiers without numbers: "highly available", "scalable", "secure", "fast", "robust", "performant"
- Tech name-dropping (Kafka, Kubernetes, gRPC, blockchain, AI) without trade-off justification
- "We will add observability later", "we will harden security later", "we will write tests later": load-bearing concerns deferred
- Reasoning by analogy ("Netflix does it this way") without proving applicability to this scale and context
- Diagrams without legends, or boxes that are not defined in prose
- Implicit assumptions about latency, availability, or correctness of dependencies
- Single-paragraph sections where a critical concern was waved away
- Decisions justified by team preference rather than constraint, evidence, or requirement
- Missing failure modes: every dependency call should have a failure-mode story
- "Single source of truth" claimed but not designed (duplicate state in multiple stores)
- Performance numbers without test methodology or environment specified
- "Stateless" claimed for systems that clearly hold state (caches, session, in-memory)
- Buzzword stacking without a delivered system that proves the combination works
- Estimates in suspiciously round numbers (1 week, 1 month, 1 quarter) with no decomposition
- Disproportionate section depth: one section many times the median weight of others, OR a critical section is a single paragraph while a peripheral section is many pages. Either rushed thinking on the short, or over-engineering on the long. Both signal imbalanced attention regardless of which direction the asymmetry runs.

