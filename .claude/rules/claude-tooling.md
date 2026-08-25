---
# *.sh/*.js entries catch wrong-language hook attempts; React/web hooks dirs (src/hooks/*.ts) deliberately unmatched
paths:
  - "**/skills/**"
  - "**/.claude/hooks/**"
  - "**/hooks/*.py"
  - "**/hooks/*.sh"
  - "**/hooks/*.js"
  - "**/hooks/hooks.json"
---
# Claude Tooling Authoring

- Claude Code hooks: Python only, never bash/sh (cross-platform).
- Plugin skills reference helper scripts via `${CLAUDE_SKILL_DIR}/scripts/…`, never `~/.claude/skills/` paths. Reach for `${CLAUDE_PLUGIN_ROOT}/skills/<other>/…` only to cross skill boundaries, which `CLAUDE_SKILL_DIR` cannot express without `../`.
  - **Exception, decided 2026-08-25 (autopilot pack):** a multi-skill pack whose skills cross-reference heavily may use `${CLAUDE_PLUGIN_ROOT}` uniformly, for own-scripts and cross-skill alike. The reason is the third column of the table below: neither placeholder resolves inside `references/`, so such packs carry a banner telling the model to hand-substitute the root when it meets one. That banner can only name one placeholder. Mixing the two would leave half the references uncovered by it, which is how the empty-string `/skills/…` bug returns. One idiom per pack beats the sharper default here. Autopilot is uniformly `${CLAUDE_PLUGIN_ROOT}` (108 references); do not "fix" it file by file. A single-skill plugin keeps `${CLAUDE_SKILL_DIR}` as the default.

## Where the path placeholders resolve

Measured against the Claude Code build, 2026-08-25. **Neither is a shell environment variable.** Both are substituted textually into the text before the model ever sees it, so headless changes nothing.

| Placeholder | SKILL.md / command body | hooks.json | `references/`, `scripts/`, anything read at runtime |
|---|---|---|---|
| `${CLAUDE_PLUGIN_ROOT}` | yes | yes | **no** |
| `${CLAUDE_SKILL_DIR}` | yes (skill mode only) | no | **no** |

The third column is the trap. A placeholder in a file the model `Read`s at runtime reaches the shell as a literal, expands to the empty string, and the path silently becomes `/skills/…`. agoge shipped that bug and only caught it in a headless run.

So:

- **SKILL.md body**: use a placeholder. It is resolved before you read it.
- **`scripts/`**: never use a placeholder. Locate siblings from `$0` or `__file__`.
- **`references/`**: a placeholder there cannot resolve itself. Either keep such paths out, or have the SKILL.md state the resolved root once so the model can substitute when it meets one.
