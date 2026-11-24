# Herdr notification review

Reviewed and changed on 2026-11-24 in `~/.config/herdr-app`, dotfiles branch
`master`. This follows the custom-mod ports from the same day.

## Result

The buvis layout already routes notifications through `my-toast`. Its history
now records every notification it receives, including info, success and agent
attention. It retains the latest 50 routine notices and every error/warning
until Clear. Existing entries keep their source, timestamp, text and action.
The status bar shows Notifications, red for errors, amber for warnings, muted
otherwise. Open it there or with `herdr-app do my-status.log`.

Ordinary errors and warnings still enter the history without a popup. Agent
attention still appears as a toast and now also enters the history. This
applies to layouts using `my-toast`, not notifications from other applications
or layouts that select another toast mod. Earlier info/success messages cannot
be recovered retrospectively. Check-mode loads do not write synthetic entries.

## Persistence

Herdr 0.1.17 gives every native toast an expiry. The timeout is milliseconds;
zero expires immediately. Defaults are 8 seconds for errors/warnings and
5 seconds otherwise. Evidence: [upstream window.rs, v0.1.17](https://raw.githubusercontent.com/herdrdev/herdr-app/v0.1.17/src/window.rs),
lines 4005 and 4036. There is no supported indefinite native toast setting.

Options considered:

- **Recommended and implemented: retain problems in the history.** It uses
  existing controls and keeps problems until Clear. It does not keep an error
  card on screen. The list requires explicit clearing and can grow indefinitely.
- **Custom persistent panel or window.** It could keep errors visible with
  individual dismiss controls. It takes screen space and needs another view.
  Its lifetime and dismissal state would become our responsibility.
- **Add indefinite native toasts upstream.** This would preserve the normal
  toast presentation. It requires an app change beyond these mods. Keeping a
  private app build would add release maintenance until upstream accepts it.

## Replacement audit

| Existing mechanism | Disposition |
| --- | --- |
| Ship-it one-off banner | Already replaced by notify on November 16; no second banner to remove |
| Runway and PR/issue/review action results | Already use notify; the new history captures them |
| Folio load/diagram errors | Keep inline: they explain the current file or diagram |
| PR/issue panel loading errors | Keep inline: they explain the current panel's unavailable data |
| Reviewer send dialog and cleanup confirmations | Keep: they collect input or authorize an action |
| Pager desktop/phone delivery | Keep: reaches the user away from Herdr; local toasts cannot replace it |
| Pager delivery failure and retry control | Keep: includes a recovery action tied to delivery state |
| Ciupaga task status and tab notes | Keep: ongoing state and durable notes, not notification messages |

No remaining duplicate notification system justified removal in this review.

## Timeout units (corrected in the follow-up)

The audit found pre-existing 2, 3, 6 and 8 millisecond timeouts that appear
intended as seconds. These can disappear before the user can read them.
The follow-up corrected all 22 values to 2000, 3000, 6000 or 8000, with
regression coverage in `tests/toast-timeouts.test.mjs`:

- `my-menu/main.js:123` and `on-screen/main.js:316` (copied text).
- `ship-it/data.js`, `ship-it-prs/data.js`, `ship-it-issues/data.js` and
  `ship-it-review/data.js`, lines 31 and 50 (agent request and push progress).
- `ship-it-prs/main.js:112,154,178,222` (errors and copied links).
- `ship-it-issues/main.js:117,119,154` (worktree results and copied link).
- `ship-it-review/main.js:335,419,613,669,707` (comments, reruns and copying).

Other mods already use milliseconds correctly. Non-notification timers remain
unchanged. See `herdr-checker-closeout-2026-11-24.md` for follow-up verification.

## Verification and review

- New coverage failed against the old code: eight failures.
- `node --test tests/mod-ports.test.mjs`: 36 passed, zero failed or skipped.
- `herdr-app check mods/my-toast` and `mods/my-status`: passed.
- Native history and actual info/success toasts inspected in
  `docs/dev/tmp/notification-history.png`. All five levels, retention, source
  capture, check-mode isolation and badge colors have automated coverage.
- Temporary verification mod, overlays and test history entries were removed.
  A subsequent read found zero verification entries. Runtime status had no
  errors when inspected after the native check.
- Self-review checked retention across mixed severity, preserved actions,
  existing warning routing, and whether other messaging served a distinct role.
- Check commands still emit environment warnings about launchd fallback,
  sandbox storage and pending async work. Checks pass, but the environment
  warnings remain a separate maintenance item.
- No native pointer automation was used. Clear and action handlers were not
  clicked in the user's live window.

Changes remain local and uncommitted. The bare dotfiles index requires warrant
in this session. Any later scoped commit must exclude concurrent edits.
