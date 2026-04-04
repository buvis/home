---
name: audit-skills
description: >-
  Use when validating skill health across personal and plugin directories.
  Runs structural validation and quality analysis. Triggers on "audit skills",
  "check skills", "skill compliance", "validate skills", "skill hygiene".
---

# Audit Skills

Run structural validation and quality analysis across all installed skills. Produces a unified compliance report.

## Step 1: Discover skills

### Personal skills

```
Glob("~/.claude/skills/*/SKILL.md")
```

### Plugin skills

```
Glob("~/.claude/plugins/cache/*/*/*/skills/*/SKILL.md")
```

If multiple versions exist for the same plugin (e.g., `superpowers/5.0.5/` and `superpowers/5.0.6/`), use only the latest version directory. Sort version directories and pick the last one per plugin.

### Plugin commands

```
Glob("~/.claude/plugins/cache/*/*/*/commands/*.md")
```

Same version-dedup rule applies.

Build a master list. Record each skill's:
- **path**: full path to SKILL.md
- **source**: "personal" or "plugin:{org}/{plugin}"
- **name**: directory name (skill dir) or filename (command)

## Step 2: Structural validation

For each personal skill, run the validator:

```bash
python3 ~/.claude/skills/create-skill/scripts/validate_skill.py <skill-dir>
```

Parse stdout for lines starting with `[ERROR]` or `[WARN]`. Record each with the skill name.

Skip plugin skills for structural validation (they follow their own conventions).

## Step 3: Quality checks

For each skill (personal and plugin), read the SKILL.md content and check:

### 3a: Description quality

Read the `description` field from frontmatter.

- **Error** if description summarizes step-by-step workflow instead of trigger conditions. Anti-pattern: describes what the skill *does* procedurally. Correct pattern: starts with "Use when...", "Triggers on...", or describes conditions/symptoms.
- **Warn** if description does not start with a trigger-oriented phrase.

### 3b: Body length

Count lines in the SKILL.md. **Warn** if over 500 lines.

### 3c: Content duplication

If a `references/` directory exists in the skill, read each file in it. Flag if significant content blocks (paragraphs of 3+ lines) appear in both the SKILL.md body and a references file. **Warn** on duplication.

### 3d: Script executability

If a `scripts/` directory exists:

```bash
test -x <script-path>
```

**Warn** for each non-executable script.

### 3e: Auxiliary docs

Check for files that do not belong in a skill directory:

```bash
test -f <skill-dir>/README.md
test -f <skill-dir>/CHANGELOG.md
```

**Warn** if any exist.

### 3f: At-path references

Search the SKILL.md body for `@`-path patterns (e.g., `@~/.claude/skills/...` or `@./references/...`). These force-load files into context. **Warn** if found; recommend referencing skills by name instead.

## Step 4: Cross-skill checks

### 4a: Duplicate names

Check for any skills sharing the same name across personal and plugin sources. **Error** on duplicates.

### 4b: Similar descriptions

Compare all skill descriptions pairwise. **Warn** when two skills have near-identical descriptions that would confuse skill selection (same trigger keywords, similar phrasing).

Use judgment: skills in the same domain (e.g., `audit-hooks` and `audit-plugins`) naturally share the word "audit" - that is fine. Flag only when the descriptions are so similar that Claude could not distinguish which skill to select.

### 4c: Metadata overhead

For each skill, estimate token cost of the name + description snippet (the always-loaded metadata). Use: word_count x 1.3 tokens.

Sum across all skills to get total metadata overhead.

## Step 5: Output report

Print in this format:

```
SKILLS COMPLIANCE AUDIT
=======================

Skills scanned: {N} personal + {M} plugin = {total} total

STRUCTURAL ERRORS (from validator):
  1. [ERROR] {skill-name}: {message}
     Fix: {suggested fix}

  2. ...

QUALITY WARNINGS:
  3. [WARN] {skill-name}: {message}
     Fix: {suggested fix}

  4. [WARN] {skill-name}: description summarizes workflow instead of triggers
     Current: "{first 80 chars of description}..."
     Fix: Rewrite to start with "Use when..." and list trigger conditions.

  5. ...

CROSS-SKILL:
  6. [ERROR] Duplicate name: "{name}" in {source1} and {source2}

  7. [WARN] {skill1} and {skill2}: near-identical descriptions
     Both mention "{overlapping keywords}"
     Fix: Differentiate trigger keywords.

  8. [INFO] Total skill metadata overhead: ~{N} tokens ({total} skills x ~{avg} tokens avg)

Summary: {errors} errors, {warnings} warnings, {infos} info
```

If no issues found in a section, print "None" under that heading.

## Step 6: Offer remediation

For actionable findings, offer to fix:

- Non-executable scripts: `chmod +x <path>`
- Auxiliary docs: remove them
- Broken references: remove link or create file

For description quality issues, suggest rewritten descriptions but ask before editing.
