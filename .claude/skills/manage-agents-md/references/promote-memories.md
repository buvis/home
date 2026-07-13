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
5. **Write** promoted facts into AGENTS.md, merged into its existing sections
   (never a "Memories" section). Rewrite impersonally, convert relative dates
   to absolute, strip machine paths. Promoted lines count against the normal
   budget (`SKILL.md` Hard Constraints); non-universal detail goes to
   `agent_docs/` with a pointer.
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
- *Universal*: applies to most tasks. If true but conditional, promote to
  `agent_docs/` instead, with a pointer line in AGENTS.md.

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

## Cadence

Run when memory has visibly accumulated (MEMORY.md past ~15 entries) or
before handing a repo to other agents/contributors. Every run doubles as a
prune-and-consolidate pass even if nothing qualifies for promotion.
