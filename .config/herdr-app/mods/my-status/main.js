import { View, div, svg } from "gpui-kit";
import { h_flex } from "gpui-base";
import { spaces, agents, theme, run, window, keys, shared, openOverlay, nextCommand, checking } from "herdr";

const openLog = () => openOverlay({ mod: "my-toast", kind: "dialog", width: 760, height: 520, props: { log: true } });
const SEVERITIES = [
  ["error", "circle-x", "blocked", "Errors"],
  ["warning", "triangle-alert", "working", "Warnings"],
  ["success", "circle-check", "done", "Successes"],
  ["info", "info", "accent", "Info"],
];

export default class WorkspaceStatus extends View {
  // my-status.log (a key, the palette, `herdr-app do`) opens notification history too.
  init(_props, cx) {
    if (checking()) return;
    cx.spawn(async (cx) => { for (;;) { if (await nextCommand() === "log") openLog(); } });
  }

  // The palette key as actually bound, not a hardcoded one; without a
  // binding the hint stays useful ("commands") instead of lying.
  hint(t) {
    const mac = window()?.platform === "macos";
    const mod = { cmd: mac ? "⌘" : "Ctrl+", ctrl: mac ? "⌃" : "Ctrl+", shift: mac ? "⇧" : "Shift+", alt: mac ? "⌥" : "Alt+", option: mac ? "⌥" : "Alt+" };
    const b = keys().find((k) => k.section === "global" && k.action === "app.palette");
    const parts = b && b.keys.endsWith("--") ? [...b.keys.slice(0, -2).split("-"), "-"] : b?.keys.split("-");
    const key = parts && parts.map((p) => mod[p.toLowerCase()] ?? p.toUpperCase()).join("");
    return key ? `${key}  commands` : "commands";
  }

  render() {
    const t = theme();
    const space = spaces().find(s => s.active);
    const list = agents();
    const needs = list.filter(a => a.status === "blocked").length;
    const alerts = shared("alerts.log") ?? []; // written by my-toast
    const counts = SEVERITIES.map(([level, icon, color, label]) => ({
      level, icon, color, label, count: alerts.filter(a => (a.level ?? "info") === level).length,
    }));
    const label = (icon, text) => h_flex().gap(6).items_center().child(svg(`mods/workspace-chrome/${icon}.svg`).size(13)).child(text);
    return h_flex().size_full().px(14).gap(16).items_center().bg(t.chrome).border_t(1).border_color(t.border).text_size(11.8).text_color(t.muted)
      .child(label(space?.machine ? "server" : "monitor", space?.machine ?? "This computer"))
      .when(Boolean(space?.branch), el => el.child(label("branch", space.branch)))
      .child(h_flex().gap(6).items_center().child(div().size(6).rounded(3).bg(t.dim)).child(`${list.length} agents`)
        .when(needs > 0, el => el.child(div().text_color(t.blocked).child(`· ${needs} needs you`))))
      .child(div().flex_1())
      .children(counts.filter(a => a.count > 0).map(a => h_flex().id(`alerts-${a.level}`).gap(5).items_center().cursor_pointer()
        .text_color(t[a.color]).hover(s => s.text_color(t.foreground))
        .tooltip(`${a.label}: ${a.count}. Open notification history`)
        .accessibility_label(`${a.label}: ${a.count}. Open notification history`)
        .on_click(openLog)
        .child(svg(`mods/my-status/${a.icon}.svg`).size(13))
        .child(String(a.count))))
      .child(div().id("palette").text_color(t.dim).on_click(() => run("app.palette")).child(this.hint(t)));
  }
}
