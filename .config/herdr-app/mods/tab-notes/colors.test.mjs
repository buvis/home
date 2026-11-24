// Run: node --test mods/tab-notes/colors.test.mjs
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { test } from "node:test";

const theme = { accent: "#111111", foreground: "#222222", ansi2: "#333333", muted: "#444444", ansi4: "#555555" };
let made;
globalThis.tabNotesTest = { theme, editor: (options) => { made = options; return { on() {}, release() {}, value: () => "" }; } };
const modules = {
  "gpui-kit": "export class View {} export const div = null;",
  "gpui-base": "export const v_flex = null, h_flex = null, Editor = null; export const EditorState = { new: (o) => globalThis.tabNotesTest.editor(o) };",
  herdr: `export const theme = () => globalThis.tabNotesTest.theme, settings = () => ({ font_family: "Mono" });
    export const spaces = () => [], machines = () => [], appHome = () => "/home";
    export const readTextFile = async () => "# note", writeTextFile = async () => {};`,
};
const hooks = registerHooks({
  resolve(name, context, next) {
    return Object.hasOwn(modules, name) ? { url: `data:text/javascript,${encodeURIComponent(modules[name])}`, shortCircuit: true } : next(name, context);
  },
});
const { default: Notes } = await import("./main.js");
hooks.deregister();

test("a note's Markdown is colored from the theme, not from fixed colors", async () => {
  const view = new Notes();
  let opened;
  const cx = { timer: { every() {} }, spawn: (task) => { opened = task(cx); }, notify() {} };
  view.init({}, cx);
  view.open("tab1", cx);
  await opened;
  assert.equal(made.language, "md");
  assert.deepEqual(Object.keys(made.syntax).sort(), ["code", "heading", "link", "list", "quote", "strong"]);
  for (const [part, color] of Object.entries(made.syntax)) assert.ok(Object.values(theme).includes(color), `${part} uses a theme color`);
});
