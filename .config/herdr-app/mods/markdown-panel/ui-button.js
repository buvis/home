// Kanso's panel kit: the button, its quiet link and icon forms, and the press that asks twice. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-button.js.
import { div, svg } from "gpui-kit";
import { v_flex, Button } from "gpui-base";
import { busyMark } from "./ui-mark.js";
import { G, H, R, T, W, ICON, ICON_ROW, ICON_INLINE, ICON_CHROME, ARM_MS, WASH, CLEAR, EASE, glyphOf, mix, well } from "./ui.js";

const filled = (fill, ink, c) => ({ fill, ink, hover: mix(fill, c.background, WASH.hover), press: mix(fill, c.background, WASH.press) });
/** A look on a pressable element: its fill, then its hover and press washes; a look with neither hover nor `pointer` is not pressable. */
export const withLook = (el, look) => el.when(Boolean(look.fill), (e) => e.bg(look.fill))
  .when(Boolean(look.hover) || Boolean(look.pointer), (e) => e.cursor_pointer())
  .when(Boolean(look.hover), (e) => e.hover((s) => s.bg(look.hover)).active((s) => s.bg(look.press)));

/** The armed look: the accent fill, its hover and press washes, the accent foreground. */
export const armedLook = (c) => filled(c.accent, c.accentText, c);
const LOOKS = {
  solid: (c) => filled(c.primary, c.primaryText, c),
  tonal: (c) => ({ fill: c.subtle, ink: c.text, hover: c.selected, press: c.selected }),
  quiet: (c) => ({ fill: null, ink: c.muted, hover: c.subtle, press: c.selected }),
  icon: (c) => ({ fill: null, ink: c.muted, hover: c.subtle, press: c.selected }),
  bare: (c) => ({ fill: null, ink: c.muted, hover: null, press: null, pointer: true }),
};

/** An icon button's square and glyph: sm is a row's tool, compact sits in a field, lg is the window chrome's tool, md everywhere else. */
const SQUARES = Object.freeze({
  sm: Object.freeze({ side: H.badge, glyph: ICON_INLINE }),
  compact: Object.freeze({ side: H.compact, glyph: ICON }),
  md: Object.freeze({ side: H.icon, glyph: ICON }),
  lg: Object.freeze({ side: H.line, glyph: ICON_CHROME }),
});

export const pressAgain = (verb) => `Press again to ${verb}`;

/** Both labels in one cell, the hidden one at no height: the box is the wider of the two at rest, so arming moves nothing. */
export function armedLabel(label, verb, on, text, { start = false } = {}) {
  const hidden = (el, hide) => (hide ? el.h(0).overflow_hidden() : el);
  return v_flex().when(start, (el) => el.items_start()).when(!start, (el) => el.items_center())
    .child(hidden(text(label).whitespace_nowrap(), on)).child(hidden(text(pressAgain(verb)).whitespace_nowrap(), !on));
}

/** solid: the one primary action; tonal: a wash, no edge; quiet: text only; bare: its content alone, with no wash under the pointer or the press; icon: `label` is its tip. `icon`: a name in kanso-chrome's icons, or a path.
 * `tip`: the tooltip, when it says more than the label; `focus`: the keyboard's ring is on it. `size`: "sm" draws the small form, an icon button at the row's 20 with a 12 glyph; "lg" an icon button at 32 with a 17 glyph. `verb`: the action asks twice; `armed` fills it with the accent and reads "Press again to <verb>".
 * `content`: drawn elements shown in place of the icon and label, such as a picture with its name; the button takes their size, and `label` is what it says.
 * `truncate`: a long label is cut at W.buttonLabel, such as a menu's chosen project, so the button never grows past it. */
export function button(id, label, onClick, c, { kind = "solid", icon = null, small = false, size = null, disabled = false, spoken = label, verb = null, armed = false, active = false, spin = false, color = null, tip = null, focus = false, held = false, content = [], truncate = false, flush = false, name = "", reveal = null } = {}) {
  const square = kind === "icon", on = armed && !disabled;
  const look = disabled ? { fill: kind === "quiet" ? null : well(c), ink: c.dim }
    : on ? armedLook(c)
      : active ? { ...LOOKS[kind](c), fill: c.w12, ink: c.text, hover: c.w12, press: c.w12 }
      : held ? { ...LOOKS[kind](c), fill: c.selected, hover: c.selected }
        : LOOKS[kind](c);
  const ink = disabled || on ? look.ink : color ?? (spin ? c.text : look.ink);
  const compact = small || size === "sm";
  const box = SQUARES[size] ?? (small ? SQUARES.compact : SQUARES.md);
  const line = compact ? H.compact : H.control;
  const inset = compact ? G.sm : G.md;
  const side = square ? box.side : line;
  const text = (words) => div().text_size(compact ? T.body : T.value).font_medium().text_color(ink).when(truncate, (el) => el.max_w(W.buttonLabel).truncate()).child(words);
  const glyphSide = square ? box.glyph : ICON_ROW;
  const glyph = icon ? (spin ? busyMark(c, glyphSide) : svg(glyphOf(icon)).size(glyphSide).flex_none().text_color(ink)) : null;
  const face = [content].flat().filter(Boolean), drawn = face.length > 0;
  // The ring is a border kept clear at rest, so focusing never resizes the box.
  const key = name ? `${id}-${name}` : id;
  const frame = Button.new(key).when(square || !drawn, (el) => el.h(side)).flex_none().items_center().justify_center().gap(G.sm).rounded(R.control)
    .border_2().border_color(focus ? c.accent : CLEAR).focus((s) => s.border_color(c.accent))
    .disabled(disabled)
    .accessibility_label(on && verb ? pressAgain(verb) : spoken)
    .when(square, (el) => (reveal ? el.min_w(side).px(G.xs).gap(0) : el.w(side)).tooltip(tip ?? spoken))
    .when(!square && Boolean(tip), (el) => el.tooltip(tip))
    .when(!square && !drawn, (el) => el.px(inset - G.hair).when(flush, (e) => e.ml(-inset)));
  const pressed = withLook(frame, look).when(!disabled && Boolean(onClick), (el) => el.on_click((_e, cx) => onClick(cx)));
  if (drawn) return pressed.children(face);
  return pressed
    .when(Boolean(glyph), (el) => el.child(glyph))
    .when(square && Boolean(reveal), (el) => el.child(div().id(`${key}-reveal`).h_full().flex().items_center().overflow_hidden().flex_none()
      .w(reveal.shown ? reveal.width : 0).opacity(reveal.shown ? 1 : 0).transition("width", EASE).transition("opacity", EASE)
      .child(text(label).pl(G.xs).whitespace_nowrap())))
    .when(!square, (el) => el.child(verb ? armedLabel(label, verb, on, text, { start: kind === "quiet" }) : text(label)));
}

/** A quiet action on a line. */
export const quietLink = (id, label, onClick, c, { label: spoken = label, ...o } = {}) => button(id, label, onClick, c, { color: c.muted, ...o, spoken, kind: "quiet", small: true });

export const iconButton = (id, icon, tip, onClick, c, o = {}) => button(id, tip, onClick, c, { ...o, kind: "icon", icon });

/** What a view has armed: one `key` at a time, for ARM_MS. */
export class Armed {
  constructor() { this.key = null; this.at = 0; }

  is(key) { return this.key === key && Date.now() - this.at <= ARM_MS; }

  clear() { this.key = null; }

  press(key, cx, act) {
    if (this.is(key)) { this.key = null; act(cx); return; }
    this.key = key; this.at = Date.now(); cx.notify();
    cx.timer?.after(ARM_MS + 50, (cx) => { if (this.key === key && !this.is(key)) { this.key = null; cx.notify(); } });
  }

  /** A button that asks twice: the first press arms `key`, the second runs `act`. */
  button(id, label, verb, key, act, c, o = {}) { return button(id, label, (cx) => this.press(key, cx, act), c, { ...o, verb, armed: this.is(key) }); }

  link(id, label, verb, key, act, c, o = {}) { return quietLink(id, label, (cx) => this.press(key, cx, act), c, { ...o, verb, armed: this.is(key) }); }

  /** A row's verb that asks twice, as props. */
  verb(label, verb, key, act, o = {}) { return { ...o, label, verb, armed: this.is(key), onClick: (cx) => this.press(key, cx, act) }; }
}
