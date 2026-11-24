# Herdr 0.1.18 environment opportunities

Reviewed 2026-11-24T20:37Z. Scope: compare the 0.1.18 update (released and
installed 2026-11-24) with the personal `buvis` layout and its mods. This is
an assessment, not an implementation. It follows
`herdr-0.1.17-opportunities-2026-11-24.md`; open items from that report are
marked "carried".

## Evidence and limits

- `herdr-app --version` reports 0.1.18. `herdr-app status` reports layout
  `buvis` and `errors: []`. This does not prove every deferred mod action works.
- Read `update-notes-cache.md`, the installed guide, `herdr.d.ts`, `keys.json`,
  `settings.json`, `layouts/buvis.json`, and the mods named below. Compared
  `my-worktree` with shipped `worktree` by diff.
- No configuration, mod or terminal changed. No `herdr-app check` ran.
- Shipped mods are not in the dotfiles repo, so there is no diff of what
  0.1.18 changed inside them. Clone drift was checked only where the
  changelog names a fix.

## Ranked opportunities

### 1. Rebase my-worktree on the shipped 0.1.18 mod (carried, now easier)

`mods/my-worktree/main.js:222` deletes the checkout and line 224 closes the
space after that. Programs in the space still run while Git deletes their
folder. 0.1.18 fixes this in shipped `worktree` (#1430): it closes the space,
waits up to 10 s for its terminals to stop, then removes the checkout.

The clone also lacks, from 0.1.16 and 0.1.17: the lock check, the
main-checkout guard in `work` (line 171), the 600 s Git timeout (the default
`exec` timeout is 30 s, so a slow `git worktree add` fails), folder names for
non-Latin branches, `.bare` repository names, and `machine: this.on ?? ""`.

The reason for the clone is gone. Shipped `worktree` reads
`worktrees.directory`, and `settings.json` already sets `~/git/src/worktrees`.
The only local edit left is the ring spinner (2 lines).

Recommended: copy shipped `main.js` over the clone, apply the spinner edit
again, set `cloned_from.version` to 0.1.18. This is smaller and safer than a
hunk-by-hunk port. Close it with a test that a refused removal does not close
the space, and a live remove of a scratch worktree.

### 2. Create AGENTS.local.md

The file does not exist. 0.1.18 makes every agent in this folder read it, and
Herdr never overwrites it. Setup knowledge now lives in Claude's project
memory (11 files), which Codex, Copilot, Kiro and Pi do not load.

Seed it from that memory: the `my-*` clone chain, the mod traps that
`herdr-app check` does not catch, the ring-spinner rule, the no-binary
download policy, the hmod lanes, and the commit route (warrant). Track it in
the dotfiles repo. Keep `GALLERY.md` as the ledger and link to it.

### 3. Stop polling while the window is hidden

`window()?.visible` is new. No mod here reads it. These timers run Git or
`gh` for as long as the app is open, once their block was shown:
`ship-it/main.js:55` (5 s), `reviewer/main.js:162` (10 s),
`ship-it-review/main.js:64,67` (20 s, 10 s), `my-space-folders/main.js:248,251`
(15 s), `ship-it-prs/main.js:44` (60 s), `runway/main.js:81` (30 s).

The 0.1.18 CPU fix for Files and Changes does not reach this layout: it uses
`filetree` and `reviewer` in those slots. Add one guard at the top of each
timer callback in the fork-lane and local mods:
`if (window()?.visible === false) return;`. Leave `pager` alone (it must
alert while the window is hidden). Leave `filetree` alone (merge lane; an
edit there costs a merge on every upstream release).

### 4. Open source-file links at the clicked line (carried, API now ready)

`link.line` and `link.column` are new, and they cover ranges (`:5-12`) and
anchors (`#L5`). Folio still parses `link.raw` with its own regex
(`mods/folio/link-target.js:11`) and handles Markdown only.
`bin/open-in-nvim:4` accepts no line.

Two steps: make Folio read `link.line` and `link.column`; then add a handler
for source files that calls `open-in-nvim` with `+<line>`. Check by hand that
`README.md#L5` and `README.md:5-12` still reach Folio: its `mod.json` pattern
allows only `:line[:column]` suffixes.

### 5. Fade unfocused panes

One field on the pane frame in `layouts/buvis.json`: `"veil": 0.3`. Today the
focused pane differs only by a 1 px accent border. Optional with it: add
`"hover": "accent"` to the root `divider` so the sidebar border shows where to
drag. Both are look choices and are reversible.

### 6. Bind agent.select

`my-agents` already publishes its order (`mods/my-agents/main.js:238`), so
`agent.select:N` follows the list on screen. No key runs it. `cmd-1..9`
(tabs) and `ctrl-1..9` (spaces) are taken; `cmd-alt-1..9` is free in
`keys.json`. A small index beside each row in `my-agents` makes it usable.

### 7. Palette entries for local mods

No mod declares `"palette"` in `mod.json`. The Ctrl-Q `m` list in
`mods/prefix/main.js:68` is kept by hand. Add entries to local mods only
(bim-projects, runway, sudoku, the notification log `my-status.log`). Do not
edit gallery mods for this: it marks them "Edited locally" in hmod. Low
value while the launcher and the prefix list exist.

### 8. Markdown colors in tab-notes

`mods/tab-notes/main.js:70` creates the editor with `language: "md"` and no
`syntax` colors. 0.1.18 adds `heading`, `strong`, `emphasis`, `code`, `quote`,
`list` and `link` keys. Pass `theme()` colors. Small.

## Arrives with the app, no work needed

Shift+click extends a selection. Closing a tab keeps `--outlive-parent`
agents. A zoomed tab unzooms at one pane. `herdr-app &` no longer freezes.

## Not needed here

- `font_weight_bold`: MesloLGS has Regular and Bold only.
- `pickFiles`, scroll offsets, window-level drag, back and forward mouse
  buttons, `raw_html(false)`: no mod here has a use for them now. `my-toast`
  already fences message bodies.
- Emoji space avatars: the clones lack the fix; no space here uses an emoji.

## Found outside the scope

- `GALLERY.md` lists keys (`cmd-e`, `cmd-o`, `cmd-shift-u`, ...) that
  `keys.json` no longer binds. They moved under Ctrl-Q on 2026-11-15.
- At 2026-11-24T20:30Z the dotfiles repo showed 42 modified, uncommitted
  tracked files under this folder, from other sessions.

## Delivery sequence

1. my-worktree rebase (safety).
2. AGENTS.local.md.
3. Visibility guards.
4. Folio `link.line`, then source files in Neovim.
5. Veil, `agent.select` keys, palette entries, tab-notes colors, as wanted.

## Outcome (2026-11-24, same day)

The person agreed to items 1 to 5, 7 and 8, declined item 6 (they select
agents by status, not by key), and asked for the `GALLERY.md` key correction.

| Item | Result |
|---|---|
| 1 my-worktree | Done. Shipped 0.1.18 code plus the ring spinner. `mods/my-worktree/remove.test.mjs`: 6 rules, 5 fail on the old code. The dialog was not opened in the live window (it takes the keyboard). |
| 2 AGENTS.local.md | Done. |
| 3 hidden-window polls | Done for ship-it (four folders), reviewer, my-space-folders. `tests/window-hidden.test.mjs`: 15 rules. Not done: runway (another session was editing it). pager and filetree stay as planned. |
| 4 links | Done. Folio reads `link.line`; new mod `beeline` for `file:line`. Not clicked in the live window: a click cannot be sent from a script. |
| 5 veil | Done, `"veil": 0.3`. Checked in Herdr's source (`src/window.rs` at v0.1.18): the veil covers the terminal area only, and uses the same selected pane as `my-pane`'s header fade. Checked by eye in a split tab. |
| 6 agent.select | Declined. |
| 7 palette | Done: 16 entries in `mods/prefix/mod.json`, one in `mods/my-status/mod.json`. |
| 8 tab-notes | Done, and checked by eye in a notes pane. |

Review: one independent correctness review of the diff. No critical or high
finding. Fixed: a PR queue load that was dropped while the window was hidden
left a false empty list (`ship-it-prs/main.js`, with a regression test that
fails without the fix); agent stops were missed while hidden; the line guard
in `beeline` had no upper bound. Rejected with evidence: "emphasis has no
color" (the type file says it inherits the foreground, and the picture shows
it). Found during the fix: a catch-up on each return would call GitHub on
each quick app switch, so it runs only after an absence of 30 s or more.

## Commit scope and open decisions

The dotfiles repo (`buvis/home` on GitHub) is public. The commit takes all
tracked files that changed under this folder, the new files of this work, and
the new source files that tracked mod code imports. It leaves out what would
be published for the first time without a decision:

**Decision 1: the Obsidian PDF bundles.** `mods/obsidian/pdf/convert.mjs`
(533 KB, bundles markdown-it and highlight.js) and `pdf/mermaid.min.js`
(5.5 MB) are untracked. Their sources (`convert.src.mjs`, `package.json`) are
in the commit.

1. **Recommended: keep both out and ignore them.** Add the two paths to
   `.gitignore` and rebuild on a new machine with the commands in the header
   of `convert.src.mjs`. Good: the repo stays small and publishes no
   third-party code, like the file-picker precedent. Bad: PDF export fails on
   a new machine until the rebuild. Ugly: the rebuild step must be written
   down (a line in `GALLERY.md`) or it is forgotten.
2. **Commit both, with their license files.** Good: export works at once on
   each machine. Bad: 6 MB more in a 14.6 MB repo, and public redistribution
   needs the MIT and BSD notices. Ugly: each Mermaid update adds 5 MB to the
   history for good.
3. **Commit `convert.mjs` only; read Mermaid from `pdf/node_modules`.** That
   folder is ignored already. Good: small. Bad: still third-party code in a
   public repo, with notices to add. Ugly: two ways to get one feature.

**Decision 2: the untracked project-management documents of other sessions**
(about 65 files, 5 MB: PRDs, reviews, designs, autopilot reports and two
window screenshots).

1. **Recommended: track the text documents, not screenshots or run logs,
   after the Runway PRD 00005 session closes.** Good: the durable records are
   tracked, as the working-documents rule asks. Bad: internal planning text
   becomes public. Ugly: about 60 files must be screened for private content
   first.
2. **Track all of it.** Good: nothing stays loose. Bad: window screenshots
   can show private terminal text. Ugly: only a force push takes it back.
3. **Move this tree to a private repository.** Good: no publication risk.
   Bad: one more repository, against the 2026-11-13 choice to keep buvis as
   the only tracker. Ugly: the history of this home is split.

`loupe` reports `exec(GH(), [...])` in the ship-it files as shell injection.
These are false positives: Herdr's `exec(program, args[])` starts no shell,
and the lines are not part of this change.
