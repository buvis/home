# Question Bank

Questions organized by depth level and category. Each entry has the question text, multiple-choice options, when to ask, and what it informs in the discovery doc.

## Standard Depth Questions (3-6)

### 1. Problem Validation
**When**: Always at standard+ depth
**Informs**: Problem section

> What triggers this need?
> a) Specific pain point I've hit repeatedly
> b) Preventive improvement before it becomes a problem
> c) External request (client, user, dependency)
> d) Other

### 2. Scope Boundaries
**When**: Always at standard+ depth
**Informs**: Out of scope section

> What is explicitly out of scope for this work?

Open-ended. If the user struggles, prompt with likely adjacent features that should be excluded.

### 3. Success Criteria
**When**: Always at standard+ depth
**Informs**: Success Criteria section

> How will you know this works?
> a) Specific measurable outcome (state it)
> b) Behavioral test I can run
> c) Manual verification against a checklist
> d) Other

### 4. Integration Points
**When**: Standard+ depth, brownfield only. Auto-populate options from codebase scan.
**Informs**: Codebase Context section

> Which existing components does this touch?
> a) {auto-populated from scan}
> b) {auto-populated from scan}
> c) {auto-populated from scan}
> d) Other

Multi-select. Skip if greenfield.

### 5. Constraints
**When**: Standard+ depth when constraints aren't obvious from input
**Informs**: Constraints section

> Any hard constraints?
> a) Must be backwards-compatible with existing behavior
> b) No new external dependencies
> c) Performance-sensitive (latency, memory, tokens)
> d) Other

Multi-select.

### 6. Priority
**When**: Standard+ depth when urgency unclear
**Informs**: Metadata, ordering in backlog

> When does this need to land?
> a) Next autopilot batch
> b) Eventually, no rush
> c) Blocking other work
> d) Other

## Comprehensive Depth Additions (up to 6 more)

### 7. Approach Preference
**When**: Comprehensive depth, multiple viable approaches exist
**Informs**: Approach section

Present 2-3 approaches with tradeoffs, sourced from brownfield analysis and domain knowledge. Ask user to pick.

> I see a few ways to approach this:
> a) {Approach A}: {1-line description}. Tradeoff: {tradeoff}
> b) {Approach B}: {1-line description}. Tradeoff: {tradeoff}
> c) {Approach C}: {1-line description}. Tradeoff: {tradeoff}
> d) Other

### 8. Decomposition Check
**When**: Comprehensive depth, scope may warrant multiple PRDs
**Informs**: Whether to produce one or multiple discovery docs

> This has {n} loosely coupled parts. Should this be one PRD or split?
> a) One PRD, they're tightly coupled enough
> b) Split into {n} separate PRDs
> c) Split but sequence them (PRD B depends on PRD A)
> d) Other

### 9. Risk Identification
**When**: Comprehensive depth
**Informs**: Risks section

> What could go wrong or block progress?

Open-ended. If user draws blank, prompt with common risk categories: external dependencies, unclear requirements, performance unknowns, compatibility concerns.

### 10. Pattern Reuse
**When**: Comprehensive depth, brownfield, similar existing code found
**Informs**: Codebase Context section

> I found similar existing implementations:
> - {pattern A}: {file path, brief description}
> - {pattern B}: {file path, brief description}
>
> Which patterns should we follow?
> a) Follow {pattern A}
> b) Follow {pattern B}
> c) New approach, don't follow existing patterns
> d) Other

### 11. Edge Cases
**When**: Comprehensive depth, domain-specific edge cases are non-obvious
**Informs**: Requirements section (must have / nice to have)

Domain-specific. Formulate based on the problem space. Examples:
- For skills: "What happens if the user interrupts mid-workflow?"
- For hooks: "What if the expected data format changes?"
- For integrations: "What if the external service is unavailable?"

### 12. Contradiction Resolution
**When**: Comprehensive depth, previous answers conflict
**Informs**: Resolves ambiguity across all sections

> Your answers seem to pull in different directions:
> - You said {X} but also {Y}
> Which takes priority?
> a) {X} wins
> b) {Y} wins
> c) They're not actually in conflict because {explain}
> d) Other

## Question Principles

- **One question per message.** Concise, with enough context to answer quickly.
- **Multiple-choice with "Other".** Use AskUserQuestion tool when possible.
- **Don't ask what codebase analysis can answer.** If scanning reveals the answer, state the finding instead of asking.
- **Adaptive skip.** If the user's input already answers a question clearly, skip it. Note the inferred answer in the discovery log.
- **Store Q&A in the discovery file.** After each answer, append to the Discovery Log section. This survives compaction.
