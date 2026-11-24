# Herdr timeout and checker follow-up

Prepared 2026-11-24 in the live Herdr home, dotfiles branch `master`.

## Changes

- Converted 22 notification timeouts across nine files from 2/3/6/8 to
  2000/3000/6000/8000 milliseconds. No command timeout changed.
- Guarded background startup with Herdr's `checking()` API in my-agents,
  my-spaces, my-space-folders, my-status, ship-it, ship-it-prs,
  ship-it-issues and ship-it-review. Initial state and render checks remain.
  Live behavior keeps its timers, command listeners and data probes.
- Added regression coverage for millisecond units and check-mode startup.

## Checker environment

The pending-task warnings came from init starting timers, command listeners
and machine probes during a one-shot check. The guards remove those warnings
without hiding diagnostics. The live app still starts that work normally.

The remaining launchd submission and storage warnings are sandbox denials.
The checker submits a job to the user's GUI launchd domain and stores data at
`~/Library/Application Support/gpui-shell/apps/`. Neither operation is allowed
by the agent sandbox. The selected solution is warrant for native checks,
not a broader sandbox policy or a change to the installed app binary.

For future checks from a sandboxed session, request the specific check through
warrant. The human approves it outside the sandbox. A batch can use a reviewed
shell script, as the prepared closeout request does. Source:
[Herdr v0.1.17 checker startup](https://github.com/herdrdev/herdr-app/blob/v0.1.17/src/macos_check.rs).

## Verification before warrant

- Timeout regression baseline: nine tests failed before production edits.
  A syntax typo in the first test draft was fixed before that baseline.
- Check-mode baseline: four tests failed on background startup.
- Final combined suite: 49 passed, zero failed or skipped.
- All 12 affected native mod checks passed in the sandbox. None emitted
  pending-task or real-process warnings after the guards. Launchd/storage
  denials remained, so warning-free checks are a gate in the warrant script.
- Source review confirmed all 22 changed values belong to notifications.
  A subsequent scan found no remaining single-digit literal timeouts in mods.
- The commit preparation excludes unrelated existing edits, including the
  folder loading spinner and unrelated menu, review, worktree and documentation
  changes. It includes the earlier agent-status, saved-state, long-toast and
  notification-history work, its tests, and review records.

## Completion gate

The prepared warrant action checks an exact staged-content snapshot, rejects
warnings, checks that HEAD and the user's index have not changed, stages only
the reviewed patch, verifies its blobs, and makes a local conventional commit.
It does not push. If any check fails, it stops before the commit.

At preparation time the warrant run and commit are pending. Its output is the
completion evidence; a submitted request alone does not mean the commit exists.
