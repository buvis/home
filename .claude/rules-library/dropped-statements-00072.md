# Statements dropped by PRD 00072

Archive of normative prose deleted from `~/.claude/rules/` by PRD 00072
("Slim the Always-Loaded Boot Prefix Content"), preserved here because
`rules-library/` is git-tracked and is not loaded into the session boot prefix.

This file covers 2 of the PRD's 4 deleting commits — `844b21d78` and
`3f9478fc8`, detailed in the sections below. The other two deleting commits
record their own drops in their commit bodies, not here: `8d5aea83b` (the
`rules/testing.md` condense) and `5bb54f288` (the personality-rules merge
into `rules/operating-principles.md`).

- Source files: `rules/patterns.md`, `rules/security.md`, `rules/code-review.md`
- Deleting commit: `844b21d78`
- Date: 2026-07-21
- Original (ephemeral) record: `dev/local/assumptions.md` task 4 — untracked and GC'd, which is why this copy exists

## rules/patterns.md (deleted whole, nothing folded forward)

- "Scope: these patterns apply only when their precondition holds. Simple scripts, CLIs, and single-backend apps are exempt; the Simplicity rules in `rules/coding-style.md` govern them."
- "Applies when a data layer has more than one real backend, or tests genuinely need to swap storage."
- "Define standard operations: findAll, findById, create, update, delete"
- "Concrete implementations handle storage details"
- "Business logic depends on the abstract interface, not storage"
- "One storage backend and no swap need: call it directly, no repository layer."
- "Applies to public-facing HTTP APIs."
- "Success/status indicator"
- "Data payload (nullable on error)"
- "Error message field (nullable on success)"
- "Metadata for paginated responses (total, page, limit)"
- "Internal tools and one-consumer endpoints may return the payload bare."

## rules/security.md (only the secret-rotation line was folded forward, into AGENTS.md)

- "The full checklist applies to network-facing services. Local CLIs and tools apply the relevant subset: secrets, plus input validation at trust boundaries." (the section's scoping preamble; dropped outright — not folded forward; absent from `rules/`, `rules-library/`, and `AGENTS.md`)
- "No hardcoded secrets (API keys, passwords, tokens)"
- "All user inputs validated"
- "SQL injection prevention (parameterized queries)"
- "XSS prevention (sanitized HTML)"
- "CSRF protection enabled"
- "Authentication/authorization verified"
- "Rate limiting on all endpoints"
- "Error messages don't leak sensitive data"
- "Use environment variables or a secret manager."
- "Validate required secrets are present at startup."
- Security Response steps 1, 2 and 4:
  - "STOP immediately"
  - "Fix CRITICAL issues before continuing"
  - "Review codebase for similar issues"
- Step 3 ("Rotate any exposed secrets") is covered by the fold — folded forward into AGENTS.md, not dropped.

## rules/code-review.md (only the review triggers and the N+1 emphasis were folded forward, into rules/development-workflow.md)

- The whole review checklist:
  - "Code is readable and well-named"
  - "Function/file size and nesting within limits"
  - "Errors handled explicitly"
  - "No hardcoded secrets or credentials"
  - "No debug statements left in"
  - "Regression tests cover new behavior"
- The `## Security Review Triggers` list:
  - "Authentication or authorization code"
  - "User input handling"
  - "Database queries"
  - "File system operations"
  - "External API calls"
  - "Cryptographic operations"
  - "Payment or financial code"
- The four-row severity table (CRITICAL/HIGH/MEDIUM/LOW definitions)
- "missing pagination, unbounded queries, missing caching"

## Deletions from commit 3f9478fc8 (enforced-prose trim, empty commit body)

Commit `3f9478fc8` trimmed four rule files to pointers at the aegis hooks that
enforce them, but shipped with no commit body, so these deletions were recorded
nowhere until now.

### rules/coding-style.md

- "Prefer immutable data to prevent hidden side effects, simplify debugging, and enable safe concurrency." → survives implicitly: the two bullets directly beneath it in the same Immutability section carry the actual per-language directive.
- "(e.g. `review-deps-prs`, not `dep-updates`)" — the parenthetical example dropped from the Naming bullet ("Name commands, skills, functions, and anything that performs an action starting with an action verb"). Not recorded elsewhere in `rules/`.
- The remaining hunks (the Production-Ready Code paragraph reflow, and the Warnings section's hook-filename correction `block-suppression-markers.py` → `block_suppression_markers.py`) are reword/correction-only — every fact present before the commit is still present after it.

### rules/tools.md

- "Check documentation for APIs and dependencies before writing code." (the whole `## Search and Documentation` section) → survives condensed in `rules/development-workflow.md` line 5, pipeline step 0: "check library docs for API behavior and version-specific details".
- "Don't pipe command output to `tail`/`head`/`grep` to trim it." — plus its two guidance sub-bullets:
  - "Run the command bare (`cargo test -p ddb-core`) - the Bash tool already truncates long output."
  - "If you need a specific slice, redirect to a file (`cargo test -p ddb-core > /tmp/ddb-test.log`) and `Read` it with `offset`/`limit`."
  → survives enforced: the **aegis** plugin's `prefer_tools.py` hook, documented in `aegis/rules/tools.md` line 21, carries the same guidance verbatim ("run `cmd` bare ... or redirect to a file ... and `Read` it with `offset`/`limit`"), and rules/tools.md's own "Tool vs. Bash (BLOCKING)" section already points readers at that doc.

### rules/development-workflow.md

- "(conventional commit format, no boilerplate trailers, no HEREDOC)" — the parenthetical detailing what "the full policy" covers, dropped from the sentence pointing at the `validate_commit_msg.py` hook. → survives: the **aegis** plugin's `rules/development-workflow.md` doc (lines 15-16, 22, 24) spells out the no-trailer/no-HEREDOC/conventional-format rules enforced by `validate_commit_msg.py`, and rules/development-workflow.md's pointer sentence already directs there.
- "templates" — dropped from pipeline step 0's search list ("Search GitHub for existing implementations, templates, and patterns" → "search GitHub for existing implementations and patterns"). Not recorded elsewhere in `rules/`.
- The remaining hunks (steps 1, 3, and 4 of the Feature Implementation Pipeline; the three Bug Fix Discipline bullets; the Commit Messages CRITICAL sentence) are reword/condense-only — every fact present before the commit is still present after it.

### rules/working-documents.md

- No normative statements were dropped from this file. Both hunks (the `dev/local/` paragraph and the "Layout (GC contract)" paragraph) are reword/condense-only — every fact present before the commit (dev/local location, gitignore requirement, hook name and behavior, GC retention specifics) is still present after it, just phrased more tersely.
