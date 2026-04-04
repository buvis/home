---
name: audit-rules
description: Use when auditing rule files for conflicts, redundancies, shadowing, or staleness across global and project scopes. Triggers on "audit rules", "rules conflicts", "check rules", "rules overlap", "rules redundancy", "rules audit".
---

# Audit Rules

Read all rule files across global and project scopes. Identify contradictions, redundancies, shadowing, and staleness. Output a structured report.

## Step 1: Collect global rules

```
Glob("~/.claude/rules/**/*.md")
```

Read every file found. For each, record:
- File path
- Word count
- Key topics covered (2-5 keywords)
- A brief summary of guidance given

## Step 2: Collect CLAUDE.md files

```
Read ~/.claude/CLAUDE.md
Glob("~/.claude/projects/*/CLAUDE.md")
```

Read each. Record the same fields. These contain instructions that may overlap with rule files.

## Step 3: Collect project rules

Check for project-level rule overrides:

```
Glob("~/.claude/projects/*/rules/**/*.md")
```

If any exist, read them. Record same fields plus which project they belong to.

Also check active repos for local `.claude/rules/` directories. To find repo paths, parse the project directory names under `~/.claude/projects/` (they encode the repo path with hyphens). Only check repos that are likely to exist on disk.

## Step 4: Analyze for findings

Compare all collected files semantically. Look for these categories:

### Contradictions

Rules giving opposing guidance on the same topic. Examples:
- "always mock external services" vs "never use mocks"
- "use tabs" vs "use spaces"
- One file says to do X, another says to avoid X

Rate severity: HIGH if guidance is directly opposed, MEDIUM if partially conflicting.

### Redundancy

Same guidance repeated across multiple files. Examples:
- TDD workflow described in both testing.md and development-workflow.md
- Immutability guidance repeated in coding-style.md and a language-specific file
- Same security checklist in security.md and a language-specific security file

For language-specific files that explicitly extend a common file (e.g., "This file extends common/coding-style.md"), check whether they duplicate content from the parent or genuinely add new guidance. Extension is fine; repeating the same rules is redundant.

### Shadowing

Project-level rules that silently override global rules without acknowledging the override. A project rule that says "extends" or "overrides" the global rule is fine. A project rule that gives different guidance on the same topic without referencing the global rule is shadowing.

### Staleness

Rules referencing tools, patterns, file paths, or conventions that may no longer exist:
- References to specific CLI tools not commonly installed
- File paths that don't exist
- Patterns referencing deprecated APIs or frameworks

### CLAUDE.md overlap

Content in CLAUDE.md that duplicates what rule files already cover. CLAUDE.md is always loaded; rule files are also always loaded for the relevant scope. Duplication wastes tokens.

## Step 5: Estimate token cost

Calculate total token overhead of all rules:

| Scope | Files | Words | Est. Tokens (words x 1.3) |
|-------|-------|-------|---------------------------|
| Global rules | N | N | N |
| Global CLAUDE.md | 1 | N | N |
| Project CLAUDE.md files | N | N | N |
| Project rules | N | N | N |
| **Total** | **N** | **N** | **N** |

## Step 6: Output report

Print the report in this exact format:

```
RULES AUDIT
===========

Scanned: {N} global rules, {N} CLAUDE.md files, {N} project rule overrides
Token cost: ~{N} tokens ({N} words across {N} files)

FINDINGS
--------

{number}. {CATEGORY}: {short title}
   Files: {path1}
          {path2}
   Detail: {what conflicts/overlaps and why it matters}
   Suggested fix: {specific actionable resolution}

...repeat for each finding...

If no findings in a category:
{number}. OK: No {category} detected

SUMMARY
-------
{N} rule files checked, {findings count by category}
Token overhead: ~{N} tokens (rules are always-loaded for their scope)
```

Categories appear in this order: Contradictions, Redundancy, Shadowing, Staleness, CLAUDE.md overlap.

Number findings sequentially across all categories.

## Analysis guidelines

- Prioritize actionable findings over noise. A testing.md and python/testing.md covering different aspects of testing is not redundancy. The same TDD steps copy-pasted into two files is.
- Language-specific rules that add detail beyond the common rule are not redundant. They are redundant only if they repeat the same guidance verbatim or near-verbatim.
- When suggesting fixes, prefer consolidation into one location over deletion. Specify which file should own the guidance.
- For contradictions, identify which rule should win and why (usually the more specific or more recent one).
