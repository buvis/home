---
name: audit-settings
description: >-
  Use when auditing settings for conflicts across levels, redundant overrides, permission
  escalations, or duplicate MCP servers. Triggers on "audit settings", "settings conflicts",
  "check settings consistency", "settings diff".
---

# Audit Settings Consistency

Compare settings across global, project, and local levels. Flag conflicts, redundancies, escalations, and unknown keys.

## Settings levels (highest priority wins)

1. **Global**: `~/.claude/settings.json` and `~/.claude/settings.local.json`
2. **Project**: `~/.claude/projects/<project-dir>/settings.json` and `settings.local.json`
3. **Local**: `.claude/settings.local.json` inside repo directories

Project overrides global. Local overrides project.

## Known settings keys

Valid top-level keys: `$schema`, `permissions`, `env`, `hooks`, `mcpServers`, `enabledPlugins`, `extraKnownMarketplaces`, `effortLevel`, `skipDangerousModePermissionPrompt`, `model`, `preferredNotifChannel`, `trustedDirectories`, `allowedTools`, `apiKeyHelper`, `customApiKeyResponses`, `enableAllProjectMcpServers`, `projects`.

Flag any key not in this list as potentially unknown (could be a typo).

## Step 1: Read global settings

Read both files. Either may not exist.

```
Read: ~/.claude/settings.json
Read: ~/.claude/settings.local.json
```

Merge them (local overrides global for same keys). This is the "effective global" config.

## Step 2: Find project settings

```
Glob: **/settings.json in ~/.claude/projects/
Glob: **/settings.local.json in ~/.claude/projects/
```

For each project directory that has settings, read and merge (local overrides non-local within same project).

## Step 3: Find local repo settings

Scan known repo roots for `.claude/settings.local.json`. Use the project directory names from `~/.claude/projects/` to derive repo paths (decode `-` to `/`, leading `-` to `/`). For each resolved path, check if `.claude/settings.local.json` exists there.

```
Glob: **/.claude/settings.local.json in ~/git/
```

## Step 4: Run comparisons

For every project and local config, compare against effective global. Check these categories:

### 4a: Permission escalation

Compare `permissions.allow` arrays. If a project or local config allows a tool pattern not covered by any global allow entry, flag it. This is not necessarily wrong (projects legitimately need project-specific permissions) but worth surfacing.

Severity: INFO for project-specific tool permissions. WARN if a project allows something the global config explicitly denies.

### 4b: Duplicate MCP servers

Compare `mcpServers` keys across levels. If the same server name appears at multiple levels:
- Same config: flag as NO-OP (redundant)
- Different config: flag as DUPLICATE with both configs shown

### 4c: No-op settings

Any key-value pair in a project or local config that is identical to the effective global value. These can be removed without changing behavior.

Compare scalar values directly. Compare arrays as sets (order-insensitive for permissions). Compare objects recursively.

### 4d: Conflicting values

Same key set to different values at different levels. Show both values and which level wins.

Severity: INFO (override system is working as designed, but worth knowing about).

### 4e: Unknown keys

Any top-level key not in the known keys list. Flag as WARN with suggestion to check for typos.

### 4f: Permission deny override

If a project or local config has `permissions.allow` entries that match patterns in the global `permissions.deny`, flag as CRITICAL. A lower level should not circumvent global deny rules.

## Step 5: Output report

```
SETTINGS CONSISTENCY AUDIT
==========================

Levels scanned: global + {N} project configs + {M} local configs

Findings:

  {number}. {SEVERITY} {CATEGORY}: {short description}
     Global: {value}
     Project ({name}): {value}
     Resolution: {which level wins}

Summary: {total} configs checked, {critical} critical, {warn} warnings, {info} info, {noop} no-ops
```

If no findings: `Settings audit: clean. No inconsistencies found across {N} configs.`

Omit the Global/Project/Local lines when not relevant to a finding. Keep each finding to 3 lines max.

## Step 6: Offer fixes

For NO-OP findings, offer to remove the redundant entries. For CRITICAL findings (deny overrides), warn strongly and offer to remove the offending allow entries. For other findings, explain but take no action unless asked.
