Your tests have quality issues. Fix them.

Issues found:
{QUALITY_FEEDBACK}

Original requirements (unchanged):

Description:
{TASK_DESCRIPTION}

Acceptance Criteria:
{TASK_ACCEPTANCE_CRITERIA}

Rewrite the tests addressing each issue above. Keep every test that is already
sound — this is a targeted fix, not a rewrite from scratch.

The original rules still apply. In particular:

1. Write tests from requirements only. You are a USER of this API, not its builder.
2. Each test name describes a behavior, not an implementation detail.
3. Assert on outputs, return values, side effects, and errors. Never assert on mock existence.
4. For EACH test, ask yourself: "What wrong implementation would still pass this?" If easy to answer, add constraints.
5. SIMPLICITY FIRST: test only the behavior in the acceptance criteria. Strengthening a weak test does not mean adding tests nobody asked for.
6. NEVER INVENT A CONTRACT: if the requirements name a data structure but do not pin its exact field names, enum values, or types, STOP and report it as a blocker rather than inventing a plausible schema.
7. SURGICAL: only create/modify test files. Match the existing test file's style.

Read only the files listed above. If a file or symbol you need is not listed, stop and report it as a blocker — do not run broad `rg` sweeps to discover scope.

Abort and report if you read more than 100K of total input. Return the partial result and an abort_reason: context_overrun field.

Read every file before your first Edit to it. Never call bash `head`, `tail`, `cat`, `grep`, or `find` - a hook blocks them. Use the Read tool (offset/limit), `rg`, or `rg --files` instead.

End your report with `ASSUMPTIONS:` - one line per assumption you made where the task, tests, or listed files were silent (guessed interface, data shape, resolved ambiguity, unstated behavior). Write `ASSUMPTIONS: none` if you made none.
