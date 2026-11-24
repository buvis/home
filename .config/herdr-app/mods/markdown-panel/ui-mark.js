// Kanso's panel kit: an agent's state mark, the ensō as working, blocked, done, idle, asleep or limited. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-mark.js.
import { div, svg } from "gpui-kit";
import { ICON, ICON_ROW, ICON_INLINE, SPIN, OPACITY, glyphOf } from "./ui.js";

export const MARK_SIZES = Object.freeze({ sm: ICON_INLINE, md: ICON_ROW, lg: ICON });
// The blocked dot's "!" as a share of the dot.
const BANG = 0.68;

const art = (name, color, side) => svg(glyphOf(name)).size(side).flex_none().text_color(color);
const dot = (color, ink, side) => div().size(side).flex_none().rounded_full().bg(color)
  .text_size(Math.round(side * BANG)).font_bold().text_color(ink).flex().items_center().justify_center().child("!");

const MARKS = Object.freeze({
  working: (c, side) => art("working", c.working, side).spin(SPIN),
  blocked: (c, side) => dot(c.blocked, c.chrome, side),
  done: (c, side) => art("enso", c.done, side),
  idle: (c, side) => art("enso-idle", c.idle, side).opacity(OPACITY.idle),
  asleep: (c, side) => art("moon", c.muted, side),
  limited: (c, side) => art("clock", c.muted, side),
});

export const busyMark = (c, side) => MARKS.working(c, side);

/** `status`: working, blocked, done, idle, asleep or limited; any other draws nothing. `size`: sm, md or lg. */
export const mark = (c, { status, size = "md" } = {}) => (Object.hasOwn(MARKS, status) ? MARKS[status](c, MARK_SIZES[size] ?? MARK_SIZES.md) : null);
