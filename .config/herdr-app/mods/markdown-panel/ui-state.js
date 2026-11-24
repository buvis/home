// Kanso's panel kit: empty, failure, pending and undo, each drawn one way everywhere. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-state.js.
import { div, svg } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { G, H, R, T, ICON_ROW, ICON_EMPTY, OPACITY, breathe, glyphOf, monoFont } from "./ui.js";
import { button } from "./ui-button.js";
import { dot } from "./ui-dot.js";
import { mark } from "./ui-mark.js";

/** A reversible action, done: what happened, and Undo at the end of its line. */
export const undoLine = (id, text, onUndo, c) => h_flex().id(id).min_w(0).items_center().gap(G.md)
  .child(div().min_w(0).truncate().text_size(T.body).font_medium().text_color(c.text).child(text))
  .child(button(`${id}-undo`, "Undo", onUndo, c, { kind: "tonal", small: true }));

/** Empty: the view's icon, one sentence and at most one tonal action, centred where the list would be; `onClick` presses the action. */
export const stateEmpty = (id, c, { icon = "", text, action = "", onClick = null }) => v_flex().id(id).w_full().items_center().gap(G.sm).px(G.lg).py(G.xl)
  .when(Boolean(icon), (el) => el.child(svg(glyphOf(icon)).size(ICON_EMPTY).flex_none().text_color(c.dim)))
  .child(div().w_full().text_center().text_size(T.value).text_color(c.muted).child(text))
  .when(Boolean(action), (el) => el.child(button(`${id}-action`, action, onClick, c, { kind: "tonal" })));

// The block's own sizes: its edge (border_1), its leading, and the source's words at most two lines.
const EDGE = 1;
const LEADING = 1.5;
const EVIDENCE_PX = T.mono * LEADING * 2;

/** The tallest a `stateBlock` with these parts draws when our words wrap to `lines`: a fixed-size home makes room with it. */
export const stateBlockPx = ({ source = "", fix = "" } = {}, lines = 1) => 2 * (EDGE + G.md) + T.card * LEADING * lines
  + (source ? G.xs + EVIDENCE_PX : 0) + (fix ? 2 * G.xs + H.control : 0);

/** Failure, block: a blocked edge; the mark and our words, the source's words in mono at most two lines, then the one solid fix. */
export function stateBlock(id, c, { text, source = "", fix = "", onClick = null, agent = "", onExplain = null, lit = null }) {
  return v_flex().id(id).w_full().p(G.md).gap(G.xs).rounded(R.card).border_1().border_color(c.blocked)
    .child(h_flex().w_full().min_w(0).items_center().gap(G.sm).child(mark(c, { status: "blocked" }))
      .child(div().flex_1().min_w(0).text_size(T.card).line_height(LEADING).font_medium().text_color(c.text).child(text)))
    .when(Boolean(source), (el) => el.child(h_flex().w_full().pl(ICON_ROW + G.sm)
      .child(div().w_full().max_h(EVIDENCE_PX).overflow_hidden().font_family(monoFont()).text_size(T.mono).line_height(LEADING).text_color(c.muted).tooltip(source).child(source))))
    .when(Boolean(fix || agent), (el) => el.child(h_flex().w_full().pl(ICON_ROW + G.sm).pt(G.xs).gap(G.sm)
      .when(Boolean(fix), (row) => row.child(button(`${id}-fix`, fix, onClick, c, { kind: "solid", focus: lit === "fix" }).flex_1()))
      .when(Boolean(agent), (row) => row.child(button(`${id}-explain`, `Explain to ${agent}`, onExplain, c, { kind: "tonal", icon: "bot", focus: lit === "agent" })))));
}

/** Failure on a line (status bar, pane header, toast): the mark, our words, the one fix as a small quiet button; `detail` is the tooltip. */
export const stateLine = (id, c, { text, fix = "", detail = "", onClick = null }) => h_flex().id(id).min_w(0).items_center().gap(G.sm)
  .when(Boolean(detail), (el) => el.tooltip(detail))
  .child(mark(c, { status: "blocked" }))
  .child(div().min_w(0).truncate().text_size(T.value).font_medium().text_color(c.text).child(text))
  .when(Boolean(fix), (el) => el.child(button(`${id}-fix`, fix, onClick, c, { kind: "quiet", small: true })));

/** Pending: the new state drawn at once at this opacity, with `pendingDot` breathing beside it until the write is confirmed. */
export const PENDING = OPACITY.pending;
export const pendingDot = (id, c) => breathe(dot(c, "muted", "sm").id(id));
