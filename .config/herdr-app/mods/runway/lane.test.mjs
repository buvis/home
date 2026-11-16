import assert from "node:assert/strict";
import { test } from "node:test";
import { actionFor, openLane, planLane } from "./lane.js";

const PM = "docs/dev/project-management";
const PRDS = `${PM}/prds`;
const STATE = `${PM}/autopilot/state.json`;

function prdCard(name, { checkout = "/repo", bucket = "backlog", group = "prd", stage = "backlog" } = {}) {
  return {
    id: `prd:${name}`,
    kind: "prd",
    number: name.slice(0, 5),
    title: name.slice(6, -3),
    group,
    stage,
    checkout,
    file: `${checkout}/${PRDS}/${bucket}/${name}`,
  };
}

function specCard(name, { checkout = "/repo", group = "spec", title = "Some Title" } = {}) {
  return {
    id: `spec:${name}`,
    kind: "spec",
    number: name.slice(0, 5),
    title,
    group,
    stage: "tasks",
    checkout,
    file: `${checkout}/docs/specs/${name}/requirements.md`,
  };
}

// The item name is the card.id suffix after "idea:" (the folder name, number included), never the title.
function ideaCard(name, { checkout = "/repo", title = "A Different Title" } = {}) {
  return {
    id: `idea:${name}`,
    kind: "idea",
    number: name.slice(0, 5),
    title,
    group: "idea",
    stage: "idea",
    checkout,
    file: `${checkout}/${PM}/intake/new/${name}/idea.md`,
  };
}

const repo = (name, main, { branches = [], worktrees = [] } = {}) => ({
  name,
  main,
  branches: ["master", ...branches],
  worktrees: [{ path: main, branch: "master", main: true }, ...worktrees],
});

const HERDR = repo("herdr", "/repo");
const TOOL = repo("tool", "/src/tool", {
  branches: ["feature/00001-old"],
  worktrees: [{ path: "/home/b/git/src/worktrees/tool/feature-00001-old", branch: "feature/00001-old", main: false }],
});
const GAMMA = prdCard("00012-gamma.md");
const CACHE = prdCard("00140-api-cache-v3.md", { checkout: "/src/tool" });
const QUEUE = specCard("00008-queue-view");
const LANES = specCard("00031-runway-lanes", { checkout: "/src/tool" });

const ok = (stderr = "") => ({ code: 0, stderr });

// Fake I/O: a set of existing paths and a log of every call. `checkout` lists paths git add creates.
function fakeIo(existing, { git = ok(), checkout = [], move } = {}) {
  const fs = new Set(existing);
  const calls = [];
  const io = {
    async git(args, cwd) {
      calls.push(["git", args, cwd]);
      const r = typeof git === "function" ? await git(args, cwd) : git;
      if (r.code === 0) for (const p of checkout) fs.add(p);
      return r;
    },
    async exists(p) {
      calls.push(["exists", p]);
      return fs.has(p);
    },
    async move(from, to) {
      calls.push(["move", from, to]);
      if (move) return move(fs, from, to);
      fs.delete(from);
      fs.add(to);
    },
    async remove(p) {
      calls.push(["remove", p]);
      fs.delete(p);
    },
    async mkdir(p) {
      calls.push(["mkdir", p]);
      fs.add(p);
    },
  };
  return { io, fs, calls, writes: () => calls.filter((c) => c[0] !== "exists") };
}

const addArgs = (plan) => ["worktree", "add", "-b", plan.branch, plan.path, "HEAD"];

test("plans_feature_branch_and_worktree_path_for_prd", () => {
  const a = planLane(GAMMA, HERDR, "/Users/a");
  const pa = "/Users/a/git/src/worktrees/herdr/feature-00012-gamma";
  assert.equal(a.error, undefined);
  assert.equal(a.branch, "feature/00012-gamma");
  assert.equal(a.path, pa);
  assert.equal(a.main, "/repo");
  assert.equal(a.from, `/repo/${PRDS}/backlog/00012-gamma.md`);
  assert.equal(a.to, `${pa}/${PRDS}/wip/00012-gamma.md`);
  assert.equal(a.stale, `${pa}/${PRDS}/backlog/00012-gamma.md`);

  // A trailing -v<N> is dropped; other branches and worktrees do not block.
  const b = planLane(CACHE, TOOL, "/home/b");
  const pb = "/home/b/git/src/worktrees/tool/feature-00140-api-cache";
  assert.equal(b.branch, "feature/00140-api-cache");
  assert.equal(b.path, pb);
  assert.equal(b.main, "/src/tool");
  assert.equal(b.from, `/src/tool/${PRDS}/backlog/00140-api-cache-v3.md`);
  assert.equal(b.to, `${pb}/${PRDS}/wip/00140-api-cache-v3.md`);
  assert.equal(b.stale, `${pb}/${PRDS}/backlog/00140-api-cache-v3.md`);
  assert.equal(planLane(prdCard("00144-dev-v12.md"), HERDR, "/h").branch, "feature/00144-dev");

  // Near misses of -v<N> stay in the slug.
  assert.equal(planLane(prdCard("00141-gamma-vault.md"), HERDR, "/h").branch, "feature/00141-gamma-vault");

  // Each run of other characters is one dash in the path, never in the branch.
  const odd = planLane(prdCard("00142-a & b.md"), HERDR, "/h");
  assert.equal(odd.branch, "feature/00142-a & b");
  assert.equal(odd.path, "/h/git/src/worktrees/herdr/feature-00142-a-b");
  const kept = planLane(prdCard("00143-x+y_1.2.md"), HERDR, "/h");
  assert.equal(kept.branch, "feature/00143-x+y_1.2");
  assert.equal(kept.path, "/h/git/src/worktrees/herdr/feature-00143-x-y_1.2");
  const punct = planLane(prdCard("00145-a:b#c@d.md"), HERDR, "/h");
  assert.equal(punct.branch, "feature/00145-a:b#c@d");
  assert.equal(punct.path, "/h/git/src/worktrees/herdr/feature-00145-a-b-c-d");

  // The slug comes from the file name, never the title; only a trailing -v<N> goes.
  const titled = planLane({ ...GAMMA, title: "Gamma Feature" }, HERDR, "/h");
  assert.equal(titled.branch, "feature/00012-gamma");
  assert.equal(titled.path, "/h/git/src/worktrees/herdr/feature-00012-gamma");
  assert.equal(planLane(prdCard("00150-v2-api.md"), HERDR, "/h").branch, "feature/00150-v2-api");
});

test("plans_specflow_branch_for_spec", () => {
  const a = planLane(QUEUE, HERDR, "/Users/a");
  assert.equal(a.error, undefined);
  assert.equal(a.branch, "feature/specflow-00008");
  assert.equal(a.path, "/Users/a/git/src/worktrees/herdr/feature-specflow-00008");
  assert.equal(a.main, "/repo");
  assert.equal(a.from, undefined);
  assert.equal(a.to, undefined);
  assert.equal(a.stale, undefined);

  // The backlog rule is for PRDs only: a spec in a worktree still plans.
  const inTree = specCard("00031-runway-lanes", { checkout: "/home/b/git/src/worktrees/tool/feature-00001-old" });
  for (const card of [LANES, inTree]) {
    const b = planLane(card, TOOL, "/home/b");
    assert.equal(b.error, undefined);
    assert.equal(b.branch, "feature/specflow-00031");
    assert.equal(b.path, "/home/b/git/src/worktrees/tool/feature-specflow-00031");
    assert.equal(b.main, "/src/tool");
    assert.equal(b.from, undefined);
  }
});

test("refuses_prd_outside_main_backlog", () => {
  const msg = "Only a backlog PRD in the main checkout can move";
  const wt = "/home/b/git/src/worktrees/tool/feature-00001-old";
  for (const card of [
    prdCard("00012-gamma.md", { bucket: "wip", stage: "wip" }),
    prdCard("00012-gamma.md", { bucket: "hold", group: "parked", stage: "parked" }),
    prdCard("00012-gamma.md", { bucket: "done", stage: "closed" }),
  ]) {
    assert.deepEqual(planLane(card, HERDR, "/h"), { error: msg }, card.file);
  }
  // Backlog of a linked worktree, and a checkout whose path only starts like main.
  assert.deepEqual(planLane(prdCard("00140-api-cache.md", { checkout: wt }), TOOL, "/h"), { error: msg });
  assert.deepEqual(planLane(prdCard("00140-api-cache.md", { checkout: "/src/tool-old" }), TOOL, "/h"), { error: msg });

  // Paths that share the main backlog prefix but are not directly in it.
  for (const bucket of ["backlog/old", "backlog-old"]) {
    assert.deepEqual(planLane(prdCard("00012-gamma.md", { bucket }), HERDR, "/h"), { error: msg }, bucket);
  }
  // A backlog folder elsewhere under main is not the PRD backlog.
  for (const file of ["/repo/other/backlog/00012-gamma.md", "/repo/vendor/x/backlog/00012-gamma.md"]) {
    assert.deepEqual(planLane({ ...GAMMA, file }, HERDR, "/h"), { error: msg }, file);
  }

  // The backlog rule wins over an existing branch.
  const taken = repo("herdr", "/repo", { branches: ["feature/00012-gamma"] });
  assert.deepEqual(planLane(prdCard("00012-gamma.md", { bucket: "wip" }), taken, "/h"), { error: msg });

  // The same card in the main backlog plans.
  assert.equal(planLane(prdCard("00140-api-cache.md"), repo("tool", "/repo"), "/h").error, undefined);
});

test("refuses_existing_branch", () => {
  const taken = repo("herdr", "/repo", { branches: ["feature/00001-x", "feature/00012-gamma", "feature/specflow-00008"] });
  assert.deepEqual(planLane(GAMMA, taken, "/h"), { error: "Branch feature/00012-gamma exists; use its chip" });
  assert.deepEqual(planLane(QUEUE, taken, "/h"), { error: "Branch feature/specflow-00008 exists; use its chip" });

  // Near-miss branch names do not block.
  const near = repo("herdr", "/repo", {
    branches: ["feature/00012-gamma-v2", "feature/00012-gamm", "00012-gamma", "feature/00012-gamma/x", "feature/specflow-000080"],
  });
  assert.equal(planLane(GAMMA, near, "/h").error, undefined);
  assert.equal(planLane(QUEUE, near, "/h").error, undefined);

  // A worktree already at the path is refused; the branch error comes first.
  const p = "/h/git/src/worktrees/herdr/feature-00012-gamma";
  const at = (path, branches = []) =>
    repo("herdr", "/repo", { branches, worktrees: [{ path, branch: "detached", main: false }] });
  assert.deepEqual(planLane(GAMMA, at(p), "/h"), { error: `Worktree ${p} exists` });
  const sp = "/h/git/src/worktrees/herdr/feature-specflow-00008";
  assert.deepEqual(planLane(QUEUE, at(sp), "/h"), { error: `Worktree ${sp} exists` });
  assert.deepEqual(planLane(GAMMA, at(p, ["feature/00012-gamma"]), "/h"), {
    error: "Branch feature/00012-gamma exists; use its chip",
  });
  assert.equal(planLane(GAMMA, at(`${p}-old`), "/h").error, undefined);
});

test("moves_prd_into_worktree_wip_and_removes_stale_copy", async () => {
  for (const [card, r, home] of [[GAMMA, HERDR, "/Users/a"], [CACHE, TOOL, "/home/b"]]) {
    const plan = planLane(card, r, home);
    const f = fakeIo([plan.from], { checkout: [plan.stale] });
    assert.deepEqual(await openLane(plan, f.io), { path: plan.path, branch: plan.branch });
    assert.deepEqual(f.writes(), [
      ["git", addArgs(plan), r.main],
      ["mkdir", `${plan.path}/${PRDS}/wip`],
      ["move", plan.from, plan.to],
      ["remove", plan.stale],
    ]);
    assert.ok(f.fs.has(plan.to));
    assert.ok(!f.fs.has(plan.from));
    assert.ok(!f.fs.has(plan.stale));
    // The state.json check runs after the add and before the move.
    const i = (pred) => f.calls.findIndex(pred);
    const state = i((c) => c[0] === "exists" && c[1] === `${plan.path}/${STATE}`);
    assert.ok(state > i((c) => c[0] === "git") && state < i((c) => c[0] === "mkdir"));
  }

  // No stale copy: nothing is removed.
  const plan = planLane(GAMMA, HERDR, "/h");
  const f = fakeIo([plan.from]);
  assert.deepEqual(await openLane(plan, f.io), { path: plan.path, branch: plan.branch });
  assert.equal(f.calls.filter((c) => c[0] === "remove").length, 0);
});

test("changes_nothing_when_worktree_add_fails", async () => {
  const cases = [
    [GAMMA, HERDR, { code: 128, stderr: "Preparing worktree (new branch)\nfatal: '/x' already exists\n" }, "fatal: '/x' already exists"],
    [CACHE, TOOL, { code: 1, stderr: "fatal: invalid reference: HEAD" }, "fatal: invalid reference: HEAD"],
    [GAMMA, HERDR, { code: 1, stderr: "Preparing worktree\nerror: unable to create file\n" }, "error: unable to create file"],
  ];
  for (const [card, r, git, line] of cases) {
    const plan = planLane(card, r, "/h");
    const f = fakeIo([plan.from], { git });
    await assert.rejects(openLane(plan, f.io), { message: `Could not create the worktree: ${line}; nothing changed` });
    assert.deepEqual(f.writes(), [["git", addArgs(plan), r.main]]);
    assert.deepEqual([...f.fs], [plan.from]);
  }

  // A PRD gone from the backlog stops before git.
  const plan = planLane(GAMMA, HERDR, "/h");
  const f = fakeIo([]);
  await assert.rejects(openLane(plan, f.io), { message: "The PRD is no longer in the backlog; nothing changed" });
  assert.deepEqual(f.writes(), []);
  assert.deepEqual([...f.fs], []);
});

test("keeps_prd_in_main_when_worktree_has_state_json", async () => {
  for (const [card, r] of [[GAMMA, HERDR], [CACHE, TOOL]]) {
    const plan = planLane(card, r, "/h");
    const state = `${plan.path}/${STATE}`;
    const f = fakeIo([plan.from], { checkout: [plan.stale, state] });
    await assert.rejects(openLane(plan, f.io), {
      message: `The new worktree has a tracked state.json. The PRD did not move. Worktree: ${plan.path}`,
    });
    assert.deepEqual(f.writes(), [["git", addArgs(plan), r.main]]);
    assert.ok(f.fs.has(plan.from) && f.fs.has(plan.stale) && f.fs.has(state));
  }

  // A spec lane is refused the same way.
  const spec = planLane(QUEUE, HERDR, "/h");
  const s = fakeIo([], { checkout: [`${spec.path}/${STATE}`] });
  await assert.rejects(openLane(spec, s.io), {
    message: `The new worktree has a tracked state.json. The PRD did not move. Worktree: ${spec.path}`,
  });

  // A state.json elsewhere, or a near-miss name, does not stop the move.
  const plan = planLane(GAMMA, HERDR, "/h");
  const f = fakeIo([plan.from, `/repo/${STATE}`], { checkout: [`${plan.path}/${STATE}.bak`] });
  assert.deepEqual(await openLane(plan, f.io), { path: plan.path, branch: plan.branch });
  assert.ok(f.fs.has(plan.to));
});

test("reports_both_paths_when_move_is_incomplete", async () => {
  const noop = () => {};
  const copy = (fs, _from, to) => void fs.add(to);
  for (const [card, r, move] of [[GAMMA, HERDR, noop], [CACHE, TOOL, copy]]) {
    const plan = planLane(card, r, "/h");
    const f = fakeIo([plan.from], { checkout: [plan.stale], move });
    await assert.rejects(openLane(plan, f.io), {
      message: `The PRD move did not complete. Check ${plan.from} and ${plan.to}`,
    });
    assert.deepEqual(f.calls.filter((c) => c[0] === "remove"), []);
    assert.ok(f.fs.has(plan.from));
    assert.ok(f.fs.has(plan.stale));
  }

  // A move that drops the source without writing the target is not a success.
  const plan = planLane(GAMMA, HERDR, "/h");
  const lose = fakeIo([plan.from], { checkout: [plan.stale], move: (fs, from) => void fs.delete(from) });
  await assert.rejects(openLane(plan, lose.io), {
    message: `The PRD move did not complete. Check ${plan.from} and ${plan.to}`,
  });
  assert.deepEqual(lose.calls.filter((c) => c[0] === "remove"), []);
  assert.ok(lose.fs.has(plan.stale));
});

test("refuses_second_lane_while_one_opens", async () => {
  let release;
  let entered;
  const gate = new Promise((r) => (release = r));
  const started = new Promise((r) => (entered = r));
  const plan = planLane(GAMMA, HERDR, "/h");
  const slow = fakeIo([plan.from], { git: () => (entered(), gate) });
  const first = openLane(plan, slow.io);
  await started;

  const other = planLane(CACHE, TOOL, "/h");
  const second = fakeIo([other.from]);
  await assert.rejects(openLane(other, second.io), { message: "A lane is already opening" });
  assert.deepEqual(second.calls, []);

  release(ok());
  assert.deepEqual(await first, { path: plan.path, branch: plan.branch });

  // The flag clears after success.
  const third = fakeIo([other.from]);
  assert.deepEqual(await openLane(other, third.io), { path: other.path, branch: other.branch });
});

test("clears_busy_flag_after_failure", async () => {
  const plan = planLane(GAMMA, HERDR, "/h");
  const failures = [
    fakeIo([plan.from], { git: { code: 128, stderr: "fatal: nope\n" } }),
    fakeIo([plan.from], { move: () => {} }),
    fakeIo([plan.from], { git: () => Promise.reject(new Error("spawn git ENOENT")) }),
    fakeIo([plan.from], { move: () => Promise.reject(new Error("EACCES")) }),
  ];
  // Every injected I/O call that throws must still clear the flag.
  const boom = async () => {
    throw new Error("EIO");
  };
  for (const name of ["exists", "mkdir", "remove"]) {
    const f = fakeIo([plan.from], { checkout: [plan.stale] });
    f.io[name] = boom;
    failures.push(f);
  }
  for (const f of failures) {
    await assert.rejects(openLane(plan, f.io), Error);
    const next = fakeIo([plan.from]);
    assert.deepEqual(await openLane(plan, next.io), { path: plan.path, branch: plan.branch });
  }
});

test("spec_lane_moves_no_file", async () => {
  for (const [card, r] of [[QUEUE, HERDR], [LANES, TOOL]]) {
    const plan = planLane(card, r, "/h");
    const f = fakeIo([]);
    assert.deepEqual(await openLane(plan, f.io), { path: plan.path, branch: plan.branch });
    assert.deepEqual(f.writes(), [["git", addArgs(plan), r.main]]);
    assert.deepEqual(f.calls.filter((c) => c[0] === "exists"), [["exists", `${plan.path}/${STATE}`]]);
  }
});

const PARKED = prdCard("00030-paused.md", { bucket: "hold", group: "parked", stage: "parked" });
const PARKED2 = prdCard("00031-held.md", { bucket: "hold", group: "parked", stage: "parked" });
const SPEC_ON = { specflow: true };
const SPEC_OFF = { specflow: false };

test("triage_stub_cannot_be_unparked", () => {
  for (const [card, key] of [[PARKED, "T-12"], [PARKED2, "triage-7"]]) {
    for (const env of [SPEC_ON, SPEC_OFF]) {
      const a = actionFor(card, { ledger_key: key, status: "hold" }, env);
      assert.equal(a.label, "Un-park");
      assert.equal(a.disabled, true);
      assert.equal(a.tip, "Triage stub: promote it by writing a PRD");
    }
  }
  // Near-miss keys are not a triage stub.
  for (const fm of [{ ledger: "T-12" }, { ledger_keys: "T-12" }, { key: "T-12" }]) {
    const a = actionFor(PARKED, fm, SPEC_OFF);
    assert.equal(a.kind, "move", JSON.stringify(fm));
    assert.ok(!a.disabled, JSON.stringify(fm));
  }
  // An active PRD with a ledger key gets no button.
  assert.equal(actionFor(prdCard("00012-gamma.md", { bucket: "wip" }), { ledger_key: "T-12" }, SPEC_ON), null);
});

test("parked_prd_unparks_by_move", () => {
  for (const card of [PARKED, PARKED2]) {
    for (const [fm, env] of [[{}, SPEC_ON], [{ status: "hold", title: "x" }, SPEC_OFF], [null, SPEC_ON], [undefined, SPEC_OFF]]) {
      const a = actionFor(card, fm, env);
      assert.equal(a.label, "Un-park");
      assert.equal(a.kind, "move");
      assert.ok(!a.disabled);
      assert.equal(a.task, undefined);
    }
  }
  // Active PRDs get no button.
  assert.equal(actionFor(GAMMA, {}, SPEC_ON), null);
  assert.equal(actionFor(prdCard("00012-gamma.md", { bucket: "wip", stage: "build" }), {}, SPEC_OFF), null);
});

test("parked_spec_resumes_through_specflow", () => {
  const cases = [
    [specCard("00008-queue-view", { group: "parked", title: "Queue View" }), "00008-queue-view"],
    [specCard("00031-runway-lanes", { group: "parked", title: "Lanes" }), "00031-runway-lanes"],
  ];
  for (const [card, name] of cases) {
    for (const env of [SPEC_ON, SPEC_OFF]) {
      const a = actionFor(card, {}, env);
      assert.equal(a.label, "Resume");
      assert.equal(a.kind, "agent");
      assert.equal(a.task, `/specflow:spec-workflow Resume ${name}`);
      assert.ok(!a.disabled);
    }
  }
  // An active spec gets no button.
  assert.equal(actionFor(QUEUE, {}, SPEC_ON), null);
  assert.equal(actionFor(LANES, {}, SPEC_OFF), null);
});

test("idea_creates_spec_where_specflow_is_configured", () => {
  for (const [name, fm] of [["00022-late", {}], ["00023-night-mode", null]]) {
    const a = actionFor(ideaCard(name, { title: "Late Night" }), fm, SPEC_ON);
    assert.equal(a.label, "Create spec");
    assert.equal(a.kind, "agent");
    assert.equal(a.task, `/specflow:spec-workflow Create a spec for ${name}`);
    assert.ok(!a.disabled);
  }
});

test("idea_elicits_elsewhere", () => {
  for (const [name, number, fm] of [["00022-late", "00022", {}], ["00023-night-mode", "00023", undefined]]) {
    const a = actionFor(ideaCard(name), fm, SPEC_OFF);
    assert.equal(a.label, "Elicit");
    assert.equal(a.kind, "agent");
    assert.equal(a.task, `/elicit-requirements ${number}`);
    assert.ok(!a.disabled);
  }
  // A card of an unknown kind gets no button, whatever its group.
  for (const group of ["idea", "parked"]) {
    const card = { ...ideaCard("00024-odd"), id: "note:00024-odd", kind: "note", group };
    for (const env of [SPEC_ON, SPEC_OFF]) assert.equal(actionFor(card, {}, env), null, group);
  }
});
