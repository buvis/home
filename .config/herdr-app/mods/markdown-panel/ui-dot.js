// Kanso's panel kit: the dot, a state's colour where a word alone would not carry it. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-dot.js.
import { div } from "gpui-kit";
import { G, toneColor } from "./ui.js";

export const DOT_SIZES = Object.freeze({ sm: G.xs, md: G.sm });

/** `tone`: a kit tone (blocked, working, done, accent...) or a #rrggbb colour; `size`: sm (pending, a list's bullet) or md. */
export const dot = (c, tone, size = "md") => div().size(DOT_SIZES[size] ?? DOT_SIZES.md).flex_none().rounded_full()
  .bg(tone.startsWith("#") ? tone : toneColor(c, tone));
