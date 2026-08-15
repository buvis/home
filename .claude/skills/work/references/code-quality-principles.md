# Code Quality Principles

Rules injected into implementor (Ivan) prompts. Ivan runs as a Codex/Gemini
subagent and does NOT inherit the user's global `~/.claude/rules/`, so the
dispatch prompt must carry these rules itself.

The **Prompt Snippet** section below is baked verbatim into `~/.claude/agents/ivan.md`,
so every Ivan dispatch that renders from that persona carries it by
construction — initial implementation (step 3), test-failure retry (5.5),
review-fix retry (5.7) and regression fix (step 7).
**Do not copy it into a dispatch prompt**: `ivan.md` already has it, and adding
it again duplicates the block in the prompt. This file remains the source of
truth — edit the snippet here, then propagate it to `ivan.md`. The four rule
families counter the anti-patterns LLM coding agents produce by default:
speculative abstractions, drive-by refactoring, style drift, and silent
assumptions.

## Prompt Snippet

> Copy everything between the markers verbatim into the Ivan prompt.

<!-- BEGIN PROMPT SNIPPET -->

### Code quality rules (mandatory)

Follow these four rules. They override any instinct to "improve" the code
beyond what the failing tests require.

**1. Think before coding.** Re-read the task and the failing tests. If scope,
data shape, target file, or success criteria are ambiguous - more than one
reasonable implementation would pass the tests differently - STOP and report
the ambiguity as a blocker. Do not guess and proceed.

**2. Simplicity.** Write the simplest code that makes the failing tests pass.

- No abstractions, helpers, or interfaces built for a single caller.
- No error handling, fallbacks, or validation for inputs the tests never
  exercise. Validate at real system boundaries only.
- No features, options, or configuration the task did not ask for.
- If your draft runs long and the same behavior fits in far fewer lines,
  rewrite it before returning.

**3. Surgical changes.** Touch only what the task requires.

- Do not refactor, reformat, or "improve" code outside the change.
- Match the surrounding style even if you would write it differently.
- Remove imports, variables, and functions that YOUR change orphaned. Do not
  delete pre-existing dead code - mention it instead.
- Every changed line must trace to the task or a failing test.

**4. Goal-driven.** The failing tests are the spec. Make them pass - do not
modify them, do not weaken them, do not add tests. If a test looks wrong,
report it as a blocker rather than changing it.

<!-- END PROMPT SNIPPET -->

## Why these four

| Rule | Anti-pattern it counters |
|------|--------------------------|
| Think before coding | Silent assumptions - guessing at unstated requirements |
| Simplicity | Speculative abstractions - building for hypothetical futures |
| Surgical changes | Drive-by refactoring - unrequested edits to adjacent code |
| Goal-driven | Style drift and test-tampering - reshaping the spec to fit the code |

See `code-quality-examples.md` for before/after examples of each.
