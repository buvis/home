// The repo reader: git, the PRD folders, autopilot state and specflow status, per checkout.
import { exec, readTextFile, home, spaces, panes, focused, layout, knownAgents } from "herdr";
import { parseWorktrees, parseListing, newestVersion } from "./model.js";

// Reads write nothing under .git (no index refresh or lock, no fsmonitor cookie):
// a folder watch would see it, and every refresh would start the next one.
const READ = ["--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "diff.autoRefreshIndex=false"];

const PM = "docs/dev/project-management";
// `@specflow` goes last: parseListing takes every line after it as the JSON.
const SCRIPT = [
  `for b in backlog wip hold done; do echo "@$b"; ls -1 ${PM}/prds/$b 2>/dev/null; done`,
  `echo @intake; ls -1 ${PM}/intake/new 2>/dev/null`,
  `if [ -d ${PM} ]; then echo @pm; fi`,
  "echo @specflow; cat .agents/specflow.json 2>/dev/null",
].join("\n");
const TAIL = "skills/spec-workflow/scripts/validate_spec.py";

const json = async (text) => { try { return JSON.parse(await text); } catch { return null; } };

// The machine's validate_spec.py: newest plugin cache version, else the source checkout.
async function specflowScript(on) {
  const h = on ? (await exec("sh", ["-c", 'printf %s "$HOME"'], { on })).stdout : home();
  const cache = `${h}/.claude/plugins/cache/buvis-agent-plugins/specflow`;
  const ls = await exec("ls", ["-1", cache], { on }).catch(() => null);
  const v = ls?.code === 0 ? newestVersion(ls.stdout.split("\n")) : null;
  for (const p of [v && `${cache}/${v}/${TAIL}`, `${h}/git/src/github.com/buvis/agent-plugins/plugins/specflow/${TAIL}`]) {
    if (p && (await exec("sh", ["-c", 'test -f "$1"', "sh", p], { on })).code === 0) return p;
  }
  return null;
}

async function checkout(t, l, on, script) {
  const dir = `${t.path}/${PM}/autopilot`;
  const runs = script && l.specflow?.trim() && (t.main || t.spec || t.branch?.startsWith("feature/specflow-"));
  // python3 exits 1 when specs have problems; its stdout still holds the JSON.
  const [state, wave, specs, conf] = await Promise.all([
    json(readTextFile(`${dir}/state.json`, { on })),
    json(readTextFile(`${dir}/wave.json`, { on })),
    runs ? json(exec("python3", [script, "status", "--json"], { cwd: t.path, on }).then((r) => r.stdout)) : null,
    json(l.specflow),
  ]);
  const { backlog, wip, hold, done } = l;
  return { path: t.path, branch: t.branch, main: t.main, spec: t.spec, buckets: { backlog, wip, hold, done }, intake: l.intake,
    state, wave, specs, specsDir: conf?.specsDir ?? null };
}

export async function snapshot(cwd, on) {
  const top = await exec("git", [...READ, "rev-parse", "--show-toplevel"], { cwd, on }).catch(() => null);
  if (top?.code !== 0) return null;
  const wl = await exec("git", [...READ, "worktree", "list", "--porcelain"], { cwd, on });
  if (wl.code !== 0) throw new Error(wl.stderr.trim() || "git worktree list failed");
  const refs = await exec("git", [...READ, "for-each-ref", "--format=%(refname:short)", "refs/heads"], { cwd, on });
  const trees = parseWorktrees(wl.stdout);
  const root = trees[0].path;
  const base = { root, repo: root.split("/").pop(), on, branches: refs.stdout.split("\n").filter(Boolean) };
  // A rejected exec (folder gone) skips that checkout.
  const outs = await Promise.all(trees.map((t) => exec("sh", ["-c", SCRIPT], { cwd: t.path, on }).then((r) => r.stdout, () => null)));
  const found = trees.map((t, i) => outs[i] !== null && { t, out: outs[i] }).filter(Boolean);
  if (!found.some(({ out }) => out.split("\n").includes("@pm"))) return { ...base, checkouts: [], specflow: "none" };
  const listed = found.map(({ t, out }) => ({ t, l: parseListing(out) }));
  const wanted = listed.some(({ l }) => l.specflow?.trim());
  const script = wanted ? await specflowScript(on) : null;
  const links = new Map();
  if (script && listed.some(({ t, l }) => !t.main && t.branch && l.specflow?.trim())) {
    const config = await exec("git", [...READ, "config", "--local", "--null", "--get-regexp", "^branch\\..*\\.herdr-spec$"], { cwd, on });
    if (config.code !== 0 && config.code !== 1) throw new Error(config.stderr.trim() || "Could not read spec branch links");
    for (const item of config.stdout.split("\0")) {
      const match = /^branch\.(.+)\.herdr-spec\n(.+)$/.exec(item);
      if (match) links.set(match[1], match[2]);
    }
  }
  const checkouts = await Promise.all(listed.map(({ t, l }) => checkout({ ...t, spec: links.get(t.branch) }, l, on, script)));
  return { ...base, checkouts, specflow: !wanted ? "none" : script ? "ok" : "missing" };
}

// Absolute file paths -> { [file]: text }; a missing file reads as "".
export async function texts(files, on) {
  const read = await Promise.all(files.map((f) => readTextFile(f, { on }).catch(() => null)));
  return Object.fromEntries(files.map((f, i) => [f, read[i] ?? ""]));
}

export async function repos() {
  const text = await readTextFile(`${home()}/.config/gita/repos.csv`);
  return (text ?? "").split("\n").filter((l) => l.trim()).map((l) => l.split(",")[0]);
}

// The focused pane's live folder and the machine it is on. A mod pane has no
// folder, so the last terminal's stays (`last`).
export function location(last) {
  const space = spaces().find((s) => s.active), f = focused();
  const pane = f?.pane ? panes().find((p) => p.pane === f.pane) : null;
  if (pane && !pane.terminal && last && last.space === space?.id) return last;
  const on = f?.pane === null ? (f.terminal?.includes("/") ? f.terminal.split("/")[0] : null) : space?.machine ?? null;
  // A mod pane focused first in this space: the tab's first terminal, not the space's starting folder.
  const sibling = pane && !pane.terminal ? panes().find((p) => p.tab === pane.tab && p.terminal && p.cwd) : null;
  return { cwd: pane?.cwd || sibling?.cwd || f?.cwd || space?.folder || null, on, space: space?.id ?? null };
}

function findNode(node, id) {
  if (node?.id === id) return node;
  for (const child of node?.children ?? []) { const found = findNode(child, id); if (found) return found; }
  return null;
}

export function panelShown(id) {
  const root = layout(), panel = findNode(root, "panel"), body = findNode(root, "panel-body");
  return Boolean(panel && !panel.hidden && body?.active === id);
}

export function places(on) {
  const ps = panes();
  return spaces().filter((s) => (s.machine ?? null) === (on ?? null)).map((s) => {
    const tabs = new Set((s.tabs ?? []).map((t) => t.id));
    return { s, at: ps.find((p) => tabs.has(p.tab) && p.cwd)?.cwd || s.folder || null };
  });
}

export async function installedAgents(on) {
  const all = (await knownAgents({ on })).filter((a) => a.installed && a.run?.length);
  return all.sort((a, b) => (b.key === "claude") - (a.key === "claude"));
}

// Which hosts have specflow installed on a machine, cached per machine until reload.
const hostsCache = new Map();
export function specflowHosts(on) {
  if (!hostsCache.has(on)) hostsCache.set(on, (async () => {
    const h = on
      ? await exec("sh", ["-c", 'printf %s "$HOME"'], { on }).then((r) => (r.code === 0 ? r.stdout : ""), () => "")
      : home();
    const dirs = { claude: `${h}/.claude/plugins/cache/buvis-agent-plugins/specflow`,
      codex: `${h}/.codex/plugins/cache/buvis-agent-plugins`, kiro: `${h}/.kiro/powers/installed/specflow` };
    const found = await Promise.all(Object.values(dirs).map((d) =>
      h ? exec("test", ["-d", d], { on }).then((r) => r.code === 0, () => false) : false));
    return Object.fromEntries(Object.keys(dirs).map((k, i) => [k, found[i]]));
  })());
  return hostsCache.get(on);
}

export function spaceAt(path, where, paths = []) {
  if (!path) return undefined;
  const inside = (p, dir) => p === dir || p?.startsWith(dir + "/");
  return where.find(({ at }) => inside(at, path) && !paths.some((c) => c.length > path.length && inside(at, c)))?.s;
}
