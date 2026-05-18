# Codex Integration

How to invoke Codex for task implementation. Dispatch the `use-codex` helper script (`~/.claude/skills/use-codex/scripts/codex-run.sh`) - never call `codex`/`copilot` directly. The helper auto-detects its backend: the native `codex` CLI when installed, the `copilot` CLI as fallback. On the copilot backend it defaults to `gpt-5.4` (1x multiplier); on the codex backend it uses codex's own configured default. See the `use-codex` skill for the full flag reference.

## Prompt Template

```
Task: {task.subject}

Description:
{task.description}

Acceptance Criteria:
{task.acceptance_criteria or "Complete the task as described"}

Architecture:
{relevant sections from AGENTS.md or agent_docs/architecture.md}

Key invariants:
{domain rules and boundaries from AGENTS.md or agent_docs/}

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

These are `codex-run.sh` helper flags. Pass the prompt with `-f <file>`.

| Task type | Flags |
|-----------|-------|
| Analysis only | `-f prompt.txt` (default, read-only) |
| Code changes | `-a -f prompt.txt` (auto-approve tools) |
| Needs network or broad access | `-y -f prompt.txt` (full permissions) |

## TDD Implementation Mode (Ivan)

When tests already exist from step 2.7, use this prompt variant instead of the standard template:

```
Failing tests exist at: {test_file_paths}

Make all failing tests pass.

Architecture:
{relevant sections from AGENTS.md or agent_docs/architecture.md}

Key invariants:
{domain rules and boundaries from AGENTS.md or agent_docs/}

Context:
- Working directory: {cwd}
- Relevant files: {list files if known}

Rules:
1. Do NOT modify test files
2. Read the tests to understand expected behavior
3. Implement minimal code to pass all tests
4. Follow existing patterns and conventions
5. Run tests after implementation to verify
```

The task's acceptance criteria prose is intentionally omitted. Tests ARE the spec.

## Common Issues

### Timeout

The Codex agent has a context/time limit. Signs of timeout:
- Incomplete changes
- Missing files mentioned in plan
- Abrupt stop mid-implementation

**Fix**: Split task into smaller pieces.

### Context exceeded

Large codebases may exceed context window.

**Fix**:
- Specify exact files to work with
- Split into file-specific tasks
- Use `-d <DIR>` to narrow scope

### Wrong approach

Codex took an unexpected direction.

**Fix**:
- Be more specific in prompt
- Add constraints: "Do NOT create new files" or "Use existing X pattern"
- Reference specific files: "Follow pattern in src/existing.ts"
