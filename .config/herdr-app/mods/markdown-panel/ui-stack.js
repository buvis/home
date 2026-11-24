// Kanso's panel kit: the stacks, the wrappers that only place other pieces, each laid out as its Storybook class lays it out. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-stack.js.
import { h_flex, v_flex, Button, Popover } from "gpui-base";
import { div } from "gpui-kit";
import { G, H, R, T, LINE, PANE, SIDEBAR, DIALOG, TINT, CLEAR, alpha, sidebarSides } from "./ui.js";
import { dot } from "./ui-dot.js";
import { RULES } from "./ui-css.js";
import { box, lastOp } from "./ui-draw.js";
import { stylesFor } from "./ui-match.js";

// Each child piece drawn with its own id and its stack's handlers; a piece that draws nothing leaves no gap. `context` says where it sits;
// `slots` names each place, else its index.
const drawn = (id, c, kids, more = {}, context = {}, slots = []) => kids
  .map((kid, i) => (typeof kid === "function" ? kid(`${id}-${slots[i] ?? i}`, c, more, context) : kid)).filter(Boolean);
const placed = (el, id, c, kids, more, context, slots) => el.children(drawn(id, c, kids, more, context, slots));

// A Button whose menu, open, hangs beside it (`anchor`): a press on the Button opens it; once open, Herdr's popover shuts it
// on a press, outside it or on Escape. `onOpen(open, cx)` says which. Without `onOpen` the pieces are only placed.
const withMenu = (anchor, room) => (id, c, _flags, [first, menu = null], more, wire, context) => {
  const { onOpen = null, onChange = null } = more;
  if (!onOpen) return placed(h_flex().flex_none(), id, c, [first, menu], more, context);
  const trigger = first(`${id}-button`, c, { ...more, onClick: menu ? null : (cx) => onOpen(true, cx) }, { ...context, ink: menu ? null : context.ink });
  const pop = Popover.new(id).trigger(trigger).anchor(anchor(context)).open(Boolean(menu)).on_open_change((open, cx) => onOpen(open, cx));
  return menu ? pop.content(room(context).child(menu(`${id}-menu`, c, { onChange }, context))) : pop;
};

// One group on the rail, centred in its row: a button, so Tab reaches it and Enter or Space presses it; `wire` gives it the pointer's handlers.
// Its ring is a border kept clear at rest, so nothing moves.
const railTile = (id, c, { on, strong, label }, kids, { onClick = null }, wire) => h_flex().w_full().h(SIDEBAR.railRow).flex_none().justify_center().items_center().child(wire(Button.new(id).w(SIDEBAR.tile).h(H.row).flex_none()
  .flex().flex_col().items_center().justify_center().gap(G.hair).rounded(R.control).cursor_pointer()
  .border_1().border_color(strong ? alpha(c.accent, TINT.ring) : CLEAR).focus((s) => s.border_color(c.accent))
  .selected(on)
  .when(Boolean(label), (el) => el.accessibility_label(label).tooltip(label))
  .when(on, (el) => el.bg(c.w12))
  .when(!on, (el) => el.hover((s) => s.bg(c.w4)))
  .when(Boolean(onClick), (el) => el.on_click((_e, cx) => onClick(cx)))
  .children(drawn(id, c, kids))));

// Open, the track across the sidebar's gutter. Collapsed (`onOpen`), the current view's button; open, its menu beside it.
// The button and its menu are a Button with its menu, as Sort's and Settings' are.
const bare = () => div();
const below = () => div().pt(G.xs);
const viewMenu = withMenu(() => "left_center", bare);
const viewSwitch = (id, c, flags, kids, more, wire, context) => {
  const { onChange = null, onOpen = null } = more;
  if (!onOpen) return kids[0](`${id}-tabs`, c, { onChange }).mx(G.sm).mt(G.xs).mb(G.sm);
  return h_flex().flex_none().justify_center().mt(G.xs).mb(G.sm).child(viewMenu(id, c, flags, kids, more, wire, context));
};

// The Toolbar: large icon Buttons in a row 4 apart, or a column 8 apart; a press in it stays in it.
// In the header, the row is 40 tall and the column a hair below the header's top.
const toolbar = (id, c, { column }, kids, more, _wire, { header = false }) => placed((column ? v_flex().gap(G.sm) : h_flex().gap(G.xs)).id(id).flex_none().items_center()
  .when(header && !column, (el) => el.h(H.row)).when(header && column, (el) => el.pt(G.hair))
  .on_mouse_down("left", (_e, cx) => cx.stop_propagation()), id, c, kids, more, { column });
// Sort is dim at its default order, and drawn like the other tools once sorted.
const sortMenu = withMenu(({ column }) => (column ? "left_center" : "top_left"), ({ column }) => (column ? div().pl(G.xs) : below()));
const sort = (id, c, { sorted }, kids, more, wire, context) => sortMenu(id, c, {}, kids, more, wire, { ...context, ink: sorted ? null : "dim" });
// The header: 8 at the sides seen, so the Toolbar's icons sit 15.5 in, as the Storybook's do; collapsed, the rail's column, centred. Dawn's sky lies behind the rest.
const header = (id, c, { collapsed }, kids, more) => placed(v_flex().id(id).w_full().flex_none().relative().overflow_hidden().bg(c.chrome).pb(G.xs)
  .when(collapsed, (el) => el.px(G.sm).items_center()).when(!collapsed, (el) => sidebarSides(el, G.sm)), id, c, kids, more, { header: true });
// The lights' row, as tall as the tab bar, Dawn Mode's pill at its right. Herdr draws the lights in this block itself,
// so the app kit has no windowControls (kit-parity `missing`) and the row lays out only what it holds.
const headerTitle = (id, c, _flags, kids, more) => placed(h_flex().w_full().h(H.tabBar).flex_none().items_center().justify_end().pl(G.xs), id, c, kids, more);
// A dialog's rows, one line each, a hairline apart. Proposed: `scroll`, a set height of at most six rows, past it the list scrolls;
// it keeps the rows' side room, so a ring is not cut.
const dialogList = (id, c, { scroll = false }, kids) => {
  const rows = drawn(id, c, kids).map((kid) => kid.flex_none());
  return v_flex().id(id).flex_none().mt(G.sm).gap(G.hair).children(rows)
    .when(scroll, (el) => el.h(Math.min(rows.length * (H.line + G.hair) - G.hair, DIALOG.list)).mx(-G.sm).px(G.sm).overflow_y_scrollbar());
};

// The footer's room, its height fitted to its rows: open, its rows touch between 8 above and 16 below, on the sidebar's gutter
// at both sides seen, as the list's rows are; a refused update's block a hair under its row and 8 above the next; in the rail, its icon Buttons a hair apart above 12.
export const FOOTER = Object.freeze({ top: G.sm, bottom: G.md, side: SIDEBAR.gutter, railBottom: G.md, railGap: G.hair, refusalAbove: G.hair, refusalBelow: G.sm });
// The Footer composition's pieces by name: kansō's update, its refusal (only under it), then Settings, always last.
// Each is drawn under its name, so Settings keeps its id as the rows above it come and go.
const footerSlots = (kids, slots = null) => slots ?? (kids.length === 3 ? ["update", "refused", "settings"] : ["update", "settings"].slice(-kids.length));

const cssNode = (classes, parent = null) => ({ tag: "div", attrs: {}, classes, parent, children: [] });
const statusFace = () => cssNode(["kanso-status-bar", "kanso-status-bar--grid"]);
// The row and its three tracks stand in for grid-template-columns, which gpui cannot draw.
const statusBar = (id, c, _flags, kids, more) => placed(box(statusFace(), c, RULES, id).flex().w_full(),
  id, c, kids, more, {}, ["left", "middle", "right"]);
const statusHalf = (end) => (id, c, _flags, kids, more) => (kids.length ? placed(box(
  cssNode([end ? "kanso-status-bar__right" : "kanso-status-bar__left"], statusFace()), c, RULES, id).h_full().flex_1(), id, c, kids, more) : null);
const statusMiddle = (id, c, _flags, kids, more) => (kids.length ? placed(box(
  cssNode(["kanso-status-bar__middle"], statusFace()), c, RULES, id).h_full().flex_none(), id, c, kids, more) : null);

const tabBarFace = () => cssNode(["kanso-tab-bar"]);
const opOf = (node, name) => lastOp(stylesFor(node, RULES), name)?.[1] ?? 0;
const doorsFace = () => cssNode(["kanso-tab-bar__doors"], tabBarFace());
const doorFace = () => ({ ...cssNode(["kanso-button", "kanso-button--icon"], doorsFace()), tag: "span" });
const tabBar = (id, c, _flags, kids, more) => box(tabBarFace(), c, RULES, id).w_full()
  .children(kids.map((kid, i) => (typeof kid === "function" ? kid(`${id}-${i}`, c, more, { bar: true, index: i }) : kid)).filter(Boolean));
const tabBarMenu = withMenu(() => "top_left", below);
const tabBarDoors = (id, c, _flags, kids, more) => placed(box(doorsFace(), c, RULES, id), id, c, kids, more);
const tabBarInsertion = (id, c) => box({ ...cssNode(["kanso-tab-bar__insertion"], doorsFace()), tag: "i" }, c, RULES, id);
const holder = (id, c, _flags, kids, more, _wire, context) => placed(div(), id, c, kids, more, context);

export const tabBarRoom = (width, { tools = [], doors = [] }) => {
  const bar = tabBarFace(), gap = opOf(bar, "gap"), side = opOf(doorFace(), "w"), doorGap = opOf(doorsFace(), "gap");
  const pad = stylesFor(bar, RULES).filter(([op]) => op === "px" || op === "pl" || op === "pr").reduce((sum, [op, value]) => ({ ...sum, ...(op === "px" ? { pl: value, pr: value } : { [op]: value }) }), {});
  const doorsWidth = doors.reduce((sum, door, i) => sum + (door ?? side) + (i ? doorGap : 0), 0);
  const toolsWidth = tools.reduce((sum, tool) => sum + (tool ?? side) + gap, 0);
  return width - (pad.pl ?? 0) - (pad.pr ?? 0) - toolsWidth - 2 * gap - doorsWidth;
};

const STACKS = {
  toolbar: { states: ["column"], draw: toolbar },
  "toolbar add": { draw: (id, c, _flags, kids, more, _wire, context) => placed(h_flex().flex_none(), id, c, kids, more, context) },
  "toolbar sort": { states: ["sorted"], draw: sort },
  "toolbar group": { states: ["open"], draw: (id, c, { open }, kids, more, _wire, context) => placed(v_flex().id(id).flex_none().items_center().gap(G.xs).rounded(R.card)
    .when(open, (el) => el.bg(c.w4)), id, c, kids, more, context) },
  "toolbar menu": { draw: holder },
  sidebar: { draw: (id, c, _flags, kids, more) => placed(v_flex().id(id).size_full().min_h(0).bg(c.chrome).text_size(T.card), id, c, kids, more) },
  "sidebar switch": { draw: (id, c, _flags, kids, more) => placed(div().id(id).flex_none(), id, c, kids, more) },
  "sidebar rows": { draw: (id, c, _flags, kids, more) => placed(v_flex().id(id).flex_1().min_h(0), id, c, kids, more) },
  "sidebar find": { draw: (id, c, _flags, kids, more) => h_flex().id(id).flex_none().items_center().pl(G.sm).pr(SIDEBAR.gutter).pb(G.sm).child(placed(div().flex_1().min_w(0), id, c, kids, more)) },
  header: { states: ["collapsed"], draw: header },
  "header title": { draw: headerTitle },
  "rail tile": { states: ["strong"], draw: railTile, pressable: true },
  "rail count": { draw: (id, c, _flags, kids) => h_flex().flex_none().items_center().gap(G.hair).children(drawn(id, c, kids)) },
  "view switch": { draw: viewSwitch },
  "view menu": { draw: (id, c, _flags, kids, more) => div().pl(G.xs).children(drawn(id, c, kids, more)) },
  // Proposed: the collapsed view button carrying the dot while someone needs you, a hairline in from its corner.
  "view button": { draw: (id, c, _flags, [button], more) => button(id, c, more).relative().child(dot(c, "blocked").absolute().top(LINE).right(LINE)) },
  // Both sit at the block's foot.
  footer: { states: ["height", "slots"], draw: (id, c, { height, slots }, kids, more) => placed(sidebarSides(v_flex().id(id).w_full().h(height).flex_none().justify_end().bg(c.chrome).pt(FOOTER.top), FOOTER.side).pb(FOOTER.bottom),
    id, c, kids, more, {}, footerSlots(kids, slots)) },
  "rail footer": { states: ["height", "slots"], draw: (id, c, { height, slots }, kids, more) => placed(v_flex().id(id).w_full().h(height).flex_none().justify_end().items_center().bg(c.chrome).pt(FOOTER.top).pb(FOOTER.railBottom)
    .gap(FOOTER.railGap), id, c, kids, more, {}, footerSlots(kids, slots)) },
  // Proposed: Settings and its menu, which opens over it; a refused update's block in the footer's room.
  "footer settings": { draw: withMenu(() => "bottom_left", bare) },
  "footer menu": { draw: holder },
  "footer refusal": { draw: (id, c, _flags, kids, more) => placed(div().mt(FOOTER.refusalAbove).mb(FOOTER.refusalBelow), id, c, kids, more) },
  "dialog list": { states: ["scroll"], draw: dialogList },
  "tab bar": { draw: tabBar },
  "tab bar more": { draw: tabBarMenu },
  "tab bar menu": { draw: holder },
  "tab bar doors": { draw: tabBarDoors },
  "tab bar insertion": { draw: tabBarInsertion },
  "status bar": { states: ["grid"], draw: statusBar },
  "status bar left": { draw: statusHalf(false) },
  "status bar middle": { draw: statusMiddle },
  "status bar right": { draw: statusHalf(true) },
  // The menu of the open item, beside the bar. The story anchors it to that item.
  "status bar popup": { draw: (id, c, _flags, kids, more) => placed(div().id(id), id, c, kids, more) },
  away: { draw: (id, c, _flags, kids, more) => placed(v_flex().id(id).flex_none().mx(G.sm).mb(G.md).pl(G.sm - LINE).pr(G.md - LINE).py(G.xs - LINE).rounded(R.card).bg(c.raised)
    .border_1().border_color(c.border), id, c, kids, more, { card: true }) },
};

/** A stack the app draws: `variant` names its layout, `flags` its states, `kids` its child pieces, `more` its handlers;
 * `wire` adds the pointer's handlers to what is pressed, the stack itself unless it says. An unknown variant or state throws, as the Storybook's does. */
export function stackOf(id, c, { variant, on = false, label = "", ...flags }, kids, more = {}, wire = (el) => el, context = {}) {
  if (!Object.hasOwn(STACKS, variant)) throw new Error(`kit: the app has no stack "${variant}"`);
  const { states = [], draw, pressable = false } = STACKS[variant];
  const unknown = Object.keys(flags).filter((flag) => !states.includes(flag));
  if (unknown.length) throw new Error(`kit: stack "${variant}" has no state ${unknown.join(", ")}`);
  const el = draw(id, c, { on, label, ...flags }, kids, more, wire, context);
  return pressable ? el : wire(el);
}
