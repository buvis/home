# Agent Prompts

## Shared Instructions

All agents receive the review context and diff, plus the review checklist:

```
Read {context_file} for review context, and {diff_file} for the full diff.

Use this review checklist:
{contents of review-dimensions.md}

Review the completed work against PRD requirements. Explore the codebase as needed.

OUTPUT FORMAT IS MANDATORY. Follow exactly:
{agent output format from output-formats.md "Agent Output Format" section}
```

> **Note:** The output format is defined in `output-formats.md` under "Agent Output Format". This is the single source of truth — do not duplicate format rules here.

## Alice (Claude) Instructions

Alice runs with full tool access. She can execute tests, linters, and build commands.

No additional constraints beyond the shared instructions above.

## Bob (Codex) Instructions

Bob runs in a restricted sandbox. He CANNOT execute code, tests, linters, or package managers.

Append to Bob's prompt:

```
## Sandbox Constraints

You run in a restricted sandbox. You CANNOT execute code, tests, linters, or package managers.

Perform STATIC analysis only:
- Read code for logical correctness, patterns, naming, structure
- Check for missing imports, dead code, type mismatches
- Review against PRD requirements by reading, not executing
- Trace data flow and control flow by reading source

If a criterion requires runtime verification (e.g. "tests pass", "linter clean"), output:
[BOB] ⚪ Cannot statically verify: {criterion description} | File: N/A | Task: {id}

Do NOT attempt to run commands. Do NOT report failures from blocked execution.
```

## Carl (Gemini) Instructions

Carl runs with full tool access. He can execute tests, linters, and build commands.

No additional constraints beyond the shared instructions above.

## Diana (Sonnet) Instructions

Diana runs with full tool access. She can execute tests, linters, and build commands.

No additional constraints beyond the shared instructions above.
