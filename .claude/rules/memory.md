# Memory Persistence

Two tiers of memory, different homes:

- **Global / cross-machine memory, preference rules, and reusable methodology** (how to communicate, durable working preferences, skills) live under `~/.claude/` (`rules/`, `AGENTS.md`, `skills/`) and MUST be committed to the **buvis dotfiles bare repo** so they survive on a new machine:
  - `git --git-dir=~/.buvis --work-tree=~ add <path>`
  - `git --git-dir=~/.buvis --work-tree=~ commit -m "<conventional message>"` then push.
  - The buvis repo sets `status.showUntrackedFiles=no`, so a brand-new file will NOT appear in `status` — stage it by explicit path.
  - `~/.claude/CLAUDE.md` is only an `@AGENTS.md` pointer (also symlinked as `~/.codex/AGENTS.md`); edit `~/.claude/AGENTS.md`, never the pointer.
- **Project-scoped facts** (a codebase's gotchas, in-flight work) stay in the project auto-memory at `~/.claude/projects/<hash>/memory/` — not global, not committed to buvis.

When the user says "remember this globally" or "put it in global memory," default to a buvis-tracked file under `~/.claude/`, not the project auto-memory.

## Instincts vs auto-memory

Two machine-written planes teach future sessions; they have different owners:

- **Auto-memory** (`projects/<hash>/memory/`) holds curated facts written deliberately.
- **Instincts** (`~/.claude/instincts/`) holds statistical habits distilled from tool
  observations, confidence-gated; raw observations are pruned after
  `INSTINCTS_RETENTION_DAYS` (default 14).
- On conflict, auto-memory wins: an instinct that contradicts a memory is wrong or
  stale - fix or delete the instinct, never follow it over a memory.
