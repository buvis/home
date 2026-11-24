// Rules for the worktree dialog, run with: node --test mods/my-worktree/remove.test.mjs
// Order since Herdr 0.1.18: check, stop the space's programs, then let Git delete the folder.
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { test } from "node:test";

const modules = {
  "gpui-kit": "export class View {} export const div = null, svg = null;",
  "gpui-base": `export const v_flex = null, h_flex = null, Input = null, Scrollbar = null;
    export const InputState = { new: () => ({ on() {}, focus() {}, value: () => "" }) };`,
  herdr: `const t = globalThis.worktreeTest;
    export const { exec, run, props, spaces, panes, terminals, home, appHome, readTextFile } = t;
    export const closeOverlay = () => {}, theme = null;`,
};

const UNLOCKED = "worktree /repo\nHEAD 1\nbranch refs/heads/master\n\nworktree /topic\nHEAD 2\nbranch refs/heads/topic";
const ok = (stdout = "") => ({ code: 0, stdout, stderr: "" });
let s; // per-test state

function reset(over = {}) {
  s = {
    log: [], live: new Set(["t1"]), liveAtRemove: null, list: UNLOCKED,
    removal: ok(), props: { space: "worktree-space", action: "remove" }, ...over,
  };
}

function exec(program, args, opts = {}) {
  assert.equal(program, "git");
  s.log.push(["git", args, opts]);
  if (args.includes("config")) return { code: 1, stdout: "" }; // no submodules
  if (args.includes("status")) return ok("");
  if (args.includes("--absolute-git-dir")) return ok("/repo/.git/worktrees/topic");
  if (args.includes("--show-toplevel")) return ok("/repo");
  if (args.includes("--git-common-dir")) return ok("/repo/.git");
  if (args[0] === "show-ref") return { code: 1, stdout: "" }; // the branch is new
  if (args.includes("list")) return ok(s.list);
  if (args[0] === "worktree" && args[1] === "add") return ok();
  if (args[0] === "worktree" && args[1] === "remove") { s.liveAtRemove = s.live.size; return s.removal; }
  throw new Error(`unexpected: git ${args.join(" ")}`);
}

globalThis.worktreeTest = {
  exec: async (...a) => exec(...a),
  run: (name, args) => s.log.push(["run", name, args]),
  props: () => s.props,
  spaces: () => [{ id: "worktree-space", name: "topic", machine: null, tabs: [{ id: "tab1" }] }],
  panes: () => [{ pane: "p1", tab: "tab1", terminal: "t1", cwd: "/topic" }],
  terminals: () => [...s.live].map((address) => ({ address, state: "live" })),
  home: () => "/home/u",
  appHome: () => "/home/u/.config/herdr-app",
  readTextFile: async () => JSON.stringify({ worktrees: { directory: "~/git/src/worktrees" } }),
};
const hooks = registerHooks({
  resolve(specifier, context, next) {
    if (!Object.hasOwn(modules, specifier)) return next(specifier, context);
    return { url: `data:text/javascript,${encodeURIComponent(modules[specifier])}`, shortCircuit: true };
  },
});
const { default: Worktree } = await import("./main.js");
hooks.deregister();
delete globalThis.worktreeTest;

const view = () => Object.assign(new Worktree(), { repo: { top: "/topic", main: "/repo", name: "repo", linked: true }, dirty: false, unpushed: [] });
const closes = () => s.log.filter(([kind, name]) => kind === "run" && name === "space.close");
const removals = () => s.log.filter(([kind, args]) => kind === "git" && args[0] === "worktree" && args[1] === "remove");
// The space's programs stop on the first wait, as they do once Herdr has closed the space.
const stopping = { sleep: async () => s.live.clear(), notify() {} };

test("stops the space's programs before git deletes the folder", async () => {
  reset();
  assert.equal(await view().remove(stopping), "");
  const order = s.log.map(([kind, a]) => (kind === "run" ? a : a.slice(0, 2).join(" ")));
  assert.ok(order.indexOf("space.close") < order.indexOf("worktree remove"), "close the space first");
  assert.equal(s.liveAtRemove, 0, "no program of the space may run while git deletes its folder");
  assert.deepEqual(closes()[0][2], { id: "worktree-space", confirmed: true });
});

test("refuses a locked worktree without closing the space", async () => {
  reset({ list: `${UNLOCKED}\nlocked on a USB stick` });
  assert.equal(await view().remove(stopping), "This worktree is locked: on a USB stick");
  assert.deepEqual(closes(), []);
  assert.deepEqual(removals(), []);
});

test("keeps the checkout while the space's programs still run", async (t) => {
  reset();
  let now = 0;
  t.mock.method(Date, "now", () => now);
  const stuck = { sleep: async (ms) => { now += ms * 100; }, notify() {} };
  assert.match(await view().remove(stuck), /haven't stopped yet/);
  assert.deepEqual(removals(), []);
});

test("reports git's refusal instead of closing the dialog as done", async () => {
  reset({ removal: { code: 1, stdout: "", stderr: "fatal: cannot remove" } });
  assert.equal(await view().remove(stopping), "fatal: cannot remove");
});

test("ignores Enter on the repository's main checkout", async () => {
  reset();
  const main = Object.assign(view(), { repo: { top: "/repo", main: "/repo", name: "repo", linked: false }, busy: false });
  await main.work(stopping);
  assert.deepEqual(s.log, []);
});

test("creates checkouts under settings.json worktrees.directory and gives git ten minutes", async () => {
  reset({ props: { space: "worktree-space", action: "new" } });
  let loaded;
  const cx = { spawn: (task) => { loaded = task(cx); }, notify() {}, focus_handle: () => ({ focus() {} }), timer: { after() {} }, sleep: async () => {} };
  const dialog = new Worktree();
  dialog.init({}, cx);
  await loaded;
  dialog.text = "feature/x";
  assert.equal(await dialog.create(), "");
  const [, args, opts] = s.log.find(([kind, a]) => kind === "git" && a[1] === "add");
  assert.deepEqual(args, ["worktree", "add", "-b", "feature/x", "/home/u/git/src/worktrees/repo/feature-x", "HEAD"]);
  assert.equal(opts.timeout, 600_000);
  assert.deepEqual(s.log.at(-1), ["run", "space.new", { folder: "/home/u/git/src/worktrees/repo/feature-x", machine: "", tab: undefined, argv: undefined }]);
});
