# Brush hygiene rules

Prime rule: **untracked does not mean disposable.** Default for any untracked
path is KEEP. Only the narrow junk classes below ever become candidates;
class `other` is never touched, only counted. `dev/local` is important
local-only support material: brush never hand-cleans it, only purge-devlocal's
coded rules may move anything there.

Safety taxonomy. Every candidate action falls in exactly one class:

1. Git-tracked change: reversible via git. AUTO, committed as `chore(hygiene): ...` (no CHANGELOG entry needed).
2. Untracked file removal: no git safety net. AUTO only via trash-first move (manifest, 30-day window).
3. Ref deletion: reflog-recoverable. AUTO only when provably merged, sha recorded in the report.
4. Remote, history, or permanent ops: irreversible. Never unattended; queue as Decision or MANUAL.

## AUTO - run unattended, record in report section 1 with undo

| action | precondition | undo |
|---|---|---|
| `git fetch --prune` | remote exists | refetch |
| `git worktree prune` | always | metadata only |
| `git worktree remove <wt>` | worktree clean AND branch merged (remove refuses dirty trees by itself) | re-add worktree |
| `git branch -d <b>` | `merge-base --is-ancestor` true | `git branch <b> <sha>` |
| `git branch -D <b>` | upstream `[gone]` AND (gh shows merged PR OR `squash_merged` true) | `git branch <b> <sha>` |
| trash untracked junk | class os-junk / junk / junk-dir, age >= 3d, not referenced | mv back per manifest.tsv |
| append `.gitignore` gaps | `gitignore_missing` from facts | `git revert` |
| `git rm --cached` + ignore | tracked os-junk only (.DS_Store class) | `git revert` |
| `git maintenance run --auto` | always | none needed |
| purge-devlocal skill (dry, sanity-check, apply) | dev/local exists | its own manifest |

## Phase-2 order (facts go stale)

1. `git fetch --prune` (and `git fetch upstream` when that remote exists).
2. Re-run collect_facts in full: `[gone]`, merged, and upstream state are
   fetch-dependent, so the preflight JSON is stale for ref decisions.
3. Gitignore fixes: ensure `dev/local/` is ignored BEFORE the first trash
   move ever creates it.
4. Trash moves, then branch and worktree actions, then
   `git maintenance run --auto`, then purge-devlocal.
5. Commit tracked fixes only while on the default branch; on any other
   branch queue them as BR-items (keeps feature-PR diffs clean).

## ASK - queue as `- [ ] BR-n` Decisions (report section 2)

- Delete unmerged or no-upstream local branches (`git branch -D`, sha in the item).
- Drop stashes older than 30d (`git stash drop`, highest index first).
- Trash scratch-class files (debug_*, scratch*, tmp_*, root test.py/test.sh).
- `git rm` tracked junk beyond the os-junk class (committed logs, build output).
- `git maintenance start` (registers background schedule) and `fetch.prune=true`.
- Anything whose `referenced` flag is true or unknown.

## MANUAL - report section 3, never executed by apply

- Remote branch deletion (`git push origin --delete ...`).
- History rewrite / `git filter-repo` / LFS migration when `big_tracked` or pack size is alarming (>500MB: flag, suggest investigation).
- Submodule drift surgery.
- Fork drift: when an `upstream` remote exists, report how far HEAD is
  behind `upstream/<default>` and point at `git-ferry:catchup-upstream`;
  never auto-sync.
- Anything involving files matching secret patterns. A TRACKED secret is CRITICAL: put it at the top of the report and stop hygiene until acknowledged.

## NEVER

`git clean -f` (bypasses trash), any `git push` (brush never pushes; the
report counts unpushed commits), tag deletion, `git gc --aggressive`
(disruptive; maintenance covers it), touching dirty tracked files, stashing or
staging user WIP, docs (`*.md`, `*.rst`, `*.txt`, `docs/`, README, LICENSE,
CHANGELOG), anything under `dev/local/` (purge-devlocal owns it), `.env*` and
key material.

## Guards (apply to every candidate)

- Age >= 3 days for any trash move (enforced by trash_untracked.py).
- Branches with an open PR (facts `open_prs`): untouchable.
- Current and default branch: untouchable. Default branch detection is master-first per house rule.
- Heavy dirs (node_modules, target, dist, build, venv): never moved; the fix is a `.gitignore` entry only.
- dev/local content: owned by purge-devlocal; brush never hand-cleans it.
- Apply mode re-verifies each item's recorded sha/path before executing; mismatch means the repo moved on: mark STALE, skip, note.

Junk patterns live in `scripts/collect_facts.py` (code is the source of truth); this file owns only the action classes.
