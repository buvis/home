# Codex Integration

How to invoke Codex via `copilot` CLI for task implementation. The helper script auto-detects the latest `gpt-*-codex` model from `copilot --help`.

## Prompt Template

```
Task: {task.subject}

Description:
{task.description}

Acceptance Criteria:
{task.acceptance_criteria or "Complete the task as described"}

Context:
- Working directory: {cwd}
- Relevant files: {list files if known}

Instructions:
1. Read existing code before making changes
2. Follow existing patterns and conventions
3. Run tests if available
4. Keep changes minimal and focused
```

## Permission Modes

| Task type | Flags |
|-----------|-------|
| Analysis only | `-p "prompt"` (default, interactive approval) |
| Code changes | `--allow-all-tools -p "prompt"` |
| Needs network or broad access | `--allow-all -p "prompt"` |

## Common Issues

### Timeout

Copilot has a context/time limit. Signs of timeout:
- Incomplete changes
- Missing files mentioned in plan
- Abrupt stop mid-implementation

**Fix**: Split task into smaller pieces.

### Context exceeded

Large codebases may exceed context window.

**Fix**:
- Specify exact files to work with
- Split into file-specific tasks
- Use `--add-dir <DIR>` to narrow scope

### Wrong approach

Codex took an unexpected direction.

**Fix**:
- Be more specific in prompt
- Add constraints: "Do NOT create new files" or "Use existing X pattern"
- Reference specific files: "Follow pattern in src/existing.ts"
