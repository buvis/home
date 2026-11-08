// tmux-style prefix: keys.json binds "ctrl-q": "mod.open:prefix". This popup takes the
// keyboard, runs the command for the next key, and closes. Any other key just closes it.
import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { closeOverlay, props, run, theme } from "herdr";

// ponytail: tmux's bindings mapped to herdr commands; edit here, no config file
const KEYS = {
  c: ["tab.new"],
  n: ["tab.next"],
  p: ["tab.prev"],
  left: ["tab.prev"],
  right: ["pane.go", { direction: "left" }],
  ",": ["tab.rename"],
  "&": ["tab.close"],
  "%": ["pane.split", { direction: "right" }],
  '"': ["pane.split", { direction: "down" }],
  x: ["pane.close"],
  q: ["pane.close"],
  z: ["pane.zoom"],
  h: ["pane.go", { direction: "left" }],
  j: ["pane.go", { direction: "down" }],
  k: ["pane.go", { direction: "up" }],
  l: ["pane.go", { direction: "right" }],
  "(": ["space.prev"],
  ")": ["space.next"],
  $: ["space.rename"],
  s: ["pane.split", { direction: "down" }],
  v: ["pane.split", { direction: "right" }],
  w: ["mod.open", { name: "picker" }],
  "[": ["terminal.search"],
  ";": ["last-pane.go"],
  "?": ["app.help"],
};
for (let i = 1; i <= 9; i++) KEYS[i] = ["tab.select", { index: i }];

export default class Prefix extends View {
  init(_props, cx) {
    this.handle = cx.focus_handle();
    this.handle.focus();
    cx.timer.after(600, () => this.handle.focus());
  }

  key(e, cx) {
    cx.stop_propagation();
    closeOverlay(props().overlay);
    const hit = KEYS[e.key_char] ?? KEYS[e.key];
    if (hit) run(hit[0], hit[1] ?? {});
  }

  render() {
    const t = theme();
    const rows = Object.entries(KEYS).filter(([k]) => !/^[2-9]$/.test(k));
    return v_flex()
      .id("prefix")
      .track_focus(this.handle)
      .on_key_down((e, cx) => this.key(e, cx))
      .w_full()
      .p(12)
      .gap(2)
      .bg(t.popover)
      .text_size(12)
      .child(h_flex().justify_between().mb(6)
        .child(div().font_semibold().text_color(t.foreground).child("ctrl-q …"))
        .child(div().text_size(11).text_color(t.dim).child("Esc")))
      .children(rows.map(([k, [cmd, args]]) =>
        h_flex().gap(10)
          .child(div().w(28).text_color(t.accent).child(k === "1" ? "1-9" : k))
          .child(div().text_color(t.muted).child(args ? `${cmd} ${Object.values(args)[0]}` : cmd))));
  }
}
