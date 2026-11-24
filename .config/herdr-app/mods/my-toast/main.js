// Every notification enters shared "alerts.log". Info, success and agent
// attention also show as toasts; other errors/warnings stay in the log.
// my-status opens props {log: true}: full text, copy and source navigation.

import { View, div, image, svg } from "gpui-kit";
import { v_flex, h_flex, TextView } from "gpui-base";
import { props, closeOverlay, run, theme, shared, setShared, focused, panes, spaces, checking } from "herdr";

const DOT = { error: "blocked", warning: "working", success: "done", info: "accent" };
const LOG = "alerts.log";
const KEEP = 50; // Routine notices only; errors/warnings remain until Clear.
const problem = (level) => level === "error" || level === "warning";
const clock = (date) => [date.getHours(), date.getMinutes(), date.getSeconds()].map(n => String(n).padStart(2, "0")).join(":");
const timestamp = (at) => { const date = new Date(at); return `${date.toLocaleDateString()} ${clock(date)}`; };
const text = (a) => `[${timestamp(a.at)}] ${a.level}: ${a.title}${where(a) ? ` (from ${where(a)})` : ""}${a.body ? `\n${a.body}` : ""}`;

// Where a message came from, as pane.focus args ({terminal} or {pane}): what its
// action names, else what was focused when it was posted. Mods that report after
// an await capture it first: action {name: "pane.focus", args: {terminal} | {pane}}.
const pick = (o) => o?.terminal ? { terminal: o.terminal } : o?.pane ? { pane: o.pane } : null;
const find = (g) => g && panes().find((x) => (g.terminal && x.terminal === g.terminal) || (g.pane && x.pane === g.pane));
const paneName = (p) => p?.name || p?.title || p?.terminal || p?.pane || null;
// Older entries did not capture pane names; use their live target when available.
const where = (a) => a.paneName ? a.where : [a.where, paneName(find(a.target))].filter(Boolean).join(" / ");
function formatTime(at) {
  const date = new Date(at), today = new Date(Date.now());
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const prefix = date >= today ? "" : date >= yesterday ? "Yesterday " : `${date.toLocaleDateString()} `;
  return prefix + clock(date);
}
function source(p) {
  const target = pick(p.action?.args) ?? pick(focused());
  const pane = find(target);
  const space = pane ? spaces().find((s) => s.tabs.some((tb) => tb.id === pane.tab)) : null;
  const tab = space?.tabs.find((tb) => tb.id === pane.tab);
  const name = paneName(pane);
  return { target, paneName: name, where: space
    ? [space.name, tab?.name, name].filter(Boolean).join(" / ")
    : [target?.terminal, name !== target?.terminal ? name : null].filter(Boolean).join(" / ") };
}
const live = (g) => Boolean(find(g));
const go = (g) => run("pane.focus", g);

export default class Toast extends View {
  init() {
    const p = props() ?? {};
    if (p.log) return;
    this.src = source(p);
    if (checking() || !p.overlay) return;
    const level = p.level ?? "info";
    const action = p.action?.name && p.action.name !== "pane.focus" ? p.action : null;
    let notices = 0;
    setShared(LOG, [{ at: Date.now(), level, title: p.title ?? "", body: p.body ?? "", action, ...this.src }, ...(shared(LOG) ?? [])]
      .filter((a) => problem(a.level) || notices++ < KEEP));
    // Agent attention stays visible; ordinary problems keep their durable log route.
    if (problem(level) && p.action?.name !== "agent.focus") closeOverlay(p.overlay);
  }

  render() {
    const p = props() ?? {};
    return p.log ? this.log(theme(), p) : this.toast(theme(), p);
  }

  dismiss(entry) {
    const list = shared(LOG) ?? [];
    // Read current history: another toast may have arrived since this row rendered.
    // Remove one match, including for older entries that have no unique ID.
    const at = list.findIndex(a => JSON.stringify(a) === JSON.stringify(entry));
    if (at >= 0) setShared(LOG, list.filter((_a, i) => i !== at));
  }

  log(t, p) {
    const list = shared(LOG) ?? [];
    const btn = (id, icon, label, fn) => div().id(id).flex_none().size(26).flex().items_center().justify_center().rounded(4).bg(t.raised)
      .text_color(t.foreground).cursor_pointer().hover((s) => s.bg(t.hover)).on_click(fn)
      .tooltip(label).accessibility_label(label).child(svg(`mods/my-toast/${icon}.svg`).size(14));
    const copy = (id, value) => btn(id, this.copied === id ? "check" : "copy", this.copied === id ? "Copied" : id === "copy-all" ? "Copy all" : "Copy notification",
      (_e, cx) => { cx.write_to_clipboard(value); this.copied = id; cx.notify(); });
    return v_flex().id("alerts").size_full().bg(t.popover).text_color(t.foreground)
      .child(h_flex().flex_none().px(16).py(10).gap(8).items_center().border_b(1).border_color(t.border)
        .child(div().flex_1().font_semibold().text_size(14).child(list.length ? `Notifications (${list.length})` : "No notifications"))
        .when(list.length > 0, (e) => e.child(copy("copy-all", list.map(text).join("\n\n")))
          .when(list.some(a => a.level === "info" || a.level === "success"), e => e.child(btn("clear-routine", "list-check", "Dismiss info and success", () => {
            setShared(LOG, (shared(LOG) ?? []).filter(a => a.level !== "info" && a.level !== "success"));
          })))
          .child(btn("clear", "trash", "Clear all notifications", () => { setShared(LOG, []); closeOverlay(p.overlay); })))
        .child(btn("close", "x", "Close history", () => closeOverlay(p.overlay))))
      .child(div().flex_none().px(16).py(6).text_size(11).text_color(t.dim).child("Latest 50 routine notices. Errors and warnings stay until dismissed or cleared."))
      .child(v_flex().id("alerts-list").flex_1().min_h(0).overflow_y_scrollbar().px(16).py(8).gap(12)
        .children(list.map((a, i) => v_flex().gap(4)
          .child(h_flex().gap(8).items_center()
            .child(div().size(8).rounded(4).flex_none().bg(t[DOT[a.level]]))
            .child(div().flex_1().min_w(0).font_semibold().text_size(13).child(a.title))
            .child(div().id(`time-${i}`).flex_none().text_size(11).text_color(t.dim).tooltip(timestamp(a.at)).child(formatTime(a.at)))
            .when(Boolean(a.action?.name), (e) => e.child(btn(`act-${i}`, "external-link", "Open notification action", () => { run(a.action.name, a.action.args ?? {}); closeOverlay(p.overlay); })))
            .when(Boolean(a.target), (e) => e.child(live(a.target)
              ? btn(`go-${i}`, "terminal", `Go to ${where(a) || "source pane"}`, () => { go(a.target); closeOverlay(p.overlay); })
              : div().id(`go-${i}`).flex_none().size(26).flex().items_center().justify_center().disabled(true)
                .text_color(t.dim).tooltip("Source terminal is no longer available").accessibility_label("Source terminal is no longer available")
                .child(svg("mods/my-toast/terminal-off.svg").size(14))))
            .child(copy(`copy-${i}`, text(a)))
            .child(btn(`dismiss-${i}`, "x", "Dismiss notification", () => this.dismiss(a))))
          .when(Boolean(where(a)), (e) => e.child(div().text_size(11).text_color(t.dim).child(`from ${where(a)}`)))
          .when(Boolean(a.body), (e) => e.child(TextView.markdown(`body-${i}`, `~~~~\n${a.body}\n~~~~`).selectable(true))))));
  }

  toast(t, p) {
    const login = /^([a-z0-9][a-z0-9_.-]{0,31}) needs login; run hc machine login \1$/.exec(p.body ?? "");
    const command = login ? `hc machine login ${login[1]}` : null;
    return h_flex()
      .id("toast")
      .when(p.fitHeight, (el) => el.w_full().min_h(70).flex_none().py(12))
      .when(!p.fitHeight, (el) => el.size_full())
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
          .min_w(0)
          // 0.1.17 only gives the shipped toast automatic height; custom cards stay 72px.
          .when(!p.fitHeight, (el) => el.id("toast-text").h_full().min_h(0).overflow_y_scrollbar().py(10))
          .child(div().flex_none().font_semibold().text_size(13).text_color(t.foreground).child(login ? `${login[1]} needs a login: run` : p.title ?? ""))
          .when(!login && Boolean(p.body), (el) => el.child(div().flex_none().text_size(12).text_color(t.muted).child(p.body)))
          .when(Boolean(login), (el) => el.child(h_flex().gap(8).items_center()
            .child(div().flex_1().min_w(0).truncate().tooltip(command).text_size(12).text_color(t.muted).child(command))
            .child(div().id("toast-login-copy").flex_none().px(6).py(3).rounded(4).bg(t.raised)
              .text_size(12).text_color(t.foreground).cursor_pointer().hover(s => s.bg(t.hover))
              .on_click((_e, cx) => { cx.stop_propagation(); cx.write_to_clipboard(command); this.copied = true; cx.notify(); })
              .child(this.copied ? "Copied" : "Copy")))),
      );
  }
}
