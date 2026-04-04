# Changelog Maintenance

BLOCKING RULE: Every commit with a user-visible change MUST update `CHANGELOG.md` in the same commit. This is not optional and not deferrable to release time.

## What requires an entry

- `feat` commits: Added
- `fix` commits: Fixed
- Breaking changes (`!`): Changed or Removed
- `perf` commits with user-visible impact: Changed

## What does NOT require an entry

- `refactor`, `style`, `test`, `docs`, `build`, `ops`, `chore`
- Dependency bumps (unless they fix a user-facing bug or change behavior)
- CI-only changes

## How to write the entry

Add a bullet under the appropriate category in `[Unreleased]`:

```markdown
## [Unreleased]

### Fixed

- **dot**: scroll file list panes to keep selected file visible
```

- Prefix with `**tool-or-scope**:` matching the commit scope
- Describe the user-visible effect, not the implementation detail
- One line per entry

## Self-check before committing

If the commit type is `feat`, `fix`, or has `!` (breaking), verify CHANGELOG.md is in the staged files. If it is not, stop and add the entry before committing.
