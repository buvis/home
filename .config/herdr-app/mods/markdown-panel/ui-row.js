// Kanso's panel kit: the row, one named item in a list with its facts, its mark and its tools. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-row.js.
import { div, svg, image } from "gpui-kit";
import { h_flex, v_flex, Button } from "gpui-base";
import { G, H, LH, R, T, W, ICON_ROW, ICON_INLINE, CLEAR, OPACITY, alpha, glyphOf, toneColor } from "./ui.js";
import { button } from "./ui-button.js";
import { chip } from "./ui-chip.js";
import { dot } from "./ui-dot.js";
import { glint as glinting } from "./ui-glint.js";
import { keyHint } from "./ui-key-hint.js";
import { busyMark, mark } from "./ui-mark.js";
import { PENDING, pendingDot } from "./ui-state.js";

// Each step in is the lead icon and its gap; the guide of a deeper row runs under its parent's icon.
const indent = (depth) => G.sm * (depth + 1) + ICON_ROW * depth;
const guideAt = (level) => indent(level) + ICON_ROW / 2;

const glyph = (icon, side, ink) => svg(glyphOf(icon)).size(side).flex_none().text_color(ink);
// A program's own art: tinted, or in its own colours, faded with the row when dimmed.
const leadOf = (icon, ink, dimmed) => {
  if (typeof icon === "string") return glyph(icon, ICON_ROW, ink);
  const art = icon.tint ? svg(icon.icon).size(ICON_ROW).flex_none().text_color(ink) : image(icon.icon).w(ICON_ROW).h(ICON_ROW).flex_none();
  return dimmed ? art.opacity(OPACITY.away) : art;
};
// A tool's press stays on the tool: the row under it does not run its own click.
const alone = (onClick) => onClick && ((cx) => { cx.stop_propagation(); onClick(cx); });

// A fact is a string or `{ icon, text, tone, tip }`; in the detail a tone leads with its dot.
const factOf = (part) => (typeof part === "object" ? part : { text: part });
const tipped = (el, id, tip) => (tip ? el.id(id).tooltip(tip) : el);
const textOf = (c, id, { text, tone, tip }) => tipped(div().min_w(0).truncate().when(Boolean(tone), (el) => el.text_color(toneColor(c, tone))).child(String(text)), id, tip);
// A fact with a `label` is a press: a quiet small button showing its text, its tip saying what it does.
const pressFact = (c, id, { text, tip, label, onClick }) => held(button(id, String(text), alone(onClick), c, { kind: "quiet", size: "sm", tip: tip || label }));
const fact = (c, id) => (part, i) => {
  if (typeof part === "string") return div().flex_none().child(part);
  if (part.label) return pressFact(c, `${id}-${i}`, part);
  return h_flex().flex_none().items_center().gap(G.xs)
    .when(Boolean(part.icon), (el) => el.child(glyph(part.icon, ICON_INLINE, c.dim)))
    .when(Boolean(part.tone), (el) => el.child(dot(c, part.tone)))
    .child(textOf(c, `${id}-${i}`, part));
};

const detailOf = (c, id, detail, names) => {
  const facts = [detail ?? []].flat().filter(Boolean);
  return facts.length ? h_flex().min_w(0).overflow_hidden().items_center().gap(G.sm).whitespace_nowrap().text_color(c.dim).when(names, (el) => el.text_size(T.body)).children(facts.map(fact(c, `${id}-detail`))) : null;
};

// The second line: a string, or facts in a row where the first one gives way.
// A sidebar row's facts are told apart by a dot, the way the story reads "Run npm publish? · 2m".
const secondOf = (c, id, second, names) => {
  const line = div().w_full().min_w(0).text_size(T.body).text_color(c.dim);
  if (typeof second === "string") return line.truncate().child(second);
  const parts = second.filter(Boolean).map((part, i) => textOf(c, `${id}-second-${i}`, factOf(part)).when(i > 0, (el) => el.flex_none()));
  const told = names ? parts.flatMap((part, i) => (i ? [div().flex_none().text_color(c.dim).child("\u00b7"), part] : [part])) : parts;
  return h_flex().w_full().min_w(0).items_center().gap(names ? G.xs : G.sm).whitespace_nowrap().text_size(T.body).text_color(c.dim).children(told);
};

// A file's git `letter` takes the icon's slot; modified keeps the slot empty so names align.
const LETTER_TONES = { A: "dim", D: "dim", U: "blocked" };
const letterOf = (c, letter) => div().w(ICON_ROW).flex_none().text_center().text_size(T.body)
  .when(Object.hasOwn(LETTER_TONES, letter), (el) => el.text_color(toneColor(c, LETTER_TONES[letter])))
  .child(letter === "M" ? "" : letter);
// A tree row leads with its fold: a folder's chevron, `open` or not, or an empty slot for a file.
const foldOf = (c, open) => div().w(ICON_INLINE).flex_none().flex().items_center().justify_center()
  .when(open !== null, (el) => el.child(glyph(open ? "chevron-down" : "chevron-right", ICON_INLINE, c.dim)));
const slotOf = (c, { letter, icon, tone, ink, dimmed, busy }) => {
  if (letter) return letterOf(c, letter);
  if (!icon) return null;
  return busy ? busyMark(c, ICON_ROW) : leadOf(icon, tone ? toneColor(c, tone) : ink, dimmed);
};

const chipOf = (id, c, count) => {
  const { label, tip } = typeof count === "object" ? count : { label: count };
  return tipped(chip(c, { label }), `${id}-chip`, tip);
};

// Nor does a press on it start the row's drag or double-click.
const held = (el) => el.on_mouse_down("left", (_e, cx) => cx.stop_propagation());
const tool = (id, c) => ({ label, onClick, ...rest }, i) => held(button(`${id}-tool-${i}`, label, alone(onClick), c, { kind: "icon", size: "sm", ...rest }));
const actionOf = (id, c, { label, onClick, ...rest }) => held(button(`${id}-action`, label, alone(onClick), c, { size: "sm", ...rest }));

const verb = (id, c) => ({ label, onClick, ...rest }, i) => button(`${id}-verb-${i}`, label, alone(onClick), c, { kind: "quiet", size: "sm", ...rest });
const verbsOf = (id, c, verbs) => (verbs.length ? h_flex().w_full().flex_wrap().items_center().gap(G.sm).children(verbs.map(verb(id, c))) : null);

// Over whatever is under the row: the list, a slab, the pill.
const WASHES = { blocked: (c) => alpha(c.blocked, OPACITY.blockedRow) };
const groundOf = (c, { current, hover, title, wash }) => {
  if (current) return c.selected;
  if (hover && !title) return c.subtle;
  return WASHES[wash]?.(c) ?? null;
};

// A wrapped name runs over as many lines as it needs, such as a review thread's comment.
// A group's head stands over the rows of its group: strong, in the row's ink, one step up the type scale from a heading.
// In the sidebar (`names`) every name is the name size: a head strong, a session medium, in the ink its state gives it.
const nameOf = (id, c, { name, heading, group, title, ink, glint, wrap, names }) => (glint ? glinting(name, c, id) : div().min_w(0).text_color(ink)
  .when(wrap, (el) => el.flex_1().line_height(LH.body))
  .when(!wrap, (el) => el.truncate())
  .when(heading || group || title, (el) => el.font_semibold())
  .when(names && !(heading || group || title), (el) => el.font_medium())
  .when(group || names, (el) => el.text_size(T.card))
  .when(names && (heading || group), (el) => el.flex_none().max_w(W.buttonLabel))
  .when(title, (el) => el.text_size(T.page))
  .child(name));

// Meta and flag give way to the tools while they show.
const asideOf = (id, c, { meta, flag, dimmed }) => {
  const { text, tone, tip } = meta ? factOf(meta) : {};
  const ink = tone ? toneColor(c, tone) : dimmed ? c.muted : c.dim;
  return [
    meta ? tipped(div().flex_none().whitespace_nowrap().text_size(T.body).text_color(ink).child(String(text)), `${id}-meta`, tip) : null,
    flag ? glyph(flag, ICON_ROW, c.dim) : null,
  ];
};

// A row's tool is an icon Button at H.badge holding an ICON_INLINE glyph: the last thing in the row, it reaches out by the room
// around its glyph, so the glyph ends on the row's edge as the name starts on it. A mark or a pending dot after it is on the edge itself.
const TOOL_ROOM = (H.badge - ICON_INLINE) / 2;
const controlsOf = (id, c, { actions, count, action, tools, keys, last }) => [
  actions.length ? h_flex().flex_none().items_center().gap(G.hair).my(-G.xs).when(last && !count && !action, (el) => el.mr(-TOOL_ROOM)).children(actions.map(tool(id, c))) : null,
  count ? chipOf(id, c, count) : null,
  action ? actionOf(id, c, action).when(last && action.kind === "icon", (el) => el.mr(-TOOL_ROOM)) : null,
  ...tools,
  ...keys.map((key) => keyHint(c, key)),
];

const besideOf = (lead, body) => (lead ? h_flex().w_full().min_w(0).items_center().gap(G.md).child(lead).child(body) : body);
const ringOf = (c, { selected, focus }) => (selected || focus ? c.accent : CLEAR);
const heightOf = ({ title, under, two }) => {
  if (two) return H.two;
  if (under) return null;
  return title ? H.row : H.line;
};

// An elbow leaves its guide at the middle of the first line and stops short of the row's icon.
export const ELBOW = { y: H.line / 2, w: ICON_ROW / 2 + G.xs };
const line = (c) => div().absolute().border_color(c.w12);
const GUIDES = {
  pass: (c, x) => [line(c).top_0().bottom_0().left(x).border_l_1()],
  tee: (c, x) => [line(c).top_0().bottom_0().left(x).border_l_1(), line(c).top(ELBOW.y).left(x).w(ELBOW.w).border_t_1()],
  end: (c, x) => [line(c).top_0().h(ELBOW.y).left(x).border_l_1(), line(c).top(ELBOW.y).left(x).w(ELBOW.w).border_t_1()],
};
// One guide per depth above the row, under that depth's icon: `tee`, `end`, `pass` or null; without them a deeper row has one under its parent's.
const guidesOf = (c, depth, guides) => {
  const lines = guides.length ? guides : depth > 1 ? [null, "pass"] : [];
  return lines.flatMap((kind, level) => GUIDES[kind]?.(c, guideAt(level)) ?? []);
};

const DROPS = { before: (el) => el.top_0(), after: (el) => el.bottom_0() };
const dropOf = (c, drop) => (DROPS[drop] ? DROPS[drop](div().absolute().left_0().right_0().h(G.hair).bg(c.accent)) : null);

// A tree row steps in by `level`; any other by its `depth`.
const leftOf = (level, depth) => (level === null ? indent(depth) : G.sm + G.lg * level);

// A row that acts is a Button: Tab reaches it, Enter and Space press it, a screen reader calls it a button; a handle given keeps its focus.
// One whose keys the caller reads stays plain.
const rootOf = (id, { onClick, onKey }) => (onClick && !onKey ? Button.new(id).flex() : h_flex().id(id));

const wire = (el, c, { onClick, onHover, onKey, focusHandle }) => el
  .when(Boolean(onClick), (e) => e.cursor_pointer().on_click((_e, cx) => onClick(cx)))
  .when(Boolean(onHover), (e) => e.on_hover(onHover))
  .when(Boolean(onKey), (e) => e.on_key_down(onKey))
  .when(Boolean(focusHandle), (e) => e.track_focus(focusHandle))
  .when(Boolean(onClick || focusHandle), (e) => e.focus((s) => s.border_color(c.accent)));

const INERT = Object.freeze({
  selected: false, hover: false, focus: false, actions: Object.freeze([]), action: null, verbs: Object.freeze([]), start: Object.freeze([]), tools: Object.freeze([]),
  onClick: null, onHover: null, onKey: null, focusHandle: null,
});
const withoutPress = (detail) => [detail ?? []].flat().filter(Boolean).map((part) => (typeof part === "object" ? { ...part, label: null, onClick: null } : part));

// `start`, `tools`: drawn elements before the icon and always at the end; `actions`: tools shown with `hover` or `focus`; `keys`: key hint props.
// `level` makes it a tree row, `open` its folder's fold; `verbs`: quiet word actions on a line under it.
// `group`: a heading that heads a group, such as a computer over its projects; `wrap`: the name wraps instead of one truncated line; `drop`: where a dragged row lands; `wash`: a state's ground; `guides`: one per level.
export function row(id, c, {
  icon = null, tone = null, letter = null, level = null, open = null, name, detail: told = null, meta = null, chip: count = null, flag = null, mark: status = "none", second = null, heading = false, group = false, title = false,
  depth = 0, selected: picked = false, current = false, dimmed = false, busy = false, pending = false, hover: hovering = false, focus: focusing = false, actions: offered = [], action: offer = null, verbs: said = [], start: leading = [], tools: own = [], keys = [],
  glint = false, wrap = false, drop = null, wash = null, guides = [], names = false, nameInk = null, lead = null,
  onClick: pressed = null, onHover: hovered = null, onKey: keyed = null, focusHandle: kept = null,
} = {}) {
  const { selected, hover, focus, actions, action, verbs, start, tools, detail, onClick, onHover, onKey, focusHandle } = busy ? { ...INERT, detail: withoutPress(told) }
    : { selected: picked, hover: hovering, focus: focusing, actions: offered, action: offer, verbs: said, start: leading, tools: own, detail: told, onClick: pressed, onHover: hovered, onKey: keyed, focusHandle: kept };
  const ink = dimmed ? c.muted : c.text;
  const nameColour = names && nameInk ? { fg: c.text, muted: c.muted, dim: c.dim }[nameInk] : ink;
  const shown = hover || focus;
  const ground = groundOf(c, { current, hover, title, wash });
  const under = Boolean(second) || verbs.length > 0 || wrap;
  const two = Boolean(second) && !title && !verbs.length && !wrap;
  const height = heightOf({ title, under, two });
  const marked = mark(c, { status });
  const first = h_flex().w_full().min_w(0).items_center().gap(G.sm).when(wrap, (el) => el.items_start()).when(Boolean(second && title), (el) => el.h(H.row)).children([
    ...start,
    level === null ? null : foldOf(c, open),
    slotOf(c, { letter, icon, tone, ink: names ? c.muted : ink, dimmed, busy }),
    nameOf(`${id}-name`, c, { name, heading, group, title, ink: nameColour, glint, wrap, names }),
    detailOf(c, id, detail, names),
    div().flex_1(),
    ...(shown && actions.length ? [] : asideOf(id, c, { meta, flag, dimmed })),
    ...controlsOf(id, c, { actions: shown ? actions : [], count, action, tools, keys, last: !tools.length && !keys.length && !pending && !marked }),
    pending ? pendingDot(`${id}-pending`, c) : null,
    marked,
  ].filter(Boolean));
  // The ring is a border kept clear at rest, so a focus or a pick never moves the content.
  return wire(rootOf(id, { onClick, onKey }).relative().min_w(0).mx(-G.sm).items_center().rounded(R.control)
    .border_2().border_color(ringOf(c, { selected, focus }))
    .pl(leftOf(level, depth) - G.hair).pr(G.sm - G.hair).text_size(names ? T.card : T.value).text_color(ink)
    .when(under && !two && !title, (el) => el.py(G.sm - G.hair))
    .when(Boolean(height), (el) => el.h(height))
    .when(Boolean(ground), (el) => el.bg(ground))
    .when(!title && !busy, (el) => el.hover((s) => s.bg(current ? c.selected : c.subtle)).active((s) => s.bg(c.selected)))
    .when(pending, (el) => el.opacity(PENDING))
    .children([...guidesOf(c, depth, guides), dropOf(c, drop)].filter(Boolean))
    .child(besideOf(lead, under ? v_flex().w_full().min_w(0).gap(two && !names ? G.xs : G.sm).child(first)
      .children([second ? secondOf(c, id, second, names) : null, verbsOf(id, c, verbs)].filter(Boolean)) : first)), c, { onClick, onHover, onKey, focusHandle });
}
