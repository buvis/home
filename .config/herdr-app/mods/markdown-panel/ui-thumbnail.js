// Kanso's panel kit: the thumbnail, one small picture to pick in a strip. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-thumbnail.js.
import { div, image } from "gpui-kit";
import { G, H, R, breathe } from "./ui.js";
import { button } from "./ui-button.js";

/** A square with its edge on the raised ground, the picture inside it; `selected` takes the accent ring, `loading` breathes as its own silhouette.
 * `color` (Proposed): the picture's own colour, its ground until the picture is drawn. A quiet kit button: Tab reaches it, Enter and Space pick it, and its name is its tooltip. */
export const thumbnail = (id, c, { image: picture = "", label, selected = false, loading = false, color = "" }, onClick = null) => {
  const square = div().size(H.row).flex_none().rounded(R.sm).overflow_hidden();
  const face = loading ? breathe(square.bg(c.border))
    : square.p(G.hair).bg(color || c.raised).border_1().border_color(c.border)
      .when(Boolean(picture), (el) => el.child(image(picture).size_full().rounded(R.sm)));
  return button(id, label, onClick, c, { kind: "quiet", content: [face], focus: selected, tip: label });
};
