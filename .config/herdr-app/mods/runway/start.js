// Which PRD autopilot starts next, and how a card's start button starts an agent.

const SPECFLOW = ["claude", "codex", "kiro"];

export function pickOf(checkout) {
  const { wip, backlog } = checkout.buckets;
  const list = wip.length ? wip : backlog;
  return list.length ? [...list].sort()[0] : null;
}

export function startLabel(card) {
  if (card.kind === "idea" || card.group === "idea" || card.group === "parked") return null;
  const { stage, next } = card;
  if (card.kind === "spec") return `Continue: ${next || stage}`;
  if (card.kind !== "prd") return null;
  if (stage === "paused") return "Resume";
  if (stage === "backlog" || stage === "wip") return "Start build";
  if (next === "build") return { review: "Start rework", build: "Continue build" }[stage] ?? null;
  if (next.startsWith("review")) return `Start ${next}`;
  if (next === "done") return "Finish";
  return null;
}

function plainTask(card) {
  const kind = card.kind === "prd" ? "PRD" : card.kind;
  const rel = card.file.slice(card.checkout.length + 1);
  return (
    `Work on ${kind} ${card.number} "${card.title}" in ${rel}. Its stage is ${card.stage}. ` +
    `Do only this next stage: ${startLabel(card)}. ` +
    "Follow the repository's workflow documents. Stop when that stage is done."
  );
}

export function startFor(card, agent, env) {
  const name = `${card.number} ${agent.name}`;
  const key = agent.key;
  const plain = {
    argv: key === "copilot" ? [...agent.run, "-i"] : agent.run,
    task: plainTask(card),
    name,
    gated: false,
    disabled: false,
  };

  if (card.kind === "spec") {
    if (!SPECFLOW.includes(key)) return plain;
    const spec = card.id.slice("spec:".length);
    const start = {
      argv: agent.run,
      task: `${key === "claude" ? "/specflow:spec-workflow " : ""}Continue spec ${spec}`,
      name,
      gated: true,
      disabled: !env.specflow[key],
    };
    return start.disabled ? { ...start, tip: `specflow is not installed for ${agent.name}` } : start;
  }

  const file = card.file.slice(card.file.lastIndexOf("/") + 1);
  let start;
  if (key === "claude") start = { argv: agent.run, task: `/autopilot:run-autopilot ${file}` };
  else if (key === "codex" && env.on === null) start = { argv: ["autocodex", "--once"] };
  else return plain;

  const off = env.pick !== null && env.pick !== file;
  return {
    ...start,
    name,
    gated: true,
    disabled: off,
    ...(off ? { tip: `autopilot 0.10.0 starts ${env.pick} first` } : {}),
  };
}
