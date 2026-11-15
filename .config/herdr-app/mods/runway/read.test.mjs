import assert from "node:assert/strict";
import {registerHooks} from "node:module";
import {test} from "node:test";

// Harness: replace the external "herdr" module with one that forwards to globalThis.__herdr.
const NAMES = ["exec", "readTextFile", "home", "spaces", "panes", "focused", "layout", "knownAgents"];
const LISTS = new Set(["spaces", "panes"]);
const SOURCE = NAMES.map((n) => `export function ${n}(...a) { const f = globalThis.__herdr?.${n};` +
  ` return f ? f(...a) : ${LISTS.has(n) ? "[]" : "undefined"}; }`).join("\n");
registerHooks({
  resolve(specifier, context, next) {
    if (specifier === "herdr") return {url: `data:text/javascript,${encodeURIComponent(SOURCE)}`, shortCircuit: true};
    return next(specifier, context);
  },
});

let generation = 0;
const freshReader = () => import(new URL(`./read.js?case=${++generation}`, import.meta.url));

const at = (on, path) => `${on}|${path}`;
const specflowPaths = (h) => ({
  claude: `${h}/.claude/plugins/cache/buvis-agent-plugins/specflow`,
  codex: `${h}/.codex/plugins/cache/buvis-agent-plugins`,
  kiro: `${h}/.kiro/powers/installed/specflow`,
});

// A fake set of machines: `homes[on]` is each machine's home, `dirs` holds "on|path" folders that exist.
function fakeMachines({localHome, homes = {}, dirs = new Set(), rejects = new Set()}) {
  const calls = [];
  globalThis.__herdr = {
    home: () => localHome,
    exec: async (command, args = [], options = {}) => {
      const on = options?.on ?? null;
      calls.push({command, args, on});
      if (command !== "test") return {code: 0, stdout: `${homes[on]}\n`, stderr: ""};
      const key = at(on, args[1]);
      if (rejects.has(key)) throw new Error(`unreachable: ${key}`);
      return {code: dirs.has(key) ? 0 : 1, stdout: "", stderr: ""};
    },
  };
  return {calls, dirs, testCalls: () => calls.filter((c) => c.command === "test")};
}

const sortedArgs = (calls) => calls.map((c) => JSON.stringify([c.args, c.on])).sort();
const expectedArgs = (on, h) => Object.values(specflowPaths(h)).map((p) => JSON.stringify([["-d", p], on])).sort();

test("specflow_hosts_checks_each_host_folder_in_the_local_home", async () => {
  const a = specflowPaths("/home/alice");
  const fake = fakeMachines({localHome: "/home/alice", dirs: new Set([at(null, a.claude), at(null, a.kiro),
    at(null, "/home/alice/.codex/plugins/cache"), at(null, `${a.kiro}-old`), at(null, `/home/bob${a.codex.slice(11)}`)])});
  const {specflowHosts} = await freshReader();
  assert.deepEqual(await specflowHosts(null), {claude: true, codex: false, kiro: true});
  assert.deepEqual(sortedArgs(fake.testCalls()), expectedArgs(null, "/home/alice"));

  const b = specflowPaths("/Users/bob");
  fakeMachines({localHome: "/Users/bob", dirs: new Set([at(null, b.codex),
    at(null, "/Users/bob/.claude/plugins/cache/buvis-agent-plugins"), at(null, a.claude), at(null, a.kiro)])});
  const second = await freshReader();
  assert.deepEqual(await second.specflowHosts(null), {claude: false, codex: true, kiro: false});
});

test("specflow_hosts_reads_a_remote_machine_in_that_machines_home", async () => {
  const remote = specflowPaths("/srv/carol");
  const local = specflowPaths("/home/alice");
  const fake = fakeMachines({localHome: "/home/alice", homes: {vps: "/srv/carol"},
    dirs: new Set([at("vps", remote.codex), at("vps", remote.kiro), at(null, local.claude), at("vps", local.claude)])});
  const {specflowHosts} = await freshReader();
  assert.deepEqual(await specflowHosts("vps"), {claude: false, codex: true, kiro: true});
  assert.ok(fake.calls.length > 0);
  assert.ok(fake.calls.every((c) => c.on === "vps"), "every exec runs on the remote machine");
  assert.deepEqual(sortedArgs(fake.testCalls()), expectedArgs("vps", "/srv/carol"));
});

test("specflow_hosts_counts_a_rejected_check_as_absent", async () => {
  const a = specflowPaths("/home/alice");
  fakeMachines({localHome: "/home/alice", dirs: new Set([at(null, a.claude), at(null, a.codex)]),
    rejects: new Set([at(null, a.codex)])});
  const {specflowHosts} = await freshReader();
  assert.deepEqual(await specflowHosts(null), {claude: true, codex: false, kiro: false});

  fakeMachines({localHome: "/home/alice", dirs: new Set(Object.values(a).map((p) => at(null, p))),
    rejects: new Set(Object.values(a).map((p) => at(null, p)))});
  const second = await freshReader();
  assert.deepEqual(await second.specflowHosts(null), {claude: false, codex: false, kiro: false});
});

test("specflow_hosts_caches_each_machine_separately", async () => {
  const local = specflowPaths("/home/alice");
  const vps = specflowPaths("/srv/carol");
  const vps2 = specflowPaths("/srv/dave");
  const fake = fakeMachines({localHome: "/home/alice", homes: {"vps": "/srv/carol", "vps-2": "/srv/dave"},
    dirs: new Set([at(null, local.claude), at("vps", vps.codex), at("vps-2", vps2.kiro)])});
  const {specflowHosts} = await freshReader();
  assert.deepEqual(await specflowHosts(null), {claude: true, codex: false, kiro: false});
  const afterLocal = fake.calls.length;

  fake.dirs.add(at(null, local.codex));
  fake.dirs.add(at("vps", vps.kiro));
  assert.deepEqual(await specflowHosts(null), {claude: true, codex: false, kiro: false});
  assert.equal(fake.calls.length, afterLocal, "a cached machine is not checked again");

  assert.deepEqual(await specflowHosts("vps"), {claude: false, codex: true, kiro: true});
  assert.deepEqual(sortedArgs(fake.testCalls().filter((c) => c.on === "vps")), expectedArgs("vps", "/srv/carol"));
  const afterVps = fake.calls.length;
  assert.deepEqual(await specflowHosts("vps-2"), {claude: false, codex: false, kiro: true});
  assert.ok(fake.calls.length > afterVps, "a machine sharing a name prefix is checked on its own");

  fake.dirs.add(at("vps", vps.claude));
  const before = fake.calls.length;
  assert.deepEqual(await specflowHosts("vps"), {claude: false, codex: true, kiro: true});
  assert.equal(fake.calls.length, before);
});

function fakeAgents(result) {
  const calls = [];
  globalThis.__herdr = {
    knownAgents: async (options) => {
      calls.push(options);
      if (result instanceof Error) throw result;
      return result;
    },
  };
  return calls;
}

const agent = (key, name, run, installed = true) => ({key, name, run, installed});

test("installed_agents_keeps_installed_runnable_agents_with_claude_first", async () => {
  const calls = fakeAgents([agent("codex", "Codex", ["codex", "--no-daemon"]), agent("gemini", "Gemini", ["gemini"], false),
    agent("cursor", "Cursor", []), agent("kiro", "Kiro", ["kiro-cli"]), agent("claude", "Claude", ["claude"]),
    agent("amp", "Amp", ["amp"])]);
  const {installedAgents} = await freshReader();
  const list = await installedAgents("vps");
  assert.deepEqual(list.map((a) => a.key), ["claude", "codex", "kiro", "amp"]);
  assert.deepEqual(list[1].run, ["codex", "--no-daemon"]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0]?.on, "vps");

  const local = fakeAgents([agent("kiro", "Kiro", ["kiro-cli"]), agent("claude", "Claude", ["claude"], false),
    agent("opencode", "OpenCode", ["opencode"])]);
  assert.deepEqual((await installedAgents(null)).map((a) => a.key), ["kiro", "opencode"]);
  assert.equal(local[0]?.on ?? null, null);
});

test("installed_agents_puts_only_the_claude_key_first_whatever_the_names", async () => {
  fakeAgents([agent("codex", "Codex", ["codex"]), agent("claude-alt", "Claude", ["claude-alt"]),
    {key: "aider", name: "Aider", installed: true}, agent("kiro", "Kiro", ["kiro-cli"]),
    agent("claude", "My Assistant", ["my-claude", "--fast"]), agent("amp", "Amp", ["amp"])]);
  const {installedAgents} = await freshReader();
  const list = await installedAgents(null);
  assert.deepEqual(list.map((a) => [a.key, a.name]), [["claude", "My Assistant"], ["codex", "Codex"],
    ["claude-alt", "Claude"], ["kiro", "Kiro"], ["amp", "Amp"]]);
  assert.deepEqual(list[0].run, ["my-claude", "--fast"]);
});

test("installed_agents_returns_empty_when_none_are_installed", async () => {
  const {installedAgents} = await freshReader();
  fakeAgents([]);
  assert.deepEqual(await installedAgents(null), []);
  fakeAgents([agent("claude", "Claude", ["claude"], false), agent("cursor", "Cursor", [])]);
  assert.deepEqual(await installedAgents(null), []);
});

test("installed_agents_surfaces_a_failed_agent_listing", async () => {
  const {installedAgents} = await freshReader();
  fakeAgents(new Error("shell check failed"));
  await assert.rejects(installedAgents("vps"), /shell check failed/);
});
