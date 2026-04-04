---
name: audit-hooks
description: >-
  Use when validating hook health, debugging failures, after editing hooks in
  settings.json, or when tool calls feel slow. Checks existence, permissions,
  silent failures, performance. Triggers on "audit hooks", "check hooks",
  "hook hygiene".
---

# Audit Hooks

Validate all hooks configured in settings.json files. Check existence, permissions, silent failure suppression, and performance concerns.

## Step 1: Discover hook sources

Read these files if they exist:

- `~/.claude/settings.json` (source: **global**)
- `.claude/settings.json` in the current working directory (source: **project**)

For each file, parse the `hooks` key. The structure is:

```json
{
  "hooks": {
    "<EventType>": [
      {
        "matcher": "<optional tool/event matcher>",
        "hooks": [
          {
            "type": "command",
            "command": "<shell command>",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

Event types: `PreToolUse`, `PostToolUse`, `Notification`, `Stop`, `SessionStart`, `SubagentStop`.

Build a flat list of hook entries, each with:
- `event`: the event type
- `matcher`: the matcher string (or "all" if absent)
- `command`: the shell command string
- `timeout`: timeout value if set
- `source`: "global" or "project"

## Step 2: Resolve and check each command

For each hook command:

### 2a: Identify the executable

Parse the command string to find the executable. Handle these patterns:
- Direct script path: `~/.claude/hooks/foo.sh` - check that path
- Interpreter prefix: `python3 ~/.claude/hooks/foo.py` - check the script path (second token), not the interpreter
- Inline commands (e.g., `echo`, `test`, shell builtins) - mark as inline, skip file checks

Expand `~` to the actual home directory when checking paths.

### 2b: Check existence

```bash
test -f <resolved_path>
```

If missing, record finding: **CRITICAL** - "script not found: `<path>`"

### 2c: Check executability

For shell scripts (.sh, .bash, no extension without interpreter prefix):

```bash
test -x <resolved_path>
```

If not executable, record finding: **HIGH** - "script not executable: `<path>`"

Python scripts invoked via `python3` do not need the executable bit.

### 2d: Read script content for anti-patterns

For each script that exists, read its content. Check for these patterns:

| Pattern | Severity | Description |
|---------|----------|-------------|
| `2>/dev/null` | MEDIUM | Suppresses stderr, hides errors |
| `\|\| true` | MEDIUM | Swallows non-zero exit codes |
| `\|\| :` | MEDIUM | Same as `\|\| true` |
| `>/dev/null 2>&1` | MEDIUM | Suppresses all output |
| `set +e` | MEDIUM | Disables errexit, errors continue silently |
| `trap '' ERR` | HIGH | Ignores all errors via trap |

For MEDIUM findings on Notification hooks, note in the output that suppression may be intentional for non-critical notifications.

### 2e: Check for performance concerns

For **PreToolUse** hooks only (these run before every matching tool call):

Flag if the script contains:
- `curl`, `wget`, `fetch` - network calls add latency
- `npm`, `npx`, `cargo build`, `make` - heavy build operations
- `docker` - container operations
- `sleep` - explicit delays

Record finding: **MEDIUM** - "PreToolUse hook contains potentially slow operation: `<pattern>`"

Also flag any PreToolUse hook with `timeout` > 10 seconds as **MEDIUM** - "high timeout for PreToolUse hook (runs on every tool call)"

## Step 3: Check for duplicate event coverage

Group hooks by event + matcher. If multiple hooks from different sources (global and project) match the same event+matcher combination, record an informational note about execution ordering.

## Step 4: Output report

Print the report in this format:

```
HOOK HYGIENE AUDIT
==================

Hook                              Event          Source    Status
---------------------------------------------------------------
<label>                           <event>        <source>  <OK|WARNING|ERROR>
...

Findings:
  1. <label>: <description>
     Severity: <CRITICAL|HIGH|MEDIUM>

  2. ...

Summary: <N> hooks checked, <critical> critical, <high> high, <medium> medium, <ok> ok
```

For the hook label, derive a short name:
- From the script filename without extension: `protect-config.sh` becomes "protect-config"
- For interpreter-prefix commands: use the script name, e.g., `python3 ~/.claude/hooks/foo.py` becomes "foo"
- Append the matcher if present: "protect-config [Edit|Write|MultiEdit]"

If no findings exist, print:

```
Findings:
  No issues found. All hooks are healthy.
```

## Step 5: Offer remediation

For CRITICAL findings (missing scripts), ask if the user wants to remove the dead hook entry from settings.json.

For HIGH findings (not executable), offer to fix with `chmod +x`.

For MEDIUM findings, note they may be intentional and ask if the user wants details.
