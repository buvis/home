// The navigator's columns past the title: what they say, the room each
// needs for what it holds, and how wide they are drawn.
//
// Every length here is in px on a dialog drawn at its design size; a larger
// or smaller one draws them to scale.
//
// A column is as wide as its content needs (columnNeeds), unless a person
// dragged it to a width, which is kept (loadKept). fitColumns shares the
// row out when it can't hold them all: the name first, up to half the
// list, then the columns, the folder giving way first.

import { STATUS_WORD } from "./items.js";
import { DESIGN_TEXT } from "./look.js";
import { textWidth } from "./textwidth.js";

/** The columns that have a width of their own, in the order drawn. The name takes what they leave. */
const SIZED = ["location", "folder", "branch", "status"];
/** The widest a column is fitted or dragged to. */
export const MAX_WIDTH = 520;
/** The least the name keeps when a dragged column or a narrow dialog takes its room; a name that needs less keeps what it needs. */
export const NAME_MIN_WIDTH = 200;
/** The share of the list the name may ask for before the other columns have what they need. */
const NAME_SHARE = 0.5;
/**
 * The order the columns give way in when the row can't hold them all. The
 * folder first: cut at its start it loses what its rows share, and a row's
 * location and branch stay whole for as long as that is enough. The status
 * gives way only when it was dragged, and then last.
 */
const GIVE_ORDER = ["folder", "location", "branch", "status"];

/** Text sizes: a cell's, the status word's and a column head's. The name is drawn at the dialog's own. */
export const CELL_TEXT = 12;
export const STATUS_TEXT = 11.5;
export const HEAD_TEXT = 10.5;

/**
 * What the list is made of besides the names and the columns: the category
 * rail beside it, a row's margin and padding at each end, the gap between
 * its cells, and its status glyph, icon and badge. The navigator draws the
 * head and the rows from these, and rowRoom counts on them.
 */
export const LAYOUT = { rail: 60, margin: 4, pad: 8, gap: 8, glyph: 10, icon: 30, badge: 16 };
/** A name's indent under its main checkout, and the gap between the parts of a name (before a clue's reason, before a message). */
export const NESTED_INDENT = 18;
export const NAME_GAP = 8;

/** The columns a category shows, in the order drawn. All leads each name with its path, so it has no location. */
export function shownColumns(category) {
  return category === "all" ? SIZED.filter((column) => column !== "location") : SIZED;
}

/** What a column's head says. */
export function headLabel(column, category) {
  if (column === "location") return category === "spaces" ? "CONTENTS" : "LOCATION";
  return column.toUpperCase();
}

/** How wide each column's head is: the least that column is ever drawn at. */
export function headWidths(category, metrics) {
  return Object.fromEntries(SIZED.map((column) => [column, textWidth(headLabel(column, category), HEAD_TEXT, metrics)]));
}

/** Where an item sits ("space › tab"); a space sits nowhere, so what it holds. */
export function location(item) {
  if (item.kind === "space") return [item.where, item.detail].filter(Boolean).join(" · ");
  if (!item.spaceName) return "";
  return item.tabName ? `${item.spaceName} › ${item.tabName}` : item.spaceName;
}

/** The room a row's name needs: its indent, its path and itself, and a clue's reason. Not an agent's last message, which shows in what is left. */
function nameNeed(item, metrics) {
  const reason = item.kind === "hint" ? NAME_GAP + textWidth(`(${item.reason})`, DESIGN_TEXT, metrics) : 0;
  return (item.nested ? NESTED_INDENT : 0) + textWidth(`${item.crumb ?? ""}${item.title ?? ""}`, DESIGN_TEXT, metrics) + reason;
}

/**
 * The room each column needs to show its longest value among `items` whole:
 * { name, location, folder, branch, status }. A column is never narrower
 * than its head (`heads`, from headWidths), nor wider than MAX_WIDTH; the
 * name has no such bounds.
 */
export function columnNeeds(items, heads, metrics) {
  const needs = { name: 0, ...heads };
  const grow = (column, width) => { if (width > needs[column]) needs[column] = width; };
  for (const item of items) {
    grow("name", nameNeed(item, metrics));
    grow("location", textWidth(location(item), CELL_TEXT, metrics));
    grow("folder", textWidth(item.path, CELL_TEXT, metrics));
    grow("branch", textWidth(item.branch, CELL_TEXT, metrics));
    grow("status", textWidth(STATUS_WORD[item.status], STATUS_TEXT, metrics));
  }
  for (const column of SIZED) needs[column] = Math.min(needs[column], MAX_WIDTH);
  return needs;
}

/** The widths a person dragged, as stored (shared "recall.widths"): { column: px } for those columns only. */
export function loadKept(raw) {
  const stored = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  return Object.fromEntries(SIZED
    .filter((column) => Number.isFinite(stored[column]) && stored[column] > 0)
    .map((column) => [column, Math.min(MAX_WIDTH, Math.round(stored[column]))]));
}

/**
 * A column's width once its left edge has been dragged `dx` px on screen
 * (negative: leftwards) from where it was `start` wide, on a dialog drawn
 * `scale` times its design size: no narrower than `least`, its head, nor
 * wider than MAX_WIDTH. The name column gives or takes the difference, so
 * the edge stays under the pointer.
 */
export function dragWidth(start, dx, scale, least) {
  return Math.max(least, Math.min(MAX_WIDTH, Math.round(start - dx / scale)));
}

/** What a row has for its name and its `count` columns, on a list `listWidth` wide. */
function rowRoom(listWidth, count) {
  const cells = count + 4; // the status glyph, the icon, the name, the columns, the badge
  return listWidth - 2 * (LAYOUT.margin + LAYOUT.pad) - LAYOUT.glyph - LAYOUT.icon - LAYOUT.badge - LAYOUT.gap * (cells - 1);
}

const total = (widths) => Object.values(widths).reduce((sum, width) => sum + width, 0);

/**
 * Narrows the columns in `width` until together they take `room`: what is
 * over is taken from them in `order`, each down to its head before the
 * next gives any. All at their heads is as far as it goes.
 */
function giveWay(width, heads, order, room) {
  const out = { ...width };
  let over = total(out) - room;
  for (const column of order) {
    if (over <= 0) break;
    if (!(column in out)) continue;
    const cut = Math.min(over, out[column] - heads[column]);
    out[column] = Math.floor(out[column] - cut);
    over -= cut;
  }
  return out;
}

/**
 * How wide each of the `shown` columns is drawn on a list `listWidth` px
 * wide: { column: px }, with `name`: the least the name is drawn at. What
 * the columns leave of the row is the name's.
 *
 * First, as if nothing had been dragged:
 * - the status is as wide as its words need;
 * - the name asks for what it needs, at most half the list, but leaves the
 *   other columns their heads;
 * - the other columns are as wide as they need if that fits beside the
 *   name. If it doesn't, the folder gives way, then the location, then
 *   the branch, none past its head.
 *
 * Then a column in `kept` is drawn at the width it was dragged to, no
 * narrower than its head. The name gives or takes the difference, down to
 * NAME_MIN_WIDTH (or what it asked for, if less). Past that the columns
 * that weren't dragged give way, and the dragged ones only after them.
 *
 * On a list too narrow even for the heads the widths overrun the row, and
 * the navigator narrows location, folder and branch in proportion.
 */
export function fitColumns({ needs, heads, kept, listWidth, shown }) {
  const room = rowRoom(listWidth, shown.length);
  const pick = (from, columns) => Object.fromEntries(columns.map((column) => [column, from[column]]));
  const fitting = shown.filter((column) => column !== "status");

  const asked = Math.min(needs.name, listWidth * NAME_SHARE);
  const least = Math.min(asked, NAME_MIN_WIDTH);
  const name = Math.max(least, Math.min(asked, room - needs.status - total(pick(heads, fitting))));
  const width = { ...giveWay(pick(needs, fitting), heads, GIVE_ORDER, room - needs.status - name), status: needs.status };

  const dragged = shown.filter((column) => kept[column] != null);
  if (!dragged.length) return { name: least, ...width };
  for (const column of dragged) width[column] = Math.max(kept[column], heads[column]);
  const order = [...GIVE_ORDER.filter((column) => !dragged.includes(column)), ...GIVE_ORDER.filter((column) => dragged.includes(column))]
    .filter((column) => column !== "status" || dragged.includes("status"));
  const held = total(width) - total(pick(width, order.filter((column) => column in width)));
  return { name: least, ...width, ...giveWay(pick(width, order.filter((column) => column in width)), heads, order, room - least - held) };
}
