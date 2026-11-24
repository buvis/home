export const CLOSED = "recall.closed-tabs";

export function loadClosed(value) {
  return Array.isArray(value) ? value.filter((tab) => tab && typeof tab.id === "string" && typeof tab.title === "string" &&
    typeof tab.folder === "string" && Number.isFinite(tab.at) && tab.reviveLabels && typeof tab.reviveLabels === "object") : [];
}

export function tabSnapshot(spaces, panes, terminals, machines, previous = new Map()) {
  const ready = new Set(machines.filter((m) => m.layout === "ready").map((m) => m.name));
  const tabs = new Map();
  const cores = new Map(terminals.map((t) => [t.address, t]));
  const byTab = new Map();
  for (const p of panes) {
    if (!p.terminal) continue;
    const list = byTab.get(p.tab) ?? [];
    list.push(p);
    byTab.set(p.tab, list);
  }
  for (const space of spaces) {
    if (!ready.has(space.machine)) continue;
    for (const tab of space.tabs) {
      const candidates = byTab.get(tab.id) ?? [];
      const pane = candidates.find((p) => p.focused && p.program?.agent) ?? candidates.find((p) => p.program?.agent)
        ?? candidates.find((p) => p.focused) ?? candidates[0];
      const core = cores.get(pane?.terminal);
      const prior = previous.get(tab.id);
      if (!pane || !core) {
        if (prior) tabs.set(tab.id, prior); // terminal can disappear before its tab
        continue;
      }
      const folder = pane.cwd ?? core.cwd;
      if (!folder) continue;
      const labels = core.labels ?? {};
      const reviveLabels = Object.fromEntries(["agent", "session", "cwd", "flags", "needs"].map((key) => `revive.${key}`)
        .filter((key) => typeof labels[key] === "string").map((key) => [key, labels[key]]));
      const title = tab.named ? tab.name : (pane.title !== pane.terminal && pane.title) || pane.program?.name || `Tab ${tab.name}`;
      tabs.set(tab.id, { id: tab.id, space: space.id, spaceName: space.name, named: space.named, machine: space.machine,
        title, tabNamed: tab.named, folder, agent: Boolean(pane.program?.agent || reviveLabels["revive.session"]), reviveLabels });
    }
  }
  return { tabs, ready };
}

export function rememberClosed(previous, current, history, now) {
  const lost = [...previous.entries()].filter(([id, tab]) => current.ready.has(tab.machine) && !current.tabs.has(id));
  if (!lost.length) return history;
  return [...lost.map(([, tab]) => ({ ...tab, at: now })), ...history].slice(0, 40);
}

export function closedItems(history, home) {
  return history.map((tab) => {
    const path = tab.folder.startsWith(`${home}/`) ? `~${tab.folder.slice(home.length)}` : tab.folder;
    const spaceName = [tab.spaceName, tab.machine].filter(Boolean).join(" · ");
    return { kind: "closed", key: `closed:${tab.id}:${tab.at}`, title: tab.title, spaceName, path, at: tab.at, tab,
      fields: [{ key: "title", text: tab.title }, { key: "where", text: spaceName }, { key: "path", text: path }] };
  });
}
