---
name: catchup-ecc
description: Review new changes in affaan-m/everything-claude-code and surface ideas worth adopting. Triggers on "catchup ecc", "check ecc", "what's new in ecc", "scan ecc", "check affaan".
---

# Catchup ECC

Review new commits in `affaan-m/everything-claude-code` since last check and surface changes worth adopting.

## Step 1 - Read cursor

Read `~/.claude/dev/local/ecc-cursor`. Format:

```
<last_commit_sha>
```

If no cursor file exists (first run), fetch the latest commit SHA from the repo, write it to the cursor file, report "Cursor initialized at \<sha\>, nothing to compare yet" and stop.

## Step 2 - Fetch new commits

Use the GitHub API to list commits since the cursor SHA:

```bash
gh api repos/affaan-m/everything-claude-code/commits --paginate -q '.[].sha' > /tmp/ecc-commits.txt
```

Find commits newer than the cursor SHA. If the cursor SHA is not found in the list (history rewrite or too old), fetch the last 30 commits and note this in the report.

If no new commits, report "No new changes since last check" and stop.

## Step 3 - Review changes

For each new commit (oldest first):

1. Fetch the commit details: `gh api repos/affaan-m/everything-claude-code/commits/<sha>`
2. Note: files changed, commit message, diff content
3. Classify relevance to the user's `~/.claude` setup:
   - **interesting** - new skill, useful pattern, config improvement, hook idea
   - **skip** - repo-specific, cosmetic, or already covered in user's setup
   - **check** - needs user judgment (unclear value or potential conflict)

Focus on:
- New or updated skills (SKILL.md files)
- CLAUDE.md changes (instructions, workflows, conventions)
- Hook configurations
- MCP server setups
- Settings patterns
- Useful scripts or references

## Step 4 - Present summary

Show a table:

```
SHA (short) | message | classification | what's relevant
```

For each **interesting** or **check** item, include a brief note on what the user might want to adopt and how it differs from their current setup.

Wait for user input before making any changes.

## Step 5 - Update cursor

After review is complete (regardless of what the user adopts), write the new HEAD SHA to `~/.claude/dev/local/ecc-cursor`.

## Edge cases

| Situation | Action |
|-----------|--------|
| Cursor file missing | Initialize and stop (first run) |
| Cursor SHA not in history | Fetch last 30 commits, note gap |
| `gh` not authenticated | Ask user to run `! gh auth login` |
| Rate limit hit | Report and suggest trying later |
| Repo renamed/deleted | Report error and stop |
