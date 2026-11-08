// App launcher. Lists every mod whose mod.json has an "app" entry:
//   { "place": "none", "title": "Sudoku", "app": { "icon": "🧩", "about": "Number puzzle", "open": "tab" } }
// "open": "tab" (default) | "right" | "down" (split). Keys: ↑/↓ or j/k move, Enter or 1-9 open, Esc closes.
import { View, div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { exec, appHome, run, theme, props, closeOverlay } from "herdr";

export default class Launcher extends View {
  init(_p, cx) {
    this.handle = cx.focus_handle();
    this.handle.focus();
    this.apps = null;
    this.sel = 0;
    cx.spawn(async (cx) => {
      const home = appHome(), list = [];
      try {
        const r = await exec("sh", ["-c", `for f in "${home}"/mods/*/mod.json; do grep -q '"app"' "$f" && { echo "@@$f"; cat "$f"; echo; }; done`]);
        for (const chunk of r.stdout.split("@@").filter(Boolean)) {
          const nl = chunk.indexOf("\n"), f = chunk.slice(0, nl), mod = f.split("/").slice(-2)[0];
          try {
            const j = JSON.parse(chunk.slice(nl + 1));
            if (j.app) list.push({ mod, name: j.title ?? mod, icon: j.app.icon ?? "▫", about: j.app.about ?? "", open: j.app.open ?? "tab" });
          } catch (e) { this.err = `${mod}: ${e?.message ?? e}`; }
        }
      } catch (e) { this.err = `scan failed: ${e?.message ?? e}`; }
      this.apps = list.sort((a, b) => a.name.localeCompare(b.name));
      cx.notify();
    });
  }

  launch(a) {
    closeOverlay(props().overlay);
    if (a.open === "tab") run("tab.new", { name: a.name, mod: a.mod });
    else run("pane.split", { direction: a.open, mod: a.mod });
  }

  onKey(e, cx) {
    const n = this.apps?.length ?? 0, k = e.key;
    if (k === "escape") closeOverlay(props().overlay);
    else if (k === "down" || k === "j") this.sel = n ? (this.sel + 1) % n : 0;
    else if (k === "up" || k === "k") this.sel = n ? (this.sel + n - 1) % n : 0;
    else if (k === "enter" && n) this.launch(this.apps[this.sel]);
    else if (/^[1-9]$/.test(k) && this.apps?.[+k - 1]) this.launch(this.apps[+k - 1]);
    else return;
    cx.stop_propagation();
    cx.notify();
  }

  render() {
    const t = theme(), apps = this.apps ?? [];
    return v_flex().id("launcher").w_full().p(12).gap(8).bg(t.popover).text_color(t.foreground).text_size(13)
      .track_focus(this.handle).on_key_down((e, cx) => this.onKey(e, cx))
      .child(h_flex().items_center().px(4)
        .child(div().flex_1().text_size(15).font_semibold().child("Apps"))
        .child(div().text_size(11).text_color(t.dim).child("↑↓ Enter · Esc")))
      .child(v_flex().flex_none().h(Math.min(320, Math.max(46, apps.length * 46))).min_h(0).gap(2).overflow_y_scrollbar()
        .children(apps.map((a, i) =>
          h_flex().id(`app-${a.mod}`).h(44).flex_none().px(10).gap(10).items_center().rounded(8).cursor_pointer()
            .when(i === this.sel, (e) => e.bg(t.selected)).hover((s) => s.bg(t.hover))
            .on_click(() => this.launch(a))
            .child(div().w(26).flex_none().text_size(20).child(a.icon))
            .child(v_flex().flex_1().min_w(0)
              .child(div().truncate().child(a.name))
              .child(div().truncate().text_size(11).text_color(t.dim).child(a.about)))
            .child(div().text_size(11).text_color(t.dim).child(i < 9 ? String(i + 1) : "")))))
      .when(this.apps && !apps.length, (e) => e.child(div().p(10).text_color(t.dim).child('No apps. Add "app": {…} to a mod.json.')))
      .when(this.err, (e) => e.child(div().px(10).text_size(10).text_color(t.dim).child(this.err)));
  }
}
