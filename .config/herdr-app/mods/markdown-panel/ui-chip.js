// Kanso's panel kit: the chip, a count or a short fact on a wash, or quiet as plain dim text. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-chip.js.
import { div } from "gpui-kit";
import { G, H, R, T, toneColor } from "./ui.js";

const filled = (el, c) => el.h(H.compact).px(G.sm).rounded(R.control).bg(c.w7);
const inkOf = (c, quiet, tone) => {
  if (tone) return toneColor(c, tone);
  return quiet ? c.dim : c.text;
};

// The pill says Dawn Mode: always the night of the sky with light words, in dark and light.
const pilled = (el, c) => el.h(H.badge).px(G.sm).rounded_full().bg(c.dawn.top).text_color(c.dawn.star).font_medium();

/** `label`: a count or a few words; `quiet`: no wash, dim text; `pill`: Dawn Mode's pill; `tone`: a tone name that colours the text. */
export const chip = (c, { label, quiet = false, pill = false, tone = null } = {}) => div().flex().flex_none().items_center().whitespace_nowrap()
  .text_size(T.body).text_color(inkOf(c, quiet, tone))
  .when(!quiet && !pill, (el) => filled(el, c))
  .when(pill, (el) => pilled(el, c))
  .child(String(label));
