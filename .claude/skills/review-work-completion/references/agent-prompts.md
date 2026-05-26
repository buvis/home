# Agent Prompts

## Shared Instructions

All agents receive the review context and diff, plus the review checklist:

```
Read {context_file} for review context, and {diff_file} for the full diff.

Use this review checklist:
{contents of review-dimensions.md}

In addition, work through the numbered rubric:
{contents of rubric.md}

Review the completed work against PRD requirements. Explore the codebase as needed.

OUTPUT FORMAT IS MANDATORY. Follow exactly:
{agent output format from output-formats.md "Agent Output Format" section}

PER-RULE VERDICTS ARE MANDATORY. For every rule in the numbered rubric, emit one line:
R{n}: pass   or   R{n}: fail
(one rule per line, no other text on the line, no rationale).

## Coverage Block (mandatory at end of output)

Emit a `---review-coverage---` block as the LAST thing in your output. Fill three dimensions: `files`, `features`, `rubric`. Leave `tests` empty (the consolidation step fills it).

Format (delimiters are EXACT strings on their own lines):

---review-coverage---
files:
  <path>: reviewed
  <path>: n/a:<reason>
tests:
  pending: filled by consolidation
features:
  <feature name>: verified
  <feature name>: reviewed
  <feature name>: failed
rubric:
  R{n}: pass
  R{n}: fail
---end-review-coverage---

Rules:
- `files`: one entry per diff path. Value is `reviewed` or `n/a:<reason>` (free text after the colon).
- `tests`: leave it as the single line `pending: filled by consolidation`. Do NOT report test counts; consolidation runs the suite and fills the aggregate.
- `features`: one entry per PRD `#### Feature:` heading. Value is `verified` / `reviewed` / `failed`.
- `rubric`: one entry per rule ID from the surface's rubric. Value is `pass` / `fail`. Lowercase only.
- A feature or rule you cannot evaluate counts as `failed` / `fail` — never omit the line.

Source of truth for the block format: `~/.claude/skills/review-work-completion/references/review-coverage-format.md`.
```

> **Note:** The output format is defined in `output-formats.md` under "Agent Output Format". This is the single source of truth — do not duplicate format rules here.

> **Note:** The numbered rubric lives at `references/rubric.md` and is inlined into
> every reviewer's prompt via `{contents of rubric.md}` (same template syntax as
> `review-dimensions.md`). Three of the four reviewers — Bob (Codex), Carl (Gemini),
> Diana (Sonnet via copilot) — are external CLIs that cannot resolve a relative
> path, so the rubric MUST be embedded inline, not referenced. The rubric's rule IDs
> are stable: add new rules with new IDs, never renumber.

> **Note:** The coverage block format is defined in `references/review-coverage-format.md`. The block's structure is embedded inline in the template above for the same reason as the rubric — external-CLI reviewers cannot resolve relative paths.

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

Carl is the **frontend & design specialist**. Append to Carl's prompt:

```
## Frontend & Design Focus

You still review every dimension in the checklist, but you are the panel's
frontend and design specialist. On any UI, component, styling, or
user-facing change, review with extra depth:

- Accessibility: semantic markup, keyboard navigation, focus management,
  ARIA usage, colour contrast, screen-reader labels.
- Responsive behaviour: layout across breakpoints, overflow, touch targets.
- Visual consistency: design-token usage, spacing/typography scale, reuse
  of existing components over one-off styling.
- UX correctness: loading/empty/error states, form validation feedback,
  no layout shift, sensible defaults.
- Component structure: state vs props boundaries, no prop drilling,
  composability, no duplicated markup.

If the change has no frontend surface, review it as a generalist against
the shared checklist - do not invent frontend findings.
```

## Diana (Sonnet) Instructions

Diana runs with full tool access. She can execute tests, linters, and build commands.

No additional constraints beyond the shared instructions above.
