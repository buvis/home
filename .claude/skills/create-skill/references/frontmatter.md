# Frontmatter Reference

All SKILL.md files begin with YAML frontmatter between `---` markers. All fields are optional. Only `description` is strongly recommended.

## Core Fields

### name

Display name for the skill. If omitted, the directory name is used.

- Lowercase letters, digits, and hyphens only
- Max 64 characters
- Must match the parent directory name
- Becomes the `/slash-command` name

```yaml
name: deploy-staging
```

### description

What the skill does and when to use it. This is the primary trigger mechanism - Claude reads all skill descriptions to decide which skills are relevant.

- Keep under 250 characters (truncated in context listing)
- Include specific trigger scenarios, file types, or task descriptions
- All "when to use" information belongs here, not in the body

```yaml
description: Deploy to staging environment. Use when user says "deploy to staging", "push to staging", or asks to test changes in staging.
```

## Invocation Control

### disable-model-invocation

When `true`, prevents Claude from auto-loading the skill. Users can still invoke it manually with `/name`. Default: `false`.

Use for skills with side effects (deploys, sends messages, modifies external state).

```yaml
disable-model-invocation: true
```

### user-invocable

When `false`, hides the skill from the `/` autocomplete menu. Claude can still invoke it automatically. Default: `true`.

Use for internal skills that should only trigger automatically.

```yaml
user-invocable: false
```

### Invocation Matrix

| Frontmatter | User can invoke | Claude can invoke |
|---|---|---|
| (defaults) | Yes | Yes |
| `disable-model-invocation: true` | Yes | No |
| `user-invocable: false` | No | Yes |

## Execution Control

### allowed-tools

Tools Claude can use without permission prompts when the skill is active. Space-separated string or YAML list.

```yaml
allowed-tools: Bash Read Write Edit
```

```yaml
allowed-tools:
  - Bash
  - Read
  - Write
```

### model

Override which model to use when the skill is active.

```yaml
model: sonnet
```

### effort

Override effort level. Options: `low`, `medium`, `high`, `max`.

```yaml
effort: max
```

### context

Set to `fork` to run the skill in an isolated subagent context. The subagent gets its own context window and returns results to the main conversation.

```yaml
context: fork
```

### agent

Which subagent type to use when `context: fork` is set. Options: `Explore`, `Plan`, `general-purpose`, or a custom agent name from `.claude/agents/`.

```yaml
context: fork
agent: Explore
```

## Scoping

### paths

Glob patterns limiting when the skill auto-activates. Only skills whose paths match the current working context are considered. Comma-separated string or YAML list.

```yaml
paths: "src/frontend/**"
```

```yaml
paths:
  - "src/frontend/**"
  - "*.svelte"
```

### argument-hint

Hint shown in autocomplete when the user types `/name`. Helps communicate expected arguments.

```yaml
argument-hint: "[environment] [--dry-run]"
```

## Advanced

### hooks

Hooks scoped to the skill lifecycle. Same syntax as settings.json hooks.

```yaml
hooks:
  PreToolUse:
    - matcher: Bash
      hooks:
        - command: echo "Skill is running a bash command"
          type: notification
```

### shell

Shell for `` !`command` `` blocks. Default: `bash`. Set to `powershell` for Windows (requires `CLAUDE_CODE_USE_POWERSHELL_TOOL=1`).

```yaml
shell: powershell
```

## Open Standard Fields

These fields come from the Agent Skills open standard (agentskills.io) and are recognized but not Claude Code-specific:

- `license` - License name or reference to bundled license file
- `compatibility` - Environment requirements (max 500 chars)
- `metadata` - Arbitrary key-value mapping

```yaml
license: MIT
compatibility: "Requires Python 3.10+"
metadata:
  version: "1.2.0"
  author: "team-name"
```
