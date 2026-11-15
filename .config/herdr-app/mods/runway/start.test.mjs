import assert from "node:assert/strict";
import { test } from "node:test";
import { pickOf, startFor, startLabel } from "./start.js";

const PRDS = "docs/dev/project-management/prds";

function prdCard(name, stage, next, { title = "Gamma", checkout = "/repo", bucket = "wip", group = "prd" } = {}) {
  return {
    id: `prd:${name}`,
    kind: "prd",
    number: name.slice(0, 5),
    title,
    group,
    stage,
    next,
    detail: "",
    reason: "",
    checkout,
    file: `${checkout}/${PRDS}/${bucket}/${name}`,
  };
}

function specCard(name, stage, next, { title, checkout = "/repo", specsDir = "docs/specs", group = "spec" } = {}) {
  return {
    id: `spec:${name}`,
    kind: "spec",
    number: name.slice(0, 5),
    title: title ?? name.slice(6).replaceAll("-", " "),
    group,
    stage,
    next,
    detail: "",
    reason: "",
    checkout,
    file: `${checkout}/${specsDir}/${name}/requirements.md`,
  };
}

const agent = (key, name, run) => ({ key, name, run, installed: true });
const CLAUDE = agent("claude", "Claude", ["claude"]);
const CODEX = agent("codex", "Codex", ["codex", "--no-daemon"]);
const KIRO = agent("kiro", "Kiro", ["kiro-cli", "chat"]);
const GEMINI = agent("gemini", "Gemini", ["gemini"]);
const COPILOT = agent("copilot", "Copilot", ["copilot"]);
const CLAUDE_ALT = agent("claude-alt", "Claude (alt)", ["my-claude-alt"]);

const ALL_SPECFLOW = { claude: true, codex: true, kiro: true };
const NO_SPECFLOW = { claude: false, codex: false, kiro: false };
const env = (pick = null, on = null, specflow = ALL_SPECFLOW) => ({ pick, on, specflow });

const plain = (kind, number, title, rel, stage, label) =>
  `Work on ${kind} ${number} "${title}" in ${rel}. Its stage is ${stage}. Do only this next stage: ${label}. ` +
  "Follow the repository's workflow documents. Stop when that stage is done.";

const GAMMA = prdCard("00012-gamma.md", "build", "review, cycle 1", { checkout: "/wt/gamma" });
const GAMMA_TASK =
  'Work on PRD 00012 "Gamma" in docs/dev/project-management/prds/wip/00012-gamma.md. Its stage is build. ' +
  "Do only this next stage: Start review, cycle 1. Follow the repository's workflow documents. Stop when that stage is done.";
const ALPHA = prdCard("00010-alpha.md", "backlog", "build", { title: "Alpha queue", bucket: "backlog" });
const ALPHA_TASK = plain("PRD", "00010", "Alpha queue", `${PRDS}/backlog/00010-alpha.md`, "backlog", "Start build");

const QUEUE = specCard("00008-queue-view", "tasks", "design gate");
const LANES = specCard("00007-runway-cards", "implementation", "task T4", { checkout: "/wt/s7", specsDir: "specs/v2" });

const co = (buckets) => ({
  path: "/repo",
  branch: "master",
  main: true,
  buckets: { backlog: [], wip: [], hold: [], done: [], ...buckets },
  state: null,
});
const frozen = (list) => Object.freeze([...list]);

test("pick_is_lowest_wip_then_lowest_backlog", () => {
  const wip = frozen(["00031-c.md", "00012-gamma.md", "00020-b.md"]);
  assert.equal(pickOf(co({ wip, backlog: frozen(["00001-a.md"]) })), "00012-gamma.md");
  assert.deepEqual(wip, ["00031-c.md", "00012-gamma.md", "00020-b.md"]);
  assert.equal(pickOf(co({ wip: frozen(["00041-y.md", "00040-x.md"]) })), "00040-x.md");
  assert.equal(pickOf(co({ wip: frozen(["00050-only.md"]) })), "00050-only.md");

  // No wip: the lowest backlog name, by name order, not list order.
  const backlog = frozen(["00100-z.md", "00099-y.md", "00203-q.md"]);
  assert.equal(pickOf(co({ backlog })), "00099-y.md");
  const others = { hold: frozen(["00001-held.md"]), done: frozen(["00002-done.md"]) };
  assert.equal(pickOf(co({ backlog: frozen(["00010-alpha.md", "00009-z.md"]), ...others })), "00009-z.md");

  // Hold and done are never the pick.
  assert.equal(pickOf(co(others)), null);
  assert.equal(pickOf(co({})), null);
});

test("labels_each_prd_stage", () => {
  const label = (stage, next, bucket = "wip") => startLabel(prdCard("00012-gamma.md", stage, next, { bucket }));
  assert.equal(label("paused", "build"), "Resume");
  assert.equal(label("paused", "review, cycle 2"), "Resume");
  assert.equal(label("backlog", "build", "backlog"), "Start build");
  assert.equal(label("wip", "build"), "Start build");
  assert.equal(label("build", "review, cycle 1"), "Start review, cycle 1");
  assert.equal(label("review", "review, cycle 2"), "Start review, cycle 2");
  assert.equal(label("review", "build"), "Start rework");
  assert.equal(label("review", "done"), "Finish");
  assert.equal(label("closed", "done"), "Finish");
  assert.equal(label("build", "build"), "Continue build");

  // Any other case has no button, near misses included.
  assert.equal(label("closed", ""), null);
  assert.equal(label("closed", "close"), null);
  assert.equal(label("done", ""), null);
  assert.equal(label("review", ""), null);
  assert.equal(label("build", ""), null);
  assert.equal(label("closed", "undone"), null);
  assert.equal(label("closed", "pre-review"), null);
  assert.equal(label("build", "rebuild"), null);
  assert.equal(label("reviewing", "build"), null);
});

test("parked_and_idea_cards_have_no_label", () => {
  assert.equal(startLabel(prdCard("00030-paused.md", "parked", "", { bucket: "hold", group: "parked" })), null);
  // The group decides before stage and next would give a label.
  assert.equal(startLabel(prdCard("00031-held.md", "backlog", "build", { group: "parked" })), null);
  assert.equal(startLabel(prdCard("00031-held.md", "backlog", "build")), "Start build");
  assert.equal(startLabel(specCard("00008-queue-view", "tasks", "design gate", { group: "parked" })), null);
  assert.equal(startLabel(specCard("00008-queue-view", "tasks", "design gate")), "Continue: design gate");

  const idea = {
    id: "idea:00022-late",
    kind: "idea",
    number: "00022",
    title: "late",
    group: "idea",
    stage: "idea",
    next: "",
    detail: "",
    reason: "",
    checkout: "/wt/two",
    file: "/wt/two/docs/dev/project-management/intake/new/00022-late/idea.md",
  };
  assert.equal(startLabel(idea), null);
  assert.equal(startLabel({ ...idea, next: "build" }), null);
});

test("spec_label_names_next_gate", () => {
  assert.equal(startLabel(QUEUE), "Continue: design gate");
  assert.equal(startLabel(LANES), "Continue: task T4");
  assert.equal(startLabel(specCard("00009-lanes", "tasks", "implementation gate")), "Continue: implementation gate");
  // No next: the stage names it.
  assert.equal(startLabel(specCard("00009-lanes", "implementation", "")), "Continue: implementation");
  assert.equal(startLabel(specCard("00010-other", "design", "")), "Continue: design");
});

test("claude_prd_start_sends_run_autopilot_with_bare_file_name", () => {
  const a = startFor(GAMMA, CLAUDE, env("00012-gamma.md"));
  assert.deepEqual(a.argv, ["claude"]);
  assert.equal(a.task, "/autopilot:run-autopilot 00012-gamma.md");
  assert.equal(a.name, "00012 Claude");
  assert.equal(a.gated, true);
  assert.ok(!a.disabled);

  // argv follows agent.run; claude is gated on any machine; no pick means no gate on the pick.
  const custom = agent("claude", "Claude Code", ["my-claude", "--fast"]);
  const b = startFor(ALPHA, custom, env(null, "vps", NO_SPECFLOW));
  assert.deepEqual(b.argv, ["my-claude", "--fast"]);
  assert.equal(b.task, "/autopilot:run-autopilot 00010-alpha.md");
  assert.equal(b.name, "00010 Claude Code");
  assert.equal(b.gated, true);
  assert.ok(!b.disabled);
  assert.deepEqual(custom.run, ["my-claude", "--fast"]);
});

test("local_codex_prd_start_runs_autocodex_once", () => {
  const a = startFor(GAMMA, CODEX, env("00012-gamma.md", null));
  assert.deepEqual(a.argv, ["autocodex", "--once"]);
  assert.ok(!a.task);
  assert.equal(a.name, "00012 Codex");
  assert.equal(a.gated, true);
  assert.ok(!a.disabled);

  // agent.run is not used, and specflow does not matter for a PRD.
  const other = agent("codex", "OpenAI Codex", ["codex-nightly"]);
  const b = startFor(ALPHA, other, env(null, null, NO_SPECFLOW));
  assert.deepEqual(b.argv, ["autocodex", "--once"]);
  assert.ok(!b.task);
  assert.equal(b.name, "00010 OpenAI Codex");
  assert.equal(b.gated, true);
  assert.ok(!b.disabled);
});

test("remote_codex_prd_start_is_ungated", () => {
  const a = startFor(GAMMA, CODEX, env("00012-gamma.md", "vps"));
  assert.deepEqual(a.argv, ["codex", "--no-daemon"]);
  assert.equal(a.task, GAMMA_TASK);
  assert.equal(a.name, "00012 Codex");
  assert.equal(a.gated, false);
  assert.ok(!a.disabled);

  const b = startFor(ALPHA, CODEX, env(null, "build-box"));
  assert.deepEqual(b.argv, ["codex", "--no-daemon"]);
  assert.equal(b.task, ALPHA_TASK);
  assert.equal(b.gated, false);
});

test("other_agent_prd_start_is_ungated_plain_task", () => {
  const a = startFor(GAMMA, GEMINI, env("00012-gamma.md"));
  assert.deepEqual(a.argv, ["gemini"]);
  assert.equal(a.task, GAMMA_TASK);
  assert.equal(a.name, "00012 Gemini");
  assert.equal(a.gated, false);
  assert.ok(!a.disabled);

  // A key that only starts with "claude" is another agent.
  const b = startFor(ALPHA, CLAUDE_ALT, env(null));
  assert.deepEqual(b.argv, ["my-claude-alt"]);
  assert.equal(b.task, ALPHA_TASK);
  assert.equal(b.name, "00010 Claude (alt)");
  assert.equal(b.gated, false);

  // Kiro is gated only for specs.
  const c = startFor(prdCard("00014-two-words.md", "review", "build", { title: "Two words", checkout: "/wt/side" }), KIRO, env(null));
  assert.equal(c.task, plain("PRD", "00014", "Two words", `${PRDS}/wip/00014-two-words.md`, "review", "Start rework"));
  assert.equal(c.gated, false);
  assert.equal(c.name, "00014 Kiro");
});

test("gated_prd_start_is_disabled_off_the_pick", () => {
  for (const [who, on] of [[CLAUDE, null], [CLAUDE, "vps"], [CODEX, null]]) {
    const a = startFor(GAMMA, who, env("00010-alpha.md", on));
    assert.equal(a.disabled, true, `${who.key}@${on}`);
    assert.equal(a.tip, "autopilot 0.10.0 starts 00010-alpha.md first");
  }
  assert.equal(startFor(GAMMA, CLAUDE, env("00011-beta.md")).tip, "autopilot 0.10.0 starts 00011-beta.md first");

  // Near misses of the card's own name are other PRDs.
  for (const near of ["00012-gamma-v2.md", "x00012-gamma.md", "00012-gamma"]) {
    const a = startFor(GAMMA, CLAUDE, env(near));
    assert.equal(a.disabled, true, near);
    assert.equal(a.tip, `autopilot 0.10.0 starts ${near} first`);
  }

  // The pick itself, or no pick, starts.
  assert.ok(!startFor(GAMMA, CLAUDE, env("00012-gamma.md")).disabled);
  assert.ok(!startFor(GAMMA, CODEX, env("00012-gamma.md")).disabled);
  assert.ok(!startFor(GAMMA, CLAUDE, env(null)).disabled);
  assert.ok(!startFor(GAMMA, CODEX, env(null)).disabled);
});

test("ungated_start_is_never_disabled_by_the_pick", () => {
  const off = env("00010-alpha.md");
  for (const who of [GEMINI, COPILOT, CLAUDE_ALT, KIRO]) {
    const a = startFor(GAMMA, who, off);
    assert.ok(!a.disabled, who.key);
    assert.equal(a.gated, false, who.key);
    assert.equal(a.task, GAMMA_TASK, who.key);
  }
  const remote = startFor(GAMMA, CODEX, env("00010-alpha.md", "vps"));
  assert.ok(!remote.disabled);
  assert.equal(remote.gated, false);
  assert.equal(remote.task, GAMMA_TASK);

  // The pick rule is for PRDs only: a spec start ignores it.
  const spec = startFor(QUEUE, CLAUDE, env("00010-alpha.md"));
  assert.ok(!spec.disabled);
  assert.equal(spec.gated, true);
});

test("spec_start_sends_continue_with_claude_prefix", () => {
  const a = startFor(QUEUE, CLAUDE, env(null));
  assert.deepEqual(a.argv, ["claude"]);
  assert.equal(a.task, "/specflow:spec-workflow Continue spec 00008-queue-view");
  assert.equal(a.name, "00008 Claude");
  assert.equal(a.gated, true);
  assert.ok(!a.disabled);

  for (const [who, on] of [[CODEX, null], [CODEX, "vps"], [KIRO, null]]) {
    const b = startFor(LANES, who, env(null, on));
    assert.deepEqual(b.argv, who.run, `${who.key}@${on}`);
    assert.equal(b.task, "Continue spec 00007-runway-cards", `${who.key}@${on}`);
    assert.equal(b.name, `00007 ${who.name}`);
    assert.equal(b.gated, true);
    assert.ok(!b.disabled);
  }
  assert.equal(startFor(LANES, CLAUDE, env(null)).task, "/specflow:spec-workflow Continue spec 00007-runway-cards");
});

test("spec_start_is_disabled_without_specflow", () => {
  const some = { claude: false, codex: true, kiro: false };
  assert.equal(startFor(QUEUE, CLAUDE, env(null, null, some)).disabled, true);
  assert.equal(startFor(QUEUE, CLAUDE, env(null, null, some)).tip, "specflow is not installed for Claude");
  assert.equal(startFor(QUEUE, KIRO, env(null, null, some)).tip, "specflow is not installed for Kiro");
  assert.equal(startFor(QUEUE, KIRO, env(null, null, some)).disabled, true);
  assert.ok(!startFor(QUEUE, CODEX, env(null, null, some)).disabled);

  // The flag of the starting agent decides, not the others.
  const flipped = { claude: true, codex: false, kiro: true };
  const codex = startFor(LANES, CODEX, env(null, "vps", flipped));
  assert.equal(codex.disabled, true);
  assert.equal(codex.tip, "specflow is not installed for Codex");
  assert.ok(!startFor(LANES, CLAUDE, env(null, null, flipped)).disabled);
  assert.ok(!startFor(LANES, KIRO, env(null, null, flipped)).disabled);
  const renamed = agent("claude", "Claude Code", ["claude"]);
  assert.equal(startFor(LANES, renamed, env(null, null, NO_SPECFLOW)).tip, "specflow is not installed for Claude Code");

  // Other agents need no specflow: an ungated plain task naming the spec.
  const a = startFor(QUEUE, GEMINI, env(null, null, NO_SPECFLOW));
  assert.ok(!a.disabled);
  assert.equal(a.gated, false);
  assert.deepEqual(a.argv, ["gemini"]);
  assert.equal(a.task, plain("spec", "00008", "queue view", "docs/specs/00008-queue-view/requirements.md", "tasks", "Continue: design gate"));
  const b = startFor(LANES, CLAUDE_ALT, env(null, null, NO_SPECFLOW));
  assert.equal(b.task, plain("spec", "00007", "runway cards", "specs/v2/00007-runway-cards/requirements.md", "implementation", "Continue: task T4"));
  assert.equal(b.gated, false);
});

test("copilot_gets_dash_i", () => {
  const a = startFor(GAMMA, COPILOT, env("00010-alpha.md"));
  assert.deepEqual(a.argv, ["copilot", "-i"]);
  assert.equal(a.task, GAMMA_TASK);
  assert.equal(a.name, "00012 Copilot");
  assert.equal(a.gated, false);

  const wrapped = agent("copilot", "GitHub Copilot", ["gh", "copilot", "--banner"]);
  const b = startFor(QUEUE, wrapped, env(null, null, NO_SPECFLOW));
  assert.deepEqual(b.argv, ["gh", "copilot", "--banner", "-i"]);
  assert.equal(b.task, plain("spec", "00008", "queue view", "docs/specs/00008-queue-view/requirements.md", "tasks", "Continue: design gate"));
  assert.deepEqual(wrapped.run, ["gh", "copilot", "--banner"]);

  // Only copilot gets it.
  assert.deepEqual(startFor(GAMMA, GEMINI, env(null)).argv, ["gemini"]);
  assert.deepEqual(startFor(ALPHA, CLAUDE_ALT, env(null)).argv, ["my-claude-alt"]);
});
