// Revive: bring back the coding agent a terminal lost, and fork a live one.
//
// The dialog (`mod.open:revive`) lists every session remembered on a terminal:
// the focused one first, with Fork and Resume, then the ones that need you,
// then the rest. The remembering and the automatic resume after a restart are
// done by revive.mjs, from the agents' hooks and the shell's rc file, so they
// work while this dialog, and the app, are closed.

import { View, div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { exec, run, theme, focused, appHome, home, props, closeOverlay, notify } from "herdr";
import { AGENTS, canFork, command, shortId, ago, shJoin, unresumable, needsCommand } from "./lib/core.js";

/**
 * Why a running session can't be forked from here, or null. A fork opens a new
 * terminal with the app's environment and the recorded folder: a session that
 * needs a variable or flag Revive doesn't carry, or whose folder failed the
 * check, would start without it, or elsewhere.
 */
const unforkable = (rec) => (rec?.needs?.length ? `It ran with ${rec.needs.join(", ")}: fork it from its own shell.`
  : rec?.cwdRefused ? "Its folder is missing, not yours, or writable by others." : null);

const ENGINE = () => `${appHome()}/mods/revive/revive.mjs`;
const REFRESH_MS = 4000;
// The dialog grows with its content up to this share of the window; past it, the sessions scroll.
const MAX_SHARE = 0.85;
// Room kept for the padding, the header and the footer; a note takes NOTE_H more.
const CHROME_H = 130;
const NOTE_H = 56;

/**
 * The tallest the sessions may be, in pixels, so the whole dialog fits the
 * window, or null when the window's size isn't known. A dialog sized by its
 * content can't shrink a part of itself, so the part gets a height of its own.
 */
function listMaxH(withNote) {
  let height = null;
  try { height = window.viewport_size()?.height; } catch { /* no window yet */ }
  if (!Number.isFinite(height) || height <= 0) return null;
  return Math.max(160, Math.floor(height * MAX_SHARE) - CHROME_H - (withNote ? NOTE_H : 0));
}

/** A folder the way a shell prompt shows it: the home folder as `~`. */
function tilde(path) {
  const h = home();
  if (!path || !h) return path;
  return path === h ? "~" : path.startsWith(h + "/") ? "~" + path.slice(h.length) : path;
}

const STATE = {
  running: { word: "Running", color: (t) => t.ansi2 },
  lost: { word: "Lost to a restart", color: (t) => t.ansi3 },
  interrupted: { word: "Interrupted", color: (t) => t.ansi3 },
  failed: { word: "Resume failed", color: (t) => t.ansi1 },
};
const NEEDS_YOU = new Set(["lost", "interrupted", "failed"]);
// Claude Code and pi write a session down only once it has a message; until then a resume finds nothing.
const NO_MESSAGE = "This session has no message yet, so there is nothing to fork. Send it one first.";

async function engine(args) {
  let r;
  try { r = await exec("node", [ENGINE(), ...args]); }
  catch (e) { return { ok: false, error: `Couldn't run node: ${e}` }; }
  if (r.code !== 0) return { ok: false, error: (r.stderr || r.stdout).trim() || `revive.mjs exited ${r.code}` };
  return { ok: true, out: r.stdout };
}

function button(t, id, label, onClick, { kind = "outline", hint = null, disabled = false } = {}) {
  const solid = kind === "solid";
  return h_flex().id(id).flex_none().h(28).px(10).gap(6).items_center().justify_center().rounded(7).text_size(12)
    .when(kind === "outline", (el) => el.border_1().border_color(t.border))
    .when(solid && !disabled, (el) => el.bg(t.solid).text_color(t.solid_foreground))
    .when(!solid, (el) => el.text_color(disabled ? t.dim : t.foreground))
    .when(disabled, (el) => el.opacity(0.5))
    .when(!disabled, (el) => el.cursor_pointer().hover((s) => (solid ? s.opacity(0.9) : s.bg(t.hover))))
    .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
    .on_click((e, cx) => { if (!disabled) onClick(e, cx); })
    .child(label)
    .when(Boolean(hint), (el) => el.child(div().text_size(10.5).text_color(solid ? t.solid_foreground : t.dim).opacity(0.7).child(hint)));
}

const heading = (t, text) => div().mt(16).mb(8).text_size(10.5).font_medium().text_color(t.dim).child(text);

function badge(t, state) {
  const s = STATE[state];
  if (!s) return div();
  return h_flex().flex_none().gap(5).items_center().text_size(11).text_color(s.color(t))
    .child(div().size(6).rounded(3).bg(s.color(t)))
    .child(s.word);
}

export default class Revive extends View {
  init(_props, cx) {
    this.entries = [];
    this.setup = null;
    this.loading = true;
    this.note = null;
    this.busy = false;
    this.focus = focused()?.terminal ?? null;
    this.handle = cx.focus_handle();
    this.handle.focus();
    // An overlay may not take focus while it is still opening; ask again once it is up.
    cx.timer.after(120, () => this.handle.focus());
    this.load(cx, { setup: true });
    cx.timer.every(REFRESH_MS, (cx) => this.load(cx));
  }

  /**
   * Asks the engine for the list. A request made while one is running (after
   * a click) runs again when that one returns, so its answer isn't stale.
   * Errors from the list itself go away once it works again; an action's stay
   * until the next action.
   */
  load(cx, { setup = false } = {}) {
    if (setup) this.wantSetup = true;
    if (this.fetching) { this.again = true; return; }
    this.fetching = true;
    this.again = false;
    cx.spawn(async (cx) => {
      const args = ["list"];
      if (this.focus && !this.focus.includes("/")) args.push("--focus", this.focus);
      if (this.wantSetup || !this.setup) { args.push("--setup"); this.wantSetup = false; }
      const r = await engine(args);
      this.fetching = false;
      this.loading = false;
      let failure = r.ok ? null : r.error;
      if (r.ok) {
        try {
          const data = JSON.parse(r.out);
          this.entries = data.entries ?? [];
          if (data.setup) this.setup = data.setup;
        } catch { failure = "revive.mjs answered something that isn't JSON."; }
      }
      if (failure) this.note = { level: "error", text: failure, from: "list" };
      else if (this.note?.from === "list") this.note = null;
      cx.notify();
      if (this.again) this.load(cx);
    });
  }

  close() { closeOverlay(props().overlay); }

  current() { return this.entries.find((e) => e.address === this.focus) ?? null; }

  fork(entry, place) {
    if (entry?.forkable === false || unforkable(entry?.rec)) return;
    const argv = command(entry?.rec, "fork");
    if (!argv) return;
    this.close();
    run("terminal.open", { argv, folder: entry.rec.cwd ?? undefined, place });
  }

  resume(entry, cx) {
    if (this.busy || unresumable(entry?.rec)) return;
    this.busy = true;
    this.note = null;
    cx.notify();
    cx.spawn(async (cx) => {
      const r = await engine(["resume", entry.address]);
      this.busy = false;
      if (!r.ok) { this.note = { level: "error", text: r.error }; cx.notify(); return; }
      this.close();
      run("pane.focus", { terminal: entry.address });
    });
  }

  setAuto(entry, on, cx) {
    this.note = null;
    cx.spawn(async (cx) => {
      const r = await engine(["auto", entry.address, on ? "on" : "off"]);
      if (!r.ok) this.note = { level: "error", text: r.error };
      this.load(cx);
    });
  }

  install(cx) {
    if (this.busy) return;
    this.busy = true;
    cx.notify();
    cx.spawn(async (cx) => {
      const r = await engine(["install"]);
      this.busy = false;
      this.note = r.ok ? { level: "info", text: r.out.trim() } : { level: "error", text: r.error };
      if (r.ok) notify({ title: "Revive", body: "Installed. New agent sessions are remembered from now on.", level: "success" });
      this.load(cx, { setup: true });
    });
  }

  key(e, cx) {
    const entry = this.current();
    const k = e.key;
    if (k === "escape") { cx.stop_propagation(); this.close(); return; }
    if (k === "r") { this.load(cx); return; }
    if (!entry?.rec) return;
    if (entry.state === "running" && canFork(entry.rec.agent)) {
      if (k === "f") this.fork(entry, "right");
      else if (k === "d") this.fork(entry, "down");
      else if (k === "t") this.fork(entry, "tab");
    } else if (k === "enter" && NEEDS_YOU.has(entry.state) && !unresumable(entry.rec)) this.resume(entry, cx);
  }

  // ── drawing ──

  focusedCard(t) {
    const entry = this.current();
    if (this.focus?.includes("/")) {
      return div().text_size(12).text_color(t.dim).child("The focused terminal is on another machine. Revive works on this computer for now.");
    }
    if (!entry?.rec && AGENTS[entry?.live]) return this.unrecordedCard(t, entry);
    if (!entry?.rec) {
      return div().text_size(12).text_color(t.dim).child(this.loading ? "Looking…" : "No agent session in the focused terminal.");
    }
    const { rec, state } = entry;
    const agent = AGENTS[rec.agent];
    const running = state === "running";
    const forks = canFork(rec.agent);
    const blocked = running && forks ? unforkable(rec) : null;
    const empty = running && (entry.forkable === false || Boolean(blocked));
    const flags = rec.flags?.length ? shJoin(rec.flags) : null;
    // Resume by hand that the engine would refuse: why, and what to run instead.
    const stuck = NEEDS_YOU.has(state) ? unresumable(rec) : null;
    const byHand = stuck?.needs ? needsCommand(rec) : null;
    return v_flex().gap(12).p(14).rounded(12).bg(t.raised).border_1().border_color(t.border)
      .child(h_flex().gap(8).items_center()
        .child(div().text_size(14).font_semibold().text_color(t.foreground).child(agent?.name ?? rec.agent))
        .child(div().text_size(11.5).text_color(t.dim).font_family("JetBrains Mono").child(shortId(rec.session)))
        .child(div().flex_1())
        .child(badge(t, state)))
      .child(v_flex().gap(4).text_size(12).text_color(t.muted)
        .when(Boolean(rec.cwd), (el) => el.child(div().truncate().child(tilde(rec.cwd))))
        .when(Boolean(flags), (el) => el.child(div().truncate().text_color(t.dim).font_family("JetBrains Mono").text_size(10.5).child(flags)))
        .when(Boolean(entry.unrecorded), (el) => el.child(div().text_color(t.dim).child(forks
          ? "Started before Revive was installed: it can be forked, but won't come back by itself."
          : "Started before Revive was installed: it won't come back by itself.")))
        .when(running && !forks, (el) => el.child(div().text_color(t.dim).child(`${agent?.name ?? rec.agent} can't fork a session.`)))
        .when(forks && empty, (el) => el.child(div().text_color(t.dim).child(blocked ?? NO_MESSAGE)))
        .when(Boolean(stuck?.folder), (el) => el.child(div().text_color(t.dim)
          .child(`Its folder ${tilde(stuck.folder)} is missing, not yours, or writable by others, so it isn't resumed here.`)))
        .when(Boolean(stuck?.needs), (el) => el.child(div().text_color(t.dim)
          .child(`It ran with ${stuck.needs.join(", ")}, which Revive doesn't carry. ${stuck.needs.some((n) => !n.startsWith("-")) ? "Set it in a shell" : "Fill in the folder"} and run:`)))
        .when(Boolean(byHand), (el) => el.child(div().text_color(t.muted).font_family("JetBrains Mono").text_size(10.5).child(byHand))))
      .child(h_flex().gap(6).flex_wrap()
        .when(running && forks, (el) => el
          .child(button(t, "fork-right", "Fork right", () => this.fork(entry, "right"), { hint: "F", disabled: empty }))
          .child(button(t, "fork-down", "Fork below", () => this.fork(entry, "down"), { hint: "D", disabled: empty }))
          .child(button(t, "fork-tab", "Fork to a tab", () => this.fork(entry, "tab"), { hint: "T", disabled: empty })))
        .when(NEEDS_YOU.has(state), (el) => el
          .when(Boolean(byHand), (row) => row.child(button(t, "copy-command", "Copy command", (_e, cx) => {
            cx.write_to_clipboard(byHand);
            notify({ title: "Copied", body: byHand, level: "success", timeout: 2500 });
          })))
          .child(button(t, "resume-here", this.busy ? "Resuming…" : "Resume", (_e, cx) => this.resume(entry, cx), { kind: "solid", hint: "↵", disabled: this.busy || Boolean(stuck) }))));
  }

  /**
   * An agent running in the focused terminal that Revive has no record of. A
   * Codex session is recorded at its first message, and never while Codex's
   * shared background server runs it: that server, not the terminal, runs the
   * hooks, so they can't tell which terminal the session is in.
   */
  unrecordedCard(t, entry) {
    const agent = AGENTS[entry.live];
    const why = entry.live === "codex"
      ? "Revive has no record of this session, so it can't be forked or brought back. Codex records it at its first message, and not at all while its shared background server runs it (daemon_auto_start)."
      : "Revive has no record of this session, so it can't be forked or brought back. It is recorded when it starts once Revive is installed.";
    return v_flex().gap(12).p(14).rounded(12).bg(t.raised).border_1().border_color(t.border)
      .child(h_flex().gap(8).items_center()
        .child(div().text_size(14).font_semibold().text_color(t.foreground).child(agent.name))
        .child(div().flex_1())
        .child(badge(t, "running")))
      .child(v_flex().gap(4).text_size(12).text_color(t.muted)
        .when(Boolean(entry.folder), (el) => el.child(div().truncate().child(tilde(entry.folder))))
        .child(div().text_color(t.dim).child(why)));
  }

  row(t, entry, i) {
    const { rec, state } = entry;
    const agent = AGENTS[rec.agent];
    const needs = NEEDS_YOU.has(state);
    return h_flex().id(`row-${i}`).h(48).px(12).gap(12).items_center().rounded(10).cursor_pointer()
      .when(needs, (el) => el.bg(t.raised))
      .hover((s) => s.bg(t.hover))
      .on_click(() => { this.close(); run("pane.focus", { terminal: entry.address }); })
      .child(v_flex().flex_1().min_w(0)
        .child(h_flex().gap(6).items_center()
          .child(div().text_size(13).font_medium().text_color(t.foreground).child(agent?.name ?? rec.agent))
          .child(div().text_size(11).text_color(t.dim).font_family("JetBrains Mono").child(shortId(rec.session))))
        .child(div().truncate().text_size(11).text_color(t.dim)
          .child([entry.where ?? entry.address, rec.resumed ? `resumed ${ago(rec.resumed)}` : null].filter(Boolean).join(" · "))))
      .child(badge(t, state))
      .when(!entry.unrecorded, (el) => el.child(button(t, `auto-${i}`, rec.auto ? "Auto" : "Auto off", (_e, cx) => this.setAuto(entry, !rec.auto, cx), { kind: "ghost" })))
      .when(Boolean(entry.unrecorded), (el) => el.child(div().flex_none().text_size(11).text_color(t.dim).child("not remembered")))
      .when(needs, (el) => el.child(button(t, `resume-${i}`, "Resume", (_e, cx) => this.resume(entry, cx), { kind: "solid", disabled: this.busy || Boolean(unresumable(rec)) })));
  }

  setupLine(t) {
    const s = this.setup;
    if (!s) return div();
    const shellOk = Object.values(s.shell ?? {}).some(Boolean);
    // One entry per agent: true, false, or null when that agent isn't installed.
    const agents = Object.keys(AGENTS).filter((k) => s[k] !== null && s[k] !== undefined);
    const ok = shellOk && agents.every((k) => s[k]);
    const part = (name, on) => h_flex().gap(4).text_color(on ? t.muted : t.ansi1)
      .child(div().text_color(on ? t.ansi2 : t.ansi1).child(on ? "✓" : "✕"))
      .child(name);
    return h_flex().gap(10).items_center().text_size(11)
      // pi's and omp's hooks come from an extension, not a hooks file.
      .children(agents.map((k) => part(k === "pi" || k === "omp" ? `${AGENTS[k].name} extension` : `${AGENTS[k].name} hooks`, s[k])))
      .child(part("shell", shellOk))
      .child(div().flex_1())
      .when(!ok, (el) => el.child(button(t, "install", this.busy ? "Installing…" : "Install", (_e, cx) => this.install(cx), { kind: "solid", disabled: this.busy })));
  }

  render(cx) {
    const t = theme();
    const others = this.entries.filter((e) => e.rec && e.address !== this.focus);
    const needs = others.filter((e) => NEEDS_YOU.has(e.state));
    const rest = others.filter((e) => !NEEDS_YOU.has(e.state));
    const listH = listMaxH(Boolean(this.note));
    return v_flex().id("revive").track_focus(this.handle).on_key_down((e, cx) => this.key(e, cx))
      .w_full().bg(t.popover).px(20).pt(18).pb(16)
      .child(h_flex().flex_none().items_center().gap(8)
        .child(div().text_size(16).font_semibold().text_color(t.foreground).child("↻ Revive"))
        .child(div().text_size(11.5).text_color(t.dim).child("Agent sessions, remembered on their terminals")))
      .child(div().id("revive-scroll").when(listH !== null, (el) => el.max_h(listH)).overflow_y_scrollbar()
        .child(heading(t, "FOCUSED TERMINAL"))
        .child(this.focusedCard(t))
        .when(needs.length > 0, (el) => el.child(heading(t, "NEED YOU")).child(v_flex().gap(4).children(needs.map((e, i) => this.row(t, e, `n${i}`)))))
        .when(rest.length > 0, (el) => el.child(heading(t, "OTHER SESSIONS")).child(v_flex().gap(4).children(rest.map((e, i) => this.row(t, e, `r${i}`))))))
      .when(Boolean(this.note), (el) => el.child(div().flex_none().mt(8).p(8).rounded(6).bg(t.raised).text_size(11.5)
        .text_color(this.note.level === "error" ? t.ansi1 : t.muted).child(this.note.text)))
      .child(div().flex_none().mt(16).pt(12).border_t_1().border_color(t.border).child(this.setupLine(t)));
  }
}
