// Small pieces the walkthrough draws with.

import { div, PathBuilder, Background } from "gpui-kit";
import { h_flex, v_flex, v_virtual_list, Scrollbar } from "gpui-base";

/**
 * kind: "solid" (the main action), "outline", "ghost" or "soft" (an accent tint:
 * a secondary action that still stands out). A disabled button is dim and ignores clicks.
 */
export function button(t, id, label, onClick, { kind = "outline", disabled = false, small = false, tooltip = null } = {}) {
  const solid = kind === "solid", soft = kind === "soft";
  const el = h_flex().id(id).flex_none().h(small ? 26 : 32).px(small ? 10 : 14).gap(6).items_center().justify_center()
    .rounded(small ? 7 : 8).text_size(small ? 12 : 12.5).font_medium()
    .when(kind === "outline", (e) => e.border_1().border_color(t.border).bg(t.surface ?? t.raised))
    .when(solid && !disabled, (e) => e.bg(t.solid).text_color(t.solid_foreground).shadow_xs())
    .when(solid && disabled, (e) => e.bg(t.raised).text_color(t.dim))
    .when(soft, (e) => e.bg(disabled ? t.raised : t.accent + "1f").text_color(disabled ? t.dim : t.accent))
    .when(!solid && !soft, (e) => e.text_color(disabled ? t.dim : t.foreground))
    .when(!disabled, (e) => e.cursor_pointer().hover((s) => (solid ? s.opacity(0.88) : soft ? s.bg(t.accent + "33") : s.bg(t.hover))))
    .when(disabled, (e) => e.cursor_not_allowed())
    .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
    .on_click((e, cx) => { if (!disabled) onClick(e, cx); })
    .child(label);
  return tooltip ? el.tooltip(tooltip) : el;
}

const RECT = () => PathBuilder.fill().move_to("0%", "0%").line_to("100%", "0%").line_to("100%", "100%").line_to("0%", "100%").close().build();

/** A layer that fills its parent (make it relative, and overflow_hidden for rounded corners) with a gradient. */
export const gradient = (from, to, angle = 135) =>
  window.paint_path(RECT(), Background.linear_gradient(angle, from, to)).absolute().top(0).left(0).size_full();

/** The mod's mark: three lines of text, the middle one shorter, on a blue-to-magenta tile. */
export const logo = (t, size = 22) => {
  const bar = (w) => div().h(Math.max(2, Math.round(size / 11))).w(Math.round(size * w)).rounded_full().bg("#ffffff");
  return div().relative().flex_none().size(size).rounded(Math.round(size * 0.3)).overflow_hidden()
    .child(gradient(t.ansi4 ?? t.accent, t.ansi5 ?? t.accent))
    .child(v_flex().absolute().top(0).left(0).size_full().items_center().justify_center().gap(Math.max(2, Math.round(size / 11)))
      .child(bar(0.46)).child(bar(0.32)).child(bar(0.46)));
};

/** A small pill. With a fill it is a tinted label; without, an outlined one. */
export const chip = (t, text, color, fill) => div().flex_none().px(8).h(20).flex().items_center().rounded_full()
  .when(Boolean(fill), (e) => e.bg(fill)).when(!fill, (e) => e.border_1().border_color(color ? color + "66" : t.border))
  .text_size(11).font_medium().text_color(color ?? t.muted).child(text);

/** A 16px pill for a count or a short tag in a row: `color` on `fill`. */
export const tag = (t, text, color = t.dim, fill = t.raised, size = 10.5) => div().flex_none().px(6).h(16).flex().items_center().rounded_full()
  .bg(fill).text_size(size).font_semibold().text_color(color).child(text);

/** A report page's frame: scrolls, with the same margins on every page (the width maths in view.js's contentWidth follow them). */
export const PAGE_PADDING = 28;
export const pageFrame = (id) => v_flex().id(id).flex_1().min_h(0).overflow_y_scrollbar().px(PAGE_PADDING).pt(20).pb(28).gap(14);

/** A key cap, for the shortcuts shown beside what they do. */
export const kbd = (t, text) => div().flex_none().px(5).h(18).min_w(18).flex().items_center().justify_center().rounded(5)
  .border_1().border_color(t.border).bg(t.raised).text_size(10.5).font_medium().text_color(t.muted).child(text);

/** Upper case in the text's own language: Turkish "i" is "İ", not "I". */
export const upper = (text, locale) => { try { return String(text).toLocaleUpperCase(locale || "en"); } catch { return String(text).toUpperCase(); } };

/** A small caps label over a section, with an optional count or note on the right. `locale`: the text's language tag. */
export const eyebrow = (t, text, right = null, locale = "en") => h_flex().gap(8).items_center().text_size(10.5).font_semibold().text_color(t.dim)
  .child(div().flex_1().min_w(0).truncate().child(upper(text, locale)))
  .when(right !== null, (e) => e.child(div().flex_none().font_medium().child(right)));

/** A thin rounded progress bar `width` wide, `share` (0..1) of it filled. */
export const meter = (t, width, share, color = t.accent) => div().flex_none().w(width).h(4).rounded_full().bg(t.raised)
  .child(div().h_full().rounded_full().bg(color).w(Math.round(width * Math.max(0, Math.min(1, share)))));

/** A tinted card with a label pill, for a note beside a step or a message on a page. */
export const callout = (t, color, label, body) => h_flex().w_full().gap(10).items_start().px(12).py(9).rounded(10)
  .border_1().border_color(color + "33").bg(color + "0f")
  .when(Boolean(label), (e) => e.child(chip(t, label, color, color + "1f")))
  .child(div().flex_1().min_w(0).pt(1).text_size(12.5).line_height(1.55).text_color(t.foreground).child(body));

const ROW = 30, ROW_WITH_HINT = 44, MENU_MAX = 360;

/**
 * A picker's list: one row per option, the chosen one ticked, the highlighted
 * one (`active`, moved by the keyboard) filled. A virtual list, so the wheel
 * scrolls it and `scroll` (a VirtualListScrollHandle) keeps the highlight in
 * view; its rows take no handlers, so a click comes through `on_item_click`.
 */
export function menu(t, id, items, onPick, { width = 280, active = -1, scroll = null } = {}) {
  const frame = v_flex().id(`${id}-frame`).w(width).p(5).rounded(12).border_1().border_color(t.border).bg(t.popover).shadow_lg()
    .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
    // The list scrolls first; the wheel stops here instead of also scrolling the page under the menu.
    .on_scroll_wheel((_e, cx) => cx.stop_propagation());
  if (!items.length) return frame.child(div().p(8).text_size(12).text_color(t.dim).child("Nothing to pick."));
  const sizes = items.map((item) => (item.hint ? ROW_WITH_HINT : ROW));
  const height = Math.min(MENU_MAX, sizes.reduce((a, b) => a + b, 0));
  const row = (item, i) => v_flex().w_full().h(sizes[i]).px(8).justify_center().rounded(8).cursor_pointer()
    .when(i === active, (e) => e.bg(t.hover))
    .when(item.selected && i !== active, (e) => e.bg(t.selected))
    .child(h_flex().gap(6).items_center()
      .child(div().w(12).flex_none().text_size(11).text_color(t.accent).child(item.selected ? "✓" : ""))
      .child(div().flex_1().min_w(0).truncate().text_size(12.5).text_color(t.foreground).child(item.label))
      .when(Boolean(item.right), (e) => e.child(div().flex_none().text_size(11).text_color(t.dim).child(item.right))))
    .when(Boolean(item.hint), (e) => e.child(div().pl(18).text_size(11).text_color(t.dim).truncate().child(item.hint)));
  let list = v_virtual_list(id, items.length, sizes, (i) => String(i), (range) => items.slice(range.start, range.end).map((item, k) => row(item, range.start + k)))
    .size_full()
    .on_item_click((key, cx) => { const item = items[Number(key)]; if (item) onPick(item, cx); });
  if (scroll) list = list.track_scroll(scroll);
  return frame.child(div().relative().w_full().h(height).child(list).child(Scrollbar.vertical(id).absolute().inset_0()));
}

/** A dropdown's face: its label and a caret. */
export function picker(t, id, label, onClick, { disabled = false, tooltip = null, kind = "outline" } = {}) {
  return button(t, id, h_flex().gap(5).items_center().child(div().max_w(220).truncate().child(label)).child(div().text_color(t.dim).text_size(10).child("▾")), onClick, { small: true, disabled, tooltip, kind });
}

export const formatElapsed = (ms) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

export const formatTokens = (n) => (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n));
