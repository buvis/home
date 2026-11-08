// Recency history: which spaces, tabs, panes and agents were focused, most
// recent first. The tracker records every focus change; the navigator reads
// each row's last focus from it and the quick-focus commands jump back through it.
//
// Shape (kept in shared state, so it survives restarts):
//   { v: 1, space: [{ id, at }], tab: [{ id, space, at }],
//     pane: [{ id, space, tab, at }], agent: [{ id, space, tab, at }] }
// The head of each list is the one focused now (or last).

export const KINDS = ["space", "tab", "pane", "agent"];
export const LIMIT = 200;

export function empty() {
  return { v: 1, space: [], tab: [], pane: [], agent: [] };
}

/** A stored history, repaired: unknown versions and broken lists start empty. */
export function load(value) {
  if (!value || value.v !== 1) return empty();
  const out = empty();
  for (const kind of KINDS) {
    const list = Array.isArray(value[kind]) ? value[kind] : [];
    out[kind] = list.filter((e) => e && typeof e.id === "string" && typeof e.at === "number");
  }
  return out;
}

function push(list, entry) {
  if (list[0]?.id === entry.id) return list;
  return [entry, ...list.filter((e) => e.id !== entry.id)].slice(0, LIMIT);
}

/**
 * Records a focus: `{ space, tab, pane, agent }`, any of them null. Returns
 * the new history, or the same object when nothing moved (so the caller can
 * skip writing it).
 */
export function record(history, focus, now) {
  if (!focus) return history;
  let next = history;
  const at = now;
  const put = (kind, entry) => {
    const list = push(next[kind], entry);
    if (list !== next[kind]) next = { ...next, [kind]: list };
  };
  if (focus.space) put("space", { id: focus.space, at });
  if (focus.tab) put("tab", { id: focus.tab, space: focus.space ?? null, at });
  if (focus.pane) put("pane", { id: focus.pane, space: focus.space ?? null, tab: focus.tab ?? null, at });
  if (focus.agent) put("agent", { id: focus.agent, space: focus.space ?? null, tab: focus.tab ?? null, at });
  return next;
}

/** Drops entries whose ids no longer exist. `live[kind]` is a Set of ids. */
export function prune(history, live) {
  let next = history;
  for (const kind of KINDS) {
    if (!live[kind]) continue;
    const kept = next[kind].filter((e) => live[kind].has(e.id));
    if (kept.length !== next[kind].length) next = { ...next, [kind]: kept };
  }
  return next;
}

/** When an id was last focused (ms), or null. */
export function lastFocused(history, kind, id) {
  return history[kind].find((e) => e.id === id)?.at ?? null;
}

/**
 * The entry to jump back to: the most recent one that is not `current`,
 * still exists (`live`, a Set), and passes `keep` when given.
 */
export function previous(history, kind, { current, live, keep } = {}) {
  for (const e of history[kind]) {
    if (e.id === current) continue;
    if (live && !live.has(e.id)) continue;
    if (keep && !keep(e)) continue;
    return e;
  }
  return null;
}
