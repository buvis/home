// Kanso's panel kit: the key hint, a chord in mono on a thin edge, faint when unset, breathing in the accent while it records. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-key-hint.js.
import { div } from "gpui-kit";
import { G, H, R, T, breathe } from "./ui.js";

const inkOf = (c, faint, recording) => {
  if (recording) return c.accent;
  return faint ? c.dim : c.muted;
};

// `font`: the mono family the caller reads from its settings.
export const keyHint = (c, { text, faint = false, recording = false, font = null } = {}) => {
  const hint = div().flex().flex_none().items_center().h(H.compact).px(G.sm).rounded(R.sm)
    .border_1().border_color(recording ? c.accent : c.border).whitespace_nowrap()
    .text_size(T.body).text_color(inkOf(c, faint, recording))
    .when(Boolean(font), (el) => el.font_family(font))
    .child(String(text ?? ""));
  return recording ? breathe(hint) : hint;
};
