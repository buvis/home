// Kanso's panel kit: the Menu, an optional heading and its items, drawn one way wherever one opens. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-menu.js.
import { div, svg } from "gpui-kit";
import { h_flex, v_flex, Button } from "gpui-base";
import { G, H, R, T, W, ICON_ROW, TINT, breathe, glyphOf, mix } from "./ui.js";
import { armedLook, pressAgain, withLook } from "./ui-button.js";
import { tile } from "./ui-avatar.js";
import { field } from "./ui-field.js";
import { dot as drawDot } from "./ui-dot.js";
import { mark } from "./ui-mark.js";
import { stateBlock, stateBlockPx } from "./ui-state.js";

const RULE = 1;
const ITEM_PX = H.control;
const TWO_LINES_PX = H.control + G.md;
// A scroll run shows this many items unless it says.
export const RUN_ROWS = 4;

// A heading wraps; its `mark` sits at its right, the state of what it names.
export const menuHeading = (title, c, status = null) => div().min_h(H.icon).flex().items_center().px(G.sm).py(G.xs).text_size(T.body).text_color(c.dim).child(title)
  .when(Boolean(status), (el) => el.justify_between().gap(G.sm).child(mark(c, { status, size: "sm" })));
export const menuSeparator = (c) => div().m(G.xs).border_t_1().border_color(c.border);
const spacer = () => div().size(ICON_ROW).flex_none().flex().items_center().justify_center();
// An item leads with an app's picture or letter as a tile, a colour dot, or its icon.
const lead = (c, { picture, letter, tone, dot, icon }, ink) => {
  if (picture || letter) return tile(c, { initial: letter ?? "", image: picture, size: "sm", tone });
  if (dot) return spacer().child(drawDot(c, dot));
  return icon ? svg(glyphOf(icon)).size(ICON_ROW).flex_none().text_color(ink) : spacer();
};
const badge = (text, c) => div().flex().flex_none().items_center().h(H.badge).px(G.sm).rounded_full().bg(mix(c.accent, c.popover, TINT.soft))
  .text_size(T.body).font_semibold().text_color(c.accent).child(text);
const labelOf = (words, second, ink, c) => (second
  ? v_flex().flex_1().min_w(0).child(div().truncate().text_size(T.value).text_color(ink).child(words))
    .child(div().truncate().text_size(T.body).text_color(c.dim).child(second))
  : div().flex_1().min_w(0).truncate().text_size(T.value).text_color(ink).child(words));
// Loading items in a row read as one skeleton, the view's one breathing block.
const bone = (c) => h_flex().w_full().h(ITEM_PX).flex_none().items_center().gap(G.sm).px(G.sm)
  .child(div().size(ICON_ROW).flex_none().rounded(R.sm).bg(c.border))
  .child(div().flex_1().h(G.sm).rounded(R.sm).bg(c.border));
const bones = (count, c) => breathe(v_flex().id("kanso-skeleton").w_full()).children(Array.from({ length: count }, () => bone(c)));
const grouped = (items) => items.reduce((lines, line) => {
  const end = lines.length - 1;
  if (!line.loading) return [...lines, line];
  return lines[end]?.bones ? lines.map((kept, i) => (i === end ? { bones: kept.bones + 1 } : kept)) : [...lines, { bones: 1 }];
}, []);

const lookOf = (c, { armed, selected, disabled }) => {
  if (disabled) return { fill: null, ink: c.dim, hover: null, press: null };
  if (armed) return armedLook(c);
  return { fill: selected ? c.selected : null, ink: c.text, hover: c.w7, press: c.selected };
};

/** One item: `selected` is the lit one (the keyboard's, or the current choice); `armed` asks twice, in the button's words;
 * `disabled` is dim and does nothing; `checked` ends it with a check; `second` is a line under the label.
 * Without `onClick` it takes no handler; `onSecondaryClick` answers a right click. `position`: [n, of] for a screen reader. */
export function menuItem(id, { icon = null, picture = null, letter = null, tone = null, dot = null, label, second = null, hint = null, badge: count = null,
  mark: status = null, armed = false, verb = null, selected = false, checked = false, disabled = false, onClick = null, onSecondaryClick = null, position = null }, c) {
  const look = lookOf(c, { armed, selected, disabled });
  const words = armed ? pressAgain(verb ?? String(label).toLowerCase()) : label;
  return withLook(Button.new(id), look).w_full().h(second ? TWO_LINES_PX : ITEM_PX).flex_none().items_center().gap(G.sm).px(G.sm).rounded(R.control)
    .accessibility_label(words)
    .disabled(disabled)
    .selected(selected)
    .when(Boolean(position), (el) => el.set_position(...position))
    .when(!disabled, (el) => el.focus((s) => s.bg(c.selected)))
    .when(Boolean(onClick) && !disabled, (el) => el.on_click((_e, cx) => onClick(cx)))
    .when(Boolean(onSecondaryClick) && !disabled, (el) => el.on_mouse_down("right", (_e, cx) => { cx.stop_propagation(); onSecondaryClick(cx); }))
    .child(lead(c, { picture, letter, tone, dot, icon }, armed ? look.ink : c.muted))
    .child(labelOf(words, second, look.ink, c))
    .when(Boolean(count), (el) => el.child(badge(count, c)))
    .when(Boolean(hint), (el) => el.child(div().flex_none().text_size(T.body).text_color(c.dim).child(hint)))
    .when(Boolean(status), (el) => el.child(mark(c, { status })))
    .when(checked, (el) => el.child(svg(glyphOf("check")).size(ICON_ROW).flex_none().text_color(c.muted)));
}

// A `scroll` run shows `rows` items, the rest scroll inside the menu; `handle`, a ScrollHandle, lets the keyboard bring one into view.
const run = (id, line, c) => v_flex().id(id).flex_none().max_h(linePx(line)).overflow_y_scrollbar()
  .when(Boolean(line.handle), (el) => el.track_scroll(line.handle))
  .children(drawn(id, line.scroll, c));

// A `field` finds in the menu: `text` is its TextField.
const finder = (id, { field: label, text }, c) => div().p(G.xs).child(field(id, text, c, { icon: "search", spoken: label }));

function entry(id, line, c) {
  if (line.separator) return menuSeparator(c);
  if (line.field) return finder(id, line, c);
  if (line.failure) return stateBlock(id, c, line.failure);
  if (line.heading) return menuHeading(line.heading, c, line.mark);
  if (line.scroll) return run(id, line, c);
  if (line.bones) return bones(line.bones, c);
  return menuItem(id, line, c);
}

const linePx = (line) => {
  if (line.separator) return 2 * G.xs + RULE;
  if (line.field) return 2 * G.xs + H.control;
  if (line.failure) return stateBlockPx(line.failure);
  if (line.heading) return H.icon;
  if (line.scroll) return line.scroll.slice(0, line.rows ?? RUN_ROWS).reduce((sum, item) => sum + linePx(item), 0);
  return line.second ? TWO_LINES_PX : ITEM_PX;
};

// Each item knows its place among the list's items, for a screen reader.
const placed = (lines) => {
  const items = lines.filter((line) => "label" in line);
  return lines.map((line) => ("label" in line ? { ...line, position: [items.indexOf(line) + 1, items.length] } : line));
};
function drawn(id, lines, c) {
  return grouped(placed(lines)).map((line, i) => entry(`${id}-${i}`, line, c));
}

/** How tall a Menu with these lines draws, for a popup that opens at its size. */
export const menuHeight = ({ title = null, items = [] }) => 2 * G.xs + (title ? H.icon : 0) + items.reduce((sum, line) => sum + linePx(line), 0);

/** The Menu inside a frame its host draws (a popup Herdr frames): its heading and items, full width. `items`: an item (see menuItem),
 * { heading, mark }, { loading: true }, { failure: { text, source, fix, onClick } }, { field, text }, { scroll: items, rows, handle } or { separator: true }. */
export const menuList = (id, { title = null, items = [] }, c) => v_flex().id(id).w_full().p(G.xs).bg(c.popover)
  .when(Boolean(title), (el) => el.child(menuHeading(title, c)))
  .children(drawn(id, items, c));

/** A Menu that draws its own frame, where it hangs from a control. */
export const menu = (id, { title = null, items = [] }, c) => menuList(id, { title, items }, c).w(W.menu).rounded(R.card).border_1().border_color(c.border).shadow_md();
