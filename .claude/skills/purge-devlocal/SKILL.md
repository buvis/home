---
name: purge-devlocal
description: Use when purging stale dev/local artifacts across repos (review debris, done-PRD satellites, old autopilot state) via trash-first GC. Triggers on "purge dev local", "clean dev local", "gc dev local", "empty dev local trash".
---

# Purge dev/local

## Dependencies

- Cross-skill script: `~/.claude/skills/review-prd-backlog/scripts/check_links.py`
  (post-apply dangling-reference verification, PRD 00081)

Deterministic garbage collector for `dev/local` artifact stores. Relevance is
decided by code, not judgment: a 5-digit PRD token links artifacts to
`prds/{backlog,wip,done}`, and type + age covers the unlinkable rest. Nothing
is deleted directly; everything moves to `<store>/.trash/<date>/` with a
manifest, and trash batches older than 30 days are emptied on later runs.

## How to run

1. Dry-run and show the user the per-store summary:

   ```
   python3 $CLAUDE_SKILL_DIR/scripts/purge_devlocal.py --all
   ```

   Scope to one repo with `--repo <repo-root>` (repeatable). Add `-v` to list
   every candidate file.

2. Sanity-check the output. `prds/**`, keepers (capsule, decisions, cursors),
   and anything linked to a backlog/wip PRD must never appear as trash. FLAG
   lines are kept files whose PRD vanished; surface them to the user instead
   of acting.

   **Consumed-spike prompt (spike deletion's owner).** A FLAG line under
   `spikes/<slug>/` whose PRD number resolves to `prds/done/` (check with `ls
   dev/local/prds/done/` for the 5-digit token) is a **consumed** spike — the
   spike did its job (it elicited requirements by building) and its PRD
   shipped, so the throwaway can go. In an **attended** run, PROMPT the user to
   trash it (offer it explicitly — this is the point where a consumed spike
   finally gets an owner instead of lingering forever); on yes, move it through
   the normal trash path with a manifest row `<today>\tspike-consumed\t<path>`.
   **Unattended** (`CLAUDE_UNATTENDED=1`): never auto-trash a curated spike —
   leave it flagged for the next attended run. A spike whose PRD is **missing**
   (in neither `done/` nor backlog/wip) is NOT consumed — it stays flagged-keep
   (it may be an orphan worth investigating, not a shipped one).

3. Pre-trash reference check (PRD 00081): before applying, verify nothing
   still points at a trash candidate. For each candidate path from the `-v`
   dry-run, search the store's markdown plus the project auto-memory for
   references to it (`rg -F "<candidate basename>"` over `dev/local`
   excluding `.trash/`, and `~/.claude/projects/<hash>/memory/` when purging
   `~/.claude`). A referenced candidate is NOT trashed this run: `touch` it
   (the `--min-age-days` guard then keeps it) and append a manifest row
   `<today>\tkept-referenced\t<path>\tstill referenced by <file:line>`.
   There is no force override - a referenced path stays until the reference
   is fixed or waived with `link-ok:` on the citing line.
   `${CLAUDE_SKILL_DIR}/../review-prd-backlog/scripts/check_links.py --json`
   finds the inverse direction (references whose target is already gone) -
   run it after apply to confirm the sweep created no new dangling refs.

4. Apply:

   ```
   python3 $CLAUDE_SKILL_DIR/scripts/purge_devlocal.py --all --apply
   ```

## Rules (first match wins)

| rule | target | action |
|---|---|---|
| prds / keeper / live-linked | prds/**, capsule, decisions.md, cursors, live-PRD satellites | keep |
| prd-gone | discovery/specs/notes/walkthroughs/audit-results/spikes with a done or missing PRD | flag, keep |
| done-linked | any non-prds file carrying a done PRD number | trash |
| missing-prd | numbered designs/reviews/plans/root files with no PRD anywhere | trash |
| stale-tmp | tmp/** older than 7d | trash |
| ledger | autopilot/ledger/** (durable outcome ledger) | keep |
| stale-autopilot | autopilot/** older than 14d | trash |
| stale-log | root *.log, *.bak, *.tmp older than 7d | trash |
| unclassified | everything else | keep, counted |

Safety rails: `--min-age-days 3` vetoes trashing anything freshly touched
(live batches stay intact); dry-run is the default; PRD number collisions are
absorbed by the 30-day trash window.

## Recovery

`<store>/.trash/manifest.tsv` records `date, rule, original path, trash path`
for every move. Restore by `mv`-ing the file back. Trash survives 30 days
(`--empty-trash-days`).

Trashed `reviews/*.md` leave their `Verdict:` lines in
`autopilot/ledger/review-verdicts.jsonl` before the move - review outcomes
outlive the satellite GC, and the wrapper appends loop-metrics to the same
GC-exempt `ledger/` dir.

## Wire-in

`autoclaude` (in `~/.config/bash/plugins/development.plugin.bash`) runs
`--repo "$PWD" --apply` after a successful backlog drain, so stores GC
themselves at batch end. Manual runs cover repos that never see autopilot.

## Tests

```
python3 -m pytest $CLAUDE_SKILL_DIR/scripts/test_purge_devlocal.py -q
```
