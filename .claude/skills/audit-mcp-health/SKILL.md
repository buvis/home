---
name: audit-mcp-health
description: Cross-reference configured MCP servers against live deferred tool list, check connection status, flag stale or unused servers. Triggers on "audit mcp", "mcp health", "check mcp servers", "stale mcp", "mcp cleanup".
---

# Audit MCP Server Health

Cross-reference configured MCP servers against the live deferred tool list. Detect disconnected, unused, or bloated servers. Report with actionable findings.

## Step 1: Gather configured servers

Read `~/.claude/settings.json` and extract the `mcpServers` object. Each key is a server name.

Then scan for project-level MCP configs:

```
Glob("~/.claude/projects/*/settings.json")
```

Read each project settings file and extract any `mcpServers` entries. Record for each server:
- Server name (the JSON key)
- Source: "global" (from `~/.claude/settings.json`) or "project" with project path

If a server name appears in both global and a project config, flag it as a duplicate in findings.

## Step 2: Count live tools from deferred tool list

The system prompt contains deferred tool entries. MCP tools use the prefix `mcp__<normalized_server>__<tool_name>`.

Server name normalization in the prefix: spaces become underscores, special characters are normalized. The prefix also includes the MCP hub name (e.g., `claude_ai_` for Claude.ai-hosted servers, `serena` for local servers). Examples:
- "Cloudflare Developer Platform" in settings -> `mcp__claude_ai_Cloudflare_Developer_Platform__*`
- "Google Calendar" in settings -> `mcp__claude_ai_Google_Calendar__*`
- "serena" in settings -> `mcp__serena__*`
- "youtube_transcript" in settings -> `mcp__youtube_transcript__*`

For each configured server, search the deferred tool list for matching `mcp__*` tool names. Use ToolSearch to query for each server's tools if needed.

Record per server:
- Tool count (number of matching deferred tool entries)
- Connection status: "Connected" if tool_count > 0, "Disconnected" if 0

## Step 3: Check session usage history

Grep the observations JSONL files for MCP tool invocations:

```
Grep(pattern: "mcp__", path: "~/.claude/instincts/projects", glob: "*.jsonl", output_mode: "content")
```

These files are written by the PostToolUse observe-tool hook. Each line is JSON with a `tool` field containing the tool name (e.g., `mcp__serena__find_symbol`). The `ts` field has the ISO timestamp.

For each configured server, find the most recent `ts` value from any matching `mcp__<server>__*` entry across all observation files. Record as "last used" date. If no matches, record "never".

## Step 4: Produce the report

Print the table:

```
MCP SERVER HEALTH AUDIT
=======================

Server                   Source    Tools   Status        Last Used
----------------------------------------------------------------------
Cloudflare               global      25   Connected     2026-04-01
Gmail                    global       6   Connected     2026-03-15
serena                   global      28   Connected     2026-04-03
Context7                 global       2   Connected     2026-04-02
Google Calendar          global       1   Connected     never
youtube_transcript       global       0   Disconnected  never
```

Sort order: Connected servers first (by tool count descending), then Disconnected.

## Step 5: Generate findings

Evaluate each server and list actionable findings numbered sequentially:

**Disconnected servers** (configured but no tools in deferred list):
- "{name}: configured but not connected (no tools in deferred list) - check server command/config or remove"

**Never-used servers** (connected but no invocations in observation history):
- "{name}: connected but never used in session history - consider removing"

**High tool count** (>20 tools) with low or no usage:
- "{name}: {count} tools, ~{count * 50} always-loaded tokens in deferred list - verify all needed"

**Duplicate configs** (same server name in global and project):
- "{name}: configured in both global and {project_path} - consolidate to avoid conflicts"

Only include findings that apply. If no findings, print "No issues found. All servers are connected and actively used."
