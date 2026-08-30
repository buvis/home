# Hook Locations

The enumerated surface a guard can actually live on. A guard proposal naming a
location outside this set is a defect. Every location below carries the command
that enumerates it; when one fails, the guard proposal that would have named it
**fails loudly**. Never name a location you did not read.

The plugin half is discovered at run time, never pinned. Version counts and
plugin names below are examples from the last sweep (2026-08-30), not a list to
trust.

## 1. `~/.claude/settings.json` hooks block

```bash
jq -c '.hooks' ~/.claude/settings.json
```

Events wired today: `SessionStart` (matcher `compact`), `PreToolUse`,
`PostToolUse`, `Stop`, `Notification`. Three funnel into one dispatcher
(`dispatch.py pre|post|stop`); `SessionStart` and `Notification` call their
handlers directly.

The hazard here is not a second command under one event - those fire once each,
which is how `notify.py` and `reinject_contract_card.py` are wired. It is
registering the **same handler** in both this block and `ROUTES` (or a plugin
`hooks.json`): that fires it twice per tool call. See the comment at
`dispatch.py:54-62`.

## 2. `~/.claude/hooks/dispatch.py` `ROUTES`

```bash
rg -n "^ROUTES|^PLUGIN_OWNED|^RETIRED" ~/.claude/hooks/dispatch.py
```

Read all three sets:

- `ROUTES` - the live handlers, each a `Route(event, matcher, name, path, timeout, kind=...)`.
- `PLUGIN_OWNED` - handlers that moved into a plugin. Routing one here again
  double-fires it. Do not propose a route with a name in this set.
- `RETIRED` - handlers deliberately deleted. Proposing one back re-litigates a
  settled decision; read the comment above the set first.

`kind` does **not** decide whether a handler can block. `_aggregate`
(`dispatch.py:435`) blocks on any exit 2 regardless of kind. `kind` picks the
exit code only when a handler produced no decision at all - crash, missing
`run()`, timeout: `enforcement` fails closed (2), `observer` fails open (0).
See `_no_decision_code` (`dispatch.py:227`).

This is the default home for a new Claude-side guard.

## 3. Plugin `hooks/hooks.json` (discover live)

Resolve the active version first - several are cached per plugin and only the
installed one fires:

```bash
jq -r '.plugins | to_entries[] | "\(.key) \(.value[].version) \(.value[].installPath)"' ~/.claude/plugins/installed_plugins.json
```

Then list the hook files under those install paths:

```bash
rg --files ~/.claude/plugins/cache -g 'hooks.json'
```

Last sweep: five plugins carry a `hooks.json` - `aegis`, `warden`, `loupe`,
`ponytail`, `autopilot`. A guard proposed into a plugin also needs a release and
a `/plugin update` before it is live: a plugin PRD is not done until released
**and** installed.

## 4. `warden.yaml`

```bash
ls ~/.claude/warden.yaml; rg --files . -g '.claude/warden.yaml'
```

Global at `~/.claude/warden.yaml`, per-repo at `<repo>/.claude/warden.yaml`.
The place for Bash-command gating (allow / ask / deny). `ask` deadlocks
unattended sessions; under `WARDEN_UNATTENDED=1` it degrades to deny.

## 5. `~/.codex/hooks`

```bash
ls ~/.codex/hooks
```

Codex's own copies. Machine-local and gitignored **except** `notify.py`, a
buvis-tracked symlink to `~/.claude/hooks/notify.py`. A guard that must hold on
both hosts needs a decision here too; one that only makes sense inside Claude
does not.

## 6. `autopilot loop` wrapper breakers

Resolve the installed autopilot root via location 3, then:

```bash
rg -n "breaker" <installPath>/skills/run-autopilot/cli/loop.py
rg -n "autoclaude" ~/.config/bash/plugins/development.plugin.bash
```

The `loop.py` module docstring enumerates the live breakers: memory
circuit-breaker, loop registry + duplicate guard, plugin-pin preflight,
usage-limit wait, network-outage poll, died-retry + park marker,
progress-fingerprint bound.

The right location only for an incident that kills or wedges a **batch**, not
one a single tool call causes.

## What blocks, and what does not

`PreToolUse` blocks on exit 2. **`Stop` also blocks on exit 2** - the installed
autopilot plugin ships one (`skills/run-autopilot/scripts/review_coverage_hook.py`),
and it works headless.

`PostToolUse` exit 2 does **not** block. It only feeds stderr back to the model.
A proposal that relies on `PostToolUse` to gate is invalid on arrival, whichever
location it names.

(PRD 00156 stated the narrower "only `PreToolUse` can block". Corrected here
against `dispatch.py:227-241` and the Stop hook above, 2026-08-30.)
