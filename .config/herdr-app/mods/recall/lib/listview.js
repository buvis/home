// What the navigator shows for one category: the seam every list rule is
// tested through. Pure: no gpui, no Herdr runtime, so `node --test` drives
// it with fixture snapshots.
//
//   listView(category, snap, query, options) → { rows, count, total, selected, label, fitTo }
//
// - category: a category id: "all" (every space, tab, pane and agent),
//   "spaces", "tabs", "panes", "agents" or "clues" (the clue search).
// - snap: a Herdr snapshot as items.js reads it, focus history included
//   ({ spaces, panes, agents, terminals, focused, history, home, worktrees }).
// - query: what the person typed, as typed.
// - options.agentSort: Agents' order, "mru" | "priority" | "grouped".
// - options.cluesAvailable: false when Clues is not one of the person's
//   categories, so All has nowhere to send a query it cannot match
//   (default true).
// - options.clueData: the clues read so far for Clues
//   ({ paneState, content, procs, listeners }, see clues.js).
//
// - rows: [{ item, hits }] in display order; `hits[fieldKey]` lists the
//   highlighted code points of that field. Typed, every category but Clues
//   sorts its matches into two tiers (ADR 0002): rows where every term
//   appears unbroken in some field, then the rest, each tier in the order
//   the list has with nothing typed. Clues keeps its own order.
//   When All matches nothing it has one row, kind "to-clues", offering
//   `Search Clues for "<query>"`; opening it is the navigator's job.
//   All's items carry `crumb`, the
//   path drawn before the name (`space › tab › `, `space › `, or "" for a
//   space); it begins with the `where` field, so `hits.where` lights up
//   inside it.
// - count: how many rows match (the header's n in n/total); the Clues offer
//   row is not a match, so it is 0 when that is all there is.
// - total: how many rows the category lists with nothing typed, or null
//   when it shows no total (Clues).
// - selected: the index of the row to select when the list opens or the
//   query changes: the first row that isn't where you are now (nor a
//   clue's reason), typed or not; 0 when there is no such row.
// - label: the clue-type chip to show beside the query, or null.
// - fitTo: the items the columns' widths fit: every item the category
//   lists, whatever is typed, so the columns hold still while typing.
//   Clues has rows only from its search, so there it is the items found.
//
// The navigator renders this and keeps only its own UI state (moving the
// selection, re-aiming until the person moves, scrolling). Rules about
// which rows a list has, their order while typing, the selection and the
// query syntax belong here, behind this same signature: a new category
// is a new id, and a synthetic row (such as one offering another search)
// is a row with its own item kind and no actions, which the navigator
// opens by that kind.

import { buildItems } from "./items.js";
import { tiered } from "./fuzzy.js";
import { buildClues } from "./clues.js";

/**
 * The row to open on, typed or not: the first that isn't where you are now
 * and isn't a clue's reason; row 0 when there is no such row.
 */
function openingRow(rows) {
  const first = rows.findIndex((r) => !r.item.current && r.item.kind !== "hint");
  return first < 0 ? 0 : first;
}

const NO_CLUES = { paneState: new Map(), content: new Map(), procs: null, listeners: null };

export function listView(category, snap, query, options = {}) {
  if (category === "clues") {
    const { rows, label } = buildClues(snap, options.clueData ?? NO_CLUES, query);
    return { rows, count: rows.length, total: null, selected: openingRow(rows), label, fitTo: rows.map((r) => r.item) };
  }
  const items = buildItems(category, snap, { agentSort: options.agentSort });
  const rows = tiered(items, query, (i) => i.fields);
  const matched = rows.length;
  // All finds nothing: offer the search that looks deeper (Clues keeps the query).
  if (category === "all" && query.trim() && !rows.length && options.cluesAvailable !== false) {
    rows.push({ item: { kind: "to-clues", key: "to-clues", title: `Search Clues for "${query.trim()}"`, actions: [] }, hits: {} });
  }
  return { rows, count: matched, total: items.length, selected: openingRow(rows), label: null, fitTo: items };
}
