---
name: audit-context
description: Scan Claude Code setup and estimate context window token overhead per component. Classifies each as always-loaded, on-demand, or hidden tax. Reports with optimization recommendations. Triggers on "audit context", "check token usage", "context budget", "how much context am I using", "token overhead".
---

# Audit Context Budget

Scan the Claude Code setup, estimate token overhead per component, classify load behavior, and report with optimization recommendations.

## Step 1: Scan global config

Read these files and count characters/words:

```
Read ~/.claude/CLAUDE.md
Read ~/.claude/settings.json
```

Record for each:
- File path
- Character count
- Word count

## Step 2: Scan project configs

```
Glob("~/.claude/projects/*/CLAUDE.md")
Glob("~/.claude/projects/*/settings.json")
```

Read each file found. Record path, char count, word count.

## Step 2b: Scan memory files

```
Glob("~/.claude/projects/*/memory/MEMORY.md")
Glob("~/.claude/projects/*/memory/*.md")
```

MEMORY.md is auto-loaded for the active project in every conversation. Individual memory files referenced by MEMORY.md are loaded alongside it. These are always-loaded for the relevant project session.

Read each file found. Record path, char count, word count. Group by project.

## Step 3: Count MCP tools

Count actual MCP tools visible in the current session. Look at the system prompt's deferred tool list for `mcp__*` prefixed tools. Group by server prefix (e.g., `mcp__claude_ai_Gmail__*` = Gmail server). This is the authoritative count.

Also parse `~/.claude/settings.json` field `mcpServers` and each project settings.json to list configured servers. Cross-reference: if a configured server has no `mcp__*` tools in the deferred list, it may not be connected.

## Step 4: Estimate plugin overhead

Scan installed plugins. The cache structure is `{org}/{plugin}/{version}/`, so use 3 wildcards:

```
Glob("~/.claude/plugins/cache/*/*/*/agents/*.md")
Glob("~/.claude/plugins/cache/*/*/*/skills/*/SKILL.md")
Glob("~/.claude/plugins/cache/*/*/*/commands/*.md")
```

If multiple versions exist for the same plugin (e.g. `superpowers/5.0.5/` and `superpowers/5.0.6/`), use only the latest version directory. Sort version directories and pick the last one per plugin.

For each file found:
- Read it
- Record: plugin name, file type (agent/skill/command), char count, word count

Agent descriptions are the biggest concern - they load into every conversation as part of the Agent tool description.

## Step 5: Scan user skills

```
Glob("~/.claude/skills/*/SKILL.md")
```

For each skill:
- Read the file
- Record: skill name, char count, word count

User skills appear in the skill listing in every conversation but their full content loads only on invocation. For each skill, separately record:
- **Name + description** (from frontmatter): always loaded in the skill listing (~50-100 words per skill)
- **Full content** (entire SKILL.md): on-demand, loaded only when invoked via Skill tool

The same applies to plugin skills and commands from Step 4. Only the name+description snippet counts toward always-loaded overhead.

## Step 6: Estimate tokens

Apply these heuristics to each component:

| Content type | Formula | Rationale |
|-------------|---------|-----------|
| Prose (CLAUDE.md, agent descriptions, skill descriptions) | word_count x 1.3 | Prose tokenizes ~1.3 tokens per word |
| Code/config (settings.json, tsconfig, etc.) | char_count / 4 | Code/JSON tokenizes ~4 chars per token |
| MCP tool names (deferred list entries) | 50 per tool | Each deferred tool name is ~50 tokens (just the name string) |
| MCP tool full schemas (fetched via ToolSearch) | 500 per tool | Full schema is ~500 tokens (name + description + parameters), but on-demand |

## Step 7: Classify components

Assign each component one classification:

| Classification | Meaning | Examples |
|---------------|---------|----------|
| **Always loaded** | In context for every message | CLAUDE.md files, MCP tool *names* (deferred tool list), plugin agent descriptions (in Agent tool definition), plugin skill/command names (in skill listing), memory files (MEMORY.md per project) |
| **On-demand** | Loaded only when explicitly invoked | Skill full content (loaded on /skill-name), command content, MCP tool full schemas (loaded via ToolSearch) |
| **Hidden tax** | Loaded implicitly by common operations | Agent descriptions embedded in Agent tool - present whenever Agent tool is available, even if never spawned. |

Key distinction: skill *names and descriptions* are always loaded (they appear in the system prompt skill listing). Skill *full content* is on-demand (loaded only when invoked via Skill tool).

Similarly: MCP tool *names* appear in deferred tool lists (always loaded, ~50 tokens each). Full MCP tool *schemas* load only when fetched via ToolSearch (on-demand, ~500 tokens each). The always-loaded cost is the deferred tool name list, not the full schemas.

## Step 8: Output report

Print an ASCII table sorted by token estimate (descending):

```
CONTEXT BUDGET AUDIT
====================

Component                          Type           Class          Est. Tokens
─────────────────────────────────────────────────────────────────────────────
~/.claude/CLAUDE.md                Config         Always loaded      X,XXX
Cloudflare MCP (XX tool names)     MCP names      Always loaded      X,XXX
superpowers plugin (XX agents)     Plugin agents  Hidden tax         X,XXX
pr-review-toolkit (XX agents)      Plugin agents  Hidden tax         X,XXX
...                                ...            ...                  ...
─────────────────────────────────────────────────────────────────────────────
TOTAL ALWAYS LOADED                                                 XX,XXX
TOTAL HIDDEN TAX                                                     X,XXX
TOTAL ON-DEMAND (not counted)                                        X,XXX
─────────────────────────────────────────────────────────────────────────────
GRAND TOTAL (always + hidden)                                       XX,XXX
```

## Step 9: Recommendations

List top 3 optimization recommendations, ranked by potential token savings:

Format each as:
```
N. [Component]: [current tokens] tokens — [specific action]
   Savings: ~[tokens] tokens
```

Examples of actionable recommendations:
- "Cloudflare MCP: 25 tool names, ~1.3K always-loaded tokens (plus ~12.5K on-demand if schemas fetched) - consider disabling if not actively used"
- "superpowers plugin: 6 agent descriptions, ~8K tokens hidden tax - these load into every Agent tool call"
- "Project CLAUDE.md for inactive project: ~2K tokens - consider archiving"

## Step 10: Threshold warning

If total always-loaded + hidden-tax tokens exceed 30% of 1,000,000 (i.e., 300,000 tokens):

```
WARNING: Context overhead is {pct}% of your 1M context window.
Consider disabling unused MCP servers or plugins to free capacity.
```

If under threshold, print:
```
Context overhead: {pct}% of 1M window — within budget.
```
