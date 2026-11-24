// Recall: an IntelliJ-style "Recent" switcher for the Herdr app.
//
// One mod, two roles, told apart by props().role:
// - "tracker": an invisible kept window. It records every focus change into
//   the recency history (shared "recall.history") and answers the recall.*
//   key commands: open the navigator on a category, or jump back.
// - the navigator (any other props): the dialog people see.
// Opening the navigator (re)opens the tracker, so one open starts tracking;
// `keep` brings the tracker back on every start.
//
// The top of a mod's file runs once and is shared by its copies; each copy
// has its own instance. The dialog and the tracker are separate instances,
// and a crash loses module state, so the open navigator still announces
// itself in shared "recall.open" with a heartbeat: a second open within a
// beat is a toggle, and a crash leaves nothing stuck.

import { View, div } from "gpui-kit";
import { v_flex, InputState, VirtualListScrollHandle } from "gpui-base";
import {
  spaces, panes, agents, terminals, focused, theme, settings, fonts, props, run, shared, setShared,
  openOverlay, closeOverlay, nextCommand, home, appHome, readTextFile, exec, hc,
} from "herdr";
import * as mru from "./lib/mru.js";
import { listView } from "./lib/listview.js";
import { actionFor, isPrintable, normalizeKey, normalizeLook, parseConfig, parseOpenCommand } from "./lib/config.js";
import { createCluesRefresh } from "./lib/clues-refresh.js";
import { parseRevParse, resolveWorktrees } from "./lib/worktrees.js";
import { columnNeeds, dragWidth, drawnListWidth, fitColumns, headWidths, loadKept, newMeasure, shownColumns } from "./lib/columns.js";
import { DESIGN_TEXT, pickFont, textScale } from "./lib/look.js";
import { metricsFor } from "./lib/textwidth.js";
import { isCurrentTracker, trackerWindow } from "./lib/tracker.js";
import { navigator } from "./ui.js";

const MOD = "recall";
const HISTORY = "recall.history";
const OPEN = "recall.open";
const LAST = "recall.last";
const KEPT = "recall.widths";
const LOOK = "recall.look";
const BEAT = 1500;
const FRESH = 4000;
// The git probe that groups worktrees is given this long (Herdr's default is 30 s), a budget of its own.
const WORKTREE_PROBE_TIMEOUT = 5000;
const TRACKER = trackerWindow(MOD);
const DIALOG = { kind: "dialog", width: 0.74, height: 0.7 };

const AGENT_SORTS = ["mru", "priority", "grouped"];
const KEY_CONTEXT = "RecallNavigator";
const KEY_ACTIONS = {
  next_category: "recall::next_category",
  previous_category: "recall::previous_category",
  dismiss: "recall::dismiss",
  force_quit: "recall::force_quit",
};

function fresh(open) {
  return open && typeof open.at === "number" && Date.now() - open.at < FRESH;
}

export default class Recall extends View {
  init(_props, cx) {
    const p = props() ?? {};
    this.role = p.role === "tracker" ? "tracker" : "navigator";
    if (this.role === "tracker") return this.initTracker(p, cx);
    return this.initNavigator(p, cx);
  }

  async close() {
    if (this.role !== "navigator") return;
    if (shared(OPEN)?.id === this.overlayId) setShared(OPEN, null);
    if (this.category) setShared(LAST, this.category);
  }

  render(cx) {
    if (this.role === "tracker") return this.renderTracker();
    if (this.role === "closing") return div();
    return this.renderNavigator(cx);
  }

  // ── Tracker ────────────────────────────────────────────────────────────

  initTracker(p, cx) {
    this.sig = null;
    // Herdr reopens a kept window as it was last opened. One kept at another
    // size gives way to one at this size, which takes its place.
    if (!isCurrentTracker(p)) {
      openOverlay(TRACKER);
      return;
    }
    cx.spawn(async () => {
      for (;;) this.trackerCommand(await nextCommand());
    });
  }

  renderTracker() {
    const f = focused();
    if (f?.space && f?.tab) {
      const agent = agents().find((a) => a.focused)?.address ?? null;
      const sig = `${f.space}|${f.tab}|${f.pane}|${agent}`;
      if (sig !== this.sig) {
        this.sig = sig;
        const before = mru.load(shared(HISTORY));
        const after = mru.record(before, { space: f.space, tab: f.tab, pane: f.pane, agent }, Date.now());
        if (after !== before) setShared(HISTORY, after);
      }
    }
    return div().size(0);
  }

  trackerCommand(command) {
    if (command === "open" || command.startsWith("open-")) {
      if (fresh(shared(OPEN))) return; // the open navigator takes it
      const { category, sort } = parseOpenCommand(command);
      openOverlay({ ...DIALOG, mod: MOD, props: { category, agentSort: sort, from: "tracker" } });
    } else if (command.startsWith("previous-")) {
      this.jumpBack(command.slice("previous-".length));
    }
  }

  /**
   * Back to the most recently focused tab, pane, agent or space that still
   * exists and isn't where you are, across spaces.
   */
  jumpBack(kind) {
    const history = mru.load(shared(HISTORY));
    const f = focused();
    if (kind === "tab") {
      const live = new Set(spaces().flatMap((s) => s.tabs.map((t) => t.id)));
      const e = mru.previous(history, "tab", { current: f?.tab, live });
      if (e) run("tab.select", { id: e.id });
    } else if (kind === "pane") {
      const all = panes();
      const e = mru.previous(history, "pane", { current: f?.pane, live: new Set(all.map((p) => p.pane)) });
      if (!e) return;
      run("tab.select", { id: all.find((p) => p.pane === e.id).tab });
      run("pane.focus", { pane: e.id });
    } else if (kind === "agent") {
      const list = agents();
      const current = list.find((a) => a.focused)?.address;
      const e = mru.previous(history, "agent", { current, live: new Set(list.map((a) => a.address)) });
      if (e) run("agent.focus", { terminal: e.id });
    } else if (kind === "space") {
      const e = mru.previous(history, "space", { current: f?.space, live: new Set(spaces().map((s) => s.id)) });
      if (e) run("space.select", { id: e.id });
    }
  }

  // ── Navigator: lifecycle ───────────────────────────────────────────────

  initNavigator(p, cx) {
    this.overlayId = p.overlay;
    const open = shared(OPEN);
    if (fresh(open) && open.id !== this.overlayId) {
      // Pressed again while open: close both.
      this.role = "closing";
      setShared(OPEN, null);
      closeOverlay(open.id);
      closeOverlay(this.overlayId);
      return;
    }
    this.beat();
    cx.timer.every(BEAT, () => this.beat());
    if (p.from !== "tracker") openOverlay(TRACKER);

    const { config } = parseConfig(null);
    this.applyConfig(config, cx);
    // recall.json is read after the first frame: until then, draw in the
    // font and size it asked for last time, so the dialog doesn't jump.
    this.applyLook(normalizeLook(shared(LOOK)));
    this.scale = 1;
    this.requested = p.category ?? null;
    this.category = this.startCategory();
    this.agentSort = p.agentSort ?? "mru";
    // kept: the widths the person dragged. widths and heads: what each
    // column is drawn at and how wide its head is, worked out on every
    // frame from what the category lists.
    this.kept = loadKept(shared(KEPT));
    this.widths = {};
    this.heads = {};
    this.resizing = null;
    // How wide Herdr laid the list out, in the window's px, and at what
    // window width, zoom and scale; null until it has, after the first frame.
    this.measure = null;
    this.query = "";
    this.at = null;
    this.follow = true;
    this.done = false;
    this.worktrees = null;
    this.refresh = createCluesRefresh({ exec, hc, terminalPanes: () => this.clueTargets() });
    this.data = this.refresh.data;
    this.handle = cx.focus_handle();
    this.scroll = VirtualListScrollHandle.new();
    this.input = InputState.new({ placeholder: "Type to search" });
    this.input.on("change", (_e, cx) => {
      const value = this.input.value();
      if (value === this.query) return;
      this.query = value;
      this.at = null;
      this.follow = true;
      cx.notify();
    });
    this.input.on("submit", (_e, cx) => {
      this.open(this.rows?.[this.at]?.item);
      cx.notify();
    });
    this.focusForMode();
    cx.timer.after(250, () => this.focusForMode());

    cx.spawn(async (cx) => {
      const text = await readTextFile(`${appHome()}/recall.json`).catch(() => null);
      const { config, error } = parseConfig(text);
      this.configError = error;
      this.applyConfig(config, cx);
      this.applyLook(config);
      this.keepLook(config);
      this.category = this.startCategory();
      this.at = null;
      this.focusForMode();
      cx.notify();
    });
    cx.spawn(async (cx) => {
      for (;;) {
        this.navigatorCommand(await nextCommand());
        cx.notify();
      }
    });
    cx.spawn(async (cx) => {
      this.worktrees = await this.probeWorktrees();
      cx.notify();
    });
    cx.timer.every(1000, (cx) => this.refreshClues(cx));
    this.refreshClues(cx);
  }

  beat() {
    setShared(OPEN, { id: this.overlayId ?? true, at: Date.now() });
  }

  applyConfig(config, cx) {
    this.categories = config.categories;
    this.keys = config.keys;
    this.modal = config.modal;
    this.mode = this.modal ? "navigation" : "type";
    this.bindKeys(cx);
  }

  /**
   * The font and text size recall.json asks for; without them the dialog
   * follows Herdr's. fonts() lists every family on the machine, so it is
   * asked only when a font is named.
   */
  applyLook({ font, fontSize }) {
    this.fontSize = fontSize;
    this.font = font ? pickFont(font, fonts()) : null;
  }

  /** Keeps what recall.json asks for, in its own spelling, for the next open's first frame. */
  keepLook({ font, fontSize }) {
    const look = font || fontSize ? { font, font_size: fontSize } : null;
    if (JSON.stringify(shared(LOOK) ?? null) !== JSON.stringify(look)) setShared(LOOK, look);
  }

  /**
   * Category and close keys as bindings in this dialog's key context, so
   * they beat the search field's own bindings and Tab focus traversal,
   * which take a key before any on_key_down sees it. Printable keys stay
   * with on_key_down: whether they type or move depends on the mode.
   */
  bindKeys(cx) {
    const bindings = [];
    for (const [action, name] of Object.entries(KEY_ACTIONS)) {
      for (const keystroke of this.keys[action]) {
        if (isPrintable(keystroke)) continue;
        for (const context of [KEY_CONTEXT, `${KEY_CONTEXT} > Input`]) bindings.push({ keystroke, action: name, context });
      }
    }
    try {
      cx.bind_keys(bindings);
    } catch {
      // A keystroke GPUI rejects: on_key_down still handles the rest.
    }
  }

  /** The asked-for category, else the last one used, else the first configured. */
  startCategory() {
    for (const c of [this.requested, shared(LAST)]) if (c && this.categories.includes(c)) return c;
    return this.categories[0];
  }

  focusForMode() {
    if (this.mode === "navigation") this.handle?.focus();
    else this.input?.focus();
  }

  dismiss() {
    if (this.done) return;
    this.done = true;
    closeOverlay(this.overlayId);
  }

  open(item) {
    if (!item || this.done) return;
    if (item.kind === "to-clues") return this.switchTo("clues"); // the query stays in the field
    if (!item.actions?.length) return this.dismiss();
    this.dismiss();
    for (const [name, args] of item.actions) run(name, args);
  }

  navigatorCommand(command) {
    if (command !== "open" && !command.startsWith("open-")) return;
    const { category, sort } = parseOpenCommand(command);
    const target = category ?? this.category;
    const sameSort = !sort || sort === this.agentSort;
    if (target === this.category && sameSort) return this.dismiss();
    if (this.categories.includes(target)) this.switchTo(target, sort);
  }

  // ── Navigator: data ────────────────────────────────────────────────────

  async probeWorktrees() {
    const local = spaces().filter((s) => !s.machine && s.folder);
    const probes = await Promise.all(local.map(async (s) => {
      try {
        const r = await exec("git", ["-C", s.folder, "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir"], { timeout: WORKTREE_PROBE_TIMEOUT });
        const parsed = r.code === 0 ? parseRevParse(r.stdout) : null;
        return parsed ? { id: s.id, name: s.name, branch: s.branch, ...parsed } : null;
      } catch {
        return null;
      }
    }));
    return resolveWorktrees(probes.filter(Boolean));
  }

  /** While Clues shows: ask the refresh to run whatever round is due. */
  refreshClues(cx) {
    if (this.role !== "navigator" || this.category !== "clues" || this.done) return;
    if (!this.refresh.due(Date.now())) return;
    cx.spawn(async (cx) => {
      await this.refresh.run(Date.now(), () => cx.notify());
    });
  }

  clueTargets() {
    return panes().filter((p) => p.terminal);
  }

  snapshot() {
    return {
      spaces: spaces(),
      panes: panes(),
      agents: agents(),
      terminals: terminals(),
      focused: focused(),
      history: mru.load(shared(HISTORY)),
      home: home(),
      worktrees: this.worktrees,
    };
  }

  // ── Navigator: input ───────────────────────────────────────────────────

  switchTo(category, sort) {
    this.category = category;
    if (sort && AGENT_SORTS.includes(sort)) {
      this.agentSort = sort;
    }
    this.at = null;
    this.follow = true;
  }

  cycleCategory(step) {
    const i = Math.max(0, this.categories.indexOf(this.category));
    this.switchTo(this.categories[(i + step + this.categories.length) % this.categories.length]);
  }

  move(step) {
    const n = this.rows?.length ?? 0;
    if (!n) return;
    this.auto = false;
    this.at = ((this.at ?? 0) + step + n) % n;
    this.follow = true;
  }

  clearQuery() {
    this.input.set_value("");
    this.query = "";
    this.at = null;
  }

  /** Esc: leave the filter, then clear the query, then close. */
  backOut() {
    if (this.mode === "filtering") {
      this.mode = "navigation";
      this.focusForMode();
    } else if (this.query) this.clearQuery();
    else this.dismiss();
  }

  onKey(e, cx) {
    const k = normalizeKey(e.keystroke) ?? e.keystroke;
    const typing = this.mode === "type" || this.mode === "filtering";
    const printable = isPrintable(k);

    if (k === "escape") this.backOut();
    else if (this.mode === "filtering" && printable) return; // the input types it
    else {
      const action = actionFor(this.keys, k);
      if (action === "dismiss") this.backOut();
      else if (action === "force_quit") this.dismiss();
      else if (action === "select") this.open(this.rows?.[this.at]?.item);
      else if (action === "move_up") this.move(-1);
      else if (action === "move_down") this.move(1);
      else if (action === "next_category") this.cycleCategory(1);
      else if (action === "previous_category") this.cycleCategory(-1);
      else if (action === "backspace") {
        if (typing) return; // the input deletes it
        this.input.set_value(this.query.slice(0, -1));
        this.query = this.input.value();
        this.at = null;
      } else if (this.mode === "navigation" && k === "/") {
        this.mode = "filtering";
        this.focusForMode();
      } else if (this.mode === "navigation" && k === "j") this.move(1);
      else if (this.mode === "navigation" && k === "k") this.move(-1);
      else if (this.mode === "navigation" && k === "h") this.cycleCategory(-1);
      else if (this.mode === "navigation" && k === "l") this.cycleCategory(1);
      else if (k === "ctrl-s" && this.category === "agents") this.cycleSort();
      else if (this.mode === "navigation" && printable) {} // swallowed: navigation types nothing
      else return;
    }
    cx.stop_propagation();
    cx.notify();
  }

  cycleSort() {
    this.agentSort = AGENT_SORTS[(AGENT_SORTS.indexOf(this.agentSort) + 1) % AGENT_SORTS.length];
    this.at = null;
    this.follow = true;
  }

  /**
   * A press on a column's left edge starts dragging it, from the width it
   * is drawn at; a double-click lets it fit its content again.
   */
  startResize(column, e) {
    if (e.click_count >= 2) {
      this.resizing = null;
      const { [column]: _dropped, ...kept } = this.kept;
      this.kept = kept;
      this.storeKept();
    } else this.resizing = { column, x: e.position.x, width: this.widths[column] };
  }

  /**
   * The pointer moved while resizing: true when the column's kept width
   * changed. A press that hasn't moved sideways is no drag, so it leaves
   * the column fitting.
   */
  resizeTo(x) {
    const r = this.resizing;
    if (!r || x === r.x) return false;
    const width = dragWidth(r.width, x - r.x, this.scale, this.heads[r.column]);
    if (width === this.kept[r.column]) return false;
    this.kept = { ...this.kept, [r.column]: width };
    return true;
  }

  /** Released, or the pointer left the dialog: keep the dragged widths for next time. */
  endResize() {
    if (!this.resizing) return false;
    this.resizing = null;
    this.storeKept();
    return true;
  }

  /** Stores the dragged widths; nothing dragged stores nothing. */
  storeKept() {
    setShared(KEPT, Object.keys(this.kept).length ? this.kept : null);
  }

  /** What the list is laid out at now, besides its own width. */
  layoutNow() {
    return { windowWidth: window.viewport_size()?.width, zoom: settings()?.zoom, scale: this.scale };
  }

  /** Herdr laid the list out `width` px wide, in the window's px: true when the dialog should draw again. */
  listMeasured(width) {
    const measure = newMeasure(this.measure, width, this.layoutNow());
    if (!measure) return false;
    this.measure = measure;
    return true;
  }

  /**
   * The list's width as designed: as Herdr last measured it, or, in the
   * first frame or right after the window, the zoom or the scale changed,
   * worked out from the window's width.
   */
  listWidth() {
    return drawnListWidth({ measure: this.measure, ...this.layoutNow(), share: DIALOG.width });
  }

  // ── Navigator: view ────────────────────────────────────────────────────

  renderNavigator() {
    const t = theme();
    const view = listView(this.category, this.snapshot(), this.query, { agentSort: this.agentSort, clueData: this.data, cluesAvailable: this.categories.includes("clues") });
    this.rows = view.rows;

    // Open on the row listView picks (the one before where you are, as
    // IntelliJ's Recent Files does). Until the person moves, keep
    // re-aiming: focus can settle after the first frame.
    if (this.at === null || this.auto) {
      this.auto = true;
      this.at = view.selected;
      this.follow = true;
    }
    this.at = Math.max(0, Math.min(this.at, this.rows.length - 1));
    if (this.follow && this.rows.length) {
      this.scroll.scroll_to_item(this.at, "center");
      this.follow = false;
    }
    const loading = this.category === "clues" && this.clueTargets().length > 0 && !this.data.paneState.size;
    // Herdr's interface text size, as settings() reports it (13 today; the
    // typings leave its shape open, so textScale takes a missing one as 13).
    // Read on every frame, not kept: a frame drawn after it changes follows it.
    this.scale = textScale(this.fontSize, settings()?.ui_font_size);
    // Each column as wide as what the category lists needs, or as dragged.
    const metrics = metricsFor(this.font ?? settings()?.ui_font_family);
    this.heads = headWidths(this.category, metrics);
    this.widths = fitColumns({
      needs: columnNeeds(view.fitTo, this.heads, metrics),
      heads: this.heads,
      kept: this.kept,
      listWidth: this.listWidth(),
      shown: shownColumns(this.category),
    });

    const act = (fn) => (_e, cx) => { fn(); cx.notify(); };
    return v_flex()
      .id("recall")
      .key_context(KEY_CONTEXT)
      .track_focus(this.handle)
      .size_full()
      .bg(t.popover)
      .text_size(DESIGN_TEXT * this.scale)
      .when(Boolean(this.font), (el) => el.font_family(this.font))
      .text_color(t.foreground)
      .on_action(KEY_ACTIONS.next_category, act(() => this.cycleCategory(1)))
      .on_action(KEY_ACTIONS.previous_category, act(() => this.cycleCategory(-1)))
      .on_action(KEY_ACTIONS.dismiss, act(() => this.backOut()))
      .on_action(KEY_ACTIONS.force_quit, act(() => this.dismiss()))
      .on_key_down((e, cx) => this.onKey(e, cx))
      .child(navigator(this, { view, loading }));
  }
}
