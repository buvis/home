// Switcher order. Nothing blocked or done: Herdr's own agents order (the sidebar's, what cmd-] walks).
// Otherwise what needs me first: blocked, done, working, idle; inside a group, the agents order again.
const RANK = { blocked: 0, done: 1, working: 2 };
const rank = (a) => RANK[a.status] ?? 3;

export function sortAgents(agents) {
  if (!agents.some((a) => rank(a) < 2)) return [...agents];
  const at = new Map(agents.map((a, i) => [a, i]));
  return [...agents].sort((a, b) => rank(a) - rank(b) || at.get(a) - at.get(b));
}

const needsMe = (a) => a.status === "blocked" || a.status === "done";

// Which row of the sorted list starts selected.
// Something needs me: the first row, or the second when the first is where I already am.
// Nothing does: the agent after the focused one in agents() order (what agent.next does), wrapping.
export function initialIndex(agents) {
  const rows = sortAgents(agents);
  if (rows.length < 2) return 0;
  if (rows.some(needsMe)) return rows[0].focused ? 1 : 0;
  const f = agents.findIndex((a) => a.focused);
  const next = agents[(f + 1) % agents.length];
  return Math.max(0, rows.indexOf(next));
}

export function move(at, by, n) {
  return n ? (((at + by) % n) + n) % n : 0;
}
