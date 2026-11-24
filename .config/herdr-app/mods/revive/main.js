// Revive: bring back the coding agent a terminal lost, and fork a live one.
//
// The dialog (`mod.open:revive`) lists every session remembered on a terminal:
// the focused one first, with Fork and Resume, then the ones that need you,
// then the rest. The remembering and the automatic resume after a restart are
// done by revive.mjs, from the agents' hooks and the shell's rc file, so they
// work while this dialog, and the app, are closed.

import { View, div, image, svg } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { exec, run, theme, focused, appHome, home, props, closeOverlay, notify, shared, setShared } from "herdr";
import * as herdr from "herdr";
import { AGENTS, canFork, canRestore, command, shortId, ago, unresumable, needsCommand, cameBack } from "./lib/core.js";
import { updater, VERSION, PROMPT, RELEASES } from "./lib/update.js";

/**
 * Whether `herdr-app check` is loading the dialog: `init()` runs for real
 * there, so it mustn't run the engine or ask GitHub. `checking` came with
 * Herdr 0.1.16; read from the module, not imported by name, so an older
 * Herdr, which has no such export, still loads the mod.
 */
const checking = () => {
  try { return typeof herdr.checking === "function" && herdr.checking() === true; }
  catch { return false; }
};

/**
 * Whether the app runs on Windows, where herdr-core starts PowerShell: a
 * command shown to copy is written in its syntax there. Read from the module
 * like `checking`, so a Herdr without `window()` still loads the mod.
 */
const onWindows = () => {
  try { return typeof herdr.window === "function" && herdr.window()?.platform === "windows"; }
  catch { return false; }
};

/**
 * Why a running session can't be forked from here, or null. A fork opens a new
 * terminal with the app's environment and the recorded folder: a session that
 * needs a variable or flag Revive doesn't carry, or whose folder failed the
 * check, would start without it, or elsewhere.
 */
const unforkable = (rec) => (rec?.needs?.length ? `It ran with ${rec.needs.join(", ")}: fork it from its own shell.`
  : rec?.cwdRefused ? "Its folder is missing, not yours, or writable by others." : null);

const ENGINE = () => `${appHome()}/mods/revive/revive.mjs`;
// svg() paths resolve against the app's folder, like the engine's.
const ICONS = "mods/revive/icons";
const MONO = "JetBrains Mono";
const REFRESH_MS = 4000;
// The dialog grows with its content up to this share of the window; past it, the sessions scroll.
const MAX_SHARE = 0.85;
// Room kept for the header and the footer; a note takes NOTE_H more, the
// new-release strip UPDATE_H, the came-back strip CAME_BACK_H.
const CHROME_H = 150;
const NOTE_H = 56;
const UPDATE_H = 150;
const CAME_BACK_H = 80;
// Shared state: the latest came-back resume the person dismissed (lib/core.js cameBack).
const CAME_BACK_SEEN = "revive.cameBack";

/**
 * The tallest the sessions may be, in pixels, so the whole dialog fits the
 * window, or null when the window's size isn't known. A dialog sized by its
 * content can't shrink a part of itself, so the part gets a height of its own.
 */
function listMaxH(extra) {
  let height = null;
  try { height = window.viewport_size()?.height; } catch { /* no window yet */ }
  if (!Number.isFinite(height) || height <= 0) return null;
  return Math.max(160, Math.floor(height * MAX_SHARE) - CHROME_H - extra);
}

/** A folder the way a shell prompt shows it: the home folder as `~`. */
function tilde(path) {
  const h = home();
  if (!path || !h) return path;
  return path === h ? "~" : path.startsWith(h + "/") || path.startsWith(h + "\\") ? "~" + path.slice(h.length) : path;
}

/** A theme color with an alpha (two hex digits), as Herdr's own mods do; any other format is left alone. */
const alpha = (color, aa) => (/^#[0-9a-fA-F]{6}$/.test(color ?? "") ? color + aa : color);

const STATE = {
  running: { word: "Running", color: (t) => t.ansi2 },
  lost: { word: "Lost to a restart", color: (t) => t.ansi3 },
  interrupted: { word: "Interrupted", color: (t) => t.ansi3 },
  failed: { word: "Resume failed", color: (t) => t.ansi1 },
};
const NEEDS_YOU = new Set(["lost", "interrupted", "failed"]);
// Claude Code and pi write a session down only once it has a message; until then a resume finds nothing.
const NO_MESSAGE = "This session has no message yet, so there is nothing to fork. Send it one first.";
const NO_MESSAGE_UNRECORDED = "This session has no message yet, so there is nothing to fork or remember. Send it one first.";

async function engine(args) {
  let r;
  try { r = await exec("node", [ENGINE(), ...args]); }
  catch (e) { return { ok: false, error: `Couldn't run node: ${e}` }; }
  if (r.code !== 0) return { ok: false, error: (r.stderr || r.stdout).trim() || `revive.mjs exited ${r.code}` };
  return { ok: true, out: r.stdout };
}

// ── pieces ──────────────────────────────────────────────────────────────────

const icon = (name, size, color) => svg(`${ICONS}/${name}.svg`).size(size).flex_none().text_color(color);
// Local edit: the one busy indicator, the same ring as the tab bar, agents list and Ship bar.
const busyLabel = (t, text) => h_flex().gap(6).items_center()
  .child(svg("mods/workspace-chrome/spinner.svg").size(12).flex_none().text_color(t.working).spin(900)).child(text);

/** A key, as the dialog shows it on a button or in the footer. */
const kbd = (t, key, onAccent = false) => div().flex_none().px(5).rounded(4).font_family(MONO).text_size(10)
  .when(onAccent, (el) => el.bg(alpha(t.accent_foreground, "24")).text_color(t.accent_foreground))
  .when(!onAccent, (el) => el.bg(t.raised).border_1().border_color(t.border).text_color(t.muted))
  .child(key);

/**
 * A button: `solid` (the one thing to do, in the theme's accent), `outline` or
 * `ghost` (text only). `icon` names a file in icons/, `hint` its key.
 */
function button(t, id, label, onClick, { kind = "outline", icon: name = null, hint = null, disabled = false, small = false } = {}) {
  const solid = kind === "solid";
  const ink = solid ? t.accent_foreground : kind === "ghost" ? t.muted : t.foreground;
  return h_flex().id(id).flex_none().h(small ? 28 : 32).px(small ? 10 : 12).gap(8).items_center().justify_center().rounded(8)
    .text_size(small ? 12 : 12.5).text_color(ink)
    .when(solid, (el) => el.bg(t.accent).font_semibold())
    .when(kind === "outline", (el) => el.bg(t.raised).border_1().border_color(t.border))
    .when(disabled, (el) => el.opacity(0.45))
    .when(!disabled, (el) => el.cursor_pointer().hover((s) => (solid ? s.opacity(0.88) : s.bg(t.hover))))
    .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
    .on_click((e, cx) => { if (!disabled) onClick(e, cx); })
    .when(Boolean(name), (el) => el.child(icon(name, 14, solid ? t.accent_foreground : t.muted)))
    .child(label)
    .when(Boolean(hint), (el) => el.child(kbd(t, hint, solid)));
}

/** A small text link. */
const link = (t, id, label, onClick, color = t.dim) => div().id(id).flex_none().text_size(11.5).text_color(color)
  .cursor_pointer().hover((s) => s.text_color(t.foreground))
  .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
  .on_click(onClick).child(label);

/** An on/off switch. */
const toggle = (t, id, on, onClick) => h_flex().id(id).flex_none().w(32).h(18).p(2).rounded(9).items_center()
  .bg(on ? t.accent : alpha(t.foreground, "2e")).when(on, (el) => el.justify_end())
  .cursor_pointer().on_mouse_down("left", (_e, cx) => cx.stop_propagation()).on_click(onClick)
  .child(div().size(14).rounded(7).bg("#ffffff"));

/** A section title, with a count when it has one. */
const section = (t, text, count = null, color = null) => h_flex().gap(8).items_center().mt(18).mb(8)
  .child(div().text_size(11).font_medium().text_color(t.dim).child(text))
  .when(count !== null, (el) => el.child(div().px(6).rounded(8).text_size(10.5).font_semibold()
    .bg(alpha(color, "24")).text_color(color).child(String(count))));

/** A session's state: a filled pill when it needs you, a dot and a word otherwise. */
function status(t, state) {
  const s = STATE[state];
  if (!s) return div();
  const color = s.color(t);
  return h_flex().flex_none().gap(6).items_center().text_size(11.5).font_medium().text_color(color)
    .when(NEEDS_YOU.has(state), (el) => el.h(22).px(9).rounded(11).bg(alpha(color, "1f")))
    .child(div().size(6).rounded(3).bg(color))
    .child(s.word);
}

/** Carried flags as chips: each flag with its values. */
function flagChips(t, flags = []) {
  const units = [];
  for (const word of flags.map(String)) {
    if (word.startsWith("-") || !units.length) units.push(word);
    else units[units.length - 1] += ` ${word}`;
  }
  return h_flex().gap(6).flex_wrap().children(units.map((u) => div().px(7).py(3).rounded(6).bg(t.background)
    .border_1().border_color(t.border).font_family(MONO).text_size(10.5).text_color(t.muted).child(u)));
}

/** A line of dim help text in a card. */
const hint = (t, text, color = t.dim) => div().text_size(12).line_height(1.45).text_color(color).child(text);

// ── the dialog ──────────────────────────────────────────────────────────────

export default class Revive extends View {
  init(_props, cx) {
    this.entries = [];
    this.setup = null;
    this.loading = true;
    this.note = null;
    this.busy = false;
    this.programs = {};
    this.focus = focused()?.terminal ?? null;
    this.handle = cx.focus_handle();
    this.handle.focus();
    // An overlay may not take focus while it is still opening; ask again once it is up.
    cx.timer.after(120, () => this.handle.focus());
    this.update = updater({ shared, setShared, fetch, wait: (ms) => new Promise((done) => cx.timer.after(ms, () => done())) });
    // Under `herdr-app check`: draw, but run nothing (no engine, no refresh, no GitHub).
    if (checking()) { this.loading = false; return; }
    this.load(cx, { setup: true });
    cx.timer.every(REFRESH_MS, (cx) => this.load(cx));
    cx.spawn(async (cx) => { await this.update.check(); cx.notify(); });
    cx.spawn(async (cx) => { await this.loadPrograms(); cx.notify(); });
  }

  /**
   * Herdr's own icon and tile for each agent (`knownAgents`, keyed by the
   * program table's key). A Herdr without it, or an agent it doesn't list,
   * gets a lettered tile.
   */
  async loadPrograms() {
    try {
      if (typeof herdr.knownAgents !== "function") return;
      const list = await herdr.knownAgents();
      for (const p of list ?? []) if (p?.key) this.programs[p.key] = p;
    } catch { /* lettered tiles */ }
  }

  program(key) {
    const agent = AGENTS[key];
    for (const name of [key, agent?.bin, ...(agent?.apps ?? [])]) if (name && this.programs[name]?.icon) return this.programs[name];
    return null;
  }

  /** The agent's icon on a tile of its color. */
  agentTile(t, key, size) {
    const p = this.program(key);
    const glyph = Math.round(size * 0.55);
    return div().size(size).flex_none().rounded(Math.round(size * 0.27)).flex().items_center().justify_center()
      .bg(p?.tile ? alpha(p.tile, "2e") : alpha(t.foreground, "1f"))
      .child(p ? (p.tint ? svg(p.icon).size(glyph).text_color(p.color ?? t.foreground) : image(p.icon).w(glyph).h(glyph))
        : div().text_size(Math.round(size * 0.42)).font_semibold().text_color(t.muted)
          .child((AGENTS[key]?.name ?? key ?? "?").slice(0, 1).toUpperCase()));
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

  /**
   * Writes the record a Claude Code session started before Revive was
   * installed never got, as its SessionStart would have (`revive.mjs adopt T`).
   * The engine says why when it won't; the list then shows it as remembered.
   */
  remember(entry, cx) {
    if (this.busy || !entry?.unrecorded || !entry.rememberable) return;
    this.busy = true;
    this.note = null;
    cx.notify();
    cx.spawn(async (cx) => {
      const r = await engine(["adopt", entry.address]);
      this.busy = false;
      if (!r.ok) this.note = { level: "error", text: r.error };
      this.load(cx);
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

  /** omp only: resume with --restore, which goes on with the unfinished turn. */
  setRestore(entry, on, cx) {
    this.note = null;
    cx.spawn(async (cx) => {
      const r = await engine(["restore", entry.address, on ? "on" : "off"]);
      if (!r.ok) this.note = { level: "error", text: r.error };
      else if (on) this.note = { level: "info", text: "omp will go on with its unfinished turn when this session comes back, and may run its tools again." };
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

  header(t) {
    return h_flex().flex_none().items_center().gap(12).px(20).pt(18).pb(16)
      .child(div().size(32).flex_none().rounded(9).bg(alpha(t.accent, "29")).flex().items_center().justify_center()
        .child(icon("logo", 18, t.accent)))
      .child(v_flex().flex_1().min_w(0).gap(2)
        .child(h_flex().gap(8).items_center()
          .child(div().text_size(15).font_semibold().text_color(t.foreground).child("Revive"))
          .child(div().px(6).rounded(6).bg(t.raised).border_1().border_color(t.border)
            .font_family(MONO).text_size(10.5).text_color(t.muted).child(VERSION)))
        .child(div().text_size(12).text_color(t.dim).child("Agent sessions, remembered on their terminals")))
      .child(button(t, "close", "Esc", () => this.close(), { kind: "outline", small: true }));
  }

  /**
   * The sessions Revive brought back lately (after a reboot or a core
   * restart, or a Resume here), so what it did doesn't go unseen. Dismiss
   * hides that batch for good.
   */
  cameBackStrip(t, back) {
    const n = back.list.length;
    const named = back.list.slice(0, 3).map((e) => `${AGENTS[e.rec.agent]?.name ?? e.rec.agent} in ${e.where ?? e.address}`);
    const more = n > 3 ? ` and ${n - 3} more` : "";
    return h_flex().flex_none().mx(20).mb(14).px(14).py(12).gap(12).items_center().rounded(12)
      .bg(alpha(t.ansi2, "1f")).border_1().border_color(alpha(t.ansi2, "59"))
      .child(div().size(28).flex_none().rounded(8).bg(alpha(t.ansi2, "24")).flex().items_center().justify_center()
        .child(icon("logo", 15, t.ansi2)))
      .child(v_flex().flex_1().min_w(0).gap(2)
        .child(h_flex().gap(8).items_center()
          .child(div().text_size(13).font_semibold().text_color(t.foreground)
            .child(n === 1 ? "1 session came back" : `${n} sessions came back`))
          .child(div().text_size(12).text_color(t.dim).child(ago(back.latest))))
        .child(div().truncate().text_size(11.5).text_color(t.muted).child(named.join(", ") + more)))
      .child(link(t, "came-back-dismiss", "Dismiss", (_e, cx) => { setShared(CAME_BACK_SEEN, back.latest); cx.notify(); }));
  }

  /**
   * A newer release, when there is one: what to ask the agent, since an added
   * mod can't update itself (see lib/update.js).
   */
  updateStrip(t, latest) {
    return v_flex().flex_none().mx(20).mb(14).px(14).py(12).gap(10).rounded(12)
      .bg(alpha(t.accent, "12")).border_1().border_color(alpha(t.accent, "47"))
      .child(h_flex().gap(10).items_center()
        .child(icon("download", 16, t.accent))
        .child(div().text_size(13).font_semibold().text_color(t.foreground).child(`Revive ${latest.tag} is out`))
        .child(div().text_size(12).text_color(t.dim).child(`you have ${VERSION}`))
        .child(div().flex_1())
        .child(link(t, "update-stop", "Stop checking", (_e, cx) => { this.update.stop(); cx.notify(); })))
      .child(h_flex().gap(8).items_center().px(10).py(8).rounded(8).bg(t.background).border_1().border_color(t.border)
        .child(div().flex_1().min_w(0).truncate().font_family(MONO).text_size(11).text_color(t.foreground).child(PROMPT))
        .child(button(t, "update-copy", "Copy", (_e, cx) => {
          cx.write_to_clipboard(PROMPT);
          notify({ title: "Copied", body: PROMPT, level: "success", timeout: 2500 });
        }, { kind: "solid", icon: "copy", small: true })))
      .child(h_flex().gap(14).items_center()
        .child(div().text_size(11.5).text_color(t.dim).child("Paste it to your agent."))
        .child(div().flex_1())
        .child(link(t, "update-notes", "What changed", (_e, cx) => cx.open_url(latest.url ?? RELEASES), t.accent))
        .child(link(t, "update-later", "Later", (_e, cx) => { this.update.dismiss(latest.tag); cx.notify(); }, t.muted)));
  }

  /** A dashed card for a terminal with nothing to show. */
  emptyCard(t, title, text) {
    return h_flex().gap(12).items_center().px(16).py(14).rounded(12).border_1().border_dashed().border_color(t.border)
      .child(icon("terminal", 18, t.dim))
      .child(v_flex().gap(2).min_w(0)
        .child(div().text_size(12.5).text_color(t.muted).child(title))
        .when(Boolean(text), (el) => el.child(div().text_size(11.5).text_color(t.dim).child(text))));
  }

  focusedCard(t) {
    const entry = this.current();
    if (this.focus?.includes("/")) return this.emptyCard(t, "The focused terminal is on another machine", "Revive works on this computer for now.");
    if (!entry?.rec && AGENTS[entry?.live]) return this.unrecordedCard(t, entry);
    if (!entry?.rec) {
      return this.loading ? this.emptyCard(t, busyLabel(t, "Looking…"), null)
        : this.emptyCard(t, "No agent in this terminal", "Start one here and Revive remembers it from its first message.");
    }
    const { rec, state } = entry;
    const agent = AGENTS[rec.agent];
    const running = state === "running";
    const forks = canFork(rec.agent);
    const blocked = running && forks ? unforkable(rec) : null;
    const empty = running && (entry.forkable === false || Boolean(blocked));
    // Resume by hand that the engine would refuse: why, and what to run instead.
    const stuck = NEEDS_YOU.has(state) ? unresumable(rec) : null;
    const byHand = stuck?.needs ? needsCommand(rec, { dialect: onWindows() ? "pwsh" : "posix" }) : null;
    // Started before Revive was installed, and a Claude Code session (the
    // engine says): Remember records it. No message yet: nothing to remember.
    const remembers = Boolean(entry.unrecorded) && entry.rememberable != null;
    const rememberable = remembers && entry.rememberable && entry.forkable !== false;
    const notes = [
      remembers ? "Started before Revive was installed: it can be forked, but won't come back by itself until you remember it."
        : entry.unrecorded ? (forks ? "Started before Revive was installed: it can be forked, but won't come back by itself."
          : "Started before Revive was installed: it won't come back by itself.") : null,
      running && !forks ? `${agent?.name ?? rec.agent} can't fork a session.` : null,
      forks && empty ? blocked ?? (remembers ? NO_MESSAGE_UNRECORDED : NO_MESSAGE) : null,
      remembers && !entry.rememberable && entry.forkable !== false ? `Revive can't remember it: ${entry.rememberWhy}.` : null,
      stuck?.folder ? `Its folder ${tilde(stuck.folder)} is missing, not yours, or writable by others, so it isn't resumed here.` : null,
      stuck?.needs ? `It ran with ${stuck.needs.join(", ")}, which Revive doesn't carry. ${stuck.needs.some((n) => !n.startsWith("-")) ? "Set it in a shell" : "Fill in the folder"} and run:` : null,
    ].filter(Boolean);
    return v_flex().gap(14).p(16).rounded(12).bg(t.raised).border_1().border_color(t.border)
      .child(h_flex().gap(12).items_start()
        .child(this.agentTile(t, rec.agent, 38))
        .child(v_flex().flex_1().min_w(0).gap(4)
          .child(h_flex().gap(8).items_center()
            .child(div().text_size(14).font_semibold().text_color(t.foreground).child(agent?.name ?? rec.agent))
            .child(div().text_size(11).font_family(MONO).text_color(t.dim).child(shortId(rec.session))))
          .when(Boolean(rec.cwd), (el) => el.child(h_flex().gap(6).items_center().min_w(0)
            .child(icon("folder", 13, t.dim))
            .child(div().truncate().text_size(12).text_color(t.muted).child(tilde(rec.cwd))))))
        .child(status(t, state)))
      .when(Boolean(rec.flags?.length), (el) => el.child(flagChips(t, rec.flags)))
      .when(notes.length > 0, (el) => el.child(v_flex().gap(4).children(notes.map((n) => hint(t, n)))))
      .when(Boolean(byHand), (el) => el.child(div().px(10).py(8).rounded(8).bg(t.background).border_1().border_color(t.border)
        .font_family(MONO).text_size(10.5).text_color(t.foreground).child(byHand)))
      .when((running && forks) || NEEDS_YOU.has(state), (el) => el.child(h_flex().gap(8).flex_wrap()
        .when(running && forks, (row) => row
          .child(button(t, "fork-right", "Fork right", () => this.fork(entry, "right"), { kind: "solid", icon: "fork-right", hint: "F", disabled: empty }))
          .child(button(t, "fork-down", "Below", () => this.fork(entry, "down"), { icon: "fork-down", hint: "D", disabled: empty }))
          .child(button(t, "fork-tab", "New tab", () => this.fork(entry, "tab"), { icon: "fork-tab", hint: "T", disabled: empty })))
        .when(remembers, (row) => row
          .child(button(t, "remember-here", this.busy ? "Remembering…" : "Remember", (_e, cx) => this.remember(entry, cx), { disabled: this.busy || !rememberable })))
        .when(NEEDS_YOU.has(state), (row) => row
          .child(button(t, "resume-here", this.busy ? busyLabel(t, "Resuming…") : "Resume", (_e, cx) => this.resume(entry, cx), { kind: "solid", hint: "↵", disabled: this.busy || Boolean(stuck) }))
          .when(Boolean(byHand), (r) => r.child(button(t, "copy-command", "Copy command", (_e, cx) => {
            cx.write_to_clipboard(byHand);
            notify({ title: "Copied", body: byHand, level: "success", timeout: 2500 });
          }, { icon: "copy" }))))));
  }

  /**
   * An agent running in the focused terminal that Revive has no record of. A
   * Codex or Copilot CLI session is recorded at its first message. A Codex one
   * is never recorded while Codex's shared background server runs it: that
   * server, not the terminal, runs the hooks, so they can't tell which
   * terminal the session is in.
   */
  unrecordedCard(t, entry) {
    const agent = AGENTS[entry.live];
    const why = entry.live === "codex"
      ? "Revive has no record of this session, so it can't be forked or brought back. Codex records it at its first message, and not at all while its shared background server runs it (daemon_auto_start)."
      : entry.live === "copilot"
        ? "Revive has no record of this session, so it can't be brought back. Copilot CLI records it at its first message."
        : "Revive has no record of this session, so it can't be forked or brought back. It is recorded when it starts once Revive is installed.";
    return v_flex().gap(12).p(16).rounded(12).bg(t.raised).border_1().border_color(t.border)
      .child(h_flex().gap(12).items_start()
        .child(this.agentTile(t, entry.live, 38))
        .child(v_flex().flex_1().min_w(0).gap(4)
          .child(div().text_size(14).font_semibold().text_color(t.foreground).child(agent.name))
          .when(Boolean(entry.folder), (el) => el.child(h_flex().gap(6).items_center().min_w(0)
            .child(icon("folder", 13, t.dim))
            .child(div().truncate().text_size(12).text_color(t.muted).child(tilde(entry.folder))))))
        .child(status(t, "running")))
      .child(hint(t, why));
  }

  row(t, entry, i, continueCol = false) {
    const { rec, state } = entry;
    const agent = AGENTS[rec.agent];
    const needs = NEEDS_YOU.has(state);
    return h_flex().id(`row-${i}`).h(needs ? 54 : 50).px(12).gap(12).items_center().rounded(10).cursor_pointer()
      .when(needs, (el) => el.bg(t.raised).border_1().border_color(t.border))
      .hover((s) => s.bg(t.hover))
      .on_click(() => { this.close(); run("pane.focus", { terminal: entry.address }); })
      .child(this.agentTile(t, rec.agent, 30))
      .child(v_flex().flex_1().min_w(0).gap(2)
        .child(h_flex().gap(8).items_center()
          .child(div().text_size(13).font_medium().text_color(t.foreground).child(agent?.name ?? rec.agent))
          .child(div().text_size(10.5).font_family(MONO).text_color(t.dim).child(shortId(rec.session))))
        .child(div().truncate().text_size(11.5).text_color(t.dim)
          .child([entry.where ?? entry.address, rec.resumed ? `resumed ${ago(rec.resumed)}` : null].filter(Boolean).join(" · "))))
      .child(status(t, state))
      .when(!entry.unrecorded && canRestore(rec.agent), (el) => el.child(h_flex().flex_none().gap(8).items_center()
        .child(div().text_size(11.5).text_color(t.dim).child("Continue"))
        .child(toggle(t, `restore-${i}`, Boolean(rec.restore), (_e, cx) => this.setRestore(entry, !rec.restore, cx)))))
      .when(continueCol && !entry.unrecorded && !canRestore(rec.agent), (el) => el.child(h_flex().flex_none().gap(8).items_center().invisible()
        .child(div().text_size(11.5).child("Continue"))
        .child(div().flex_none().w(32).h(18))))
      .when(!entry.unrecorded, (el) => el.child(h_flex().flex_none().gap(8).items_center()
        .child(div().text_size(11.5).text_color(t.dim).child("Auto"))
        .child(toggle(t, `auto-${i}`, Boolean(rec.auto), (_e, cx) => this.setAuto(entry, !rec.auto, cx)))))
      .when(Boolean(entry.unrecorded), (el) => el.child(div().flex_none().text_size(11.5).text_color(t.dim).child("not remembered")))
      .when(Boolean(entry.unrecorded) && Boolean(entry.rememberable), (el) => el
        .child(button(t, `remember-${i}`, "Remember", (_e, cx) => this.remember(entry, cx), { kind: "ghost", small: true, disabled: this.busy })))
      .when(needs, (el) => el.child(button(t, `resume-${i}`, "Resume", (_e, cx) => this.resume(entry, cx), { kind: "solid", small: true, hint: null, disabled: this.busy || Boolean(unresumable(rec)) })));
  }

  /** Nothing remembered anywhere and no agent in the focused terminal. */
  emptyState(t) {
    const s = this.setup ?? {};
    const installed = Object.keys(AGENTS).filter((k) => s[k] !== null && s[k] !== undefined);
    const shown = installed.slice(0, 4);
    return v_flex().items_center().gap(14).px(36).py(28)
      .child(div().size(52).rounded(16).bg(t.raised).border_1().border_color(t.border).flex().items_center().justify_center()
        .child(icon("logo", 24, t.muted)))
      .child(v_flex().items_center().gap(6)
        .child(div().text_size(14).font_semibold().text_color(t.foreground).child("No sessions remembered yet"))
        .child(div().text_size(12.5).line_height(1.5).text_color(t.dim).text_center()
          .child("Start an agent in a Herdr terminal. Revive remembers its session at the first message and brings it back after a reboot or a core restart.")))
      .when(shown.length > 0, (el) => el.child(h_flex().gap(8).items_center().flex_wrap().justify_center()
        .children(shown.map((k) => h_flex().gap(6).items_center().h(26).px(9).rounded(13).bg(t.raised).border_1().border_color(t.border)
          .child(this.agentTile(t, k, 16)).child(div().text_size(11.5).text_color(t.muted).child(AGENTS[k].name))))
        .when(installed.length > shown.length, (row) => row.child(div().text_size(11.5).text_color(t.dim).child(`+${installed.length - shown.length} more`)))));
  }

  /**
   * What's set up: one line when all is, else what's missing and Install.
   * Keys on the right, unless there's nothing they could act on (`showKeys`).
   */
  footer(t, showKeys = true) {
    const s = this.setup;
    const keys = h_flex().flex_none().gap(10).items_center().text_size(11).text_color(t.dim)
      .child(h_flex().gap(4).items_center().child(kbd(t, "↵")).child("resume"))
      .child(h_flex().gap(4).items_center().child(kbd(t, "F")).child("fork"))
      .child(h_flex().gap(4).items_center().child(kbd(t, "R")).child("refresh"));
    const bar = (el) => el.flex_none().gap(12).items_center().px(20).border_t_1();
    if (!s) return bar(h_flex()).py(11).border_color(t.border).bg(t.chrome).child(div().flex_1()).when(showKeys, (el) => el.child(keys));
    const shells = Object.entries(s.shell ?? {}).filter(([, on]) => on).map(([name]) => name);
    // One entry per agent: true, false, or null when that agent isn't installed.
    const agents = Object.keys(AGENTS).filter((k) => s[k] !== null && s[k] !== undefined);
    const missing = [
      ...agents.filter((k) => !s[k]).map((k) => (k === "pi" || k === "omp" ? `${AGENTS[k].name} extension missing` : k === "muse" ? `${AGENTS[k].name} plugin missing` : `${AGENTS[k].name} hooks missing`)),
      ...(shells.length ? [] : ["shell block missing"]),
    ];
    if (!missing.length) {
      return bar(h_flex()).py(11).border_color(t.border).bg(t.chrome)
        .child(h_flex().flex_1().min_w(0).gap(6).items_center()
          .child(icon("check", 13, t.ansi2))
          .child(div().truncate().text_size(11.5).text_color(t.muted)
            .child(`Ready: ${[...agents.map((k) => AGENTS[k].name), ...shells].join(", ")}`)))
        .when(showKeys, (el) => el.child(keys));
    }
    return bar(h_flex()).py(12).border_color(alpha(t.ansi3, "40")).bg(alpha(t.ansi3, "12"))
      .child(icon("alert", 16, t.ansi3))
      .child(v_flex().flex_1().min_w(0).gap(1)
        .child(div().text_size(12).font_medium().text_color(t.foreground).child("Setup isn't complete"))
        .child(div().truncate().text_size(11.5).text_color(t.muted).child(missing.join(" · "))))
      .child(button(t, "install", this.busy ? busyLabel(t, "Installing…") : "Install", (_e, cx) => this.install(cx), { kind: "solid", small: true, disabled: this.busy }));
  }

  render(cx) {
    const t = theme();
    const others = this.entries.filter((e) => e.rec && e.address !== this.focus);
    const needs = others.filter((e) => NEEDS_YOU.has(e.state));
    const rest = others.filter((e) => !NEEDS_YOU.has(e.state));
    const mine = this.current();
    const nothing = !this.loading && !others.length && !mine?.rec && !AGENTS[mine?.live] && !this.focus?.includes("/");
    const latest = this.update?.available() ?? null;
    const back = cameBack(this.entries, { seen: shared(CAME_BACK_SEEN) });
    const listH = listMaxH((this.note ? NOTE_H : 0) + (latest ? UPDATE_H : 0) + (back.list.length ? CAME_BACK_H : 0));
    // When an omp row shows Continue, the other rows keep its room, so the states line up.
    const continueCol = [...needs, ...rest].some((e) => !e.unrecorded && canRestore(e.rec.agent));
    return v_flex().id("revive").track_focus(this.handle).on_key_down((e, cx) => this.key(e, cx))
      .w_full().bg(t.popover)
      .child(this.header(t))
      .when(back.list.length > 0, (el) => el.child(this.cameBackStrip(t, back)))
      .when(Boolean(latest), (el) => el.child(this.updateStrip(t, latest)))
      .child(div().flex_none().h(1).bg(t.border))
      .child(div().id("revive-scroll").when(listH !== null, (el) => el.max_h(listH)).overflow_y_scrollbar()
        .when(nothing, (el) => el.child(this.emptyState(t)))
        .when(!nothing, (el) => el.child(v_flex().px(20).pt(2).pb(14)
          .child(section(t, "FOCUSED TERMINAL"))
          .child(this.focusedCard(t))
          .when(needs.length > 0, (b) => b.child(section(t, "NEEDS YOU", needs.length, t.ansi3))
            .child(v_flex().gap(4).children(needs.map((e, i) => this.row(t, e, `n${i}`, continueCol)))))
          .when(rest.length > 0, (b) => b.child(section(t, "OTHER SESSIONS"))
            .child(v_flex().gap(2).children(rest.map((e, i) => this.row(t, e, `r${i}`, continueCol))))))))
      .when(Boolean(this.note), (el) => el.child(div().flex_none().mx(20).mb(12).px(10).py(8).rounded(8).text_size(11.5)
        .bg(alpha(this.note.level === "error" ? t.ansi1 : t.foreground, "14"))
        .text_color(this.note.level === "error" ? t.ansi1 : t.muted).child(this.note.text)))
      .child(this.footer(t, !nothing));
  }
}
