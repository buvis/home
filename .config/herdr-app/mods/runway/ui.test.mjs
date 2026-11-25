import assert from "node:assert/strict";
import {registerHooks} from "node:module";
import {test} from "node:test";

// Harness: "herdr" forwards every export to globalThis.__herdr; "gpui-kit" and "gpui-base" build a
// plain tree of fluent elements that the tests read and click.
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
    // Local imports carry the importer's ?case= query, so every case loads fresh read.js/model.js/start.js.
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

const TASK_ERRORS = [];
// Every native callback gets its own cx. Spawned bodies run at once; each timer fires once.
function makeCx() {
  const spawn = (body) => {
    Promise.resolve().then(() => body(makeCx())).catch((e) => TASK_ERRORS.push(e));
    return {cancel() {}};
  };
  const cx = {
    notify() {}, stop_propagation() {}, propagate() {}, bind_keys: () => 0, open_url() {},
    spawn,
    sleep: async () => {},
    timer: {every: (_ms, handler) => spawn(handler), after: (_ms, handler) => spawn(handler)},
    focus_handle: () => ({focus() {}, is_focused: () => false}),
    theme: () => ({}),
    new(Class, props) { const view = new Class(props); view.init?.(props, makeCx()); return {[NODE]: {view}}; },
  };
  return cx;
}

// Expand a rendered value into plain nodes, rendering nested views.
function expand(value) {
  if (value == null || value === false) return null;
  if (typeof value !== "object" && typeof value !== "function") return String(value);
  const node = value[NODE];
  if (!node) return String(value);
  if (node.view) return expand(node.view.render(makeCx()));
  return {...node, kids: node.kids.map(expand).filter((k) => k !== null)};
}
const textOf = (n) => (n == null ? "" : typeof n === "string" ? n : n.kids.map(textOf).join(" "));
const walk = (n, out = []) => {
  if (n && typeof n === "object") { out.push(n); n.kids.forEach((k) => walk(k, out)); }
  return out;
};

// A fake world: checkouts per machine (the first is the repo's main), spaces, and the focused pane.
const SECTIONS = ["backlog", "wip", "hold", "done", "intake"];
function listing(c) {
  const lines = SECTIONS.flatMap((s) => [`@${s}`, ...(c[s] ?? [])]);
  return [...lines, "@pm", "@specflow", c.specflow ? JSON.stringify({specsDir: "docs/specs"}) : ""].join("\n");
}
const inside = (path, root) => path === root || path?.startsWith(`${root}/`);
const PM = "docs/dev/project-management";
const TITLES = {"00005-old.md": "Old thing", "00010-alpha.md": "Queue alpha", "00011-beta.md": "Queue beta",
  "00012-gamma.md": "Gamma work", "00030-paused.md": "Paused thing", "00040-done.md": "Done thing",
  "00022-late": "Late idea", "00020-remote.md": "Remote thing", "00021-delta.md": "Delta work",
  "00009-cross-host-validation": "cross host validation"};
// Every file the reader may ask for: PRD texts, intake ideas and autopilot state; anything else is null.
function filesOf(checkouts) {
  const files = {};
  for (const c of checkouts) {
    for (const s of ["backlog", "wip", "hold", "done"]) {
      for (const f of c[s] ?? []) files[`${c.path}/${PM}/prds/${s}/${f}`] = `# ${TITLES[f]}\n\nBody.\n`;
    }
    for (const f of c.intake ?? []) files[`${c.path}/${PM}/intake/new/${f}/idea.md`] = `# ${TITLES[f]}\n`;
    if (c.state) files[`${c.path}/${PM}/autopilot/state.json`] = JSON.stringify(c.state);
  }
  return files;
}
const PANEL = {id: "root", children: [{id: "panel", hidden: false, children: [{id: "panel-body", active: "runway",
  children: [{id: "runway", content: {mod: "runway"}}]}]}]};
const DIM = "#111111";
const MUTED = "#222222";

// `specflowDirs`: folders `test -d` finds; a checkout's `specflow` list is its validate_spec.py status.
function world({on = null, checkouts, spaces, focusedPane, agents, specflowDirs = []}) {
  const calls = {exec: [], run: [], knownAgents: [], readTextFile: []};
  const files = filesOf(checkouts);
  // Reads and git calls answer only on the fixture's machine, so dropped `on` plumbing fails.
  const here = (options) => (options?.on ?? null) === on;
  const owner = (where) => checkouts.filter((c) => inside(where, c.path)).sort((a, b) => b.path.length - a.path.length)[0];
  const ok = (stdout) => ({code: 0, stdout, stderr: ""});
  const panes = spaces.flatMap((s) => s.tabs.map((t) => ({pane: t.pane, terminal: `${t.id}-term`, tab: t.id,
    title: "sh", cwd: t.cwd, branch: null, status: null, app: null, focused: t.pane === focusedPane, zoomed: false})));
  const focus = panes.find((p) => p.focused);
  const focusSpace = spaces.find((s) => s.tabs.some((t) => t.id === focus.tab));
  globalThis.__herdr = {
    exec: async (command, args = [], options = {}) => {
      calls.exec.push({command, args, options});
      const where = args.includes("-C") ? args[args.indexOf("-C") + 1] : options.cwd;
      if (command === "test") return {code: specflowDirs.includes(args[1]) ? 0 : 1, stdout: "", stderr: ""};
      if (!here(options)) return {code: 255, stdout: "", stderr: `ssh: wrong machine ${options?.on}`};
      if (command === "sh" && String(args[1]).includes("HOME")) return ok(on ? "/srv/home" : "/home/u");
      if (command === "sh" && args[1] === 'test -f "$1"') return {code: specflowDirs.length ? 0 : 1, stdout: "", stderr: ""};
      const c = owner(where) ?? checkouts.find((k) => args.some((a) => String(a).includes(k.path)));
      if (command === "python3" && c?.specflow) return ok(JSON.stringify({specs: c.specflow}));
      if (command === "git" && args.includes("rev-parse") && c) {
        return ok(`${args.includes("--git-common-dir") ? `${checkouts[0].path}/.git` : c.path}\n`);
      }
      if (command === "git" && args.includes("worktree") && c) {
        return ok(checkouts.map((k) => `worktree ${k.path}\nHEAD ${"a".repeat(40)}\nbranch refs/heads/${k.branch}\n`).join("\n"));
      }
      if (c && command !== "git") return ok(listing(c));
      return {code: 128, stdout: "", stderr: `fatal: not handled: ${command} ${args.join(" ")}`};
    },
    readTextFile: async (path, options) => {
      calls.readTextFile.push({path, options});
      return here(options) ? files[path] ?? null : null;
    },
    knownAgents: (options) => { calls.knownAgents.push(options); return agents(); },
    run: (name, args) => { calls.run.push([name, args]); return null; },
    spaces: () => spaces.map((s, index) => ({id: s.id, index, name: s.id, named: false, folder: s.folder,
      machine: s.machine ?? null, branch: null, active: s === focusSpace, status: null,
      tabs: s.tabs.map((t, i) => ({id: t.id, index: i + 1, name: String(i + 1), named: false, active: true,
        status: null, panes: 1, zoomed: false, settled: false}))})),
    panes: () => panes,
    focused: () => ({space: focusSpace.id, tab: focus.tab, pane: focus.pane, terminal: focus.terminal, shown: null,
      agent: null, cwd: focus.cwd}),
    machines: () => [{name: null, layout: "ready"}, ...(on ? [{name: on, layout: "ready"}] : [])],
    home: () => "/home/u", appHome: () => "/home/u/.config/herdr-app", checking: () => false,
    theme: () => new Proxy({}, {get: (_t, k) => (k === "dim" ? DIM : k === "muted" ? MUTED : "#808080")}),
    settings: () => ({dark: true}),
    agents: () => [], terminals: () => [],
    layout: () => PANEL, layouts: () => [], keys: () => [], commands: () => [],
    props: () => ({}), shared: () => undefined, setShared: () => null, setAgentOrder: () => null,
    nextCommand: () => new Promise(() => {}), watchFolder: () => Object.assign(new Promise(() => {}), {cancel() {}}),
    notify: () => null, openOverlay: () => "o1", closeOverlay: () => null, setWindowTitle: () => null,
    window: () => ({platform: "macos", active: true, visible: true}),
  };
  return calls;
}

const settle = async () => { for (let i = 0; i < 40; i++) await new Promise((r) => setImmediate(r)); };
let generation = 0;
async function openPanel() {
  TASK_ERRORS.length = 0;
  const {default: Runway} = await import(new URL(`./main.js?case=${++generation}`, import.meta.url));
  const view = new Runway({});
  view.init?.({}, makeCx());
  await settle();
  return {render: () => expand(view.render(makeCx()))};
}

const agent = (key, name, run) => ({key, name, run, installed: true, icon: null, tint: false, tile: null,
  color: null, shell: false, agent: true});
const CLAUDE = agent("claude", "Claude", ["claude"]);
const CODEX = agent("codex", "Codex", ["codex", "--no-daemon"]);
const GEMINI = agent("gemini", "Gemini", ["gemini"]);

// This computer: main /work/app with a space; worktree /wt/gamma without one, whose lowest wip name
// (00005-old.md) is done on main: its card is dropped, yet autopilot there still picks it.
// 00040-done.md is finished per state: no label.
const LOCAL = {
  checkouts: [
    {path: "/work/app", branch: "master", backlog: ["00011-beta.md", "00010-alpha.md"], hold: ["00030-paused.md"],
      done: ["00005-old.md"], intake: ["00022-late"]},
    {path: "/wt/gamma", branch: "feature/gamma", wip: ["00005-old.md", "00012-gamma.md", "00040-done.md"],
      state: {prd: "00040-done.md", phase: "done"}},
  ],
  spaces: [
    {id: "s2", folder: "/elsewhere", tabs: [{id: "t2", pane: "p2", cwd: "/elsewhere"}]},
    {id: "s1", folder: "/work/app", tabs: [{id: "t1", pane: "p1", cwd: "/work/app/src"}]},
  ],
  focusedPane: "p1",
};

// Machine vps: main /srv/app with a space there; worktree /srv/wt/delta without one.
const REMOTE = {
  on: "vps",
  checkouts: [
    {path: "/srv/app", branch: "master", backlog: ["00020-remote.md"]},
    {path: "/srv/wt/delta", branch: "feature/delta", wip: ["00021-delta.md"]},
  ],
  spaces: [{id: "vps/r1", machine: "vps", folder: "/srv/app",
    tabs: [{id: "vps/rt1", pane: "vps/rp1", cwd: "/srv/app"}]}],
  focusedPane: "vps/rp1",
};

const ALL_TITLES = Object.values(TITLES);
const norm = (n) => textOf(n).replace(/\s+/g, " ").trim();
// A card: the largest clickable node holding its title and no other card's title.
function cardOf(tree, title) {
  const found = walk(tree).filter((n) => n.on.on_click && norm(n).includes(title) &&
    ALL_TITLES.every((t) => t === title || !norm(n).includes(t)));
  assert.ok(found.length, `card "${title}" is rendered and clickable in: ${norm(tree)}`);
  return found.sort((a, b) => norm(b).length - norm(a).length)[0];
}
// A button: the outermost node inside the card whose text is the agent name, maybe plus "ungated".
const buttonRe = (name) => new RegExp(`^${name}(\\W+ungated)?$`);
const buttonOf = (card, name) => walk(card).slice(1).find((n) => buttonRe(name).test(norm(n)));
const agentButtons = (card) => [CLAUDE, CODEX, GEMINI, KIRO].map((a) => a.name).filter((n) => buttonOf(card, n));
// Clicks `node`; with `parent` (the card) given, the click bubbles to it unless stopped.
async function click(node, parent) {
  const handler = walk(node).map((n) => n.on.on_click).find(Boolean);
  let stopped = false;
  if (handler) handler({}, {...makeCx(), stop_propagation() { stopped = true; }});
  if (parent && !stopped) parent.on.on_click?.({}, makeCx());
  await settle();
  return Boolean(handler);
}
const hasSpinner = (n) => walk(n).some((k) => k.path === "mods/workspace-chrome/spinner.svg");
const dimmed = (n) => walk(n).some((k) => k.calls.some(([m, a]) =>
  (m === "opacity" && a[0] < 1) || (m === "text_color" && (a[0] === DIM || a[0] === MUTED))));
const KIRO = agent("kiro", "Kiro", ["kiro-cli", "chat"]);
const AGENTS = () => Promise.resolve([CODEX, GEMINI, {...KIRO, installed: false}, {...CLAUDE, run: null},
  CLAUDE, agent("copilot", "Copilot", null)]);
const clean = () => assert.deepEqual(TASK_ERRORS, [], "no task rejected");
const plain = (number, title, rel, stage, label) => `Work on PRD ${number} "${title}" in ${rel}. Its stage is ` +
  `${stage}. Do only this next stage: ${label}. Follow the repository's workflow documents. Stop when that stage is done.`;

test("labelled card shows its stage then one button per installed agent, Claude first, ungated marked", async () => {
  const calls = world({...LOCAL, agents: AGENTS});
  const panel = await openPanel();
  const tree = panel.render();
  const alpha = cardOf(tree, "Queue alpha");
  const text = norm(alpha);
  assert.match(text, /Start build/);
  assert.deepEqual(agentButtons(alpha), ["Claude", "Codex", "Gemini"], "not installed or no run: no button");
  assert.ok(text.indexOf("Start build") < text.indexOf("Claude"), "label before the buttons");
  assert.ok(text.indexOf("Claude") < text.indexOf("Codex") && text.indexOf("Claude") < text.indexOf("Gemini"));
  assert.equal(norm(buttonOf(alpha, "Claude")), "Claude");
  assert.equal(norm(buttonOf(alpha, "Codex")), "Codex", "local Codex is gated");
  assert.match(norm(buttonOf(alpha, "Gemini")), /^Gemini\W+ungated$/);
  // The other checkout's card gets its own row from the same, single discovery.
  assert.deepEqual(agentButtons(cardOf(tree, "Gamma work")), ["Claude", "Codex", "Gemini"]);
  assert.equal(calls.knownAgents.length, 1, "agents are listed once for this machine");
  assert.equal(calls.knownAgents[0]?.on ?? null, null);
  clean();
});

test("off-pick card dims gated buttons, shows the tip last and starts nothing on click", async () => {
  const calls = world({...LOCAL, agents: AGENTS});
  const panel = await openPanel();
  const beta = cardOf(panel.render(), "Queue beta");
  const text = norm(beta);
  const tip = "autopilot 0.10.0 starts 00010-alpha.md first";
  assert.match(text, /Start build/);
  assert.ok(text.endsWith(tip), `tip is the row's last line: ${text}`);
  assert.ok(text.indexOf("Gemini") < text.indexOf(tip));
  for (const name of ["Claude", "Codex"]) {
    const button = buttonOf(beta, name);
    assert.ok(button, `${name} button shown`);
    assert.ok(dimmed(button), `${name} is dimmed`);
    await click(button, beta);
    assert.deepEqual(calls.run, [], `disabled ${name} runs nothing, not even the card's open`);
  }
  assert.ok(!dimmed(buttonOf(beta, "Gemini")), "ungated Gemini stays enabled");
  // The pick itself carries no tip.
  assert.ok(!norm(cardOf(panel.render(), "Queue alpha")).includes(tip));
  clean();
});

test("idea, parked and finished cards get no stage buttons", async () => {
  world({...LOCAL, agents: AGENTS});
  const panel = await openPanel();
  // Parked is folded: unfold it through its header.
  const header = walk(panel.render()).filter((n) => n.on.on_click && /Parked \(1\)/.test(norm(n)))
    .sort((a, b) => norm(a).length - norm(b).length)[0];
  assert.ok(header, "Parked group header");
  await click(header);
  const tree = panel.render();
  for (const title of ["Late idea", "Paused thing", "Done thing"]) {
    const card = cardOf(tree, title);
    assert.deepEqual(agentButtons(card), [], `${title}: no agent buttons`);
    assert.ok(!hasSpinner(card), `${title}: no busy ring`);
    assert.doesNotMatch(norm(card), /Start build|Resume|Finish|Could not list agents/);
  }
  // Their absence counts only once the labelled card shows the loaded agents.
  assert.deepEqual(agentButtons(cardOf(tree, "Queue alpha")), ["Claude", "Codex", "Gemini"], "agents loaded");
  clean();
});

test("agent row shows the shared busy ring while listing, then Could not list agents on failure", async () => {
  let fail;
  world({...LOCAL, agents: () => new Promise((_ok, no) => { fail = no; })});
  const panel = await openPanel();
  const loading = cardOf(panel.render(), "Queue alpha");
  assert.match(norm(loading), /Start build/);
  assert.ok(hasSpinner(loading), "busy ring while knownAgents is pending");
  assert.deepEqual(agentButtons(loading), []);
  assert.ok(fail, "knownAgents was asked");
  fail(new Error("shell exited 1"));
  await settle();
  const failed = cardOf(panel.render(), "Queue alpha");
  assert.match(norm(failed), /Could not list agents/);
  assert.ok(!hasSpinner(failed), "ring gone after the failure");
  assert.deepEqual(agentButtons(failed), [], "no buttons remain");
  clean();
});

test("button in a checkout with a space selects it and opens the agent tab there", async () => {
  const calls = world({...LOCAL, agents: AGENTS});
  const panel = await openPanel();
  await click(buttonOf(cardOf(panel.render(), "Queue alpha"), "Claude"));
  assert.deepEqual(calls.run, [
    ["space.select", {id: "s1"}],
    ["tab.new", {space: "s1", folder: "/work/app", name: "00010 Claude", argv: ["claude"],
      task: "/autopilot:run-autopilot 00010-alpha.md"}],
  ]);
  calls.run.length = 0;
  // Local Codex runs autocodex and sends no task at all.
  await click(buttonOf(cardOf(panel.render(), "Queue alpha"), "Codex"));
  assert.deepEqual(calls.run, [
    ["space.select", {id: "s1"}],
    ["tab.new", {space: "s1", folder: "/work/app", name: "00010 Codex", argv: ["autocodex", "--once"]}],
  ]);
  assert.ok(!("task" in calls.run[1][1]), "task key left out");
  clean();
});

test("stale done-on-main wip name still blocks gated starts, because autopilot reads the raw wip folder", async () => {
  const calls = world({...LOCAL, agents: AGENTS});
  const panel = await openPanel();
  const gamma = cardOf(panel.render(), "Gamma work");
  assert.match(norm(gamma), /Start build/);
  assert.match(norm(gamma), /autopilot 0\.10\.0 starts 00005-old\.md first/);
  assert.ok(dimmed(buttonOf(gamma, "Claude")), "Claude dimmed: autopilot in /wt/gamma enters 00005-old.md");
  await click(buttonOf(gamma, "Claude"), gamma);
  assert.deepEqual(calls.run, [], "a gated start off the raw pick runs nothing");
  await click(buttonOf(gamma, "Gemini"), gamma);
  assert.deepEqual(calls.run, [["space.new", {folder: "/wt/gamma", tab: "00012 Gemini", machine: "", argv: ["gemini"],
    task: plain("00012", "Gamma work", `${PM}/prds/wip/00012-gamma.md`, "wip", "Start build")}]]);
  assert.equal(calls.run[0][1].machine, "", "explicitly target this computer");
  clean();
});

test("remote cards list agents on their machine and start there, Codex ungated", async () => {
  const calls = world({...REMOTE, agents: () => Promise.resolve([CODEX, CLAUDE])});
  const panel = await openPanel();
  const main = cardOf(panel.render(), "Remote thing");
  assert.match(norm(buttonOf(main, "Codex")), /^Codex\W+ungated$/);
  await click(buttonOf(main, "Codex"));
  const rel = `${PM}/prds/backlog/00020-remote.md`;
  assert.deepEqual(calls.run, [
    ["space.select", {id: "vps/r1"}],
    ["tab.new", {space: "vps/r1", folder: "/srv/app", name: "00020 Codex", argv: ["codex", "--no-daemon"],
      task: plain("00020", "Remote thing", rel, "backlog", "Start build")}],
  ]);
  calls.run.length = 0;
  await click(buttonOf(cardOf(panel.render(), "Delta work"), "Claude"));
  assert.deepEqual(calls.run, [["space.new", {folder: "/srv/wt/delta", tab: "00021 Claude", machine: "vps",
    argv: ["claude"], task: "/autopilot:run-autopilot 00021-delta.md"}]]);
  assert.deepEqual(calls.knownAgents.map((o) => o?.on), ["vps"], "one listing, on vps");
  clean();
});

test("All repos starts a local card locally while a remote space is focused", async () => {
  const calls = world({...LOCAL, spaces: REMOTE.spaces, focusedPane: REMOTE.focusedPane, agents: AGENTS});
  const read = globalThis.__herdr.readTextFile;
  globalThis.__herdr.readTextFile = (path, options) => path === "/home/u/.config/gita/repos.csv"
    ? Promise.resolve("/work/app,app\n") : read(path, options);
  const panel = await openPanel();
  const scope = walk(panel.render()).find((n) => n.calls.some(([name, args]) =>
    name === "id" && args[0] === "runway-scope-chip"));
  assert.ok(scope, "scope control exists");
  await click(scope);
  const alpha = cardOf(panel.render(), "Queue alpha");
  assert.deepEqual(agentButtons(alpha), ["Claude", "Codex", "Gemini"]);
  assert.equal(globalThis.__herdr.spaces().find((s) => s.active).machine, "vps");
  assert.deepEqual(calls.knownAgents, [{on: null}], "All repos discovers local agents");
  await click(buttonOf(alpha, "Claude"));
  assert.deepEqual(calls.run, [["space.new", {folder: "/work/app", tab: "00010 Claude", machine: "",
    argv: ["claude"], task: "/autopilot:run-autopilot 00010-alpha.md"}]]);
  clean();
});

test("spec card starts specflow only where it is installed, and tells which agent lacks it", async () => {
  const spec = {spec: "00009-cross-host-validation", phase: "requirements", state: "valid",
    gates: {design: "closed", tasks: "closed", implementation: "closed"}, nextTask: null, hold: null};
  const calls = world({...LOCAL, checkouts: [{...LOCAL.checkouts[0], specflow: [spec]}], agents: AGENTS,
    specflowDirs: ["/home/u/.claude/plugins/cache/buvis-agent-plugins/specflow"]});
  const panel = await openPanel();
  const card = cardOf(panel.render(), "cross host validation");
  const text = norm(card);
  assert.match(text, /Continue: design gate/);
  assert.ok(text.endsWith("specflow is not installed for Codex"), `tip is the row's last line: ${text}`);
  assert.ok(!dimmed(buttonOf(card, "Claude")), "Claude has specflow");
  assert.ok(dimmed(buttonOf(card, "Codex")), "Codex lacks specflow");
  assert.match(norm(buttonOf(card, "Gemini")), /ungated$/);
  await click(buttonOf(card, "Codex"), card);
  assert.deepEqual(calls.run, [], "a start without specflow runs nothing");
  await click(buttonOf(card, "Claude"), card);
  assert.deepEqual(calls.run, [
    ["space.select", {id: "s1"}],
    ["tab.new", {space: "s1", folder: "/work/app", name: "00009 Claude", argv: ["claude"],
      task: "/specflow:spec-workflow Continue spec 00009-cross-host-validation"}],
  ]);
  clean();
});

