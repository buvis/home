// Kanso's panel kit: the text field and the text it edits. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-field.js.
import { div, svg } from "gpui-kit";
import { h_flex, v_flex, Input, InputState, Textarea, TextareaState } from "gpui-base";
import { G, H, R, T, LINE, ICON_ROW, CLEAR, glyphOf, well } from "./ui.js";
import { iconButton, button } from "./ui-button.js";

/** The most lines a multi-line field grows to before it scrolls. */
export const FIELD_LINES = 10;

const capped = (text = "", limit = null) => (limit ? [...text].slice(0, limit).join("") : text);

/** A field's text. Create it in init or a handler, never in render. `limit`: the most characters it holds. */
export class TextField {
  constructor(options = {}, { multiline = false, limit = null } = {}) {
    this.multiline = multiline;
    this.focused = false;
    const start = limit ? { ...options, value: capped(options.value, limit) } : options;
    this.state = multiline ? TextareaState.new(start) : InputState.new(start);
    if (multiline) this.state.set_auto_grow(1, FIELD_LINES);
    // Herdr's text state has no length cap, so typing past the limit is cut back at once.
    if (limit) this.state.on("change", () => {
      const value = this.state.value();
      if (capped(value, limit) !== value) this.state.set_value(capped(value, limit));
    });
    // Herdr styles no focus on a text frame, so the ring follows these.
    this.state.on("focus", (_e, cx) => { this.focused = true; cx.notify(); });
    this.state.on("blur", (_e, cx) => { this.focused = false; cx.notify(); });
  }

  value() { return this.state.value(); }

  set_value(next) { this.state.set_value(next); }

  set_selected_range(range) { this.state.set_selected_range(range); }

  on(event, handler) { return this.state.on(event, handler); }

  focus() { this.state.focus(); }

  release() { return this.state.release(); }
}

/** One text field. `text` is a TextField; `icon` adds a trailing icon button, `iconTip` its name.
 * `inline`: rename in place, a badge tall inside the line it renames, with no action. */
export function field(id, text, c, { label = null, icon = null, onIcon = null, iconTip = label, error = false, disabled = false, spoken = label, inline = false, lead = null } = {}) {
  const multi = text.multiline && !inline;
  const radius = inline ? R.sm : R.control;
  const inset = inline ? G.xs : G.md;
  const editor = disabled
    ? div().flex_1().min_w(0).text_color(c.dim).when(!multi, (el) => el.truncate()).child(text.value())
    : (multi ? Textarea : Input).new(text.state).flex_1().min_w(0).text_color(c.text);
  const box = h_flex().id(`${id}-box`).rounded(radius).border_1().bg(disabled ? well(c) : c.canvas)
    .border_color(error ? c.blocked : c.input)
    .when(!disabled && !error, (el) => el.hover((s) => s.border_color(c.muted)))
    .when(multi, (el) => el.min_h(H.control * 2 + G.md).items_stretch())
    .when(!multi, (el) => el.h(inline ? H.badge : H.control))
    .when(Boolean(lead) && !inline, (el) => el.pl(G.sm - LINE).gap(G.sm).child(svg(glyphOf(lead)).size(ICON_ROW).flex_none().text_color(c.muted)))
    .child(editor.text_size(T.value).when(!lead || inline, (el) => el.pl(inset)).when(!icon || inline, (el) => el.pr(inset)).when(multi, (el) => el.py(G.sm))
      .when(Boolean(spoken), (el) => el.accessibility_label(spoken)))
    .when(Boolean(icon) && !inline, (el) => el.gap(G.sm).pr(G.xs)
      .child(iconButton(`${id}-icon`, icon, iconTip ?? icon, onIcon, c, { small: true, disabled })));
  // The ring sits outside the edge and takes no room, as an outline would; Herdr has none.
  const ring = v_flex().id(id).m(-G.hair).rounded(radius + G.hair).border_2()
    .border_color(text.focused && !disabled ? c.accent : CLEAR).child(box);
  return label && !inline ? labelled(label, ring, c) : ring;
}

export const labelled = (label, child, c) => v_flex().gap(G.sm).child(div().text_size(T.value).font_medium().text_color(c.muted).child(label)).child(child);

export const choices = (id, items, on, onPick, c) => h_flex().id(id).flex_wrap().gap(G.xs)
  .children(items.map(({ key, label }) => button(`${id}-${key}`, label, (cx) => onPick(key, cx), c, { kind: "tonal", small: true, held: on(key) })));
