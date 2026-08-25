# Shared agent skills

`~/.agents/skills` is the assembled discovery view for skills that should be
available to more than one assistant. It is local generated state, not the
canonical Git source. A skill is a directory containing `SKILL.md`; supporting
`scripts/`, `references/`, and `assets/` stay beside it.

## Agreed source and overlay architecture

Do **not** make `~/.agents` a submodule of the home dotfiles repository. Keep
each ownership/security domain in its own normal checkout and compose them into
`~/.agents/skills` with per-skill symlinks:

```text
~/git/src/github.com/buvis/agent-skills/       # public personal source
~/git/src/<employer>/agent-skills/             # private internal source

~/.config/agent-skills/sources.d/
├── personal                                   # dotfiles-managed
└── work                                       # work-machine only; never public

~/.agents/skills/
├── create-prd -> <personal-source>/skills/create-prd
├── company-release -> <work-source>/skills/company-release
└── ...
```

The dotfiles repository should track only bootstrap/composition configuration,
not a submodule gitlink for `~/.agents`. This avoids a second parent commit
whenever the public skill repository advances.

Maintenance rules:

- Edit a skill in its owning source checkout. Existing links reflect content
  edits immediately; recomposition is needed only after adding, removing, or
  renaming a skill.
- Commit and push personal changes in the public `agent-skills` repository.
  Pull on another machine only to receive changes made elsewhere.
- Keep employer skills in a separate internal repository. Never copy them into,
  or create tracked links from, the public checkout.
- Prefer repository-scoped employer skills (`<work-repo>/.agents/skills`) when
  they apply only to that repository. Put a work skill in the global union only
  when it genuinely applies across work projects.
- The composer must reject duplicate skill names by default. Resolve a
  collision by renaming or by an explicit machine-local precedence rule; never
  depend on an assistant's host-specific discovery order.
- A generated-state manifest must record every link the composer owns. Cleanup
  may remove only those recorded links, never arbitrary files under
  `~/.agents/skills`.

`braid` currently projects the assembled `~/.agents/skills` view into Claude.
Its planned composition phase should first build that view from the configured
source directories, validate collisions, and then run the existing host
projection. Kiro projection can use the same assembled view; Copilot and Codex
already discover it directly.

## How each assistant sees skills

| Assistant | Personal discovery path | Recommended setup |
|---|---|---|
| Codex | `~/.agents/skills` | Native. No extra link is needed. |
| Claude Code | `~/.claude/skills` | Run `~/.agents/bin/braid`; it creates per-skill links. |
| GitHub Copilot | `~/.agents/skills` | Native. It also understands `.github/skills`, `.copilot/skills`, and `.claude/skills`. |
| Kiro | `~/.kiro/skills` | Add `skill://~/.agents/skills/*/SKILL.md` to a custom agent, or create equivalent per-skill links. Kiro's import command copies rather than links. |

Do not link all of `~/.agents/skills` over `~/.claude/skills`: Claude-only
skills and plugin-owned skills also live there. `braid` links one skill at a
time, preserves destination-only entries, and skips names in
`~/.agents/braid.ignore`.

`~/.codex/skills` has a different job. Codex and its installers use it for
Codex-owned/system skills (notably `~/.codex/skills/.system`) and other
Codex-specific installations. Do not make it the shared source and do not
symlink it wholesale. User-authored cross-agent skills belong in
`~/.agents/skills`.

## Syncing Claude

Preview, apply, or verify the projection:

```bash
~/.agents/bin/braid --dry-run
~/.agents/bin/braid
~/.agents/bin/braid --check
```

For each non-ignored canonical skill, `braid` creates an absolute symlink at
`~/.claude/skills/<name>`. If that name is already a real directory or points
somewhere else, it is moved first to
`~/.claude/skills-backup/<timestamp>-<pid>/`. Claude-only destination entries
are untouched. Restart the assistant after changing skills if its current
session does not notice the update.

`braid.ignore` is intentional policy, not an error list. It excludes:

- Claude plugin-owned skills, to avoid a duplicate unnamespaced command;
- Codex-specific forks that inspect `~/.codex` state;
- workflows superseded or consolidated by a Claude plugin.

## Updating a skill

1. Resolve `~/.agents/skills/<name>` to its owning source checkout and edit the
   source, not the generated link farm.
2. If a newer standalone Claude definition exists, merge it into that source
   directory, keep its resources together, and replace avoidable host tool
   names with capability language (for example, “ask the user” or “spawn a
   sub-agent”).
3. If host coupling is real, keep it explicit in the `compatibility` frontmatter
   field. Do not pretend Claude hooks, Codex session storage, or a proprietary
   sub-agent API is portable.
4. Validate with the public repository's validator, then run `braid --check`.
5. Commit and push in the owning source repository. Recompose only if skill
   membership or names changed.

The current tree uses these compatibility classes:

- **Portable** — instructions and resources use ordinary filesystem, Git, or
  language tooling and can be followed by any capable assistant.
- **Portable compatibility copy** — the skill is owned by a Claude plugin, but
  a standalone copy remains under `~/.agents` for agents without that plugin.
  It is skipped when projecting back to Claude.
- **Personal runtime** — callable from another assistant, but depends on Bob's
  Claude/autoclaude files, wrappers, quotas, or review protocol.
- **Codex-specific / Claude-specific** — depends on that host's config,
  transcript format, hook lifecycle, or tool names. The frontmatter says so and
  `braid.ignore` prevents an invalid projection where needed.

## Plugins: reuse versus port

A plugin is a package around skills and possibly agents, hooks, MCP servers,
commands, or executables. Sharing its `skills/` directory is not the same as
sharing the whole plugin.

- Reuse the same package when it implements the Agent Plugins 1.0/Open Plugin
  conventions supported by the target host and keeps host-specific behavior in
  namespaced adapters.
- Reuse portable `SKILL.md` content and MCP server definitions directly where
  the host supports them.
- Port the manifest and integration layer when the package is a legacy Claude
  plugin. Claude hook events, tool names, permissions, commands, agents, and
  `${CLAUDE_PLUGIN_ROOT}` are not automatically meaningful to another host.
- A recognized manifest is only an installability signal; test hooks, agents,
  resource paths, and permissions on every target.

GitHub Copilot recognizes several plugin manifest locations, including
`.claude-plugin/plugin.json`, and supports Agent Plugins. Kiro supports Agent
Plugins 1.0. Codex has its own plugin packaging and can reuse portable skills,
MCP, and host adapters, but a legacy Claude bundle is not automatically a Codex
plugin.

Current local policy:

| Claude plugin | Treatment outside Claude |
|---|---|
| `git-ferry` | Keep its six skills as standalone compatibility copies in `~/.agents`; skip them in `braid`. |
| `strunk` | Keep the language/testing skills as standalone compatibility copies; skip them in `braid`. |
| `claude-checkup` | Claude owns the consolidated audits. Existing `~/.agents` audits are Codex-specific forks and are not projected to Claude. |
| `aegis` | `gateguard` documents a Claude hook and remains Claude-specific; no cross-host behavior without an adapter. |
| `warden` | Already carries Codex and Copilot adapters in addition to Claude integration; continue moving it toward one multi-host plugin. |
| `loupe` | Hook-heavy Claude plugin; port the hook/event adapter before reuse. |
| `agoge` | Claude agent pack; its prompts are reusable, but agent declarations and orchestration need host adapters. |
| `frontend-design` | Treat as vendor/plugin-owned; install the host's corresponding plugin or keep a separate portable skill. |

For a new cross-host plugin, prefer one repository with portable `skills/` and
MCP definitions at the root, plus small `.claude-plugin`, `.codex-plugin`, and
other host adapters. Do not maintain divergent copies of the skill prose unless
the behavior truly differs.

## References

- [OpenAI: Build skills](https://learn.chatgpt.com/docs/build-skills)
- [OpenAI: Plugins](https://learn.chatgpt.com/docs/plugins)
- [Claude Code: skills and symlink discovery](https://code.claude.com/docs/en/slash-commands)
- [GitHub Copilot: agent skills](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills)
- [GitHub Copilot: plugins](https://docs.github.com/en/copilot/concepts/agents/about-plugins)
- [GitHub Copilot: plugin manifest reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference)
- [Kiro: skills](https://kiro.dev/docs/skills/)
- [Kiro: Agent Plugins support](https://kiro.dev/blog/powers-supports-plugins/)
