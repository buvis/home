import assert from "node:assert/strict";
import {registerHooks} from "node:module";

// Shared harness for housekeeping*.test.mjs (as in ui.test.mjs): "herdr" forwards every export to
// globalThis.__herdr; "gpui-kit" and "gpui-base" build a plain tree of fluent elements that the tests read and click.
const HERDR = ["exec", "hc", "home", "appHome", "checking", "readTextFile", "writeTextFile", "knownAgents",
  "pickFolder", "playSound", "run", "machines", "spaces", "agents", "panes", "setAgentOrder", "terminals",
  "focused", "layout", "layouts", "commands", "window", "setWindowTitle", "setBadge", "placement", "theme",
  "themes", "fonts", "updates", "presentUpdateNotes", "telemetry", "settings", "keys", "openOverlay",
  "closeOverlay", "notify", "props", "shared", "setShared", "nextCommand", "watchFolder"];
const HERDR_SOURCE = HERDR.map((n) => `export function ${n}(...a) { return globalThis.__herdr.${n}(...a); }`).join("\n");
const KIT_SOURCE = `const k = globalThis.__kit; export const View = k.View; export const div = k.div;
  export const svg = k.svg; export const image = k.image;`;
const BASE_SOURCE = "const k = globalThis.__kit; export const v_flex = k.v_flex; export const h_flex = k.h_flex;";
const MODULES = {herdr: HERDR_SOURCE, "gpui-kit": KIT_SOURCE, "gpui-base": BASE_SOURCE};
registerHooks({
  resolve(specifier, context, next) {
    if (MODULES[specifier]) {
      return {url: `data:text/javascript,${encodeURIComponent(MODULES[specifier])}`, shortCircuit: true};
    }
    // Local imports carry the importer's ?case= query, so every case loads fresh lane/read/model/start modules.
    const resolved = next(specifier, context);
    const query = context.parentURL?.startsWith("file:") ? new URL(context.parentURL).search : "";
    if (query.startsWith("?case=") && specifier.startsWith(".") && resolved.url.startsWith("file:")) {
      return {...resolved, url: `${resolved.url.split("?")[0]}${query}`};
    }
    return resolved;
  },
});

const NODE = Symbol("node");
function element(kind, extra = {}) {
  const node = {kind, ...extra, kids: [], on: {}, calls: []};
  const proxy = new Proxy(node, {
    get(target, name) {
      if (name === NODE) return target;
      if (typeof name === "symbol" || name === "then") return undefined;
      return (...args) => {
        if (name === "child") target.kids.push(args[0]);
        else if (name === "children") target.kids.push(...Array.from(args[0] ?? []));
        else if (name === "when") return args[0] ? args[1](proxy) : (args[2] ? args[2](proxy) : proxy);
        else if (name.startsWith("on_")) target.on[name] = args.at(-1);
        else target.calls.push([name, args]);
        return proxy;
      };
    },
  });
  return proxy;
}

globalThis.__kit = {
  View: class View {},
  div: () => element("div"),
  v_flex: () => element("v_flex"),
  h_flex: () => element("h_flex"),
  svg: (path) => element("svg", {path}),
  image: (path) => element("image", {path}),
};

export const TASK_ERRORS = [];
// Every native callback gets its own cx. Spawned bodies run at once; each timer fires once.
export function makeCx() {
  const spawn = (body) => {
    Promise.resolve().then(() => body(makeCx())).catch((e) => TASK_ERRORS.push(e));
    return {cancel() {}};
  };
  return {
    notify() {}, stop_propagation() {}, propagate() {}, bind_keys: () => 0, open_url() {},
    spawn,
    sleep: async () => {},
    timer: {every: (_ms, handler) => spawn(handler), after: (_ms, handler) => spawn(handler)},
    focus_handle: () => ({focus() {}, is_focused: () => false}),
    theme: () => ({}),
    new(Class, props) { const view = new Class(props); view.init?.(props, makeCx()); return {[NODE]: {view}}; },
  };
}

function expand(value) {
  if (value == null || value === false) return null;
  if (typeof value !== "object" && typeof value !== "function") return String(value);
  const node = value[NODE];
  if (!node) return String(value);
  if (node.view) return expand(node.view.render(makeCx()));
  return {...node, kids: node.kids.map(expand).filter((k) => k !== null)};
}
const textOf = (n) => (n == null ? "" : typeof n === "string" ? n : n.kids.map(textOf).join(" "));
export const walk = (n, out = []) => {
  if (n && typeof n === "object") { out.push(n); n.kids.forEach((k) => walk(k, out)); }
  return out;
};
export const norm = (n) => textOf(n).replace(/\s+/g, " ").trim();

// An in-memory disk per world: path -> text (null for a folder). Only the fake exec touches it.
export const PM = "docs/dev/project-management";
const SECTIONS = ["backlog", "wip", "hold", "done"];
const TITLES = {"00005-old.md": "Old thing", "00010-alpha.md": "Queue alpha", "00011-beta.md": "Queue beta",
  "00012-gamma.md": "Gamma work", "00030-paused.md": "Paused thing", "00020-remote.md": "Remote thing",
  "00021-delta.md": "Delta work", "00031-far.md": "Far thing", "00022-late": "Late idea", "00023-early": "Early idea",
  "00009-cross-host-validation": "cross host validation", "00008-side-quest": "side quest",
  "00042-zeta.md": "Zeta work", "00044-omega.md": "Omega work"};
const ALL_TITLES = Object.values(TITLES);
export const PLUGIN = "/home/u/.claude/plugins/cache/buvis-agent-plugins/specflow";
const CONFIG = ".agents/specflow.json";
const inside = (path, root) => path === root || path?.startsWith(`${root}/`);
export const exists = (fs, p) => [...fs.keys()].some((k) => inside(k, p));
export const ok = (stdout = "") => ({code: 0, stdout, stderr: ""});
export const status = (code, stderr = "") => ({code, stdout: "", stderr});
const kids = (fs, dir) => [...new Set([...fs.keys()].filter((k) => k.startsWith(`${dir}/`))
  .map((k) => k.slice(dir.length + 1).split("/")[0]))].sort();

// A checkout's `specflow` is its validate_spec.py status list and implies the repo config; `config` alone gives
// the repo `.agents/specflow.json` without specs. `texts` overrides a PRD file's text (frontmatter cases).
function seed(checkouts, specflowDirs) {
  const fs = new Map(specflowDirs.map((d) => [d, null]));
  for (const c of checkouts) {
    fs.set(c.path, null);
    for (const s of SECTIONS) {
      for (const f of c[s] ?? []) fs.set(`${c.path}/${PM}/prds/${s}/${f}`, c.texts?.[f] ?? `# ${TITLES[f]}\n\nBody.\n`);
    }
    for (const f of c.intake ?? []) fs.set(`${c.path}/${PM}/intake/new/${f}/idea.md`, `# ${TITLES[f]}\n`);
    if (c.specflow || c.config) fs.set(`${c.path}/${CONFIG}`, JSON.stringify({specsDir: "docs/specs"}));
  }
  return fs;
}
function listing(fs, c) {
  const lines = SECTIONS.flatMap((s) => [`@${s}`, ...kids(fs, `${c.path}/${PM}/prds/${s}`)]);
  return [...lines, "@intake", ...kids(fs, `${c.path}/${PM}/intake/new`), "@pm", "@specflow",
    fs.get(`${c.path}/${CONFIG}`) ?? ""].join("\n");
}
function move(fs, src, dst, noClobber) {
  if (!exists(fs, src)) return status(1, `mv: ${src}: No such file or directory`);
  if (noClobber && exists(fs, dst)) return ok();
  for (const k of [...fs.keys()]) {
    if (inside(k, src)) { fs.set(dst + k.slice(src.length), fs.get(k)); fs.delete(k); }
  }
  return ok();
}
// `git worktree add [-b branch] <path> [base]`: the new checkout holds a copy of main's files.
function addWorktree(w, args) {
  const rest = args.slice(args.indexOf("add") + 1);
  const positional = [];
  let branch = "detached";
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === "-b" || rest[i] === "-B") branch = rest[++i];
    else if (!String(rest[i]).startsWith("-")) positional.push(rest[i]);
  }
  const path = positional[0];
  if (!path || exists(w.fs, path)) return status(128, `fatal: '${path}' already exists`);
  const main = w.checkouts[0];
  for (const [k, v] of [...w.fs]) if (k.startsWith(`${main.path}/`)) w.fs.set(path + k.slice(main.path.length), v);
  w.fs.set(path, null);
  w.checkouts.push({path, branch, specflow: main.specflow, config: main.config});
  return ok(`Preparing worktree (new branch '${branch}')\n`);
}
// Branches: every checkout's plus the fixture's extra `branches`, short or full per the asked format.
function branchList(w, args) {
  const names = [...w.checkouts.map((k) => k.branch), ...w.branches];
  const short = args.some((a) => /refname:(short|lstrip=2)/.test(String(a)));
  return ok(names.map((b) => (short ? b : `refs/heads/${b}`)).join("\n") + "\n");
}
function git(w, args, c) {
  if (!c) return status(128, "fatal: not a git repository");
  const branches = [...w.checkouts.map((k) => k.branch), ...w.branches];
  const named = (a) => branches.includes(String(a).replace(/^refs\/heads\//, ""));
  if (args.includes("worktree") && args.includes("add")) return addWorktree(w, args);
  if (args.includes("worktree") && args.includes("list")) {
    return ok(w.checkouts.map((k) => `worktree ${k.path}\nHEAD ${"a".repeat(40)}\nbranch refs/heads/${k.branch}\n`).join("\n"));
  }
  if (args.includes("for-each-ref")) return branchList(w, args);
  if (args.includes("show-ref") || (args.includes("rev-parse") && args.includes("--verify"))) {
    return status(args.some(named) ? 0 : 1);
  }
  if (args.includes("rev-parse")) {
    return ok(`${args.includes("--git-common-dir") ? `${w.checkouts[0].path}/.git` : c.path}\n`);
  }
  // Never accept a git command the fixture does not model.
  w.unknownGit.push(args);
  return status(128, `fatal: fake git does not handle: ${args.join(" ")}`);
}
// `sh -c 'test -f "$1"'`: the repo config answers from the disk; anything else is the specflow plugin probe.
function shTest(w, paths) {
  const path = paths.at(-1);
  if (path?.endsWith(`/${CONFIG}`)) return status(exists(w.fs, path) ? 0 : 1);
  return status(w.specflowDirs.length ? 0 : 1);
}
// The machine: answers only for the fixture's `on`; the four mutation programs act on the disk.
function handle(w, command, args, options) {
  if ((options?.on ?? null) !== w.on) return command === "test" ? status(1) : status(255, `ssh: wrong machine ${options?.on}`);
  const paths = args.map(String).filter((a) => a.startsWith("/"));
  if (command === "test") return status(exists(w.fs, paths.at(-1)) ? 0 : 1);
  if (command === "mkdir") { for (const p of paths) if (!w.fs.has(p)) w.fs.set(p, null); return ok(); }
  if (command === "rm") { for (const p of paths) for (const k of [...w.fs.keys()]) if (inside(k, p)) w.fs.delete(k); return ok(); }
  if (command === "mv") return move(w.fs, paths.at(-2), paths.at(-1), args.includes("-n"));
  if (command === "sh" && String(args[1]).includes("HOME")) return ok(w.on ? "/srv/home" : w.home);
  if (command === "sh" && args[1] === 'test -f "$1"') return shTest(w, paths);
  const where = args.includes("-C") ? args[args.indexOf("-C") + 1] : options?.cwd;
  const c = w.checkouts.filter((k) => inside(where, k.path)).sort((a, b) => b.path.length - a.path.length)[0] ??
    w.checkouts.find((k) => args.some((a) => String(a).includes(k.path)));
  if (command === "git") return git(w, args, c);
  if (command === "python3" && (c?.specflow || c?.config)) return ok(JSON.stringify({specs: c.specflow ?? []}));
  if (c) return ok(listing(w.fs, c));
  return status(128, `fatal: not handled: ${command} ${args.join(" ")}`);
}

function host(spaces, focusedPane, on, home) {
  const panes = spaces.flatMap((s) => s.tabs.map((t) => ({pane: t.pane, terminal: `${t.id}-term`, tab: t.id,
    title: "sh", cwd: t.cwd, branch: null, status: null, app: null, focused: t.pane === focusedPane, zoomed: false})));
  const focus = panes.find((p) => p.focused);
  const focusSpace = spaces.find((s) => s.tabs.some((t) => t.id === focus.tab));
  return {
    spaces: () => spaces.map((s, index) => ({id: s.id, index, name: s.id, named: false, folder: s.folder,
      machine: s.machine ?? null, branch: null, active: s === focusSpace, status: null,
      tabs: s.tabs.map((t, i) => ({id: t.id, index: i + 1, name: String(i + 1), named: false, active: true,
        status: null, panes: 1, zoomed: false, settled: false}))})),
    panes: () => panes,
    focused: () => ({space: focusSpace.id, tab: focus.tab, pane: focus.pane, terminal: focus.terminal, shown: null,
      agent: null, cwd: focus.cwd}),
    machines: () => [{name: null, layout: "ready"}, ...(on ? [{name: on, layout: "ready"}] : [])],
    home: () => home, appHome: () => `${home}/.config/herdr-app`, checking: () => false,
    theme: () => new Proxy({}, {get: () => "#808080"}), settings: () => ({dark: true}),
    agents: () => [], terminals: () => [], layout: () => PANEL, layouts: () => [], keys: () => [], commands: () => [],
    props: () => ({}), shared: () => undefined, setShared: () => null, setAgentOrder: () => null,
    nextCommand: () => new Promise(() => {}), watchFolder: () => Object.assign(new Promise(() => {}), {cancel() {}}),
    openOverlay: () => "o1", closeOverlay: () => null, setWindowTitle: () => null,
  };
}
const PANEL = {id: "root", children: [{id: "panel", hidden: false, children: [{id: "panel-body", active: "runway",
  children: [{id: "runway", content: {mod: "runway"}}]}]}]};

// `intercept({command, args, options, real, fs})` may answer an exec instead of the machine.
export function world({on = null, checkouts, spaces, focusedPane, agents, specflowDirs = [], branches = [],
  home = "/home/u", intercept}) {
  const w = {on, home, specflowDirs, branches, unknownGit: [], checkouts: checkouts.map((c) => ({...c}))};
  w.fs = seed(w.checkouts, specflowDirs);
  const calls = {exec: [], run: [], notify: [], unknownGit: w.unknownGit};
  globalThis.__herdr = {
    ...host(spaces, focusedPane, on, home),
    exec: async (command, args = [], options = {}) => {
      calls.exec.push({command, args, options});
      const real = () => handle(w, command, args, options);
      return (await intercept?.({command, args, options, real, fs: w.fs})) ?? real();
    },
    readTextFile: async (path, options) => ((options?.on ?? null) === on ? w.fs.get(path) ?? null : null),
    knownAgents: () => agents(),
    run: (name, args) => { calls.run.push([name, args]); return null; },
    notify: (n) => { calls.notify.push(n); return null; },
  };
  return {calls, fs: w.fs};
}

export const settle = async () => { for (let i = 0; i < 40; i++) await new Promise((r) => setImmediate(r)); };
let generation = 0;
export async function openPanel() {
  TASK_ERRORS.length = 0;
  const {default: Runway} = await import(new URL(`./main.js?case=hk${++generation}`, import.meta.url));
  const view = new Runway({});
  view.init?.({}, makeCx());
  await settle();
  return {render: () => expand(view.render(makeCx()))};
}

const agent = (key, name, run) => ({key, name, run, installed: true, icon: null, tint: false, tile: null,
  color: null, shell: false, agent: true});
// A non-default Claude run, so a hardcoded ["claude"] argv fails.
export const CLAUDE = agent("claude", "Claude", ["claude", "--permission-mode", "plan"]);
export const CODEX = agent("codex", "Codex", ["codex", "--no-daemon"]);
export const WITH_CLAUDE = () => Promise.resolve([CODEX, CLAUDE]);
export const NO_CLAUDE = [() => Promise.resolve([]), () => Promise.resolve([CODEX, {...CLAUDE, installed: false}])];
export const spec = (name, hold = null) => ({spec: name, phase: "requirements", state: "valid",
  gates: {design: "closed", tasks: "closed", implementation: "closed"}, nextTask: null, hold});

// This computer: main /work/app (space s1) and worktree /wt/gamma (no space), whose raw pick 00005-old.md
// is done on main, so its card is dropped and no shown card there is the pick.
export const LOCAL = {
  checkouts: [
    {path: "/work/app", branch: "master", backlog: ["00011-beta.md", "00010-alpha.md"], hold: ["00030-paused.md"],
      done: ["00005-old.md"], intake: ["00022-late", "00023-early"]},
    {path: "/wt/gamma", branch: "feature/gamma", wip: ["00005-old.md", "00012-gamma.md"]},
  ],
  spaces: [
    {id: "s2", folder: "/elsewhere", tabs: [{id: "t2", pane: "p2", cwd: "/elsewhere"}]},
    {id: "s1", folder: "/work/app", tabs: [{id: "t1", pane: "p1", cwd: "/work/app/src"}]},
  ],
  focusedPane: "p1",
};
export const SPECS = {...LOCAL, specflowDirs: [PLUGIN], checkouts: [
  {...LOCAL.checkouts[0], specflow: [spec("00009-cross-host-validation")]},
  {...LOCAL.checkouts[1], specflow: [spec("00008-side-quest")]}]};
export const ZED = {checkouts: [{path: "/work/zed", branch: "master", backlog: ["00011-beta.md"]}],
  spaces: [{id: "s5", folder: "/work/zed", tabs: [{id: "t5", pane: "p5", cwd: "/work/zed"}]}], focusedPane: "p5"};
// Another repo and home on this computer, so hardcoded alpha, /work/app or /home/u values fail.
export const ZETA = {home: "/home/zoe",
  checkouts: [{path: "/srv/code/zeta", branch: "master", backlog: ["00042-zeta.md", "00044-omega.md"]}],
  spaces: [{id: "s7", folder: "/srv/code/zeta", tabs: [{id: "t7", pane: "p7", cwd: "/srv/code/zeta"}]}],
  focusedPane: "p7"};
// Machine vps: main /srv/app with a space, worktree /srv/wt/delta.
export const REMOTE = {
  on: "vps",
  checkouts: [
    {path: "/srv/app", branch: "master", backlog: ["00020-remote.md"], hold: ["00031-far.md"]},
    {path: "/srv/wt/delta", branch: "feature/delta", wip: ["00021-delta.md"]},
  ],
  spaces: [{id: "vps/r1", machine: "vps", folder: "/srv/app", tabs: [{id: "vps/rt1", pane: "vps/rp1", cwd: "/srv/app"}]}],
  focusedPane: "vps/rp1",
};

export function cardOf(tree, title) {
  const found = walk(tree).filter((n) => n.on.on_click && norm(n).includes(title) &&
    ALL_TITLES.every((t) => t === title || !norm(n).includes(t)));
  assert.ok(found.length, `card "${title}" is rendered and clickable in: ${norm(tree)}`);
  return found.sort((a, b) => norm(b).length - norm(a).length)[0];
}
export const LANE = "New worktree";
export const LOOP = "Run loop (whole queue)";
export const labelled = (card, label) => walk(card).slice(1).find((n) => norm(n) === label);
export async function click(node, parent) {
  const handler = walk(node).map((n) => n.on.on_click).find(Boolean);
  let stopped = false;
  if (handler) handler({}, {...makeCx(), stop_propagation() { stopped = true; }});
  if (parent && !stopped) parent.on.on_click?.({}, makeCx());
  await settle();
  return Boolean(handler);
}
// Clicks the card's control labelled exactly `label`, bubbling to the card unless stopped.
export async function press(panel, title, label) {
  const card = cardOf(panel.render(), title);
  const button = labelled(card, label);
  assert.ok(button, `${title} offers ${label}: ${norm(card)}`);
  await click(button, card);
}
export async function unfoldParked(panel) {
  const header = walk(panel.render()).filter((n) => n.on.on_click && /Parked \(\d+\)/.test(norm(n)))
    .sort((a, b) => norm(a).length - norm(b).length)[0];
  assert.ok(header, "Parked group header");
  await click(header);
}
// Switches the scope chip to All repos, with gita listing `repos`.
export async function allRepos(panel, repos) {
  const read = globalThis.__herdr.readTextFile;
  globalThis.__herdr.readTextFile = (path, options) => (path === "/home/u/.config/gita/repos.csv"
    ? Promise.resolve(repos) : read(path, options));
  const scope = walk(panel.render()).find((n) => n.calls.some(([name, args]) =>
    name === "id" && args[0] === "runway-scope-chip"));
  assert.ok(scope, "scope control exists");
  await click(scope);
}
export const hasSpinner = (n) => walk(n).some((k) => k.path === "mods/workspace-chrome/spinner.svg");
export const gitCalls = (calls, ...words) =>
  calls.exec.filter((c) => c.command === "git" && words.every((w) => c.args.includes(w)));
export const gitWhere = (c) => (c.args.includes("-C") ? c.args[c.args.indexOf("-C") + 1] : c.options?.cwd);
export const reloads = (calls) => gitCalls(calls, "worktree", "list").length;
export const runsOf = (calls, name) => calls.run.filter(([n]) => n === name).map(([, a]) => a);
export const started = (calls) => calls.run.filter(([, a]) => a && ("argv" in a || "task" in a));
export const mutations = (calls) => calls.exec.filter((e) => ["mv", "rm", "mkdir"].includes(e.command));
export const failed = (n) => n.level === "error" || /did not complete/.test(String(n.body));
export const clean = () => assert.deepEqual(TASK_ERRORS, [], "no task rejected");
