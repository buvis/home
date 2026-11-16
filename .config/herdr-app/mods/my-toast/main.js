// Notifications. Info and success show as a toast, like the shipped `toast`.
// Errors and warnings go to a log instead (shared "alerts.log"): the status
// bar (my-status) shows a sign for them, and its click opens this mod with
// props {log: true} as a dialog that shows each one in full, selectable and
// copyable.

import { View, div, image } from "gpui-kit";
import { v_flex, h_flex, TextView } from "gpui-base";
import { props, closeOverlay, run, theme, shared, setShared, focused, panes, spaces } from "herdr";

const DOT = { error: "blocked", warning: "working", success: "done", info: "accent" };
const LOG = "alerts.log";
const KEEP = 50; // ponytail: newest 50 only; raise if older errors get lost
const text = (a) => `[${new Date(a.at).toLocaleString()}] ${a.level}: ${a.title}${a.where ? ` (from ${a.where})` : ""}${a.body ? `\n${a.body}` : ""}`;

// Where a message came from, as pane.focus args ({terminal} or {pane}): what its
// action names, else what was focused when it was posted. Mods that report after
// an await capture it first: action {name: "pane.focus", args: {terminal} | {pane}}.
const pick = (o) => o?.terminal ? { terminal: o.terminal } : o?.pane ? { pane: o.pane } : null;
const find = (g) => g && panes().find((x) => (g.terminal && x.terminal === g.terminal) || (g.pane && x.pane === g.pane));
function source(p) {
  const target = pick(p.action?.args) ?? pick(focused());
  const pane = find(target);
  const space = pane ? spaces().find((s) => s.tabs.some((tb) => tb.id === pane.tab)) : null;
  const tab = space?.tabs.find((tb) => tb.id === pane.tab);
  return { target, where: space ? `${space.name} / ${tab?.name ?? ""}` : target?.terminal ?? null };
}
const live = (g) => Boolean(find(g));
const go = (g) => run("pane.focus", g);

export default class Toast extends View {
  init() {
    const p = props() ?? {};
    if (p.log) return;
    this.src = source(p);
    // Herdr's "needs you" toasts (agent.focus) stay toasts: they are attention, not errors.
    if (p.action?.name === "agent.focus" || !["error", "warning"].includes(p.level)) return;
    const action = p.action?.name && p.action.name !== "pane.focus" ? p.action : null;
    setShared(LOG, [{ at: Date.now(), level: p.level, title: p.title ?? "", body: p.body ?? "", action, ...this.src }, ...(shared(LOG) ?? [])].slice(0, KEEP));
    closeOverlay(p.overlay);
  }

  render() {
    const p = props() ?? {};
    return p.log ? this.log(theme(), p) : this.toast(theme(), p);
  }

  log(t, p) {
    const list = shared(LOG) ?? [];
    const btn = (id, label, fn) => div().id(id).flex_none().px(8).py(3).rounded(4).bg(t.raised).text_size(12)
      .text_color(t.foreground).cursor_pointer().hover((s) => s.bg(t.hover)).on_click(fn).child(label);
    const copy = (id, value) => btn(id, this.copied === id ? "Copied" : "Copy", (_e, cx) => { cx.write_to_clipboard(value); this.copied = id; cx.notify(); });
    return v_flex().id("alerts").size_full().bg(t.popover).text_color(t.foreground)
      .child(h_flex().flex_none().px(16).py(10).gap(8).items_center().border_b(1).border_color(t.border)
        .child(div().flex_1().font_semibold().text_size(14).child(list.length ? `Errors and warnings (${list.length})` : "No errors"))
        .when(list.length > 0, (e) => e.child(copy("copy-all", list.map(text).join("\n\n")))
          .child(btn("clear", "Clear", () => { setShared(LOG, []); closeOverlay(p.overlay); })))
        .child(btn("close", "Close", () => closeOverlay(p.overlay))))
      .child(v_flex().id("alerts-list").flex_1().min_h(0).overflow_y_scrollbar().px(16).py(8).gap(12)
        .children(list.map((a, i) => v_flex().gap(4)
          .child(h_flex().gap(8).items_center()
            .child(div().size(8).rounded(4).flex_none().bg(t[DOT[a.level]]))
            .child(div().flex_1().min_w(0).font_semibold().text_size(13).child(a.title))
            .child(div().flex_none().text_size(11).text_color(t.dim).child(new Date(a.at).toLocaleTimeString()))
            .when(Boolean(a.action?.name), (e) => e.child(btn(`act-${i}`, "Open", () => { run(a.action.name, a.action.args ?? {}); closeOverlay(p.overlay); })))
            .when(Boolean(a.target), (e) => e.child(live(a.target)
              ? btn(`go-${i}`, a.target.terminal ? "Go to terminal" : "Go to pane", () => { go(a.target); closeOverlay(p.overlay); }).tooltip(a.where)
              : div().flex_none().text_size(11).text_color(t.dim).child("terminal gone")))
            .child(copy(`copy-${i}`, text(a))))
          .when(Boolean(a.where), (e) => e.child(div().text_size(11).text_color(t.dim).child(`from ${a.where}`)))
          .when(Boolean(a.body), (e) => e.child(TextView.markdown(`body-${i}`, `~~~~\n${a.body}\n~~~~`).selectable(true))))));
  }

  toast(t, p) {
    const login = /^([a-z0-9][a-z0-9_.-]{0,31}) needs login; run hc machine login \1$/.exec(p.body ?? "");
    const command = login ? `hc machine login ${login[1]}` : null;
    return h_flex()
      .id("toast")
      .size_full()
      .px(18)
      .gap(12)
      .items_center()
      .bg(t.popover)
      .cursor_pointer()
      .hover((s) => s.bg(t.hover))
      .on_click(() => {
        if (p.action?.name) run(p.action.name, p.action.args ?? {});
        else if (live(this.src?.target)) go(this.src.target);
        closeOverlay(p.overlay);
      })
      .child(p.icon ? image(p.icon).w(18).h(18).flex_none() : div().size(8).rounded(4).flex_none().bg(t[DOT[p.level] ?? "accent"]))
      .child(
        v_flex()
          .flex_1()
          .overflow_hidden()
          .child(div().truncate().font_semibold().text_size(13).text_color(t.foreground).child(login ? `${login[1]} needs a login: run` : p.title ?? ""))
          .when(!login && Boolean(p.body), (el) => el.child(div().truncate().text_size(12).text_color(t.muted).child(p.body ?? "")))
          .when(Boolean(login), (el) => el.child(h_flex().gap(8).items_center()
            .child(div().flex_1().min_w(0).truncate().tooltip(command).text_size(12).text_color(t.muted).child(command))
            .child(div().id("toast-login-copy").flex_none().px(6).py(3).rounded(4).bg(t.raised)
              .text_size(12).text_color(t.foreground).cursor_pointer().hover(s => s.bg(t.hover))
              .on_click((_e, cx) => { cx.stop_propagation(); cx.write_to_clipboard(command); this.copied = true; cx.notify(); })
              .child(this.copied ? "Copied" : "Copy")))),
      );
  }
}
