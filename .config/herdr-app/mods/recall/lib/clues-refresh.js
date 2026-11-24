// Clues' data refresh, apart from the view so node tests can drive it with
// fake `exec` and `hc`. Two rounds: the pane-state round (`hc get` per
// terminal, plus `ps` and `lsof`) every 10 s, and the buffer round (`hc read`,
// new panes only) every 30 s. The view keeps its 1 s timer and calls
// `run(now)`, which starts whichever round is due. A round still running is
// not started again, until it has run ROUND_LIMIT: `hc` has no timeout, so
// a round whose call never settles must not block the next for good. The
// results a superseded round brings back late are dropped.
import { cleanBuffer, parseLsof, parsePs, parseSshTarget } from "./clue-extract.js";

export const PANE_STATE_EVERY = 10000;
export const CONTENT_EVERY = 30000;
// Each program Clues runs through `exec` gets this long (Herdr's default is 30 s).
export const PROGRAM_TIMEOUT = 5000;
// A round running this long no longer blocks the next one.
export const ROUND_LIMIT = 30000;

/**
 * `exec(cmd, args)` and `hc(args)` are Herdr's; `terminalPanes()` lists the panes
 * that have a terminal (each `{ pane, terminal, cwd }`).
 * `data` is the one object listView reads; its fields are filled in place.
 */
export function createCluesRefresh({ exec, hc, terminalPanes }) {
  const data = { paneState: new Map(), content: new Map(), procs: null, listeners: null };
  // Each round has a token, the number of rounds of its kind started so far;
  // only the latest round's results are kept. `startedAt` is when it began, and
  // `running` that it hasn't settled. The two rounds are guarded apart.
  const rounds = {
    paneState: { token: 0, startedAt: 0, running: false, every: PANE_STATE_EVERY },
    content: { token: 0, startedAt: 0, running: false, every: CONTENT_EVERY },
  };
  // The lsof that has answered (exited, whatever its code), once one has.
  let lsofBin = null;

  function due(kind, now) {
    const r = rounds[kind];
    if (r.running && now - r.startedAt < ROUND_LIMIT) return false;
    return !r.startedAt || now - r.startedAt >= r.every;
  }

  async function fetchPaneState(live) {
    await Promise.all(terminalPanes().map(async (p) => {
      try {
        const r = await hc(["get", p.terminal, "--json"]);
        if (r.code !== 0 || !live()) return;
        const j = JSON.parse(r.stdout);
        const fg = j.foreground;
        const command = fg?.argv?.length ? fg.argv.join(" ") : fg?.name ?? null;
        data.paneState.set(p.pane, {
          cwd: fg?.cwd ?? j.cwd ?? p.cwd ?? null,
          command: command && command.trim() ? command : null,
          ssh: command ? parseSshTarget(command) : null,
          shellPid: j.pid ?? null,
        });
      } catch {}
    }));
  }

  // The process table is replaced whenever `ps` answers, the listener list
  // whenever `lsof` answers, each apart from the other. A failure (a rejection,
  // or an exit code that is not an answer) keeps that one's last good value, and
  // with none yet it is empty.
  async function fetchLocator(live) {
    const [ps, lsof] = await Promise.all([askPs(), askLsof()]);
    if (!live()) return;
    data.procs = ps ?? data.procs ?? new Map();
    data.listeners = lsof ?? data.listeners ?? [];
  }

  async function askPs() {
    try {
      const r = await exec("ps", ["-eo", "pid=,ppid=,command="], { timeout: PROGRAM_TIMEOUT });
      return r.code === 0 ? parsePs(r.stdout) : null;
    } catch {
      return null;
    }
  }

  // `/usr/sbin/lsof` is for a machine where `lsof` isn't on the PATH. Both are
  // tried until an lsof has answered in this dialog, then only that one. Herdr's
  // error doesn't tell a timeout from a program that can't start, so an lsof
  // that only ever times out is still followed by the other each round.
  async function askLsof() {
    for (const bin of lsofBin ? [lsofBin] : ["lsof", "/usr/sbin/lsof"]) {
      try {
        const r = await exec(bin, ["-nP", "-iTCP", "-sTCP:LISTEN", "-F", "pn"], { timeout: PROGRAM_TIMEOUT });
        lsofBin = bin;
        return r.code === 0 || r.code === 1 ? parseLsof(r.stdout) : null;
      } catch {}
    }
    return null;
  }

  async function fetchContent(live) {
    const missing = terminalPanes().filter((p) => !data.content.has(p.pane));
    await Promise.all(missing.map(async (p) => {
      try {
        const r = await hc(["read", p.terminal, "--lines", "3000"]);
        const text = r.code === 0 ? cleanBuffer(r.stdout) : null;
        if (text && live()) data.content.set(p.pane, text);
      } catch {}
    }));
  }

  /** Starts a round of `kind`; `work(live)` fills the data while `live()` holds. */
  function start(kind, now, work, onRound) {
    const r = rounds[kind];
    const token = ++r.token;
    r.startedAt = now;
    r.running = true;
    const live = () => r.token === token;
    return work(live).finally(() => { if (live()) r.running = false; }).then(() => { if (live()) onRound(); });
  }

  /** Whether `run(now)` would start a round, so a tick with nothing due can skip it. */
  function isDue(now) {
    return due("paneState", now) || due("content", now);
  }

  /**
   * Start each round that is due at `now` (ms). `onRound` is called as each round
   * settles (the view redraws then). Resolves when the rounds it started are done.
   */
  function run(now, onRound = () => {}) {
    const started = [];
    if (due("paneState", now)) {
      started.push(start("paneState", now, (live) => Promise.all([fetchPaneState(live), fetchLocator(live)]), onRound));
    }
    if (due("content", now)) started.push(start("content", now, fetchContent, onRound));
    return Promise.all(started).then(() => {});
  }

  return { data, run, due: isDue };
}
