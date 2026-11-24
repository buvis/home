// Kanso's panel kit: the skeleton a view draws while it loads. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-skeleton.js.
import { div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { G, H, R, W, SIDEBAR, SKELETON, ICON_ROW, breathe } from "./ui.js";
import { RULES } from "./ui-css.js";
import { box } from "./ui-draw.js";

// Widths in G.xs, as the Storybook's: the lines take theirs in turn.
const LINES = [30, 24, 35, 21, 27.5, 18];
const SPAN = { title: 22, detail: 18, value: 45, stat: 12, tile: 7, picture: 84, pictureH: 52.5, device: 50, deviceH: 105 };
const STATS = 3;
const ONCE = ["header", "picture", "metric", "device"];

const bar = (c, w, h = SKELETON.text, radius = R.sm) => div().w(w).h(h).flex_none().rounded(radius).bg(c.border);
const span = (c, name, h, radius) => bar(c, SPAN[name] * G.xs, h, radius);
const line = (c, i, h) => bar(c, LINES[i % LINES.length] * G.xs, h);
const row = () => h_flex().w_full().h(H.line).flex_none().items_center().gap(G.sm);
const grow = () => div().flex_1();
const meta = (c) => bar(c, H.row, SKELETON.meta);

const SHAPES = {
  row: (c, i) => row().child(bar(c, ICON_ROW, ICON_ROW)).child(line(c, i)),
  "list row": (c, i) => row().child(line(c, i)).child(grow()).child(meta(c)),
  header: (c) => row().child(span(c, "title", ICON_ROW)).child(grow()).child(bar(c, H.icon, H.icon, R.control)),
  line: (c, i) => row().child(line(c, i)),
  "two lines": (c, i) => v_flex().w_full().flex_none().py(G.sm).gap(G.sm)
    .child(h_flex().items_center().gap(G.sm).child(line(c, i, SKELETON.meta)).child(grow()).child(meta(c)))
    .child(span(c, "detail")),
  picture: (c) => span(c, "picture", SPAN.pictureH * G.xs, R.card).w_full().max_w(SPAN.picture * G.xs),
  metric: (c) => v_flex().gap(G.md).child(span(c, "value", H.row, R.control)).child(line(c, 0))
    .child(h_flex().pt(G.sm).gap(G.xl).children(Array.from({ length: STATS }, () => span(c, "stat", H.badge, R.control)))),
  tile: (c) => h_flex().w_full().h(SIDEBAR.railRow).flex_none().justify_center().items_center().child(span(c, "tile", H.line, R.control)),
  device: (c) => h_flex().w_full().justify_center().child(span(c, "device", SPAN.deviceH * G.xs, R.card)),
};

/** A view's loading skeleton, breathing: `count` of one shape; a header, a picture, a metric and a device are drawn once. */
export const skeletonOf = (id, c, { shape, count = 1 }) => breathe(v_flex().id(id).w_full())
  .children(Array.from({ length: ONCE.includes(shape) ? 1 : count }, (_, i) => SHAPES[shape](c, i)));

const barSkeletons = (count) => {
  const bar = { tag: "div", attrs: {}, classes: ["kanso-tab-bar"], parent: null, get children() { return kids; } };
  const kids = Array.from({ length: count }, () => ({ tag: "span", attrs: {}, classes: ["kanso-skeleton", "kanso-skeleton--breathing", "kanso-tab-bar__skeleton"], parent: bar, children: [] }));
  return kids;
};
/** One breathing tab while a tab bar waits for its computer: the first long, every later one short. */
export const tabSkeleton = (id, c, index) => {
  const skeletons = barSkeletons(Math.min(index, 1) + 1);
  return breathe(box(skeletons[skeletons.length - 1], c, RULES, id));
};
