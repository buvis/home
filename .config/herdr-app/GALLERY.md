# Gallery mods: what is installed, from where, and what was declined

Ledger for herdr.dev/gallery mods. Update it when a mod is added, removed or
edited. Update tracking itself is hmod's: open Mod updates with `cmd-shift-u`,
or run `bin/hmod check` (data in `~/.local/state/herdr-mod-updater`; the clone
is `~/git/src/github.com/jonathan-fielding/herdr-mod-updater`).

Policy: no downloads of prebuilt binaries or release bundles from GitHub. Grep a
mod for `curl`, `releases/download`, `.tar.gz`, `fetch(` and installer scripts
before adding it.

## Installed 2026-11-08

| Mod folder | Source (gallery owner/repo, path) | Key | Local edits and notes |
|---|---|---|---|
| revive | dmazlum/herdr-revive 0.5.0 | cmd-alt-r | Key moved from cmd-shift-r (space.rename). `revive.mjs install` not run yet: it edits ~/.claude/settings.json, ~/.codex/hooks.json and the bash login file. Its dialog needs node on Herdr's PATH (see Setup). |
| reviewer | vytasgavelis/herdr-reviewer 0.4.0 | (Changes slot) | Was the `changes` child of `panel-body`; another session replaced it with ship-it-changes the same evening. The folder stays installed and unreferenced. hmod can't link it (`cloned_from: changes`). |
| obsidian | cunderw/herdr-obsidian | cmd-shift-n popup, cmd-alt-n panel | Keys moved from ctrl-b f / ctrl-b a. `obsidian.json` sets vault `~/bim`, editor nvim. mod:obsidian: ctrl-j/k, alt-enter send, cmd-s/ctrl-s save. |
| markdown-panel | jlopezlira/herdr-kanso, markdown-panel/mods/markdown-panel | cmd-shift-m | Kanso Markdown `.md` handler app not installed. |
| ciupaga | rgonek/Ciupaga | cmd-alt-t | No key shipped; cmd-alt-t chosen. |
| copy-mode | zamonia500/herdr-copy-mode | ctrl-shift-x | Runs nvim and hc in a terminal tab. |
| on-screen | kerembakir/herdr-mods, on-screen/mods/on-screen | cmd-shift-o, right-click | `terminal_menu: on-screen` on the buvis root (items match shipped `menu` 0.1.13). hmod can't link it (`cloned_from: path-menu`). |
| recall | shihyuho/herdr-recall | cmd-e | Opens a kept 2x2 tracker window `recall-tracker`. |
| attn-next | iml885203/herdr-mods, attn-next/mods/attn-next | cmd-shift-j (J/K inside) | |
| last-pane | ohneda/herdr-last-pane | ctrl-q ; | Floating 0x0 block `last-pane` on the buvis root; `;` added to mods/prefix KEYS. |
| worktreeinclude | madwire/herdr-worktreeinclude | cmd-alt-i, cmd-alt-shift-i | Writes `.git/hooks/post-checkout` into repos that have a `.worktreeinclude`. |
| mod-updater | jonathan-fielding/herdr-mod-updater (clone-installed) | cmd-shift-u, ctrl-shift-u | Installed with `bin/hmod mod install`; `bin/hmod` shim sets HMOD_HOME. Update it from the dialog (pulls the clone). The CLI reads mod sources from api.github.com (source files, no binaries). |
| filetree + file-icons | cybertron288/herdr-mods, filetree/mods/{filetree,file-icons} | Files slot; cmd-shift-e toggles the panel | `files` child of `panel-body` now shows filetree (file-icons is its icon store). config.json `open` -> `bin/open-in-nvim {path}` (double-click opens the file in nvim, split right), so hmod shows it Edited locally. Optional Claude Code hook (`bridge.ts`, bun) not registered. Runs git, sh, find, stat, du, open; reads `~/.local/state/herdr-filetree/activity.jsonl`. In dotfiles since 2026-11-09 with the upstream MIT `LICENSE`, `LICENSE-claude-code-filetree` (the port's source) and `LICENSE-lucide` added. |
| file-picker | arjunmahishi/herdr-file-picker | cmd-o | `file-picker.json`: Enter opens the file in nvim (right split), ctrl-d git diff popup. picker.js lines 82 and 101: `/bin/sh -c` -> `-lc`, so the fzf and action shells read `~/.profile` (mise shims) whatever PATH herdr-core holds; hmod shows it Edited locally, redo after an update. Not in dotfiles (only `file-picker.json` is): the upstream repo has no license, so the code is not redistributable; reinstall with hmod. |
| tab-notes | unknown (not in ashrodan/ship-it; hmod can't link it) | Notes child of `panel-body` | Per-tab notes in `~/.config/herdr-app/tab-notes/` (gitignored). Ships `LICENSE-lucide`. |

Installed by another session the same evening, not through this ledger:
ship-it, ship-it-changes, ship-it-file, ship-it-prs, ship-it-review
(ashrodan/ship-it): a 40px strip under the tabs and three panel children; it
took the `changes` slot from reviewer. No downloads or network calls in its code.
In dotfiles since 2026-11-09 with the upstream MIT `LICENSE` in each folder and
`LICENSE-lucide` beside the icons. Local edit: `GH` in main.js and data.js is
`() => \`${appHome()}/bin/ghx\`` (gh with Bitbucket Cloud support) instead of
upstream's `gh`; redo after an update.

## Setup done 2026-11-08

- `~/.profile` line 40 puts `~/.local/share/mise/shims` on PATH, so Herdr's
  `exec` (a non-interactive login shell; `.bashrc` returns before
  `mise activate`) finds node, fzf, rg, nvim. Takes effect after a Herdr relaunch.
- herdr-nvim's leftover runtime removed.
- Revive hooks installed (`doctor`: claude, codex, pi, bash).

herdr-core keeps the PATH it started with (2026-11-09: still the pre-change
one, up 8 h), so `hc run` shells don't see mise tools until the core restarts:
Ciupaga tasks that need npm or just fail until then. `hc server restart` parks
kept terminals (agents become shells; Revive resumes only sessions started
after its hooks were installed), so do it at a quiet moment, from your own
terminal, or let the next reboot do it.

Optional, not done: `ln -s ~/.config/herdr-app/bin/hmod ~/.local/bin/hmod`;
filetree's Claude Code hook (4 entries in `~/.claude/settings.json` running
`bun "$HOME/.config/herdr-app/mods/filetree/bridge.ts"`, recipe section
"Optional Claude Code hook"); `herdr-app do app.welcome` to show the Files and
Changes buttons again (`workspace.panels`).

## Declined

| Mod | Why |
|---|---|
| github (mrolafsson) | Installed 2026-11-08, removed the same day: it downloads the `herdr-github` release binary from GitHub on first open. |
| herdr-nvim (ChmaraX) | Installed 2026-11-08 22:32 by its installer (release bundle download), uninstalled with its own `--uninstall` the same evening: policy. |
| usage-limits (nozikov) | Installed 2026-11-08, removed the same day on request. Also: `claude -p` every 5 min would use the Keychain OAuth login; the setup token reports no rate limits. |
| quote-reply (daniel7an) | Installed 2026-11-08, removed the same day on request. |
| Agent sessions (cunderw) | Not wanted. |
| Kiosk, Telescope, Sheepdog, WASM Mods, Mission Control | Need a downloaded helper program or installer. |
| Tab bar, spaces sidebar, pane header replacements (Auto tabs, Session titles, Better *, Spaces *, Paddock, Crest, ...) | Collide with the my-tabs, my-spaces/my-space-folders, my-pane clones. |
| Splits Nav | mods/nav already does ctrl-h/j/k/l with nvim. |
| Desktop notifications | mods/pager covers desktop and phone alerts. |
| Automations, Automate everything, Task scheduler | Overlap the autoclaude loop and the sysup rule for recurring work. |
| Linear, Jira, Sentry, Vercel, Cloudflare, Kubernetes, Pokémon family | Not used. |
