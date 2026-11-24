# Notification controls and command-exit feasibility

Reviewed 2026-11-24. Scope: custom `my-toast`, `my-status`, their icons and regression tests.

## Follow-up checklist

- Individual dismissal removes one notification and keeps history open. New arrivals are preserved.
- The status bar replaces its Notifications label with distinct error, warning, success and info icons and counts. Empty groups disappear.
- History actions use icons with tooltips and accessible labels.
- A missing source terminal uses a dimmed, crossed-out terminal icon. It is disabled, has no click handler, and explains its state in a tooltip and accessible label.
- New entries capture space, tab and pane names. Older entries use their live pane name when available; a closed historical pane's missing name cannot be recovered.
- Today shows time only, yesterday shows Yesterday plus time, and older messages show date plus time. Local calendar boundaries handle year changes and daylight saving time.
- Every time uses 24-hour HH:mm:ss, including tooltips and copied text. Copy retains the full date.
- Dismiss info and success removes those two severities, including new arrivals, while preserving all errors and warnings. The separate trash action still clears everything.
- Command-exit logging was investigated only. No shell hook, watcher or exit-code notification was implemented.

Earlier upstream ports, all-severity history, timeout corrections and checker startup fixes were committed as `59034a3f`. That approved warrant ran 49 tests and 24 warning-free native checks. This follow-up preserves the existing policy: ordinary errors and warnings remain in history until explicitly dismissed, while routine history keeps its latest 50 entries.

## Verification and review

- `TZ=Europe/Prague node --test tests/mod-ports.test.mjs tests/toast-timeouts.test.mjs`: 58 passed, zero failed or skipped. The missing-terminal regression test failed against the previous text-only state before the icon fix.
- Regression failures were observed before the fixes for dismissal/counts, dates/pane labels and 24-hour formatting.
- Both changed mods pass `herdr-app check`. Inside the agent environment, the checker reports its launchd fallback warning. The prepared warrant repeats snapshot and live checks outside that environment and refuses to commit if diagnostics remain.
- Native screenshots inspected: severity counts, dated history, pane paths, icon actions, explicit 24-hour times and the disabled crossed-out terminal icon. Evidence is local under `docs/dev/tmp/notification-controls-24h.png`, `notification-severity-counts.png` and `notification-terminal-off.png`.
- Temporary preview entries and overlays were removed. User entries were preserved.
- Self-review checked concurrent arrivals, duplicate entries, empty history, retained problems, legacy records, captured names after renaming, calendar boundaries and all action labels. No supported in-scope defect remains.

## Nonzero command exits: feasible, with shell integration

Installed versions inspected: Herdr app 0.1.17 and core 0.1.22. Core records `exit_code` when the terminal's root process ends. This does not report each command executed inside a persistent shell. The mod API and core event stream expose terminal facts, not a command-completion result for each shell command. Sources: [core terminal registry](https://github.com/herdrdev/herdr-core/blob/v0.1.22/crates/herdr-core/src/terminals.rs), [core event stream](https://github.com/herdrdev/herdr-core/blob/v0.1.22/crates/herdr-core/src/events.rs), installed `herdr.d.ts`, `hc get` and `hc events --help`.

Three approaches exist:

1. **Recommended: interactive shell hook plus explicit user-shell origin.** Capture the final command status before existing prompt code changes it, then send a structured event to history. This covers ordinary commands but requires shell-specific integration and an explicit origin marker; the current Bash history and revive prompt hooks must remain intact.
2. **Terminal process exit watcher.** Core already provides final process status, so this needs less integration. It misses failed commands in an open shell and must avoid duplicating Herdr's existing early launch-failure notification.
3. **Core command-completion integration.** A core event for shell command completion would give mods a common interface. It requires upstream work and shell integration, and still needs origin tracking to exclude agent activity.

Agent exclusion cannot use `parent == null` alone because directly launched agents can also have no parent. Core's `reported` field means a terminal has ever reported agent status; using that permanently would exclude a user shell after an agent returns. Use explicitly marked user shells, reject agent descendants and unknown origins, and preserve provenance across program transitions. Process facts cannot distinguish a human command from an agent command typed into the same shell without additional provenance.

Bash runs `PROMPT_COMMAND` before displaying its primary prompt ([Bash manual](https://www.gnu.org/software/bash/manual/html_node/Bash-Variables.html)). The current `.bashrc` starts it with `history -a`, so a future hook must capture `$?` first. Terminal text parsing or foreground-process polling cannot recover reliable command exit status. A future implementation should define handling of pipelines and interrupted commands before coding; no such policy was added here.

## Remaining gate

The follow-up UI is live. Its scoped commit and warning-free native checks must run through warrant, as required by the environment policy. The frozen bundle contains only the files listed in its blob manifest; it rejects a changed HEAD or a nonempty index and performs no push.
