# AI assistant instructions

- Solo developer. Be extremely concise, skip formalities.
- Simplest safe assumption when ambiguity isn't material.
- This file (`~/.claude/AGENTS.md`) is the single source of user-global agent instructions. `~/.claude/CLAUDE.md` is only an `@AGENTS.md` pointer and `~/.codex/AGENTS.md` symlinks here. Edit this file, never the pointers.

## Workflow

- After completing all PRD tasks, run `/review-work-completion` in a fresh session - never from the work session (hand off first; see the review-phase rule below).
- For end-to-end PRD execution, use `/run-autopilot`.
- Procedures mandated by an invoked skill count as explicitly requested: ponytail (and any other minimalism mode) must never thin, skip, or down-scope skill-mandated steps. Minimalism governs what you build, not whether you follow the skill.
- Never skip or thin the review phase of `/run-autopilot`: every review cycle runs all lenses - consensus (Alice), blind/PRD-only (Blake), doubt+de-slop with rubric R1-R5 (Bob) - regardless of how small, simple, or well-specified the PRD looks. Do not ask whether the review is worth it - the answer is always yes. The worst issues land precisely when the code feels obviously correct. Reviewers get isolated contexts by construction (subagent prompts, external CLIs); the review phase itself runs in a fresh session after the build hand-off (end the turn: set `state.next_phase`, print the banner, STOP; in loop mode the headless session exits and the `autoclaude` wrapper relaunches from `state.json`). Never invoke `/review-work-completion` from the work session, even if context budget appears sufficient.
- After completing work, clean up stale worktrees, orphan branches, temp files, and executed plan files in the repo's `dev/local/plans/`.
- Meta-budget: Claude-on-Claude work (the `~/.claude` project) targets <= 30% of monthly spend; the portfolio brief surfaces the share monthly (red above ceiling). Released-plugin repo work counts as product, not meta.
- If a secret may have been exposed, rotate it.

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
- The default model carries `[1m]` (1M window). The autopilot context cap (`autopilot_context_cap_hook.USAGE_CAP`, mirrored in `tracon/model.py`) is 500K, coupled to that 1M default: never drop it toward 150K unless the default window also shrinks below 200K, or the cap misfires at ~163K aborting healthy build sessions (PRD 00073; 150K pin reverted 2026-07-20 when `[1m]` was restored).
- Before launching a `~/.claude` autopilot batch, `export _AUTOPILOT_WRITE_SCOPE_EXTRA="$HOME/.config/bash:$HOME/.codex:$HOME/.local/bin"` - the buvis repo spans those roots and the write-scope fence (`hooks/enforce_write_scope.py`, armed by `CLAUDE_UNATTENDED=1`) denies them otherwise; `_AUTOPILOT_WRITE_SCOPE=off` disarms the fence for one batch.

## Conventions

- Repos live at `~/git/src/github.com/{org}/{repo}` (Go-style layout).
- Name tools, plugins, and projects with evocative single words (warden, strunk) over descriptive concatenations; offer 3-4 candidates with rationale.
- When a standing rule already mandates a change discovered mid-task, produce the reversible artifact instead of asking; flag user-facing impact in the summary.
- **Skills live in `~/git/src/github.com/buvis/agent-skills`, not in buvis** (since 2026-08-25). `~/.agents/skills/<name>` symlinks into that repo; `~/.agents/bin/braid` lays a second hop at `~/.claude/skills/<name>`. Edit and commit in the source repo, then `braid --check`. Never edit through the link farm, and never stage a skill path into buvis - you would record a symlink, not the change. `~/.agents/README.md` holds the source/overlay design, the `compatibility:` frontmatter classes, and the `braid.ignore` policy (plugin-owned names are excluded there to avoid duplicate unnamespaced commands).
- Kept-but-dormant material lives in `~/.claude/.archive/`: `skills/` (parked skills, not scanned, so they cost no boot context - `mv` one back into `~/.claude/skills/` to reactivate it) and `rules/` (retired rule text). `rules-library/` is NOT an archive: `rationalizations.md` is read at runtime by `hooks/cartographer-echo.py`.
- Native Bash grants in `settings.json` are deliberately broad (`git`, `rmdir`, `docker`, `kubectl` at `:*`), and so are the `tmp` Edit wildcards. `rm` is NOT granted natively - warden gates every `rm`. **Warden is the gate**, not the native allowlist: it filters every Bash command and asks or denies on its own rules. Config audits will keep flagging these as broad grants - that verdict is accepted, decided 2026-08-02. Do not re-narrow them audit by audit. Revisit only if warden stops gating Bash.

## Dotfiles repo

- Tracked in a bare repo at `~/.buvis`, work-tree is `$HOME`. Run git as `git --git-dir=~/.buvis --work-tree=~ <cmd>` (no shell alias assumed).
- **This repo answers "not tracked" by staying silent. That has already caused a wrong conclusion.** Treat ANY empty output from `~/.buvis` as unverified until a known-tracked control path proves the command shape works.
  - The index IS populated and matches HEAD (verified 2026-08-17: `ls-files` and `ls-tree -r --name-only HEAD` both return 641 entries), so `ls-files` is a valid tracking check. Still prefer `git diff HEAD` over plain `git diff`: the index is shared with the user's live sessions, so anything they staged is invisible to an index-vs-worktree diff.
  - Pathspecs resolve against **cwd**, not the work-tree. From anywhere but `~`, `-- .claude/foo` silently searches `<cwd>/.claude/foo` and finds nothing. Anchor every pathspec with `:(top)`, e.g. `add ':(top).claude/rules/foo.md'`. `git log` and `show --stat` keep working regardless, which makes the repo look fine while the path looks absent.
- The `rules/changelog.md` mandate does **not** apply here: no releases, no CHANGELOG. Commit `feat`/`fix` directly without a CHANGELOG entry, and don't add a CHANGELOG.md to this repo.
