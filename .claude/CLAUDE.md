# AI assistant instructions

- Solo developer. Be extremely concise, skip formalities.
- Simplest safe assumption when ambiguity isn't material.

## Workflow

- After completing all PRD tasks, run `/review-work-completion` in a fresh session — never from the work session (hand off first; see the review-phase rule below).
- For end-to-end PRD execution, use `/run-autopilot`.
- Never skip or thin the review phase of `/run-autopilot`: every review cycle runs all lenses — consensus (Alice), blind/PRD-only (Blake), doubt+de-slop with rubric R1-R5 (Bob) — regardless of how small, simple, or well-specified the PRD looks. Do not ask whether the review is worth it - the answer is always yes. The worst issues land precisely when the code feels obviously correct. Reviewers get isolated contexts by construction (subagent prompts, external CLIs); the review phase itself runs in a fresh session after the build hand-off (end the turn: set `state.next_phase`, print the banner, STOP — in loop mode the headless session exits and the `autoclaude` wrapper relaunches from `state.json`). Never invoke `/review-work-completion` from the work session, even if context budget appears sufficient.
- After completing work, clean up stale worktrees, orphan branches, temp files, and executed plan files in the repo's `dev/local/plans/`.

## Compaction

- After failed approach: compact
- Mid-implementation: don't compact
- After completing a PRD, before next: compact

With 1M context, research stays in-flight through implementation.

## Planning

- End plans with unresolved questions.
- One question at a time, concise, with enough context to answer quickly.

## Toolchain

- CLI tools and language runtimes are managed with **mise**. Installs live under `~/.local/share/mise/installs/<tool>/<version>/`; shims at `~/.local/share/mise/shims/`.
- Global `npm ls -g`, `/opt/homebrew/bin`, `/usr/local/bin` will NOT list mise-managed tools - don't conclude a tool is missing from those. Locate one with `mise which <tool>`; run one not on PATH via `mise exec -- <tool>`.
- Not every install gets a shim - `mise which` can resolve a tool even when `command -v` fails. If a tool is missing from PATH, suggest `mise reshim`.

## Dotfiles repo

- Tracked in a bare repo at `~/.buvis`, work-tree is `$HOME`. Run git as `git --git-dir=~/.buvis --work-tree=~ <cmd>` (no shell alias assumed).
- The `rules/changelog.md` mandate does **not** apply here: no releases, no CHANGELOG. Commit `feat`/`fix` directly without a CHANGELOG entry, and don't add a CHANGELOG.md to this repo.
