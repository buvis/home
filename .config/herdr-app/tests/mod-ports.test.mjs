import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { test, beforeEach } from "node:test";

// Load the real mods against in-memory Herdr data, without running programs.
const calls = [];
let data, stored;
const cx = { timer: { every() {}, after() {} }, spawn() {}, notify() {} };
function element(kind) {
  const node = { kind, kids: [], styles: {}, events: {} };
  const proxy = new Proxy(node, {
    get(target, key) {
      if (key in target) return target[key];
      if (key === "then" || typeof key === "symbol") return undefined;
      return (...args) => {
        if (key === "child") node.kids.push(args[0]);
        else if (key === "children") node.kids.push(...args[0]);
        else if (key === "when") return args[0] ? args[1](proxy) : proxy;
        else if (key.startsWith("on_")) node.events[key] = args.at(-1);
        else node.styles[key] = args;
        return proxy;
      };
    },
  });
  return proxy;
}
const functions = ["agents", "terminals", "panes", "focused", "spaces", "run", "theme",
  "shared", "setShared", "setAgentOrder", "openOverlay", "closeOverlay", "props", "window",
  "layout", "settings", "machines", "exec", "hc", "watchFolder", "pickFolder", "home",
  "nextCommand", "appHome", "checking", "keys"];
globalThis.modPortTest = {
  element,
  call(name, ...args) {
    if (name === "shared") return data.shared[args[0]];
    if (name === "setShared") { data.shared[args[0]] = args[1]; return; }
    if (name in data) return data[name];
    calls.push([name, ...args]);
  },
};
const modules = {
  herdr: functions.map(name => `export const ${name} = (...args) => globalThis.modPortTest.call("${name}", ...args);`).join("\n"),
  "gpui-kit": `export class View {};
    export const div = () => globalThis.modPortTest.element("div"), image = div;
    export const svg = path => globalThis.modPortTest.element("svg").asset(path);`,
  "gpui-base": `export const v_flex = () => globalThis.modPortTest.element("column"), h_flex = () => globalThis.modPortTest.element("row");
    export const InputState = {}, Input = {}, TextView = { markdown: (_id, text) => v_flex().child(text) };`,
};
const hooks = registerHooks({
  resolve(name, context, next) {
    return Object.hasOwn(modules, name)
      ? { url: `data:text/javascript,${encodeURIComponent(modules[name])}`, shortCircuit: true }
      : next(name, context);
  },
});
const [Agents, Tabs, Folders, Spaces, Toast, Status] = await Promise.all(
  ["my-agents", "my-tabs", "my-space-folders", "my-spaces", "my-toast", "my-status"]
    .map(async name => (await import(`../mods/${name}/main.js`)).default),
);
hooks.deregister();

beforeEach(() => {
  calls.length = 0;
  stored = {};
  globalThis.localStorage = {
    getItem: key => stored[key] ?? null,
    setItem: (key, value) => { stored[key] = value; },
    removeItem: key => { delete stored[key]; },
  };
  data = { props: {}, checking: false, keys: [], agents: [], terminals: [], panes: [], spaces: [], machines: [],
    focused: {}, shared: {}, settings: { zoom: 1 }, window: { platform: "macos" },
    layout: { id: "sidebar", size: { px: 268 } },
    theme: { done: "green", idle: "grey", dim: "dim", selected: "selected", muted: "muted", blocked: "red", working: "amber", accent: "blue" } };
});
function start(Class) {
  const view = new Class();
  // These independent async probes are not part of saved-state initialization.
  if (view.refreshMachines) view.refreshMachines = () => {};
  if (view.loadFolders) view.loadFolders = () => {};
  view.init?.({}, cx);
  return view;
}

for (const [name, Class] of [["agents", Agents], ["space folders", Folders], ["spaces", Spaces], ["status", Status]]) {
  test(`${name}: checks render without launching background work`, () => {
    data.checking = true;
    const view = new Class();
    const unexpected = () => assert.fail("check started background work");
    view.init({}, { timer: { every: unexpected, after: unexpected }, spawn: unexpected });
    view.render();
    assert.ok(!calls.some(([name]) => ["exec", "hc"].includes(name)));
  });
}
const walk = root => root && typeof root === "object"
  ? [root, ...root.kids.flatMap(walk)] : [];
const find = (root, id) => walk(root).find(node => node.styles.id?.[0] === id);
const text = root => typeof root === "string" ? root : root?.kids?.map(text).join(" ") ?? "";

for (const value of ["{bad", "null", "false", "7", '"wrong"', "[]"]) {
  test(`agent and panel maps recover from invalid saved state: ${value}`, () => {
    stored = { changed: value, panels: value };
    const agents = start(Agents);
    assert.deepEqual(agents.changed, {});
    agents.track([{ address: "t1", status: "working" }], 100);
    assert.equal(agents.since({ address: "t1" }), 100);
    const tabs = start(Tabs);
    assert.deepEqual(tabs.panels, {});
    tabs.syncPanel({ id: "s1" }, { hidden: false }, { active: "files" }, ["files"]);
    assert.equal(JSON.parse(stored.panels).s1, "files");
  });
}
for (const value of ["{bad", "null", "false", "7", '"wrong"', "{}"]) {
  test(`pin and folded-machine lists recover from invalid saved state: ${value}`, () => {
    stored = { pins: value, "machines.folded": value };
    assert.deepEqual(start(Agents).pendingPins, []);
    assert.deepEqual([...start(Folders).folded], []);
    assert.deepEqual([...start(Spaces).folded], []);
  });
}
for (const value of ["{bad", "null", "false", "7", '"wrong"', "[]", '{"vps":null}']) {
  test(`reconnect state recovers without blocking the sidebar: ${value}`, () => {
    stored["machines.reconnecting"] = value;
    assert.deepEqual(start(Spaces).reconnecting, {});
  });
}
test("valid saved choices survive initialization and reconnect busy resets", () => {
  stored = { changed: '{"t1":{"s":"working","at":12}}', pins: '["t2"]',
    panels: '{"s1":"runway"}', "machines.folded": '["vps"]',
    "machines.reconnecting": '{"vps":{"machine":"vps","busy":true}}' };
  const agents = start(Agents);
  assert.equal(agents.since({ address: "t1" }), 12);
  assert.deepEqual(agents.pendingPins, ["t2"]);
  assert.equal(start(Tabs).panels.s1, "runway");
  assert.deepEqual([...start(Folders).folded], ["vps"]);
  const spaces = start(Spaces);
  assert.deepEqual([...spaces.folded], ["vps"]);
  assert.deepEqual(spaces.reconnecting.vps, { machine: "vps", busy: false });
});

function family(status, kept = true) {
  const parent = { address: "parent", status: "working", space: "s1", tab: "tab1", seq: 1 };
  const child = { address: "child", status, parent: "parent", state: "live", seq: 2 };
  data.agents = kept ? [parent, child] : [parent];
  data.terminals = [parent, child];
  return start(Agents).render(cx);
}
test("kept finished child displays Done while its working parent stays Working", () => {
  const root = family("done");
  assert.ok(find(root, "sec-2"));
  assert.equal(find(root, "sec-3"), undefined);
  assert.ok(walk(find(root, "sub-child")).some(n => n.styles.bg?.[0] === "green"));
});
test("unkept finished child stays idle and blocked child raises parent urgency", () => {
  assert.ok(walk(find(family("done", false), "sub-child")).some(n => n.styles.border_color?.[0] === "grey"));
  assert.ok(find(family("error", false), "sec-4"));
  assert.ok(find(family("blocked"), "sec-4"));
});
test("local hold-in-Done remains until focus leaves the finished agent", () => {
  const view = start(Agents);
  const done = { address: "t1", focused: true, status: "done" };
  view.hold([done]);
  const idle = { ...done, status: "idle" };
  view.hold([idle]);
  assert.equal(view.rank(idle), 3);
  view.hold([]);
  assert.equal(view.rank(idle), 1);
});

test("expanded toast retains every line and sizes to its content", () => {
  data.props = { fitHeight: true, title: "Title\nsecond title line", body: "first\nlast line", overlay: "test" };
  const root = start(Toast).render();
  for (const value of [data.props.title, data.props.body]) {
    const node = walk(root).find(n => n.kids.includes(value));
    assert.ok(node, value);
    assert.equal(node.styles.truncate, undefined);
  }
  assert.deepEqual(root.styles.min_h, [70]);
  assert.equal(root.styles.size_full, undefined);
});
test("custom fixed-height toast keeps every line in a scrollable card", () => {
  data.props = { title: "Title", body: "first\nlast line" };
  const root = start(Toast).render();
  assert.deepEqual(root.styles.size_full, []);
  assert.ok(text(root).includes("first"));
  assert.ok(text(root).includes("last line"));
  assert.ok(walk(root).some(n => n.styles.overflow_y_scrollbar));
  assert.equal(walk(root).find(n => n.kids.includes(data.props.body)).styles.truncate, undefined);
});
test("errors still enter the full log while attention warnings remain toasts", () => {
  data.props = { level: "error", title: "Failure", body: "first\nlast", overlay: "error" };
  start(Toast);
  assert.equal(data.shared["alerts.log"][0].body, "first\nlast");
  assert.deepEqual(calls, [["closeOverlay", "error"]]);
  calls.length = 0;
  data.props = { level: "warning", title: "Needs you", action: { name: "agent.focus", args: { terminal: "t1" } }, overlay: "attention" };
  const root = start(Toast).render();
  assert.equal(data.shared["alerts.log"].length, 2);
  assert.deepEqual(calls, []);
  root.events.on_click();
  assert.deepEqual(calls, [["run", "agent.focus", { terminal: "t1" }], ["closeOverlay", "attention"]]);
});

for (const level of [undefined, "info", "success", "warning", "error"]) {
  test(`notification history records ${level ?? "default info"} with full text`, () => {
    data.props = { overlay: "notification", title: "Result", body: "first\nlast", ...(level ? { level } : {}) };
    start(Toast);
    const [entry] = data.shared["alerts.log"];
    assert.equal(entry.level, level ?? "info");
    assert.equal(entry.body, "first\nlast");
    assert.equal(entry.title, "Result");
    assert.deepEqual(calls, ["error", "warning"].includes(level) ? [["closeOverlay", "notification"]] : []);
  });
}
test("routine notifications cannot evict older errors or warnings", () => {
  data.shared["alerts.log"] = [
    { level: "error", title: "Unresolved error", at: 1 },
    { level: "warning", title: "Unresolved warning", at: 2 },
  ];
  for (let i = 0; i < 60; i++) {
    data.props = { overlay: `n${i}`, title: `Info ${i}` };
    start(Toast);
  }
  const history = data.shared["alerts.log"];
  assert.equal(history.length, 52);
  assert.equal(history[0].title, "Info 59");
  assert.ok(history.some(a => a.title === "Unresolved error"));
  assert.ok(history.some(a => a.title === "Unresolved warning"));
  assert.ok(!history.some(a => a.title === "Info 9"));
});
test("log inspection and mod checks do not generate notifications", () => {
  const entries = [{ level: "error", title: "Existing", at: 1 }];
  data.shared["alerts.log"] = entries;
  data.props = { log: true };
  assert.ok(text(start(Toast).render()).includes("Notifications (1)"));
  data.props = { overlay: "check", title: "Check", level: "error" };
  data.checking = true;
  start(Toast);
  assert.equal(data.shared["alerts.log"], entries);
  assert.deepEqual(calls, []);
});
test("history keeps the captured source and action after focus changes", () => {
  data.panes = [{ pane: "p1", terminal: "t1", tab: "tab1" }];
  data.spaces = [{ id: "s1", name: "Project", tabs: [{ id: "tab1", name: "Task" }] }];
  data.props = { overlay: "success", title: "Complete", level: "success",
    action: { name: "agent.focus", args: { terminal: "t1" } } };
  start(Toast);
  data.focused = { terminal: "t2" };
  data.props = { log: true, overlay: "log" };
  const root = start(Toast).render();
  assert.equal(data.shared["alerts.log"][0].where, "Project / Task / t1");
  find(root, "act-0").events.on_click();
  assert.deepEqual(calls, [["run", "agent.focus", { terminal: "t1" }], ["closeOverlay", "log"]]);
});
test("status shows one distinct severity icon and count per nonempty group", () => {
  data.shared["alerts.log"] = ["error", "error", "warning", "success", "info", "info", "info"].map(level => ({ level }));
  const root = start(Status).render();
  const icons = new Set();
  for (const [level, count, color] of [["error", 2, "red"], ["warning", 1, "amber"], ["success", 1, "green"], ["info", 3, "blue"]]) {
    const badge = find(root, `alerts-${level}`);
    assert.equal(text(badge).trim(), String(count));
    assert.deepEqual(badge.styles.text_color, [color]);
    assert.ok(badge.styles.tooltip[0].toLowerCase().includes(level));
    icons.add(walk(badge).find(node => node.kind === "svg").styles.asset[0]);
    badge.events.on_click();
  }
  assert.equal(icons.size, 4);
  assert.ok(!text(root).includes("Notifications"));
  assert.equal(calls.filter(([name]) => name === "openOverlay").length, 4);
});
test("status hides empty severity groups and removes the final badge", () => {
  data.shared["alerts.log"] = [{ level: "warning" }];
  const root = start(Status).render();
  for (const level of ["error", "success", "info"]) assert.equal(find(root, `alerts-${level}`), undefined);
  data.shared["alerts.log"] = [];
  assert.equal(find(start(Status).render(), "alerts-warning"), undefined);
});
test("dismiss removes only its notification despite newer arrivals and keeps history open", () => {
  const first = { at: 1, level: "error", title: "First" }, second = { at: 2, level: "warning", title: "Second" };
  data.shared["alerts.log"] = [first, second];
  data.props = { log: true, overlay: "history" };
  const root = start(Toast).render();
  const newer = { at: 3, level: "info", title: "New" };
  data.shared["alerts.log"] = structuredClone([newer, first, second]);
  find(root, "dismiss-1").events.on_click();
  assert.deepEqual(data.shared["alerts.log"], [newer, first]);
  assert.deepEqual(calls, []);
});
test("dismiss removes just one duplicate and can leave an empty open history", () => {
  const entry = { at: 1, level: "error", title: "Same" };
  data.shared["alerts.log"] = [entry, structuredClone(entry)];
  data.props = { log: true, overlay: "history" };
  const view = start(Toast);
  find(view.render(), "dismiss-1").events.on_click();
  assert.deepEqual(data.shared["alerts.log"], [entry]);
  find(view.render(), "dismiss-0").events.on_click();
  assert.deepEqual(data.shared["alerts.log"], []);
  assert.ok(text(view.render()).includes("No notifications"));
  assert.deepEqual(calls, []);
});
for (const now of [new Date(2026, 0, 1, 0, 30), new Date(2026, 2, 30, 0, 30)]) {
  test(`history dates use local calendar days across ${now.toDateString()}`, (t) => {
    t.mock.method(Date, "now", () => now.getTime());
    const today = new Date(now); today.setMinutes(5);
    const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1); yesterday.setHours(0, 15);
    const older = new Date(now); older.setDate(now.getDate() - 2); older.setHours(23, 59);
    data.props = { log: true };
    data.shared["alerts.log"] = [today, yesterday, older].map(at => ({ at: +at, level: "info", title: "Notice" }));
    const root = start(Toast).render();
    assert.equal(text(find(root, "time-0")), "00:05:00");
    assert.equal(text(find(root, "time-1")), "Yesterday 00:15:00");
    assert.equal(text(find(root, "time-2")), `${older.toLocaleDateString()} 23:59:00`);
    assert.equal(find(root, "time-2").styles.tooltip[0], `${older.toLocaleDateString()} 23:59:00`);
  });
}
test("history actions use icons with labels and copying keeps the captured pane name", () => {
  data.panes = [{ pane: "p1", terminal: "t1", tab: "tab1", name: "Build", title: "bash" }];
  data.spaces = [{ id: "s1", name: "Project", tabs: [{ id: "tab1", name: "Task" }] }];
  data.props = { overlay: "notice", title: "Complete", action: { name: "agent.focus", args: { terminal: "t1" } } };
  start(Toast);
  data.panes[0] = { ...data.panes[0], name: "Renamed" };
  data.props = { log: true };
  const root = start(Toast).render();
  assert.ok(text(root).includes("from Project / Task / Build"));
  for (const id of ["copy-all", "clear", "close", "act-0", "go-0", "copy-0", "dismiss-0"]) {
    const action = find(root, id);
    assert.ok(walk(action).some(node => node.kind === "svg"), id);
    assert.ok(action.styles.accessibility_label?.[0], id);
    assert.ok(action.styles.tooltip?.[0], id);
    assert.equal(text(action), "", id);
  }
  let copied;
  find(root, "copy-0").events.on_click({}, { write_to_clipboard: value => { copied = value; }, notify() {} });
  assert.ok(copied.includes("Project / Task / Build"));
  assert.ok(!/\b(?:AM|PM)\b/.test(copied));
});
test("a gone terminal has a disabled crossed-out icon instead of text or navigation", () => {
  data.props = { log: true };
  data.shared["alerts.log"] = [{ at: 1, level: "info", title: "Notice", target: { terminal: "gone" } }];
  const root = start(Toast).render(), action = find(root, "go-0");
  assert.ok(action, "Keep the source action in its usual position");
  assert.deepEqual(action.styles.disabled, [true]);
  assert.deepEqual(action.styles.text_color, ["dim"]);
  assert.deepEqual(action.styles.tooltip, ["Source terminal is no longer available"]);
  assert.deepEqual(action.styles.accessibility_label, action.styles.tooltip);
  assert.equal(action.events.on_click, undefined);
  assert.equal(text(action), "");
  assert.ok(walk(action).some(node => node.styles.asset?.[0] === "mods/my-toast/terminal-off.svg"));
  assert.ok(!text(root).includes("terminal gone"));
});
test("legacy history can show the current pane name without changing saved entries", () => {
  data.panes = [{ pane: "p1", terminal: "t1", name: "Build" }];
  const entry = { at: 1, level: "info", title: "Old", where: "Project / Task", target: { terminal: "t1" } };
  data.shared["alerts.log"] = [entry];
  data.props = { log: true };
  assert.ok(text(start(Toast).render()).includes("from Project / Task / Build"));
  assert.equal(data.shared["alerts.log"][0], entry);
});
test("bulk routine dismissal keeps every error and warning, including new arrivals", () => {
  const error = { at: 1, level: "error", title: "Error" }, warning = { at: 2, level: "warning", title: "Warning" };
  data.shared["alerts.log"] = [error, { at: 3, level: "info" }, warning, { at: 4, level: "success" }];
  data.props = { log: true };
  const view = start(Toast), root = view.render();
  const newWarning = { at: 5, level: "warning", title: "New warning" };
  data.shared["alerts.log"] = [newWarning, ...data.shared["alerts.log"], { at: 6, level: "info" }];
  find(root, "clear-routine").events.on_click();
  assert.deepEqual(data.shared["alerts.log"], [newWarning, error, warning]);
  assert.equal(find(view.render(), "clear-routine"), undefined);
  assert.deepEqual(calls, []);
});
test("login toast keeps copy action without dismissing or navigating", () => {
  data.props = { fitHeight: true, body: "vps needs login; run hc machine login vps" };
  const root = start(Toast).render();
  let copied, stopped = false;
  find(root, "toast-login-copy").events.on_click({}, {
    stop_propagation() { stopped = true; }, write_to_clipboard(value) { copied = value; }, notify() {},
  });
  assert.equal(copied, "hc machine login vps");
  assert.equal(stopped, true);
  assert.deepEqual(calls, []);
});
