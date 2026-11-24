// tmux-style prefix: keys.json binds "ctrl-q": "mod.open:prefix". This popup takes the
// keyboard and shows the shortcuts. "m" opens the mods menu; "r" enters resize mode.
import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { closeOverlay, props, run, theme } from "herdr";

const open = (name) => ["mod.open", { name }];
const BROWSE = ["pane.split", { direction: "right", argv: ["/Users/bob/.config/herdr-app/bin/browse"] }];
const MODS = "mods";
const RESIZE = "resize";
const DIRECTIONS = { h: "left", j: "down", k: "up", l: "right" };
const RESIZE_KEYS = new Map(Object.entries(DIRECTIONS).flatMap(([key, direction]) =>
  [[key, direction], [direction, direction]]));

// ponytail: edit here, no config file. item = [keys (first is shown first), label, action]
const COLUMNS = [
  [
    ["Tabs", [
      [["c", "t"], "new", ["tab.new"]],
      [["n", "right"], "next", ["tab.next"]],
      [["p", "left"], "previous", ["tab.prev"]],
      [["#"], "rename", ["tab.rename"]],
      [["&"], "close", ["tab.close"]],
      [["1-9"], "select", null],
    ]],
    ["Spaces", [
      [[")"], "next", ["space.next"]],
      [["("], "previous", ["space.prev"]],
      [["@"], "rename", ["space.rename"]],
    ]],
  ],
  [
    ["Panes", [
      [["s", '"'], "split down", ["pane.split", { direction: "down" }]],
      [["v", "%"], "split right", ["pane.split", { direction: "right" }]],
      [["x", "q"], "close", ["pane.close"]],
      [["z"], "zoom", ["pane.zoom"]],
      [["h", "j", "k", "l"], "focus", null],
      [["r"], "resize", RESIZE],
      [["$"], "rename", ["pane.rename"]],
      [[";"], "last pane", ["last-pane.go"]],
    ]],
    ["View", [
      [["b"], "sidebar", ["layout.toggle", { id: "sidebar" }]],
      [["f"], "panel", ["layout.toggle", { id: "panel" }]],
      [["L"], "layout", ["layout.switch"]],
      [["."], "settings", ["app.settings"]],
    ]],
  ],
  [
    ["Launch", [
      [["space"], "launcher", open("launcher")],
      [["w"], "picker", open("picker")],
      [[":"], "palette", ["app.palette"]],
      [["e"], "recall", open("recall")],
      [["o"], "files", open("file-picker")],
      [["O"], "on-screen", open("on-screen")],
      [["a"], "attention", open("attn-next")],
    ]],
    ["Other", [
      [["["], "search", ["terminal.search"]],
      [["?", "/"], "help", ["app.help"]],
      [["m"], "mods …", MODS],
    ]],
  ],
];

// Mirrored in mod.json "palette", so the command palette finds these by name
// (palette.test.mjs fails when the two lists drift).
export const MOD_ITEMS = [
  [["o"], "obsidian", open("obsidian")],
  [["O"], "obsidian panel", ["pane.split", { direction: "right", mod: "obsidian", props: { view: "panel" } }]],
  [["m"], "markdown", open("markdown-panel")],
  [["t"], "ciupaga", open("ciupaga")],
  [["b"], "browse", BROWSE],
  [["p"], "projects", ["tab.new", { name: "projects", mod: "bim-projects" }]],
  [["r"], "revive", open("revive")],
  [["u"], "updater", open("mod-updater")],
  [["i"], "worktree include", open("worktreeinclude")],
  [["x"], "copy mode", open("copy-mode")],
  [["w"], "walkthrough", open("walkthrough")],
];

const lookup = (items) => {
  const m = {};
  for (const [keys, , act] of items) if (act) for (const k of keys) m[k] = act;
  return m;
};
const KEYS = lookup(COLUMNS.flat().flatMap(([, items]) => items));
for (let i = 1; i <= 9; i++) KEYS[i] = ["tab.select", { index: i }];
for (const [key, direction] of Object.entries(DIRECTIONS)) KEYS[key] = ["pane.go", { direction }];
const SUB = lookup(MOD_ITEMS);

const SHOWN = { space: "␣", left: "←", right: "→" };
const keyLabel = (keys) => keys.map((k) => SHOWN[k] ?? k).join(" ");

export default class Prefix extends View {
  init(_props, cx) {
    this.sub = null;
    this.handle = cx.focus_handle();
    this.handle.focus();
    cx.timer.after(600, () => this.handle.focus());
  }

  key(e, cx) {
    cx.stop_propagation();
    if (this.sub === RESIZE) {
      const direction = RESIZE_KEYS.get(e.keystroke);
      if (direction) run("pane.resize", { direction });
      else if (e.keystroke === "escape" || e.keystroke === "enter") closeOverlay(props().overlay);
      return;
    }
    const table = this.sub === MODS ? SUB : KEYS;
    const k = e.key_char && e.key_char !== " " ? e.key_char : e.key;
    const hit = table[k] ?? table[e.key];
    if (hit === MODS || hit === RESIZE) {
      this.sub = hit;
      cx.notify();
      return;
    }
    closeOverlay(props().overlay);
    if (hit) run(hit[0], hit[1] ?? {});
  }

  group(t, title, items) {
    return v_flex().gap(2).mb(10)
      .child(div().text_size(11).font_semibold().text_color(t.dim).mb(2).child(title.toUpperCase()))
      .children(items.map(([keys, label]) =>
        h_flex().gap(8)
          .child(div().w(62).text_color(t.accent).child(keyLabel(keys)))
          .child(div().text_color(t.muted).child(label))));
  }

  render() {
    const t = theme();
    const body = this.sub === RESIZE
      ? div().text_color(t.muted).child("Use h j k l or the arrow keys to move the pane border.")
      : this.sub === MODS
      ? h_flex().child(v_flex().flex_1().child(this.group(t, "Mods", MOD_ITEMS)))
      : h_flex().gap(20).children(COLUMNS.map((col) =>
          v_flex().flex_1().children(col.map(([title, items]) => this.group(t, title, items)))));
    return v_flex()
      .id("prefix")
      .track_focus(this.handle)
      .on_key_down((e, cx) => this.key(e, cx))
      .w_full()
      .p(14)
      .bg(t.popover)
      .text_size(12)
      .child(h_flex().justify_between().mb(10)
        .child(div().font_semibold().text_color(t.foreground).child(
          this.sub === RESIZE ? "Resize pane" : this.sub === MODS ? "ctrl-q  m …" : "ctrl-q …"))
        .child(div().text_size(11).text_color(t.dim).child(this.sub === RESIZE ? "Enter or Esc to exit" : "Esc")))
      .child(body);
  }
}
