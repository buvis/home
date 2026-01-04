# Review Taskmaster Completion

Taskmaster — FIRST CHECK (MANDATORY, do not skip):

1. Output a table of ALL tasks/subtasks: | ID | Title | Status | (use "todo", "in-progress" [started/active/reviewing/blocked], "done").
2. If ANY "in-progress", STOP IMMEDIATELY. Output ONLY:

   STOPPED: In-progress task(s): [ID1 (title), ID2…]. No further work.

   Do not dispatch agents, review, or create tasks.

CONTINUE ONLY IF ZERO in-progress tasks.

DEFINITIONS:

- Complexity: S (<4h, single change), M (1d, few related changes), L (>1d, multi-file/arch changes).
- Severity: Critical (security/bugs), High (gaps/correctness), Med (quality), Low (style).
- PRDs: Source of truth for "desired state" (.taskmaster/docs/*.prd; read ALL relevant via `read_file` tool).

PREP STEPS:

1. Index future tasks (not-yet-done): Bullet list | ID | Title |.
2. Read ALL PRDs: Summarize key "desired state" sections relevant to completed tasks.

WORK LOOP (per completed task/subtasks):
Dispatch Alice and Bob (simultaneously, competing: "Find more real issues to win promotion"). Instruct each:

- Review THIS task/subtasks ONLY: architecture, code, tests, docs.
- Check:
  - Plan compliance: Matches task intent/details/acceptance criteria.
  - PRD coverage: Verify desired state in PRDs was achieved. Flag any unaddressed element as an individual gap, citing exact PRD section/requirement (e.g., "PRD v1.2#3.1: Missing X").
  - No gaps: Cross-ref future tasks index. If missing work planned later, note "planned later (ID Y)"—do NOT flag as issue.
  - Engineering quality: Standards (style/structure/tests/docs/maintainability).
  - Security: No risks (leaks/injections/auth regressions/misconfigs).
  - Correctness: No bugs/edges/races/errors/observability gaps.
- Limit: Max 5 findings each, tagged [Critical/High/Med/Low].

PER-TASK OUTPUT (table format):

## Task [ID]: [Title]

| Alice Findings | Bob Findings | De-duped Issues | Planned Later Notes |
|----------------|--------------|-----------------|--------------------|
| - [High] Bullet (file:foo.py, subtask Z, PRD#3.1) | - [High] Same… | - [Both] Bullet (sev:High, file:foo.py) | - GapX (task Y) |

AFTER ALL TASKS:

1. MERGED ISSUES TABLE (de-duped across all, prioritized Critical first):

## Merged Actionable Issues

   | Task/Subtask | Description | Why Issue | Where (file/area) | Sev |
   |--------------|-------------|-----------|-------------------|-----|
   | …         | …        | …      | …              | …|

1. Generate NEW top-level tasks (add after existing list):
   - One per thematic group (e.g., "Fix auth security gaps").
   - Per issue/table row: Title, desc (ref issue), 3-5 testable criteria.
   - Assess S/M/L; if M/L, add 2-4 focused subtasks.
   - Max 10 new tasks (batch rest into "Misc fixes").

FINAL OUTPUT:

## Proposed New Tasks

1. [ID] Title (S/M/L)
   - Desc…
   - Criteria: …
   - Subtasks: …

Stop here.
