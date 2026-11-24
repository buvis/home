// Kanso's panel kit: the toast, a notice on the popover ground with its lead, its words and its buttons. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-toast.js.
import { div, image, svg } from "gpui-kit";
import { h_flex, v_flex, Button } from "gpui-base";
import { G, T, ICON_ROW, CLEAR, glyphOf, toneColor } from "./ui.js";
import { mark as drawMark } from "./ui-mark.js";
import { dot } from "./ui-dot.js";
import { button, withLook } from "./ui-button.js";

export const LEVELS = Object.freeze({ error: "blocked", warning: "working", success: "done", info: "accent" });
const KIT_NAME = /^[a-z0-9-]+$/;

const glyph = (c, icon, tone) => (KIT_NAME.test(icon) ? svg(glyphOf(icon)).text_color(toneColor(c, tone)) : image(icon)).size(ICON_ROW).flex_none();
const centered = (el) => h_flex().size(ICON_ROW).flex_none().items_center().justify_center().child(el);
const line = (size, ink, words) => div().truncate().text_size(size).text_color(ink).child(words);

const leadOf = (c, level) => {
  if (level === "error") return drawMark(c, { status: LEVELS.error });
  if (level === "success") return glyph(c, "check", LEVELS.success);
  return centered(dot(c, LEVELS[level] ?? LEVELS.info));
};
const headOf = (c, { level, icon, status, tone }) => {
  if (status) return drawMark(c, { status });
  return icon ? glyph(c, icon, tone ?? LEVELS[level] ?? LEVELS.info) : leadOf(c, level);
};

// `icon` is a kit name or Herdr's picture; a press on the toast or its buttons runs `onClick`.
export function toast(id, c, { level = "info", icon = null, title = "", body = null, action = null, explain = null, mark = null, tone = null, detail = null, onClick = null } = {}) {
  const press = (cx) => { cx.stop_propagation(); onClick?.(cx); };
  const small = (key, label, glyphName = null) => button(`${id}-${key}`, label, press, c, { kind: "tonal", small: true, icon: glyphName });
  const root = Button.new(id).flex().size_full().pl(G.md).pr(G.sm).gap(G.sm).items_center()
    .border_2().border_color(CLEAR).focus((s) => s.border_color(c.accent));
  return withLook(root, { fill: c.popover, hover: c.subtle, press: c.selected })
    .when(Boolean(body), (el) => el.py(G.sm))
    .when(Boolean(detail), (el) => el.tooltip(detail))
    .when(Boolean(onClick), (el) => el.on_click((_e, cx) => onClick(cx)))
    .child(headOf(c, { level, icon, status: mark, tone }))
    .child(v_flex().flex_1().min_w(0).child(line(T.value, c.text, title)).when(Boolean(body), (el) => el.child(line(T.body, c.muted, body))))
    .when(Boolean(action), (el) => el.child(small("fix", action)))
    .when(Boolean(explain), (el) => el.child(small("explain", `Explain to ${explain}`, "bot")));
}
