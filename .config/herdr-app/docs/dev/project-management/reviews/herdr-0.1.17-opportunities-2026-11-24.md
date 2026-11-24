# Herdr 0.1.17 environment opportunities

Reviewed 2026-11-24. Scope: compare the installed update with the personal
`buvis` layout and its mods. This is an assessment, not an implementation.

The best order is to recover missed fixes in personal clones, then add direct
file clicks and keyboard pane controls. Keep the current layout and workflows.

## Evidence and limits

- CLI and app bundle both report 0.1.17. The release is dated November 22,
  although this review follows the user's November 24 update.
- At 2026-11-24T05:46:09Z, `herdr-app status` reported layout `buvis` and
  `errors: []`. This does not prove every deferred mod action works.
- Read the installed guide, generated types, commands, current settings and
  keys, personal mod sources, and shipped counterparts. Compared worktree and
  agent clones directly with their shipped versions.
- No live configuration, terminals or worktrees changed. No runtime mod checks
  or interaction tests ran. Some checks execute real side effects, including
  notification delivery in pager; they are unsuitable for a passive audit.
- Source: [official 0.1.17 changelog](https://raw.githubusercontent.com/herdrdev/herdr-app/v0.1.17/CHANGELOG.md).
  Local release notes: `update-notes-cache.md`.

## Ranked opportunities

### 1. Recover worktree removal safety first

`mods/my-worktree/main.js:209` still closes the space before Git removes the
worktree. A refused removal can therefore end terminals even though the
checkout stays. The clone also lacks the shipped lock check and action-level
main-checkout guard. The new-menu and custom context menu still call this clone.

Port the safeguards from `mods/worktree/main.js:192` and `:231`. Keep the local
spinner. The shipped settings reader can replace the hardcoded worktree root:
`settings.json` already specifies `~/git/src/worktrees`. The current diff also
includes longer Git timeouts, better dialog focus, and explicit local-machine
targeting. Review these together rather than copying the entire mod blindly.

Close this item with regression tests for locked/main checkouts and failed Git
removal, proving no premature space close, plus an isolated UI check.

### 2. Open the exact clicked file

The `buvis` layout has no `link_handlers`. `mods/on-screen/paths.js` scans the
terminal screen and strips line suffixes. It cannot identify the clicked word.
Folio already supplies Markdown preview and a Neovim edit-and-return workflow.

Add a small handler for recognized local Markdown links that opens Folio using
the clicked source pane. Extend to source files with line/column navigation in
Neovim after that works. Reuse an existing editor only when its server can be
identified reliably. Keep on-screen for its keyboard picker and command actions.

The new API provides source terminal, machine, cwd and pane. File paths may be
null, and bare filenames are skipped by native detection. Return `pass` for
unsupported targets; never treat remote paths as local ones. Verify spaces in
paths, diagnostic suffixes, missing files, and clicks from an unfocused pane.

### 3. Add keyboard resize and visible pane names

Neither `keys.json` nor `mods/prefix/main.js` binds `pane.resize`. Add resize to
the existing Ctrl-Q menu, for example Shift-H/J/K/L. This follows the current
keyboard scheme without taking another shell control key.

Both `my-menu` and `on-screen` lack pane Rename. `mods/my-pane/main.js:55`
does not read `p.name`, whereas the shipped header does. Add Rename to both
menus and prefer `p.name` in the header. Verify resize direction, focus, saved
names, and both context-menu entry points.

### 4. Port agent and notification fixes selectively

- `my-agents` maps every child's `done` status to idle, including children kept
  as panes. Shipped `agents` preserves their displayed status. Port that logic
  and its parent-ranking rule together, keeping the local branch labels and
  the deliberate hold-in-Done behavior.
- `my-agents`, `my-tabs` and `my-space-folders` parse saved startup state without
  equivalent validation. Add the relevant saved-state safeguards from shipped
  mods, with malformed-state regression cases. This includes older missed fixes.
- `my-toast` still truncates ordinary toasts and lacks the shipped `fitHeight`
  handling. Port that support while preserving the existing full error log.
- `my-status` still prints `1 agents`; use singular for one. Low priority.

Close these items with focused tests, passing mod checks, and live checks of
the changed states. An empty runtime error list alone is insufficient.

### 5. Make the improvements survive future updates

GALLERY.md already points to gems backlog PRDs 00156 (clone audit) and 00160
(reviewed clone ports). Use those existing plans rather than another updater.
The audit should surface stale personal clones after app updates; the port
workflow should preserve local changes and require evidence for each candidate.

These PRDs remained in the gems backlog when inspected. They are roadmap
evidence, not proof that an installed command exists. Connect this report to
their implementation as a concrete set of acceptance examples.

## Secondary items from earlier releases

- Add a Dock count of blocked agents and a window title with space/tab through
  one persistent mod. `my-status` already computes the blocked count; neither
  it nor pager calls `setBadge` or `setWindowTitle`. This complements pager.
- Add `checking()` guards to pager before any alert delivery. Its render path
  calls `observe`, which can launch the sender even during a mod check.
- Cancel obsolete watches in `my-space-folders`. Its watcher awaits
  `watchFolder(repo)` without retaining the cancellable promise, so removing a
  repository from the active set cannot immediately release that pending call.
- Filetree preview uses a fixed 12px font. Reviewer already scales from the
  terminal font minus one. Consider unifying this only if the mismatch bothers
  the user; the shipped preview change does not update these replacements.

## Already present or not needed

Cmd+A, Cmd+F, Cmd+M, copy-on-select off, and the preferred worktree directory
are configured. Copy mode is already reachable through Ctrl-Q, m, x. Keep
these; do not add duplicate controls. Engine-level crash and responsiveness
fixes arrive with the app and need no personal-mod port.

## Delivery sequence

1. Port worktree safety and guard notification side effects during checks.
2. Port agent state, saved-state, and toast fixes with regression coverage.
3. Add resize and rename controls.
4. Add direct Markdown clicks, then source-file navigation.
5. Use the existing gems clone-audit and port PRDs for recurring maintenance.

All implementation items remain proposals. The requested assessment is complete.

## Report tracking

The report is saved locally but untracked. On 2026-11-24, both normal and
escalated staging attempts failed to create `/Users/bob/.buvis/index.lock`
with `Operation not permitted`. No commit or push occurred. Track this report
through the established warrant workflow when recording the implementation.
