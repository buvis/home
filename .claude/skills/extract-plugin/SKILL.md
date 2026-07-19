---
name: extract-plugin
description: Use when extracting a cluster of personal skills/hooks/commands into a new Claude Code plugin repo and publishing to the buvis marketplace. Triggers on "extract plugin", "ship as plugin", "make plugin from", "spin out plugin".
---

# Extract Plugin

End-to-end playbook for turning a cluster of personal `~/.claude/` items into a published plugin in the `buvis-plugins` marketplace. Walks through eleven phases with four user checkpoints. Codifies what we learned shipping `audit-suite` and `strunk`.

## Dependencies

- Personal skills: `create-skill` (Phase 8 runs `python3 ~/.claude/skills/create-skill/scripts/validate_skill.py`)
- CLIs: `gh`, `git`, `python3`, `uv` (`uv run --with pytest`), and **bash >= 4** (`scripts/check-readiness.sh` uses `mapfile`; macOS `/bin/bash` 3.2 lacks it)
- External repos: `~/git/src/github.com/buvis/claude-plugins` (marketplace registration), `claude-strunk` (source of the copied LICENSE and `.gitignore`)
- Reads `~/.claude/` surfaces (`hooks/`, `commands/`, `agents/`, `rules/`, `settings.json`) and the shell rc files
- Harness tool: `AskUserQuestion`

## Conventions

- Plugin repos live at `~/git/src/github.com/buvis/claude-<plugin-name>/`.
- Marketplace is the central `~/git/src/github.com/buvis/claude-plugins/` repo. Each plugin gets one entry in its `.claude-plugin/marketplace.json`.
- Initial version is always `0.1.0`. Subsequent releases use the plugin's own `dev/bin/release [patch|minor|major]`.
- Default branch is `master`.

## Phase 1: Intake

Confirm the cluster. The user will name a target (often from `project_next_plugins_to_ship.md` memory). Resolve it to a concrete list of skills, commands, hooks, and agents in `~/.claude/`.

Output of this phase: the **cluster list** — concrete skill names (e.g. `python-patterns python-testing rust-patterns`). Substitute them for `<skill1> <skill2> ...` in every command below as you dispatch it.

If the user named hooks or commands directly, list those too. The cluster can include any of:
- Skills at `~/.claude/skills/<name>/`
- Commands at `~/.claude/commands/<name>.md`
- Agents at `~/.claude/agents/<name>.md` (directory absent until a custom agent is defined — skip when missing)
- Hooks at `~/.claude/hooks/<name>.py` (referenced from `~/.claude/settings.json`)

## Phase 2: Readiness check (CHECKPOINT 1)

Run the completeness audit:

```bash
bash ~/.claude/skills/extract-plugin/scripts/check-readiness.sh <skill1> <skill2> ...
```

The script greps **seven surfaces** for inbound references to each cluster item, then runs the inverse check (what each cluster item references outward), plus two ambient probes:

| Surface | Why it matters |
|---|---|
| 1. Hooks (`~/.claude/hooks/*.py` + `~/.claude/settings.json`) | A hook may invoke or depend on the cluster |
| 2. Commands (`~/.claude/commands/*.md`) | Slash commands often glue skills together |
| 3. Agents (`~/.claude/agents/*.md`) | Sub-agents may invoke cluster skills |
| 4. Other skills (`~/.claude/skills/*/SKILL.md`) | Cross-skill invocation via `/name` |
| 5. Rules (`~/.claude/rules/**/*.md`) | Workflow rules may name the cluster |
| 6. **User instructions** (`~/.claude/{AGENTS,CLAUDE,GEMINI}.md`) | These can carry multi-paragraph operational rules tied to the cluster (e.g. autopilot's "never skip review phases"). A plugin can't edit the user's CLAUDE.md — affected text must either ship as the plugin's own `AGENTS.md` or stay with the user as a documented residue |
| 7. **Shell rc / shell plugins** (`~/.config/bash/**`, `~/.zshrc`, `~/.bashrc`, `~/.config/fish/**`) | Shell functions (e.g. `autoclaude`) can hard-code paths like `~/.claude/skills/<name>/...` that break the moment the skill moves. Plugins can't install shell functions, so any hit here forces a distribution decision (ship as `bin/` script, leave in dotfiles with updated paths, etc.) |

**Inverse-check categories** for what each cluster item points OUTWARD at:

- Other skill paths (`~/.claude/skills/<other>/...`)
- Slash commands (`/other-command`) — find these by grepping for the leading slash followed by a known command name
- Hardcoded state-file or sentinel paths shared with other subsystems (e.g. `dev/local/autopilot/state.json` read by the autoclaude wrapper and tracon)

**Ambient probes** (run by the script, no per-item argument):

- **Soft coupling probe**: scan non-cluster hooks for string-literal references to cluster runtime artifacts — session-name keywords, env-var sentinels (`_AUTOPILOT_LOOP`), state-file paths. Example: `observe_tool.py` matches `"autopilot"` in `CLAUDE_SESSION_NAME`. These hooks don't move, but they create a hidden contract the plugin's session naming must preserve.
- **Personal-data probe**: hard-coded `/Users/bob`, `buvis-plugins`, etc. inside cluster items — must be sanitized before publish.

Classify each finding:

| Class | Action |
|---|---|
| **Same cluster** | Already covered — no action |
| **Different cluster, already a plugin** | Use namespaced reference (`<otherplugin>:<skill>`); document as runtime dep in README |
| **Different cluster, not yet a plugin** | Decide extraction order: ship the dependency plugin first, OR accept and document the dep, OR vendor the script (per Phase 5b) |
| **Personal-only** (observe_tool/instincts hooks, hardcoded buvis paths) | Exclude — won't ship |
| **Built-in** (`/doctor`, superpowers, etc.) | Ignore |
| **Soft coupling in non-cluster hooks** | Document as a stability contract in the plugin README (e.g. "session names must contain `<keyword>` for X to observe Y") |
| **Shell-function hit** | Make an explicit distribution decision before proceeding — see Phase 5d |
| **User-instructions hit** | Copy the text into the plugin's `AGENTS.md`, plan a follow-up cleanup of the user's CLAUDE.md/AGENTS.md |
| **MISSING-FROM-PLUGIN** | Expand cluster scope to include the missing hook/command/agent, then re-run check |

**Stop here and confirm with the user**: did the audit surface anything that needs to be added to the cluster, deferred, or distributed via a non-plugin channel? Do not proceed until the cluster is finalized and every shell-rc / user-instructions hit has an explicit plan.

## Phase 3: Naming (CHECKPOINT 2)

Per the AGENTS.md naming convention (evocative single words over descriptive concatenations): propose 3-4 distinct evocative names with one-line rationale each. Avoid `<adjective>-<noun>-suite` patterns. Look for:

- Concrete objects (whetstone, anvil, lighthouse)
- Mythological figures (warden, sentinel, hermes, aegis)
- Action verbs (hone, plumb, forge)
- Insider jokes / homages (strunk for style guides)
- Single-word and pronounceable

Use `AskUserQuestion` with options. Capture the choice as the **plugin name** (lowercase, no spaces) and substitute it for `<plugin-name>` in every command below as you dispatch it. Commands in this playbook never rely on shell variables: each Bash call starts a fresh shell, so a variable set in one call is empty in the next.

## Phase 4: Scaffolding

The repo path is `~/git/src/github.com/buvis/claude-<plugin-name>` (e.g. `/Users/bob/git/src/github.com/buvis/claude-warden`). **Substitute the concrete absolute path for `<repo>` in every command from here on as you dispatch it** — never assign it to a shell variable. Shell state does not survive between Bash calls, and an unset variable silently turns a path like `$REPO/skills` into the root-anchored `/skills`.

Create the repo skeleton:

```bash
mkdir -p <repo>/.claude-plugin <repo>/skills <repo>/dev/bin
```

If the cluster includes commands, hooks, or agents, run one more `mkdir -p` naming exactly the extra dirs (`<repo>/commands`, `<repo>/hooks`, `<repo>/agents`).

## Phase 5: Port components

For each item in the cluster:

**Skills**: `cp -r ~/.claude/skills/<name> <repo>/skills/`

**Commands**: `cp ~/.claude/commands/<name>.md <repo>/commands/`

**Agents**: `cp ~/.claude/agents/<name>.md <repo>/agents/`

**Hooks**: copy the script to `<repo>/hooks/<name>.py`, then create `<repo>/hooks/hooks.json` referencing it via `${CLAUDE_PLUGIN_ROOT}/hooks/<name>.py`. Cross-check `~/.claude/settings.json` to mirror the hook event/matcher.

Then apply three transforms:

### 5a. Path fixups

Skills with helper scripts must use `${CLAUDE_SKILL_DIR}` instead of `~/.claude/skills/<name>/scripts/...`:

```bash
rg -ln 'python3 ~/.claude/skills' <repo>/skills/
```

For each listed file, rewrite with the Edit tool: `~/.claude/skills/<this-skill>/scripts/foo.py` → `${CLAUDE_SKILL_DIR}/scripts/foo.py` (per-file, because the skill name in the path varies).

### 5b. Vendor cross-skill dependencies

If a skill in the cluster references scripts from a skill outside the cluster (e.g. `audit-skills` calling `create-skill/scripts/validate_skill.py`), copy the dependency into the dependent skill's own `scripts/` directory. Note in CHANGELOG as a snapshot/vendor.

### 5c. Sanitize personal references

```bash
rg -ln '/Users/bob|buvis-plugins|~/bim/|/dev/local/' <repo>/skills/ <repo>/commands/ <repo>/agents/ <repo>/hooks/
```

Name only the directories that actually exist (rg errors on missing paths). Note rg alternation is `|`, not grep's `\|`.

Each hit is one of:
- **Cosmetic example output** in SKILL.md (e.g., `/Users/bob/.claude` in sample tables): replace with `/Users/alice/.claude` or similar synthetic.
- **Real production reference** in code: stop and ask the user.

Also clean caches **repo-wide**, not just under `skills/*/scripts/`:

1. List them: `rg --files <repo> -g '*.pyc'` (a hit inside any `__pycache__/` marks that directory for removal; shipped plugins have carried stray `.pyc` under `lib/` before).
2. Delete each with an explicit concrete path, e.g. `rm -rf <repo>/lib/__pycache__` — before any `rm -rf`, verify the path exists and sits inside `<repo>`; never run it with an empty or unsubstituted prefix (the fact-forcing gate may ask for confirmation).
3. Verify ignores: `rg -n '__pycache__|\.pyc' <repo>/.gitignore` — add both patterns if missing.

### 5d. Shell-rc and user-instructions residue

If Phase 2 surfaced any shell-function or user-instructions hits, resolve them now — they can't ship as plugin files but they're part of the cluster's contract.

**Shell functions** (e.g. an `autoclaude` wrapping `/run-autopilot` in a loop):

- Plugins cannot install into `~/.zshrc` / `~/.bashrc` / `~/.config/bash/**`. Pick one:
  - **Ship as `bin/<name>` script** in the plugin repo. User sources or symlinks. Function body can reference `${CLAUDE_PLUGIN_ROOT}/...` if invoked with that env set, otherwise hard-code expected install paths.
  - **Leave in dotfiles** with paths updated to point at the plugin install location. Note that plugin install paths are version-suffixed (`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/...`) — use the **install-path symlink** or env discovery rather than literal version strings.
- Document the user-side install step in the plugin README ("Source `bin/<name>` from your shell rc").

**User instructions** (paragraphs in `~/.claude/{AGENTS,CLAUDE,GEMINI}.md`):

- Copy the relevant paragraphs into `<repo>/AGENTS.md` so plugin installers inherit them automatically.
- Leave a short pointer in the user's own CLAUDE.md (e.g. "see `<plugin>` plugin AGENTS.md") and queue the full-paragraph removal for Phase 11 cleanup.

## Phase 6: Plugin metadata

Write these files. Use exact schemas:

### `.claude-plugin/plugin.json`

```json
{
  "name": "<plugin-name>",
  "version": "0.1.0",
  "description": "<one-paragraph description, ~150 chars>",
  "author": { "name": "buvis" }
}
```

### `.claude-plugin/marketplace.json` (self-reference)

```json
{
  "name": "claude-<plugin-name>",
  "description": "<short description>",
  "owner": { "name": "buvis" },
  "plugins": [
    {
      "name": "<plugin-name>",
      "description": "<one-line>",
      "version": "0.1.0",
      "author": { "name": "buvis" },
      "source": "./",
      "category": "<category>"
    }
  ]
}
```

### `LICENSE` (MIT)

Copy from `claude-strunk/LICENSE` verbatim. Copyright year = current year. Holder = `buvis`.

### `.gitignore`

Standard Python + editor + Claude Code local. Copy from `claude-strunk/.gitignore`.

### `README.md`

Structure:
1. Title + license shield
2. Tagline / quote (1-2 lines, evocative)
3. **What's inside** table — skill name → trigger keywords
4. **Install** — `/plugin marketplace add buvis/claude-plugins` + `/plugin install <name>@buvis-plugins`
5. **Update** — `/plugin update <name>@buvis-plugins`
6. **Alternative: install directly from this repo** — `/plugin marketplace add buvis/claude-<name>`
7. **Why "<name>"** (optional, if the name has a story — strunk does, audit-suite doesn't)
8. **License: MIT**

### `CHANGELOG.md`

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - YYYY-MM-DD

### Added

- Initial release with N skills:
  - `skill-name` — one-line summary
  - ...
```

## Phase 7: Release tooling

Copy the release script template:

```bash
cp ~/.claude/skills/extract-plugin/references/release-script.sh.template <repo>/dev/bin/release
```

Edit `<repo>/dev/bin/release` and set `PLUGIN_NAME="<plugin-name>"` near the top (this variable lives inside the release script file, where it is fine — the ban is on variables spanning the playbook's own Bash calls).

```bash
chmod +x <repo>/dev/bin/release
```

```bash
bash -n <repo>/dev/bin/release
```

## Phase 8: Verification

For every skill in the new repo, validate its frontmatter — one validator run per skill directory, one command per Bash call (no shell loops; a `for` prefix breaks permission matching):

```bash
python3 ~/.claude/skills/create-skill/scripts/validate_skill.py <repo>/skills/<skill1>
```

If any skill has helper scripts with tests, locate them:

```bash
rg --files <repo>/skills -g 'test_*.py'
```

Then run each test file's parent directory without `cd`:

```bash
uv run --directory <parent-dir> --with pytest python -m pytest -q
```

## Phase 9: Git + GitHub remote (CHECKPOINT 3)

One command per Bash call, `<repo>` spelled concrete in each:

```bash
git -C <repo> init -b master
git -C <repo> add -A
git -C <repo> status --short   # show user
git -C <repo> commit -m "feat: initial release with N skills [and commands/hooks]"
git -C <repo> tag -a v0.1.0 -m "v0.1.0 - initial release"
gh repo create buvis/claude-<plugin-name> --public --source <repo> --remote origin \
  --description "<short description>"
```

**Stop here and confirm with the user before pushing.** Show the commit and the GitHub URL. After confirmation:

```bash
git -C <repo> push -u origin master
git -C <repo> push origin v0.1.0
```

## Phase 10: Marketplace registration

Edit `~/git/src/github.com/buvis/claude-plugins/.claude-plugin/marketplace.json`. Add a new entry to the `plugins` array:

```json
{
  "name": "<plugin-name>",
  "source": {
    "source": "url",
    "url": "https://github.com/buvis/claude-<plugin-name>.git"
  },
  "description": "<description matching plugin.json>",
  "version": "0.1.0"
}
```

Commit and push:

```bash
git -C ~/git/src/github.com/buvis/claude-plugins add .claude-plugin/marketplace.json
git -C ~/git/src/github.com/buvis/claude-plugins commit -m "feat: register <plugin-name> plugin v0.1.0"
git -C ~/git/src/github.com/buvis/claude-plugins push origin master
```

## Phase 11: Local cleanup (CHECKPOINT 4)

Tell the user the migration commands:

```
/plugin marketplace update buvis-plugins
/plugin install <plugin-name>@buvis-plugins
```

After they confirm the published plugin works, suggest (don't auto-run) the cleanup:

```bash
rm -rf ~/.claude/skills/{<skill1>,<skill2>,...}
# plus any commands/hooks/agents that were ported
```

If the cluster included hooks: also instruct the user to remove the corresponding `hooks` entries from `~/.claude/settings.json` (the plugin's `hooks/hooks.json` registers them now).

If Phase 2 found user-instructions residue: instruct the user to delete the migrated paragraphs from `~/.claude/{AGENTS,CLAUDE,GEMINI}.md` and replace with a short pointer to the plugin.

If Phase 2 found a shell function: instruct the user to source the plugin's `bin/<name>` script from their shell rc (or update the in-place function's paths). Show the exact line to add.

## Update memories

After successful publish, update `project_next_plugins_to_ship.md` to mark this cluster as shipped, and note any new candidates the readiness audit surfaced.

## Failure modes to watch

- **`${CLAUDE_SKILL_DIR}` shows as empty**: the bash invocation didn't originate from a skill context. Verify by running the failing command from inside Claude Code after a fresh install + restart.
- **Plugin install succeeds but skills don't appear**: stale session. Run `/reload-plugins` or restart Claude Code.
- **Skill name collision**: local copy still at `~/.claude/skills/<name>/` after plugin install. Move locals to `/tmp/backup/` to test plugin isolation; remove when confirmed.
- **Central marketplace bump forgotten**: `/plugin update` won't see new versions. Always bump all three places (plugin.json, self-ref, central) — the `dev/bin/release` script handles this for subsequent versions.
