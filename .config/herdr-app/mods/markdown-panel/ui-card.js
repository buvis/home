// Kanso's panel kit: the card, a bounded group with one identity: who or what, its facts, then prose or other pieces. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-card.js.
import { div, svg } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { G, H, R, T, LH, ICON_INLINE, breathe, glyphOf, monoFont } from "./ui.js";
import { avatar } from "./ui-avatar.js";

const headerOf = (c, { author, image, age, initial, where, step }) => h_flex().w_full().min_w(0).items_center().gap(G.sm).whitespace_nowrap().text_size(T.value)
  .when(Boolean(initial), (el) => el.child(avatar(c, { initial, image })))
  .child(div().flex_none().text_size(T.card).font_medium().text_color(c.text).child(author))
  .when(Boolean(step), (el) => el.child(svg(glyphOf("chevron-right")).size(ICON_INLINE).flex_none().text_color(c.dim)).child(div().min_w(0).truncate().text_color(c.muted).child(step)))
  .when(Boolean(where), (el) => el.child(div().min_w(0).truncate().font_family(monoFont()).text_size(T.mono).text_color(c.dim).child(where)))
  .child(div().flex_1())
  .when(Boolean(age), (el) => el.child(div().flex_none().text_color(c.dim).child(age)));

const proseOf = (c, body) => div().w_full().text_size(T.value).line_height(LH.body).text_color(c.text).child(body);

/** `initial`: the avatar's letter, none when empty; `where`: a path in mono; `step`: what it was doing; `content`: drawn pieces in place of the prose `body`; `loading`: its silhouette. */
export const card = (id, c, { author = "", image = null, age = "", body = "", loading = false, initial = author, where = "", step = "", content = [] }) => (loading
  ? breathe(div().id(id).w_full().h(H.two).rounded(R.card).bg(c.border))
  : v_flex().id(id).w_full().p(G.md).gap(G.xs).rounded(R.card).bg(c.canvas)
    .when(Boolean(author), (el) => el.child(headerOf(c, { author, image, age, initial, where, step })))
    .children(content.length ? content : [proseOf(c, body)]));
