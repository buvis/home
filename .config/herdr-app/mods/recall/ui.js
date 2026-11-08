// The navigator's look ("Columns" layout): a header with the category
// title and the search box, then an icon rail of the categories beside a
// table of the rows: name, location, folder, branch and status. On All the
// name is led by its path (`space › tab › `) and there is no location
// column. Each column is as wide as what the category lists needs
// (nav.widths, from lib/columns.js). Dragging the edge left of a head sets
// that column's width (a double-click on it lets it fit again). A
// one-line footer under them names the keys.
//
// navigator(nav, ctx) draws the dialog from the navigator's state and
// changes nothing but through nav's own methods:
//   reads  nav.{category, categories, rows, at, scroll, input, mode, query,
//               agentSort, widths, resizing, keys, configError, scale}
//   calls  nav.{switchTo, focusForMode, open,
//               startResize, resizeTo, endResize}
//   ctx  = { view, loading }  (view: what lib/listview.js's listView returned)
//
// Every length here is written as designed, for 13px text, and scaled by
// nav.scale (lib/look.js) through `u`, so text, rows, icons, columns and
// spacing grow together. The atoms that take a `size` (badge, glyph, icon)
// are handed one already scaled. Hairlines stay 1px.

import { div, svg, image } from "gpui-kit";
import { v_flex, h_flex, Input, v_virtual_list } from "gpui-base";
import { theme, shared } from "herdr";
import { segments } from "./lib/fuzzy.js";
import {
  CELL_TEXT, HEAD_TEXT, LAYOUT, NAME_GAP, NESTED_INDENT, STATUS_TEXT, headLabel, location, shownColumns,
} from "./lib/columns.js";
import { STATUS_WORD } from "./lib/items.js";

// Each category's rail label, header title and rail icon (icons/<icon>.svg).
const CATEGORY = {
  all: { label: "All", title: "Find Anywhere", icon: "all" },
  spaces: { label: "Spaces", title: "Recent Spaces", icon: "spaces" },
  tabs: { label: "Tabs", title: "Recent Tabs", icon: "tabs" },
  panes: { label: "Panes", title: "Recent Panes", icon: "panes" },
  agents: { label: "Agents", title: "Agents", icon: "agents" },
  clues: { label: "Clues", title: "Find by Clue", icon: "search" },
};
const SORT_LABEL = { mru: "Recent", priority: "Priority", grouped: "Grouped" };
const CLUE_COLOR = { ssh: "ansi6", cmd: "ansi3", file: "ansi5", term: "ansi4", port: "ansi6", pid: "ansi5" };
const CHIP_COLOR = { ".": "accent", port: "ansi6", pid: "ansi5" };
const KIND_ICON = { space: "spaces", tab: "tabs", pane: "panes", agent: "agents", clue: "panes", hint: "search", "to-clues": "search" };
const PREFIXES = "cmd ssh file term port pid";
const SPINNER = "mods/workspace-chrome/spinner.svg";
const ROW = 30;

// ── atoms ─────────────────────────────────────────────────────────────────

// Space colors as Herdr's own mods keep them (shared "space.colors"), so a
// space's badge here matches its badge in the sidebar and in Go to.
const MARK = { ansi6: "#22a99a", ansi3: "#e3814f", ansi4: "#5b8def", ansi5: "#8b7cf6", ansi2: "#3fae6a", ansi1: "#d9649a" };
const PROJECT_COLORS = ["ansi6", "ansi3", "ansi4", "ansi5", "ansi2", "ansi1"];
function spaceColor(t, id, name) {
  if (name === "~") return t.dim;
  const c = (shared("space.colors") ?? {})[id] ?? PROJECT_COLORS[0];
  return c.startsWith("#") ? c : (MARK[c] ?? t[c]);
}

/** The space's first letter on its color; an empty box keeps the column when there's no space. */
function badge(t, item, size) {
  if (!item.spaceId) return div().size(size).flex_none();
  const letter = [...(item.spaceName ?? "?")][0]?.toUpperCase() ?? "?";
  return h_flex().size(size).flex_none().rounded(Math.round(size * 0.28)).bg(spaceColor(t, item.spaceId, item.spaceName))
    .items_center().justify_center().text_size(size * 0.58).font_bold().text_color("#ffffff").child(letter);
}

function glyph(t, status, size) {
  if (status === "working") return svg(SPINNER).size(size).flex_none().text_color(t.working).spin(900);
  const g = status === "blocked" || status === "done" ? "●" : status === "idle" ? "○" : "";
  return div().w(size).flex_none().text_size(size * 0.9).text_color(t[status] ?? t.dim).child(g);
}

function statusWord(t, u, status) {
  const word = STATUS_WORD[status];
  return word ? div().flex_none().text_size(u(STATUS_TEXT)).text_color(t[status]).child(word) : null;
}

function icon(t, item, size) {
  const p = item.program;
  if (p?.icon) return p.tint ? svg(p.icon).size(size).flex_none().text_color(t.muted) : image(p.icon).size(size).flex_none();
  return svg(`mods/recall/icons/${KIND_ICON[item.kind] ?? "panes"}.svg`).size(size).flex_none().text_color(t.dim);
}

/** Text with the matched characters (`idx`) drawn in `hitColor`. */
function highlighted(s, idx, color, hitColor) {
  if (!idx?.length) return div().flex_none().text_color(color).child(s ?? "");
  return h_flex().flex_none().children(segments(s, idx).map((seg) =>
    div().text_color(seg.hit ? hitColor : color).when(seg.hit, (d) => d.font_semibold()).child(seg.text)));
}

/** A buffer match is drawn as its excerpt; highlight the whole excerpt. */
function titleHits(item, hits) {
  if (!item.excerpt) return hits.title;
  return Array.from({ length: item.excerpt[1] - item.excerpt[0] }, (_, i) => item.excerpt[0] + i);
}

const KEY_GLYPH = { enter: "⏎", escape: "esc", tab: "⇥", up: "↑", down: "↓", left: "←", right: "→", backspace: "⌫", space: "␣" };
const MOD_GLYPH = { ctrl: "⌃", alt: "⌥", shift: "⇧", cmd: "⌘" };
/** "shift-tab" → "⇧⇥". */
export function keyLabel(keystroke) {
  if (!keystroke) return "";
  const parts = keystroke.split("-");
  const key = parts.pop();
  return parts.map((m) => MOD_GLYPH[m] ?? m).join("") + (KEY_GLYPH[key] ?? (key.length === 1 ? key.toUpperCase() : key));
}

// ── header ────────────────────────────────────────────────────────────────

function filterChip(t, u, label) {
  return div().px(u(6)).h(u(18)).flex_none().flex().items_center().rounded(u(4)).text_size(u(11)).font_semibold()
    .bg(t[CHIP_COLOR[label] ?? CLUE_COLOR[label] ?? "accent"] ?? t.accent).text_color(t.background)
    .child(label === "." ? "content" : label);
}

function sortToggle(t, u, nav) {
  return h_flex().flex_none().gap(u(2)).p(u(2)).rounded(u(7)).bg(t.raised).children(["mru", "priority", "grouped"].map((s) =>
    div().id(`recall-sort-${s}`).px(u(8)).h(u(20)).flex().items_center().rounded(u(5)).text_size(u(11.5)).cursor_pointer()
      .when(nav.agentSort === s, (el) => el.bg(t.selected).text_color(t.foreground))
      .when(nav.agentSort !== s, (el) => el.text_color(t.dim).hover((x) => x.text_color(t.foreground)))
      .on_click((_e, cx) => { nav.switchTo(nav.category, s); cx.notify(); })
      .child(SORT_LABEL[s])));
}

function header(t, u, nav, view) {
  const label = view.label;
  const count = nav.query.trim() && view.total !== null ? `${view.count}/${view.total}` : String(view.count);
  const search = h_flex().flex_1().h(u(30)).px(u(10)).gap(u(8)).items_center().rounded(u(8)).border_1()
    .border_color(nav.mode === "navigation" ? t.border : t.accent).bg(t.background)
    .children([
      svg("mods/recall/icons/search.svg").size(u(14)).text_color(t.dim),
      label ? filterChip(t, u, label) : null,
      Input.new(nav.input).flex_1().h_full().text_size(u(12.8)).text_color(nav.mode === "navigation" ? t.muted : t.foreground),
      nav.mode === "navigation" && !nav.query ? div().flex_none().text_size(u(11)).text_color(t.dim).child("/ to filter") : null,
      div().flex_none().text_size(u(11)).text_color(t.dim).child(count),
    ].filter(Boolean));
  return h_flex().h(u(48)).flex_none().px(u(12)).gap(u(12)).items_center().border_b(1).border_color(t.border)
    .children([
      div().w(u(150)).flex_none().text_size(u(14)).font_semibold().truncate().child(CATEGORY[nav.category].title),
      search,
      nav.category === "agents" ? sortToggle(t, u, nav) : null,
      div().flex_none().text_size(u(11)).text_color(t.dim).child("Esc"),
    ].filter(Boolean));
}

// ── rail and table ─────────────────────────────────────────────────────────

function rail(t, u, nav) {
  const entry = (c) => {
    const on = c === nav.category;
    return v_flex().id(`recall-cat-${c}`).w(u(48)).h(u(46)).gap(u(2)).items_center().justify_center().rounded(u(8)).cursor_pointer()
      .when(on, (el) => el.bg(t.selected))
      .when(!on, (el) => el.hover((s) => s.bg(t.hover)))
      .on_click((_e, cx) => { nav.switchTo(c); nav.focusForMode(); cx.notify(); })
      .child(svg(`mods/recall/icons/${CATEGORY[c].icon}.svg`).size(u(16)).text_color(on ? t.accent : t.muted))
      .child(div().text_size(u(9.5)).text_color(on ? t.foreground : t.dim).child(CATEGORY[c].label));
  };
  return v_flex().w(u(LAYOUT.rail)).h_full().flex_none().py(u(6)).gap(u(2)).items_center().border_r(1).border_color(t.border)
    .children(nav.categories.map(entry));
}

/** The grip on a column's left edge, over the gap before it. */
function edge(t, u, nav, column) {
  const on = nav.resizing?.column === column;
  return h_flex().id(`recall-edge-${column}`).absolute().top(0).bottom(0).left(u(-8)).w(u(8)).justify_center().cursor_col_resize()
    .hover((x) => x.bg(t.hover))
    .on_mouse_down("left", (e, cx) => { nav.startResize(column, e); cx.stop_propagation(); cx.notify(); })
    .child(div().w(1).h_full().bg(on ? t.accent : t.border));
}

/**
 * A sized column's box, at the width nav.widths gives it, the same in the
 * head and in every row. Those widths already leave the name its room; the
 * name takes what they leave, and never less than nav.widths.name. On a
 * dialog too narrow even for that, location, folder and branch narrow in
 * proportion; status holds a word or two that must stay whole, so it
 * keeps its width.
 *
 * The head and a row hold the same cells: the status glyph, the icon, the
 * name, the shown columns and the badge. lib/columns.js counts on that to
 * know how much of a row the name and the columns have.
 */
const sized = (el, u, nav, key) => (key === "status"
  ? el.w(u(nav.widths.status)).flex_none()
  : el.w(u(nav.widths[key])).flex_shrink(1).min_w(0));

function columnHead(t, u, nav) {
  const label = (key, text) => h_flex().id(`recall-col-${key}`).size_full().min_w(0).items_center()
    .when(key === "status", (el) => el.justify_end())
    .text_color(t.dim)
    .child(div().truncate().child(text));
  const head = (key) => sized(h_flex(), u, nav, key).h_full().relative()
    .child(label(key, headLabel(key, nav.category))).child(edge(t, u, nav, key));
  return h_flex().h(u(26)).flex_none().mx(u(LAYOUT.margin)).px(u(LAYOUT.pad)).gap(u(LAYOUT.gap)).items_center()
    .text_size(u(HEAD_TEXT)).font_semibold().border_b(1).border_color(t.border)
    .child(div().w(u(LAYOUT.glyph)).flex_none())
    .child(div().w(u(LAYOUT.icon)).flex_none())
    .child(h_flex().flex_1().min_w(u(nav.widths.name)).h_full().child(label("name", "NAME")))
    .children(shownColumns(nav.category).map(head))
    .child(div().w(u(LAYOUT.badge)).flex_none());
}

function row(t, u, nav, { item, hits }, on) {
  const isClueRow = item.kind === "clue" || item.kind === "hint";
  const cell = (key, text, color) => sized(div(), u, nav, key).truncate().text_size(u(CELL_TEXT)).text_color(color).child(text || "");
  const cells = {
    location: () => cell("location", location(item), t.muted),
    // A folder too long for its column loses its start: what tells two paths apart is at their end.
    folder: () => cell("folder", item.path, t.dim).text_ellipsis_start(),
    branch: () => cell("branch", item.branch, t.dim),
    status: () => sized(h_flex(), u, nav, "status").justify_end().child(statusWord(t, u, item.status) ?? div()),
  };
  // The id is what makes the light follow the pointer: Herdr draws a frame
  // for a hover only on an element it keeps state for, and without one the
  // light waits for the next frame something else asks for.
  return h_flex().id(`recall-row-${item.key}`).h(u(ROW)).mx(u(LAYOUT.margin)).px(u(LAYOUT.pad)).gap(u(LAYOUT.gap)).items_center().rounded(u(6))
    .when(on, (el) => el.bg(t.selection))
    // The row under the pointer lights up, except during a column resize,
    // when the pointer only passes over it. A style, not a handler, so the
    // list's renderer may declare it.
    .when(!nav.resizing, (el) => el.cursor_pointer())
    .when(!on && !nav.resizing, (el) => el.hover((s) => s.bg(t.hover)))
    .child(glyph(t, item.status, u(LAYOUT.glyph)))
    .child(isClueRow
      ? div().w(u(LAYOUT.icon)).flex_none().text_size(u(11)).font_semibold().text_color(item.kind === "hint" ? t.dim : t[CLUE_COLOR[item.clue]] ?? t.dim).child(item.clue)
      : h_flex().w(u(LAYOUT.icon)).flex_none().child(icon(t, item, u(14))))
    .child(h_flex().flex_1().min_w(u(nav.widths.name)).gap(u(NAME_GAP)).items_center().overflow_hidden()
      .when(Boolean(item.nested), (el) => el.pl(u(NESTED_INDENT)))
      .child(h_flex().flex_none().items_center()
        // All's path, dimmed, right before the name; it starts with the
        // `where` field, so that field's hits light up inside it.
        .when(Boolean(item.crumb), (el) => el.child(highlighted(item.crumb, hits.where, t.dim, t.accent)))
        .child(highlighted(item.title, titleHits(item, hits), item.kind === "hint" ? t.dim : t.foreground, t.accent)
          .when(Boolean(item.current), (d) => d.font_semibold())))
      .when(item.kind === "hint", (el) => el.child(div().flex_none().text_color(t.blocked).child(`(${item.reason})`)))
      // An unnamed tab's panes, in what room is left; it is the `panes`
      // field, so that field's hits light up inside it.
      .when(Boolean(item.paneList), (el) => el.child(h_flex().min_w(0).overflow_hidden().text_size(u(12))
        .child(highlighted(item.paneList, hits.panes, t.dim, t.accent))))
      .when(Boolean(item.message), (el) => el.child(div().min_w(0).truncate().text_size(u(12)).text_color(t.dim).child(item.message))))
    .children(shownColumns(nav.category).map((key) => cells[key]()))
    .child(badge(t, item, u(LAYOUT.badge)));
}

function list(t, u, nav, loading) {
  const rows = nav.rows;
  if (!rows.length) {
    const msg = loading ? "Reading panes…" : nav.query ? "Nothing matches" : "Nothing here yet";
    return v_flex().size_full().items_center().justify_center().text_color(t.dim).child(msg);
  }
  // A virtual list, not uniform_list: only it takes the scroll handle that
  // keeps the selected row in view (uniform_list ignores track_scroll).
  return v_virtual_list("recall-rows", rows.length, u(ROW), (i) => rows[i].item.key, (range) => {
    const out = [];
    for (let i = range.start; i < range.end; i++) out.push(row(t, u, nav, rows[i], i === nav.at));
    return out;
  })
    .track_scroll(nav.scroll)
    .on_item_click((key, cx) => {
      const r = rows.find((x) => x.item.key === key);
      if (!r) return;
      nav.open(r.item);
      if (!nav.done) { nav.focusForMode(); cx.notify(); }
    })
    .size_full();
}

// ── footer ────────────────────────────────────────────────────────────────

/** The keys worth knowing in this mode: [keys, what they do], the last one drawn at the right. */
function hints(nav) {
  const first = (a) => keyLabel(nav.keys[a]?.[0]);
  const move = `${first("move_up")}${first("move_down")}`;
  const close = [first("dismiss"), nav.query ? "clear" : "close"];
  let out;
  if (nav.mode === "navigation") out = [[first("select"), "open"], [move, "move"], ["/", "filter"], [first("next_category"), "category"], close];
  else if (nav.mode === "filtering") out = [[first("select"), "open"], [move, "move"], [first("dismiss"), "done"], [first("force_quit"), "close"]];
  else out = [[first("select"), "open"], [move, "move"], [first("next_category"), "category"], close];
  const extra = nav.category === "agents" ? [["⌃S", "sort"]] : nav.category === "clues" ? [[".", "buffers"], [PREFIXES, "prefixes"]] : [];
  return [...out.slice(0, -1), ...extra, out[out.length - 1]];
}

function footer(t, u, nav) {
  const chip = ([keys, label]) => h_flex().flex_none().gap(u(5)).items_center()
    .child(div().px(u(5)).rounded(u(4)).bg(t.raised).text_color(t.muted).child(keys))
    .child(div().text_color(t.dim).child(label));
  const all = hints(nav);
  const tail = all.pop();
  return h_flex().h(u(28)).flex_none().px(u(14)).gap(u(14)).items_center().border_t(1).border_color(t.border).bg(t.chrome)
    .text_size(u(11)).overflow_hidden()
    .children([
      nav.configError ? div().flex_none().max_w(u(320)).truncate().text_color(t.blocked).child(nav.configError) : null,
      ...all.map(chip),
      div().flex_1(),
      chip(tail),
    ].filter(Boolean));
}

// ── the dialog ────────────────────────────────────────────────────────────

export function navigator(nav, { view, loading }) {
  const t = theme();
  const u = (px) => px * nav.scale;
  return v_flex().id("recall-table").size_full()
    // A resize follows the pointer anywhere over the dialog, and ends on release or on leaving it.
    .when(Boolean(nav.resizing), (el) => el.cursor_col_resize())
    .on_mouse_move((e, cx) => { if (nav.resizeTo(e.position.x)) cx.notify(); })
    .on_mouse_up("left", (_e, cx) => { if (nav.endResize()) cx.notify(); })
    .on_hover((hovered, cx) => { if (!hovered && nav.endResize()) cx.notify(); })
    .child(header(t, u, nav, view))
    .child(h_flex().flex_1().min_h(0).items_start()
      .child(rail(t, u, nav))
      .child(v_flex().flex_1().min_w(0).h_full().py(u(4))
        .child(columnHead(t, u, nav))
        .child(div().flex_1().min_h(0).pt(u(2)).child(list(t, u, nav, loading)))))
    .child(footer(t, u, nav));
}
