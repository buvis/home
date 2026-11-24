import { View, div, svg } from "gpui-kit";
import { h_flex } from "gpui-base";
import { spaces, agents, theme, run, window, keys, shared, openOverlay, nextCommand, checking } from "herdr";

const openLog = () => openOverlay({ mod: "my-toast", kind: "dialog", width: 760, height: 520, props: { log: true } });

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
    const errors = alerts.some(a => a.level === "error"), warnings = alerts.some(a => a.level === "warning");
    const label = (icon, text) => h_flex().gap(6).items_center().child(svg(`mods/workspace-chrome/${icon}.svg`).size(13)).child(text);
    return h_flex().size_full().px(14).gap(16).items_center().bg(t.chrome).border_t(1).border_color(t.border).text_size(11.8).text_color(t.muted)
      .child(label(space?.machine ? "server" : "monitor", space?.machine ?? "This computer"))
      .when(Boolean(space?.branch), el => el.child(label("branch", space.branch)))
      .child(h_flex().gap(6).items_center().child(div().size(6).rounded(3).bg(t.dim)).child(`${list.length} agents`)
        .when(needs > 0, el => el.child(div().text_color(t.blocked).child(`· ${needs} needs you`))))
      .child(div().flex_1())
      .when(alerts.length > 0, el => el.child(h_flex().id("alerts").gap(5).items_center().cursor_pointer()
        .text_color(errors ? t.blocked : warnings ? t.working : t.muted).hover(s => s.text_color(t.foreground))
        .tooltip(alerts[0].title)
        .on_click(openLog)
        .when(errors || warnings, e => e.child(svg("mods/my-status/triangle-alert.svg").size(13)))
        .child(`Notifications (${alerts.length})`)))
      .child(div().id("palette").text_color(t.dim).on_click(() => run("app.palette")).child(this.hint(t)));
  }
}
