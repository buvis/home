# Gallery mods: what is installed, from where, and what was declined

Ledger for herdr.dev/gallery mods. Update it when a mod is added, removed or
edited. Update tracking itself is hmod's: open Mod updates with Ctrl-Q `m` `u`,
or run `bin/hmod check` (data in `~/.local/state/herdr-mod-updater`; the clone
is `~/git/src/github.com/jonathan-fielding/herdr-mod-updater`).

Policy: no downloads of prebuilt binaries or release bundles from GitHub. Grep a
mod for `curl`, `releases/download`, `.tar.gz`, `fetch(` and installer scripts
before adding it.

## Installed 2026-11-08

Keys corrected 2026-11-24: on 2026-11-15 the per-mod `cmd-`/`ctrl-shift-` keys
left `keys.json`. Mods open from the Ctrl-Q popup (`mods/prefix/main.js`), and
since 2026-11-24 by name from the command palette (Ctrl-Q `:`).

| Mod folder | Source (gallery owner/repo, path) | Key | Local edits and notes |
|---|---|---|---|
| revive | dmazlum/herdr-revive 0.5.0 | Ctrl-Q `m` `r` | `revive.mjs install` not run yet: it edits ~/.claude/settings.json, ~/.codex/hooks.json and the bash login file. Its dialog needs node on Herdr's PATH (see Setup). |
| reviewer | vytasgavelis/herdr-reviewer 0.4.0 | Changes slot (`changes` child of `panel-body`); no `mod:reviewer` keys, the panel's buttons do it | Inline diff comments sent to the space's agent with `hc send`. Lost the slot to ship-it-changes on 2026-11-08, got it back on 2026-11-09 (its agent comments are the point; ship-it-changes only fed the strip's file count). hmod can't link it (`cloned_from: changes`). |
| obsidian | cunderw/herdr-obsidian | Ctrl-Q `m` `o` popup, Ctrl-Q `m` `O` panel | `obsidian.json` sets vault `~/bim`, editor nvim. mod:obsidian: ctrl-j/k, alt-enter send, cmd-s/ctrl-s save. PDF export needs two third-party bundles that are NOT in dotfiles (the repo is public; `.gitignore` lists them). On a new machine: `cd mods/obsidian/pdf && npm install && bun build convert.src.mjs --target node --outfile convert.mjs`, then `npm install --no-save mermaid && cp node_modules/mermaid/dist/mermaid.min.js .` (Mermaid diagrams print as source text without it). |
| markdown-panel | jlopezlira/herdr-kanso, markdown-panel/mods/markdown-panel | Ctrl-Q `m` `m` | Kanso Markdown `.md` handler app not installed. |
| ciupaga | rgonek/Ciupaga | Ctrl-Q `m` `t` | No key shipped. |
| copy-mode | zamonia500/herdr-copy-mode | Ctrl-Q `m` `x` | Runs nvim and hc in a terminal tab. |
| on-screen | kerembakir/herdr-mods, on-screen/mods/on-screen | Ctrl-Q `O`, right-click | `terminal_menu: on-screen` on the buvis root (items match shipped `menu` 0.1.13). Local changes: Markdown defaults to Folio preview; Right/Below/Tab placement for previews and terminal editors; other paths use the default app. Editor detection includes mise shims. hmod can't link it (`cloned_from: path-menu`). |
| folio | local | Cmd-click a Markdown path in a terminal; on-screen's Markdown actions | Link handler (`link_handlers` on the buvis root) since 0.1.17; reads `link.line`/`link.column` since 0.1.18. Read-only native Markdown preview; Neovim replaces it in place and quitting restores the preview. Watches file changes. `nvim.sh` uses native pane commands and preserves sizing; see `mods/folio/README.md`. |
| beeline | local (2026-11-24) | Cmd-click `file:line` in a terminal | Link handler after folio in `link_handlers`: opens the file in nvim at that line (and column), split right of the clicked pane. A link without a line stays with Herdr's default opener; remote terminals pass. `node --test mods/beeline/link.test.mjs`. |
| recall | shihyuho/herdr-recall | Ctrl-Q `e` | Opens a kept 2x2 tracker window `recall-tracker`. |
| attn-next | iml885203/herdr-mods, attn-next/mods/attn-next | Ctrl-Q `a` (cmd-shift-j/k inside) | |
| last-pane | ohneda/herdr-last-pane | ctrl-q ; | Floating 0x0 block `last-pane` on the buvis root; `;` added to mods/prefix KEYS. |
| worktreeinclude | madwire/herdr-worktreeinclude | Ctrl-Q `m` `i` (its second key, cmd-alt-shift-i, is unbound) | Writes `.git/hooks/post-checkout` into repos that have a `.worktreeinclude`. |
| mod-updater | jonathan-fielding/herdr-mod-updater (clone-installed) | Ctrl-Q `m` `u` | Installed with `bin/hmod mod install`; `bin/hmod` shim sets HMOD_HOME. Update it from the dialog (pulls the clone). The CLI reads mod sources from api.github.com (source files, no binaries). |
| filetree + file-icons | cybertron288/herdr-mods, filetree/mods/{filetree,file-icons} | Files slot; Ctrl-Q `f` toggles the panel | `files` child of `panel-body` now shows filetree (file-icons is its icon store). config.json `open` -> `bin/open-in-nvim {path}` (double-click opens the file in nvim, split right), so hmod shows it Edited locally. Optional Claude Code hook (`bridge.ts`, bun) not registered. Runs git, sh, find, stat, du, open; reads `~/.local/state/herdr-filetree/activity.jsonl`. In dotfiles since 2026-11-09 with the upstream MIT `LICENSE`, `LICENSE-claude-code-filetree` (the port's source) and `LICENSE-lucide` added. |
| file-picker | arjunmahishi/herdr-file-picker | Ctrl-Q `o` | `file-picker.json`: Enter opens the file in nvim (right split), ctrl-d git diff popup. picker.js lines 82 and 101: `/bin/sh -c` -> `-lc`, so the fzf and action shells read `~/.profile` (mise shims) whatever PATH herdr-core holds; hmod shows it Edited locally, redo after an update. Not in dotfiles (only `file-picker.json` is): the upstream repo has no license, so the code is not redistributable; reinstall with hmod. |
| tab-notes | unknown (not in ashrodan/ship-it; hmod can't link it) | Notes child of `panel-body` | Per-tab notes in `~/.config/herdr-app/tab-notes/` (gitignored). Ships `LICENSE-lucide`. |
| walkthrough | dmazlum/herdr-walkthrough 0.10.0 (8d35fd1), added 2026-11-24 | Ctrl-Q `m` `w`, palette "Walkthrough" (upstream's cmd-shift-k is not bound) | A model orders a diff into steps and explains each (Uncommitted, Staged, Branch, Commit, Pull request); it explains, it does not judge. Local edits, kept by `node --test tests/walkthrough-local.test.mjs`: `engine.js` `programOf` starts `bin/run-claude-pat` (claude with the setup token; a bare `claude` from Herdr has no token and its OAuth login expires); `view.js` shows the shared ring in its 5 busy states (helper `ring`); upstream MIT `LICENSE` added. Not installed: the "Last turn" hooks (the agent sandbox cannot write `~/.herdr`, and each prompt would snapshot the tree); Record stays off. On Generate it sends the diff, untracked files up to 1 MB, and up to 6,000 characters of the prompts typed to Claude, pi and codex in that repo (read from `~/.claude/projects`, `~/.pi`, `~/.codex`) to the model. The Pull request tab needs `gh` and GitHub. Its update strip: press "Stop checking" when it first shows, and never use its "Copy prompt" (an agent that follows it replaces the folder and drops the edits); update with `bin/hmod-merge walkthrough`. State: `~/.herdr/walkthrough/`. Audit 2026-11-24 (every file read): no download, no config edit; `find "$@"` in `lib/sources.js:188` and `hooks/turn.sh:47` reads an untracked file name that starts with `-` as an option (Last turn flows only). |

Installed by another session the same evening, not through this ledger:
ship-it, ship-it-changes, ship-it-file, ship-it-prs, ship-it-review
(ashrodan/ship-it): a 40px strip under the tabs and panel children
ship-it-review and ship-it-prs. ship-it-changes held the `changes` slot from
2026-11-08 to 2026-11-09, when reviewer took it back; its folder was deleted
2026-11-10 together with the strip's dead `pr-changes` button (it rendered only
with a `ship-it-changes` block). PR, checks, Review, PRs and Ship are unaffected. No downloads or network calls in its code.
In dotfiles since 2026-11-09 with the upstream MIT `LICENSE` in each folder and
`LICENSE-lucide` beside the icons. Local edit: `GH` in main.js and data.js is
`() => \`${appHome()}/bin/ghx\`` (gh with Bitbucket Cloud support) instead of
upstream's `gh`; redo after an update. Local edit 2026-11-10: the strip
always shows the folder (upstream hides it at a repo root) and, beside it, the
uncommitted files/+/− (`git diff HEAD`), or when clean the branch's since its
base ("vs master"), as a button that toggles the `changes` panel (reviewer);
my-tabs dropped its Files and Changes buttons for these and moved `+` beside
the last tab. A deleted folder (a removed worktree) shows "folder deleted"
instead of silently looking like a non-repo. Local edit 2026-11-10: Create PR
(strip and review) calls `createPr` in data.js. On GitHub it hands the PR to
an agent (`prTask` is the prompt): an idle or done agent already in the
checkout gets it with `hc send --if idle`, else the first installed agent
starts in a "Create PR" tab; the button spins until the PR shows (5 min at
most). Bitbucket, GitLab and no installed agent: push a branch with no
upstream, then `gh pr create --web`, failures as a toast (upstream ran gh
alone and dropped its "you must first push" error). data.js is copied to all
four ship-it folders. Local edit 2026-11-10: an open PR row in ship-it-prs
offers "Review with <agent>" per installed agent (as ship-it-issues does for
issues): it starts the agent in a `#<n> <agent>` tab in the PR's checkout
(created if missing) with `reviewTask` in main.js as the prompt. Both panels
add `-i` before the task for Copilot (`copilot "<prompt>"` is rejected);
`programs.json` runs Kiro as `kiro-cli chat` for the same reason and retires
Gemini with `"run": []` (CLI discontinued; ship-it and my-new-menu skip
agents with an empty `run`). on-screen's pane
menu gained Copy path and Copy branch name the same day.
Local edit for PRD 00006: ship-it-prs and ship-it-issues read shared "runway.show" at the top of render and expand that PR or issue (the runway mod's chip jump).
Local edit 2026-11-16: Ship ran `ship(cx)` straight from the click and used
the click's `cx` after an await ("cx is no longer valid"); it now runs in
`cx.spawn`. The strip's own message banner is gone: `say` posts `notify()`,
so errors land in the status bar log (my-toast, see below). data.js exports
`backTo()`; createPr and the error paths in ship-it-review, -prs and -issues
capture it before their first await, so each error's Go leads to the terminal
the action started from.

## Notification history (updated 2026-11-24)

The buvis layout sets `"toast": "my-toast"` (clone of `toast`) and its status
block shows `my-status` (clone of `workspace-status`). Every toast enters shared
`alerts.log`: the newest 50 routine notices, plus all errors and warnings until
Clear. The Notifications count opens full text (selectable, Copy, Copy all,
Clear, Go to terminal/pane); `my-status.log` opens it too. The count is red for
errors, amber for warnings, otherwise muted. Errors and warnings go straight
to the log instead of popping up, except Herdr's `agent.focus` "needs you"
toasts, which stay visible and are also logged. Info and success still pop up.
Herdr 0.1.17 always expires native toasts; `timeout: 0` is not persistent.
A mod that reports after an await passes
`action: {name: "pane.focus", args: {terminal} | {pane}}` captured at the start.
Gallery mods edited for that, redo after an hmod update: file-picker (Go to
where the picker was opened), reviewer `ask.js` (Send failed goes to the
agent). Local: move-pane, folio, runway. The other gallery mods' errors
(obsidian, filetree, on-screen) come within a second of the click, so the
focused terminal at post time is right; left unedited to keep hmod updates clean.

## Custom mod fixes (2026-11-24)

2026-11-24: selectively ported 0.1.17 fixes into my-agents (kept-child Done
status and parent priority), my-tabs/my-agents/my-space-folders/my-spaces
(saved-state recovery), and my-toast (full text with scrolling). Herdr only
auto-sizes its shipped toast, so the custom card keeps its fixed height.
Local branch labels, hold-in-Done, and the error log remain. Provenance versions
remain unchanged because these are partial ports. Regression command:
`node --test tests/mod-ports.test.mjs`. See
`docs/dev/project-management/reviews/herdr-mod-ports-2026-11-24.md`.

Toast durations now use milliseconds. Check-mode startup skips background work.
See `docs/dev/project-management/reviews/herdr-checker-closeout-2026-11-24.md`.

2026-11-24: adapted four Mission Control ideas. Agent task titles appear in
`my-pane` headers. Recall tracks recently closed tabs and uses Revive's
session record to reopen an agent. Ship It PRs shows open pull requests,
review requests and failing checks across GitHub and Bitbucket spaces. The Claude
status line keeps Ponytail and sends the reported context reading and session
ID to herdr-core for the agent list. Jira workstream queues are in project intake.

## Herdr 0.1.18 round (2026-11-24)

Report: `docs/dev/project-management/reviews/herdr-0.1.18-opportunities-2026-11-24.md`.

- `my-worktree` is shipped `worktree` 0.1.18 plus the ring spinner (2 lines).
  It stops the space's programs before git deletes the checkout, refuses a
  locked worktree and the main checkout, reads `worktrees.directory` and gives
  git 10 minutes. On each release: copy shipped `main.js` over it and redo the
  spinner line. `node --test mods/my-worktree/remove.test.mjs`.
- Polls wait while the window is hidden (minimized, covered, on another
  Space). Local edits, redo after a merge: ship-it `data.js` (`windowHidden`
  in `panelShown` and `modShown`; copy the file to the three other ship-it
  folders), ship-it `main.js` (`back(cx)`, its three timers, one line in
  `render`; after an absence of 30 s or more the first look refreshes git and
  the PR; `watchAgents` still runs hidden, because it acts only when an agent
  stops), ship-it-prs `main.js` (`refreshQueue` marks a load that was dropped
  out of sight as stale), reviewer `main.js` (the 10 s timer). Also
  my-space-folders (two 15 s timers) and runway (`onTick`). Not done on
  purpose: filetree (merge lane), pager (it must alert while hidden).
  `node --test tests/window-hidden.test.mjs`.
- Links: folio reads `link.line` and `link.column`; the new local mod
  `beeline` opens `file:line` in nvim (table above).
- Look: `"veil": 0.3` on the pane frame in `layouts/buvis.json`. Herdr draws
  the veil over the terminal area only, and for the same selected pane that
  `my-pane` uses for its header fade, so the two do not stack. The header
  fade went from 0.35 to 0.55, so the title stays readable beside the veil.
- Palette: the Ctrl-Q `m` list is mirrored in `mods/prefix/mod.json`
  `palette`; `my-status` adds "Notification log".
  `node --test mods/prefix/palette.test.mjs`.
- tab-notes colors Markdown from the theme
  (`node --test mods/tab-notes/colors.test.mjs`).

## Keeping mods current (2026-11-16)

Three lanes; `bin/hmod-merge status` shows all of them.

- **hmod** (linked, unedited): `hmod update --all` in sysup. A mod's first
  update is never automatic (`first_update_pending`): run `hmod update <mod>`.
- **merge** (linked, edited: revive, file-picker, filetree, worktreeinclude,
  ciupaga, file-icons, walkthrough): `bin/hmod-merge <mod>` 3-way merges upstream into the
  local files (base = hmod's recorded install commit), checks, backs up, and
  records the new baseline in hmod's sources.json. A conflict changes nothing.
  Never `hmod update --force` these: it replaces the edits.
- **fork** (`forks.json`: ship-it, ship-it-prs, ship-it-review, ship-it-file,
  reviewer, on-screen): rewritten here or refused by hmod (`cloned_from`).
  Same merge engine, base = the commit in forks.json, never unattended. Install
  commits found 2026-11-16 from the mods' versions and dates.
- Ours, nothing upstream: ship-it-issues, tab-notes, folio, runway, and the
  other local mods. my-* clones of Herdr's own mods: gems PRDs 00156/00160.

2026-11-18 round: recall a7b0134 and markdown-panel 8375f11 (hmod), revive
0.11.0 (hmod-merge; its spinner edit redone on 0.8's new dialog), reviewer
0.6.0 (fork merged, two spinner conflicts resolved by hand). Reviewed first:
markdown-panel 3.30 vendors Kanso's platform library (process kill, Docker,
Herdr restart, keystroke paste); only its file, `userHome` and clipboard-read
parts are called. revive 0.8+ asks GitHub's releases API once a day while its
dialog is open: turned off with its own "Stop checking" flag (shared
`revive.update.off`), not by editing `CHECK`, because a line next to
`VERSION` conflicts on every release. Keep local edits away from lines
upstream bumps; prefer settings and shared state over code edits.

2026-11-24 round: markdown-panel c0fe910 (adds saving edits, local and
remote, with a changed-on-disk check; no network) and revive 0.12.1 (Muse,
Code Mode; merged, spinner edits kept) via sysup. ship-it fork: upstream
1a9978d (Ship = a 3 s stoppable countdown instead of the confirm, `--admin`
override when branch rules block, confetti mod `ship-it-confetti`) was NOT
taken: it conflicts in 5 places with this fork's own Ship flow (fresh PR
re-read, ghx/Bitbucket, Clean up, `say()` error log), and its GraphQL query
needs GitHub. forks.json marks 1a9978d as seen; port it by hand if wanted.
obsidian 0998781 (a stale viewer opens a new pane) merged over another
session's local edits (export, copy) by 10:40 the same day; check passed.

sysup `herdr-mods` (personal override in `~/.config/buvis/buvis-sysup.yaml`)
runs `hmod update --all`, then `hmod-merge --auto`: edited mods past their
first update merge unattended; everything that needs a decision fails the
step with the command to run, so it stays in sysup's attention until done.

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
