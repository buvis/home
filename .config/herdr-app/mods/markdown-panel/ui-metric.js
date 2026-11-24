// Kanso's panel kit: the one number with its unit, and its facts on a quiet line under it. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-metric.js. The app calls it through kit.js `metric`.
import { div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { G, R, T, CLEAR, toneColor } from "./ui.js";

/** The value in the display size and its unit beside it, on one baseline; `facts`, separated by |, on a quiet line under them.
 * `loading` keeps each piece's size as a skeleton shape. App only: `tone` colours the value, `tip` is its tooltip. */
export function figure(id, c, { value, unit = "", facts = "", loading = false, tone = "", tip = "" }) {
  // A piece in its size and ink; loading, the same size as a shape, its words clear.
  const piece = (size, ink, words) => div().text_size(size).text_color(loading ? CLEAR : ink).when(loading, (el) => el.rounded(R.sm).bg(c.border)).child(words);
  const list = String(facts ?? "").split("|").map((fact) => fact.trim()).filter(Boolean);
  return v_flex().id(id).min_w(0).gap(G.sm)
    .child(h_flex().flex_wrap().items_baseline().gap_x(G.sm)
      .child(piece(T.display, tone ? toneColor(c, tone) : c.text, String(value ?? "–")).line_height(1).when(Boolean(tip), (el) => el.tooltip(tip)))
      .when(Boolean(unit), (el) => el.child(piece(T.body, c.dim, unit))))
    .when(list.length > 0, (el) => el.child(h_flex().w_full().flex_wrap().gap_x(G.sm).gap_y(G.xs)
      .children(list.map((fact) => piece(T.value, c.muted, fact)))));
}
