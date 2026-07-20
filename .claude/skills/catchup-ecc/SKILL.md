---
name: catchup-ecc
description: Use when scanning new commits in the external affaan-m/everything-claude-code repo for ideas worth adopting. Triggers on "catchup ecc", "check ecc", "what is new in ecc", "check affaan".
---

# Catchup ECC

Review new commits in `affaan-m/everything-claude-code` since last check and surface changes worth adopting.

## Dependencies

- CLI: `gh`, authenticated - reads the `affaan-m/everything-claude-code` repo.
- Path: `~/.claude/dev/local/ecc-cursor` - cursor state (last SHA **and** its
  ISO 8601 commit date), created on first run. The aegis hook blocks shell
  redirects into `dev/local/`, so write the cursor with the Write tool, never
  `>` or `tee`.

## Step 1 - Read cursor

Read `~/.claude/dev/local/ecc-cursor`. Format — SHA and its ISO 8601 commit date, space-separated:

```
<last_commit_sha> <last_commit_iso8601_date>
```

e.g. `a1b2c3d4e5f6 2026-07-19T14:30:00Z`. **Old-format cursor** (a bare SHA, no date — written before this field existed): treat the date as absent, take the "no date" path in step 2, and re-init both fields in step 5.

If no cursor file exists (first run), fetch the latest commit's SHA **and its committer date** from the repo, write both to the cursor file, report "Cursor initialized at \<sha\> (\<date\>), nothing to compare yet" and stop.

## Step 2 - Fetch new commits

Use the GitHub API's `?since=<date>` **server-side** cursor — fetch only commits at/after the stored date, not the whole history:

```bash
gh api "repos/affaan-m/everything-claude-code/commits?since=<cursor_date>" -q '.[].sha'
```

This is far cheaper than `--paginate` over all history, and robust to a force-push (a date cursor does not depend on the exact SHA still existing). `since` is inclusive, so the boundary commit (the cursor's own SHA) may be re-returned — drop it by matching the stored SHA. **No date available** (old-format cursor, or a `since` query that errors): fall back to `gh api repos/affaan-m/everything-claude-code/commits --paginate -q '.[].sha'`, take the last 30, and note the gap in the report.

Save the command's output to `dev/local/tmp/ecc-commits.txt` with the **Write
tool** (shell redirects into `dev/local/` are blocked by the aegis hook).

If no new commits (the result is empty, or holds only the boundary SHA), report "No new changes since last check" and stop.

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

After review is complete (regardless of what the user adopts), write the new HEAD SHA **and its ISO 8601 committer date** (space-separated, the step-1 format) to `~/.claude/dev/local/ecc-cursor` with the Write tool. Recording the date is what lets the next run use the `?since=` server-side cursor.

## Edge cases

| Situation | Action |
|-----------|--------|
| Cursor file missing | Initialize with SHA + date and stop (first run) |
| Old-format cursor (bare SHA, no date) | Take the no-date fallback in step 2 (paginate, last 30), re-init both fields in step 5 |
| Cursor SHA not in history (force-push) | The `?since=<date>` query still works (date-based, not SHA-based); note the gap if the boundary SHA is absent from the result |
| `gh` not authenticated | Ask user to run `! gh auth login` |
| Rate limit hit | Report and suggest trying later |
| Repo renamed/deleted | Report error and stop |
