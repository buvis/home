# AI assistant instructions

- Solo developer. Be extremely concise, skip formalities.
- Simplest safe assumption when ambiguity isn't material.

## Workflow

- After completing all PRD tasks, run `/review-work-completion`.
- For end-to-end PRD execution, use `/run-autopilot`.
- Never skip review phases (Phase 4 review, Phase 7 blind-review, Phase 8 doubt-review) of `/run-autopilot`, regardless of how small, simple, or well-specified a task or PRD looks. Do not ask whether the review is worth it - the answer is always yes. The worst issues land precisely when the code feels obviously correct.
- **Always run review phases in a fresh session.** When `/run-autopilot`'s Phase 3 (Work) completes, the agent must NOT continue into Phase 4 in the same session — the review phases (4, 7, 8) each spawn multiple cloud reviewers and need a clean context window. Use autopilot's existing signal-file mechanism (same one used between PRDs at Phase 9): write `next` to `dev/local/autopilot/signal`, print the handoff banner, then STOP. The Stop hook auto-exits the session and the shell loop wrapper restarts `/run-autopilot` in a fresh session, which resumes at Phase 4 because `state.json` records `phases_completed=["catchup", "planning", "work"]`. Never ask the user to press Ctrl+D — that breaks the automated loop. Never invoke `/review-work-completion` from the work session, even if context budget appears sufficient.
- After completing work, clean up stale worktrees, orphan branches, temp files, and executed plan files in `~/.claude/plans/`.

## Compaction

- After failed approach: compact
- Mid-implementation: don't compact
- After completing a PRD, before next: compact

With 1M context, research stays in-flight through implementation.

## Planning

- End plans with unresolved questions.
- One question at a time, concise, with enough context to answer quickly.

## Dotfiles repo

- Tracked in a bare repo at `~/.buvis`, work-tree is `$HOME`. Run git as `git --git-dir=~/.buvis --work-tree=~ <cmd>` (no shell alias assumed).
- The `rules/changelog.md` mandate does **not** apply here: no releases, no CHANGELOG. Commit `feat`/`fix` directly without a CHANGELOG entry, and don't add a CHANGELOG.md to this repo.
