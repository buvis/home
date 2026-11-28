import assert from "node:assert/strict";
import {test} from "node:test";
import {CLAUDE, LANE, LOCAL, LOOP, NO_CLAUDE, PM, REMOTE, SPECS, WITH_CLAUDE, ZED, ZETA, allRepos, cardOf, clean,
  click, exists, failed, gitCalls, gitWhere, hasSpinner, labelled, mutations, norm, notBubbled, openPanel, press, confirmLane,
  reloads, runsOf, settle, started, status, unfoldParked, walk, world} from "./housekeeping-harness.mjs";

// Lane and loop controls; un-park and intake controls are in housekeeping-actions.test.mjs.

test("Create worktree shows on main-checkout backlog PRDs and main specs only", async () => {
  // 00010-alpha.md carries a heading no fixture table knows, so card titles must come from the PRD's # line.
  const checkouts = [{...SPECS.checkouts[0], texts: {"00010-alpha.md": "# Fresh heading\n\nBody.\n"}},
    SPECS.checkouts[1]];
  world({...SPECS, checkouts, agents: WITH_CLAUDE});
  const panel = await openPanel();
  await unfoldParked(panel);
  const tree = panel.render();
  assert.doesNotMatch(norm(tree), /Queue alpha/, "the PRD's own heading is the title");
  for (const title of ["Fresh heading", "Queue beta", "cross host validation"]) {
    assert.ok(labelled(cardOf(tree, title), LANE), `${title} offers ${LANE}`);
  }
  for (const title of ["Gamma work", "side quest", "Paused thing", "Late idea"]) {
    assert.equal(labelled(cardOf(tree, title), LANE), undefined, `${title}: no ${LANE}`);
  }
  assert.ok(!norm(tree).includes("Old thing"), "the worktree's wip card already done on main is dropped");
  clean();
});

test("remote cards offer neither Create worktree nor the loop", async () => {
  for (const agents of [WITH_CLAUDE, ...NO_CLAUDE]) {
    const {calls} = world({...REMOTE, agents});
    const panel = await openPanel();
    const tree = panel.render();
    assert.equal(labelled(tree, LOOP), undefined, "no repository loop on a remote machine");
    for (const title of ["Remote thing", "Delta work"]) {
      assert.equal(labelled(cardOf(tree, title), LANE), undefined, `${title}: no ${LANE}`);
      assert.equal(labelled(cardOf(tree, title), LOOP), undefined, `${title}: no loop`);
    }
    await press(panel, "Remote thing", "Send to agent…");
    const card = cardOf(panel.render(), "Remote thing");
    if (agents !== WITH_CLAUDE) {
      // No live Claude control without Claude: absent, or marked as needing it and starting nothing.
      assert.ok(!labelled(card, "Claude") || /Needs Claude Code/.test(norm(card)), `no Claude control: ${norm(card)}`);
      if (labelled(card, "Claude")) await click(labelled(card, "Claude"), card);
      assert.deepEqual(started(calls), [], "nothing starts without Claude");
      clean();
      continue;
    }
    await press(panel, "Remote thing", "Claude");
    assert.ok(runsOf(calls, "tab.new").some((a) => JSON.stringify(a.argv) === JSON.stringify(["run-agent", ...CLAUDE.run])),
      `the Claude control starts Claude: ${JSON.stringify(calls.run)}`);
    clean();
  }
});

test("Run loop appears on the repository header and starts autoclaude in the primary checkout", async () => {
  const cases = [
    {fixture: LOCAL, space: "s1", folder: "/work/app", titles: ["Queue alpha", "Queue beta", "Gamma work"]},
    {fixture: ZED, space: "s5", folder: "/work/zed", titles: ["Queue beta"]},
  ];
  for (const c of cases) {
    const {calls} = world({...c.fixture, agents: WITH_CLAUDE});
    const panel = await openPanel();
    const tree = panel.render();
    for (const title of c.titles) assert.equal(labelled(cardOf(tree, title), LOOP), undefined, `${title}: no loop`);
    const header = walk(tree).find((n) => n.calls.some(([method, args]) =>
      method === "id" && args[0].startsWith("repo-")));
    assert.ok(labelled(header, LOOP), "the repository header has the loop");
    await click(labelled(header, LOOP));
    assert.deepEqual(runsOf(calls, "tab.new"),
      [{space: c.space, folder: c.folder, name: "autoclaude", argv: ["autoclaude"]}]);
    assert.ok(calls.run.every(([n]) => n === "space.select" || n === "tab.new"), `only the loop: ${JSON.stringify(calls.run)}`);
    clean();
  }
});

test("Run loop is hidden on the pick card of a local lane worktree", async () => {
  const [main, lane] = LOCAL.checkouts;
  world({...LOCAL, checkouts: [main, {...lane, wip: ["00012-gamma.md"]}], agents: WITH_CLAUDE});
  const panel = await openPanel();
  const tree = panel.render();
  assert.ok(labelled(tree, LOOP));
  assert.equal(labelled(cardOf(tree, "Queue alpha"), LOOP), undefined);
  assert.equal(labelled(cardOf(tree, "Gamma work"), LOOP), undefined);
  clean();
});

// /work/app has no space: the focus is in the worktree's space, or (All repos) in a remote space.
const NO_SPACE = [
  {name: "worktree space focused", fixture: {...LOCAL, focusedPane: "p3", spaces: [LOCAL.spaces[0],
    {id: "s3", folder: "/wt/gamma", tabs: [{id: "t3", pane: "p3", cwd: "/wt/gamma"}]}]}},
  {name: "remote space focused", fixture: {...LOCAL, spaces: REMOTE.spaces, focusedPane: REMOTE.focusedPane},
    scope: "/work/app,app\n"},
];

test("Run loop without a space for the checkout opens a new space on this computer running autoclaude", async () => {
  for (const c of NO_SPACE) {
    const {calls} = world({...c.fixture, agents: WITH_CLAUDE});
    const panel = await openPanel();
    if (c.scope) await allRepos(panel, c.scope);
    assert.ok(await click(labelled(panel.render(), LOOP)));
    const spaces = runsOf(calls, "space.new");
    assert.equal(spaces.length, 1, `${c.name}: one new space: ${JSON.stringify(calls.run)}`);
    const {folder, machine, argv} = spaces[0];
    assert.deepEqual({folder, machine, argv}, {folder: "/work/app", machine: "", argv: ["autoclaude"]}, c.name);
    assert.ok(!("task" in spaces[0]), `${c.name}: the loop sends no task`);
    assert.ok(spaces[0].tab === undefined || spaces[0].tab === "autoclaude", `${c.name}: tab ${spaces[0].tab}`);
    assert.deepEqual(runsOf(calls, "tab.new"), [], `${c.name}: no tab in another space`);
    assert.deepEqual(runsOf(calls, "space.select"), [], `${c.name}: no other space selected`);
    notBubbled(calls);
    clean();
  }
});

// The one worktree add runs in main and ends with the literal contract tail (global git options may precede it).
function assertWorktreeAdded(calls, {main, branch, path}) {
  const adds = gitCalls(calls, "worktree", "add");
  assert.equal(adds.length, 1, "one worktree added");
  assert.equal(gitWhere(adds[0]), main, "git runs in the main checkout");
  assert.deepEqual(adds[0].args.slice(-6), ["worktree", "add", "-b", branch, path, "HEAD"], `${adds[0].args}`);
}

function assertLaneOpened(calls, {main, file, branch, path}) {
  assertWorktreeAdded(calls, {main, branch, path});
  assert.deepEqual(calls.run, [["space.new", {folder: path, machine: ""}]], "opens a shell and stops the card click");
  const moves = calls.exec.filter((c) => c.command === "mv");
  assert.ok(moves.length, "the PRD is moved with mv");
  for (const c of moves) assert.ok(c.args.includes("-n"), `mv never clobbers: ${c.args}`);
  for (const c of mutations(calls)) assert.ok(c.args.includes("--"), `${c.command} passes paths after --: ${c.args}`);
}

// The PRD's exact text lands in the lane's wip; main's backlog and the lane's stale copy are gone; others stay.
function assertPrdMoved(fs, {main, path, file, other}, text) {
  const prds = `${PM}/prds`;
  assert.equal(fs.get(`${path}/${prds}/wip/${file}`), text.file, "the PRD's text is in the lane's wip");
  assert.ok(!exists(fs, `${main}/${prds}/backlog/${file}`), "main's backlog source is gone");
  assert.ok(!exists(fs, `${path}/${prds}/backlog/${file}`), "the lane has no stale backlog copy");
  assert.equal(fs.get(`${main}/${prds}/backlog/${other}`), text.other, `${other} is unchanged in main`);
}

test("Create worktree on a backlog PRD adds a worktree from main and opens a shell", async () => {
  const cases = [
    {fixture: LOCAL, title: "Queue alpha", main: "/work/app", file: "00010-alpha.md", home: "/home/u",
      other: "00011-beta.md", branch: "feature/00010-alpha", path: "/home/u/git/src/worktrees/app/feature-00010-alpha"},
    {fixture: ZETA, title: "Omega work", main: "/srv/code/zeta", file: "00044-omega.md", home: "/home/zoe",
      other: "00042-zeta.md", branch: "feature/00044-omega",
      path: "/home/zoe/git/src/worktrees/zeta/feature-00044-omega"},
  ];
  for (const c of cases) {
    const {calls, fs} = world({...c.fixture, agents: WITH_CLAUDE});
    const text = {file: fs.get(`${c.main}/${PM}/prds/backlog/${c.file}`),
      other: fs.get(`${c.main}/${PM}/prds/backlog/${c.other}`)};
    assert.ok(text.file && text.other, "both source PRDs are on the fake disk");
    const panel = await openPanel();
    const before = reloads(calls);
    await confirmLane(panel, c.title);
    assertLaneOpened(calls, c);
    assertPrdMoved(fs, c, text);
    const shown = [c.path, c.path.replace(new RegExp(`^${c.home}`), "~")];
    assert.ok(calls.notify.some((n) => String(n.body).includes(c.file) &&
      shown.some((p) => String(n.body).includes(p))), `success names file and path: ${JSON.stringify(calls.notify)}`);
    assert.ok(!calls.notify.some(failed), "no failure toast");
    assert.ok(reloads(calls) > before, "the panel reloads");
    clean();
  }
});

test("Create worktree on a main spec runs git in main and opens a shell", async () => {
  const {calls} = world({...SPECS, agents: WITH_CLAUDE});
  const panel = await openPanel();
  await confirmLane(panel, "cross host validation");
  const path = "/home/u/git/src/worktrees/app/feature-specflow-00009";
  assertWorktreeAdded(calls, {main: "/work/app", branch: "feature/specflow-00009", path});
  assert.deepEqual(calls.run, [["space.new", {folder: path, machine: ""}]]);
  assert.deepEqual(mutations(calls), [], "a spec lane moves, removes and makes nothing");
  clean();
});

test("a shell-only lane uses the edited branch and configured directory after confirmation", async () => {
  const {calls} = world({...SPECS, agents: WITH_CLAUDE, worktreeDirectory: "~/checkouts"});
  const panel = await openPanel();
  const title = "cross host validation";
  await press(panel, title, LANE);
  const input = () => walk(cardOf(panel.render(), title))
    .flatMap((node) => node.calls).find(([method]) => method === "input")[1][0];
  assert.equal(input().text, "feature/specflow-00009");
  assert.deepEqual(gitCalls(calls, "worktree", "add"), []);
  await press(panel, title, "Cancel");
  assert.deepEqual(calls.run, []);

  await press(panel, title, LANE);
  input().text = "feature/cross-host";
  await press(panel, title, LANE);
  const path = "/home/u/checkouts/app/feature-cross-host";
  assertWorktreeAdded(calls, {main: "/work/app", branch: "feature/cross-host", path});
  assert.deepEqual(calls.run, [["space.new", {folder: path, machine: ""}]]);
  assert.ok(gitCalls(calls, "config", "branch.feature/cross-host.herdr-spec", "00009-cross-host-validation").length);
  assert.equal(labelled(cardOf(panel.render(), title), LANE), undefined, "the edited lane owns the spec");
  clean();
});

test("without Claude the worktree still opens as a shell space and the toast says so", async () => {
  for (const agents of NO_CLAUDE) {
    const {calls} = world({...LOCAL, agents});
    const panel = await openPanel();
    await confirmLane(panel, "Queue alpha");
    const adds = gitCalls(calls, "worktree", "add");
    assert.equal(adds.length, 1, "the lane still opens");
    const spaces = runsOf(calls, "space.new");
    assert.equal(spaces.length, 1, `one space: ${JSON.stringify(calls.run)}`);
    assert.ok(adds[0].args.includes(spaces[0].folder), "in the added worktree");
    assert.equal(spaces[0].machine, "");
    assert.equal(spaces[0].argv, undefined, "a shell, not an agent");
    assert.equal(spaces[0].task, undefined);
    assert.ok(calls.notify.some((n) => String(n.body).includes("new worktree at")),
      JSON.stringify(calls.notify));
    notBubbled(calls);
    clean();
  }
});

test("a failed mv or rm while opening the lane is a Runway error toast and no space starts", async () => {
  for (const program of ["mv", "rm"]) {
    let hits = 0;
    const {calls} = world({...LOCAL, agents: WITH_CLAUDE, intercept: ({command}) =>
      (command === program && ++hits === 1 ? status(1, `${program}: Permission denied`) : undefined)});
    const panel = await openPanel();
    await confirmLane(panel, "Queue alpha");
    assert.ok(hits >= 1, `${program}: the lane ran ${program}`);
    const errors = calls.notify.filter((n) => n.level === "error");
    assert.ok(errors.length && errors.every((n) => n.title === "Runway"), `${program}: ${JSON.stringify(calls.notify)}`);
    assert.ok(!calls.notify.some((n) => !failed(n) && String(n.body).includes("00010-alpha.md")),
      `${program}: no success toast`);
    assert.deepEqual(runsOf(calls, "space.new"), [], `${program}: no space for a lane whose move failed`);
    assert.ok(!hasSpinner(cardOf(panel.render(), "Queue alpha")), `${program}: busy ring cleared`);
    clean();
  }
});

test("a failed worktree add posts a Runway error toast, clears the ring and frees the next click", async () => {
  let failing = true;
  const isAdd = (command, args) => command === "git" && args.includes("worktree") && args.includes("add");
  const {calls} = world({...LOCAL, agents: WITH_CLAUDE,
    intercept: ({command, args}) => (failing && isAdd(command, args) ? status(128, "fatal: cannot lock ref") : undefined)});
  const panel = await openPanel();
  await confirmLane(panel, "Queue alpha");
  const error = calls.notify.find((n) => n.level === "error");
  assert.ok(error, `error toast: ${JSON.stringify(calls.notify)}`);
  assert.equal(error.title, "Runway");
  assert.ok(String(error.body ?? "").trim(), "the error message is shown");
  assert.deepEqual(runsOf(calls, "space.new"), [], "no space for a failed lane");
  assert.ok(!hasSpinner(cardOf(panel.render(), "Queue alpha")), "busy ring cleared");
  failing = false;
  await confirmLane(panel, "Queue alpha");
  assert.equal(gitCalls(calls, "worktree", "add").length, 2, "the lane flag was released");
  assert.equal(runsOf(calls, "space.new").length, 1, "the retry opens the space");
  clean();
});

// The branch a lane for this card creates, learned from a fake successful open (no real git runs).
async function laneBranch(fixture, title) {
  const {calls} = world({...fixture, agents: WITH_CLAUDE});
  const panel = await openPanel();
  await confirmLane(panel, title);
  const args = gitCalls(calls, "worktree", "add")[0]?.args ?? [];
  const at = args.findIndex((a) => a === "-b" || a === "-B");
  assert.ok(at >= 0 && args[at + 1], `the lane creates a named branch: ${args}`);
  return args[at + 1];
}

test("a planned lane whose branch already exists is an error toast and nothing is added or started", async () => {
  const branch = await laneBranch(LOCAL, "Queue alpha");
  const {calls, fs} = world({...LOCAL, agents: WITH_CLAUDE, branches: [branch]});
  const before = [...fs.keys()];
  const panel = await openPanel();
  await confirmLane(panel, "Queue alpha");
  assert.ok(gitCalls(calls, "for-each-ref").length, "branches were listed");
  const errors = calls.notify.filter((n) => n.level === "error");
  assert.equal(errors.length, 1, `one error toast: ${JSON.stringify(calls.notify)}`);
  assert.ok(String(errors[0].body ?? "").trim(), "the toast says why");
  assert.deepEqual(gitCalls(calls, "worktree", "add"), [], "no worktree added");
  assert.deepEqual(mutations(calls), [], "no file moved, removed or made");
  assert.deepEqual(calls.run, [], "no space, tab or card start");
  assert.deepEqual([...fs.keys()], before, "the disk is untouched");
  assert.ok(!hasSpinner(cardOf(panel.render(), "Queue alpha")), "busy ring cleared");
  clean();
});

test("the clicked card shows the busy ring while its lane opens and another lane click is ignored", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const {calls} = world({...LOCAL, agents: WITH_CLAUDE, intercept: ({command, args, real}) =>
    (command === "git" && args.includes("worktree") && args.includes("add") ? gate.then(real) : undefined)});
  const panel = await openPanel();
  assert.ok(!hasSpinner(cardOf(panel.render(), "Queue alpha")), "no ring before the click");
  await confirmLane(panel, "Queue alpha");
  const tree = panel.render();
  assert.ok(hasSpinner(cardOf(tree, "Queue alpha")), "ring while the lane opens");
  assert.ok(!hasSpinner(cardOf(tree, "Queue beta")), "busy is per card");
  await press(panel, "Queue beta", LANE);
  assert.equal(gitCalls(calls, "worktree", "add").length, 1, "no second lane while one opens");
  release();
  await settle();
  assert.ok(!hasSpinner(cardOf(panel.render(), "Queue alpha")), "ring gone once settled");
  assert.equal(gitCalls(calls, "worktree", "add").length, 1, "the ignored click was not queued");
  assert.deepEqual(started(calls), [], "no agent starts");
  clean();
});
