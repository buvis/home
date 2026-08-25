# Frontmatter Reference

All SKILL.md files begin with YAML frontmatter between `---` markers.

`name` and `description` are **required** by the [Agent Skills standard](https://agentskills.io/specification); the validator errors without them. Everything under "Open Standard Fields" below is portable across every adopting agent (Claude Code, Cursor, Copilot, Gemini CLI, Codex, and others). Every other field on this page is a Claude Code extension: valid here, ignored elsewhere, and flagged by the validator as a portability warning. Use them when the skill is Claude Code-only, and prefer the standard fields when it is not.

## Core Fields

### name

Skill identifier. Required.

- Lowercase letters, digits, and hyphens only
- Max 64 characters
- No leading, trailing, or consecutive hyphens
- Must match the parent directory name
- Becomes the `/slash-command` name

```yaml
name: deploy-staging
```

### description

What the skill does and when to use it. Required. This is the primary trigger mechanism - Claude reads all skill descriptions to decide which skills are relevant.

- Standard caps it at 1024 characters; keep under 250 (truncated in context listing)
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

Portable across every Agent Skills agent, not Claude Code-specific:

- `license` - non-empty string: license name or the bundled license file
- `compatibility` - environment requirements, max 500 chars. Most skills do not need it
- `metadata` - map of **string keys to string values**. Quote numbers and booleans (`version: "1.2"`, not `version: 1.2`) or the validator errors
- `allowed-tools` - also standard, though experimental there and honored differently per agent

```yaml
license: MIT
compatibility: "Requires Python 3.10+"
metadata:
  version: "1.2.0"
  author: "team-name"
```

## Portability Checklist

A skill meant to run on other agents keeps to `name`, `description`, `license`, `compatibility`, `metadata`, and a body that names its own steps. Claude Code-only fields (`context: fork`, `model`, `effort`, `hooks`, `paths`, `agent`, `argument-hint`, `disable-model-invocation`, `user-invocable`, `shell`) silently do nothing elsewhere - so a skill that relies on `context: fork` for isolation or `hooks` for enforcement is Claude Code-only by construction. Say so in `compatibility`.
