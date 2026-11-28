// Lane planning and opening for runway cards. Pure: Herdr I/O is injected.
const PRDS = "docs/dev/project-management/prds";
const STATE = "docs/dev/project-management/autopilot/state.json";

const itemName = (card) => card.id.slice(card.id.indexOf(":") + 1);

export function laneBranch(card) {
  return card.kind === "prd"
    ? `feature/${card.file.split("/").pop().replace(/\.md$/, "").replace(/-v\d+$/, "")}`
    : `feature/specflow-${card.number}`;
}

export function planLane(card, repo, home, branch = laneBranch(card), directory = `${home}/git/src/worktrees`) {
  let name;
  if (card.kind === "prd") {
    name = card.file.slice(card.file.lastIndexOf("/") + 1);
    if (card.checkout !== repo.main || card.file !== `${repo.main}/${PRDS}/backlog/${name}`) {
      return { error: "Only a backlog PRD in the main checkout can move" };
    }
  }
  const slug = branch.replace(/[^\p{L}\p{M}\p{N}._-]+/gu, "-").replace(/^-+|-+$/g, "");
  if (!slug || slug === "." || slug === "..") return { error: "Enter a valid branch name" };
  const path = `${directory}/${repo.name}/${slug}`;
  if (repo.branches.includes(branch)) return { error: `Branch ${branch} exists; use its chip` };
  if (repo.worktrees.some((w) => w.path === path)) return { error: `Worktree ${path} exists` };
  const plan = { branch, path, main: repo.main };
  if (name) {
    plan.from = card.file;
    plan.to = `${path}/${PRDS}/wip/${name}`;
    plan.stale = `${path}/${PRDS}/backlog/${name}`;
  } else if (branch !== laneBranch(card)) {
    plan.spec = itemName(card);
  }
  return plan;
}

// ponytail: one module-wide flag, one lane at a time across all copies.
let busy = false;

export async function openLane(plan, io) {
  if (busy) throw new Error("A lane is already opening");
  busy = true;
  try {
    const { branch, path, from, to, stale, spec } = plan;
    if (from && !(await io.exists(from))) {
      throw new Error("The PRD is no longer in the backlog; nothing changed");
    }
    const r = await io.git(["worktree", "add", "-b", branch, path, "HEAD"], plan.main);
    if (r.code !== 0) {
      const line = r.stderr.split("\n").map((l) => l.trim()).filter(Boolean).pop() ?? "";
      throw new Error(`Could not create the worktree: ${line}; nothing changed`);
    }
    if (await io.exists(`${path}/${STATE}`)) {
      throw new Error(`The new worktree has a tracked state.json. The PRD did not move. Worktree: ${path}`);
    }
    if (spec) {
      const r = await io.git(["config", "--local", `branch.${branch}.herdr-spec`, spec], plan.main);
      if (r.code !== 0) throw new Error(`Created ${path}, but couldn't link it to spec ${spec}: ${r.stderr.trim()}`);
    }
    if (from) {
      await io.mkdir(`${path}/${PRDS}/wip`);
      await io.move(from, to);
      if ((await io.exists(from)) || !(await io.exists(to))) {
        throw new Error(`The PRD move did not complete. Check ${from} and ${to}`);
      }
      if (await io.exists(stale)) await io.remove(stale);
    }
    return { path, branch };
  } finally {
    busy = false;
  }
}

export function actionFor(card, fm, env) {
  if (card.kind === "prd") {
    if (card.group !== "parked") return null;
    if (fm && Object.prototype.hasOwnProperty.call(fm, "ledger_key")) {
      return { label: "Un-park", kind: "move", disabled: true, tip: "Triage stub: promote it by writing a PRD" };
    }
    return { label: "Un-park", kind: "move" };
  }
  if (card.kind === "spec") {
    if (card.group !== "parked") return null;
    return { label: "Resume", kind: "agent", task: `/specflow:spec-workflow Resume ${itemName(card)}` };
  }
  if (card.kind === "idea") {
    return env.specflow
      ? { label: "Create spec", kind: "agent", task: `/specflow:spec-workflow Create a spec for ${itemName(card)}` }
      : { label: "Elicit", kind: "agent", task: `/elicit-requirements ${card.number}` };
  }
  return null;
}
