// Rows of the Clues category, from a snapshot plus what main.js fetched:
//   data = { paneState: Map pane → { cwd, command, ssh, shellPid },
//            content: Map pane → text, procs: Map | null, listeners: [] | null }
// Clues covers every terminal pane, agents included, so `.text` finds the
// agent session that printed it. (herdr-recent-navigator leaves agents out.)

import { index, tabName, tildify } from "./items.js";
import * as mru from "./mru.js";
import {
  CLUE_ORDER, bufferKind, commandIsShell, contentExcerpt, paneForPid, parseFilter, rankClues, sshHost,
} from "./clue-extract.js";

function firstLine(text) {
  return (text ?? "").split("\n").map((l) => l.trim()).find(Boolean) ?? "";
}

/** The panes Clues can list, each with what a row needs to say where it is. */
function candidates(snap) {
  const ix = index(snap);
  const out = [];
  for (const p of snap.panes) {
    if (!p.terminal) continue;
    const d = ix.described.get(p.pane);
    const at = ix.tab.get(p.tab);
    if (!at) continue;
    out.push({
      pane: p,
      title: d.title,
      program: d.program,
      cwd: d.cwd,
      spaceId: at.space.id,
      spaceName: at.space.name,
      tabName: tabName(at.tab),
      where: `${at.space.name} › ${tabName(at.tab)}`,
      at: mru.lastFocused(snap.history, "pane", p.pane),
      rank: snap.history.pane.findIndex((e) => e.id === p.pane),
      order: out.length,
      current: snap.focused?.pane === p.pane,
    });
  }
  return out;
}

function row(c, clue, detail, context, home, extra = {}) {
  const shown = context === "-" ? "-" : tildify(context, home);
  return {
    kind: "clue",
    clue,
    key: `clue:${clue}:${c.pane.pane}${extra.suffix ?? ""}`,
    id: c.pane.pane,
    title: detail,
    detail: shown,
    where: c.where,
    spaceId: c.spaceId,
    spaceName: c.spaceName,
    tabName: c.tabName,
    terminal: c.pane.terminal,
    path: tildify(c.cwd, home),
    branch: c.pane.branch ?? null,
    program: c.program,
    status: null,
    current: c.current,
    at: c.at,
    rank: c.rank,
    order: c.order,
    // A buffer row shows only its excerpt, so it is searched by that and its whole
    // line (a term the excerpt cut off still matches); other rows by all they show.
    fields: extra.line
      ? [{ key: "title", text: detail }, { key: "line", text: extra.line }]
      : [
        { key: "clue", text: clue },
        { key: "title", text: detail },
        { key: "detail", text: shown === "-" ? "" : shown },
        { key: "where", text: c.where },
      ],
    actions: [["tab.select", { id: c.pane.tab }], ["pane.focus", { pane: c.pane.pane }]],
    ...(extra.item ?? {}),
  };
}

function hint(clue, detail, reason, context) {
  return {
    kind: "hint",
    clue,
    key: `hint:${clue}:${detail}:${reason}`,
    id: null,
    title: detail,
    reason,
    detail: context ?? "",
    where: "",
    path: "",
    program: null,
    status: null,
    current: false,
    at: null,
    rank: Infinity,
    fields: [
      { key: "clue", text: clue },
      { key: "title", text: detail },
      { key: "reason", text: reason },
      { key: "detail", text: context ?? "" },
    ],
    actions: [],
  };
}

/**
 * Most recently focused pane first, never-focused panes after in Herdr's
 * order; a pane's rows stay together in clue order (ssh, cmd, ...).
 */
function byRecency(rows) {
  const r = (x) => (x.rank === undefined || x.rank < 0 ? Infinity : x.rank);
  const o = (x) => x.order ?? Infinity;
  return [...rows].sort((a, b) => r(a) - r(b) || o(a) - o(b) || (CLUE_ORDER[a.clue] ?? 9) - (CLUE_ORDER[b.clue] ?? 9));
}

function stateRows(cs, data, home, only) {
  const rows = [];
  for (const c of cs) {
    const o = data.paneState.get(c.pane.pane);
    if (!o) continue;
    if (o.ssh && (!only || only === "ssh")) rows.push(row(c, "ssh", o.ssh, sshHost(o.ssh), home));
    if (o.command && !commandIsShell(o.command) && (!only || only === "cmd")) rows.push(row(c, "cmd", o.command, o.cwd || "-", home));
  }
  return rows;
}

function contentRows(cs, data, home, needle, only) {
  const rows = [];
  for (const c of cs) {
    const text = data.content.get(c.pane.pane);
    if (!text) continue;
    const kind = bufferKind(data.paneState.get(c.pane.pane) ?? { cwd: c.cwd, command: null }, c.title);
    if (only && kind.kind !== only) continue;
    if (!needle) {
      rows.push(row(c, kind.kind, kind.file ? tildify(kind.file, home) : firstLine(text), kind.context, home, { suffix: ":buffer" }));
      continue;
    }
    const ex = contentExcerpt(text, needle);
    if (!ex) continue;
    rows.push(row(c, kind.kind, ex.text, kind.context, home, { suffix: ":buffer", line: ex.line, item: { excerpt: ex.hit } }));
  }
  return rows;
}

function shellMap(cs, data) {
  const shells = new Map();
  for (const c of cs) {
    const pid = data.paneState.get(c.pane.pane)?.shellPid;
    if (pid) shells.set(pid, c);
  }
  return shells;
}

function pidRows(cs, data, home, needle) {
  if (!/^\d+$/u.test(needle)) return [];
  const pid = Number(needle);
  const procs = data.procs;
  const shells = shellMap(cs, data);
  const owner = procs ? paneForPid(pid, shells, procs) : null;
  if (owner) return [row(owner, "pid", procs.get(pid)?.command || `pid ${pid}`, "-", home)];
  if (!procs || procs.size === 0) return [hint("pid", `pid ${pid}`, "ps/lsof unavailable")];
  if (!procs.has(pid)) return [hint("pid", `pid ${pid}`, "no such process")];
  if (data.paneState.size === 0) return [];
  return [hint("pid", procs.get(pid).command || `pid ${pid}`, "not in any pane", "")];
}

function portRows(cs, data, home, needle) {
  const procs = data.procs ?? new Map();
  const shells = shellMap(cs, data);
  const ownerRow = (l) => {
    const c = paneForPid(l.pid, shells, procs);
    return c ? row(c, "port", l.addr, procs.get(l.pid)?.command || `pid ${l.pid}`, home, { suffix: `:${l.addr}:${l.pid}` }) : null;
  };
  if (needle === "") {
    const listeners = [...(data.listeners ?? [])].sort((a, b) => a.port - b.port);
    return byRecency(listeners.map(ownerRow).filter(Boolean));
  }
  if (!/^\d+$/u.test(needle) || Number(needle) > 65535) return [];
  const port = Number(needle);
  if (!data.listeners?.length) return [hint("port", `port ${port}`, "ps/lsof unavailable")];
  const rows = [];
  const orphans = [];
  for (const l of data.listeners.filter((x) => x.port === port)) {
    const r = ownerRow(l);
    if (r) rows.push(r);
    else orphans.push(l);
  }
  const hints = data.paneState.size ? orphans.map((l) => hint("port", l.addr, "not in any pane", procs.get(l.pid)?.command || `pid ${l.pid}`)) : [];
  if (!rows.length && !orphans.length) return [hint("port", `port ${port}`, "nothing listening")];
  return [...byRecency(rows), ...hints];
}

/**
 * Clues' rows for a query, ranked: `{ rows: [{ item, hits }], filter,
 * label, needle }`. `label` is the prefix to show as a chip.
 */
export function buildClues(snap, data, query) {
  const { filter, label, needle } = parseFilter(query);
  const n = needle.trim();
  const cs = candidates(snap);
  const home = snap.home;
  let rows;
  let ranked;
  if (filter === "port") return { rows: portRows(cs, data, home, n).map((item) => ({ item, hits: {} })), filter, label, needle };
  if (filter === "pid") return { rows: pidRows(cs, data, home, n).map((item) => ({ item, hits: {} })), filter, label, needle };
  if (filter === null) {
    rows = [...stateRows(cs, data, home), ...(n ? contentRows(cs, data, home, n) : [])];
    ranked = query;
  } else if (filter === "content") {
    rows = n ? contentRows(cs, data, home, n) : [];
    ranked = n;
  } else if (filter === "file" || filter === "term") {
    rows = contentRows(cs, data, home, n, filter);
    ranked = n;
  } else {
    rows = stateRows(cs, data, home, filter);
    ranked = n;
  }
  return { rows: rankClues(byRecency(rows), ranked), filter, label, needle };
}
