---
name: brush
description: Use when running a project hygiene pass on a repo - git cleanup, leftover triage, evolution check, backlog review, AGENTS.md refresh. Triggers on "brush", "brush the project", "project hygiene", "tidy repo", "clean up this repo".
argument-hint: "[quick|dry|apply]"
---

# Brush

Unattended-safe project hygiene. Reversible actions run on their own;
irreversible ones queue in a report for human approval. One run ends with one
report and one exact resume instruction. Full runs are token-heavy; use
`quick` for routine passes.

Prime rule: untracked does not mean disposable. Default for any untracked
path is KEEP. `dev/local` holds important local-only support material: brush
never hand-cleans it; only the `purge-devlocal` skill's coded rules run there.

## Dependencies

Brush only orchestrates; these skills do the work. A missing or failing one:
record under Failures, skip its phase, continue. Never substitute hand-rolled
cleanup for a missing skill (especially purge-devlocal).

- `git-ferry:catchup` (phase 1) - repo context
- `purge-devlocal` (phase 2) - sole owner of dev/local GC
- `assess-evolution` (phase 3), `review-prd-backlog` (phase 4),
  `manage-agents-md` (phase 5)
- `survey` (phase 6) - Cartographer atlas refresh
- Optional plugins: `git-ferry:resolve-git-conflicts` (preflight pointer),
  `git-ferry:review-deps-prs` (report pointer when dep PRs pile up)
- Optional: `gh` (PR-merge proof; absent = gone-branch deletes demote to
  ASK unless the squash probe proves the merge), `~/.claude/hooks/notify.py`.

## Modes ($ARGUMENTS)

- (none) full: all phases
- `quick`: phases 1, 2, 7 only; pass `--fast` to collect_facts
- `dry`: like quick but execute nothing; report what would happen
  (recommended for a repo's first brush)
- `apply`: execute approved items from an existing report (see Apply)

## Preflight

1. Run `python3 ${CLAUDE_SKILL_DIR}/scripts/collect_facts.py --repo <cwd>`.
2. STOP and say why if: JSON has `refusals` (bare repo, buvis home tree),
   `autopilot_live` is true (never brush mid-batch), or `in_progress_op` is
   set (mid rebase/merge/bisect: point at `git-ferry:resolve-git-conflicts`).
3. Dirty tracked files are user WIP: never touch, never stash; list in report.
4. Read `${CLAUDE_SKILL_DIR}/references/hygiene-rules.md` before phase 2.
5. Repo-local extension: a `brush-local` project skill or an AGENTS.md
   `Hygiene` section adds rules; it never overrides the safety matrix.

## Phases

1. **Context**: run the `git-ferry:catchup` skill.
2. **Git hygiene**: follow the Phase-2 order in hygiene-rules.md (fetch,
   re-collect facts, then act): execute every AUTO row; queue ASK rows as
   BR-items and MANUAL rows as section 3 items. Trash moves only via
   `python3 ${CLAUDE_SKILL_DIR}/scripts/trash_untracked.py --repo <root> <paths>`
   (it re-vetoes protected paths itself). For dev/local, invoke the
   `purge-devlocal` skill scoped to this repo: dry-run, sanity-check, apply;
   its FLAG lines go into the report, never acted on. Commit tracked fixes as
   `chore(hygiene): ...`.
3. **Evolution** (full only): run the `assess-evolution` skill; tell it
   catchup already ran this session.
4. **Backlog** (full only): run the `review-prd-backlog` skill.
5. **Instructions** (full only): run the `manage-agents-md` skill.
6. **Atlas** (full only): run the `survey` skill so the Cartographer atlas
   is refreshed while repo context is loaded.
7. **Report + handoff**: write `dev/local/audit-results/brush-report.md`
   (audit reports live in the curated audit-results store, never dev/local
   root) per `${CLAUDE_SKILL_DIR}/references/report-template.md`.

Unattended posture for phases 3-5: take each sub-skill's recommended default
instead of asking questions; log every defaulted decision in the report. A
phase failure never aborts the run: record it under Failures and continue.

## Apply

1. Read the report; collect checked, not-yet-done `- [x] BR-n` lines.
2. Per item, in strict sequence: re-verify the recorded sha/path (mismatch =
   STALE, skip, note); execute the cmd; immediately mark the line
   `done <date>` via Edit. No batching.
3. MANUAL items are never executed, even if checked.
4. Summarize done / stale / skipped counts.

## Ending

The human must always see exactly how to proceed. Print this block verbatim,
filled in, as the last thing in the final message:

```
brush <mode> done - <repo>
report: dev/local/audit-results/brush-report.md
auto: <N> | decisions: <M> | manual: <K> | unpushed: <U>
next: edit the report, mark [x] on approved BR items, then run
  /brush apply               (in a session opened in <repo>)
  claude -p "/brush apply"   (headless)
nothing pending and no manual items -> no action needed
```

If decisions are pending or a phase failed, also send
`python3 /Users/bob/.claude/hooks/notify.py --send "brush <repo>" "<M> decisions pending - dev/local/audit-results/brush-report.md"`.
Skip the notify silently if the script is absent or the human is present in
an interactive session.

## Tests

`python3 -m pytest ${CLAUDE_SKILL_DIR}/scripts/test_brush_scripts.py -q`

## Non-goals

Remote branch/tag lifecycle, history rewriting, secret scanning depth, CI
config, cross-repo sweeps (run brush per repo; brief-portfolio reads state).
