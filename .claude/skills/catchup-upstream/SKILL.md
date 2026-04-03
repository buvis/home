---
name: catchup-upstream
description: Sync a fork with upstream by reviewing and selectively applying new commits. Triggers on "sync upstream", "catchup upstream", "check upstream", "what's new upstream", "sync fork".
argument-hint: "[owner/repo or GitHub URL]"
---

# Catchup Upstream

Review new upstream commits since last sync and selectively apply relevant changes.

## Step 1 — Resolve upstream repo

The argument can be:
- `owner/repo` (e.g. `banyudu/claude-warden`)
- A GitHub URL (e.g. `https://github.com/banyudu/claude-warden`)
- Omitted — read from `dev/local/upstream-cursor`

If no argument and no cursor, list non-origin remotes with `git remote -v` and ask the user which repo is the upstream.

### Find or create git remote

Normalize the input to a GitHub URL: `https://github.com/<owner>/<repo>.git`

Check if any existing remote points to that URL:

```bash
git remote -v
```

If a matching remote exists, use it. If not, add one using the owner as the remote name:

```bash
git remote add <owner> https://github.com/<owner>/<repo>.git
```

### Determine the default branch

```bash
git remote show <remote> | grep 'HEAD branch'
```

Use whatever branch upstream considers default (usually `main` or `master`).

## Step 2 — Fetch and find new commits

```bash
git fetch <remote>
```

Read `dev/local/upstream-cursor`:

```
<remote> <branch> <last_hash>
```

If no cursor exists (first run), set cursor to current `<remote>/<branch>` HEAD, write the cursor file, report "Cursor initialized at \<hash\>, nothing to compare yet" and stop.

List new commits:

```bash
git log --oneline <cursor_hash>..<remote>/<branch>
```

If empty, report "No new upstream commits" and stop.

## Step 3 — Review each commit

For each new commit (oldest first):

1. Show the diff: `git show <hash> --stat` then `git show <hash>` for full diff
2. Assess relevance:
   - Does it touch files/areas we've modified? Check with `git log --oneline --all -- <changed-files>` on our side
   - Is it a bugfix, feature, or refactor? Bugfixes are usually worth taking. Features depend on direction. Refactors may conflict.
   - Would it conflict with our changes? Check overlap in modified files and logic.
3. Classify as: **take** (apply), **skip** (not relevant or conflicts with our direction), or **ask** (needs user judgment)

Present a summary table to the user:

```
hash | subject | classification | reason
```

Wait for user confirmation before applying anything.

## Step 4 — Apply approved commits

For each approved commit, in order:

1. Try `git cherry-pick <hash>`. If it applies cleanly, move on.
2. If conflicts arise, assess whether manual adaptation is simpler than resolving the cherry-pick:
   - `git cherry-pick --abort`
   - Read the upstream diff and manually adapt the changes to our codebase
   - Commit with message: `feat/fix(...): <description> (from upstream <short-hash>)`
3. After each successful apply, run build and test commands if the project has them (check package.json, Makefile, etc.). If tests fail, assess whether the failure is from the upstream change or pre-existing.

## Step 5 — Update cursor

Write the new cursor to `dev/local/upstream-cursor`:

```
<remote> <branch> <new_head_hash>
```

The cursor advances to `<remote>/<branch>` HEAD regardless of which commits were taken or skipped — we've reviewed them all.

## Step 6 — Report

Summarize:
- Commits reviewed: N
- Applied: list with short descriptions
- Skipped: list with reasons
- Needs attention: anything flagged for later

## Edge cases

| Situation | Action |
|-----------|--------|
| Remote doesn't exist | Create it from owner/repo |
| Cursor file corrupt | Re-initialize from merge-base |
| Cherry-pick conflicts | Abort, adapt manually, or ask user |
| Upstream rewrote history | Detect if cursor hash is unreachable, re-initialize from merge-base |
| No `dev/local/` in .gitignore | Add it before writing cursor |
