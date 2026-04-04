---
name: audit-plugins
description: >-
  Use when the user wants to check plugin freshness, find stale cached versions,
  identify unused plugins, or reclaim disk space.
  Triggers on "audit plugins", "plugin freshness", "stale plugins",
  "clean plugin cache".
---

# Audit Plugin Freshness

Inventory cached plugin versions, identify stale caches, flag unused plugins, and report disk usage.

## Step 1: Load installed plugin manifest

Read `~/.claude/plugins/installed_plugins.json`. Parse it to build the authoritative list of installed plugins. Each key in `.plugins` is `{name}@{org}`. Extract:

- Plugin name
- Org
- Installed version
- Install path
- Last updated timestamp
- Git commit SHA

## Step 2: Scan cache directory

Use Glob to find all version directories:

```
Glob("~/.claude/plugins/cache/*/*/*/.claude-plugin/plugin.json")
```

For each `plugin.json` found, Read it and extract:
- `name`, `version`, `description`

Group results by `{org}/{plugin}`. Build a map of all cached versions per plugin.

## Step 3: Identify active version

For each plugin, determine the active version:

1. Check the manifest from Step 1 for the installed version.
2. If the manifest version is "unknown", the install path itself is the active version directory.
3. Otherwise, the active version is the one matching the manifest's `version` field.

Sort remaining versions by semver. The active version is the one the manifest points to. All other cached versions are stale.

## Step 4: Calculate disk usage

For each version directory (the parent of `.claude-plugin/`), run:

```bash
du -sh {version_directory}
```

Record size per version. Sum stale version sizes for total reclaimable space.

Run each `du` command in a separate parallel Bash call for speed.

## Step 5: Check for unused plugins

Grep recent session JSONL files for plugin skill or command invocations:

```
Grep("~/.claude/projects/", pattern: "{plugin_name}")
```

Search in `*.jsonl` session files. A plugin with zero matches across all session data is potentially unused. Mark it as "no recent usage detected".

This step is best-effort. If no session data exists, skip and note that usage data is unavailable.

## Step 6: Output report

Print the report in this exact format:

```
PLUGIN FRESHNESS AUDIT
======================

Plugin                  Org                      Versions    Active     Disk
────────────────────────────────────────────────────────────────────────────────
superpowers             claude-plugins-official    2          5.0.7      12MB
warden                  buvis-plugins              1          0.6.2       4MB
pr-review-toolkit       claude-plugins-official    1          unknown     2MB

Stale versions to clean:
  superpowers 5.0.6 — 4MB

Total reclaimable: ~4MB

Unused plugins (no recent session activity):
  (none detected, or list plugin names here)

Summary: N plugins, N stale versions, NMB reclaimable
```

Adjust column widths to fit actual data. Use the Unicode box-drawing line character for the separator.

## Step 7: Offer cleanup

After presenting the report, ask the user if they want to remove stale version directories. If yes, delete each stale version directory with:

```bash
rm -rf {stale_version_directory}
```

Confirm each deletion. Do not delete active version directories.
