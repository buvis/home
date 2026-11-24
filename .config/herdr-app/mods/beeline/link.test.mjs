// Run: node --test mods/beeline/link.test.mjs
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { test } from "node:test";

const ran = [];
globalThis.beelineRun = (...call) => ran.push(call);
const hooks = registerHooks({
  resolve(name, context, next) {
    return name === "herdr"
      ? { url: "data:text/javascript,export const run = (...a) => globalThis.beelineRun(...a);", shortCircuit: true }
      : next(name, context);
  },
});
const { editTarget, handleLink } = await import("./link.js");
hooks.deregister();

const source = { pane: "clicked", space: "workspace", machine: null };
const link = { kind: "file", path: "/repo/src/my file.rs", raw: "src/my file.rs:42:7", line: 42, column: 7 };

test("opens a clicked file:line in Neovim at that position, right of the clicked pane", () => {
  ran.length = 0;
  assert.equal(handleLink({ link, source }), "handled");
  assert.deepEqual(ran, [["pane.split", { pane: "clicked", direction: "right",
    argv: ["nvim", "+call cursor(42,7)", "--", "/repo/src/my file.rs"] }]]);
});

test("a line without a column goes to column 1, and a terminal outside a tab gets a new tab", () => {
  const [command, args] = editTarget({ link: { ...link, column: undefined }, source: { ...source, pane: null } });
  assert.equal(command, "tab.new");
  assert.deepEqual(args, { space: "workspace", name: "my file.rs", argv: ["nvim", "+call cursor(42,1)", "--", "/repo/src/my file.rs"] });
});

test("leaves links without a line, URLs, unresolved paths and remote terminals to Herdr", () => {
  ran.length = 0;
  for (const click of [
    { link: { ...link, line: undefined }, source },
    { link: { kind: "url", raw: "https://example.test", url: "https://example.test" }, source },
    { link: { ...link, path: null }, source },
    { link, source: { ...source, machine: "vps" } },
    { link, source: { pane: null, space: null, machine: null } },
  ]) assert.equal(handleLink(click), "pass");
  assert.deepEqual(ran, []);
});

test("never puts anything but whole numbers into the Neovim command", () => {
  for (const line of ["1|!touch /tmp/x", 0, -3, 1.5, NaN, 1e21]) assert.equal(editTarget({ link: { ...link, line }, source }), null);
  assert.deepEqual(editTarget({ link: { ...link, column: "7|q" }, source })[1].argv[1], "+call cursor(42,1)");
});
