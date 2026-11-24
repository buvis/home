# This machine's Herdr setup

Notes for every agent that works in this folder. Herdr never writes this file.
A date marks when a fact was last checked. Started 2026-11-24 from Claude's
project memory, so that Codex, Copilot, Kiro and Pi see the same facts.

## Where things are

- The shown layout is `layouts/buvis.json`, not `main`.
- This folder is not a git repository. Its files are tracked in the bare
  dotfiles repo `~/.buvis` (work-tree `$HOME`, branch `master`). The agent
  sandbox cannot write that repo: stage and commit through `~/bin/warrant`.
  Anchor every pathspec with `:(top)`.
- `/run-autopilot` and `autoclaude` cannot run here (no repository). PRDs in
  `docs/dev/project-management/prds/` are built in attended sessions.
- Several agent sessions edit this home at the same time. Read a file again
  immediately before you edit it. Do not revert a change you did not make.
- `GALLERY.md` is the ledger of installed gallery mods, their keys, their
  local edits, and the declined mods. Update it with each change.
- After a Herdr update, the review of what to use is in
  `docs/dev/project-management/reviews/herdr-<version>-opportunities-<date>.md`.

## Clones of shipped mods

Shipped mods are replaced on each start. Edit the `my-*` clone, never the
shipped mod.

| Clone | Of | Why it exists |
|---|---|---|
| `my-space-folders` | `spaces` | Spaces in folders; the `spaces` slot of the layout |
| `my-agents` | `agents` | Branch labels, hold-in-Done, agent titles |
| `my-tabs` | `tabs` | Panel buttons (Runway, Projects, Notes), `+` beside the last tab |
| `my-pane` | `pane` | Pane header: unfocused headers fade, right-click opens `my-menu` |
| `my-menu`, `my-new-menu` | `menu`, `new-menu` | Open `my-worktree`; skip agents with an empty `run` |
| `my-worktree` | `worktree` 0.1.18 | Only local edit: the ring spinner (2 lines). Rebase it on each release |
| `my-status`, `my-toast` | `workspace-status`, `toast` | Notification log (below) |
| `my-spaces` | `spaces` | Old clone, not in the layout |

Who opens whom (2026-11-24): `my-tabs`, `my-pane`, `my-space-folders`,
`my-spaces` and `ship-it` open `my-menu`; `my-tabs` opens `my-new-menu`;
`my-menu`, `my-new-menu` and `runway` open `my-worktree`. Keep this chain when
you rename or replace one of them.

## Keys

- `keys.json` is edited, so Herdr adds no new default keys. Add them by hand.
- Ctrl-Q opens `mods/prefix` (a tmux-style popup). Its key table is in
  `mods/prefix/main.js`. `m` opens the mods list, `:` the command palette,
  `r` resize mode.
- The mods list (`MOD_ITEMS`) is mirrored in `mods/prefix/mod.json`
  `palette`. `node --test mods/prefix/palette.test.mjs` fails when they drift.

## Rules and decisions of the person

- **One busy indicator.** Each slow action or loading state shows the shared
  ring beside its label:
  `svg("mods/workspace-chrome/spinner.svg").size(12).flex_none().text_color(t.working).spin(900)`.
  No text-only "Working…", no braille frames, no other speeds.
- **Errors go to the log.** Call `notify({level: "error"})`; do not draw a
  banner in the mod. `my-toast` records errors and warnings in shared
  `alerts.log`; the status bar count opens it. When you report after an
  `await`, pass `action: {name: "pane.focus", args: {terminal}}` that you
  captured at the start, so "Go to terminal" leads back.
- **No prebuilt binaries from GitHub.** Before you add a mod, search it for
  `curl`, `releases/download`, `.tar.gz`, `fetch(` and installer scripts.
  Cloning source and copying JavaScript mods is accepted.
- **Polls stop while the window is hidden.** A timer that runs a program
  checks `window()?.visible === false` first
  (`node --test tests/window-hidden.test.mjs`). `pager` is the exception: it
  must alert while the window is hidden. Decided 2026-11-24.

## The live window

This is an agent's note, not a rule from the person. The window is the
person's display, and they work in it while agents run. A space or tab
switch, or a dialog, takes their keyboard: their next keys go to the wrong
place. Look with `herdr-app shot`. To see a state that is not on screen,
use a tab of your own and keep the switch as short as you can.

## Traps that `herdr-app check` does not catch

- `h_flex()` centers its children vertically. A `flex_1` child with
  `size_full()` content gets height 0. Add `.items_stretch()` to the row or
  `.h_full()` to the child.
- Rows of `v_virtual_list` may not register handlers; such rows do not draw.
  Use `on_item_click` on the list, or a plain scrolling `v_flex`.
- Write `mod.json` before `main.js`. Herdr docks a folder without `mod.json`
  into the shown layout as a 320 px column. After you delete a mod, remove
  its block from the layouts.
- A hot reload leaves the old `nextCommand()` loop waiting: the first
  `<mod>.<command>` after a save is lost. Send a throwaway command first.
- An `async` method that uses a click's `cx` after an `await` throws
  "cx is no longer valid". Wrap it: `on_click((_e, cx) => cx.spawn(async (cx) => ...))`.
- `exec(cmd, args, {cwd})` rejects with an empty reason when `cwd` is gone.
  Give error text a fallback.
- `focus()` inside `render` throws. Call it from a timer, a task or a handler.
- A `"focusable": true` mod gets `"focus"` only from `pane.go`, not when its
  tab opens. `mods/sudoku` (`takeKeyboard`) shows the way to handle that.
- `overlay.close` does not close an `openOverlay({kind: "window"})`. Give a
  window mod its own close command.
- Herdr's JavaScript engine is about 12 times slower than node for compute,
  and long synchronous work is interrupted. Precompute in node or split the
  work across timer ticks.
- `exec` from a mod uses a non-interactive login shell: tools come from the
  mise shims that `~/.profile` puts on PATH. herdr-core keeps the PATH it
  started with, so in `hc run` use `/bin/sh -lc`.
- After a check passes, look at the mod in the app (`herdr-app shot`). The
  check renders once, without layout.

## Gallery mods

- Update lanes: `bin/hmod` (unedited), `bin/hmod-merge <mod>` (edited, 3-way
  merge), `forks.json` (rewritten here: the ship-it family, reviewer,
  on-screen; merge by hand). `bin/hmod-merge status` shows all lanes.
- Never run `hmod update --force` on an edited mod: it replaces the edits.
- An edit to a gallery mod costs a merge on each upstream release. Prefer the
  mod's own settings or shared state. Keep edits away from lines that
  upstream changes each release (version constants).
- `mods/ship-it/data.js` is copied byte for byte to `ship-it-prs`,
  `ship-it-review` and `ship-it-issues`. Edit one, copy to the others.
- Agent's note, checked 2026-11-24. A mod that starts `claude` itself does
  not go through `run-agent`, so it gets no setup token and would use the
  Keychain login. Start it through a wrapper that sets only
  `CLAUDE_CODE_OAUTH_TOKEN` from `~/.local/secrets/claude-setup-token`:
  `claude -p` then works from a clean environment. Inside an agent session,
  a nested `claude -p` with the inherited environment failed to authenticate.
- Agent's note, checked 2026-11-24. The agent sandbox cannot write `~/.herdr`
  (`sandbox-exec` with the profile: "Operation not permitted"). A Claude hook
  of a mod that keeps its state there does nothing in agent sessions, and
  shows no message. `~/.local/state` is writable.

## Tests

Run from this folder with `node --test <file>`:
`tests/*.test.mjs`, `mods/my-worktree/remove.test.mjs`,
`mods/prefix/*.test.mjs`, `mods/folio/*.test.mjs`, `mods/beeline/link.test.mjs`,
`mods/tab-notes/colors.test.mjs`, `mods/runway/*.test.mjs`. They load the real
mod code against stand-ins for `herdr`, `gpui-kit` and `gpui-base`.
