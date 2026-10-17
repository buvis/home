# AI assistant instructions

- Solo developer. Be extremely concise, skip formalities.
- Simplest safe assumption when ambiguity isn't material.
- This file (`~/.claude/AGENTS.md`) is the single source of user-global agent instructions. Claude imports it through `~/.claude/CLAUDE.md`; Codex (`~/.codex/AGENTS.md`), Copilot (`~/.copilot/copilot-instructions.md`), Kiro (`~/.kiro/steering/AGENTS.md`), and Pi (`~/.pi/agent/AGENTS.md`) symlink here. Edit this file, never the pointers. New sessions load the updated instructions; custom agent prompts must preserve this shared authority.

## Autonomy — standing authorization

- Own the outcome. For requested work, make the best supported decision, execute, verify, and report. Do not ask the user to approve an obvious next step or end with "say go" when the work is already authorized.
- Routine reversible work is preauthorized: local edits, fixes, documentation, tests, review findings, refactoring needed for the task, dependency/tool use, local commits, and normal fast-forward pushes under the existing git policy. Choose the simplest safe approach; state material assumptions briefly and keep moving. Stay within the requested scope.
- Ask before an irreversible action or external commitment that is not already authorized: unrecoverable deletion, destructive changes to shared/production data, force pushes, publishing or sending to others, purchases, or access/security changes. Explain the concrete consequence and present the prepared action for approval. A recoverable file edit or a reviewer's low-severity suggestion is not such an action.
- Investigate missing information first. Prefer a safe reversible default over a preference question. Only request indispensable input when no safe progress is possible; name the blocker once and continue independent work.
- Review findings are yours to adjudicate: fix supported in-scope defects, reject false positives with evidence, and record genuinely out-of-scope items durably. Do not walk the user through cosmetic or routine technical choices. Preserve every required review lens, test gate, and fresh-session boundary.
- Respect explicit stops, hard budgets, and scope limits. Use the workflow's existing convergence, deferral, or recovery policy at its cap instead of inventing an approval gate or starting an unbounded repair loop. A routine reversible pause may be resolved under this standing authorization; an irreversible-action pause may not.
- This policy supersedes older ask-first conventions in personal rules, skills, and host instructions for routine reversible work. Later explicit user restrictions still bind. It does not bypass tool approvals, security controls, or required verification. Carry this authority into delegated tasks and handoffs so another agent does not ask again.

## Workflow

- After completing all PRD tasks, run `/autopilot:review-work-completion` in a fresh session - never from the work session (hand off first; see the review-phase rule below).
- For end-to-end PRD execution, use `/autopilot:run-autopilot`.
- Procedures mandated by an invoked skill count as explicitly requested: ponytail (and any other minimalism mode) must never thin, skip, or down-scope skill-mandated steps. Minimalism governs what you build, not whether you follow the skill.
- Never skip or thin the review phase of `/autopilot:run-autopilot`: every review cycle runs all lenses - consensus (Alice), blind/PRD-only (Blake), doubt+de-slop with rubric R1-R5 (Bob) - regardless of how small, simple, or well-specified the PRD looks. Do not ask whether the review is worth it - the answer is always yes. The worst issues land precisely when the code feels obviously correct. Reviewers get isolated contexts by construction (subagent prompts, external CLIs); the review phase itself runs in a fresh session after the build hand-off (end the turn: set `state.next_phase`, print the banner, STOP; in loop mode the headless session exits and the `autoclaude` wrapper relaunches from `state.json`). Never invoke `/autopilot:review-work-completion` from the work session, even if context budget appears sufficient. Scope (decided 2026-09-14, discovery 00203): this rule governs the full lane and every fast-track roster. Lane routing is decided by code (`cli/lane.py`, autopilot PRD 00204), never by an agent's judgment; the solo lane's one-pass zero-context review of docs/test-only PRDs, with code-decided escalation to the full gate on any production or security-ish diff, a CRITICAL or a surviving HIGH (PRD 00205), is the user's design, not an agent thinning the review.
- After completing work, clean up stale worktrees, orphan branches, temp files, and executed plan files in the repo's `docs/dev/project-management/plans/`.
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

## Handing work to the user

The user runs a hand-off top to bottom and does not read ahead. Write it so that order is safe.

- One numbered list, steps in execution order, commands inline. A precondition is its own step placed before the step that needs it. A warning that applies to a step comes before that step, never after the list. Mark an optional step optional in its place. Put nothing after the list that changes how to run it. (2026-10-17, PRD 00163: the approve commands came first and the config fix came below them, so the commit went out without the fix.)
- Write hand-offs in Simplified Technical English (ASD-STE100): one instruction per sentence, imperative mood, present tense, at most 20 words, one word for one meaning, no idioms, no synonyms for the same thing. State the expected result of a step when the user needs it to continue.

## Toolchain

- Interactive agent sessions start via `~/bin/run-agent`, which runs the agent under the macOS Seatbelt profile `~/.config/seatbelt/ai-agents.sb`: reads of `~/.config/gh`, private keys and similar are denied, writes land only under the project, `~/git/src`, `~/.claude`, `~/.cache`, `~/Library/Caches`, `~/Library/Logs`, `~/.local/state`, agent state dirs, data-only package caches and temp dirs. No tool bin dir or install target is writable (`~/.local/share/mise`, `~/.config/mise`, `~/Applications`, `~/.local/share/claude` and `~/.local/bin` are read-only since 2026-10-17): install or update tools through warrant, e.g. `~/bin/warrant request --reason "..." -- mise install <tool>`. The Keychain is unreachable (every `security` secret read fails with exit 36). Claude Code's own sandbox is off, so `dangerouslyDisableSandbox` and `sandbox.excludedCommands` change nothing; the `!` prompt is inside the same boundary. `gh` authenticates with a dedicated scoped PAT in `~/.config/gh-agent` (the launcher exports `GH_CONFIG_DIR`); never try to read the user's own `~/.config/gh`.
- An operation the profile denies (for example a commit in the bare `~/.buvis` repo) goes through **warrant** (PRD 00159): run `~/bin/warrant request --reason "..." -- CMD ARG...` from the sandbox, with `--no-wait` or in the background because the request may wait hours, then `~/bin/warrant wait ID`. The user reviews and runs it outside the sandbox with `~/bin/warrant approve` and a PIN. Never try to approve, read `~/.config/warrant`, or work around a refusal.
- CLI tools and language runtimes are managed with **mise**. Installs live under `~/.local/share/mise/installs/<tool>/<version>/`; shims at `~/.local/share/mise/shims/`.
- Global `npm ls -g`, `/opt/homebrew/bin`, `/usr/local/bin` will NOT list mise-managed tools - don't conclude a tool is missing from those. Locate one with `mise which <tool>`; run one not on PATH via `mise exec -- <tool>`.
- System updates run through **sysup** (buvis-gems tool, source `~/git/src/github.com/buvis/gems/src/tools/sysup/`; steps in `default.yaml`, capabilities in `capabilities/`). Any recurring upgrade/maintenance step belongs there as a new entry or capability, not in a shell alias or ad-hoc script.
- mise `pipx:` tools are pinned to uv-managed python (`uvx_args = "--managed-python --python X.Y"` in `~/.config/mise/config.toml`) so a mise python bump can't orphan their venvs.
- Not every install gets a shim - `mise which` can resolve a tool even when `command -v` fails. If a tool is missing from PATH, run `mise reshim` through warrant (the shims dir is read-only in the sandbox).
- The default model carries `[1m]` (1M window). The autopilot context cap (`autopilot_context_cap_hook.USAGE_CAP` in the autopilot plugin's `skills/run-autopilot/scripts/`, mirrored in `tracon/model.py` beside it) is 500K, coupled to that 1M default: never drop it toward 150K unless the default window also shrinks below 200K, or the cap misfires at ~163K aborting healthy build sessions (PRD 00073; 150K pin reverted 2026-07-20 when `[1m]` was restored).
- Before launching a `~/.claude` autopilot batch, `export _AUTOPILOT_WRITE_SCOPE_EXTRA="$HOME/.config/bash:$HOME/.codex:$HOME/.local/bin"` - the buvis repo spans those roots and the write-scope fence (`hooks/enforce_write_scope.py`, armed by `CLAUDE_UNATTENDED=1`) denies them otherwise; `_AUTOPILOT_WRITE_SCOPE=off` disarms the fence for one batch.

## Conventions

- Repos live at `~/git/src/github.com/{org}/{repo}` (Go-style layout).
- Name tools, plugins, and projects with evocative single words (warden, strunk) over descriptive concatenations; offer 3-4 candidates with rationale.
- When a standing rule already mandates a change discovered mid-task, produce the reversible artifact instead of asking; flag user-facing impact in the summary.
- **Skills live in `~/git/src/github.com/buvis/agent-skills`, not in buvis** (since 2026-08-25): edit and commit there, then `braid --check`; never edit through the link farm or stage a skill path into buvis. Layout, hops and policy: `rules/memory.md` and `~/.agents/README.md`.
- Kept-but-dormant material lives in `~/.claude/.archive/`: `skills/` (parked skills, not scanned, so they cost no boot context - `mv` one back into `~/.claude/skills/` to reactivate it) and `rules/` (retired rule text). `rules-library/` is NOT an archive: `rationalizations.md` is read at runtime by `hooks/cartographer-echo.py`.
- Native Bash grants in `settings.json` are deliberately broad (`git`, `rmdir`, `docker`, `kubectl` at `:*`), and so are the `tmp` Edit wildcards. `rm` is NOT granted natively - warden gates every `rm`. **Warden is the gate**, not the native allowlist: it filters every Bash command and asks or denies on its own rules. Config audits will keep flagging these as broad grants - that verdict is accepted, decided 2026-08-02. Do not re-narrow them audit by audit. Revisit only if warden stops gating Bash.

## Dotfiles repo

- Tracked in a bare repo at `~/.buvis`, work-tree is `$HOME`. Run git as `git --git-dir=~/.buvis --work-tree=~ <cmd>` (no shell alias assumed).
- **This repo answers "not tracked" by staying silent. That has already caused a wrong conclusion.** Treat ANY empty output from `~/.buvis` as unverified until a known-tracked control path proves the command shape works.
  - The index IS populated and matches HEAD (verified 2026-08-17: `ls-files` and `ls-tree -r --name-only HEAD` both return 641 entries), so `ls-files` is a valid tracking check. Still prefer `git diff HEAD` over plain `git diff`: the index is shared with the user's live sessions, so anything they staged is invisible to an index-vs-worktree diff.
  - Pathspecs resolve against **cwd**, not the work-tree. From anywhere but `~`, `-- .claude/foo` silently searches `<cwd>/.claude/foo` and finds nothing. Anchor every pathspec with `:(top)`, e.g. `add ':(top).claude/rules/foo.md'`. `git log` and `show --stat` keep working regardless, which makes the repo look fine while the path looks absent.
- The `rules/changelog.md` mandate does **not** apply here: no releases, no CHANGELOG. Commit `feat`/`fix` directly without a CHANGELOG entry, and don't add a CHANGELOG.md to this repo.
