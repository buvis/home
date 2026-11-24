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
    export const div = () => globalThis.modPortTest.element("div"), svg = div, image = div;`,
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
    theme: { done: "green", idle: "grey", dim: "dim", selected: "selected", muted: "muted", blocked: "red", working: "amber" } };
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
  assert.equal(data.shared["alerts.log"][0].where, "Project / Task");
  find(root, "act-0").events.on_click();
  assert.deepEqual(calls, [["run", "agent.focus", { terminal: "t1" }], ["closeOverlay", "log"]]);
});
test("status bar presents routine history neutrally and problems by severity", () => {
  for (const [level, color] of [["info", "muted"], ["success", "muted"], ["warning", "amber"], ["error", "red"]]) {
    data.shared["alerts.log"] = [{ level, title: "Notice" }];
    const badge = find(start(Status).render(), "alerts");
    assert.deepEqual(badge.styles.text_color, [color]);
    assert.ok(text(badge).includes("Notifications"));
  }
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
