// Kanso's panel kit: markdown, prose in blocks with headings, lists, tables and code; Herdr's TextView draws each block's words. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-markdown.js.
import { h_flex, v_flex, TextView } from "gpui-base";
import { G, R, T, LH } from "./ui.js";
import { markdownBlocks } from "./pure.js";
import { iconButton } from "./ui-button.js";

// A block's ground: none at rest, the pointer's wash, or the raised field with the accent ring while it is edited.
const GROUNDS = {
  rest: (el) => el.py(G.hair),
  hover: (el, c) => el.py(G.hair).bg(c.subtle),
  editing: (el, c) => el.py(G.xs).bg(c.raised).border_2().border_color(c.accent),
};

/** A block's words: `source` drawn as markdown, with no padding of their own. `onLink` takes a link's press. */
export const markdownWords = (id, c, { source = "" }, handlers = {}) => {
  const words = TextView.markdown(`${id}-words`, source);
  return handlers.onLink ? words.on_link_click(handlers.onLink) : words;
};

/** One block: `state` rest, hover or editing; `content`, drawn elements in place of its formatted `source` (the editor's field, a picture and its words).
 * `onPress` (a press on the block, as `on_mouse_down`) gives it the pointer's wash; its words stay selectable. `onLink` takes a link's press. */
export const markdownBlock = (id, c, { source = "", state = "rest", content = [] }, handlers = {}) => {
  const { onLink = null, onPress = null, onOpen = null } = handlers, ground = GROUNDS[state] ?? GROUNDS.rest;
  const words = content.length ? content : [markdownWords(id, c, { source }, { onLink })];
  const block = ground(v_flex().id(id).w_full().gap(G.sm).px(G.sm).rounded(R.control).text_size(T.card).line_height(LH.body).text_color(c.text), c)
    .when(Boolean(onPress) && state === "rest", (el) => el.hover((s) => s.bg(c.subtle)).on_mouse_down("left", onPress));
  if (!onOpen || state !== "rest") return block.children(words);
  return block.child(h_flex().w_full().items_start().gap(G.sm)
    .child(v_flex().flex_1().min_w(0).gap(G.sm).children(words))
    .child(iconButton(`${id}-edit`, "pencil", "Edit block", onOpen, c, { size: "sm" })));
};

/** A document: `source` in its blocks, split as the Storybook splits them; the `block`th (from 1) is drawn in `state`. */
export const markdown = (id, c, { source, block = 0, state = "rest" }, handlers = {}) => v_flex().id(id).w_full().gap(G.xs)
  .children(markdownBlocks(source).map((one, i) => markdownBlock(`${id}-${i}`, c, { source: one, state: i + 1 === block ? state : "rest" }, handlers)));
