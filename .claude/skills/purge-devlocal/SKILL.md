---
name: purge-devlocal
description: Use when purging stale dev/local artifacts across repos (review debris, done-PRD satellites, old autopilot state) via trash-first GC. Triggers on "purge dev local", "clean dev local", "gc dev local", "empty dev local trash".
---

# Purge dev/local

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

3. Apply:

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

## Wire-in

`autoclaude` (in `~/.config/bash/plugins/development.plugin.bash`) runs
`--repo "$PWD" --apply` after a successful backlog drain, so stores GC
themselves at batch end. Manual runs cover repos that never see autopilot.

## Tests

```
python3 -m pytest $CLAUDE_SKILL_DIR/scripts/test_purge_devlocal.py -q
```
