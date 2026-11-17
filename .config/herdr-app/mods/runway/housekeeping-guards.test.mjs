import assert from "node:assert/strict";
import {test} from "node:test";
import {LANE, LOCAL, PM, SPECS, WITH_CLAUDE, cardOf, clean, labelled, mutations, openPanel,
  press, runsOf, spec, status, unfoldParked, world} from "./housekeeping-harness.mjs";

test("a held main spec still offers New worktree beside Resume", async () => {
  world({...SPECS, agents: WITH_CLAUDE, checkouts: [
    {...SPECS.checkouts[0], specflow: [spec("00009-cross-host-validation", "waiting")]}, SPECS.checkouts[1]]});
  const panel = await openPanel();
  await unfoldParked(panel);
  const card = cardOf(panel.render(), "cross host validation");
  assert.ok(labelled(card, "Resume"));
  assert.ok(labelled(card, LANE), "main specs can open lanes even when held");
  clean();
});

test("intake uses its checkout's config rather than another checkout's config", async () => {
  const cases = [
    [{...LOCAL.checkouts[0]}, {...LOCAL.checkouts[1], config: true}],
    [{...LOCAL.checkouts[0], config: true, intake: []}, {...LOCAL.checkouts[1], intake: ["00022-late"]}],
  ];
  for (const checkouts of cases) {
    world({...LOCAL, checkouts, agents: WITH_CLAUDE});
    const panel = await openPanel();
    const card = cardOf(panel.render(), "Late idea");
    assert.ok(labelled(card, "Elicit"), "this idea's checkout has no specflow config");
    assert.equal(labelled(card, "Create spec"), undefined);
    clean();
  }
});

test("a failed specflow config probe keeps every card and falls back to Elicit", async () => {
  const probe = ({command, args}) => command === "test" && args[0] === "-e" && args.at(-1).endsWith("/.agents/specflow.json");
  const failures = [() => status(2, "test: permission denied"), () => Promise.reject(new Error("machine unreachable"))];
  for (const fail of failures) {
    world({...LOCAL, agents: WITH_CLAUDE, intercept: (e) => (probe(e) ? fail() : undefined)});
    const panel = await openPanel();
    const tree = panel.render();
    assert.ok(cardOf(tree, "Queue alpha"), "an optional intake hint never hides the queue");
    const idea = cardOf(tree, "Late idea");
    assert.ok(labelled(idea, "Elicit"), "an unknown config reads as no config");
    assert.equal(labelled(idea, "Create spec"), undefined);
    clean();
  }
});

test("an unreadable lane state guard stops before any PRD move or agent start", async () => {
  const {calls} = world({...LOCAL, agents: WITH_CLAUDE, intercept: ({command, args}) =>
    command === "test" && args[0] === "-e" && args.at(-1).endsWith("/autopilot/state.json")
      ? status(2, "test: permission denied") : undefined});
  const panel = await openPanel();
  await press(panel, "Queue alpha", LANE);
  assert.deepEqual(mutations(calls), [], "unknown state must never be treated as absent");
  assert.deepEqual(runsOf(calls, "space.new"), []);
  assert.ok(calls.notify.some((n) => n.level === "error" && /permission denied/.test(n.body)));
  clean();
});

test("an unreadable un-park destination stops before moving the parked PRD", async () => {
  const dst = `/work/app/${PM}/prds/backlog/00030-paused.md`;
  const {calls} = world({...LOCAL, agents: WITH_CLAUDE, intercept: ({command, args}) =>
    command === "test" && args[0] === "-e" && args.at(-1) === dst
      ? status(2, "test: permission denied") : undefined});
  const panel = await openPanel();
  await unfoldParked(panel);
  await press(panel, "Paused thing", "Un-park");
  assert.deepEqual(mutations(calls), [], "an unknown destination is not safe to move onto");
  assert.ok(calls.notify.some((n) => n.level === "error" && /permission denied/.test(n.body)));
  clean();
});
