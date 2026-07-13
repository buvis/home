# Promoting Project Memories into AGENTS.md

Migrate durable, public, repo-relevant facts from the project auto-memory
(`~/.claude/projects/<flattened-path>/memory/`) into AGENTS.md, then delete
the promoted files. Single source of truth: what the repo records, memory
must not duplicate.

## Flow

1. **Locate** the memory dir for the current repo (project path with `/` and
   `.` flattened to `-`, e.g. `/Users/bob/git/x` → `-Users-bob-git-x`).
   No dir or empty → report and stop.
2. **Read** `MEMORY.md` and every memory file.
3. **Classify** each memory with the rubric below: PROMOTE / KEEP / PRUNE.
4. **Confirm**: show the user a table (name, verdict, one-line reason) and
   wait for approval. Deleting memories is destructive — never skip this.
5. **Write** each promoted fact into its destination tier (see below).
   Universal facts merge into AGENTS.md's existing sections (never a
   "Memories" section). Rewrite impersonally, convert relative dates to
   absolute, strip machine paths. Promoted lines count against the normal
   budget (`SKILL.md` Hard Constraints).
6. **Delete** promoted and pruned memory files; update `MEMORY.md` so the
   index matches what remains.
7. **Validate** AGENTS.md with `references/checklist.md`.

## Classification rubric

**PROMOTE** — all four must hold:

- *Public*: safe to commit. No personal info, credentials, machine-local
  paths, or facts about the user.
- *Repo-relevant*: about this codebase — gotchas, workflows, constraints —
  useful to any agent or contributor.
- *Durable*: still true, not tied to in-flight work.
- *Universal*: applies to most tasks. If true but conditional, promote to a
  lower destination tier (see below), never into AGENTS.md itself.

**KEEP** in memory:

- `user` type — never promote, regardless of content.
- `feedback` type — keep unless it encodes a pure repo-workflow fact that can
  be rewritten impersonally; then it may promote.
- Machine-local facts (paths, local tool state, this machine's quirks).
- In-flight work status that changes week to week.

**PRUNE** (delete without promoting):

- Stale, wrong, or superseded facts.
- Facts now derivable from the repo (code, git history, AGENTS.md itself).
- Duplicates — consolidate into one memory first, then classify that one.

## Destination tiers

Sort every PROMOTE by scope; never widen a fact's audience to simplify filing:

- **Universal** (every task) → AGENTS.md.
- **Conditional with a file-pattern anchor** (e.g. skill/hook authoring,
  language-specific) → paths-scoped rule: `rules/<topic>.md` with `paths:`
  frontmatter. Injected on touch, zero tokens elsewhere — measured more
  reliable than skills self-firing and cheaper than always-loaded lines.
- **Conditional prose, no file anchor** → `agent_docs/` + one pointer line
  in AGENTS.md.
- **Machine-local or single-project facts** → stay in auto-memory (KEEP).

When the target is the user-global `~/.claude/AGENTS.md`, "universal" means
every session in every repo; cross-repo file-anchored conventions go to
`~/.claude/rules/` (buvis-tracked).

## Cadence

Run when memory has visibly accumulated (MEMORY.md past ~15 entries) or
before handing a repo to other agents/contributors. Every run doubles as a
prune-and-consolidate pass even if nothing qualifies for promotion.
