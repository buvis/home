// Rule: what Ctrl-Q m offers can also be found by name in the command palette.
// Run: node --test mods/prefix/palette.test.mjs
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import { test } from "node:test";
import { isDeepStrictEqual } from "node:util";

const modules = {
  "gpui-kit": "export class View {} export const div = null;",
  "gpui-base": "export const h_flex = null, v_flex = null;",
  herdr: "export const closeOverlay = null, props = null, run = null, theme = null;",
};
const hooks = registerHooks({
  resolve(name, context, next) {
    return Object.hasOwn(modules, name) ? { url: `data:text/javascript,${encodeURIComponent(modules[name])}`, shortCircuit: true } : next(name, context);
  },
});
const { MOD_ITEMS } = await import("./main.js");
hooks.deregister();
const { palette } = JSON.parse(readFileSync(new URL("./mod.json", import.meta.url), "utf8"));

test("every Ctrl-Q m entry is in the command palette", () => {
  for (const [, label, [command, args = {}]] of MOD_ITEMS)
    assert.ok(palette.some((p) => p.command === command && isDeepStrictEqual(p.args ?? {}, args)), `missing in mod.json palette: ${label}`);
});

// The palette drops an entry without a title, or one that opens a mod it cannot find, without a word.
test("every palette entry has a title and names a mod that exists", () => {
  for (const p of palette) {
    assert.ok(typeof p.title === "string" && p.title.trim(), JSON.stringify(p));
    const mod = p.command === "mod.open" ? p.args.name : p.args?.mod;
    if (mod) assert.ok(existsSync(new URL(`../${mod}/main.js`, import.meta.url)), `${p.title}: mods/${mod}/main.js`);
  }
});
