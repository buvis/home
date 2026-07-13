---
paths:
  - "**/skills/**"
  - "**/hooks/**"
---
# Claude Tooling Authoring

- Claude Code hooks: Python only, never bash/sh (cross-platform).
- Plugin skills reference helper scripts via `${CLAUDE_SKILL_DIR}/scripts/…`, never `~/.claude/skills/` paths; `CLAUDE_PLUGIN_ROOT` resolves only in hooks.json.
