# Shared agent skills: machine-local policy

The design, install steps, `braid` usage, `.braidignore` format, multi-source
overlay pattern, and compatibility classes live in
`~/git/src/github.com/buvis/agent-skills/README.md` and are canonical. This file
carries only what is true of this machine.

## Plugin treatment outside Claude

Which Claude plugins have a standalone copy here, and how each is handled. The
names skipped by `braid` are listed in `.braidignore`.

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

## Sources composed here

One source today: `~/git/src/github.com/buvis/agent-skills`, recorded in
`~/.config/agent-skills/sources.d/personal`. Every entry in
`~/.agents/skills` is a symlink into it, and `~/.agents/bin/braid` is a symlink
into its `bin/`. Add a work-machine-only `sources.d/work` file when a private
employer checkout exists.
