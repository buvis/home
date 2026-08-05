# Browser playbook

For **judy** always, and for **walter** when a journey runs through a page. You
drive a real browser against a real server. Reading markup is not driving it.

## Is this lane armed?

Armed when the profile establishes both of these:

- a way to serve the app (its own dev/preview command, or a built server), and
- `@playwright/test` resolvable from the target's own `node_modules`.

Anything less is a **loud skip**: report the lane `skipped`, name what is missing
and what therefore went unexercised. A skip is a correct result. A finding
invented to justify the dispatch is not.

## Who owns the server

**Never leave a server running in a background shell.** A headless session kills
background shells shortly after its final result, so a server parked there either
dies mid-lane or outlives the run as an orphan. Two safe shapes, in order:

1. **The project's own Playwright config owns it.** If the config declares a
   `webServer`, `npx playwright test` starts it, waits for the port, and stops it
   on the way out. Nothing else to manage. Prefer this.
2. **One command owns start, probe and teardown.** When there is no `webServer`,
   the same shell invocation that starts the server also kills it, so the process
   cannot outlive the call:

   ```bash
   node build/index.js & SERVER=$!; trap "kill $SERVER" EXIT; \
     <wait for the port>; <run the probe>
   ```

   If your shell refuses an inline `trap`, put the same command in a scratch
   script and run that. The shape is what matters, not where it is typed.

Before you finish, prove nothing is left: `lsof -ti tcp:<port>` must be empty.
Report an orphan you could not kill as a finding against your own lane.

## Writing a probe

You cannot write into the target repo and must not try. Put probe scripts in a
scratch directory outside it (`"${TMPDIR:-/tmp}"/agoge-<lane>/`) and resolve the
browser out of the target's own dependencies, so there is one pinned version and
no second dependency tree:

```js
import { createRequire } from "node:module";
const { chromium } = createRequire(`${target}/package.json`)("@playwright/test");
```

Never `npm install` into the target. If the browser binary is missing, that is a
`skipped` lane with the install command named, not a download you perform.

## Driving doctrine

- Locate by role or `data-testid`, never by CSS class or copy. Both move.
- Locator actions auto-wait and re-query. `waitForTimeout` is not a wait — wait
  for a response, a state, or a condition.
- If you write more than a couple of specs, put the selectors in one object per
  screen and let the specs read as intent.
- Screenshot on failure when it is cheap. Trace when a step is flaky.
- Reproduce anything intermittent twice before reporting it.

## What a browser finding proves

The strongest one pairs two facts: **the system had the information, and the user
was not shown it.** Get both, and quote both.

```
POST /add answered 400 with "A title is required."
the page rendered 0 elements matching /required/i and stayed on /add
```

The response body is the first fact; the DOM count is the second. Either alone is
weak. Together they are a defect no one can argue with.

Watch for, because they only exist in a browser: an error the server returned and
the page swallowed, a state that renders identically for empty and for failed, an
action that appears to succeed, content the page interprets as markup, work the
page does per row instead of once.

## Interactive fallback — not yours

A browser-driving tool attached to a human's own browser is a legitimate surface
in interactive sessions, but **it is not available to this lane and never will
be**. You are pinned to reading and running commands; you hold no browser tool,
so there is nothing here for you to fall back to.

If Playwright is absent, your lane is `skipped`. Name what went unexercised and
stop. Do not reach for a substitute, and do not report a surface as covered
because a human could have driven it.

That fallback belongs to the **master**, in an interactive session only, and its
findings are labelled interactive-run. In an unattended run — autopilot,
headless, no human to answer — nobody selects it, because a run that depends on a
human's open browser cannot be repeated.
