# Cleanup Pass

You are a cleanup agent. Act now.

## Goal

Remove only real slop from the recent changes while preserving behavior. Do not add features, widen scope, or perform unrelated refactors.

## Task

1. Read `CLEANUP_SINCE` and `AUTOPILOT_REPORT` from the environment.
2. If `CLEANUP_SINCE` is set, inspect `git diff $CLEANUP_SINCE..HEAD --stat` and `git diff $CLEANUP_SINCE..HEAD`.
3. If `CLEANUP_SINCE` is empty, review the most recent commits on the current branch.
4. Review every changed file in scope against the rules below.
5. Fix or remove slop only when the change improves correctness, clarity, or maintainability with minimal behavioral risk.
6. Run the project’s test suite and linter/formatter using the project’s standard commands.
7. If you changed files, commit with message: `refactor: remove slop from recent changes`
8. Append results to the autopilot report.

## Scope rules

- Stay within the changed files unless a related dependency must also change to fix the slop.
- Keep diffs minimal.
- Preserve existing behavior unless the current code is clearly wrong.
- Do not reformat unrelated files.
- Do not introduce new dependencies unless they are already in the project or clearly justified and actually used.
- Prefer deleting over adding unless adding is necessary to preserve correctness.
- Do not change public APIs unless required to remove slop.
- Do not touch generated files unless they are the source of slop.
- If a cleanup would require broader architectural changes, note it in the report instead of widening scope.

## What to remove

### 1. Language/framework verification tests

Tests that only prove the runtime or framework works, not the project’s behavior.

### 2. Weak or tautological tests

Replace existence checks, mock-confirming tests, self-referential assertions, and unexplained magic assertions with behavior-focused assertions. If an important boundary or failure case is missing, add the smallest useful test.

### 3. Redundant type checks

Remove runtime checks that duplicate compile-time guarantees, except at system boundaries.

### 4. Impossible-state error handling

Remove defensive handling for states that cannot occur from the current control flow. Keep validation and error handling at boundaries.

### 5. Swallowed errors and empty catch blocks

Do not hide failures. Re-throw, surface, or handle them meaningfully.

### 6. Debug statements

Remove development-only prints and logs.

### 7. Commented-out code

Delete dead code kept in comments.

### 8. Obvious comments

Remove comments that restate the code. Keep comments that explain intent, constraints, workarounds, or why.

### 9. Over-abstraction and unnecessary indirection

Inline abstractions that have only one consumer and no current testability or architectural value.

### 10. Duplicate code

Reuse existing code or standard library helpers instead of introducing parallel logic.

### 11. Suspicious dependencies

Verify any newly added dependency exists, is used, and is justified. Remove hallucinated, unused, or speculative dependencies.

### 12. Hardcoded secrets and placeholder credentials

Replace with environment variables, secret storage, or project-approved configuration.

### 13. Deprecated APIs and outdated patterns

Modernize only when the newer approach is already supported by the project and the change stays in scope.

### 14. Naive performance patterns

Fix only if the code is on a hot path or clearly scales poorly with input size.

### 15. Leftover artifacts

Remove temp files, scratch scripts, backup files, unrelated lockfile churn, and agent-generated planning docs.

## What to keep

- Business logic tests, integration tests, and boundary tests.
- Error handling at system boundaries.
- Production logging and observability.
- Documentation that explains non-obvious intent or constraints.
- Abstractions that have more than one consumer or clear testability value.
- Dependencies that are actively used and justified.

## Fix in place, don’t delete

- Missing boundary error handling.
- Security issues.
- Violations of project conventions.
- Incomplete implementations that currently fail silently.

## Decision rules

- When in doubt, prefer the smallest safe change.
- If a test is weak, either strengthen it or remove it; do not grow the suite unnecessarily.
- If correctness is uncertain, keep the code and note the concern in the report.
- Every remaining change must have a clear purpose tied to cleanup.

## Verification

1. Run the project’s test suite.
2. Run linting and formatting.
3. If a cleanup change causes failures, restore that specific change and re-run.
4. Re-check the remaining diff and ensure it is minimal and purposeful.
5. If new dependencies were introduced in the reviewed changes, verify they resolve and are actually used.

## Reporting

Append a `### De-sloppify` subsection to the batch report.

Find the report from `AUTOPILOT_REPORT` if set; otherwise use the most recent `dev/local/autopilot/reports/*-report.md`.
Find the PRD section from `dev/local/autopilot/state.json` `prd` field; if unavailable, append under the last PRD section.

Format:

```md
### De-sloppify

| Category | Removed | Fixed |
|----------|---------|-------|
| Debug statements | 3 | 0 |
| Weak tests | 1 | 2 |

Removed 3 debug statements and fixed 2 weak tests.
```

If nothing was changed, write:

```md
### De-sloppify

No slop found.
```

If no report file exists, skip reporting.
