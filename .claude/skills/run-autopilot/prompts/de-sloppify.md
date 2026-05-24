# Cleanup Pass

You are a cleanup agent. Act now.

## Goal

Remove only real slop from the recent changes while preserving behavior. Do not add features, widen scope, or perform unrelated refactors.

## Task

1. Read `CLEANUP_SINCE`, `AUTOPILOT_REPORT`, and `QWEN_TASK_IDS` from the environment.
2. If `CLEANUP_SINCE` is set, inspect `git diff $CLEANUP_SINCE..HEAD --stat` and `git diff $CLEANUP_SINCE..HEAD`.
3. If `CLEANUP_SINCE` is empty, review the most recent commits on the current branch.
4. Categorize each changed file by tier (see "File-tier scoping" below).
5. Review every changed file in scope against the rules below.
6. Fix or remove slop only when the change improves correctness, clarity, or maintainability with minimal behavioral risk.
7. Run the project's test suite and linter/formatter using the project's standard commands.
8. If you changed files, commit with message: `refactor: remove slop from recent changes`
9. Append results to the autopilot report.

## qwen-implemented commit ranges

`QWEN_TASK_IDS` is a comma-separated list of task IDs whose attempts include a qwen-implemented + completed dispatch in this PRD's state. Empty (or unset) → no qwen-implemented work in this PRD; behave exactly as before.

When non-empty:

- The qwen-implemented commit ranges within `CLEANUP_SINCE..HEAD` are in scope for the same cleanup rules as everything else — qwen has known idiom drift (over-claims completeness, under-covers multi-file tasks, occasional speculative abstractions) the batched pass exists to catch. Inspect the listed task IDs first; commit messages and the autopilot report typically reference task IDs and let you identify which commits belong to each.
- Apply the same scope rules below to qwen commits as to any other commit. Do NOT add a separate qwen-only pass or a separate commit. Within this dispatch you produce exactly **one** cleanup commit (or none); splitting a PRD into more tasks does not multiply that. Claude/Gemini-implemented commits are unchanged by this scoping — they get the same cleanup pass they have always received. (Implementation note: the `autoclaude` shell loop dispatches this pass after each `claude` session that produced commits, scoped to `CLEANUP_SINCE..HEAD` for that session. A multi-session PRD therefore sees one pass per session-with-commits. Each individual pass still produces at most one cleanup commit, which is what this rule constrains.)
- If you cannot determine which commits belong to a listed qwen task, treat the full `CLEANUP_SINCE..HEAD` range as in scope (today's behavior). The qwen scope is additive, not a filter.

## File-tier scoping

Categorize each changed file in the diff into one of three tiers. The tier sets the per-file cleanup default — aggressive on freshly-created files (where slop concentrates), moderate on substantially-edited files, conservative on lightly-touched files (where you must not destabilize existing behavior).

Detection rules:

- **NEW** — the file was added in `CLEANUP_SINCE..HEAD`. List added files with `git log --diff-filter=A --name-only --format= $CLEANUP_SINCE..HEAD | sort -u`. If a file's path is in that list, it is NEW.
- **EXTENDED** — the file existed at `$CLEANUP_SINCE` (NOT in the NEW list) AND the diff covers ≥50% of the file's current line count. For each non-NEW changed file, read `added_plus_removed` from `git diff --numstat $CLEANUP_SINCE..HEAD <file>` (columns 1 and 2 summed), and `current_lines` from `wc -l <file>`. If `(added_plus_removed) / max(1, current_lines) ≥ 0.5`, the file is EXTENDED.
- **TOUCHED** — everything else. The file existed at `$CLEANUP_SINCE` and the diff is <50% of its current size.

Per-tier cleanup defaults (referenced from "Decision rules" below):

| Tier | Default | Examples of what to aggressively remove |
|------|---------|------------------------------------------|
| NEW | **Aggressive**: delete anything not directly required by tests, the task description, or existing-behavior preservation. The verification step below re-runs tests after each removal; anything that breaks tests gets restored. The operator can restore further from git history if needed. | Defensive guards for unreachable states, single-caller abstractions, restating docstrings, "robust" error messages without context, premature configuration, framework-verification tests. |
| EXTENDED | **Moderate**: delete defensive boilerplate, restating comments, weak tests; preserve existing patterns and shapes. | Mock-confirming tests, paraphrasing comments, debug prints, dead imports added in the diff. |
| TOUCHED | **Conservative**: mechanical removals only (debug prints, commented-out code, dead imports added in the diff). Do not restructure. | Debug `print` / `console.log` / `eprintln!` added in the diff; commented-out code added in the diff. |

The tier governs the default when a deletion call is ambiguous. The catalog of slop patterns (below) is the same across tiers — only the "when in doubt" bias differs.

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

Tests that only prove the runtime or framework works, not the project's behavior.

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

### 16. AI-style docstrings

Remove multi-paragraph docstrings on trivial functions. Remove docstrings that paraphrase the function name or restate its arguments — when the function is well-named, the docstring is noise. Remove "this function does X by calling Y" preambles that describe implementation rather than contract. Keep docstrings that capture non-obvious intent, invariants, or constraints.

### 17. Trivial-type validation

Remove runtime type guards, JSON schemas, or pydantic models that duplicate compile-time guarantees in a fully-typed file. Examples: `isinstance(x, int)` inside a function whose signature is `x: int`; a pydantic model declared for a function-internal dict whose shape is already pinned by the caller's types. Keep validation at real system boundaries (request bodies, file inputs, external API responses).

### 18. Single-instantiation factories

Inline factory functions, builders, or wrapper classes called from exactly one place where direct construction reads more clearly. A factory pattern only earns its complexity when multiple call sites benefit; before there are multiple call sites, the abstraction is speculative.

### 19. Speculative configuration

Remove config flags, env vars, options parameters that have exactly one used value across the codebase. Configuration is a contract with future readers — exposing one without a current consumer adds maintenance burden for no benefit.

### 20. Restating comments

Remove comments that say what the next line of code already says. Examples: `// increment counter` above `counter += 1`; `# parse the response` above `data = json.loads(raw)`. Keep comments that explain non-obvious why (invariants, workarounds, constraints).

### 21. Framework-verification tests

A more explicit subsection of #2. Remove tests asserting only "import works", "function exists", "method returns truthy" without exercising business logic. Remove mock-confirming tests (the only assertion is `mock.assert_called_with(...)`). Remove snapshot tests where the shape itself is not the contract — they catch any change, including correct ones. Keep behavior assertions that fail when business logic changes.

## What to keep

- Business logic tests, integration tests, and boundary tests.
- Error handling at system boundaries.
- Production logging and observability.
- Documentation that explains non-obvious intent or constraints.
- Abstractions that have more than one consumer or clear testability value.
- Dependencies that are actively used and justified.

## Fix in place, don't delete

- Missing boundary error handling.
- Security issues.
- Violations of project conventions.
- Incomplete implementations that currently fail silently.

## Decision rules

- **NEW files: when in doubt, delete and note in the report.** The verification step below re-runs tests after each removal; anything that breaks tests is restored automatically. The operator can restore further from git history if behavior breaks subtly. This bias flip is intentional: NEW files concentrate slop (scaffolding bias, defensive defaults, AI-generated patterns) and the cost of being wrong is bounded by git.
- **EXTENDED and TOUCHED files: when in doubt, prefer the smallest safe change.** Existing patterns and shapes often encode invariants that the diff alone does not expose. Bias toward keeping; surface the concern in the report so the operator can revisit later.
- If a test is weak, either strengthen it or remove it; do not grow the suite unnecessarily.
- If correctness is uncertain on EXTENDED or TOUCHED files, keep the code and note the concern in the report. On NEW files, attempt the deletion and let the test re-run be the safety net.
- Every remaining change must have a clear purpose tied to cleanup.

## Verification

1. Run the project's test suite.
2. Run linting and formatting.
3. If a cleanup change causes failures, restore that specific change and re-run.
4. Re-check the remaining diff and ensure it is minimal and purposeful.
5. If new dependencies were introduced in the reviewed changes, verify they resolve and are actually used.

## Examples

Four worked examples — read these before tackling unfamiliar slop. Pattern recognition from concrete code beats abstract rules.

### Example 1: Bloated implementation (NEW file)

Original (NEW file `format_subject.py`):

```python
def format_email_subject(prefix: str, summary: str) -> str:
    """
    Format an email subject line by combining a prefix with a summary.

    This function takes a prefix string (typically representing a category
    or label) and a summary string (the actual content) and combines them
    into a properly-formatted email subject line. The prefix is enclosed
    in square brackets and separated from the summary by a single space.

    Args:
        prefix: The category prefix for the subject line.
        summary: The summary content to follow the prefix.

    Returns:
        A formatted email subject string of the form "[prefix] summary".

    Raises:
        ValueError: If either prefix or summary is an empty string.
        TypeError: If either argument is not a string.
    """
    if prefix is None or not isinstance(prefix, str):
        raise TypeError(f"prefix must be str, got {type(prefix)}")
    if summary is None or not isinstance(summary, str):
        raise TypeError(f"summary must be str, got {type(summary)}")
    if not prefix:
        raise ValueError("prefix must be non-empty")
    if not summary:
        raise ValueError("summary must be non-empty")
    prefix_stripped = prefix.strip()
    summary_stripped = summary.strip()
    return f"[{prefix_stripped}] {summary_stripped}"
```

Cleaned:

```python
def format_email_subject(prefix: str, summary: str) -> str:
    return f"[{prefix.strip()}] {summary.strip()}"
```

Reason: the function's name and signature carry the entire contract. The docstring restated arguments (catalog #16). The `isinstance` checks duplicated the type signature (catalog #17). The `ValueError` raises had no current caller exercising them (catalog #4). On a NEW file with passing tests, all of this is slop.

### Example 2: Defensive impossibility (any tier)

Original:

```python
def select_tier(task: Task) -> str:
    if task.metadata.get("model") == "haiku":
        return "haiku"
    elif task.metadata.get("model") == "sonnet":
        return "sonnet"
    elif task.metadata.get("model") == "opus":
        return "opus"
    else:
        # Should never happen, but just in case
        try:
            unknown = task.metadata.get("model")
            raise ValueError(f"Unknown model tier: {unknown}")
        except Exception as e:
            print(f"WARNING: tier selection failed: {e}")
            return "sonnet"  # fallback
```

Cleaned:

```python
def select_tier(task: Task) -> str:
    return task.metadata["model"]
```

Reason: the dict-lookup-then-conditional pattern was redundant with the dict itself. The `try`/`except` wrapping a `raise` swallowed the same error it raised (catalog #5). The "should never happen" comment marks code that exists for a state the type system already rules out (catalog #4). If `model` can legitimately be absent, that is a system-boundary concern (validate at the boundary), not an in-flow defensive guard.

### Example 3: Single-caller factory (NEW file)

Original (NEW file `report_builder.py`, used from exactly one place):

```python
class ReportBuilder:
    def __init__(self):
        self._title = ""
        self._sections: list[str] = []

    def with_title(self, title: str) -> "ReportBuilder":
        self._title = title
        return self

    def add_section(self, section: str) -> "ReportBuilder":
        self._sections.append(section)
        return self

    def build(self) -> str:
        return self._title + "\n\n" + "\n\n".join(self._sections)


def render_report(title: str, sections: list[str]) -> str:
    return (
        ReportBuilder()
        .with_title(title)
        .add_section(sections[0] if sections else "")
        .build()
    )
```

(Single call site, in `cli.py`:)
```python
output = render_report(title="Daily Summary", sections=summary_lines)
```

Cleaned (`report_builder.py` deleted; `cli.py` becomes):

```python
output = "Daily Summary\n\n" + "\n\n".join(summary_lines)
```

Reason: the builder pattern's value is paid back when ≥2 call sites benefit from the fluent construction. With one call site, the abstraction is speculative (catalog #18). Inlining costs three lines and removes a file. If a second call site later materializes, that is the moment to extract a helper — not now.

### Example 4: AI-style docstring (any tier)

Original (function in an existing module):

```python
def add_attempt_to_state(task_id: str, attempt: dict) -> None:
    """
    Add an attempt entry to the state for the specified task.

    This function loads the current state from disk, locates the task
    with the matching task_id, appends the provided attempt dictionary
    to that task's attempts list, and writes the updated state back to
    disk atomically.

    Args:
        task_id: The unique identifier of the task to update.
        attempt: A dictionary containing the attempt entry to append.
    """
    state = _load_state()
    for task in state["tasks"]:
        if task["id"] == task_id:
            task.setdefault("attempts", []).append(attempt)
            break
    _save_state(state)
```

Cleaned:

```python
def add_attempt_to_state(task_id: str, attempt: dict) -> None:
    """Append `attempt` to the matching task's `attempts[]`. Atomic."""
    state = _load_state()
    for task in state["tasks"]:
        if task["id"] == task_id:
            task.setdefault("attempts", []).append(attempt)
            break
    _save_state(state)
```

Reason: the original docstring's prose paraphrased the function name and restated the parameter list (catalog #16). The one detail worth preserving — that the write is atomic — fits in a single line. The `Args:` block was pure restatement; the type hints already carry that information.

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
| AI-style docstrings | 4 | 0 |

Files by tier: NEW 3, EXTENDED 1, TOUCHED 5.

Removed 3 debug statements, 4 AI-style docstrings, and fixed 2 weak tests.
```

If nothing was changed, write:

```md
### De-sloppify

No slop found.
```

If no report file exists, skip reporting.
