// cmd-shift-j: agent switcher. Hold cmd+shift, tap J to move down (keys.json "mod:attn-next" routes it
// here while the popup has focus), let go to jump. Click/Enter jump, Esc closes.
import { View, div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { exec, run, nextCommand, props, closeOverlay, agents, theme, fonts, settings } from "herdr";
import { sortAgents, initialIndex, move } from "./pick.js";

const NERD_FONT = "JetBrainsMono Nerd Font";
const ICONS = { dot: "\u{f111}" };
const iconFont = () => (fonts().includes(NERD_FONT) ? NERD_FONT : settings().font_family ?? "JetBrains Mono");
const glyph = (color, icon) => div().flex_none().font_family(iconFont()).when(Boolean(color), (el) => el.text_color(color)).child(icon);

// Quick tap: no event says the modifiers are already up, so ask macOS for the global flags (NSEvent.modifierFlags).
const CMD = 1 << 20;
async function cmdHeld() {
  const r = await exec("osascript", ["-l", "JavaScript", "-e", 'ObjC.import("Cocoa"); $.NSEvent.modifierFlags']);
  const flags = Number.parseInt(r.stdout.trim(), 10);
  return Number.isNaN(flags) ? true : (flags & CMD) !== 0; // unreadable: assume held, events will decide
}

export default class AttnNext extends View {
  init(_props, cx) {
    const live = agents();
    this.rows = sortAgents(live);
    this.at = initialIndex(live);
    this.done = false;
    this.seen = false; // any event with its modifiers has reached us
    this.handle = cx.focus_handle();
    this.handle.focus();
    // Ask once now; once the popup has the keyboard, ask again (released in between). Held: events take over.
    cx.spawn(async () => {
      if (!(await cmdHeld()) && !this.seen) return this.go();
      if (this.done || this.seen || !this.handle.is_focused()) return;
      if (!(await cmdHeld()) && !this.seen) this.go();
    });
    cx.spawn(async (cx) => {
      for (;;) {
        const c = await nextCommand();
        if (this.done) return;
        if (c === "focus") this.handle.focus();
        else if (c === "next" || c === "prev") {
          // A command from keys.json means cmd+shift were down when it fired.
          this.seen = true;
                this.at = move(this.at, c === "next" ? 1 : -1, this.rows.length);
          cx.notify();
        }
      }
    });
  }

  // Every key/modifier event carries the modifiers: cmd up means go, cmd down proves they are held.
  observe(e) {
    this.seen = true;
    if (!e.modifiers.platform) this.go();
  }

  cleanup() {
    this.done = true;
    closeOverlay(props()?.overlay);
  }

  go() {
    if (this.done) return;
    const a = this.rows[this.at];
    this.cleanup();
    if (a) run("agent.focus", { terminal: a.address });
  }

  async close() {
    this.done = true;
    this.handle?.release?.();
  }

  render(cx) {
    const t = theme();
    const color = { working: t.working, blocked: t.blocked, done: t.done, idle: t.idle };
    const word = { blocked: "blocked", done: "done", working: "working", idle: "idle" };
    return v_flex().id("attn-next").track_focus(this.handle).w_full().p(6).gap(1).bg(t.popover).text_size(13)
      .on_modifiers_changed((e) => this.observe(e))
      .on_key_up((e) => this.observe(e))
      .on_key_down((e, cx) => {
        this.observe(e);
        if (this.done) return;
        if (e.key === "enter") this.go();
        else if (e.key === "escape") this.cleanup();
        else if (e.key === "down") this.at = move(this.at, 1, this.rows.length);
        else if (e.key === "up") this.at = move(this.at, -1, this.rows.length);
        else return;
        cx.notify();
      })
      .when(!this.rows.length, (el) => el.child(div().p(10).text_color(t.muted).child("No agents")))
      .children(this.rows.map((a, i) => h_flex().id(`row-${a.address}`).h(32).px(10).gap(10).items_center().rounded(7)
        .when(i === this.at, (el) => el.bg(t.selected))
        .hover((s) => s.bg(t.hover))
        .on_click(() => { this.at = i; this.go(); })
        // where you are now: an accent bar on the left, like the sidebar's current item
        .child(div().flex_none().w(3).h(16).rounded(2).when(Boolean(a.focused), (el) => el.bg(t.accent)))
        .child(glyph(color[a.status] ?? t.unknown, ICONS.dot).text_size(9))
        .child(div().flex_1().min_w(0).truncate().text_color(t.foreground).child(a.tab_name || a.program?.name || a.address))
        .child(div().flex_none().max_w(140).truncate().text_size(11.5).text_color(t.dim).child(a.space_name))
        .child(div().flex_none().w(56).text_size(11.5).text_color(color[a.status] ?? t.dim).child(word[a.status] ?? a.status))));
  }
}
