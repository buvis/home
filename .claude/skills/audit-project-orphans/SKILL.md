---
name: audit-project-orphans
description: >-
  Use when the user wants to find stale or orphaned project configs in ~/.claude/projects/.
  Triggers on "audit project orphans", "orphan projects", "stale projects", "clean up projects",
  "which projects are orphaned", "project cleanup".
---

# Audit Project Orphans

Check whether the source directory for each project config in `~/.claude/projects/` still exists on disk. Flag orphans and dormant projects.

## Step 1: List project directories

```
Bash: ls ~/.claude/projects/
```

Collect every directory name into a list.

## Step 2: Resolve each directory name to a filesystem path

For each project directory, resolve its original filesystem path using two strategies in order:

### Strategy A: Read sessions-index.json

If `~/.claude/projects/<dir>/sessions-index.json` exists, read it and extract the `projectPath` field from the first entry. This is the authoritative source path.

### Strategy B: Decode the directory name

If no sessions-index.json exists, decode the directory name:

1. The directory name encodes a full path where `/` is replaced by `-` and `.` is replaced by `-`.
2. To decode: replace the leading `-` with `/`, then replace each remaining `-` with `/`.
3. This produces a candidate path. Run `test -d <candidate>` to check existence.
4. If the candidate does not exist, try common dot-prefix corrections. The encoding turns `/.` into `--` (two consecutive hyphens become `/` + `/` which is wrong - the second segment should be dot-prefixed). Scan the decoded path for segments that look like they should be dot-prefixed: `claude`, `config`, `local`, `vifm`, `ssh`, `gnupg`, `cache`. For each `--` in the original directory name, try replacing the decoded `//` with `/.` and re-check with `test -d`.
5. If still unresolved, check if the directory contains `memory/MEMORY.md` or any `.jsonl` files. Read the first `.jsonl` file and look for a `projectPath` or `cwd` field in the JSON entries.

Record the resolved path (or "UNRESOLVED" if all strategies fail) for each project directory.

## Step 3: Check path existence

For each resolved path, run:

```
Bash: test -d "<path>" && echo EXISTS || echo ORPHAN
```

## Step 4: Get disk usage

For each project config directory:

```
Bash: du -sh ~/.claude/projects/<dir>
```

## Step 5: Get last session date

For each project directory:

1. If `sessions-index.json` exists, read it and find the most recent `modified` date across all entries.
2. If no sessions-index.json, find the most recently modified `.jsonl` file in the directory using `ls -t`. Use its filesystem modification date as the last session date.
3. If neither exists, report "unknown".

Format dates as YYYY-MM-DD.

## Step 6: Detect dormant projects

A project is dormant if:
- Its source path EXISTS on disk (not an orphan)
- Its last session date is more than 90 days ago from today

## Step 7: Output the report

Print the report in this exact format. Abbreviate long paths with `...` to keep alignment. Sort: EXISTS projects first (by last session date descending), then ORPHANs, then DORMANT.

```
PROJECT ORPHANS AUDIT
=====================

Project Path                                    Status      Last Session   Disk
────────────────────────────────────────────────────────────────────────────────
/Users/bob/.claude                              EXISTS      2026-04-03      8MB
/Users/bob/git/.../buvis/clara                  EXISTS      2026-03-28      4MB
/Users/bob/Downloads/beranky                    ORPHAN      2026-01-15      1MB
/Users/bob/vifm/Trash/000/beranky               ORPHAN      2025-12-01    512KB

Orphans: 2 configs, ~1.5MB reclaimable
Dormant (>90 days, not orphaned): 0

Suggested action: Review orphans and remove with:
  rm -rf ~/.claude/projects/<orphan-dir>
```

List each orphan's actual `rm -rf` command with the real directory name for easy copy-paste.

## Step 8: Offer archive option

After displaying the report, ask the user if they want to:
1. Delete specific orphan configs
2. Archive orphans to `~/.claude/projects-archive/` (move, not copy)
3. Do nothing

Wait for user input before taking any destructive action.
