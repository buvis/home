// Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-glint.js.
import { div } from "gpui-kit";
import { h_flex } from "gpui-base";
import { GLINT, GLINT_MS, GLINT_STAGGER, GLINT_EASE, OPACITY, onBattery } from "./ui.js";

// Seven paces, so names side by side do not glint in step.
const PACES = 7;
const WINDOWS = [[GLINT.wide, OPACITY.glintFaint], [GLINT.mid, OPACITY.glintMid], [GLINT.narrow, 1]];
const paceOf = (seed) => GLINT_MS + ([...seed].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % PACES) * GLINT_STAGGER;

// Each window slides one way while its copy of the text slides the other, so the lit letters stay in place.
const lit = (text, c, period) => ([width, strength]) => div().absolute().top_0().bottom_0().w(width).overflow_hidden().opacity(strength)
  .loop("left", { from: -width, to: GLINT.run, period, easing: GLINT_EASE })
  .child(div().absolute().top_0().whitespace_nowrap().text_color(c.text).child(text)
    .loop("left", { from: width, to: -GLINT.run, period, easing: GLINT_EASE }));

const still = (text, c) => div().min_w(0).flex_shrink_1().truncate().text_color(c.text).child(text);
const moving = (text, c, seed) => div().relative().min_w(0).flex_shrink_1().overflow_hidden()
  .child(div().truncate().text_color(c.muted).child(text))
  .children(WINDOWS.map(lit(text, c, paceOf(seed))));

export const glint = (text, c, seed = "") => h_flex().min_w(0).items_center()
  .child(onBattery() ? still(text, c) : moving(text, c, seed));
