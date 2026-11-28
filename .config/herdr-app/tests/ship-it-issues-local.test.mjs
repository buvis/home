import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { registerHooks } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

const issue = { number: 294, title: "dot run crashes with MarkupError when command output contains [/path]", labels: [] };
let base;
const launches = [];
const git = (cwd, ...args) => spawnSync("git", args, { cwd, encoding: "utf8" });
globalThis.issueWorktreeTest = {
  async exec(command, args, { cwd } = {}) {
    if (command === "sh") return { code: 0, stdout: base };
    assert.equal(command, "git");
    const { status, stdout, stderr } = git(cwd, ...args);
    return { code: status, stdout, stderr };
  },
  appHome: () => base,
  home: () => base,
  readTextFile: async () => JSON.stringify({ worktrees: { directory: "~/git/src/worktrees" } }),
  focused: () => null,
  spaces: () => [],
  panes: () => [],
  run: (...args) => launches.push(args),
  notify: ({ level, body }) => { assert.notEqual(level, "error", body); },
};
const hooks = registerHooks({
  resolve(name, context, next) {
    let stub;
    if (name === "gpui-kit") stub = "export class View {}; export const div = null, svg = null;";
    else if (name === "gpui-base") stub = `
      export const v_flex = null, h_flex = null, Input = null;
      export const InputState = { new({ value }) {
        return { text: value, value() { return this.text }, on(_, fn) { this.submit = fn } };
      } };
    `;
    else if (name === "herdr") {
      const names = "exec run spaces panes appHome knownAgents focused home layout shared setShared notify agents hc window readTextFile theme nextCommand checking".split(" ");
      stub = names.map((name) => `export const ${name} = globalThis.issueWorktreeTest.${name};`).join("\n");
    } else return next(name, context);
    return { url: `data:text/javascript,${encodeURIComponent(stub)}`, shortCircuit: true };
  },
});
const { branchFor, checkoutState, ensureWorktree, issueTree, openWorktree } = await import("../mods/ship-it-issues/issues.js");
const { default: Issues } = await import("../mods/ship-it-issues/main.js");
hooks.deregister();

test("suggests a git-flow branch without cutting off the issue title", () => {
  assert.equal(branchFor(issue), "bugfix/294-dot-run-crashes-with-markuperror-when-command-output-contains-path");
  assert.equal(branchFor({ number: 12, title: "Add Café filters", labels: ["enhancement"] }), "feature/12-add-cafe-filters");
});

function repo(t) {
  base = mkdtempSync(join(realpathSync(tmpdir()), "herdr-issue-"));
  const dir = base;
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const init = git(dir, "init", "-b", "master", "gems");
  assert.equal(init.status, 0, init.stderr);
  const root = join(dir, "gems");
  const commit = git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "Initial");
  assert.equal(commit.status, 0, commit.stderr);
  return root;
}

test("waits for confirmation, uses the edited branch verbatim, and finds it again", async (t) => {
  const root = repo(t);
  assert.deepEqual(await ensureWorktree(root, null, issue), { existing: null });
  assert.equal(git(root, "branch", "--format=%(refname:short)").stdout.trim(), "master");
  await assert.rejects(ensureWorktree(root, null, issue, "bad branch"), /branch name/i);
  await assert.rejects(ensureWorktree(root, null, issue, "master"), /already exists/i);

  const name = "bugfix/dot-markup-output";
  const created = await ensureWorktree(root, null, issue, name);
  assert.equal(created.branch, name);
  assert.equal(created.path, join(base, "git/src/worktrees/gems/bugfix-dot-markup-output"));
  assert.equal(git(created.path, "branch", "--show-current").stdout.trim(), name);
  const state = await checkoutState(created.path, null);
  assert.equal(issueTree(state.trees, issue, state.links), created.path);
  assert.equal((await ensureWorktree(root, null, issue)).path, created.path);

  const removed = git(root, "worktree", "remove", created.path);
  assert.equal(removed.status, 0, removed.stderr);
  assert.deepEqual(await ensureWorktree(root, null, issue), { existing: name });
  const reopened = await ensureWorktree(root, null, issue, name);
  assert.equal(reopened.branch, name);
  assert.equal(git(reopened.path, "branch", "--show-current").stdout.trim(), name);
});

test("offers the older branch as a choice and leaves it alone if a new name is confirmed", async (t) => {
  const root = repo(t);
  const branch = "294-dot-run-crashes-with-markuperror-when-co";
  assert.equal(git(root, "branch", branch).status, 0);
  assert.deepEqual(await ensureWorktree(root, null, issue), { existing: branch });
  assert.equal(git(root, "worktree", "list", "--porcelain").stdout.match(/^worktree /gm).length, 1);
  const opened = await ensureWorktree(root, null, issue, branch);
  assert.equal(opened.branch, branch);
  assert.equal(git(opened.path, "branch", "--show-current").stdout.trim(), branch);
  assert.equal(git(root, "worktree", "remove", opened.path).status, 0);
  const created = await ensureWorktree(root, null, issue, branchFor(issue));
  assert.equal(git(created.path, "branch", "--show-current").stdout.trim(), branchFor(issue));
  assert.equal(git(root, "show-ref", "--verify", `refs/heads/${branch}`).status, 0);
  assert.equal((await ensureWorktree(root, null, issue)).path, created.path);
});

test("starts the chosen agent only after confirming the edited name", async (t) => {
  const root = repo(t);
  const legacy = "294-dot-run-crashes-with-markuperror-when-co";
  assert.equal(git(root, "branch", legacy).status, 0);
  const panel = Object.assign(new Issues(), { root, on: null, expanded: issue.number });
  const agent = { key: "claude", name: "Claude", run: ["claude"] };
  let pending;
  const cx = { notify() {}, timer: { after() {} }, spawn: (task) => { pending = task(cx); } };

  panel.work(issue, agent, cx);
  await pending;
  assert.equal(panel.draft.input.value(), branchFor(issue));
  assert.equal(panel.draft.existing, legacy);
  assert.deepEqual(launches, []);
  const canceled = panel.draft;
  panel.draft = null;
  canceled.input.submit(null, cx);
  assert.deepEqual(launches, []);

  panel.work(issue, agent, cx);
  await pending;
  const input = panel.draft.input;
  input.text = "bugfix/markup-output";
  input.submit(null, cx);
  await pending;
  assert.equal(panel.draft, null);
  assert.equal(launches.length, 1);
  const [[action, args]] = launches;
  assert.equal(action, "space.new");
  assert.deepEqual(args.argv, ["run-agent", "claude"]);
  assert.match(args.task, /on branch bugfix\/markup-output\./);
  assert.equal(git(args.folder, "branch", "--show-current").stdout.trim(), "bugfix/markup-output");
});

test("launches with one shim and preserves the configured agent arguments", () => {
  const path = "/worktree";
  for (const [agent, argv] of [
    [{ key: "codex", name: "Codex", run: ["run-agent", "codex", "--model", "configured"] },
      ["run-agent", "codex", "--no-daemon", "--model", "configured"]],
    [{ key: "copilot", name: "Copilot", run: ["/bin/run-agent", "copilot", "-i"] },
      ["/bin/run-agent", "copilot", "-i"]],
    [{ key: "pi", name: "Pi", run: ["pi", "--model", "configured"] },
      ["run-agent", "pi", "--model", "configured"]],
  ]) {
    openWorktree(path, "mac", {}, issue, "bugfix/dot", agent);
    assert.deepEqual(launches.pop()[1].argv, argv);
  }
});
