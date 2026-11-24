// Kanso's panel kit: the tab group. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-tab.js.
import { svg } from "gpui-kit";
import { Button } from "gpui-base";
import { FOCUS, CLEAR, glyphOf } from "./ui.js";
import { field } from "./ui-field.js";
import { mark } from "./ui-mark.js";
import { pendingDot } from "./ui-state.js";
import { RULES, TAB_LOOKS } from "./ui-css.js";
import { TAB_PARTS, tabParts, tabKey, tabStates } from "./ui-tab-shapes.js";
import { lookOf, painted, lastOp, boxOf } from "./ui-draw.js";
import { Answers } from "./ui-match.js";

/** The most characters a tab's name holds. */
export const TAB_NAME_LIMIT = 64;

const known = new Answers();
const tabLooks = (group, states) => known.of(tabKey(group, states), () => {
  const kept = TAB_LOOKS.tabs[tabKey(group, states)];
  const shapes = kept ? null : tabParts(group, states);
  const parts = Object.fromEntries(TAB_PARTS.map((part, i) => [part, kept ? TAB_LOOKS.looks[kept[i]] : lookOf(shapes[part][0], RULES, null, shapes[part][1])]));
  const inset = lastOp(parts.tab.own, "px")?.[1] ?? 0;
  const ringed = inset > 0 ? { ...parts.tab, own: parts.tab.own.map((op) => (op[0] === "px" ? ["px", inset - FOCUS] : op)) } : parts.tab;
  return { ...parts, tab: ringed };
});

const glyph = (icon, looks, c) => painted(svg(glyphOf(icon)), looks.glyph, c);

// The press stays on the ×: the tab under it is not chosen. A tab that is off draws its × and does nothing.
const closeGlyph = (id, c, looks, label, onClose, disabled) => painted(Button.new(`${id}-close`), looks.close, c)
  .m(-FOCUS).border(FOCUS).border_color(CLEAR).focus((s) => s.border_color(c.accent))
  .disabled(disabled)
  .accessibility_label(`Close ${label}`)
  .when(!disabled, (el) => el.on_mouse_down("left", (_e, cx) => cx.stop_propagation()).on_click((_e, cx) => { cx.stop_propagation(); onClose(cx); }))
  .child(glyph("x", looks, c));

const nameOf = (id, item, c, looks) => (item.editing
  ? field(`${id}-name`, item.editing, c, { inline: true, spoken: item.label }).min_w(0)
    .on_mouse_down("left", (_e, cx) => cx.stop_propagation()).on_click((_e, cx) => cx.stop_propagation())
  : boxOf(looks.label, c).child(item.label));

export function tabItem(id, item, c, { group, on = false, square = false, index = 0, count = 1, onChange = null, onClose = null, onPress = null } = {}) {
  const { disabled } = group;
  const armed = Boolean(item.armed) && !disabled;
  const states = { on, square, armed, pending: Boolean(item.pending), held: Boolean(item.held), live: !disabled && !on && !armed && !item.held };
  const looks = tabLooks(group, states);
  const dot = (item.dot || (square && item.mark === "blocked")) && !on;
  return painted(Button.new(id), looks.tab, c)
    .border(FOCUS).border_color(CLEAR).focus((s) => s.border_color(c.accent))
    .selected(on)
    .disabled(disabled)
    .set_position(index + 1, count)
    .accessibility_label(item.label)
    .when(square, (el) => el.tooltip(item.label))
    .when(!square && Boolean(item.tip), (el) => el.tooltip(item.tip))
    .when(!disabled, (el) => el.cursor_pointer()
      .on_mouse_down("left", (e, cx) => { cx.stop_propagation(); onPress?.(e, cx); })
      .on_click((_e, cx) => { if (!on) onChange?.(item.key, cx); }))
    .when(Boolean(item.icon), (el) => el.child(glyph(item.icon, looks, c)))
    .when(!square || !item.icon, (el) => el.child(nameOf(id, item, c, looks)))
    .when(Boolean(item.pending), (el) => el.child(pendingDot(`${id}-pending`, c)))
    .when(Boolean(item.mark) && !square, (el) => el.child(mark(c, { status: item.mark })))
    .when(dot, (el) => el.child(boxOf(looks.dot, c)))
    .when(on && Boolean(item.closable && onClose) && !square && !item.editing, (el) => el.child(closeGlyph(id, c, looks, item.label, onClose, disabled)));
}

export function tab(id, items, value, onChange, c, { disabled = false, spoken = null, collapsed = false, track = true, size = "lg", bar = false, on = {} } = {}) {
  const group = { size, track, disabled, bar };
  const base = tabLooks(group, tabStates(group, []));
  const seg = (item, index) => {
    const own = on[item.key] ?? {};
    const drawn = tabItem(`${id}-${item.key}`, item, c, { group, on: value === item.key, square: collapsed, index, count: items.length, onChange, onClose: own.onClose, onPress: own.onPress });
    const wired = own.wire ? own.wire(drawn) : drawn;
    const landing = item.drop ? boxOf(base.insertion, c) : null;
    return item.drop === "after" ? [wired, landing] : [landing, wired];
  };
  return boxOf(base.list, c, id).when(collapsed, (el) => el.flex_col())
    .when(Boolean(spoken), (el) => el.accessibility_label(spoken))
    .children(items.flatMap(seg).filter(Boolean));
}

/** Today's name for `tab`. */
export const segmented = tab;
