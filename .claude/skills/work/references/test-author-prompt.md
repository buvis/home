# Test Author Prompt (Tess)

Tess writes tests from requirements. She has NOT seen and must NOT think about implementation.

## Prompt Template

The prompt template lives in `work/references/tess-prompt.md` (single source
of truth, registry-shaped single-brace placeholders — `render_prompt.py`
consumes it directly; see `agent-registry.md` for the placeholder table).

## Context Selection

When building Tess's prompt, include:

| Include | Why |
|---------|-----|
| Task description + acceptance criteria | The spec Tess tests against |
| Public types/interfaces | So Tess knows the API surface |
| One sample test file | So Tess follows project conventions |
| Test framework config | So imports and assertions are correct |

| Exclude | Why |
|---------|-----|
| Architecture docs | Would leak implementation thinking |
| AGENTS.md internals | Same - Tess doesn't need to know how things are built |
| Implementation files | Defeats the entire purpose |
| "How to build this" guidance | Tess is a test author, not an implementor |

## Retry Prompt (after quality gate failure)

The retry template lives in `work/references/tess-retry-prompt.md` (single
source of truth, registry-shaped single-brace placeholders — `render_prompt.py`
consumes it directly; see `agent-registry.md` for the placeholder table). It
takes `{QUALITY_FEEDBACK}`, `{TASK_DESCRIPTION}` and
`{TASK_ACCEPTANCE_CRITERIA}`, and bakes in the same fixed guards the initial
template carries (read-only scope, 100K abort line, dispatch prologue,
ASSUMPTIONS footer).

`{QUALITY_FEEDBACK}` is the step-2.8 gate's own findings, one per line, e.g.:

- Test "handles validation" is too vague. Name the specific behavior.
- Test 3 would pass with a function that always returns true. Add constraints.
- No edge case for empty input.
