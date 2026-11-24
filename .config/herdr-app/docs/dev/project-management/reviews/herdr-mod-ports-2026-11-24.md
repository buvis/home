# Herdr custom mod fixes

Implemented 2026-11-24 in the live `~/.config/herdr-app` home, dotfiles branch
`master`. Scope: agent status, saved-state recovery, and long notifications.

## Changes

- `my-agents`: kept child agents retain Done; a finished child does not move a
  working parent into Done. Blocked children still raise parent urgency.
- `my-agents`, `my-tabs`, `my-space-folders`, `my-spaces`: malformed JSON and
  wrong root types recover to empty saved state. Valid choices remain.
  The older `my-spaces` clone had the same defect and is included.
- `my-toast`: full notification text wraps and scrolls inside the custom
  card. Error/warning logging, source navigation, attention actions, and login
  copying remain. Automatic-height rendering is supported when requested.
- Tests: `tests/mod-ports.test.mjs`, using Node's test runner and the repository's
  existing module-hook testing pattern. No external test package is needed.

These are selective ports. Clone version labels are deliberately unchanged.
The existing spinner edit in my-space-folders was present before this task
and was preserved. Other concurrent edits were not changed.

## Native toast limitation

Herdr 0.1.17 only enables automatic toast height when the mod name is `toast`.
See upstream `src/window.rs:3984` at tag v0.1.17. The custom mod receives a
fixed 72px card and no `fitHeight` flag. Copying only the shipped JavaScript
would therefore retain the truncation bug. The custom card now scrolls all
message text, using the native scroll area, without changing the app binary
or replacing the user's error-log routing.

## Verification

- Before production edits: 27 tests, 5 passed, 22 failed. A test-helper naming
  collision was corrected before this baseline. Failures covered invalid
  storage, kept-child status, and toast text/layout.
- A second fail-first case caught the native custom-card height limitation
  before the scrolling fallback was added.
- Final tests: **27 passed, 0 failed, 0 skipped**.
- `herdr-app check`: all five changed mods passed. The final toast version was
  checked again after adding the fixed-height scrolling behavior.
- Native screenshots inspected: `docs/dev/tmp/mod-ports-live.png` and
  `docs/dev/tmp/mod-ports-native.png`. The live sidebar/tabs render. A temporary
  fixture used a byte-for-byte copy of the agent mod to display kept Done,
  unkept Idle, and blocked rows, and posted a real multiline notification.
- The fixture initially failed because cross-mod imports are forbidden. It
  passed after copying the source into the fixture's own folder. Its overlay,
  notification, source, and generated files were removed after the check.
- Malformed storage and click handlers were tested in memory. No live saved
  state was corrupted. The native toast was visually inspected; mouse-wheel
  scrolling was not automated on the user's display.
- At 2026-11-24T06:00:52Z, runtime status reported no errors and only the
  pre-existing recall overlay. The targeted Git whitespace check passed.

## Review and known limits

Self-review checked parent/child ranking, valid-state preservation, toast
actions and logging, same-pattern storage loading, and the native toast host.
The local hold-in-Done behavior and branch labels remain. No shared helper or
new dependency was introduced. Array validation for folded machines also
rejects strings, which JavaScript Set would otherwise accept as characters.

Checks printed environment warnings: launchd checker submission failed and
fell back to the caller process; sandbox policy denied gpui-shell storage
creation for several check instances; shutdown reported pending async/timer
tasks. The space mods also warned that their read-only machine/folder probes
run during checks. These warnings did not make the checks fail. Address the
checker environment separately if clean check logs are required.

No commit was made. The session already established that writes to the bare
dotfiles index require warrant. A future scoped commit must exclude the
pre-existing spinner edit and other concurrent changes.
