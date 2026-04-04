# Code Review Standards

## When to Review

Mandatory triggers:
- After writing or modifying code
- Before any commit to shared branches
- When security-sensitive code changes (auth, payments, user data)
- When architectural changes are made

## Review Checklist

- [ ] Code is readable and well-named
- [ ] Functions are focused (<50 lines)
- [ ] Files are cohesive (<800 lines)
- [ ] No deep nesting (>4 levels)
- [ ] Errors handled explicitly
- [ ] No hardcoded secrets or credentials
- [ ] No debug statements left in
- [ ] Tests exist for new functionality
- [ ] Test coverage meets 80% minimum

## Security Review Triggers

Stop and review carefully when touching:
- Authentication or authorization code
- User input handling
- Database queries
- File system operations
- External API calls
- Cryptographic operations
- Payment or financial code

## Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| CRITICAL | Security vulnerability or data loss risk | BLOCK - must fix |
| HIGH | Bug or significant quality issue | Should fix before merge |
| MEDIUM | Maintainability concern | Consider fixing |
| LOW | Style or minor suggestion | Optional |

## Common Issues to Catch

**Performance**: N+1 queries, missing pagination, unbounded queries, missing caching.
