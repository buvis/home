import assert from "node:assert/strict";
import { test } from "node:test";
import { newestVersion, ownItems, parseFrontmatter, parseListing, parseWorktrees, scanRefs, titleOf, toCard } from "./model.js";

const stem = (names) => names.map((n) => n.replace(/\.md$/, ""));

test("parses_worktree_list_porcelain", () => {
  const out = [
    "worktree /repo/main tree",
    "HEAD 1234abcd",
    "branch refs/heads/master",
    "",
    "worktree /wt/feature-x",
    "HEAD 5678ef01",
    "branch refs/heads/feature/x",
    "",
    "worktree /wt/detached",
    "HEAD 9abc0000",
    "detached",
    "",
  ].join("\n");
  assert.deepEqual(parseWorktrees(out), [
    { path: "/repo/main tree", branch: "master", main: true },
    { path: "/wt/feature-x", branch: "feature/x", main: false },
    { path: "/wt/detached", branch: null, main: false },
  ]);

  const other = "worktree /src/app\nHEAD aaaa\nbranch refs/heads/develop\n\nworktree /src/app-heads\nHEAD bbbb\nbranch refs/heads/bugfix/refs-heads\n";
  assert.deepEqual(parseWorktrees(other), [
    { path: "/src/app", branch: "develop", main: true },
    { path: "/src/app-heads", branch: "bugfix/refs-heads", main: false },
  ]);

  const unsorted = "worktree /z/repo\nHEAD dddd\nbranch refs/heads/master\n\nworktree /a/wt\nHEAD eeee\nbranch refs/heads/feature/a\n";
  assert.deepEqual(parseWorktrees(unsorted), [
    { path: "/z/repo", branch: "master", main: true },
    { path: "/a/wt", branch: "feature/a", main: false },
  ]);

  const detachedMain = "worktree /solo\nHEAD cccc\ndetached\n";
  assert.deepEqual(parseWorktrees(detachedMain), [{ path: "/solo", branch: null, main: true }]);

  assert.deepEqual(parseWorktrees(""), []);
});

const LISTING = [
  "warning: stray line",
  "00099-dropped.md",
  "@backlog",
  "00010-alpha.md",
  "00011-beta.md",
  "00203-y.md",
  "notes.txt",
  "00011-beta.md.bak",
  "@wip",
  "00012-gamma.md",
  "@hold",
  "@done",
  "00001-first.md",
  "00002-second.md",
  "00003-third.md",
  "00004-fourth.md",
  "00005-fifth.md",
  "@intake",
  "00020-idea.md",
  "0002-short.md",
  "x00021-prefixed.md",
  "README.md",
  "00022-other.md",
  "00203-y.md",
  "@specflow",
  "{",
  '  "specsDir": "docs/specs"',
  "}",
  "",
].join("\n");

function assertFrontmatterAndTitle() {
  const prd = "---\nid: 00203\nstatus: wip\npr: https://x/y\n---\n## Sub\n# Runway queue\nbody\n";
  assert.deepEqual(parseFrontmatter(prd), { id: "00203", status: "wip", pr: "https://x/y" });
  assert.deepEqual(parseFrontmatter("---\nstatus: done\nowner: tess\n---\nbody\n"), { status: "done", owner: "tess" });
  assert.deepEqual(parseFrontmatter("# Title\nno block here\n"), {});
  assert.deepEqual(parseFrontmatter("# Title\n---\nstatus: wip\n---\n"), {});
  assert.deepEqual(parseFrontmatter(""), {});

  assert.equal(titleOf(prd, "00203-y"), "Runway queue");
  assert.equal(titleOf("intro\n# Second title\n# Third\n", "fb"), "Second title");
  assert.equal(titleOf("## Sub only\n#NoSpace\nbody\n", "00010-alpha"), "00010-alpha");
  assert.equal(titleOf("", "00011-beta"), "00011-beta");
}

test("parses_listing_script_output", () => {
  const got = parseListing(LISTING);
  assert.deepEqual(stem(got.backlog), ["00010-alpha", "00011-beta", "00203-y"]);
  assert.deepEqual(stem(got.wip), ["00012-gamma"]);
  assert.deepEqual(got.hold, []);
  assert.deepEqual(stem(got.done), ["00001-first", "00002-second", "00003-third", "00004-fourth", "00005-fifth"]);
  assert.deepEqual(stem(got.intake), ["00020-idea", "00022-other", "00203-y"]);
  assert.deepEqual(JSON.parse(got.specflow), { specsDir: "docs/specs" });

  const other = parseListing('@hold\n00030-paused.md\n@specflow\n{\n"specsDir": "specs/v2"\n}\n@wip\n00031-busy.md\n');
  assert.deepEqual(stem(other.hold), ["00030-paused"]);
  assert.deepEqual(stem(other.wip), ["00031-busy"]);
  assert.deepEqual(other.backlog, []);
  assert.deepEqual(JSON.parse(other.specflow), { specsDir: "specs/v2" });

  const none = parseListing("");
  assert.deepEqual(
    { ...none },
    { backlog: [], wip: [], hold: [], done: [], intake: [], specflow: null },
  );
  assert.equal(parseListing("@backlog\n00040-only.md\n").specflow, null);

  assertFrontmatterAndTitle();
});

test("picks_newest_specflow_version", () => {
  assert.equal(newestVersion(["1.2.3", "1.10.0", "1.9.9"]), "1.10.0");
  assert.equal(newestVersion(["2.0.0", "10.0.0", "9.99.99"]), "10.0.0");
  assert.equal(newestVersion(["0.1.2", "0.1.10", "0.1.9"]), "0.1.10");
  assert.equal(newestVersion(["99.0.0", "100.0.0"]), "100.0.0");
  assert.equal(newestVersion(["1.0.99", "1.0.100"]), "1.0.100");
  assert.equal(newestVersion(["3.0.1", "latest", "notes.md", "4.0", "3.0.0"]), "3.0.1");
  assert.equal(newestVersion(["0.0.1"]), "0.0.1");
  assert.equal(newestVersion(["latest", "4.0", "README.md"]), null);
  assert.equal(newestVersion([]), null);

  const frozen = Object.freeze(["2.1.0", "2.10.0", "2.2.0"]);
  assert.equal(newestVersion(frozen), "2.10.0");
  assert.deepEqual(frozen, ["2.1.0", "2.10.0", "2.2.0"]);
});

const PRDS = "docs/dev/project-management/prds";
const CORE = ["id", "kind", "number", "title", "group", "stage", "next", "checkout", "file"];

function checkout(path, branch, main, extra = {}) {
  return {
    path,
    branch,
    main,
    buckets: { backlog: [], wip: [], hold: [], done: [], ...extra.buckets },
    intake: extra.intake ?? [],
    state: extra.state ?? null,
    wave: null,
    specs: extra.specs ?? null,
    specsDir: extra.specsDir ?? null,
  };
}

const prd = (name, bucket, co) => ({ kind: "prd", name, bucket, checkout: co });
const pick = (card, keys) => Object.fromEntries(keys.map((k) => [k, card[k]]));

function ownersOf(items, kind) {
  const mine = items.filter((i) => i.kind === kind);
  const map = Object.fromEntries(
    mine.map((i) => [i.name, kind === "prd" ? `${i.bucket}@${i.checkout.path}` : i.checkout.path]),
  );
  assert.equal(Object.keys(map).length, mine.length, `duplicate ${kind} items`);
  return map;
}

function wipCard(state, path = "/wt/gamma") {
  const co = checkout(path, "feature/gamma", false, { buckets: { wip: ["00012-gamma.md"] }, state });
  return toCard(prd("00012-gamma.md", "wip", co), "# Gamma\n", co);
}

test("backlog_prd_shows_backlog_and_next_build", () => {
  const state = { prd: "00010-alpha.md", phase: "build", next_phase: "review", cycle: 1 };
  const main = checkout("/repo", "master", true, { buckets: { backlog: ["00010-alpha.md", "00011-beta.md"] }, state });
  const side = checkout("/wt/side", "feature/side", false, { buckets: { backlog: ["00014-two-words.md"] } });

  assert.deepEqual(ownersOf(ownItems([main, side]), "prd"), {
    "00010-alpha.md": "backlog@/repo",
    "00011-beta.md": "backlog@/repo",
    "00014-two-words.md": "backlog@/wt/side",
  });
  assert.deepEqual(ownItems([]), []);

  const a = toCard(prd("00010-alpha.md", "backlog", main), "---\nid: 00010\n---\n# Alpha queue\nbody\n", main);
  assert.deepEqual(pick(a, CORE), {
    id: "prd:00010-alpha.md",
    kind: "prd",
    number: "00010",
    title: "Alpha queue",
    group: "prd",
    stage: "backlog",
    next: "build",
    checkout: "/repo",
    file: `/repo/${PRDS}/backlog/00010-alpha.md`,
  });

  const b = toCard(prd("00014-two-words.md", "backlog", side), "no heading here\n", side);
  assert.deepEqual(pick(b, CORE), {
    id: "prd:00014-two-words.md",
    kind: "prd",
    number: "00014",
    title: "two-words",
    group: "prd",
    stage: "backlog",
    next: "build",
    checkout: "/wt/side",
    file: `/wt/side/${PRDS}/backlog/00014-two-words.md`,
  });

  // checkout and file follow the third argument, even when item.checkout is another object.
  const moved = toCard(prd("00010-alpha.md", "backlog", main), "", side);
  assert.deepEqual(pick(moved, ["checkout", "file", "title"]), {
    checkout: "/wt/side",
    file: `/wt/side/${PRDS}/backlog/00010-alpha.md`,
    title: "alpha",
  });
});

test("wip_prd_in_build_shows_task_progress", () => {
  const busy = { prd: "00012-gamma.md", phase: "build", tasks_completed: 3, tasks_total: 7, next_phase: "review", cycle: 1 };
  const a = wipCard(busy);
  assert.deepEqual(pick(a, [...CORE, "detail"]), {
    id: "prd:00012-gamma.md",
    kind: "prd",
    number: "00012",
    title: "Gamma",
    group: "prd",
    stage: "build",
    next: "review, cycle 1",
    checkout: "/wt/gamma",
    file: `/wt/gamma/${PRDS}/wip/00012-gamma.md`,
    detail: "3/7 tasks",
  });

  const fresh = wipCard({ prd: "00012-gamma.md", phase: "build", tasks_completed: 0, tasks_total: 5, next_phase: "build" }, "/wt/g2");
  assert.equal(fresh.detail, "0/5 tasks");
  assert.equal(fresh.next, "build");
  assert.equal(fresh.checkout, "/wt/g2");

  const unplanned = wipCard({ prd: "00012-gamma.md", phase: "build", tasks_completed: 0, tasks_total: 0, next_phase: "build" });
  assert.equal(unplanned.stage, "build");
  assert.equal(unplanned.detail, "");
});

test("wip_prd_in_review_shows_cycle_of_cap", () => {
  const a = wipCard({ prd: "00012-gamma.md", phase: "review", cycle: 2, rework_cap: 3, next_phase: "review" });
  assert.deepEqual(pick(a, ["stage", "detail", "next", "group"]), {
    stage: "review",
    detail: "cycle 2 of 3",
    next: "review, cycle 2",
    group: "prd",
  });

  const b = wipCard({ prd: "00012-gamma.md", phase: "review", cycle: 1, rework_cap: 4, next_phase: "build" });
  assert.deepEqual(pick(b, ["stage", "detail", "next"]), { stage: "review", detail: "cycle 1 of 4", next: "build" });

  const paused = wipCard({ prd: "00012-gamma.md", phase: "paused", pause_reason: { detail: "needs creds" }, next_phase: "build" });
  assert.deepEqual(pick(paused, ["stage", "detail"]), { stage: "paused", detail: "needs creds" });

  const bare = wipCard({ prd: "00012-gamma.md", phase: "paused", next_phase: "build" });
  assert.deepEqual(pick(bare, ["stage", "detail"]), { stage: "paused", detail: "" });
});

test("wip_prd_without_matching_state_shows_no_state", () => {
  const expected = { stage: "wip", detail: "no state", next: "build", group: "prd" };
  const keys = Object.keys(expected);
  const phase = { phase: "review", cycle: 2, rework_cap: 3, next_phase: "review" };

  assert.deepEqual(pick(wipCard(null), keys), expected);
  assert.deepEqual(pick(wipCard({ prd: "00012-gamma-v2.md", ...phase }), keys), expected);
  assert.deepEqual(pick(wipCard({ prd: "x00012-gamma.md", ...phase }), keys), expected);

  const matched = wipCard({ prd: "00012-gamma.md", ...phase });
  assert.equal(matched.stage, "review");
  assert.notEqual(matched.detail, "no state");

});

test("drained_state_has_no_next", () => {
  const base = { prd: "00012-gamma.md", phase: "closed", cycle: 1, rework_cap: 3 };
  const empty = wipCard({ ...base, next_phase: "" });
  assert.deepEqual(pick(empty, ["stage", "next"]), { stage: "closed", next: "" });

  const absent = wipCard({ ...base, phase: "done" });
  assert.deepEqual(pick(absent, ["stage", "next"]), { stage: "done", next: "" });

  const pending = wipCard({ ...base, next_phase: "close" });
  assert.deepEqual(pick(pending, ["stage", "next"]), { stage: "closed", next: "close" });
});

test("hold_prd_is_parked_with_detail_reason", () => {
  const state = { prd: "00030-paused.md", phase: "paused", pause_reason: { detail: "awaiting API key" }, stall_reason: { stalled: "no progress in 3 cycles" } };
  const held = (st, path = "/wt/park") => checkout(path, "feature/park", false, { buckets: { hold: ["00030-paused.md"] }, state: st });
  const card = (co, text) => toCard(prd("00030-paused.md", "hold", co), text, co);

  const a = card(held(state), "# Paused\nStatus: hold\nDetail: waiting on vendor\nDetail: second\n");
  assert.deepEqual(pick(a, [...CORE, "reason"]), {
    id: "prd:00030-paused.md",
    kind: "prd",
    number: "00030",
    title: "Paused",
    group: "parked",
    stage: "parked",
    next: "",
    checkout: "/wt/park",
    file: `/wt/park/${PRDS}/hold/00030-paused.md`,
    reason: "waiting on vendor",
  });

  const noDetail = "# Paused\nDetails: not this one\n";
  assert.equal(card(held(state, "/wt/p2"), noDetail).reason, "awaiting API key");
  assert.equal(card(held(state, "/wt/p2"), noDetail).checkout, "/wt/p2");

  const stalled = { prd: "00030-paused.md", phase: "paused", stall_reason: { stalled: "no progress in 3 cycles" } };
  assert.equal(card(held(stalled), noDetail).reason, "no progress in 3 cycles");

  assert.equal(card(held({ ...state, prd: "00030-paused-v2.md" }), noDetail).reason, "");
  assert.equal(card(held(null), noDetail).reason, "");
  assert.equal(card(held(null), "Detail: from text\n").reason, "from text");
});

test("worktree_with_matching_state_owns_the_prd", () => {
  const A = "00040-shared.md";
  const B = "00041-other.md";
  const C = "00042-solo.md";
  const main = checkout("/repo", "master", true, { buckets: { wip: [A, C], backlog: [B] } });
  const one = checkout("/wt/one", "feature/one", false, { buckets: { wip: [A, B, C] }, state: { prd: "00040-shared-v2.md", phase: "build" } });
  const two = checkout("/wt/two", "feature/two", false, { buckets: { backlog: [A] }, state: { prd: A, phase: "build" } });
  const three = checkout("/wt/three", "feature/three", false, { buckets: { hold: [A] }, state: { prd: A, phase: "paused" } });
  const four = checkout("/wt/four", "feature/four", false, { buckets: { wip: [C] }, state: { prd: C, phase: "review" } });
  // Rule 1 tie: the earlier checkout wins; it has the longer, alphabetically later path.
  const D = "00043-tie.md";
  const tieFirst = checkout("/wt/z-much-longer-earlier-path", "feature/tie-z", false, { buckets: { wip: [D] }, state: { prd: D, phase: "build" } });
  const tieSecond = checkout("/wt/b", "feature/tie-b", false, { buckets: { wip: [D] }, state: { prd: D, phase: "review" } });

  const items = ownItems([main, one, two, three, four, tieFirst, tieSecond]);
  assert.deepEqual(ownersOf(items, "prd"), {
    [A]: "hold@/wt/three",
    [B]: "wip@/wt/one",
    [C]: "wip@/wt/four",
    [D]: "wip@/wt/z-much-longer-earlier-path",
  });
  assert.strictEqual(items.find((i) => i.name === D).checkout, tieFirst);
  const shared = items.find((i) => i.name === A);
  assert.equal(shared.kind, "prd");
  assert.strictEqual(shared.checkout, three);
  assert.strictEqual(items.find((i) => i.name === C).checkout, four);

  const card = toCard(shared, "# Shared\n", shared.checkout);
  assert.deepEqual(pick(card, ["group", "checkout", "file"]), {
    group: "parked",
    checkout: "/wt/three",
    file: `/wt/three/${PRDS}/hold/${A}`,
  });
});

test("prd_done_in_main_is_dropped", () => {
  const D = "00050-finished.md";
  const E = "00051-reopened.md";
  const G = "00052-done-elsewhere.md";
  const H = "00053-main-backlog.md";
  const main = checkout("/repo", "master", true, { buckets: { done: [D, E], backlog: [H] } });
  const one = checkout("/wt/one", "feature/one", false, { buckets: { backlog: [D], wip: [E], done: [G], hold: [H] } });

  assert.deepEqual(ownersOf(ownItems([main, one]), "prd"), {
    [E]: "wip@/wt/one",
    [H]: "backlog@/repo",
  });

  const onlyDone = checkout("/repo", "master", true, { buckets: { done: [D, E, G] } });
  assert.deepEqual(ownItems([onlyDone]).filter((i) => i.kind === "prd"), []);
});

function assertIdeaOwnershipAndCards() {
  const main = checkout("/repo", "master", true, { intake: ["00020-idea"] });
  const one = checkout("/wt/one", "feature/one", false, { intake: ["00020-idea", "00021-wt-only"] });
  const two = checkout("/wt/two", "feature/two", false, { intake: ["00021-wt-only", "00022-late"] });
  const items = ownItems([main, one, two]);
  assert.deepEqual(ownersOf(items, "idea"), {
    "00020-idea": "/repo",
    "00021-wt-only": "/wt/one",
    "00022-late": "/wt/two",
  });

  const late = items.find((i) => i.name === "00022-late");
  assert.strictEqual(late.checkout, two);
  assert.deepEqual(pick(toCard(late, "", two), CORE), {
    id: "idea:00022-late",
    kind: "idea",
    number: "00022",
    title: "late",
    group: "idea",
    stage: "idea",
    next: "",
    checkout: "/wt/two",
    file: "/wt/two/docs/dev/project-management/intake/new/00022-late/idea.md",
  });
  const wt = items.find((i) => i.name === "00021-wt-only");
  assert.equal(toCard(wt, "# Worktree only idea\n", one).title, "Worktree only idea");
  assert.equal(toCard(wt, "# Worktree only idea\n", one).checkout, "/wt/one");
  assert.equal(toCard({ kind: "idea", name: "00023-big-idea", checkout: two }, "", two).title, "big-idea");
}

test("prd_absent_from_main_is_owned_by_first_checkout", () => {
  const P = "00060-first.md";
  const Q = "00061-second.md";
  const R = "00062-third.md";
  const main = checkout("/repo", "master", true, { buckets: { backlog: ["00060-first-v2.md"] } });
  const one = checkout("/wt/one", "feature/one", false, { buckets: { backlog: [P], hold: [Q] } });
  const two = checkout("/wt/two", "feature/two", false, { buckets: { hold: [P], backlog: [Q, R] } });

  const items = ownItems([main, one, two]);
  assert.deepEqual(ownersOf(items, "prd"), {
    "00060-first-v2.md": "backlog@/repo",
    [P]: "backlog@/wt/one",
    [Q]: "hold@/wt/one",
    [R]: "backlog@/wt/two",
  });
  assert.strictEqual(items.find((i) => i.name === R).checkout, two);

  assertIdeaOwnershipAndCards();
});

const GATES_OPEN = { design: "open", tasks: "open", implementation: "open" };
const entry = (name, phase, extra = {}) => ({ spec: name, phase, state: "valid", gates: GATES_OPEN, nextTask: null, hold: null, ...extra });
const specMain = (specs, specsDir = "docs/specs") => checkout("/repo", "master", true, { specs: specs && { specs }, specsDir });
const specItem = (spec, co) => ({ kind: "spec", name: spec.spec, checkout: co, spec });

test("unfinished_spec_shows_phase_and_next_gate", () => {
  // Phases differ from the expected gate, so `<phase> gate` fails.
  const cards = entry("00007-runway-cards", "tasks", { gates: { design: "closed", tasks: "closed", implementation: "closed" } });
  const queue = entry("00008-queue-view", "implementation", { state: "invalid", gates: { design: "open", tasks: "closed", implementation: "closed" } });
  const main = specMain([cards, queue]);
  const items = ownItems([main]).filter((i) => i.kind === "spec");
  assert.deepEqual(items.map((i) => i.name).sort(), ["00007-runway-cards", "00008-queue-view"]);
  const item = items.find((i) => i.name === "00007-runway-cards");
  assert.deepEqual(item.spec, cards);
  assert.strictEqual(item.checkout, main);

  assert.deepEqual(pick(toCard(item, "# Ignored heading\n", main), [...CORE, "detail"]), {
    id: "spec:00007-runway-cards",
    kind: "spec",
    number: "00007",
    title: "runway cards",
    group: "spec",
    stage: "tasks",
    next: "design gate",
    checkout: "/repo",
    file: "/repo/docs/specs/00007-runway-cards/requirements.md",
    detail: "",
  });
  const q = toCard(specItem(queue, main), "", main);
  assert.deepEqual(pick(q, ["title", "stage", "detail", "next"]), { title: "queue view", stage: "implementation", detail: "state invalid", next: "tasks gate" });
  const long = entry("00009-three-word-name", "design", { state: "stale" });
  assert.deepEqual(pick(toCard(specItem(long, main), "", main), ["title", "detail"]), { title: "three word name", detail: "state stale" });

  const impl = entry("00009-lanes", "tasks", { gates: { design: "open", tasks: "open", implementation: "closed" } });
  assert.equal(toCard(specItem(impl, main), "", main).next, "implementation gate");
  const byId = entry("00009-lanes", "implementation", { gates: { design: "closed", tasks: "open", implementation: "closed" }, nextTask: { id: "T4", title: "Wire cards" } });
  assert.equal(toCard(specItem(byId, main), "", main).next, "task T4");
  const byTitle = entry("00009-lanes", "implementation", { nextTask: { id: null, title: "Draw lanes" } });
  assert.equal(toCard(specItem(byTitle, main), "", main).next, "task Draw lanes");
  assert.equal(toCard(specItem(entry("00009-lanes", "implementation"), main), "", main).next, "");
});

test("complete_spec_is_dropped", () => {
  const main = specMain([
    entry("00007-runway-cards", "design"),
    entry("00008-queue-view", "complete"),
    entry("00009-lanes", "completing"),
    entry("00010-reopen", "implementation"),
  ]);
  const done = checkout("/wt/s10", "feature/specflow-00010", false, {
    specs: { specs: [entry("00010-reopen", "complete")] },
    specsDir: "docs/specs",
  });
  const stale = checkout("/wt/other", "feature/other", false, {
    specs: { specs: [entry("00007-runway-cards", "complete"), entry("00009-lanes", "complete")] },
    specsDir: "docs/specs",
  });
  const items = ownItems([main, done, stale]).filter((i) => i.kind === "spec");
  assert.deepEqual(ownersOf(items, "spec"), { "00007-runway-cards": "/repo", "00009-lanes": "/repo" });
  assert.equal(items.find((i) => i.name === "00007-runway-cards").spec.phase, "design");

  assert.deepEqual(ownItems([specMain(null)]).filter((i) => i.kind === "spec"), []);
  assert.deepEqual(ownItems([specMain([])]).filter((i) => i.kind === "spec"), []);
  assert.deepEqual(ownItems([specMain([entry("00011-gone", "complete")])]).filter((i) => i.kind === "spec"), []);
});

test("held_spec_is_parked", () => {
  const main = specMain([]);
  const card = (hold) => toCard(specItem(entry("00007-runway-cards", "tasks", { hold }), main), "", main);

  assert.deepEqual(pick(card("waiting on design review"), ["group", "stage", "reason"]), {
    group: "parked",
    stage: "tasks",
    reason: "waiting on design review",
  });
  assert.deepEqual(pick(card({ reason: "blocked by API" }), ["group", "reason"]), { group: "parked", reason: "blocked by API" });
  assert.deepEqual(pick(card({ until: "2026-12-01" }), ["group", "reason"]), { group: "parked", reason: '{"until":"2026-12-01"}' });
  assert.deepEqual(pick(card({ reason: 5 }), ["group", "reason"]), { group: "parked", reason: '{"reason":5}' });
  assert.equal(card(null).group, "spec");
});

test("spec_branch_checkout_owns_its_spec", () => {
  const main = specMain([entry("00007-runway-cards", "design"), entry("00008-queue-view", "tasks")]);
  const own = entry("00008-queue-view", "implementation", { nextTask: { id: "T2", title: "Sort cards" } });
  const s8 = checkout("/wt/s8", "feature/specflow-00008", false, {
    specs: { specs: [entry("00007-runway-cards", "tasks"), own] },
    specsDir: "specs/v2",
  });
  const s9 = checkout("/wt/s9", "feature/specflow-00009", false, { specs: { specs: [entry("00009-lanes", "tasks")] }, specsDir: "docs/specs" });
  const near = checkout("/wt/s0", "feature/specflow-0000", false, { specs: { specs: [entry("00007-runway-cards", "implementation")] }, specsDir: "docs/specs" });
  const bugfix = checkout("/wt/bf", "bugfix/specflow-00007", false, { specs: { specs: [entry("00007-runway-cards", "tasks")] }, specsDir: "docs/specs" });
  const empty = checkout("/wt/s12", "feature/specflow-00012", false, { specsDir: "docs/specs" });

  const items = ownItems([main, s8, s9, near, bugfix, empty]).filter((i) => i.kind === "spec");
  assert.deepEqual(ownersOf(items, "spec"), {
    "00007-runway-cards": "/repo",
    "00008-queue-view": "/wt/s8",
    "00009-lanes": "/wt/s9",
  });
  assert.equal(items.find((i) => i.name === "00007-runway-cards").spec.phase, "design");
  const queue = items.find((i) => i.name === "00008-queue-view");
  assert.deepEqual(queue.spec, own);
  assert.strictEqual(queue.checkout, s8);

  assert.deepEqual(pick(toCard(queue, "", s8), ["stage", "next", "checkout", "file"]), {
    stage: "implementation",
    next: "task T2",
    checkout: "/wt/s8",
    file: "/wt/s8/specs/v2/00008-queue-view/requirements.md",
  });
});

const TYPES = ["branch", "worktree", "lane", "pr", "issue", "ref"];
const ctx = (branches = [], worktrees = [], lanes = []) => ({ branches, worktrees, lanes });
const wt = (path, branch = null, main = false) => ({ path, branch, main });

// Expected chips, whole: branch label = value = name (path only when checked out);
// worktree label = folder name, value = path = path; lane value = lane name;
// issue/pr/ref label `#<n>`, value the number or the URL.
const chip = (type, label, value, path) => (path ? { type, label, value, path } : { type, label, value });
const br = (name, path) => chip("branch", name, name, path);
const tree = (path) => chip("worktree", path.split("/").pop(), path, path);
const laneChip = (name, status) => chip("lane", `lane ${name} (${status})`, name);
const num = (type, n, url) => chip(type, `#${n}`, url ?? String(n));

function prdCard(name) {
  const co = checkout("/repo", "master", true, { buckets: { wip: [name] } });
  return toCard(prd(name, "wip", co), "", co);
}

// Checks the type order, then compares whole chips; order inside a type is free.
function same(chips, expected) {
  const ranks = chips.map((c) => TYPES.indexOf(c.type));
  assert.ok(ranks.every((r) => r >= 0), `unknown chip type in ${JSON.stringify(chips)}`);
  assert.deepEqual(ranks, [...ranks].sort((a, b) => a - b), "chips out of type order");
  const keyOf = (c) => JSON.stringify(Object.entries(c).sort(([a], [b]) => (a < b ? -1 : 1)));
  const sorted = (list) => [...list].sort((a, b) => (keyOf(a) < keyOf(b) ? -1 : 1));
  assert.deepEqual(sorted(chips), sorted(expected));
}

test("scan_finds_issue_pr_and_url_mentions", () => {
  const card = prdCard("00012-gamma.md");
  const text = [
    "# Gamma",
    "Fixes issue #12 and PR #34, see Pull Request #56 and pr 78.",
    "Issue #41 and pull request #42 too.",
    "#77 at line start",
    "Also https://github.com/o/r/issues/90 and https://gitlab.com/o/r/-/merge_requests/91",
    "and https://bitbucket.org/o/r/pull-requests/92 plus https://github.com/o/r/pull/93",
    "GitLab https://gitlab.com/o/r/-/issues/95 (https://github.com/o/r/pull/97). See https://github.com/o/r/issues/98, then.",
    "Not https://github.com/o/r/discussions/94 or https://x.org/myissues/96 or https://example.com/page#13 here.",
    "Refs #5 and #12345, not #123456, not #7a, not a#8, not /#9, not &#10; but (#11).",
    "",
  ].join("\n");
  const url = (path) => `https://${path}`;
  same(scanRefs(card, text, ctx()), [
    ...[34, 56, 78, 42].map((n) => num("pr", n)),
    num("pr", 91, url("gitlab.com/o/r/-/merge_requests/91")),
    num("pr", 92, url("bitbucket.org/o/r/pull-requests/92")),
    num("pr", 93, url("github.com/o/r/pull/93")),
    num("pr", 97, url("github.com/o/r/pull/97")),
    num("issue", 12),
    num("issue", 41),
    num("issue", 90, url("github.com/o/r/issues/90")),
    num("issue", 95, url("gitlab.com/o/r/-/issues/95")),
    num("issue", 98, url("github.com/o/r/issues/98")),
    ...[5, 12345, 11, 77].map((n) => num("ref", n)),
  ]);

  same(scanRefs(card, "issue #7 and PR #8 and #9\n", ctx()), [num("issue", 7), num("pr", 8), num("ref", 9)]);
  same(scanRefs(card, "#3", ctx()), [num("ref", 3)]);
  assert.deepEqual(scanRefs(card, "", ctx()), []);
});

test("scan_drops_branch_git_does_not_have", () => {
  const card = prdCard("00012-gamma.md");
  const textFor = (name) => [
    "---",
    "branch: feature/real, feature/gone",
    "---",
    `Merged master and main into dev; see feat, feature/${name}, feature/ghost here.`,
    `Not bugfix/typo-2 or x/bugfix/typo or .bugfix/typo or bugfix/typo. Nor ${name}.md or ${name}x.`,
    "",
  ].join("\n");
  const branchesFor = (name) => ["master", "main", "dev", "feat", `feature/${name}`, name, "bugfix/typo", "feature/real"];
  // The same text shape with another branch name: the chips follow the name.
  for (const name of ["login", "signup"]) {
    same(scanRefs(card, textFor(name), ctx(branchesFor(name))), [br("feat"), br(`feature/${name}`), br("feature/real")]);
  }
  const text = textFor("login");
  const branches = branchesFor("login");

  // Once git has them, the frontmatter branch and the mentioned branch appear.
  same(scanRefs(card, text, ctx([...branches, "feature/gone", "feature/ghost"])), [
    br("feat"),
    br("feature/login"),
    br("feature/real"),
    br("feature/gone"),
    br("feature/ghost"),
  ]);
  // A checked-out branch carries its worktree path.
  const trees = [wt("/repo", "master", true), wt("/wt/login", "feature/login")];
  same(scanRefs(card, text, ctx(branches, trees)), [br("feat"), br("feature/login", "/wt/login"), br("feature/real")]);
  assert.deepEqual(scanRefs(card, text, ctx()), []);
});

function numberedCtx(n) {
  const branches = ["master", `feature/prd-${n}`, `feature/${n}x`, `feature/1${n}-big`, `feature/${n}3`, `feature/specflow-${n}`, "feature/other"];
  const trees = [
    wt(`/src/repo-${n}`, "master", true),
    wt(`/wt/prd-${n}`, `feature/prd-${n}`),
    wt(`/wt/gamma-${n}`),
    wt(`/wt/x-${n}0`),
    wt(`/wt/x-1${n}`),
    wt(`/wt/${n}/inner`),
    wt(`/wt/specflow-${n}`),
  ];
  return ctx(branches, trees);
}

test("scan_adds_branch_and_worktree_carrying_the_number", () => {
  // The same ctx shape for two numbers: the chips follow the card's number.
  for (const [file, n] of [["00012-gamma.md", "00012"], ["00077-other.md", "00077"]]) {
    same(scanRefs(prdCard(file), "# Card\n", numberedCtx(n)), [
      br(`feature/prd-${n}`, `/wt/prd-${n}`),
      br(`feature/${n}x`),
      tree(`/wt/gamma-${n}`),
    ]);
  }
  assert.deepEqual(scanRefs(prdCard("00077-other.md"), "# Card\n", numberedCtx("00012")), []);
  assert.deepEqual(scanRefs(prdCard("00012-gamma.md"), "# Gamma\n", ctx()), []);
});

test("specflow_branch_matches_spec_cards_only", () => {
  const branches = ["master", "feature/specflow-00008", "feature/prd-00008", "feature/specflow-000081"];
  const trees = [
    wt("/repo", "master", true),
    wt("/wt/s8", "feature/specflow-00008"),
    wt("/wt/specflow-00008-scratch"),
    wt("/wt/plain-00008"),
  ];
  const main = specMain([]);
  const spec = toCard(specItem(entry("00008-queue-view", "tasks"), main), "", main);
  same(scanRefs(spec, "", ctx(branches, trees)), [br("feature/specflow-00008", "/wt/s8"), tree("/wt/specflow-00008-scratch")]);
  same(scanRefs(prdCard("00008-z.md"), "", ctx(branches, trees)), [br("feature/prd-00008"), tree("/wt/plain-00008")]);
});

test("structured_fields_are_read_and_deduped", () => {
  const card = prdCard("00012-gamma.md");
  const text = [
    "---",
    "id: 00012",
    "branch: feature/gamma, feature/gone ,  feature/login",
    "issue: 12, #34, abc, 7x, https://github.com/o/r/issues/56",
    "pr: #78, , 12, https://example.com/compare/1, https://github.com/o/r/pull/90",
    "---",
    "# Gamma",
    "issue #12 again, PR #78, https://github.com/o/r/pull/90",
    "",
  ].join("\n");
  const trees = [wt("/repo", "master", true), wt("/wt/gamma", "feature/gamma")];
  const chips = scanRefs(card, text, ctx(["master", "feature/gamma", "feature/login"], trees));
  // Prose rules scan only the body, so frontmatter `#34` and `#78` give no refs.
  same(chips, [
    br("feature/gamma", "/wt/gamma"),
    br("feature/login"),
    num("pr", 78),
    num("pr", 12),
    num("pr", 90, "https://github.com/o/r/pull/90"),
    num("issue", 12),
    num("issue", 34),
    num("issue", 56, "https://github.com/o/r/issues/56"),
  ]);

  same(scanRefs(card, "---\nissue: 5\npr: 6\n---\n# Gamma\n", ctx()), [num("pr", 6), num("issue", 5)]);
  assert.deepEqual(scanRefs(card, "---\nissue: abc\npr:\n---\n", ctx()), []);
});

test("planned_wave_lane_adds_lane_chip", () => {
  const lane = (name, branch, worktree, prds, status) => ({ name, order: 1, branch, worktree, prds, paths: [], status });
  const lanes = [
    lane("alpha", "feature/alpha", "/wt/alpha", ["00002-x.md"], "running"),
    lane("beta", "feature/beta", "/wt/beta", ["00002-x.md"], "planned"),
    lane("gamma", "feature/gamma", "/wt/gamma", ["00001-a.md", "00002-x.md"], "planned"),
    lane("delta", "feature/delta", "/wt/delta", ["00002-x-v2.md", "100002-x.md"], "planned"),
    lane("eps", "feature/eps", "/wt/eps", ["00002-x.md"], "done"),
    lane("zeta", "feature/zeta", "/wt/zeta", ["00002-x.md"], "planned"),
    lane("eta", "feature/eta", "/wt/eta", ["00003-y.md"], "blocked"),
    // Its branch also carries the number and is named in the text: still one chip.
    lane("theta", "feature/runway-00002", "/wt/runway-00002", ["00002-x.md"], "running"),
  ];
  const branches = ["master", "feature/alpha", "feature/delta", "feature/zeta", "feature/runway-00002"];
  const trees = [
    wt("/repo", "master", true),
    wt("/wt/alpha", "feature/alpha"),
    wt("/wt/beta"),
    wt("/wt/delta", "feature/delta"),
    wt("/wt/runway-00002", "feature/runway-00002"),
  ];
  const runway = br("feature/runway-00002", "/wt/runway-00002");

  same(scanRefs(prdCard("00002-x.md"), "# X\nWork on feature/runway-00002 now.\n", ctx(branches, trees, lanes)), [
    br("feature/alpha", "/wt/alpha"),
    br("feature/zeta"),
    runway,
    tree("/wt/beta"),
    laneChip("gamma", "planned"),
    laneChip("eps", "done"),
  ]);

  same(scanRefs(prdCard("00003-y.md"), "# Y\n", ctx(branches, trees, lanes)), [laneChip("eta", "blocked")]);
  same(scanRefs(prdCard("00002-x.md"), "# X\n", ctx(branches, trees, [])), [runway]);
});
