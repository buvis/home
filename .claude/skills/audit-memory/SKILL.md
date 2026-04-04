---
name: audit-memory
description: >-
  Use when the user wants to validate memory index consistency, find stale memories, or clean up
  orphan/missing entries. Triggers on "audit memory", "memory staleness", "stale memories",
  "check memories", "memory cleanup", "memory audit".
---

# Audit Memory Staleness

Validate MEMORY.md index consistency, check memory content for staleness signals, and flag entries for review.

## Step 1: Discover all project memory directories

```
Glob("~/.claude/projects/*/memory/MEMORY.md")
```

Collect the list of project directories that have a memory folder with a MEMORY.md index.

Also find memory files that exist outside any indexed project (orphan directories):

```
Glob("~/.claude/projects/*/memory/*.md")
```

Build a map of project directory name to its memory files.

## Step 2: Parse each MEMORY.md index

For each MEMORY.md, read the file and extract index entries. Each entry is a markdown list item containing a markdown link followed by an em dash and a description. The link text is the title, and the link target is a filename relative to the memory directory. Extract each referenced filename from the link targets.

## Step 3: Check index consistency

For each project memory directory:

### Orphan index entries

For each filename referenced in MEMORY.md, check if the file exists:

```
Bash: test -f ~/.claude/projects/<dir>/memory/<filename> && echo EXISTS || echo ORPHAN
```

An orphan index entry references a file that does not exist on disk.

### Missing index entries

Compare the list of `.md` files actually present in the memory directory (excluding MEMORY.md itself) against the filenames referenced in MEMORY.md. Any file present on disk but not listed in MEMORY.md is a missing index entry.

## Step 4: Read each memory file

For each memory file that exists on disk, read it and extract YAML frontmatter fields:

- `name`
- `description`
- `type` (one of: user, feedback, project, reference)

Also record the file's last modification date:

```
Bash: stat -f "%Sm" -t "%Y-%m-%d" ~/.claude/projects/<dir>/memory/<filename>
```

## Step 5: Check staleness by type

### Project memories (type: project)

Flag if the file is older than 30 days. Project context changes fast.

### Reference memories (type: reference)

Scan the file content for filesystem paths (patterns like `~/...`, `/Users/...`, `./...`). For each path found, verify it still exists:

```
Bash: test -e <path> && echo EXISTS || echo GONE
```

Flag any reference memory where a referenced path no longer exists.

### Feedback memories (type: feedback)

Scan the file content for specific file references (patterns like `src/...`, `lib/...`, filenames with extensions like `.ts`, `.py`, `.rs`, `.svelte`). For each specific file reference, resolve it relative to the project's source directory and check if it exists.

To find the project source directory: use the same resolution logic as audit-project-orphans (read `sessions-index.json` for `projectPath`, or decode the directory name).

Flag any feedback memory where referenced files no longer exist in the codebase.

### User memories (type: user)

Flag if the file is older than 6 months (180 days). User preferences change slowly but do drift.

### Unknown or missing type

Flag any memory file that has no `type` field in its frontmatter, or a type not in the known set.

## Step 6: Detect near-duplicates across projects

Collect all memory `name` and `description` fields across all projects. Flag pairs where:

- Names are identical or differ only by prefix/suffix (e.g., `feedback_local_writes` in two projects)
- Descriptions share 80%+ words (simple word-set overlap: intersection / union)

## Step 7: Output the report

Print the report in this format:

```
MEMORY STALENESS AUDIT
======================

Project: <directory-name> (<N> files)
  INDEX: <any orphan or missing index entries>
  <filename> --- <status> (<detail>)
  <filename> --- <status> (<detail>)

Project: <directory-name> (<N> files)
  <filename> --- <status> (<detail>)

Cross-Project Duplicates:
  <filename> in <project-a> ~ <filename> in <project-b>: <reason>

Summary: <N> memories checked, <N> orphan index, <N> missing index, <N> stale, <N> duplicates
```

Status values:
- `OK` - no issues found
- `STALE` - age threshold exceeded, with detail showing age and type threshold
- `ORPHAN INDEX` - referenced in MEMORY.md but file missing
- `MISSING INDEX` - file exists but not in MEMORY.md
- `BROKEN REF` - referenced path or file no longer exists, with detail showing which path
- `NO TYPE` - missing or unknown type in frontmatter

For OK entries, add a brief reason in parentheses:
- Reference type with verified paths: `(verified: <path> exists)`
- Feedback type with verified files: `(still applicable)`
- Project type within 30 days: `(<N> days old)`
- User type within 180 days: `(<N> days old)`

## Step 8: Offer actions

After displaying the report, ask the user which (if any) actions to take:

1. Fix orphan index entries (remove lines from MEMORY.md for missing files)
2. Add missing index entries to MEMORY.md
3. Review and delete specific stale memories
4. Do nothing

Wait for user input before making any changes.
