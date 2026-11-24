// Kanso's panel kit: a status bar item, its mark or icon with its words, the item of an agent waiting for you, and panes per view. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-status.js.
import { div, svg } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { G, R, LINE, FOCUS, glyphOf } from "./ui.js";
import { mark } from "./ui-mark.js";
import { button } from "./ui-button.js";
import { tipText } from "./ui-tooltip.js";
import { pendingDot } from "./ui-state.js";
import { RULES } from "./ui-css.js";
import { paint } from "./ui-draw.js";
import { stylesFor } from "./ui-match.js";

const node = (classes, parent = null) => ({ tag: "span", attrs: {}, classes, parent, children: [] });
// The item's rules are written on the bar, so the node sits in one while the app draws the item.
const inBar = (classes) => node(classes, node(["kanso-status-bar", "kanso-status-bar--grid"]));
const ITEM_HOVER = "kanso-row--hover";
const iconNode = node(["kanso-icon", "kanso-icon--inline"]);
const press = (el, { tip, onClick }) => (onClick ? el.cursor_pointer().on_click((_e, cx) => onClick(cx)) : el)
  .when(Boolean(tip), (item) => item.tooltip(tip));

/** `mark`: an agent state drawn as its mark, else `icon`, a name in kanso-chrome's icons; `tone`: a tone name for an item in that state;
 * `pending`: drawn at once at the pending opacity with a breathing dot; `open`: its menu is open; `onClick` and `tip`: where it goes and what it says. */
export const statusItem = (id, c, { icon = null, mark: status = null, text = null, tone = null, pending = false, open = false, tip = null, onClick = null } = {}) => {
  const classes = ["kanso-status-bar__item", tone ? `kanso-text--${tone}` : "", pending ? "kanso-state-line--pending" : "", open ? "kanso-status-bar__item--open" : ""].filter(Boolean);
  const lead = status ? mark(c, { status, size: "sm" }) : icon ? paint(svg(glyphOf(icon)), iconNode, c, RULES) : null;
  return press(paint(h_flex().id(id), inBar(classes), c, RULES, ITEM_HOVER), { tip, onClick })
    .when(Boolean(lead), (el) => el.child(lead))
    .when(text != null && text !== "", (el) => el.child(div().child(String(text))))
    .when(pending, (el) => el.child(pendingDot(`${id}-pending`, c)));
};

/** Who waits: the blocked mark, the name, the question trimmed to its width, and +`more` for the others; neither the name nor +N folds.
 * The question has no colour of its own: muted with the bar, foreground with the item under the pointer. */
export const needsItem = (id, c, { name, question = null, more = 0, tip = null, onClick = null } = {}) => {
  const item = inBar(["kanso-status-bar__item", "kanso-status-bar__needs"]);
  return press(paint(h_flex().id(id), item, c, RULES, ITEM_HOVER), { tip, onClick })
    .child(mark(c, { status: "blocked", size: "sm" }))
    .child(paint(div(), node(["kanso-status-bar__name"], item), c, RULES).child(name))
    .when(Boolean(question), (el) => el.child(paint(div(), node(["kanso-status-bar__question"], item), c, RULES).child(question)))
    .when(more > 0, (el) => el.child(paint(div(), node(["kanso-status-bar__more"], item), c, RULES).child(`+${more}`)));
};

// The minimap's room: each column's Button keeps its ring clear around a hairline of side room, a hair from the next.
export const COLUMN = Object.freeze({ side: LINE + FOCUS, gap: G.hair });
const focused = (el, handle) => (handle ? el.track_focus(handle) : el);
// The cascade's display: hidden at rest, grid when the stepper is hovered or open.
const toolDisplay = (parent) => {
  const ops = stylesFor(node(["kanso-button"], parent), RULES).filter(([op]) => op === "hidden" || op === "grid");
  return ops.length ? ops[ops.length - 1][0] : null;
};
const withDisplay = (el, parent) => {
  const op = toolDisplay(parent);
  return op ? el[op]() : el;
};
const still = (el, at, c) => paint(el, at, c, RULES, null, false);
const columnFace = (c, columnsNode, { width, panes }) => {
  const column = node(["kanso-status-bar__column", ...(panes.length > 1 ? ["kanso-status-bar__column--stacked"] : [])], columnsNode);
  const pane = (tone) => paint(div().w(width), node(["kanso-status-bar__pane", `kanso-status-bar__pane--${tone}`], column), c, RULES);
  return still(v_flex(), column, c).children(panes.map(pane));
};

/** Panes per view: the number, which evens out on a press, between − and +. The glyphs stay hidden unless `hover` (the pointer or the keyboard
 * is on it) or `open`. `chords`: the key table's chords for fewer, more and fit. Proposed: `columns`, the minimap before it,
 * a Button per column, each `{ width, panes }` with a tone per pane. `on`: the presses `minus`, `plus`, `value` and `column(i, cx)`,
 * `hover(over, cx)`, and `focuses`, the handles of minus, plus and value. */
export const stepper = (id, c, { value = 2, open = false, hover = false, columns = [], chords = {} }, on = {}) => {
  const { minus = null, plus = null, value: even = null, column = null, hover: onHover = null, focuses = {} } = on;
  const item = inBar(["kanso-status-bar__item", "kanso-status-bar__stepper", open ? "kanso-status-bar__item--open" : "", hover ? "kanso-control--hover" : ""].filter(Boolean));
  const columnsNode = node(["kanso-status-bar__columns"], item);
  const tool = (icon, label, chord, onClick) => focused(withDisplay(button(`${id}-${icon}`, label, onClick, c,
    { kind: "icon", icon, size: "sm", tip: tipText({ label, chord }) }), item), focuses[icon]);
  // min-width: 1ch is not drawn: gpui has no ch.
  const number = button(`${id}-value`, String(value), even, c, { kind: "quiet", content: [still(div(), node(["kanso-status-bar__value"], item), c).child(String(value))],
    tip: tipText({ label: `${value} per view`, chord: chords.fit, detail: "scroll to change, click to even out" }) });
  return still(h_flex().id(id), inBar(["kanso-status-bar__item", "kanso-status-bar__stepper"]), c)
    .when(Boolean(onHover), (el) => el.on_hover((over, cx) => onHover(over, cx)))
    .when(columns.length > 0, (el) => el.child(still(h_flex().id(`${id}-columns`), columnsNode, c)
      .children(columns.map((col, i) => button(`${id}-column-${i}`, `Column ${i + 1}`, column && ((cx) => column(i, cx)), c, { kind: "bare", content: [columnFace(c, columnsNode, col)] })))))
    .child(paint(h_flex().id(`${id}-pill`), item, c, RULES).rounded(R.full)
      .child(tool("minus", "Fewer panes per view", chords.fewer, minus))
      .child(focused(number, focuses.value))
      .child(tool("plus", "More panes per view", chords.more, plus)));
};
