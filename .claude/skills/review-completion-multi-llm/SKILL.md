---
name: Review Completion Multi-LLM
description: Review completed taskmaster tasks using Alice, Bob (Codex), and Carol (Copilot) agents
---

# Review work completion using multiple LLMs

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
Dispatch Alice, Bob, and Carol (simultaneously, competing: "Find more real issues to win promotion"). Instruct each:

- Review THIS task/subtasks ONLY: architecture, code, tests, docs.
- Check:
  - Plan compliance: Matches task intent/details/acceptance criteria.
  - PRD coverage: Verify desired state in PRDs was achieved. Flag any unaddressed element as an individual gap, citing exact PRD section/requirement (e.g., "PRD v1.2#3.1: Missing X").
  - No gaps: Cross-ref future tasks index. If missing work planned later, note "planned later (ID Y)"—do NOT flag as issue.
  - Engineering quality: Standards (style/structure/tests/docs/maintainability).
  - Security: No risks (leaks/injections/auth regressions/misconfigs).
  - Correctness: No bugs/edges/races/errors/observability gaps.
- Limit: Max 5 findings each, tagged [Critical/High/Med/Low].

Additional tool-use instructions:

- Bob should use Codex to assist with code understanding, static reasoning, and identifying potential issues in logic, structure, and tests.
- Carol should use Copilot to explore alternative implementations, suggest refactorings, and surface additional edge cases or tests that might be missing.

PER-TASK OUTPUT (table format):

## Task [ID]: [Title]

| Alice Findings | Bob Findings (Codex-assisted) | Carol Findings (Copilot-assisted) | De-duped Issues | Planned Later Notes |
|----------------|-------------------------------|-----------------------------------|-----------------|--------------------|
| - [High] Bullet (file:foo.py, subtask Z, PRD#3.1) | - [High] Bullet… | - [Med] Bullet… | - [Both] Bullet (sev:High, file:foo.py) | - GapX (task Y) |

AFTER ALL TASKS:

1. MERGED ISSUES TABLE (de-duped across all, prioritized Critical first):

## Merged Actionable Issues

| Task/Subtask | Description | Why Issue | Where (file/area) | Sev |
|--------------|-------------|-----------|-------------------|-----|
| …            | …           | …         | …                 | …   |

1. CREATE TASKS IN TASKMASTER (MANDATORY — do not just list them)

Goal: Persist the plan into Taskmaster (tasks.json), by creating new tasks and (when needed) subtasks.

Rules:

- Max 10 new tasks total; batch any overflow into 1 task titled "Misc fixes (batched)".
- One task per thematic group (e.g., "Fix auth security gaps"), mapping each MERGED ISSUES row to exactly one created task.
- Each created task must include: title, description (reference the merged-issues row(s)), and 3–5 testable acceptance criteria.
- Complexity tag in title suffix: (S/M/L). (Use definitions above.)
- Dependencies:
  - If a new task obviously depends on an existing not-yet-done task, include --dependencies=<ids> when creating it.
  - If the dependency is unclear, omit dependencies (do not guess).
- For M/L tasks: create 2–4 subtasks using `task-master expand` with a prompt that repeats the acceptance criteria and any key constraints.

Execution steps (in order):
A) For each planned new task:

1) Run:
      task-master add-task --prompt="<Title> (<S|M|L>): <1–3 sentence description>. Acceptance criteria: (1) ... (2) ... (3) ... (4) ... (5) ..." [--dependencies=...] [--priority=high|med|low]
   2) Capture the new task ID from the command output.
B) For each newly created task that is M/L:

   Run:
      task-master expand --id=<new_id> --num=<2-4> --prompt="Generate subtasks that directly satisfy the acceptance criteria. Include tests/verification steps per subtask."
C) If you realize any created task wording is off:
   Run:
      task-master update-task --id=<new_id> --prompt="Fix wording/details: ..."

FINAL OUTPUT (must reflect the actual created Taskmaster tasks, not hypothetical):

- Print a numbered list of the tasks you just created, using the real Taskmaster IDs:
  1. [ID] Title (S/M/L)
     - Desc: ...
     - Criteria: ...
     - Dependencies: ... (if any)
     - Subtasks: yes/no (and count if known)

Stop here.
