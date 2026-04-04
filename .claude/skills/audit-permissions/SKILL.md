---
name: audit-permissions
description: >-
  Use when reviewing permission sprawl, after granting broad permissions,
  or periodically to find stale/unused permission grants. Triggers on
  "audit permissions", "permission sprawl", "check permissions",
  "stale permissions", "permission hygiene".
---

# Audit Permissions

Inventory all permission grants across settings files, flag overly broad patterns, and cross-reference against recent tool usage to identify removal candidates.

## Step 1: Discover permission sources

Read these files if they exist:

- `~/.claude/settings.json` (source: **global**)
- `.claude/settings.json` in the current working directory (source: **project**)

For each file, extract:

- `permissions.allow` array (the permission grants)
- `permissions.deny` array (explicit denials)

Each entry in `permissions.allow` follows the format `ToolName(pattern)` or just `ToolName` (no parens means no pattern restriction). Examples:
- `Bash(*)` - unrestricted Bash
- `Edit(./**)` - edit anything relative to project
- `Read(~/git/**)` - read any repo
- `Grep(*)` - grep anywhere
- `mcp__serena__*` - all serena MCP tools

Build a flat list of all permission entries with their source file.

## Step 2: Classify risk level

Assign each permission a risk level:

**CRITICAL** - unrestricted access to powerful tools:
- `Bash(*)` - unrestricted shell
- `Write(*)` or `Write(**)` - write anywhere
- `Edit(*)` or `Edit(**)` - edit anywhere
- `Read(*)` or `Read(**)` - read anywhere (secrets, keys, etc.)

**HIGH** - broad path wildcards on write-capable tools:
- `Edit(~/git/**)`, `Write(~/git/**)` - any repo file
- `Edit(./**)`, `Write(./**)` - any project file
- `mcp__*__*` patterns granting all tools on an MCP server
- `Bash(<tool>:*)` for tools with destructive subcommands (docker, kubectl, git)

**MEDIUM** - tool-specific wildcards with bounded scope:
- `Bash(docker build:*)`, `Bash(npm:*)` - specific tool, all args
- `WebFetch(*)` - fetch any URL
- `Read(~/git/**)` - read any repo (lower risk since read-only)

**LOW** - narrow, well-scoped patterns:
- `Grep(*)`, `Glob(*)` - search-only tools
- `Read(~/.claude/skills/**)` - read skill files
- `WebSearch` - no pattern, single capability
- `Write(./**/dev/local/**)` - scoped write path

## Step 3: Cross-reference with session usage

Check tool usage observations at `~/.claude/instincts/projects/`. The project registry at `~/.claude/instincts/projects.json` maps project hashes to names.

For each project directory, read the `observations.jsonl` file. Each line is JSON:
```json
{"ts":"2026-04-01T10:19:12Z","tool":"Edit","in":{"file_path":"/path"},"out":"ok","sid":"...","pid":"..."}
```

For each permission in the allow list, search observations for matching tool calls:
- Match by tool name (the part before the parentheses)
- For path-based permissions, check if observed `file_path` or `path` values fall within the permission's pattern
- For `Bash(command:*)` patterns, check if the observed `command` field starts with the command prefix
- Record the most recent `ts` for each permission

If a permission has no matching observations across any project, mark it as **never exercised (in tracked history)**.

If a permission was last exercised more than 30 days ago, note the age.

Also check the warden audit log at `~/.claude/warden-audit.jsonl` for Bash command usage. Each line:
```json
{"ts":"...","sid":"...","cmd":"...","decision":"allow","reason":"ok",...}
```

## Step 4: Check for warden overlap

Read `~/.claude/warden.yaml` (user-level) and `.claude/warden.yaml` (project-level) if they exist.

Identify cases where a native permission grant (`Bash(*)` or `Bash(command:*)`) overlaps with warden's `alwaysAllow` list. Both layers independently allow the same command, so one is redundant.

For example, if `Bash(*)` is in settings permissions AND warden has `alwaysAllow: [npm, node, python3]`, those warden entries are redundant because `Bash(*)` already allows everything.

Conversely, if warden `alwaysAllow` covers all the commands a user actually runs, the broad `Bash(*)` permission may be unnecessary.

Report overlaps as informational findings.

## Step 5: Review deny permissions

List all entries from `permissions.deny`. For each, verify the denied pattern is still relevant (e.g., the sensitive files still exist or the pattern still makes sense).

Flag any deny entries that conflict with allow entries (allow is broader than deny, so deny may not be effective depending on evaluation order).

## Step 6: Present results

Format output as:

```
PERMISSION SPRAWL AUDIT
=======================

CRITICAL ({count}):

  1. {pattern} in {source}
     Risk: {why this is dangerous}
     Last used: {date or "never exercised" or "always (matches everything)"}
     Warden overlap: {if applicable}
     Fix: {specific remediation}

HIGH ({count}):

  2. {pattern} in {source}
     Risk: {why this is broad}
     Last used: {date}
     Fix: {specific remediation}

MEDIUM ({count}):

  3. {pattern} in {source}
     Last used: {date} — {N} days ago
     Fix: {suggestion}

LOW ({count}):
  (list briefly, no fix needed)

DENY RULES ({count}):
  {list deny entries and any conflicts}

WARDEN OVERLAPS ({count}):
  {list redundant entries across permission and warden layers}

UNUSED PERMISSIONS ({count}):
  {permissions with no observed usage or >30 days stale}

Summary: {critical} critical, {high} high, {medium} medium, {low} low — {actionable} permissions worth reviewing
```

Omit sections with zero entries.

## Step 7: Offer remediation

For CRITICAL findings, recommend specific narrower replacements. Examples:
- `Bash(*)` -> remove and rely on warden rules + specific `Bash(git:*)` patterns
- `Edit(./**)` -> acceptable if only used per-project, flag if in global settings
- `Write(*)` -> scope to specific directories

For unused permissions (never exercised or >30 days), recommend removal.

Ask the user which permissions they want to tighten or remove before making changes.
