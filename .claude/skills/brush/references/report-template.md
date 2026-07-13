# Brush report template

Write to `dev/local/brush-report.md` (overwrite; unchecked items re-derive on
the next run, so no carry-forward). Keep every cmd verbatim and executable.

```markdown
# Brush report - <repo-name>

- generated: <YYYY-MM-DD HH:MM> | mode: <full|quick|dry> | HEAD: <sha12> | branch: <name> | unpushed: <n>
- phases: catchup OK | git-hygiene OK | assess SKIPPED (quick) | backlog OK | agents-md FAILED | atlas OK

## 1. Done automatically (all reversible)

| action | detail | undo |
|---|---|---|
| trash | `debug_probe.py` -> `dev/local/.trash/2026-07-13/` | mv back (see manifest.tsv) |
| branch-delete | `feat/x` was `abc1234` (merged) | `git branch feat/x abc1234` |
| commit | `chore(hygiene): ignore __pycache__` -> `def5678` | `git revert def5678` |

## 2. Decisions - mark [x] to approve, then run /brush apply

- [ ] BR-1 (branch-delete) sha=abc1234 age=94d - unmerged `spike/foo`, no upstream - cmd: `git branch -D spike/foo`
- [ ] BR-2 (stash-drop) age=61d - stash@{2} "wip: old experiment" - cmd: `git stash drop stash@{2}`
- [ ] BR-3 (trash-scratch) age=12d - `scratch_bench.py`, unreferenced - cmd: `python3 ~/.claude/skills/brush/scripts/trash_untracked.py --repo <root> --rule brush-scratch scratch_bench.py`

Unchecked = skipped. Apply re-verifies sha/path first; stale items are skipped and noted.

## 3. Manual only - never executed by apply

- MANUAL BR-4 (remote-delete) `origin/old-feature` looks dead - you run: `git push origin --delete old-feature`
- MANUAL BR-5 (repo-size) pack 1.2GB - consider LFS or `git filter-repo`; investigate before acting

## 4. Phase digests

- catchup: <3 lines, capsule path>
- assess-evolution: <verdict, roadmap/PRD paths>
- backlog: <counts, findings, artifact path>
- agents-md: <what changed, commit sha>

## 5. Failures and skips

- <phase or action>: <one-line error>. Nothing is omitted silently; if this section is empty, everything above ran.

## 6. How to continue

1. Review section 2 and mark `[x]` on lines you approve (edit this file directly).
2. Resume in this repo with: `/brush apply` (headless: `claude -p "/brush apply"`).
3. Section 3 items are yours to run by hand if wanted.
4. Nothing checked and section 3 empty: done, no action needed.
```

Item grammar: `- [ ] BR-<n> (<kind>) <facts> - <why> - cmd: <exact command>`.
Kinds: branch-delete, stash-drop, trash-scratch, git-rm, config, other.
MANUAL items carry no checkbox and start with `MANUAL`.
