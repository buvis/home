// Tells the person when a newer Walkthrough is out. At most once a day, while the
// dialog is open, one GET to GitHub's public releases API: no token, nothing
// about the person, their repositories or their code. "Stop checking" turns it
// off for good; CHECK = false turns it off before it ever asks.
//
// An installed copy can't update itself (Herdr updates its own mods, not the
// ones a person added), so the dialog offers the prompt that has their agent
// do it. Nothing here imports `herdr`: the dialog hands in what it needs, so
// the tests can run it under node.

/** The installed version: the same as mod.json and package.json (test/version.test.js). */
export const VERSION = "0.10.0";
const CHECK = true;
export const REPO = "dmazlum/herdr-walkthrough";
export const RELEASES = `https://github.com/${REPO}/releases`;
export const PROMPT = `Update the Walkthrough mod from github.com/${REPO} to its latest release`;
const KEY = "walkthrough.update";
const DAY = 24 * 60 * 60 * 1000;
const RETRY = 60 * 60 * 1000;
// A request that neither answers nor fails would otherwise hold the check for a day
// (its time is saved before asking): past this it counts as failed, tried again in an hour.
const TIMEOUT = 15 * 1000;

/**
 * Resolves after `ms`. Herdr's script runtime may have no `setTimeout`: the dialog hands
 * in its own timer (`cx.timer.after`); without either, the time limit simply doesn't apply.
 */
const defaultWait = (ms) => (typeof setTimeout === "function" ? new Promise((r) => setTimeout(r, ms)) : new Promise(() => {}));

/** a > b, for versions like v1.2.3 or 1.2.3. */
export function newer(a, b) {
  const parts = (v) => String(v).replace(/^v/, "").split(".").map((n) => parseInt(n, 10) || 0);
  const [x, y] = [parts(a), parts(b)];
  for (let i = 0; i < 3; i++) if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) > (y[i] ?? 0);
  return false;
}

/**
 * The check, kept in Herdr's shared state so it lasts across restarts and every
 * open copy of the dialog sees it. A result saved for another repository (a
 * fork, a test) counts as never checked; "Stop checking" holds for all of them.
 */
export function updater({ shared, setShared, fetch, now = () => Date.now(), check = CHECK, version = VERSION, timeout = TIMEOUT, wait = defaultWait }) {
  const state = () => {
    const s = shared(KEY) ?? {};
    return s.repo === REPO ? s : { off: s.off };
  };
  const save = (change) => setShared(KEY, { ...state(), ...change, repo: REPO });

  return {
    /** The release to offer, { tag, url }, or null. */
    available() {
      const s = state();
      if (!check || s.off || !s.latest || !newer(s.latest.tag, version) || s.dismissed === s.latest.tag) return null;
      return s.latest;
    },

    /**
     * Asks GitHub, unless it was asked in the last day (an hour, after a failed
     * try). A time in the future (a clock that was wrong) counts as long ago.
     * Never throws.
     */
    async check() {
      const s = state();
      const since = now() - (s.checked ?? 0);
      if (!check || s.off || (since >= 0 && since < DAY)) return;
      // A failed try is saved as if it were a day old less an hour: asked again in an hour.
      const retry = () => save({ checked: now() - DAY + RETRY });
      try {
        // Nothing is saved before asking: Herdr may make a view and drop it at once, and a
        // request cut short with it (or by closing the dialog) must not count as asked.
        // Two copies open together may both ask; that is one more GET, once a day.
        const late = wait(timeout).then(() => { throw new Error("timed out"); });
        late.catch(() => {});
        const r = await Promise.race([fetch(`https://api.github.com/repos/${REPO}/releases/latest`, {
          headers: { Accept: "application/vnd.github+json", "User-Agent": "herdr-walkthrough" },
        }), late]);
        if (!r.ok) return retry();
        const j = await r.json();
        if (typeof j?.tag_name !== "string" || !/^v?\d+\.\d+\.\d+$/.test(j.tag_name)) return save({ checked: now() });
        // Only a page of this repository's is opened from the dialog.
        const url = String(j.html_url ?? "");
        save({ checked: now(), latest: { tag: j.tag_name, url: url.startsWith(`https://github.com/${REPO}/`) ? url : RELEASES } });
      } catch {
        // Offline, a network not up yet after a wake: try again in an hour.
        try { retry(); } catch { /* shared state gone: nothing to keep */ }
      }
    },

    /** "Later": quiet until the next release. */
    dismiss(tag) { save({ dismissed: tag }); },

    /** "Stop checking": for good, for every copy of the dialog. */
    stop() { save({ off: true }); },
  };
}
