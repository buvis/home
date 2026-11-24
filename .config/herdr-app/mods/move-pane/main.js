// Dialog: move a terminal to any tab on this computer, or to a NEW tab in any space.
// props { terminal, overlay }. Type to filter (space and tab names), ↑/↓ + Enter or click,
// Esc to leave. Stays open while moving: closing an overlay cancels its tasks.

import { View, div } from "gpui-kit";
import { v_flex, h_flex, InputState, Input } from "gpui-base";
import { run, props, closeOverlay, theme, spaces, panes, focused, notify, settings } from "herdr";
import { movePane } from "./move.js";

const H = { head: 38, tab: 32, new: 32 };
const MAX_LIST = 320;

// Where the terminal is now: its pane, tab and space (null when it is not a terminal pane).
function source() {
  const pane = panes().find((x) => x.terminal && x.terminal === props()?.terminal);
  const from = pane && spaces().find((s) => (s.tabs ?? []).some((t) => t.id === pane.tab));
  if (!from) return null;
  const tab = from.tabs.find((t) => t.id === pane.tab);
  return { pane, from, tab, lone: (tab?.panes ?? 2) <= 1 };
}

export default class MovePane extends View {
  init(_props, cx) {
    this.filter = "";
    this.at = 0;
    this.scroll = 0;
    this.moving = false;
    this.input = InputState.new({ placeholder: "Filter spaces and tabs…" });
    this.input.on("change", (_e, cx) => {
      this.filter = this.input.value();
      this.at = 0;
      this.scroll = 0;
      cx.notify();
    });
    this.input.on("submit", (_e, cx) => this.start(this.pickable()[this.at], cx));
    this.input.focus();
    cx.timer.after(600, () => this.input.focus());
    this.handle = cx.focus_handle();
  }

  // Current space first, then the others in order; spaces on other machines are left out
  // (a terminal cannot move between cores). Each space lists its other tabs, then "New tab".
  rows() {
    const src = source();
    if (!src) return [];
    const terms = this.filter.toLowerCase().split(/\s+/).filter(Boolean);
    const ok = (text) => terms.every((w) => text.toLowerCase().includes(w));
    const local = spaces().filter((s) => !s.machine);
    local.sort((a, b) => (b.id === src.from.id) - (a.id === src.from.id));
    const out = [];
    for (const w of local) {
      const here = w.id === src.from.id;
      const items = [];
      for (const tab of w.tabs) if (tab.id !== src.pane.tab && ok(`${w.name} ${tab.name}`)) items.push({ kind: "tab", w, tab });
      if (!(here && src.lone) && ok(`${w.name} new tab`)) items.push({ kind: "new", w });
      if (items.length) out.push({ kind: "head", w, here }, ...items);
    }
    return out;
  }

  pickable() {
    return this.rows().filter((r) => r.kind !== "head");
  }

  start(row, cx) {
    if (!row || this.moving) return;
    this.moving = true;
    cx.notify();
    const overlay = props().overlay;
    const dest = row.kind === "tab" ? { tab: row.tab.id } : { space: row.w.id };
    cx.spawn(async (cx) => {
      try {
        await movePane({ terminal: props().terminal, ...dest }, {
          run,
          panes,
          spaces,
          focused,
          sleep: (ms) => cx.sleep(ms),
        });
      } catch (error) {
        notify({ title: "Move pane", body: error.message, level: "error", action: { name: "pane.focus", args: { terminal: props().terminal } } });
      }
      closeOverlay(overlay);
    });
  }

  render(cx) {
    const t = theme();
    const src = source();
    const rows = this.rows();
    const pickable = rows.filter((r) => r.kind !== "head");
    this.at = Math.max(0, Math.min(this.at, pickable.length - 1));
    const sel = pickable[this.at];

    // One strip, each row at a fixed y; scrolling moves it only as far as keeps the
    // selected row in view (same technique as the picker mod).
    const tops = [];
    let y = 0;
    rows.forEach((r) => (tops.push(y), (y += H[r.kind])));
    const total = y;
    const height = Math.min(MAX_LIST, this.listHeight ?? MAX_LIST);
    const fixed = total > height;
    const maxScroll = Math.max(0, total - height);
    this.scroll = Math.max(0, Math.min(this.scroll, maxScroll));
    const si = rows.indexOf(sel);
    if (si >= 0) {
      if (tops[si] < this.scroll) this.scroll = tops[si];
      if (tops[si] + H[sel.kind] > this.scroll + height) this.scroll = tops[si] + H[sel.kind] - height;
    }
    const bottomOf = (i) => tops[i] + H[rows[i].kind];
    const place = (el, i) => (fixed ? el.absolute().left(0).right(0).top(tops[i] - this.scroll).bottom(height - (bottomOf(i) - this.scroll)) : el);
    const visible = (i) => !fixed || (bottomOf(i) > this.scroll && tops[i] < this.scroll + height);

    const row = (r) => {
      if (r.kind === "head") {
        return h_flex()
          .px(10)
          .pt(12)
          .pb(4)
          .gap(8)
          .items_center()
          .text_size(14)
          .font_semibold()
          .text_color(t.foreground)
          .child(div().truncate().child(r.w.name))
          .when(r.here, (el) => el.child(div().text_size(11).font_normal().text_color(t.dim).child("· this space")));
      }
      const on = r === sel;
      const base = h_flex()
        .id(r.kind === "tab" ? `mp-${r.tab.id}` : `mp-new-${r.w.id}`)
        .mx(4)
        .px(10)
        .h(32)
        .rounded(7)
        .gap(10)
        .items_center()
        .cursor_pointer()
        .when(on, (el) => el.bg(t.selected))
        .hover((s) => s.bg(t.hover))
        .on_click((_e, cx) => this.start(r, cx));
      if (r.kind === "new") {
        return base.text_color(t.muted).child(div().w(12).child("+")).child(div().flex_1().child("New tab"));
      }
      return base
        .child(div().w(12).flex_none().text_color(t[r.tab.status] ?? t.dim).child(r.tab.status ? "●" : "·"))
        .child(div().flex_1().truncate().text_color(t.foreground).child(r.tab.name))
        .child(div().text_size(11).text_color(t.dim).child(`${r.tab.panes} pane${r.tab.panes === 1 ? "" : "s"}`));
    };

    // The source tab disappears when its last pane leaves; its space too, if that was its only tab.
    let note = "";
    if (src?.lone) note = src.from.tabs.length === 1 ? "Moving this pane closes its tab and space" : "Moving this pane closes its tab";

    return v_flex()
      .id("move-pane")
      .track_focus(this.handle)
      .w_full()
      .min_h(0)
      .p(18)
      .gap(10)
      .bg(t.popover)
      .text_color(t.foreground)
      .text_size(13)
      .on_key_down((e, cx) => {
        if (this.moving) return;
        const k = e.key;
        if (k === "escape") return closeOverlay(props().overlay);
        if (k === "down" && pickable.length) this.at = (this.at + 1) % pickable.length;
        else if (k === "up" && pickable.length) this.at = (this.at + pickable.length - 1) % pickable.length;
        else return;
        cx.stop_propagation();
        cx.notify();
      })
      .child(
        h_flex()
          .items_center()
          .child(div().flex_1().text_size(15).font_semibold().child("Move pane to…"))
          .child(div().id("mp-esc").px(6).py(2).rounded(5).text_size(11).text_color(t.dim).cursor_pointer().hover((s) => s.bg(t.hover).text_color(t.foreground)).on_click(() => this.moving || closeOverlay(props().overlay)).child("Esc")),
      )
      .child(
        h_flex().h(36).flex_none().px(10).items_center().rounded(9).border_1().border_color(t.accent).bg(t.background)
          .child(Input.new(this.input).flex_1().h_full().text_size(12.8).text_color(t.foreground)),
      )
      .child(
        this.moving
          ? div().px(8).child("Moving…")
          : !src
            ? div().px(8).text_color(t.dim).child("Not a terminal pane")
            : !pickable.length
              ? div().px(8).text_color(t.dim).child(this.filter ? "No match" : "Nowhere to move to")
              : v_flex()
                  .id("mp-list")
                  .on_size_change((size, cx) => {
                    this.listHeight = size.height / settings().zoom;
                    cx.notify();
                  })
                  .h(Math.min(MAX_LIST, total))
                  .min_h(0)
                  .when(fixed, (el) =>
                    el.overflow_hidden().on_scroll_wheel((e, cx) => {
                      this.scroll = Math.max(0, Math.min(this.scroll - e.delta.y, maxScroll));
                      // The selection follows the wheel, so the next frame doesn't scroll back to it.
                      const idx = (n) => rows.indexOf(pickable[n]);
                      while (this.at < pickable.length - 1 && tops[idx(this.at)] < this.scroll) this.at++;
                      while (this.at > 0 && bottomOf(idx(this.at)) > this.scroll + height) this.at--;
                      cx.notify();
                    }))
                  .children(rows.map((r, i) => (visible(i) ? place(row(r), i) : null)).filter(Boolean)),
      )
      .when(note && !this.moving, (el) => el.child(div().px(4).text_size(11).text_color(t.dim).child(note)));
  }
}
