# Working Documents

## dev/local/

All self-created working documents go in `dev/local/` in repo root. Ensure `dev/local/` is in `.gitignore`. The **aegis** plugin's `block_devlocal_redirects.py` hook enforces "Write tool, not shell redirects" - see `aegis/rules/working-documents.md` for the rationale.

## Layout (GC contract)

`dev/local/` is garbage-collected by the **purge-devlocal** skill (trash-first: moves land in `.trash/<date>/` with a manifest, emptied after 30d). Never hand-delete; run the skill. Place artifacts so the GC can reason about them:

- **Root**: only the named keepers - `project-capsule.md`, `decisions.md`, `troubleshooting.md`, `assumptions.md`, `ecc-cursor`, `upstream-cursor`. No logs, no workspaces, no reports at root.
- **PRD satellites** (`designs/`, `reviews/`, `plans/`): carry the PRD number (`00XXX`) in the filename. Trashed when their PRD reaches `done/` or vanishes; kept while it sits in `backlog/`/`wip/`.
- **Ephemeral** (`tmp/`): scratch, logs, reviewer outputs, one-off workspaces. PRD-number the filename when known (dies with the PRD); unnumbered tmp is trashed after 7d.
- **`autopilot/`**: loop state and batch reports; trashed after 14d.
- **Curated** (`discovery/`, `specs/`, `notes/`, `walkthroughs/`, `audit-results/`, `spikes/`): never trashed, only flagged when their PRD is gone - the user decides.
- New artifact types: pick an existing dir before inventing one; a new top-level dir is kept-but-unclassified forever (GC blind spot).

## PRDs

PRDs live under `dev/local/prds/` in the repo root. Never use a top-level `backlog/`, `wip/`, or `done/` directory - those are PRD lifecycle subfolders, not repo-root folders.

- New PRDs start in `dev/local/prds/backlog/`. Only move to `dev/local/prds/wip/` when actively starting implementation.
- Move PRDs to `done/` once their implementation is verified complete - no approval needed, even straight from `backlog/`.
- Keep the `00XXX-` prefix on PRD filenames when moving between `backlog/`, `wip/`, `done/`.
- Use `mv` (not `cp`) when moving PRDs between folders - no duplicates across `backlog/`, `wip/`, `done/`.
