// Builds the navigator's rows from a snapshot of Herdr's live data.
//
// A snapshot is plain data, so this module runs (and is tested) without the
// app: { spaces, panes, agents, focused, history, home, worktrees }.
// Every row is an item:
//   { kind, key, id, title, detail, where, path, branch, program, status,
//     current, at, fields: [{ key, text }], actions: [[command, args]] }
// `fields` is what search matches; `actions` run in order when the row is
// opened. All's rows also carry `crumb`, the path drawn before the name,
// and an unnamed tab's row `paneList`, its panes' names drawn after it.

import * as mru from "./mru.js";

const STATUS_RANK = { blocked: 0, done: 1, working: 2, idle: 3 };

/** Sort rank of a status: blocked first, then done, working, idle; no status last. */
export function statusRank(status) {
  return STATUS_RANK[status] ?? 9;
}

/** The word the STATUS column shows, and a search matches, for a status. */
export const STATUS_WORD = { blocked: "needs you", done: "finished" };

/** `/Users/me/x` as `~/x` when it is under home. */
export function tildify(path, home) {
  if (!path) return "";
  if (home && (path === home || path.startsWith(home + "/"))) return "~" + path.slice(home.length);
  return path;
}

function lastSegment(path) {
  if (!path) return "";
  const parts = path.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

/** Indexes the snapshot's spaces and tabs by id. */
export function index(snap) {
  const space = new Map();
  const tab = new Map();
  for (const s of snap.spaces) {
    space.set(s.id, s);
    for (const t of s.tabs) tab.set(t.id, { tab: t, space: s });
  }
  const panesOf = new Map();
  const described = new Map();
  for (const p of snap.panes) {
    const d = describePane(p, snap);
    described.set(p.pane, d);
    if (!panesOf.has(p.tab)) panesOf.set(p.tab, []);
    panesOf.get(p.tab).push(d);
  }
  return { space, tab, panesOf, described };
}

/**
 * What a pane shows, filled in from what Herdr knows elsewhere. A pane in a
 * tab the window hasn't drawn yet only has its terminal's address as title
 * and its shell as program; the agents list and herdr-core know better.
 * Its title is its Pane name: agent's title, else the title its program set,
 * else its program, else its folder, else (a mod's pane) the mod.
 */
export function describePane(p, snap) {
  const agent = p.terminal ? snap.agents.find((a) => a.address === p.terminal) : null;
  const core = p.terminal ? snap.terminals?.find((x) => x.address === p.terminal) : null;
  const cwd = p.cwd ?? core?.cwd ?? null;
  const bare = !p.title || p.title === p.terminal;
  const title = agent?.title || (bare ? "" : p.title);
  const program = agent?.program ?? p.program ?? null;
  return {
    pane: p,
    agent,
    title: title || program?.name || (p.terminal ? lastSegment(cwd) : p.mod) || p.title || "",
    program,
    cwd,
    branch: p.branch ?? null,
    status: agent?.status ?? p.status ?? null,
  };
}

/**
 * What a tab is about: its agent's pane, else its focused pane, else its
 * first. It gives a tab row its icon, folder and branch, not its name.
 */
export function leadPane(described) {
  if (!described?.length) return null;
  return described.find((d) => d.agent || d.program?.agent) ?? described.find((d) => d.pane.focused) ?? described[0];
}

/** A pane's Pane name; describePane holds the fallbacks. */
function paneName(d) {
  return d?.title ?? "";
}

/** A tab's Tab name, as Herdr calls it: the name it was given, else its position in its space. */
export function tabName(tab) {
  return tab.name || String(tab.index);
}

function spaceLabel(space, worktrees) {
  const wt = worktrees?.get(space.id);
  if (wt?.linked) return `${wt.repo} ⎇ ${wt.branch ?? lastSegment(space.folder)}`;
  return space.name;
}

/** Every space as a row, in Herdr's order. */
function spaceRows(snap, ix) {
  return snap.spaces.map((s) => {
    const title = spaceLabel(s, snap.worktrees);
    const agentsHere = snap.agents.filter((a) => a.space === s.id).length;
    const path = tildify(s.folder, snap.home);
    return {
      kind: "space",
      key: `space:${s.id}`,
      id: s.id,
      title,
      detail: [`${s.tabs.length} tab${s.tabs.length === 1 ? "" : "s"}`, agentsHere ? `${agentsHere} agent${agentsHere === 1 ? "" : "s"}` : ""].filter(Boolean).join(" · "),
      where: s.machine ? `on ${s.machine}` : "",
      spaceId: s.id,
      spaceName: title,
      tabName: null,
      tabs: s.tabs.map((t) => ({ title: tabName(t), status: t.status, active: t.active })),
      path,
      branch: s.branch,
      program: null,
      status: s.status,
      current: snap.focused?.space === s.id,
      at: mru.lastFocused(snap.history, "space", s.id),
      fields: [
        { key: "title", text: title },
        { key: "path", text: path },
        { key: "branch", text: s.branch ?? "" },
        { key: "machine", text: s.machine ?? "" },
        { key: "status", text: STATUS_WORD[s.status] ?? "" },
      ],
      actions: [["space.select", { id: s.id }]],
    };
  });
}

function spaceItems(snap, ix) {
  return groupWorktrees(recentOrder(spaceRows(snap, ix)), snap.worktrees);
}

/**
 * Puts each linked worktree's space right under its main checkout's space,
 * keeping the main space where recency put it.
 */
export function groupWorktrees(items, worktrees) {
  if (!worktrees?.size) return items;
  const mainOf = (it) => {
    const wt = worktrees.get(it.id);
    return wt?.linked ? wt.main : null;
  };
  const present = new Set(items.map((i) => i.id));
  const children = new Map();
  for (const it of items) {
    const main = mainOf(it);
    if (main && present.has(main)) {
      if (!children.has(main)) children.set(main, []);
      children.get(main).push(it);
    }
  }
  const out = [];
  for (const it of items) {
    const main = mainOf(it);
    if (main && present.has(main)) continue;
    out.push(it);
    for (const child of children.get(it.id) ?? []) out.push({ ...child, nested: true });
  }
  return out;
}

/** Every tab as a row, in Herdr's order. */
function tabRows(snap, ix) {
  const items = [];
  for (const s of snap.spaces) {
    for (const t of s.tabs) {
      const ps = ix.panesOf.get(t.id) ?? [];
      const lead = leadPane(ps);
      const title = tabName(t);
      const runs = [...new Set(ps.map((d) => d.program?.name).filter(Boolean))].join(" · ");
      const paneNames = ps.map(paneName).join(" · ");
      items.push({
        kind: "tab",
        key: `tab:${t.id}`,
        id: t.id,
        title,
        detail: t.named ? paneName(lead) : runs,
        where: spaceLabel(s, snap.worktrees),
        spaceId: s.id,
        spaceName: spaceLabel(s, snap.worktrees),
        tabName: null,
        terminal: lead?.pane.terminal ?? null,
        panes: ps.map((d) => ({ title: paneName(d), program: d.program, status: d.status })),
        path: tildify(lead?.cwd, snap.home),
        branch: lead?.branch ?? null,
        program: lead?.program ?? null,
        status: t.status,
        current: snap.focused?.tab === t.id,
        at: mru.lastFocused(snap.history, "tab", t.id),
        settled: t.settled,
        // The names of the tab's panes, shown for a tab without a name of its own.
        paneList: t.named ? null : paneNames,
        // A term found in several fields lights the first, so the ones a
        // row draws (its name, All's path, the pane list) come first.
        fields: [
          { key: "title", text: title },
          { key: "where", text: spaceLabel(s, snap.worktrees) },
          { key: "panes", text: paneNames },
          { key: "detail", text: t.named ? paneName(lead) : runs },
          { key: "path", text: tildify(lead?.cwd, snap.home) },
          { key: "branch", text: lead?.branch ?? "" },
          { key: "status", text: STATUS_WORD[t.status] ?? "" },
        ],
        actions: [["tab.select", { id: t.id }]],
      });
    }
  }
  return items;
}

function tabItems(snap, ix) {
  return recentOrder(tabRows(snap, ix));
}

/** Every pane as a row, in Herdr's order. */
function paneRows(snap, ix) {
  const items = [];
  for (const p of snap.panes) {
    const at = ix.tab.get(p.tab);
    if (!at) continue;
    const d = ix.described.get(p.pane);
    const tab = tabName(at.tab);
    const spaceName = spaceLabel(at.space, snap.worktrees);
    const title = paneName(d);
    const where = `${spaceName} › ${tab}`;
    const path = tildify(d.cwd, snap.home);
    items.push({
      kind: "pane",
      key: `pane:${p.pane}`,
      id: p.pane,
      title,
      detail: d.program?.name && d.program.name !== title ? d.program.name : "",
      where,
      spaceId: at.space.id,
      spaceName,
      tabName: tab,
      path,
      branch: d.branch,
      program: d.program,
      status: d.status,
      current: snap.focused?.pane === p.pane,
      at: mru.lastFocused(snap.history, "pane", p.pane),
      terminal: p.terminal,
      fields: [
        { key: "title", text: title },
        { key: "where", text: where },
        { key: "path", text: path },
        { key: "detail", text: d.program?.name ?? "" },
        { key: "branch", text: d.branch ?? "" },
        { key: "status", text: STATUS_WORD[d.status] ?? "" },
      ],
      actions: [["tab.select", { id: p.tab }], ["pane.focus", { pane: p.pane }]],
    });
  }
  return items;
}

function paneItems(snap, ix) {
  return recentOrder(paneRows(snap, ix));
}

/** Every agent as a row, in Herdr's order. */
function agentRows(snap, ix) {
  return snap.agents.map((a, i) => {
    const at = ix.tab.get(a.tab);
    const spaceName = at ? spaceLabel(at.space, snap.worktrees) : a.space_name;
    const tab = at ? tabName(at.tab) : a.tab_name;
    const title = a.title || a.program?.name || a.address;
    const where = `${spaceName} › ${tab}`;
    const pane = ix.described.get(a.pane);
    const path = tildify(pane?.cwd, snap.home);
    return {
      kind: "agent",
      key: `agent:${a.address}`,
      id: a.address,
      title,
      detail: a.program?.name && a.program.name !== title ? a.program.name : "",
      where,
      spaceId: a.space,
      spaceName,
      tabName: tab,
      terminal: a.address,
      message: snap.terminals?.find((x) => x.address === a.address)?.report?.msg ?? null,
      path,
      branch: pane?.branch ?? null,
      program: a.program ?? null,
      status: a.status,
      current: a.focused,
      at: mru.lastFocused(snap.history, "agent", a.address),
      seq: a.seq,
      model: i,
      fields: [
        { key: "title", text: title },
        { key: "where", text: where },
        { key: "detail", text: a.program?.name ?? "" },
        { key: "path", text: path },
        { key: "branch", text: pane?.branch ?? "" },
        { key: "status", text: STATUS_WORD[a.status] ?? "" },
      ],
      actions: [["agent.focus", { terminal: a.address }]],
    };
  });
}

/**
 * Agents in one of three orders: "mru" (most recently focused first),
 * "priority" (blocked, done, working, idle; latest change first within
 * each) or "grouped" (space, tab, pane order, as Herdr lists them).
 */
function agentItems(snap, ix, sort) {
  const items = agentRows(snap, ix);
  if (sort === "priority") {
    return [...items].sort((a, b) => statusRank(a.status) - statusRank(b.status) || b.seq - a.seq || a.model - b.model);
  }
  if (sort === "grouped") return items;
  return recentOrder(items);
}

// All's levels: the most specific destinations first.
const LEVEL = { agent: 0, pane: 0, tab: 1, space: 2 };

/**
 * Recent order within one kind of row: the focused rows first, most recent
 * first, then the never-focused by status (blocked, done, working, idle,
 * none); ties keep the given (Herdr's) order. Compares `{ item, i }`.
 */
function recentCompare(a, b) {
  const x = a.item;
  const y = b.item;
  if ((x.at != null) !== (y.at != null)) return x.at != null ? -1 : 1;
  if (x.at != null && x.at !== y.at) return y.at - x.at;
  if (x.at == null) return statusRank(x.status) - statusRank(y.status) || a.i - b.i;
  return a.i - b.i;
}

function recentOrder(items) {
  return items.map((item, i) => ({ item, i })).sort(recentCompare).map(({ item }) => item);
}

/** All's order with nothing typed: by level, then the Recent order within each. */
function restingOrder(items) {
  return items
    .map((item, i) => ({ item, i }))
    .sort((a, b) => LEVEL[a.item.kind] - LEVEL[b.item.kind] || recentCompare(a, b))
    .map(({ item }) => item);
}

/**
 * All: one row per destination, each led by its path (`crumb`). An agent
 * stands for its pane; a tab gets a row only when it has several panes, a
 * space only when it has several tabs and there are several spaces.
 */
function allItems(snap, ix) {
  const agents = new Map(agentRows(snap, ix).map((a) => [a.terminal, a]));
  const panes = new Map(paneRows(snap, ix).map((p) => [p.id, p]));
  const out = [];
  for (const p of snap.panes) {
    const agent = p.terminal ? agents.get(p.terminal) : null;
    if (agent) {
      // The agent history's head stays put while a shell has focus, so its `at` can be
      // older than its pane's: the row takes the later of the two.
      const ats = [agent.at, mru.lastFocused(snap.history, "pane", p.pane)].filter((x) => x != null);
      out.push({ ...agent, at: ats.length ? Math.max(...ats) : null });
      agents.delete(p.terminal);
    } else if (panes.has(p.pane)) out.push(panes.get(p.pane));
  }
  out.push(...agents.values()); // an agent whose pane Herdr doesn't list
  const tabs = tabRows(snap, ix)
    .filter((t) => (ix.panesOf.get(t.id)?.length ?? 0) > 1)
    .map((t) => ({ ...t, program: null }));
  const spaces = snap.spaces.length > 1 ? spaceRows(snap, ix).filter((s) => s.tabs.length > 1) : [];
  const withCrumb = (i) => ({ ...i, crumb: i.kind === "space" ? "" : `${i.where} › ` });
  return restingOrder([...out, ...tabs, ...spaces].map(withCrumb));
}

/** The rows of one category. `options.agentSort`: "mru" | "priority" | "grouped". */
export function buildItems(category, snap, options = {}) {
  const ix = index(snap);
  switch (category) {
    case "all": return allItems(snap, ix);
    case "spaces": return spaceItems(snap, ix);
    case "tabs": return tabItems(snap, ix);
    case "panes": return paneItems(snap, ix);
    case "agents": return agentItems(snap, ix, options.agentSort ?? "mru");
    default: return [];
  }
}
