# Working Documents

## dev/local/

All self-created working documents go in `dev/local/` in repo root. Ensure `dev/local/` is in `.gitignore`. The **aegis** plugin's `block_devlocal_redirects.py` hook enforces "Write tool, not shell redirects" - see `aegis/rules/working-documents.md` for the rationale.

## Layout (GC contract)

Canonical policy: the **aegis** plugin's `rules/working-documents.md` (v0.3.0+). Short form: `dev/local/` is GC'd by the `purge-devlocal` skill (trash-first; never hand-delete). Root holds named keepers only; PRD satellites (`designs/`, `reviews/`, `plans/`) carry their `00XXX` number and die with the PRD; `tmp/` is ephemeral (7d when unnumbered); `autopilot/` lives 14d; curated dirs (`discovery/`, `specs/`, `notes/`, `walkthroughs/`, `audit-results/`, `spikes/`) are flagged, never trashed. Don't invent new top-level dirs.

## PRDs

PRDs live under `dev/local/prds/` in the repo root. Never use a top-level `backlog/`, `wip/`, or `done/` directory - those are PRD lifecycle subfolders, not repo-root folders.

- New PRDs start in `dev/local/prds/backlog/`. Only move to `dev/local/prds/wip/` when actively starting implementation.
- Move PRDs to `done/` once their implementation is verified complete - no approval needed, even straight from `backlog/`.
- Keep the `00XXX-` prefix on PRD filenames when moving between `backlog/`, `wip/`, `done/`.
- Use `mv` (not `cp`) when moving PRDs between folders - no duplicates across `backlog/`, `wip/`, `done/`.
