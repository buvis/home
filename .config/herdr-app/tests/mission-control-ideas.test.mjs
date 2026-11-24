import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { paneTitle } from "../mods/my-pane/task-title.js";
import { contextRemaining } from "../mods/my-agents/context.js";
import { closedItems, loadClosed, rememberClosed, tabSnapshot } from "../mods/recall/lib/closed.js";
import { listView } from "../mods/recall/lib/listview.js";
import { queueTargets, readQueue, repositoryOf } from "../mods/ship-it-prs/pr-queue.js";

const file = (path) => fileURLToPath(new URL(`../${path}`, import.meta.url));
const local = { name: null, layout: "ready" };
const remote = { name: "work", layout: "ready" };

test("agent pane titles show the task and preserve explicit pane names", () => {
  const pane = { program: { agent: true, name: "Claude Code", key: "claude" }, terminal: "t12x", title: "⠐ Test checkout" };
  assert.equal(paneTitle(pane), "Test checkout");
  assert.equal(paneTitle({ ...pane, name: "Manual pane name" }), "Manual pane name");
  for (const title of ["/tmp", "dev@mac:~/code", "t12x", "bash -l", "Claude Code"]) {
    assert.equal(paneTitle({ ...pane, title }), "Claude Code");
  }
  assert.equal(paneTitle({ title: "A shell title", program: { shell: true, name: "Bash" } }), "Bash");
});

test("context requires a fresh reading for the same live Claude session", () => {
  const labels = { "revive.agent": "claude", "revive.session": "a", "herdr.context": "a|0|1000" };
  assert.equal(contextRemaining(labels, 1_000_001), 0);
  assert.equal(contextRemaining(labels, 1_600_000), null);
  assert.equal(contextRemaining({ ...labels, "revive.session": "b" }, 1_000_001), null);
  assert.equal(contextRemaining({ ...labels, "revive.agent": "codex" }, 1_000_001), null);
  for (const reading of ["a|101|1000", "a|1|1001", "a|1", "a|1|1000|extra"]) {
    assert.equal(contextRemaining({ ...labels, "herdr.context": reading }, 1_000_001), null);
  }
});

test("status line keeps Ponytail output and publishes only valid Herdr readings", () => {
  const scratch = mkdtempSync(join(tmpdir(), "herdr-context-"));
  try {
    const hooks = join(scratch, ".claude/plugins/cache/ponytail/ponytail/4.7.0/hooks");
    mkdirSync(hooks, { recursive: true });
    writeFileSync(join(hooks, "ponytail-statusline.sh"), "printf ponytail\n");
    writeFileSync(join(scratch, "hc"), '#!/bin/sh\nprintf "%s\\n" "$@" > "$HOME/labels"\n', { mode: 0o755 });
    const run = (session_id, remaining_percentage, terminal) => spawnSync("bash", [file("mods/my-agents/claude-statusline.sh")], {
      input: JSON.stringify({ session_id, context_window: { remaining_percentage } }), encoding: "utf8",
      env: { ...process.env, HOME: scratch, HC_TERMINAL_ID: terminal, PATH: `${scratch}:${process.env.PATH}` },
    });
    assert.equal(run("test-session", 71.2, "t42").stdout, "ponytail");
    const recorded = readFileSync(join(scratch, "labels"), "utf8");
    assert.match(recorded, /^label\nt42\nherdr\.context=test-session\|71\|\d+\n$/);
    assert.equal(run("another", 77, "").stdout, "ponytail");
    assert.equal(run("another", null, "t42").stdout, "ponytail");
    assert.equal(readFileSync(join(scratch, "labels"), "utf8"), recorded);
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});

test("recently closed preserves an exact session and excludes an offline machine", () => {
  const spaces = [{ id: "space", name: "Work", named: true, machine: "work", tabs: [{ id: "tab", name: "My task", named: true }] }];
  const panes = [{ tab: "tab", terminal: "work/t1", cwd: "/repos/checkout", program: { agent: true } }];
  const labels = { "revive.agent": "claude", "revive.session": "my-session", "revive.transcript": "/private", "unrelated": "secret" };
  const before = tabSnapshot(spaces, panes, [{ address: "work/t1", labels }], [remote]);
  const offline = tabSnapshot([], [], [], [{ ...remote, layout: "unavailable" }], before.tabs);
  assert.deepEqual(rememberClosed(before.tabs, offline, [], 10), []);
  const paneGone = tabSnapshot(spaces, [], [], [remote], before.tabs);
  assert.deepEqual(rememberClosed(before.tabs, paneGone, [], 11), []);
  const after = tabSnapshot([], [], [], [remote], paneGone.tabs);
  const history = rememberClosed(paneGone.tabs, after, [], 12);
  assert.deepEqual(loadClosed([null, { title: "Incomplete" }, history[0]]), history);
  assert.deepEqual(history[0].reviveLabels, { "revive.agent": "claude", "revive.session": "my-session" });
  assert.equal(closedItems(history, "/repos")[0].path, "~/checkout");
  assert.equal(listView("closed", { closed: history, home: "/repos" }, "task").rows[0].item.tab.id, "tab");
});

test("reopen uses Revive's exact session and drops unattended permission flags", () => {
  const resume = (labels) => JSON.parse(spawnSync(process.execPath, [file("mods/recall/reopen-agent.mjs"), JSON.stringify(labels)], { encoding: "utf8" }).stdout);
  const labels = { "revive.agent": "claude", "revive.session": "exact-id", "revive.flags": '["--dangerously-skip-permissions","--model","haiku"]' };
  assert.deepEqual(resume(labels), ["claude", "--model", "haiku", "--resume", "exact-id"]);
  assert.equal(resume({ ...labels, "revive.session": "" }), null);
  assert.equal(resume({ ...labels, "revive.needs": '["CLAUDE_CONFIG_DIR"]' }), null);
});

test("the PR queue deduplicates worktrees on the same machine and keeps other machines distinct", async () => {
  const spaces = [{ id: "s1", machine: null, tabs: [{ id: "a" }, { id: "b" }] }, { id: "s2", machine: "work", tabs: [{ id: "c" }] }];
  const panes = ["a", "b", "c"].map((tab) => ({ tab, terminal: `t${tab}`, cwd: `/checkout/${tab}` }));
  const targets = queueTargets(spaces, panes, [local, remote]);
  assert.deepEqual(repositoryOf("git@github.com:buvis/gems.git"), repositoryOf("https://github.com/buvis/gems"));
  const calls = [];
  const exec = async (cmd, args, { cwd, on }) => {
    if (cmd === "git") return { code: 0, stdout: cwd.endsWith("a") ? "git@github.com:buvis/gems.git" : "https://github.com/buvis/gems" };
    calls.push({ cmd, args, cwd, on });
    if (on) return { code: 1 };
    return { code: 0, stdout: JSON.stringify([{ number: 7, updatedAt: "2026-11-23", statusCheckRollup: "fail" }, { number: 8, updatedAt: "2026-11-24", statusCheckRollup: "pass" }]) };
  };
  const options = { exec, ghx: "/herdr/bin/ghx", fields: "number", checkState: (status) => status, isCurrent: () => true };
  const failed = await readQueue(targets, "failed", options);
  assert.deepEqual(calls.map(({ cmd, cwd, on }) => [cmd, cwd, on]), [["/herdr/bin/ghx", "/checkout/a", null], ["gh", "/checkout/c", "work"]]);
  assert.deepEqual(failed.rows.map((pr) => pr.number), [7]);
  assert.deepEqual(failed.errors, ["buvis/gems · work"]);
  calls.length = 0;
  const review = await readQueue(targets, "review", options);
  assert.ok(calls.every(({ args }) => args.includes("review-requested:@me sort:updated-desc")));
  assert.deepEqual(review.rows.map((pr) => pr.number), [8, 7]);
  assert.equal(await readQueue(targets, "review", { ...options, isCurrent: () => false }), null);
});

test("the PR queue reads Bitbucket checks on each exact head and reports partial results", async () => {
  const calls = [];
  const exec = async (command, args) => {
    calls.push([command, ...args]);
    if (command === "git") return { code: 0, stdout: "git@bitbucket.org:work/build.git" };
    if (args[1] === "list") return { code: 0, stdout: JSON.stringify([
      { number: 1, headRefOid: "abc1234" }, { number: 2, headRefOid: "abc1235" }, { number: 3, headRefOid: "abc1236" },
    ]) };
    if (args[3] === "abc1234") return { code: 0, stdout: '[{"bucket":"fail"}]' };
    if (args[3] === "abc1235") return { code: 0, stdout: '[{"bucket":"pass"}]' };
    return { code: 1 };
  };
  const results = await readQueue([{ cwd: "/repo", on: null, space: "s" }], "failed", {
    exec, ghx: "local-ghx", fields: "number,headRefOid", checkState: () => assert.fail("Bitbucket list has no check rollup"), isCurrent: () => true,
  });
  assert.deepEqual(results.rows.map(({ number }) => number), [1]);
  assert.deepEqual(results.errors, ["work/build"]);
  assert.deepEqual(calls.slice(2).map(([, , , option, sha]) => [option, sha]), [["--commit", "abc1234"], ["--commit", "abc1235"], ["--commit", "abc1236"]]);
});

test("the open PR queue uses the exact GitHub repo and excludes GitLab remotes", async () => {
  const calls = [];
  const exec = async (command, args, { cwd }) => {
    if (command === "git") return { code: 0, stdout: cwd === "/notes" ? "https://gitlab.com/org/notes.git" : "git@github.com:org/code.git" };
    calls.push(args);
    if (cwd === "/notes") return { code: 1, stderr: "unknown GitHub host" };
    return { code: 0, stdout: '[{"number":42,"statusCheckRollup":[]}]' };
  };
  const targets = ["/notes", "/code"].map((cwd) => ({ cwd, on: null }));
  const result = await readQueue(targets, "open", { exec, ghx: "ghx", fields: "number", checkState: () => null, isCurrent: () => true });
  assert.equal(calls.length, 1);
  assert.equal(calls[0][calls[0].indexOf("--repo") + 1], "github.com/org/code");
  assert.deepEqual(result.rows.map((pr) => pr.number), [42]);
  assert.deepEqual(result.errors, []);
  assert.equal(result.gitLabSkipped, 1);
});
