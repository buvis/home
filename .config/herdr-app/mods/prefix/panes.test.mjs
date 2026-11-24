import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { test } from "node:test";

let props;
let pane;
let terminals = [];
let calls;
let labels;
const element = new Proxy({}, {
  get: (_, method) => (...args) => {
    if (method === "child" && typeof args[0] === "string") labels.push(args[0]);
    if (method === "when" && args[0]) args[1](element);
    return element;
  },
});
globalThis.paneTest = {
  div: () => element,
  props: () => props,
  panes: () => [pane],
  terminals: () => terminals,
  theme: () => ({}),
  home: () => "/home",
  closeOverlay: id => calls.push(["close", id]),
  openOverlay: spec => calls.push(["open", spec]),
  run: (...args) => calls.push(args),
};
const modules = {
  "gpui-kit": `export class View {}
    export const { div } = globalThis.paneTest;
    export const svg = div, image = div;`,
  "gpui-base": "export { div as h_flex, div as v_flex } from 'gpui-kit';",
  herdr: `export const { props, panes, terminals, theme, home, closeOverlay, openOverlay, run } = globalThis.paneTest;
    export const keys = () => [];
    export const exec = null, hc = null, notify = null, window = null,
      spaces = null, shared = null, setShared = null, focused = null, readTextFile = null, appHome = null;`,
};
const hooks = registerHooks({
  resolve(specifier, context, next) {
    if (!Object.hasOwn(modules, specifier)) return next(specifier, context);
    return { url: `data:text/javascript,${encodeURIComponent(modules[specifier])}`, shortCircuit: true };
  },
});
const { default: Prefix } = await import("./main.js");
const { default: Header } = await import("../my-pane/main.js");
const { default: HeaderMenu } = await import("../my-menu/main.js");
const { default: TerminalMenu } = await import("../on-screen/main.js");
hooks.deregister();
delete globalThis.paneTest;

test("Ctrl-Q R keeps resizing until Enter or Escape", () => {
  props = { overlay: "prefix" };
  const cx = {
    focus_handle: () => ({ focus() {} }),
    timer: { after() {} },
    stop_propagation() {},
    notify() {},
  };
  for (const exit of ["enter", "escape"]) {
    calls = [];
    const prefix = new Prefix();
    prefix.init(props, cx);
    for (const key of ["r", "h", "down", "up", "l", "ctrl-h", exit]) {
      prefix.key({ key, keystroke: key }, cx);
    }
    assert.deepEqual(calls, [
      ["pane.resize", { direction: "left" }],
      ["pane.resize", { direction: "down" }],
      ["pane.resize", { direction: "up" }],
      ["pane.resize", { direction: "right" }],
      ["close", "prefix"],
    ]);
  }
});

test("Ctrl-Q punctuation opens the rename dialog for each target", () => {
  props = { overlay: "prefix" };
  for (const [key, character, command] of [
    ["2", "@", "space.rename"],
    ["3", "#", "tab.rename"],
    ["4", "$", "pane.rename"],
  ]) {
    calls = [];
    new Prefix().key({ key, key_char: character }, { stop_propagation() {} });
    assert.deepEqual(calls, [["close", "prefix"], [command, {}]]);
  }
});

test("the pane header prefers a custom name and falls back when cleared", () => {
  props = { pane: "clicked" };
  const header = new Header();
  for (const name of ["Custom name", null]) {
    labels = [];
    pane = { pane: "clicked", name, program: { agent: true, name: "Codex" } };
    header.render();
    assert.equal(labels[0], name ?? "Codex");
  }
});

for (const [name, Menu] of [["header", HeaderMenu], ["terminal", TerminalMenu]]) {
  test(`the ${name} menu renames the clicked pane`, () => {
    labels = [];
    calls = [];
    pane = { pane: "clicked", terminal: "terminal", focused: false };
    props = { tab: "pane", target: { pane: "clicked", terminal: "terminal" }, overlay: "menu" };
    const menu = new Menu();
    menu.render();
    const index = labels.filter(Boolean).indexOf("Rename");
    assert.notEqual(index, -1);
    menu.choose(index);
    assert.deepEqual(calls, [["close", "menu"], ["pane.rename", { pane: "clicked" }]]);

    props.target.pane = "layout-terminal-block";
    labels = [];
    menu.render();
    assert.ok(!labels.includes("Rename"));
  });
}

test("a terminal menu with no on-screen paths still fits its pane actions", async () => {
  calls = [];
  pane = { pane: "remote/p1", terminal: "remote/t1", cwd: "/repo", branch: "topic" };
  terminals = [{ address: pane.terminal }];
  props = { tab: "pane", target: { pane: pane.pane, terminal: pane.terminal }, overlay: "menu" };
  let pending;
  new TerminalMenu().init(props, {
    focus_handle: () => ({ focus() {} }),
    spawn: task => { pending = task(); },
  });
  await pending;
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0], ["close", "menu"]);
  const [command, spec] = calls[1];
  assert.equal(command, "open");
  assert.ok(spec.height >= 8 * 31 + 9 + 12);
  assert.deepEqual(spec.props.target, props.target);
  assert.deepEqual(spec.props.paths, []);
});
