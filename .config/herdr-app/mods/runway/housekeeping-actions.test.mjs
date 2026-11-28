import assert from "node:assert/strict";
import {test} from "node:test";
import {CLAUDE, LANE, LOCAL, NO_CLAUDE, PLUGIN, PM, REMOTE, SPECS, WITH_CLAUDE, cardOf, clean, click, exists,
  failed, hasSpinner, labelled, mutations, norm, notBubbled, ok, openPanel, press, reloads, runsOf, settle, spec,
  started, status, unfoldParked, walk, world} from "./housekeeping-harness.mjs";

// Un-park, Resume and intake controls (actionFor's result); lane and loop are in housekeeping.test.mjs.
const UNPARK = "Un-park";
const RESUME = "Resume";
const ELICIT = "Elicit";
const CREATE = "Create spec";
const TRIAGE_TIP = "Triage stub: promote it by writing a PRD";
// A tip shows as card text or as a string argument of one of its elements (a tooltip).
const shows = (card, tip) => norm(card).includes(tip) ||
  walk(card).some((n) => n.calls.some(([, args]) => args.some((a) => typeof a === "string" && a.includes(tip))));

async function parkedControl(panel, title, label) {
  await unfoldParked(panel);
  const card = cardOf(panel.render(), title);
  const control = labelled(card, label);
  assert.ok(control, `${title} offers ${label}: ${norm(card)}`);
  return {card, control};
}

test("un-park moves the hold PRD to backlog on the card's machine, checks it landed and reloads", async () => {
  const cases = [{fixture: LOCAL, title: "Paused thing", file: "00030-paused.md", root: "/work/app", on: null},
    {fixture: REMOTE, title: "Far thing", file: "00031-far.md", root: "/srv/app", on: "vps"}];
  for (const c of cases) {
    const {calls, fs} = world({...c.fixture, agents: WITH_CLAUDE});
    const src = `${c.root}/${PM}/prds/hold/${c.file}`;
    const dst = `${c.root}/${PM}/prds/backlog/${c.file}`;
    const panel = await openPanel();
    const {card, control} = await parkedControl(panel, c.title, UNPARK);
    const before = reloads(calls);
    await click(control, card);
    const moves = calls.exec.filter((e) => e.command === "mv");
    assert.equal(moves.length, 1, "one mv");
    assert.deepEqual(moves[0].args.slice(-2), [src, dst]);
    assert.ok(moves[0].args.includes("-n") && moves[0].args.includes("--"), `no-clobber argv: ${moves[0].args}`);
    assert.equal(moves[0].options?.on ?? null, c.on, "mv runs on the card's machine");
    assert.ok(calls.exec.some((e) => e.command === "test" && e.args.at(-1) === dst && (e.options?.on ?? null) === c.on),
      "the new path is checked there");
    assert.ok(exists(fs, dst) && !exists(fs, src), "the PRD is queued");
    assert.deepEqual(calls.notify.filter(failed), [], "no failure toast");
    assert.deepEqual(started(calls), [], "a move starts no agent");
    assert.ok(reloads(calls) > before, "the panel reloads");
    assert.doesNotMatch(norm(panel.render()), /Parked \(1\)/, "the card left Parked");
    notBubbled(calls);
    clean();
  }
});

test("un-park shows the busy ring on its card until the move settles", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  world({...LOCAL, agents: WITH_CLAUDE, intercept: ({command, real}) => (command === "mv" ? gate.then(real) : undefined)});
  const panel = await openPanel();
  const {card, control} = await parkedControl(panel, "Paused thing", UNPARK);
  assert.ok(!hasSpinner(card), "no ring before the click");
  await click(control, card);
  assert.ok(hasSpinner(cardOf(panel.render(), "Paused thing")), "ring while the PRD moves");
  release();
  await settle();
  assert.ok(!hasSpinner(panel.render()), "ring gone once settled");
  clean();
});

test("ledger_key outside the frontmatter does not make a triage stub: Un-park stays enabled and moves", async () => {
  const text = "# Paused thing\n\nledger_key: X\n";
  const checkouts = [{...LOCAL.checkouts[0], texts: {"00030-paused.md": text}}, LOCAL.checkouts[1]];
  const {calls, fs} = world({...LOCAL, checkouts, agents: WITH_CLAUDE});
  const panel = await openPanel();
  const {card, control} = await parkedControl(panel, "Paused thing", UNPARK);
  assert.ok(!shows(card, TRIAGE_TIP), `not a stub: ${norm(card)}`);
  await click(control, card);
  assert.equal(fs.get(`/work/app/${PM}/prds/backlog/00030-paused.md`), text, "the PRD is queued");
  assert.ok(!exists(fs, `/work/app/${PM}/prds/hold/00030-paused.md`), "and left hold");
  assert.deepEqual(calls.notify.filter(failed), [], "no failure toast");
  clean();
});

test("un-park refuses when backlog already holds the file and never overwrites the queued PRD", async () => {
  const {calls, fs} = world({...LOCAL, agents: WITH_CLAUDE});
  const src = `/work/app/${PM}/prds/hold/00030-paused.md`;
  const dst = `/work/app/${PM}/prds/backlog/00030-paused.md`;
  const panel = await openPanel();
  const {card, control} = await parkedControl(panel, "Paused thing", UNPARK);
  fs.set(dst, "# Queued meanwhile\n");
  await click(control, card);
  assert.deepEqual(calls.exec.filter((e) => e.command === "mv"), [], "no mv onto a queued PRD");
  assert.equal(fs.get(dst), "# Queued meanwhile\n", "the queued PRD is untouched");
  assert.ok(exists(fs, src), "the parked PRD stays put");
  assert.ok(calls.notify.some((n) => n.level === "error"), `error toast: ${JSON.stringify(calls.notify)}`);
  clean();
});

test("un-park surfaces a move that did not land, left its source behind, or failed", async () => {
  const src = `/work/app/${PM}/prds/hold/00030-paused.md`;
  const dst = `/work/app/${PM}/prds/backlog/00030-paused.md`;
  const modes = {
    miss: () => ok(),
    copy: (fs) => { fs.set(dst, fs.get(src)); return ok(); },
    fail: () => status(1, "mv: Permission denied"),
  };
  for (const [mode, fake] of Object.entries(modes)) {
    const {calls} = world({...LOCAL, agents: WITH_CLAUDE,
      intercept: ({command, fs}) => (command === "mv" ? fake(fs) : undefined)});
    const panel = await openPanel();
    const {card, control} = await parkedControl(panel, "Paused thing", UNPARK);
    await click(control, card);
    assert.equal(calls.exec.filter((e) => e.command === "mv").length, 1, `${mode}: one mv`);
    assert.ok(calls.notify.some(failed), `${mode}: failure surfaced: ${JSON.stringify(calls.notify)}`);
    if (mode === "miss") {
      assert.ok(calls.notify.some((n) => n.body === "Un-park did not complete for 00030-paused.md"),
        JSON.stringify(calls.notify));
    }
    if (mode === "fail") assert.ok(calls.notify.some((n) => n.level === "error"), "a failed mv is an error");
    assert.deepEqual(started(calls), []);
    clean();
  }
});

test("a parked PRD with ledger_key in its frontmatter is a triage stub: Un-park is disabled and moves nothing", async () => {
  for (const ledger of ["ledger_key: L-17", "ledger_key:"]) {
    const text = `---\n${ledger}\n---\n# Paused thing\n\nBody.\n`;
    const checkouts = [{...LOCAL.checkouts[0], texts: {"00030-paused.md": text}}, LOCAL.checkouts[1]];
    const {calls, fs} = world({...LOCAL, checkouts, agents: WITH_CLAUDE});
    const src = `/work/app/${PM}/prds/hold/00030-paused.md`;
    const panel = await openPanel();
    const {card, control} = await parkedControl(panel, "Paused thing", UNPARK);
    assert.ok(shows(card, TRIAGE_TIP), `${ledger}: tip "${TRIAGE_TIP}" in: ${norm(card)}`);
    const before = calls.exec.length;
    await click(control, card);
    assert.deepEqual(calls.exec.slice(before).filter((e) => e.command === "mv" || e.command === "test"), [],
      `${ledger}: nothing moved or checked`);
    assert.deepEqual(mutations(calls), [], `${ledger}: no file program ran`);
    assert.equal(fs.get(src), text, `${ledger}: the stub stays parked`);
    assert.ok(!exists(fs, `/work/app/${PM}/prds/backlog/00030-paused.md`), `${ledger}: nothing queued`);
    assert.deepEqual(calls.run, [], `${ledger}: no agent, tab or card start`);
    clean();
  }
});

// Main owns a parked (held) spec beside the parked PRD.
const PARKED_SPEC = {...SPECS, checkouts: [
  {...SPECS.checkouts[0], specflow: [spec("00009-cross-host-validation", "waiting on upstream")]},
  SPECS.checkouts[1]]};

test("a parked main spec offers Resume, which starts Claude with the resume task in main's space", async () => {
  const {calls} = world({...PARKED_SPEC, agents: WITH_CLAUDE});
  const panel = await openPanel();
  const {card, control} = await parkedControl(panel, "cross host validation", RESUME);
  assert.equal(labelled(card, UNPARK), undefined, "a parked spec is not un-parked like a PRD");
  const paused = cardOf(panel.render(), "Paused thing");
  assert.ok(labelled(paused, UNPARK), "the parked PRD keeps Un-park");
  assert.equal(labelled(paused, RESUME), undefined, "the parked PRD has no Resume");
  assert.equal(labelled(paused, LANE), undefined, "the parked PRD has no New worktree");
  await click(control, card);
  assert.deepEqual(calls.run, [
    ["space.select", {id: "s1"}],
    ["tab.new", {space: "s1", folder: "/work/app", name: "00009 Claude", argv: ["run-agent", ...CLAUDE.run],
      task: "/specflow:spec-workflow Resume 00009-cross-host-validation"}],
  ]);
  assert.deepEqual(mutations(calls), [], "Resume moves no file");
  clean();
});

const IDEAS = [["Late idea", "00022-late"], ["Early idea", "00023-early"]];
async function startIdeas(fixture, label, taskOf) {
  const {calls} = world({...fixture, agents: WITH_CLAUDE});
  const panel = await openPanel();
  for (const [title, name] of IDEAS) {
    calls.run.length = 0;
    const card = cardOf(panel.render(), title);
    assert.doesNotMatch(norm(card), /Needs Claude Code/, "enabled with Claude");
    assert.equal(labelled(card, label === ELICIT ? CREATE : ELICIT), undefined, `${title}: only ${label}`);
    await press(panel, title, label);
    assert.deepEqual(calls.run, [
      ["space.select", {id: "s1"}],
      ["tab.new", {space: "s1", folder: "/work/app", name: `${name.slice(0, 5)} Claude`, argv: ["run-agent", ...CLAUDE.run],
        task: taskOf(name)}],
    ], `${title}: select then tab, card click stopped`);
  }
  assert.deepEqual(mutations(calls), [], "an intake start moves no file");
  clean();
}

test("an idea in a repo without .agents/specflow.json offers Elicit with its number, plugin or not", async () => {
  for (const specflowDirs of [[], [PLUGIN]]) {
    await startIdeas({...LOCAL, specflowDirs}, ELICIT, (name) => `/elicit-requirements ${name.slice(0, 5)}`);
  }
});

test("an idea in a repo with .agents/specflow.json offers Create spec for its full name, plugin or not", async () => {
  const checkouts = [{...LOCAL.checkouts[0], config: true}, LOCAL.checkouts[1]];
  for (const specflowDirs of [[], [PLUGIN]]) {
    await startIdeas({...LOCAL, checkouts, specflowDirs}, CREATE,
      (name) => `/specflow:spec-workflow Create a spec for ${name}`);
  }
});

// /work/app has no space; the focus is in the worktree's space.
const NO_SPACE = {focusedPane: "p3", spaces: [LOCAL.spaces[0],
  {id: "s3", folder: "/wt/gamma", tabs: [{id: "t3", pane: "p3", cwd: "/wt/gamma"}]}]};

test("Resume, Elicit and Create spec without a space for main open a new space on this computer with the task", async () => {
  const config = [{...LOCAL.checkouts[0], config: true}, LOCAL.checkouts[1]];
  const cases = [
    {fixture: PARKED_SPEC, title: "cross host validation", label: RESUME, parked: true,
      task: "/specflow:spec-workflow Resume 00009-cross-host-validation"},
    {fixture: LOCAL, title: "Late idea", label: ELICIT, task: "/elicit-requirements 00022"},
    {fixture: {...LOCAL, checkouts: config}, title: "Late idea", label: CREATE,
      task: "/specflow:spec-workflow Create a spec for 00022-late"},
  ];
  for (const c of cases) {
    const {calls} = world({...c.fixture, ...NO_SPACE, agents: WITH_CLAUDE});
    const panel = await openPanel();
    if (c.parked) await unfoldParked(panel);
    await press(panel, c.title, c.label);
    const spaces = runsOf(calls, "space.new");
    assert.equal(spaces.length, 1, `${c.label}: one new space: ${JSON.stringify(calls.run)}`);
    const {folder, machine, argv, task} = spaces[0];
    assert.deepEqual({folder, machine, argv, task}, {folder: "/work/app", machine: "", argv: ["run-agent", ...CLAUDE.run], task: c.task});
    assert.deepEqual(runsOf(calls, "tab.new"), [], `${c.label}: no tab in another space`);
    notBubbled(calls);
    clean();
  }
});

test("without Claude the intake control is disabled with Needs Claude Code and starts nothing", async () => {
  for (const agents of NO_CLAUDE) {
    const {calls} = world({...LOCAL, agents});
    const panel = await openPanel();
    const card = cardOf(panel.render(), "Late idea");
    assert.match(norm(card), /Needs Claude Code/);
    for (const node of walk(card).slice(1).filter((n) => n.on.on_click)) await click(node, card);
    assert.deepEqual(started(calls), [], "no agent tab");
    clean();
  }
});
