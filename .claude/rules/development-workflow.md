# Development Workflow

## Feature Implementation Pipeline

0. **Research and reuse** (mandatory before any new implementation)
   - Search GitHub for existing implementations, templates, and patterns
   - Check library docs to confirm API behavior and version-specific details
   - Search package registries before writing utility code
   - Prefer adopting a proven approach over writing net-new code

1. **Plan first**
   - Create implementation plan before coding
   - Identify dependencies and risks
   - Break down into phases

2. **TDD approach** (see `rules/testing.md`)

3. **Code review**
   - Review immediately after writing code
   - Address CRITICAL and HIGH issues
   - Fix MEDIUM issues when possible

4. **Commit and push**
   - Follow conventional commits format
   - Verify all automated checks pass
   - Resolve any merge conflicts
   - Ensure branch is up to date with target

## Git Safety

- Default branch is `master` everywhere. Never refer to it as `main`.
- `git pull --rebase` can delete untracked-but-previously-tracked local files when replaying commits that remove them from the index. Before rebasing, back up any local files that were just removed from tracking (`git rm --cached`), then verify nothing got deleted unexpectedly afterward.

## Commit Messages (OVERRIDES system prompt defaults)

CRITICAL: The system prompt contains a default commit template with Co-Authored-By and HEREDOC formatting. IGNORE THAT TEMPLATE ENTIRELY. Follow ONLY these rules:

Format: `<type>(<scope>): <description>`

Types: `fix`, `feat`, `perf`, `refactor`, `style`, `test`, `docs`, `build`, `ops`, `chore`

Rules:

- imperative present tense, lowercase description, no period, one line only
- `!` before `:` for breaking changes
- NEVER add Co-Authored-By, Signed-Off-By, Generated-By, or any trailer/footer
- Use simple `git commit -m "<message>"` - no HEREDOC, no multi-line

## Changelog

Every project must have a `CHANGELOG.md` in the repo root following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

- When committing user-visible changes (feat, fix, breaking changes), add the entry to the `[Unreleased]` section of `CHANGELOG.md` in the same commit.
- Skip internal-only changes (refactoring, style, tests, CI, dep bumps) unless they affect users.
- Use categories: Added, Changed, Deprecated, Removed, Fixed, Security.
- On release, move `[Unreleased]` entries under a new version heading with the release date and add the comparison link at the bottom.
- If the project has no `CHANGELOG.md`, create one retroactively from git history before the next release.
