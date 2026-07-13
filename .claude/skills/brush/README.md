# brush

Unattended-safe project hygiene for one repo. Reversible actions run on
their own; anything irreversible waits for your written approval in a
report. You stay in control through one file and one command.

## Quick start

```
/brush dry      # first run on any repo: report only, changes nothing
/brush quick    # routine pass: git hygiene only (phases 1, 2, 7)
/brush          # full pass: adds evolution, backlog, AGENTS.md, atlas
/brush apply    # execute the BR items you marked [x] in the report
```

## Workflow

```
            /brush [quick|dry]
                  |
   preflight guards (bare repo, buvis home,
   autopilot live, mid-rebase/merge, dirty WIP)
                  |
   1 catchup ── 2 git hygiene ── 3 assess ── 4 backlog ── 5 AGENTS.md ── 6 atlas
                  |                    (3-6 full mode only)
                  v
   7 report: dev/local/audit-results/brush-report.md
                  |
        +---------+----------+
        |                    |
   AUTO actions          decisions
   (already done,        (waiting as "- [ ] BR-n ... cmd: ...")
   each with undo)            |
                              v
              YOU: edit report, mark [x] on approved lines
                              |
                              v
                    /brush apply  (same repo)
              re-verifies sha/path, runs each cmd,
              marks the line done - stale items skipped
```

Every run ends with a printed block telling you the report path, the
counts, and the exact resume command. If you are away, ntfy pings you when
decisions are pending.

## Safety model

| class | examples | policy |
|---|---|---|
| AUTO | fetch --prune, merged-branch delete (SHA logged), junk to trash, gitignore fixes | runs unattended, undo listed in report |
| ASK | unmerged branches, stashes, scratch files, rebases, config | waits for your [x] |
| MANUAL | remote deletes, history rewrites, secrets | never executed by apply, listed for you |
| NEVER | git clean -f, any push, force-push, tags, docs, dev/local, .env | brush will not do these |

Untracked never means disposable: default is KEEP. File removals are
trash-first moves into `dev/local/.trash/<date>/` with a manifest line
(purge-devlocal format and GC window); restore is `mv` back. dev/local
itself is owned by purge-devlocal; brush never hand-cleans it.

## Recovery

- Trashed file: see `dev/local/.trash/manifest.tsv`, `mv` it back.
- Deleted branch: report row has the SHA - `git branch <name> <sha>`.
- Hygiene commit: `git revert <sha>` (sha in the report).

## Files

- `SKILL.md` - the orchestrator Claude follows
- `scripts/collect_facts.py` - read-only repo facts as JSON
- `scripts/trash_untracked.py` - trash-first mover with manifest
- `scripts/test_brush_scripts.py` - regression net (`python3 -m pytest ... -q`)
- `references/hygiene-rules.md` - full AUTO/ASK/MANUAL/NEVER matrix + guards
- `references/report-template.md` - report format and BR-item grammar

## Depends on

Skills: git-ferry:catchup, purge-devlocal, assess-evolution,
review-prd-backlog, manage-agents-md, survey. Optional: gh, notify.py,
git-ferry:resolve-git-conflicts, git-ferry:review-deps-prs. A missing
dependency skips its phase and lands in the report's Failures section.
