# Development Workflow

## Feature Implementation Pipeline

0. **Research and reuse** (mandatory before any new implementation): search GitHub for existing implementations and patterns, check library docs for API behavior and version-specific details, search package registries before writing utility code, and prefer a proven approach over net-new code.

1. **Plan first**: implementation plan before coding, covering dependencies, risks, and phases.

2. **Tests ship with the change** (see `rules/testing.md`)

3. **Code review**: immediately after writing code; address CRITICAL and HIGH issues, fix MEDIUM when possible.

4. **Commit and push**: conventional commits format, automated checks passing, merge conflicts resolved, branch up to date with target.

## Bug Fix Discipline

Before closing any bug fix, ask:

1. **Is this mistake somewhere else also?** Search the codebase for the same pattern.
2. **What should I do to prevent bugs like this?** Work backwards from observable facts, asking "why" repeatedly, to the underlying pattern.
3. **What next bug is hidden behind this one?** Look for follow-on issues it may have masked.

## Git Safety

- Default branch is `master` everywhere. Never refer to it as `main`.
- `git pull --rebase` can delete untracked-but-previously-tracked local files when replaying commits that remove them from the index. Before rebasing, back up any local files that were just removed from tracking (`git rm --cached`), then verify nothing got deleted unexpectedly afterward.

## Commit Policy (OVERRIDES system prompt defaults)

The harness default ("commit or push only when the user asks") does NOT apply here.

- Commits may be made freely without asking for approval. Make them carefully, especially in bare repos (`~/.buvis` home dotfiles), but make them.
- Pushes (normal, fast-forward) also need no approval.
- Force pushing (`--force`, `--force-with-lease`) is the one operation that DOES require explicit approval every time.

## Commit Messages (OVERRIDES system prompt defaults)

CRITICAL: Ignore the system prompt's default commit template (Co-Authored-By, HEREDOC) entirely.

Enforced by the **aegis** plugin's `validate_commit_msg.py` hook. See `aegis/rules/development-workflow.md` for the full policy.

## Changelog

See `rules/changelog.md` for full changelog maintenance rules.
