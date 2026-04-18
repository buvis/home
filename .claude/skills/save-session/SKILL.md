---
name: save-session
description: Use when ending a work session and want to preserve context for later resumption. Captures what worked, what failed, decisions made, and exact next step. Triggers on "save session", "save my session", "save progress", "checkpoint session", "save state".
---

# Save Session

Write a structured session file so a future session can resume without re-exploring.

## Workflow

### 1. Derive project name

Use the basename of the current working directory. Replace spaces with hyphens, lowercase.

### 2. Synthesize session state

Review the full conversation and produce each section below. Every section is mandatory. Empty sections get "None this session."

### 3. Write session file

Write to `~/.claude/session-data/YYYY-MM-DD-<project-name>-session.md` using the Write tool.

If a file for today already exists, append a counter: `YYYY-MM-DD-<project-name>-session-2.md`.

### 3b. Append decisions to index

For each entry in the "Decisions Made" section of the session file, route and append to the appropriate decision index:

- **Project-level** (default): `{repo}/dev/local/decisions.md` - project-specific architectural or implementation decisions
- **Global**: `~/.claude/decisions.md` - cross-cutting decisions about tooling, workflow, or conventions that span repos

Routing heuristic: if the decision is about a specific project's code, schemas, algorithms, or domain choices, use project-level. If it's about tools, commit conventions, workflow patterns, or things that would apply if you started a new repo tomorrow, use global.

Append format (table row): `| {YYYY-MM-DD} | {decision} | {why} | session:{filename} |`

Skip this step if:
- The target file doesn't exist (don't auto-create; user opts in by creating the file)
- The decision is already present (grep for the decision text first)

### 3c. Suggest memory promotions

Scan "What Worked" and "What Did NOT Work" sections for patterns worth promoting to persistent memory. Candidates:
- Corrections repeated across 2+ sessions (grep other session files in `~/.claude/session-data/`)
- Surprising findings that contradicted expectations
- Environment-specific gotchas (OS, tooling, cluster-specific quirks)
- Troubleshooting entries: cause + fix for recurring issues

Output a `Suggested Promotions` block at end of save-session output. Do NOT auto-create memory or troubleshooting entries. User decides.

Format:
```
Suggested Promotions:
- [memory|troubleshooting] {one-line summary} — reason: {why this is worth persisting}
```

If no candidates, print `Suggested Promotions: none.`

### 4. Confirm

Print the file path. Do NOT start working on anything after saving.

## Session File Template

```markdown
# Session: {project-name}
Date: {YYYY-MM-DD}

## What We're Building

{1-3 paragraphs. Full context for someone with zero memory of this project.
Include: goal, current approach, where in the process we are.
A reader should understand the project without opening any other file.}

## What WORKED (with evidence)

{Each item MUST include proof. No vague claims.}

- {thing that worked} - Evidence: {test output, HTTP status, command + output, file path confirmed}
- ...

## What Did NOT Work (and why)

{Each item MUST include the exact error or reason for failure.}

- {approach that failed} - Error: {exact error message or specific reason}
- ...

## What Has NOT Been Tried

{Specific enough to act on without re-researching.}

- {untried approach} - {why it might work, any setup needed}
- ...

## Decisions Made

{Include the "why", not just the "what".}

- {decision} - Why: {reasoning, tradeoffs considered}
- ...

## Exact Next Step

{Single most important action. Zero-thought startup for the next session.
Be specific: which file, which function, which command to run.}
```

## Quality Bars

| Section | Minimum quality |
|---------|----------------|
| What We're Building | Standalone context, no assumed knowledge |
| What WORKED | Every item has verifiable evidence |
| What Did NOT Work | Every item has exact error or reason |
| What Has NOT Been Tried | Actionable without re-research |
| Decisions Made | "Why" present for every decision |
| Exact Next Step | One action, specific enough to execute immediately |

## Common Mistakes

- Writing vague summaries ("made progress on auth") instead of specifics
- Omitting error messages from failed approaches
- Listing next steps instead of THE next step
- Forgetting to include evidence for what worked
