# Working Documents

## dev/local/

Self-created working documents go in `dev/local/` at repo root, gitignored. Enforced by the **aegis** plugin's `block_devlocal_redirects.py` hook (Write tool, not shell redirects) - see `aegis/rules/working-documents.md`.

## Layout (GC contract)

Canonical: aegis `rules/working-documents.md` (v0.3.0+). `dev/local/` is GC'd by the `purge-devlocal` skill (trash-first, never hand-delete). Root holds named keepers; PRD satellites (`designs/`, `reviews/`, `plans/`) carry their `00XXX` number and die with the PRD; `tmp/` is 7d (unnumbered), `autopilot/` 14d; curated dirs (`discovery/`, `specs/`, `notes/`, `walkthroughs/`, `audit-results/`, `spikes/`) are flagged, never trashed. Don't invent new top-level dirs.

## PRDs

PRDs live under `dev/local/prds/` in the repo root. Never use a top-level `backlog/`, `wip/`, `done/`, or `hold/` directory - those are PRD lifecycle subfolders, not repo-root folders.

- New PRDs start in `dev/local/prds/backlog/`. Only move to `dev/local/prds/wip/` when actively starting implementation.
- Move PRDs to `done/` once their implementation is verified complete - no approval needed, even straight from `backlog/`.
- `hold/` is the single parked-PRD destination - both human-decided holds (`review-prd-backlog` HOLD verdicts, merge-absorbed originals) and machine-stalled PRDs (`run-autopilot`/`plan-tasks` parking a PRD it couldn't split or rework automatically). Autopilot never reads `hold/`; a human moves a PRD back to `backlog/` or `wip/` to resume it.
- Keep the `00XXX-` prefix on PRD filenames when moving between `backlog/`, `wip/`, `done/`, `hold/`.
- Use `mv` (not `cp`) when moving PRDs between folders - no duplicates across `backlog/`, `wip/`, `done/`, `hold/`.
