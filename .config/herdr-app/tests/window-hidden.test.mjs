// Rule: while the window is hidden (minimized, covered, on another Space) no poll
// starts work, and the first look after it is back catches up.
// Run: node --test tests/window-hidden.test.mjs
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { registerHooks } from "node:module";
import { test, beforeEach } from "node:test";

const MODS = new URL("../mods/", import.meta.url);
const source = (path) => readFileSync(new URL(path, MODS), "utf8");
const POLLERS = { "ship-it": ["refreshGit", "refreshPr", "refreshCounts"], reviewer: ["refresh"], "my-space-folders": ["refreshMachines", "loadFolders"] };
const PANELS = ["ship-it", "ship-it-prs", "ship-it-review", "ship-it-issues"];
const LOADED = [...Object.keys(POLLERS), "ship-it-prs"];

// Stand-ins for the host modules: every name the mods import exists. UI parts do
// nothing; herdr's functions answer from `data`.
const HOST = ["herdr", "gpui-kit", "gpui-base"];
const names = Object.fromEntries(HOST.map((host) => [host, new Set()]));
for (const mod of LOADED) {
  for (const file of readdirSync(new URL(`${mod}/`, MODS)).filter((f) => f.endsWith(".js"))) {
    for (const [, list, host] of source(`${mod}/${file}`).matchAll(/import\s*\{([^}]*)\}\s*from\s*"(herdr|gpui-kit|gpui-base)"/g)) {
      for (const name of list.split(",")) if (name.trim()) names[host].add(name.trim().split(/\s+/)[0]);
    }
  }
}
let data;
const any = new Proxy(function () {}, { get: (_t, key) => (key === "then" || typeof key === "symbol" ? undefined : any), apply: () => any, construct: () => any });
globalThis.hiddenTest = { any, call: (name) => (name === "shared" ? undefined : data[name]) };
const stub = (host) => [...names[host]].map((name) =>
  name === "View" ? "export class View {}"
    : host === "herdr" ? `export const ${name} = (...a) => globalThis.hiddenTest.call("${name}", ...a);`
      : `export const ${name} = globalThis.hiddenTest.any;`).join("\n");
const hooks = registerHooks({
  resolve(name, context, next) {
    return HOST.includes(name) ? { url: `data:text/javascript,${encodeURIComponent(stub(name))}`, shortCircuit: true } : next(name, context);
  },
});
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
const views = {};
for (const mod of LOADED) views[mod] = (await import(new URL(`${mod}/main.js`, MODS))).default;
const { panelShown, modShown } = await import(new URL("ship-it/data.js", MODS));
hooks.deregister();

beforeEach(() => {
  data = { checking: false, props: {}, settings: { zoom: 1, font_size: 12 }, theme: {}, focused: {}, agents: [], terminals: [], machines: [],
    window: { platform: "macos", active: true, visible: true },
    spaces: [{ id: "s", active: true, tabs: [{ id: "t", active: true }] }],
    panes: [{ pane: "p", tab: "t", mod: "ship-it-review" }],
    layout: { id: "root", children: [{ id: "panel", children: [{ id: "panel-body", active: "ship-it-prs" }] }] } };
});

// A started view whose pollers only count their calls, and its timers.
function start(mod) {
  const view = new views[mod](), hits = {}, timers = [];
  for (const name of POLLERS[mod]) { hits[name] = 0; view[name] = () => { hits[name]++; }; }
  if (view.checkNew) view.checkNew = () => {}; // event-driven, not a poll: it stays unguarded
  const cx = { timer: { every: (_ms, fn) => timers.push(fn), after() {} }, spawn() {}, notify() {}, focus_handle: () => any };
  view.init({}, cx);
  const tick = () => { for (const name of POLLERS[mod]) hits[name] = 0; for (const fn of timers) fn(cx); return hits; };
  return { view, tick, cx };
}

for (const mod of Object.keys(POLLERS)) {
  test(`${mod}: no poll starts work while the window is hidden`, () => {
    const { tick } = start(mod);
    data.window.visible = false;
    assert.deepEqual(Object.values(tick()), POLLERS[mod].map(() => 0));
  });
  test(`${mod}: polls run while the window shows, and during a check (no window)`, () => {
    const { tick } = start(mod);
    // refreshPr has its own pace (every fourth poll while checks are settled).
    const polled = (hits) => Object.entries(hits).filter(([name]) => name !== "refreshPr").every(([, n]) => n > 0);
    assert.ok(polled(tick()), "visible window");
    data.window = null;
    assert.ok(polled(tick()), "no window");
  });
}

test("ship-it: back after a long absence, the first look refreshes git and the PR at once", (t) => {
  let now = 1_000_000;
  t.mock.method(Date, "now", () => now);
  const { tick, view, cx } = start("ship-it");
  const away = (ms) => { data.window.visible = false; tick(); now += ms; data.window.visible = true; };
  assert.equal(tick().refreshPr, 0, "a settled PR is not asked for on every poll");
  away(5_000);
  assert.equal(tick().refreshPr, 0, "a quick app switch asks GitHub nothing");
  away(60_000);
  assert.equal(tick().refreshPr, 1, "the first poll after a long absence catches up");
  away(60_000);
  let git = 0, pr = 0;
  view.refreshGit = () => { git++; };
  view.refreshPr = () => { pr++; };
  view.back(cx); // what render calls
  assert.deepEqual([git, pr], [1, 1], "so does a render");
});

test("ship-it still reacts when an agent stops while the window is hidden", () => {
  const { tick, view } = start("ship-it");
  let bumps = 0;
  view.bumpCounts = () => { bumps++; };
  data.agents = [{ address: "t1", status: "working" }];
  tick(); // sampled while the window shows
  data.window.visible = false;
  data.agents = [{ address: "t1", status: "done" }];
  const hits = tick();
  assert.deepEqual([bumps, hits.refreshPr], [1, 1], "it may have opened a PR or an issue: ask now");
  assert.equal(hits.refreshGit + hits.refreshCounts, 0, "the polls still wait");
});

test("ship-it-prs: an all-spaces load dropped while the window is hidden is asked again", async () => {
  const view = new views["ship-it-prs"]();
  view.refresh = () => {};
  let load;
  const cx = { timer: { every() {}, after() {} }, spawn: (task) => { load = task; }, notify() {} };
  view.init({}, cx);
  view.scope = "all";
  view.refreshQueue(cx, true);
  data.window.visible = false; // another app covers Herdr before the answer is back
  await load(cx);
  assert.equal(view.stale, true, "the dropped answer leaves the panel marked out of date");
  data.window.visible = true;
  view.refreshQueue(cx, true);
  await load(cx);
  assert.equal(view.stale, false, "an answer that arrives in sight is applied");
});

test("ship-it panels count as not shown while the window is hidden", () => {
  assert.equal(panelShown("ship-it-prs"), true);
  assert.equal(modShown("ship-it-review"), true);
  data.window.visible = false;
  assert.equal(panelShown("ship-it-prs"), false);
  assert.equal(modShown("ship-it-review"), false);
  data.window = null; // herdr-app check
  assert.equal(panelShown("ship-it-prs"), true);
});

test("the four ship-it folders carry the same data.js", () => {
  for (const mod of PANELS) assert.equal(source(`${mod}/data.js`), source("ship-it/data.js"), mod);
});
