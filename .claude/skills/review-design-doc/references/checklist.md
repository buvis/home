# Review checklist (25 dimensional items)


For each section, give a verdict (✅ Solid / ⚠️ Concern / ❌ Missing or broken / ➖ N/A) followed by 1 to 3 sentences of evidence-backed reasoning. Cite section headings or line numbers for every observation. If you mark N/A, state why in one line.

### 1. Problem framing
- Is the problem statement crisp, and is "why now" justified?
- Is the user, customer, or business outcome named, not just the technical activity?
- Are non-goals listed explicitly?
- Are success metrics measurable (numbers and time-bounded, not adjectives like "fast" or "scalable")?

### 2. Stakeholders and ownership
- Are affected users, the owning team, and the operating team identified?
- Who pages at 3am when this breaks?
- Are upstream and downstream teams informed or consulted?
- Is there a single accountable decision-maker, or is ownership diffuse?

### 3. Assumptions and constraints
- Are assumptions stated explicitly rather than buried in prose?
- Are regulatory, budget, headcount, deadline, team-skill, and existing-stack constraints acknowledged?
- Are expected load, data volume, and growth quantified, both day-1 and 12 months out?
- Are organizational constraints (other teams' roadmaps, vendor contracts, freeze windows) acknowledged?
- Are the assumptions falsifiable, or so vague they cannot be wrong?

### 4. Alternatives considered
- Are at least 2 to 3 alternatives discussed with explicit trade-offs?
- Is "do nothing" or "extend the existing system" evaluated?
- Is "buy vs. build" considered for any non-trivial component?
- Are rejection reasons substantive, or strawmen designed to make the chosen path look good?
- Is there evidence of bias (resume-driven, not-invented-here, sunk-cost, team's preferred stack)?

### 5. Architecture and component design
- Are component boundaries clear, with single responsibilities?
- Are coupling and cohesion sound: minimal cross-component knowledge, clear dependency direction?
- Is the blast radius of each component bounded?
- Do diagrams have legends, and do boxes and arrows match the prose?
- Are the layers (presentation, business, data, integration) explicit where they matter?

### 6. Data model and lifecycle
- Is the schema specified, including types, nullability, and invariants?
- Is the source of truth for each entity unambiguous?
- Are retention, archival, deletion, and backup/restore addressed?
- Is data ownership clear when multiple services touch the same data?
- Is schema evolution (additions, deprecations, migrations) addressed?
- Is data lineage traceable from origin to consumption?

### 7. Interfaces and contracts
- Are API contracts (request and response shapes, status codes, error formats) specified concretely?
- Are event schemas defined if pub/sub or messaging is used?
- Is versioning strategy explicit?
- Is backward and forward compatibility addressed?
- Are pagination, filtering, sorting, and rate-limit conventions consistent with the rest of the stack?
- Are SDKs, client libraries, or CLI surfaces part of the contract surface?

### 8. Concurrency, consistency, and semantics
- Are transactional boundaries explicit?
- Is the consistency model (strong, eventual, read-your-writes, causal) named, not assumed?
- Are idempotency, retry safety, ordering guarantees, and at-least, at-most, exactly-once semantics addressed where they matter?
- Are race conditions and concurrent-update conflicts anticipated, with resolution strategy?
- Are clocks, timestamps, and time zones handled explicitly?

### 9. Scalability and performance
- Are latency budgets specified per operation (p50, p95, p99)?
- Are throughput and capacity targets quantified?
- Has the design been stress-tested mentally at 10x load? What breaks first?
- Are bottlenecks identified, and is the plan for when they are hit?
- For data systems: are hot keys, skew, fan-out, and unbounded growth considered?
- Is caching strategy (where, what TTL, invalidation) addressed if relevant?

### 10. Failure modes and resilience
- For each external dependency: what happens when it is slow, down, returns bad data, or has a partial outage?
- Is there a circuit-breaker, timeout, and retry strategy with backoff and jitter?
- Is graceful degradation designed in, or does any failure cascade?
- Is there a rollback or recovery plan including data state?
- Are RPO (recovery point objective) and RTO (recovery time objective) defined for stateful components?
- Are partial failures (split-brain, partial writes) addressed?

### 11. Observability
- Are SLIs, SLOs, and SLAs defined for user-visible operations?
- Are logs, metrics, and traces designed in, not bolted on, with correlation IDs and a sampling strategy?
- Is the "how do we know it is broken" question answered before "how do we fix it"?
- Are dashboards and alerts described, not just promised?
- Is the error budget policy explicit (what triggers a freeze)?

### 12. Security
- Is there a threat model, at minimum: attackers, attack surface, trust boundaries?
- Are authentication and authorization spelled out, with principle of least privilege applied?
- Is encryption (at rest, in transit, key management, rotation) addressed?
- Are secrets handled via a vault or manager, not config files or environment variables in plaintext?
- Is supply-chain risk (dependencies, base images, third-party services, build pipeline) considered?
- Is audit logging tamper-evident for sensitive actions?
- Are common classes (injection, SSRF, deserialization, auth bypass, IDOR) considered for the surfaces present?
- Is multi-tenant isolation addressed if applicable?

### 13. Privacy and compliance
- Is sensitive or personal data identified and minimized?
- Are data subject rights (access, deletion, portability, correction) addressed if applicable?
- Are relevant regulatory frameworks named (without assuming which; ask if unclear)?
- Is data residency or cross-border movement addressed?
- Is consent capture, scope, and revocation handled?
- Is segregation of duties enforced for high-impact actions?

### 14. Cost and operational burden
- Rough infrastructure cost estimate, day-1 and at projected scale?
- Total cost including dev time, ops time, and lifecycle maintenance?
- What does this cost at 10x scale? Does the architecture survive economically?
- On-call rotation, runbook ownership, and operational handoff described?
- Is cost attribution (per tenant, per feature, per team) possible if it matters?

### 15. Deployment and topology
- Multi-region, multi-zone, multi-tenant considerations addressed?
- Configuration management: what is static, what is runtime, where it lives, who can change it?
- Deployment strategy (blue/green, canary, rolling, feature flag) appropriate to blast radius?
- Are dev, staging, and production environments described, including data realism?
- Is zero-downtime deployment a requirement, and if so, is it achievable?

### 16. Migration and rollout
- Is there a path from current state to target state, step by step?
- Feature flags, dark launches, shadow traffic, parallel-run strategy?
- Data migration plan including reversibility, idempotency, and progress tracking?
- User-facing communication plan if behavior changes?
- Explicit backout plan, not just "we will roll back"?
- Are intermediate states (during migration) themselves valid and operable?

### 17. Testability
- Can components be tested in isolation? Are seams designed in?
- Integration test strategy (boundaries, fixtures, contract tests)?
- Performance and load testing strategy?
- Chaos or failure-injection strategy for resilience claims?
- Is test data sourcing addressed (synthetic, anonymized prod, fixtures)?

### 18. Timeline and delivery
- Are estimates realistic given team size and other commitments?
- Are milestones defined with crisp completion criteria, not "done when it feels right"?
- Is the critical path identified, and are dependencies between phases explicit?
- Are risks to the timeline named with mitigations?

### 19. Documentation and runbook
- What gets documented, where, by whom, and by when?
- Is operator-facing documentation (runbook, troubleshooting, common incidents) part of the deliverable, not an afterthought?
- Are architectural decisions captured (ADRs) where appropriate?

### 20. Open questions and risks
- Explicit "open questions" section?
- Top risks listed with mitigations and a decision-by date?
- Is there an honest "things we do not know yet", or does the doc project false confidence?
- Are dependencies on unproven technology or unfamiliar tools flagged?

### 21. Internal consistency
- Are sections proportional in depth to their importance? **Measurement anchor**: count words (or bullet points) per top-level section, compute the median, and flag any section >3x the median weight (potential over-detail) or <1/3 the median (potential under-detail). Justify the imbalance or rebalance the doc. See the Section weight audit technique for the full procedure.
- Terminology consistent throughout (e.g., "user" vs "account" vs "tenant" not used interchangeably)?
- Do diagrams match the prose? Do schemas match the API examples?
- Do the numbers (capacity, latency, cost) reconcile across sections?

### 22. Overengineering check
For each major component or abstraction, ask: **"What would have to be true for this to be wrong or unnecessary?"** Flag any that assume future load, complexity, or requirements not justified by the problem statement. In reverse: are any "lightweight" choices going to be insufficient at projected scale?

### 23. Reversibility check
For each major decision, classify as **one-way door** (hard or impossible to undo: data models, public APIs, vendor lock-in, persistent storage choices) or **two-way door** (easy to change: internal helpers, deployment scripts). Are one-way doors given the scrutiny they deserve? Are two-way doors being over-debated?

### 24. Six-months-later test
Would a new engineer joining in 6 months understand *why* these choices were made from this doc alone? Flag missing rationale, especially for trade-offs that look arbitrary without context.

### 25. Design vs. reality (only if `$3` was provided)
Spot mismatches between what the doc claims and what the codebase actually does. Do not audit the whole codebase, just verify claims that seem load-bearing (e.g., "we already have X service" => check it exists and does what is claimed).

