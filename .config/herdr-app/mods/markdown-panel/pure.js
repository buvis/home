// Kanso, by jlopezlira (https://github.com/jlopezlira/herdr-kanso). Apache-2.0.
// This is the source copy; `npm run sync:share` copies it into every mod.

export const range = (n, from = 0) => Array.from({ length: Math.max(0, n) }, (_, i) => from + i);

export const extOf = (path) => (/\.([^./\\]+)$/.exec(String(path)) ?? [])[1]?.toLowerCase() ?? "";

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)/;
const STEPS = { "-": { old: 1, next: 0, from: "old" }, "+": { old: 0, next: 1, from: "next" }, " ": { old: 1, next: 1, from: "next" } };
// A diff numbers its lines from its hunk headers: a deleted line by the old file, the others by the new one.
// The kit's code piece numbers its diffs with it, in the app and in the Storybook.
export const diffNumbers = (lines, first) => lines.reduce(({ at, numbers }, source) => {
  const head = HUNK.exec(source);
  if (head) return { at: { old: Number(head[1]), next: Number(head[2]) }, numbers: [...numbers, undefined] };
  const step = STEPS[source[0]];
  if (!step) return { at, numbers: [...numbers, undefined] };
  return { at: { old: at.old + step.old, next: at.next + step.next }, numbers: [...numbers, at[step.from]] };
}, { at: { old: first, next: first }, numbers: [] }).numbers;

// A Markdown source's blocks, as both kits draw them: runs of lines between empty lines, a fenced block kept whole.
const FENCED = /^\s{0,3}(?:`{3,}|~{3,})/;
export const markdownBlocks = (source) => String(source).trim().split("\n").reduce(({ blocks, fenced }, line) => {
  const fence = FENCED.test(line) ? !fenced : fenced;
  if (!fenced && !line.trim()) return { blocks: blocks.at(-1)?.length ? [...blocks, []] : blocks, fenced };
  return { blocks: [...blocks.slice(0, -1), [...(blocks.at(-1) ?? []), line]], fenced: fence };
}, { blocks: [[]], fenced: false }).blocks.filter((lines) => lines.length).map((lines) => lines.join("\n"));

export const tryOr = (fn, fallback = null) => {
  try { return fn(); } catch { return fallback; }
};
export const tryOrAsync = async (fn, fallback = null) => {
  try { return await fn(); } catch { return fallback; }
};

export const same = (a, b) => String(a ?? "").toLowerCase() === String(b ?? "").toLowerCase();
export const parseOr = (text, fallback = null) => tryOr(() => JSON.parse(text), fallback);

export const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

export const DID_CAP = 200;

export function oneLine(text) {
  const line = String(text ?? "").split(/\r?\n/).find((l) => l.trim()) ?? "";
  const flat = line.replace(/\s+/g, " ").trim();
  return flat.length > DID_CAP ? `${flat.slice(0, DID_CAP - 1)}\u2026` : flat || null;
}

export function memoryFree(pct) {
  return `Memory ${Math.round(Number(pct))}% free`;
}

// A panel's first command waits one timer turn: Herdr can lose one started in a remounted view's init turn.
export const afterMount = (cx, start) => cx.timer.after(0, start);

// The mod's command reader: each command goes to `act` until the build is replaced (hot reload,
// update) and nextCommand throws, or `act` answers false. `closed` stops a start that lands after
// the view's close(); `keep` takes the task, so a close() still in time can cancel it.
export function readCommands(cx, next, act, { closed = () => false, keep = () => {} } = {}) {
  return afterMount(cx, (outer) => {
    if (closed()) return;
    keep(outer.spawn(async (loopCx) => {
      for (;;) {
        const got = await tryOrAsync(async () => ({ command: await next() }));
        // A replaced build stops here, before acting.
        if (!got) return;
        loopCx.notify();
        if ((await act(got.command, loopCx)) === false) return;
      }
    }));
  });
}

// A dialog takes the keys the moment it opens: one handle, focused.
export function focusOn(cx) {
  const handle = cx.focus_handle();
  handle.focus();
  return handle;
}

// A layout node by its id, anywhere in the tree.
export function nodeById(node, id) {
  if (node?.id === id) return node;
  for (const kid of node?.children ?? []) {
    const below = nodeById(kid, id);
    if (below) return below;
  }
  return null;
}

// Herdr can leave a promise unsettled. The timer resolves this instead, so the caller moves on.
export const LATE = Object.freeze({ late: true, code: 1, stdout: "", stderr: "timed out" });

export function bounded(promise, timer, ms = 30_000) {
  if (!timer?.after) return promise;
  const deadline = new Promise((resolve) => { timer.after(ms, () => resolve(LATE)); });
  return Promise.race([promise, deadline]);
}

export const settled = async (work) => {
  try { return { ok: true, value: await work() }; } catch (error) { return { ok: false, error }; }
};

export async function onceMore(work, timer, ms, drop = () => false, abandon = () => {}) {
  const step = async () => {
    const result = await (ms == null ? settled(work) : bounded(settled(work), timer, ms));
    return result?.late || result?.error?.late ? { ok: false, late: true, error: result.error ?? new Error("did not answer") } : result;
  };
  const first = await step();
  if (drop() || !first.late) return first;
  abandon();
  return step();
}

export async function retry(times, fn, { done = Boolean, between = async () => {} } = {}, k = 0) {
  const v = await fn(k);
  if (done(v) || k + 1 >= times) return v;
  await between(k);
  return retry(times, fn, { done, between }, k + 1);
}

export async function findAsync(list, test, i = 0) {
  if (i >= list.length) return null;
  return (await test(list[i], i)) ? list[i] : findAsync(list, test, i + 1);
}

// Halves joined once each, so no list is copied per item and depth stays log n.
export async function mapSeries(list, fn, from = 0, to = list.length) {
  if (to - from <= 0) return [];
  if (to - from === 1) return [await fn(list[from], from)];
  const mid = from + Math.floor((to - from) / 2);
  const left = await mapSeries(list, fn, from, mid);
  return left.concat(await mapSeries(list, fn, mid, to));
}

export async function reduceSeries(list, fn, acc, i = 0) {
  return i >= list.length ? acc : reduceSeries(list, fn, await fn(acc, list[i], i), i + 1);
}

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const pad2 = (n) => String(n).padStart(2, "0");
const DAY = 86_400_000;

// The meter panels' three ranges: a day of minute samples, a week and a month of hourly ones.
export const RANGES = [["day", "24 h", 1, 96], ["week", "7 days", 7, 84], ["month", "30 days", 30, 90]]
  .map(([key, label, days, buckets]) => ({ key, label, ms: days * DAY, buckets }));

// A finite number, or null: the one read of a measured value.
export const num = (v) => (Number.isFinite(v) ? v : null);

// A size in MB a person reads: whole MB under a GB, then GB, one decimal under 10.
export function sizeMB(mb) {
  const n = num(mb);
  if (n === null) return "–";
  if (n >= 1000) {
    const gb = n / 1024;
    const word = gb < 10 ? gb.toFixed(1).replace(/\.0$/, "") : Math.round(gb);
    return `${word} GB`;
  }
  return `${Math.max(0, Math.round(n))} MB`;
}

// A day's own words: "Nov 16".
export const dayWord = (d) => `${MONTHS[d.getMonth()]} ${d.getDate()}`;

export function clock(ms, now = Date.now()) {
  const d = new Date(ms);
  if (Number.isNaN(+d)) return "";
  const time = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  return new Date(now).toDateString() === d.toDateString() ? time : `${dayWord(d)} ${time}`;
}

// A title worth showing: not a path, not a user@host prompt, not the program's own name.
const TITLE_PATH = /^(?:[~/]|[A-Za-z]:\\)/;
export function tellsSomething(live, raw, program) {
  return Boolean(live) && !TITLE_PATH.test(raw) && !TITLE_PATH.test(live) && !live.includes("@")
    && live.toLowerCase() !== program?.key && live !== program?.name;
}

// The one name a person sees for a computer. A name they typed wins; otherwise the words already in use.
export function machineTitle(name, hostName, alias) {
  const named = String(alias ?? "").trim();
  return named || name || hostName || "This computer";
}

export function aliasText(names, machine) {
  return String((names ?? {})[machine || ""] ?? "").trim();
}
