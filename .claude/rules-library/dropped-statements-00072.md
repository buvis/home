# Statements dropped by PRD 00072

Archive of normative prose deleted from `~/.claude/rules/` by PRD 00072
("Slim the Always-Loaded Boot Prefix Content"), preserved here because
`rules-library/` is git-tracked and is not loaded into the session boot prefix.

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
