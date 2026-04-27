# Discovery Document Template

Use this template when generating the discovery output. Scale sections to depth level.

## Minimal Depth (~30 lines)

```markdown
# Discovery: {Feature Name}

## Classification
Depth: minimal | Date: {YYYY-MM-DD}

## Problem
{1-3 sentences. Concrete pain point.}

## Requirements

### Must have
- {Requirement}

### Out of scope
- {Explicitly excluded}

## Success Criteria
- {Measurable outcome}

## Discovery Log
{Q&A pairs if any, or "Input was sufficiently clear - no questions needed."}
```

## Standard Depth (~60-100 lines)

```markdown
# Discovery: {Feature Name}

## Classification
Depth: standard | Date: {YYYY-MM-DD}

## Problem
{2-4 sentences. What hurts, who it affects, why existing solutions fall short.}

## Requirements

### Must have
- {Requirement}

### Nice to have
- {Optional requirement}

### Out of scope
- {Explicitly excluded}

## Constraints
- {Hard constraint}

## Codebase Context
- **Relevant code**: {files, modules, patterns found during brownfield scan}
- **Conventions**: {naming, structure, testing patterns to follow}
- **Integration points**: {existing code that gets modified or extended}

## Success Criteria
- {Measurable outcome}

## Risks
- **{Risk}**: {mitigation}

## Open Questions
- {Anything unresolved - /create-prd should address these}

## Discovery Log

### Q1: {Question text}
**Answer**: {User's answer}

### Q2: {Question text}
**Answer**: {User's answer}

{...continue for all questions asked}
```

## Comprehensive Depth (full)

```markdown
# Discovery: {Feature Name}

## Classification
Depth: comprehensive | Date: {YYYY-MM-DD}

## Problem
{3-5 sentences. Full context: pain point, who is affected, why now, what happens if not addressed.}

## Requirements

### Must have
- {Requirement}

### Nice to have
- {Optional requirement}

### Out of scope
- {Explicitly excluded}

## Constraints
- {Hard constraint}

## Codebase Context
- **Relevant code**: {files, modules, patterns found during brownfield scan}
- **Conventions**: {naming, structure, testing patterns to follow}
- **Integration points**: {existing code that gets modified or extended}
- **Similar implementations**: {existing code that solves adjacent problems - reference for patterns}

## Approach
- **Chosen**: {description of selected approach}
- **Why**: {rationale}
- **Rejected alternatives**:
  - {Alternative A}: {why rejected}
  - {Alternative B}: {why rejected}

## Success Criteria
- {Measurable outcome}

## Risks
- **{Risk}**: {mitigation}

## Open Questions
- {Anything unresolved - /create-prd should address these}

## Discovery Log

### Q1: {Question text}
**Answer**: {User's answer}

### Q2: {Question text}
**Answer**: {User's answer}

{...continue for all questions asked}
```

## Rules

- **Discovery Log is mandatory** at all depths. It creates traceability from requirements to user decisions.
- **Open Questions section**: list anything unresolved. `/create-prd` will see these and can either resolve them during PRD creation or carry them forward.
- **Codebase Context**: only include at standard+ depth. Include file paths, not vague descriptions.
- **Approach section**: only include at comprehensive depth. Always state why alternatives were rejected.
- **No stubs**: every section that appears must have real content. If a section doesn't apply, omit it entirely rather than writing "N/A".
