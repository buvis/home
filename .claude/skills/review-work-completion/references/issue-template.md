# Issue Documentation Format

## Single Issue

```
- [{severity}] {one-line description}
  - File: {path/to/file.ts:line}
  - Task: #{task-id}
  - PRD ref: {section} (if applicable)
  - Impact: {why this matters}
```

## Severity Guidelines

| Severity | Criteria | Examples |
|----------|----------|----------|
| Critical | Must fix before release | Security vulnerability, data corruption, crash |
| High | Blocks functionality | Missing required feature, incorrect behavior |
| Medium | Quality concern | Missing tests, poor error messages |
| Low | Nice to have | Style inconsistency, minor optimization |

## Grouping Issues

When multiple issues share a theme, group them:

```
### Auth Security Issues
- [High] Missing rate limiting on login endpoint
  - File: src/auth/login.ts:45
- [High] Password not hashed before storage
  - File: src/auth/register.ts:23
- [Med] No account lockout after failed attempts
  - File: src/auth/login.ts:50

→ Create single task: "Fix auth security gaps (M)"
```

## Issue → Task Mapping

| Issue count | Task approach |
|-------------|---------------|
| 1-2 related | Single task |
| 3-5 related | Single task with subtasks in description |
| 6+ related | Split into 2-3 themed tasks |
| Unrelated | Separate tasks |
