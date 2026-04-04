# Claude Code Platform Details

## Skill Placement

Skills are discovered from multiple locations, with higher priority winning on name conflicts:

| Priority | Location | Scope |
|---|---|---|
| 1 (highest) | Enterprise managed settings | All users in org |
| 2 | `~/.claude/skills/<name>/SKILL.md` | All your projects (personal) |
| 3 | `.claude/skills/<name>/SKILL.md` | This project only |
| 4 | Plugin skills | Where plugin is enabled |

Plugin skills use namespaced names (`plugin-name:skill-name`) to avoid conflicts.

### Automatic Discovery

When working in subdirectories, Claude Code discovers skills from nested `.claude/skills/` dirs. Editing in `packages/frontend/` also loads `packages/frontend/.claude/skills/`. This supports monorepos.

Skills in `.claude/skills/` within `--add-dir` directories are loaded automatically with live change detection.

## Legacy Commands

Files at `.claude/commands/*.md` still work and support the same frontmatter as skills. Skills are recommended because they support additional features (supporting files, directory structure). If both exist with the same name, the skill takes precedence.

## String Substitutions

These variables are replaced in SKILL.md content before Claude sees it:

| Variable | Description |
|---|---|
| `$ARGUMENTS` | All arguments passed when invoking the skill |
| `$ARGUMENTS[N]` | Specific argument by 0-based index |
| `$0`, `$1`, `$2` | Shorthand for `$ARGUMENTS[0]`, `$ARGUMENTS[1]`, etc. |
| `${CLAUDE_SESSION_ID}` | Current session ID |
| `${CLAUDE_SKILL_DIR}` | Directory containing this skill's SKILL.md |

If `$ARGUMENTS` is not referenced in the content, arguments are appended as `ARGUMENTS: <value>`.

### Example

```markdown
Read the file at `$0` and summarize the function at line `$1`.

Use the helper script at `${CLAUDE_SKILL_DIR}/scripts/analyze.py`.
```

Invoked as `/my-skill src/main.py 42`, Claude sees:

```markdown
Read the file at `src/main.py` and summarize the function at line `42`.

Use the helper script at `/Users/you/.claude/skills/my-skill/scripts/analyze.py`.
```

## Dynamic Context Injection

The `` !`<command>` `` syntax runs a shell command BEFORE the skill content is sent to Claude. The command output replaces the placeholder. This is preprocessing, not something Claude executes at runtime.

```markdown
Current branch: !`git branch --show-current`

Recent changes:
!`git log --oneline -5`
```

Can be disabled with the `disableSkillShellExecution` setting.

## Description Budget

The total space for all skill descriptions scales at 1% of the context window, with a fallback of 8,000 characters. Individual descriptions are capped at 250 characters (truncated beyond that). Override with `SLASH_COMMAND_TOOL_CHAR_BUDGET` env var.

## Extended Thinking

Including the word "ultrathink" anywhere in skill content enables extended thinking mode.
