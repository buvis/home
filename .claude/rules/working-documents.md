# Working Documents

## dev/local/

Self-created working documents go in `dev/local/` at repo root, gitignored. Enforced by the **aegis** plugin's `block_devlocal_redirects.py` hook (Write tool, not shell redirects) - see `aegis/rules/working-documents.md`.

## Layout (GC contract)

Canonical: aegis `rules/working-documents.md` (aegis 0.3.2 carries it). `dev/local/` is GC'd by the `purge-devlocal` skill (trash-first, never hand-delete). Named keepers (capsule, decisions, assumptions, agoge-profile, cursors) live in `dev/local/meta/` since 2026-08-23, their only home; the root compat symlinks were removed 2026-08-27 (PRD 00139) and root is now directories only. The GC still accepts a root keeper file, because other machines migrate their stores later. PRD satellites (`designs/`, `reviews/`, `plans/`) carry their `00XXX` number and die with the PRD; `tmp/` is 7d while a PRD is in `prds/wip/`, 3d when wip is empty (no loop in flight); `autopilot/` 14d; curated dirs (`discovery/`, `specs/`, `notes/`, `walkthroughs/`, `audit-results/`, `spikes/`) are flagged, never trashed. Don't invent new top-level dirs.

Since 2026-08-23 the layout is enforced at write time by `~/.claude/hooks/enforce_prd_location.py` (via `dispatch.py`): non-keeper root files, new top-level dirs, `.trash/` writes, and files directly in `prds/` all block with a message naming the right home. Throwaway output goes to `dev/local/tmp/`, PRD-numbered when one applies.

## PRDs

PRDs live under `dev/local/prds/` in the repo root. Never use a top-level `backlog/`, `wip/`, `done/`, or `hold/` directory - those are PRD lifecycle subfolders, not repo-root folders.

- New PRDs start in `dev/local/prds/backlog/`. Only move to `dev/local/prds/wip/` when actively starting implementation.
- Move PRDs to `done/` once their implementation is verified complete - no approval needed, even straight from `backlog/`.
- `hold/` is the single parked-PRD destination - both human-decided holds (`review-prd-backlog` HOLD verdicts, merge-absorbed originals) and machine-stalled PRDs (`run-autopilot`/`plan-tasks` parking a PRD it couldn't split or rework automatically). Autopilot never reads `hold/`; a human moves a PRD back to `backlog/` or `wip/` to resume it.
- Keep the `00XXX-` prefix on PRD filenames when moving between `backlog/`, `wip/`, `done/`, `hold/`.
- Use `mv` (not `cp`) when moving PRDs between folders - no duplicates across `backlog/`, `wip/`, `done/`, `hold/`.
