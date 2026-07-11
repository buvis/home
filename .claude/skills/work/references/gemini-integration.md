# Gemini Integration

How to invoke Gemini for task implementation via the `~/.claude/skills/use-gemini/scripts/gemini-run.sh` helper, which wraps the native Gemini CLI. Always pass the prompt with `-f <file>`. With no `-m`, the CLI uses its default model.

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

All flags are passed to `gemini-run.sh`.

| Task type | Flags |
|-----------|-------|
| Analysis only | `-f prompt.txt` (no extra flags) |
| Code changes | `-a -f prompt.txt` (auto-approve edit tools) |
| Full autonomy | `-y -f prompt.txt` (auto-approve all tools) |
| Specific dirs | `-d <path> -f prompt.txt` |

## Execution Modes

| Mode | Flag | Use case |
|------|------|----------|
| Non-interactive | `-f prompt.txt` | Scripted execution, exits after completion |
| Interactive | `-i "prompt"` | Needs user input during execution |

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

### Session needs context

Gemini may need access to files outside the working directory.

**Fix**: Use `-d <path>` to grant access to additional directories.

### Tool approval interrupts

Default mode prompts for tool approval.

**Fix**: Use `-a` for auto-approval of edit tools, or `-y` for full permissions.

### Wrong approach

Gemini took an unexpected direction.

**Fix**:
- Be more specific in prompt
- Add constraints: "Do NOT create new files" or "Use existing X pattern"
- Reference specific files: "Follow pattern in src/existing.ts"

### Resume needed

Incomplete work needs continuation.

**Fix**: Use `gemini-run.sh -c` to resume the most recent session, or `-r <ID>` to pick a session.

## Design Authority (visual tasks)

For visual tasks, Gemini can challenge existing specs (moved here from
`SKILL.md` "Gemini as design authority"):

1. Share the planned design/spec with Gemini
2. Ask for critical review before implementation
3. **Trust Gemini's feedback** on visual matters - it has better taste
4. Adjust the plan based on its recommendations
5. Then proceed with implementation

Example prompt addition for visual tasks:

```text
Before implementing, critically review this design spec.
Suggest improvements to colors, spacing, typography, or layout.
Challenge anything that feels generic or could be more distinctive.
```
