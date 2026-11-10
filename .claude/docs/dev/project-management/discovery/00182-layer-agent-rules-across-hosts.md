# Discovery: cross-host agent rules with overlays

Status: decided, 2026-11-02. Specced 2026-11-02: phase 1 as buvis/gems PRD 00115,
buvis/agent-skills PRD 00159 and buvis home PRD 00183; phase 2 as buvis/gems PRD
00116; phase 3 as buvis home PRD 00184 (split ~/.claude/AGENTS.md and
~/.claude/rules into agent-rules, cut every host over to braid output).

## Problem

Skills have a shared standard (`SKILL.md`, `~/.agents/skills`). Always-on
instructions ("rules", "steering", "custom instructions") do not. Each host
reads its own path and format. We need one source of rules, layered:

1. public, shared by every machine
2. company, shared by one employer's machines
3. machine-local, never leaves the box

## What each host reads (user level)

| Host | Path | Shape | Many files? |
|---|---|---|---|
| Claude Code | `~/.claude/rules/*.md`, `~/.claude/CLAUDE.md` | dir + file (`@` imports) | yes |
| Kiro | `~/.kiro/steering/*.md` | dir | yes |
| Codex | `~/.codex/AGENTS.md` | one file, no imports | no |
| Copilot CLI | `~/.copilot/copilot-instructions.md` | one file | no |
| Pi | `~/.pi/agent/AGENTS.md` | one file | no |
| Gemini CLI | `~/.gemini/GEMINI.md` | one file (`@` imports) | no (unverified on this setup) |

Two classes: directory hosts take per-file links; single-file hosts need
one composed file.

## Proposal: rules are a second braid kind

Reuse everything braid already does for skills. Nothing new except one
generated file per single-file host.

### Repos and tooling

Content and tooling split into separate repos:

| Repo | Holds |
|---|---|
| `buvis/agent-skills` | `skills/` only (content) |
| `buvis/agent-rules` (new, public) | `rules/`, `hosts/<host>/rules/` (content) |
| `buvis/gems` | `braid` as `src/tools/braid/`, per the gems tool standard |
| company repo(s) | any mix of `skills/`, `rules/`, `hosts/` |

- braid is machine tooling, like `sysup`, so it belongs in gems; content repos
  stop carrying a Python package. gems already ships to PyPI and supports
  Windows, which braid needs.
- The skill validator stays inside `skills/create-skill/`; it is part of that
  skill. `agent-plugins/scripts/validate.py` and `tools/autopilot/` stay too:
  they check that repo's own content in its CI, not a machine.
- A source is any directory listed in `sources.d`; braid scans whichever of
  `skills/`, `rules/`, `hosts/` it has. So `personal` lists two repos, and a
  company may use one repo or two.
- Config moves from `~/.config/agent-skills/` to `~/.config/braid/` (one-time
  migration, no fallback path). State stays at `~/.agents/.braid-state.json`.
  **Superseded 2026-11-10:** gems tools keep config in `~/.config/buvis/`, so
  sources become a `sources:` list in `~/.config/buvis/buvis-braid.yaml`, and
  company or machine-only sources go in `~/.local/.config/buvis/buvis-braid.yaml`
  (buvis/gems#272, #273). Read `sources.d` below as that list.

Order: (1) port braid into gems at parity, retire `agent-skills-braid` and the
`~/.agents/bin/braid` link; (2) add the rules kind in gems; (3) create
`agent-rules` and migrate the public subset of `~/.claude/rules`.

### Source layout

Every source repo in `sources.d` may carry `rules/` beside `skills/`. A rule
mirrors a skill:

```text
rules/<name>/RULE.md          # slim, always loaded: the rule + "when X, read Y"
rules/<name>/references/*.md  # detail, read on demand (progressive discovery)
```

`RULE.md` points at detail as `~/.agents/rules/<name>/references/x.md`, the
same path convention skills use. Long procedures can also point at a skill.

### Host-specific rules

Any source may also carry rules for one host only:

```text
hosts/<host>/rules/<name>/RULE.md   # host in: claude, kiro, codex, copilot, pi, gemini
```

They layer exactly like shared rules, because every source can have them:
Kiro steering in the public repo reaches home and work; a company repo or the
machine-local source adds more Kiro steering on the work box only.

A host-specific `RULE.md` is passed through unchanged, so it may use that
host's native frontmatter (Kiro `inclusion: fileMatch`, Claude `paths:`).
Shared rules stay plain Markdown. A directory, not a `hosts:` frontmatter
field: the scope is visible in the tree, needs no parsing, and matches how
Claude-only skills are kept out of `skills/` rather than tagged. Host
references resolve at `~/.agents/hosts/<host>/rules/<name>/references/`.

Names must be unique across shared and that host's rules; a clash is the same
error as a duplicate skill.

### Layers = sources.d (already exists)

```text
~/.config/agent-skills/sources.d/
├── personal   # tracked in dotfiles -> public agent-skills repo
├── work       # symlink -> ~/.local/.config/agent-skills/sources.d/work
└── local      # symlink -> ~/.local/.config/agent-skills/sources.d/local
```

`local` names a plain directory (for example `~/.local/share/agents/local`)
holding `rules/` and optionally `skills/`. Machine-local files live under
`~/.local`, per the existing dotfiles rule.

### Merge semantics

Same as skills: the union of all sources, duplicate names rejected, a
`.braidignore` entry drops a name on one machine. To amend a public rule, add
a new rule in the later layer; do not shadow by name. (run-shell-hooks merges
by key because tasks are data; rules are prose, and silent shadowing of prose
is how drift hides.)

### Projection

| Target | How |
|---|---|
| `~/.agents/rules/<name>` | per-rule dir link (shared union view) |
| `~/.agents/hosts/<host>/rules/<name>` | per-rule dir link (host union view) |
| `~/.claude/rules/<name>.md` | link to `RULE.md` only (shared + claude), so references stay out of boot context |
| `~/.kiro/steering/<name>.md` | link to `RULE.md` only (shared + kiro), when Kiro is enrolled |
| `~/.agents/hosts/<host>/AGENTS.md` | generated per single-file host: shared then host `RULE.md` files, each group in layer then name order, with a "generated by braid, edit sources" header |
| Codex, Copilot, Pi, Gemini files | symlink to their own `~/.agents/hosts/<host>/AGENTS.md` (same pattern as today's links to `~/.claude/AGENTS.md`) |

`braid --check` treats a stale generated file as drift. State manifest records
every link and generated file, as for skills.

Rules braid does not own (real files already in `~/.claude/rules/` or
`~/.kiro/steering/`) are preserved as destination-only entries, the same rule
as for skills. They can migrate into `hosts/<host>/rules/` of a source at
leisure.

## Why slim rules matter here

Single-file hosts load everything every session, and Codex caps project docs
at 32 KiB by default. The always-on part must be an index of short rules plus
pointers; detail is read only when a pointer fires.

## Alternatives rejected

- Rules in buvis/docs: no composer, no `sources.d`, no validator, and a work
  machine may not have that checkout. Docs can still link to or render them.
- Rules inside agent-skills: mixes two kinds of content in a repo named for
  one, and keeps braid tied to skills.
- Per-host `@import` chains: Codex, Copilot and Pi have no imports.
- `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`, Gemini `context.fileName`: host-specific
  knobs; one generated file covers all single-file hosts.
- Override-by-name layering: see merge semantics.

## Unresolved

1. Decided 2026-11-02: new `buvis/agent-rules` repo; braid moves to gems.
2. Decided 2026-11-02: braid follows the full gems tool standard; colleagues
   consuming a company repo install `buvis-gems`.
3. Decided 2026-11-02: personal-setup rules (seatbelt, warrant, mise, bare
   dotfiles repo, autopilot) go in `agent-rules` too; buvis/home is already
   public, so nothing new is exposed. A colleague who adopts `agent-rules`
   drops unwanted names with `.braidignore`; a company repo never lists it
   for them by default. Only secrets or employer-confidential rules stay in
   the company or machine-local source.
4. Decided 2026-11-02 (agent default): no conditional loading for shared
   rules in v1; all shared rules are always-on. Host rules already get it
   through native frontmatter.
