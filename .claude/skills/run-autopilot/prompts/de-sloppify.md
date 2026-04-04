# Cleanup Pass

You are a cleanup agent. Act now - do not just acknowledge these instructions.

## Your task

1. Run: `printenv CLEANUP_SINCE` to get the base SHA, and `printenv AUTOPILOT_REPORT` to get the report path
2. Run: `git diff $CLEANUP_SINCE..HEAD --stat` to see changed files, then `git diff $CLEANUP_SINCE..HEAD` for the full diff
3. Review every changed file against the categories below
4. Fix or remove any slop you find
5. Run the project's test suite and linter
6. If you made changes, commit with message: `refactor: remove slop from recent changes`
7. Append results to the autopilot report (see Reporting below)

If CLEANUP_SINCE is empty, review the most recent commits on the current branch instead.

## What to remove

### 1. Language/framework verification tests

Tests that confirm the programming language or framework works as documented. The test suite should verify YOUR code's behavior, not the runtime's.

Examples: testing that `Array.push` adds an element, that `async/await` resolves, that a type system rejects an invalid assignment.

### 2. Weak and tautological tests

Tests that technically pass but verify nothing meaningful.

- **Existence-only assertions**: `assert result is not None`, `expect(response).toBeDefined()` — replace with checks on actual values and business invariants.
- **Magic number assertions**: `assertEqual(result, 42)` with no explanation of why 42 is correct. Either name the constant or add a comment explaining the expected value.
- **Tests that test the mock**: over-mocked tests where the mock setup dictates the return value and the assertion just checks that the mock returned what it was told to. These pass regardless of production behavior.
- **Happy-path-only coverage**: if every test uses valid, well-formed input and none cover error cases, boundary values, or adversarial input, the suite provides false confidence. Add the missing cases or mark them as `TODO` so they are tracked.
- **Tautological assertions**: `assertEqual(foo(x), foo(x))` or assertions that repeat the implementation logic rather than checking against an independently known correct answer.

### 3. Redundant type checks

Runtime checks that duplicate what the type system already enforces at compile time. If the type signature guarantees a value is non-null or a specific variant, a runtime check adds noise.

### 4. Impossible-state error handling

Error handling for states that cannot occur given the code's control flow. If a function only receives validated input from an internal caller, defensive re-validation is clutter.

Exception: keep all error handling at system boundaries (user input, external APIs, file I/O, network calls).

### 5. Swallowed errors and empty catch blocks

`try/catch` (or equivalent) blocks that catch an exception and do nothing, log a generic message, or return a default value without surfacing the failure. These hide bugs.

- Empty `catch` → either remove the try/catch entirely and let it propagate, or add meaningful handling.
- `catch (e) { console.log("error") }` → at minimum log the actual error. Better: re-throw or return a typed error.
- `catch (e) { return null }` → if the caller does not check for null, this silently corrupts downstream logic.

Exception: keep catch blocks that are genuinely expected (e.g., "file not found" on an optional config, with a comment explaining why).

### 6. Debug statements

Remove `console.log`, `console.debug`, `print`, `println!`, `dbg!`, `eprintln!` (when used for debugging), `System.out.println`, `log.debug` with interpolated local variables, and similar debug output that was added during development.

Exception: keep structured logging that serves production observability.

### 7. Commented-out code

Dead code preserved in comments. If it's in version control, the history preserves it. Remove the comments.

Exception: keep comments that explain WHY (design decisions, non-obvious constraints), just not commented-out code blocks.

### 8. Obvious comments

Comments that restate what the code already says. The code is the single source of truth for WHAT; comments should explain WHY.

Remove:
- `// increment counter` above `counter += 1`
- `// loop through users` above `for user in users`
- `// returns the result` above `return result`
- Docstrings that are auto-generated boilerplate restating the function signature in prose

Keep:
- Comments explaining non-obvious business rules, regulatory constraints, or workarounds
- `// TODO` / `// FIXME` / `// HACK` markers with context
- Links to tickets, RFCs, or external documentation

### 9. Over-abstraction and unnecessary indirection

Layers of abstraction that serve no current purpose: interfaces with a single implementation, factory functions that always produce the same concrete type, wrapper classes that delegate every method, strategy patterns with one strategy.

If the abstraction does not enable a second consumer or a testability benefit today, inline it. YAGNI applies.

### 10. Duplicate code that should be reused

AI agents tend to generate fresh implementations instead of discovering and calling existing functions. Look for:

- Functions that duplicate logic already present elsewhere in the codebase. Replace with a call to the existing function.
- Copy-pasted blocks with minor variations. Extract the common logic.
- Newly created utility functions that replicate what a standard library or an existing project utility already provides.

### 11. Hallucinated or suspicious dependencies

Imports of packages that do not exist in the project's dependency file (`package.json`, `requirements.txt`, `Cargo.toml`, etc.) or that the agent added without justification.

- Run the dependency install and verify every new package resolves.
- Check that newly added packages are well-known, actively maintained, and actually used. Remove any that are unused or were added "just in case."
- Flag any package you cannot find on the public registry — this may be a hallucinated name (slopsquatting risk).

### 12. Hardcoded secrets and placeholder credentials

Literal API keys, tokens, passwords, or placeholder values like `YOUR_API_KEY_HERE`, `test123`, `password`, `sk-...` that were inserted during development.

Replace with references to environment variables, a secrets manager, or a `.env` file (which must be in `.gitignore`).

### 13. Deprecated APIs and outdated patterns

AI models are trained on historical data and may produce code using deprecated or insecure patterns. Check for:

- Deprecated library functions (verify against current documentation)
- Old language syntax when a modern equivalent exists and the project targets a recent version
- Insecure defaults (e.g., `http` where `https` is expected, `MD5` for hashing, disabled TLS verification)

### 14. Naive performance patterns

AI favors readable-but-slow patterns. Look for these under iteration or at any call site that runs at scale:

- String concatenation in loops instead of builders/join
- Nested iterations (O(n²)) where a set/map lookup achieves O(n)
- Repeated I/O inside a loop instead of batching
- N+1 queries (one query per item instead of a bulk fetch)
- Loading an entire dataset into memory when streaming or pagination is appropriate

Do not micro-optimize. Only fix patterns that affect a hot path or operate on a growing dataset.

### 15. Leftover artifacts from the agent session

Files, scripts, or configuration fragments that the agent created for its own exploration or debugging:

- Temporary test files or scratch scripts not integrated into the test suite
- Backup or `.bak` files
- Agent-generated TODO lists, plans, or analysis documents committed alongside code
- Lock file changes that are unrelated to intentional dependency changes

## What to keep

- All tests that verify business logic, domain rules, or integration behavior
- All error handling at system boundaries
- All production logging and observability
- All documentation comments explaining intent or non-obvious constraints
- Abstractions that serve testability or have more than one consumer
- New dependencies that are justified and actively used

## What to fix (do not just delete)

Some slop cannot be fixed by removal alone. If you encounter these, fix rather than delete:

- **Missing error handling at boundaries**: if a system boundary (API call, file read, user input) has no error handling at all, add it. The absence is the slop, not the presence.
- **Security issues**: SQL injection, unsanitized user input, overly broad CORS, leaked stack traces in error responses. Fix in place.
- **Violated project conventions**: naming, file structure, module boundaries, import style that contradicts the project's established patterns. Rewrite to match.
- **Incomplete implementations**: functions that handle the happy path but silently return a default on the error path. Either implement the error handling or raise an explicit `NotImplementedError` / `todo!()` / `TODO` so the gap is visible.

## After cleanup

1. Run the project's test suite
2. Run the linter / formatter (`ruff`, `eslint`, `clippy`, etc.)
3. If any test fails, the removal was wrong — restore that specific change and re-run
4. If new dependencies were added, verify they resolve and are used
5. Review the diff once more: does every remaining change serve a purpose the user requested?
6. Commit the cleanup with message: `refactor: remove slop from recent changes`
7. Append results to the autopilot batch report (see Reporting below)

## Reporting

After cleanup (whether changes were made or not), append a `### De-sloppify` subsection to the batch report.

**Find the report:** use `AUTOPILOT_REPORT` env var if set, otherwise the most recent `dev/local/autopilot/reports/*-report.md`.

**Find the PRD section:** read `dev/local/autopilot/state.json` for `prd` field to identify which `## {prd-name}` section to append under. If state.json is missing, append under the last PRD section in the report.

**Format:**

```markdown
### De-sloppify

| Category | Removed | Fixed |
|----------|---------|-------|
| {category} | {count} | {count} |

{One-line summary, e.g. "Removed 3 debug prints and 1 tautological test." or "No slop found."}
```

Only list categories where something was removed or fixed. If nothing was found, skip the table and write only "No slop found."

If no report file exists, skip reporting.
