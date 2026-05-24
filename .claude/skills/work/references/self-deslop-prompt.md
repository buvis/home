# Self-Deslop Prompt Template

This is the prompt template dispatched by `/work` step 5.6 — the per-task
self-deslop pass that runs between test-pass verification (step 5.5) and the
per-task code review (step 5.7).

`/work` step 5.6 substitutes the placeholders below before dispatching the
subagent. **`{{slop_catalog}}` is filled in at dispatch time** by reading the
current `~/.claude/skills/run-autopilot/prompts/de-sloppify.md`, extracting the
`## What to remove` section verbatim, and inlining it here. The subagent
receives one self-contained prompt with no extra filesystem reads required.
This keeps `prompts/de-sloppify.md` as the single source of truth for slop
patterns: when it evolves, the next step-5.6 dispatch picks up the new catalog
with no edit to this template.

Placeholders:

- `{{task_subject}}` — `task.subject` from `TaskGet`.
- `{{task_description}}` — `task.description` from `TaskGet`.
- `{{task_acceptance_criteria}}` — `task.acceptance_criteria` from `TaskGet`,
  or the literal string `(none recorded)` when absent.
- `{{test_files}}` — comma-separated paths of the test files Tess wrote in
  step 2.7 and the implementor just made pass in step 5.5.
- `{{diff_files}}` — comma-separated paths of files touched in the implementor's
  most recent commit (`git diff-tree --no-commit-id --name-only -r HEAD`).
- `{{slop_catalog}}` — verbatim contents of `## What to remove` from
  `prompts/de-sloppify.md`.

---

## Prompt Template

```
A diff has been written to satisfy this task. The implementation passed its
tests. Your job: prune slop from the diff while keeping every test green.
This is best-effort cleanup, not a correctness rework — do not change
behavior, do not modify tests, do not refactor.

Task: {{task_subject}}

Description:
{{task_description}}

Acceptance criteria:
{{task_acceptance_criteria}}

Tests that the diff made pass (do NOT modify):
{{test_files}}

Files in the diff:
{{diff_files}}

Procedure:

1. Read the diff for each file in scope (`git diff HEAD~1..HEAD <file>` or
   equivalent in your environment).
2. For each line, block, helper, comment, docstring, or test added in the
   diff, ask:
     "Does this trace to a failing test, an acceptance criterion, or
     existing-behavior preservation?"
   If the answer is no, mark the construct for removal.
3. Apply removals one at a time. After each individual removal, re-run the
   tests listed above (the narrow set Tess wrote). If any test fails,
   restore that single removal and move on to the next candidate. Never
   delete the test that fails — the test is authoritative.
4. If no removal survived its test re-run, exit WITHOUT committing. Return
   the literal string "no slop found" so the caller can record a noop.
5. If at least one removal survived, commit with message:
     chore: prune slop from {{task_subject}}
   No CHANGELOG entry. No HEREDOC. No Co-Authored-By trailer. One commit
   only — do not split into multiple cleanup commits.

Rules:

- **Do not modify tests.** If a test reads as weak, that is the per-task
  reviewer's call (step 5.7), not yours. Leave it.
- **Do not change behavior.** Tests prove behavior; if you cannot satisfy
  the tests, the deletion is wrong. Restore.
- **Do not refactor.** This pass deletes; it does not move code around,
  rename symbols, or extract helpers. If a slop pattern would only resolve
  through restructuring, note it in the return message instead of acting.
- **Do not touch files outside the diff.** The cleanup is scoped to what
  the implementor just produced. Adjacent slop in untouched files is out
  of scope here — the post-session codex pass catches it separately.

Slop patterns to look for (catalog inlined from `prompts/de-sloppify.md`):

{{slop_catalog}}

Return one of:
  - "no slop found" — exited without commit, nothing to clean.
  - "committed {sha}" — committed `chore: prune slop from ...` at {sha},
    test suite green.
  - "errored: {short reason}" — dispatch problem; do not commit, just
    explain so the caller can record the failure.
```

---

## Dispatch contract reminders

The `/work` step 5.6 caller, NOT the subagent, is responsible for:

- The 30-net-lines / 2-files skip rule. The subagent only sees prompts for
  non-trivial diffs.
- The fresh-Agent-dispatch requirement (not the implementor's session).
- The 15-minute watchdog and `TaskStop` on timeout.
- Writing the outcome to `state.tasks[i].attempts[-1].self_deslop`.

See `SKILL.md` step 5.6 for the full contract.
