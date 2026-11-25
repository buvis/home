// Rules for the local edits to the gallery mod `walkthrough` (GALLERY.md). An
// upstream update that drops one of them fails here.
// Run: node --test tests/walkthrough-local.test.mjs
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { registerHooks } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const APP_HOME = fileURLToPath(new URL("../", import.meta.url));
const WRAPPER = join(APP_HOME, "bin/run-claude-pat");
const MOD = join(APP_HOME, "mods/walkthrough");

// A home of its own with a stand-in `claude` that prints the token it got and its arguments.
const homes = [];
after(() => { for (const home of homes) rmSync(home, { recursive: true, force: true }); });
function fakeHome(token) {
  const home = mkdtempSync(join(tmpdir(), "run-claude-pat-"));
  homes.push(home);
  mkdirSync(join(home, "bin"));
  writeFileSync(join(home, "bin/claude"), '#!/bin/sh\nprintf "%s|" "$CLAUDE_CODE_OAUTH_TOKEN" "$@"\n');
  chmodSync(join(home, "bin/claude"), 0o755);
  if (token !== null) {
    mkdirSync(join(home, ".local/secrets"), { recursive: true });
    writeFileSync(join(home, ".local/secrets/claude-setup-token"), token);
  }
  return { HOME: home, PATH: `${join(home, "bin")}:/usr/bin:/bin` };
}
const wrapper = (env, ...args) => spawnSync(WRAPPER, args, { env, encoding: "utf8" });

test("run-claude-pat gives claude the setup token and passes every argument through", () => {
  const r = wrapper(fakeHome("tok-123\n"), "-p", "--tools", "", "--model", "haiku");
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.stdout, "tok-123|-p|--tools||--model|haiku|");
});

test("run-claude-pat replaces a token that is already in the environment", () => {
  const r = wrapper({ ...fakeHome("tok-123"), CLAUDE_CODE_OAUTH_TOKEN: "stale" }, "-p");
  assert.equal(r.stdout, "tok-123|-p|");
});

test("run-claude-pat drops a carriage return and blanks around the token", () => {
  assert.equal(wrapper(fakeHome(" tok-123\r\n"), "-p").stdout, "tok-123|-p|");
});

// The mod shows a failed `--version` probe as "claude isn't installed" and turns Generate off.
test("run-claude-pat answers the version probe without a token, so a missing token is not shown as a missing claude", () => {
  const r = wrapper(fakeHome(null), "--version");
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.stdout, "|--version|");
});

test("run-claude-pat fails without starting claude when the token file is missing or empty", () => {
  for (const token of [null, "", "\n", " \t\r\n"]) {
    const r = wrapper(fakeHome(token), "-p");
    assert.notEqual(r.status, 0, `token ${JSON.stringify(token)}`);
    assert.equal(r.stdout, "", "claude must not run");
    assert.match(r.stderr, /claude-setup-token/);
  }
});

test("walkthrough starts Claude generations through run-claude-pat, never a bare claude", async () => {
  const engine = readFileSync(join(MOD, "engine.js"), "utf8");
  const imported = engine.match(/import\s*\{([^}]*)\}\s*from\s*"herdr"/);
  assert.ok(imported, "engine.js imports herdr in another shape now: update this stub");
  const names = imported[1].split(",").map((n) => n.trim()).filter(Boolean);
  const stub = names.map((n) => `export const ${n} = ${n === "appHome" ? '() => "/app-home"' : "() => { throw new Error('not expected') }"};`).join("\n");
  const hooks = registerHooks({
    resolve: (name, context, next) => (name === "herdr" ? { url: `data:text/javascript,${encodeURIComponent(stub)}`, shortCircuit: true } : next(name, context)),
  });
  const { programOf } = await import(pathToFileURL(join(MOD, "engine.js")).href);
  hooks.deregister();
  assert.equal(await programOf("claude"), "/app-home/bin/run-claude-pat");
});

// Its update strip hands out a prompt that has an agent replace the folder, which drops
// the local edits. Updates come through sysup (bin/hmod-merge --auto), which also runs
// this file, so the mod stays quiet.
test("walkthrough never checks for a release itself and never offers its update prompt", async () => {
  const view = readFileSync(join(MOD, "view.js"), "utf8");
  assert.ok(view.includes("this.update = updater({ check: false,"), "view.js builds its updater with the check on");
  assert.equal(view.split("updater(").length - 1, 1, "view.js builds a second updater");
  // `check: false` must still mean "no request, no strip" after a merge of lib/update.js.
  const { updater, REPO } = await import(pathToFileURL(join(MOD, "lib/update.js")).href);
  let asked = 0;
  // `wait` never resolves: the default one arms a real 15 s timer.
  const waiting = { shared: () => ({ repo: REPO, latest: { tag: "v99.0.0" } }), setShared: () => {}, wait: () => new Promise(() => {}), fetch: () => { asked += 1; throw new Error("offline"); } };
  const on = updater({ ...waiting, check: true });
  await on.check();
  assert.equal(asked, 1, "control: with the check on, this state asks GitHub");
  assert.ok(on.available(), "control: with the check on, this state shows the strip");
  asked = 0;
  const off = updater({ ...waiting, check: false });
  await off.check();
  assert.equal(asked, 0, "it asked GitHub");
  assert.equal(off.available(), null, "it offers the release");
});

test("walkthrough shows the shared ring for busy states, never braille frames", () => {
  const sources = readdirSync(MOD).filter((f) => f.endsWith(".js")).map((f) => [f, readFileSync(join(MOD, f), "utf8")]);
  // assert.ok on a boolean: a failed assert.match would print the whole source file.
  for (const [file, text] of sources) assert.ok(!text.includes(".frames("), `${file} draws braille frames`);
  const view = sources.find(([file]) => file === "view.js")[1];
  assert.ok(view.includes('svg("mods/workspace-chrome/spinner.svg").size(size).flex_none().text_color(t.working).spin(900)'), "the shared ring, at its one speed");
  // The loading titles, the running banner and the Post button are text-only upstream.
  assert.ok(!/this\.posting \? "Posting…"|"…", `Writing a new walkthrough/.test(view), "a busy state without the ring");
  assert.ok(view.includes(".when(!icon, (e) => e.child(ring(t"), "the Reading… titles carry the ring");
  // Header, Reading… titles, progress row, running banner, Post button.
  assert.ok(view.split("ring(t").length - 1 >= 5, "one of the five busy states lost its ring");
});
