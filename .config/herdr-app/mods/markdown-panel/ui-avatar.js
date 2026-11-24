// Kanso's panel kit: the avatar, a round initial on a wash with a picture over it when there is one. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-avatar.js.
import { div, image } from "gpui-kit";
import { G, H, R, T, toneColor } from "./ui.js";

export const AVATAR_SIZES = Object.freeze({
  sm: Object.freeze({ side: G.lg, text: T.body }),
  md: Object.freeze({ side: H.badge, text: T.body }),
  lg: Object.freeze({ side: H.line, text: T.card }),
});

// A round avatar on the stronger wash; a tile square-cornered on the lighter one.
const ROUND = Object.freeze({ corner: (el) => el.rounded_full(), wash: "w12" });
const TILE = Object.freeze({ corner: (el) => el.rounded(R.sm), wash: "w7" });
const drawn = (c, { initial, image: src = null, size = "md", tone = null }, { corner, wash }) => {
  const { side, text } = AVATAR_SIZES[size] ?? AVATAR_SIZES.md;
  return corner(div().relative().size(side).flex_none().overflow_hidden().bg(c[wash]))
    .flex().items_center().justify_center().text_size(text).text_color(tone ? toneColor(c, tone) : c.muted)
    .child(String(initial ?? "").charAt(0))
    .when(Boolean(src), (el) => el.child(corner(image(src).absolute().inset_0().size_full())));
};

/** `initial`: its first letter is drawn; `image`: a picture over it; `size`: sm, md or lg; `tone`: a host's hue for the letter. */
export const avatar = (c, { initial, image = null, size = "md", tone = null } = {}) => drawn(c, { initial, image, size, tone }, ROUND);

/** The avatar as a tile: an app's picture or its letter. */
export const tile = (c, { initial, image = null, size = "md", tone = null } = {}) => drawn(c, { initial, image, size, tone }, TILE);
