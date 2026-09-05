# Memory Persistence

Two tiers of memory, different homes:

- **Global / cross-machine memory and preference rules** (how to communicate, durable working preferences) live under `~/.claude/` (`rules/`, `AGENTS.md`) and MUST be committed to the **buvis dotfiles bare repo** so they survive on a new machine:
  - `git --git-dir=~/.buvis --work-tree=~ add <path>`
  - `git --git-dir=~/.buvis --work-tree=~ commit -m "<conventional message>"` then push.
  - The buvis repo sets `status.showUntrackedFiles=no`, so a brand-new file will NOT appear in `status` - stage it by explicit path.
  - `~/.claude/CLAUDE.md` is only an `@AGENTS.md` pointer (also symlinked as `~/.codex/AGENTS.md`); edit `~/.claude/AGENTS.md`, never the pointer.
- **Skills are NOT in buvis** (changed 2026-08-25). Cross-agent skills live in `~/git/src/github.com/buvis/agent-skills`, reach `~/.agents/skills/<name>` as symlinks, and reach `~/.claude/skills/<name>` as a second hop laid by `~/.agents/bin/braid`. Commit a skill edit in THAT repo, then run `braid --check`; never edit through the link farm. `~/.claude/skills/` holds only Claude-only skills as real directories; everything else there is a link, so staging one into buvis records a symlink, not your change. See `~/.agents/README.md` for the source/overlay design, the `compatibility:` frontmatter classes, and the `braid.ignore` policy (plugin-owned names are excluded there to avoid duplicate unnamespaced commands).
- **Project-scoped facts** (a codebase's gotchas, in-flight work) stay in the project auto-memory at `~/.claude/projects/<hash>/memory/` - not global, not committed to buvis.

When the user says "remember this globally" or "put it in global memory," default to a buvis-tracked file under `~/.claude/`, not the project auto-memory.

## Auto-memory is the only machine-written plane

`projects/<hash>/memory/` holds curated facts written deliberately, and nothing
else teaches future sessions.

The **instincts** plane (`~/.local/share/agents/instincts/`, written by
`hooks/observe_tool.py` and `hooks/analyze-instincts.py`) was retired
2026-08-26. It had never delivered: its only output went to
`~/.claude/projects/<encoded>/CLAUDE.md`, and it encoded the repo path by
replacing `/` alone while the harness also replaces `.`, so every repo under
`github.com/` landed in a phantom sibling directory that held no sessions. What
it produced was tautologies ("Repeated sequence: Bash -> Bash -> Bash", trigger
identical to action), so it was deleted rather than repaired. Do not re-add a
statistical-habit plane without a delivery path proven end to end first.
