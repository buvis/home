---
name: catchup-upstream
description: Use when syncing a fork with its upstream remote by reviewing and selectively applying new upstream commits. Triggers on "sync upstream", "catchup upstream", "sync fork", "check upstream".
argument-hint: "[owner/repo or GitHub URL]"
---

# Catchup Upstream

Review new upstream commits since last sync, selectively apply relevant changes, and **leave the fork no longer "behind" upstream on GitHub**.

The closing merge with `-s ours` is mandatory: it advances the merge graph without altering the tree, so `git log HEAD..<remote>/<branch>` is empty afterward and GitHub stops counting the fork as behind. The merge graph itself records the reviewed point — no separate cursor file is needed.

## Step 1 — Resolve upstream repo

The argument can be:
- `owner/repo` (e.g. `banyudu/claude-warden`)
- A GitHub URL (e.g. `https://github.com/banyudu/claude-warden`)
- Omitted — infer from a non-`origin` remote if exactly one exists; otherwise list remotes and ask

### Find or create git remote

Normalize the input to `https://github.com/<owner>/<repo>.git`. Check existing remotes with `git remote -v`. If a matching remote exists, use it. Otherwise add one named after the owner:

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
git log --oneline HEAD..<remote>/<branch>
```

If empty, report "No new upstream commits — already caught up" and stop.

**First-run fallback:** If the list is huge (>50 commits), no `-s ours` merge has ever happened. Ask the user for a starting point (specific hash, "last 20", or "merge-base") and use that as the lower bound for review. The closing merge in Step 5 will still cover everything up to `<remote>/<branch>` HEAD.

**Legacy cursor migration:** If `dev/local/upstream-cursor` exists, treat it as the starting point for this run, then delete it after Step 5 succeeds — the merge graph supersedes it.

## Step 3 — Review each commit

For each new commit (oldest first):

1. Show the diff: `git show <hash> --stat` then `git show <hash>` for the full diff
2. Assess relevance:
   - Does it touch files/areas we've modified? Check with `git log --oneline --all -- <changed-files>` on our side
   - Bugfixes are usually worth taking; features depend on direction; refactors may conflict
   - Would it conflict with our changes? Look at overlap in modified files and logic
3. Classify as **take** (apply), **skip** (not relevant or conflicts with our direction), or **ask** (needs user judgment)

Present a summary table:

```
hash | subject | classification | reason
```

Wait for user confirmation before applying anything.

## Step 4 — Apply approved commits

For each approved commit, in order:

1. Try `git cherry-pick <hash>`. If it applies cleanly, move on.
2. If conflicts arise, assess whether manual adaptation is simpler than resolving the cherry-pick:
   - `git cherry-pick --abort`
   - Read the upstream diff and manually adapt the changes
   - Commit with message: `feat/fix(...): <description> (from upstream <short-hash>)`
3. After each successful apply, run build and test commands if the project has them. If tests fail, assess whether the failure is from the upstream change or pre-existing.

## Step 5 — Mark upstream as merged (MANDATORY)

This step is required even if zero commits were taken. It is what makes the fork no longer "behind" on GitHub.

```bash
git merge <remote>/<branch> -s ours -m "chore: merge <remote>/<branch> with -s ours strategy"
git push origin <current-branch>
```

`-s ours` keeps our tree byte-identical (cherry-picks from Step 4 are preserved) while recording `<remote>/<branch>` as a parent. After the push, GitHub recognizes the fork as caught up.

If the merge fails (e.g., detached HEAD, dirty tree), surface the error and stop — do not skip this step silently.

## Step 6 — Verify caught up

```bash
git rev-list --count HEAD..<remote>/<branch>
```

Must print `0`. If not, the merge didn't take effect; investigate before declaring success.

Also delete `dev/local/upstream-cursor` if it existed (legacy artifact).

## Step 7 — Report

Summarize:
- Commits reviewed: N
- Applied: list with short descriptions
- Skipped: list with reasons
- Merge commit: `<sha>` (pushed to `origin/<branch>`)
- Confirmed caught up: `git rev-list --count HEAD..<remote>/<branch>` = 0

## Edge cases

| Situation | Action |
|-----------|--------|
| Remote doesn't exist | Create it from owner/repo |
| Upstream rewrote history | Note it in the report; the `-s ours` merge still works |
| Cherry-pick conflicts | Abort, adapt manually, or ask user |
| Dirty working tree at Step 5 | Stop and ask user to commit/stash before merging |
| Detached HEAD at Step 5 | Stop and ask user to check out a branch |
| Push rejected (non-fast-forward on origin) | Pull `--rebase`, retry; if still failing, ask user |
| Not actually a fork (just tracking a repo) | Step 5 still works; the merge keeps history linked even without GitHub fork-tracking |
