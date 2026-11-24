// Sudoku. Open as a pane: herdr-app do pane.split '{"direction":"right","mod":"sudoku"}'
// Keys: 1-9 fill, 0/backspace/delete clear, arrows or jk move, h h hint (asks first), s step, c check, n new, e enter from paper.
import { View, div, svg } from "gpui-kit";
import { v_flex, h_flex, InputState, Input } from "gpui-base";
import { theme, notify, shared, setShared, home, appHome, exec, writeTextFile, nextCommand, focused, panes } from "herdr";
import { ok, solve, generate, adjustHints, TIERS } from "./solver.js";
import { nextStep, rc, rate, seLabel, PEERS } from "./logic.js";
import { sheetPdf } from "./pdf.js";
import { guidePages, board, legend, markBg, marksOf, cellBg, bars, rankOf } from "./guide.js";

const KEY = "sudoku-v1", LIB = "sudoku.library", PRINT = "sudoku-print";
const LEVELS = Object.keys(TIERS);
const MAX_EXTRA = 40, MIN_EXTRA = -20, EXTRA_STEP = 2;
const TITLE_H = 22; // height of each title line; the side panel is padded by it to line up with the grid
const pad = (n) => String(n).padStart(2, "0");
const today = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const fail = (body) => notify({ level: "error", title: "Sudoku", body });
// "Kids, holiday ,kids" -> ["kids", "holiday"]
const parseTags = (s) => [...new Set(s.split(",").map((x) => x.trim().toLowerCase()).filter(Boolean))];
// The level as bars; puzzles typed in or loaded have no tier, so they say where they came from.
const levelMark = (t, l) => (TIERS[l] ? bars(t, rankOf(l), t.muted) : div().child(l === "custom" ? "from paper" : "saved"));
// Each level's bars beside what it means: the key for every place that shows only bars.
const tierKey = (t) => v_flex().gap(4).children(LEVELS.map((l) => h_flex().gap(8).items_center()
  .child(bars(t, rankOf(l), t.muted)).child(div().text_size(11).text_color(t.dim).child(TIERS[l].about))));
// New puzzles made by node (make.mjs, fast) in the background; hints: digits to add (+) or hide (-)
// afterwards. Each comes back with its level after that (rank) and the actual change (delta).
// If node can't run them, says so and falls back to the built-in pool (rated, shuffled, instant).
async function newPuzzles(level, count, hints = 0) {
  try {
    const r = await exec("node", [`${appHome()}/mods/sudoku/make.mjs`, level, String(count), String(hints)], { timeout: 120000 });
    if (r.code !== 0) throw new Error(r.stderr.trim() || `exit code ${r.code}`);
    const list = JSON.parse(r.stdout), isGrid = (s) => typeof s === "string" && /^\d{81}$/.test(s);
    if (!Array.isArray(list) || list.length !== count || !list.every((x) => isGrid(x.puz) && isGrid(x.sol))) throw new Error("unexpected output");
    return list.map((x) => {
      const puz = [...x.puz].map(Number);
      return { puz, sol: [...x.sol].map(Number), cur: puz.slice(), level, se: +x.se, stuck: !!x.stuck, rank: +x.rank, delta: +x.delta };
    });
  } catch (e) {
    if (Date.now() - warnedAt > 10000) {
      warnedAt = Date.now();
      notify({ level: "warning", title: "Sudoku", body: `Could not make new puzzles with node (${String(e) || "no reason given"}). Using the built-in ones.` });
    }
    return Array.from({ length: count }, () => (hints ? adjustHints(generate(level), hints) : generate(level)));
  }
}
let warnedAt = 0; // one warning, not one per PDF row
const spinner =(t) => svg("mods/workspace-chrome/spinner.svg").size(13).flex_none().text_color(t.working).spin(900);

export default class Sudoku extends View {
  init(_p, cx) {
    this.handle = cx.focus_handle();
    this.sel = 40;
    this.checked = false;
    this.view = "play";
    this.page = 0;
    this.hi = null;
    this.msg = null;
    this.ask = null; // a shortcut waiting for "are you sure": { kind: "hint", cell } or { kind: "solve" }
    this.waiting = false; // Step's explanation is open and not yet acknowledged
    this.pencil = false; // digits go in as pencil marks
    this.undo = [];
    this.width = 0; // the pane's width: the controls sit beside the board when it fits
    try { this.g = JSON.parse(localStorage.getItem(KEY) || "null"); } catch { this.g = null; }
    const g = this.g;
    if (!g || g.cur?.length !== 81 || g.sol?.includes(0) || !g.puz?.some((v) => v)) this.g = generate("beginner");
    if (this.g.se === undefined) Object.assign(this.g, (({ se, stuck }) => ({ se, stuck }))(rate(this.g.puz)));
    try { this.rows = JSON.parse(localStorage.getItem(PRINT) || "null"); } catch { this.rows = null; }
    if (!Array.isArray(this.rows) || this.rows.length !== 3) this.rows = ["easy", "beginner", "medium"];
    // Older saves hold plain level names.
    this.rows = this.rows.map((r) => {
      const level = typeof r === "string" ? r : r?.level;
      return { level: LEVELS.includes(level) ? level : "easy", extra: Math.min(Math.max(+r?.extra || 0, MIN_EXTRA), MAX_EXTRA) };
    });
    this.started = Date.now() - (this.g.elapsed || 0);
    this.input = InputState.new({ placeholder: "e.g. Daily Paper, 2026-11-16, page 34, top left" });
    this.input.on("submit", (_e, cx) => { this.saveDesc(); cx.notify(); });
    this.saveTags = InputState.new({ placeholder: "tags, comma separated (optional)" });
    this.saveTags.on("submit", (_e, cx) => { this.saveDesc(); cx.notify(); });
    this.printTags = InputState.new({ placeholder: "tags for this sheet's puzzles, comma separated (optional)" });
    this.printLabel = InputState.new({ placeholder: "label for this sheet (optional), e.g. weekend for the kids" });
    this.libFilter = null; // { tag } or { sheet }: what the library shows
    cx.timer.every(200, () => this.takeKeyboard());
    cx.timer.every(1000, (cx) => { if (this.view === "play" && !this.g.entry && !this.won()) cx.notify(); });
    // keys.json actions: sudoku.guide, sudoku.library, sudoku.print, sudoku.play, sudoku.next, sudoku.prev, sudoku.step, sudoku.hint, sudoku.solve, sudoku.new, sudoku.pdf
    cx.spawn(async (cx) => {
      for (;;) {
        const c = String(await nextCommand()).replace(/^sudoku\./, ""), last = guidePages().length - 1;
        // Herdr hands this pane the keyboard (focusable in mod.json); without taking it, keys go nowhere.
        if (c === "focus") { if (this.view === "save") this.input.focus(); else this.handle.focus(); }
        else if (["play", "guide", "library", "print"].includes(c)) this.go(c);
        else if (c === "next") this.page = Math.min(this.page + 1, last);
        else if (c === "prev") this.page = Math.max(this.page - 1, 0);
        else if (c === "step") this.step();
        else if (c === "hint") this.hint();
        else if (c === "solve") this.solveAll();
        else if (c === "new") await this.fresh(this.nextLevel(), cx);
        else if (c === "pdf") await this.makePdf(cx);
        cx.notify();
      }
    });
  }

  save() { this.g.elapsed = Date.now() - this.started; localStorage.setItem(KEY, JSON.stringify(this.g)); }
  won() { return this.g.cur.every((v, i) => v === this.g.sol[i]); }
  play(g) {
    this.g = g; this.started = Date.now(); this.checked = false; this.hi = this.msg = null; this.undo = [];
    this.card = this.ask = null; this.waiting = false;
    this.save();
  }

  // Pencil marks: a bitmask per cell (bit v = digit v), saved with the game.
  marks() { return (this.g.marks ??= Array(81).fill(0)); }
  // Undo keeps the last 200 changes to digits and marks, for this session.
  remember() {
    this.undo.push({ cur: this.g.cur.slice(), marks: this.marks().slice(), sel: this.sel });
    if (this.undo.length > 200) this.undo.shift();
  }
  undoLast() {
    const u = this.undo.pop();
    if (!u || this.g.entry) return;
    Object.assign(this.g, { cur: u.cur, marks: u.marks, auto: false, done: false });
    this.sel = u.sel; this.checked = false; this.save();
  }
  // Puts digit v (0 clears) in cell i; a placed digit also leaves the marks of its row, column and box.
  place(i, v) {
    this.g.cur[i] = v;
    const m = this.marks();
    if (v) { m[i] = 0; for (const p of PEERS[i]) m[p] &= ~(1 << v); }
  }
  nextLevel() { return LEVELS.includes(this.g.level) ? this.g.level : "beginner"; }
  async fresh(level, cx) {
    if (this.busy) return;
    this.busy = level; cx.notify();
    try { this.play((await newPuzzles(level, 1))[0]); } finally { this.busy = null; cx.notify(); }
  }
  go(view) { this.view = view; if (view === "play") this.handle.focus(); }

  grid() { return this.g.entry || this.g.cur; }

  conflict(i) {
    const v = this.grid()[i];
    if (!v) return false;
    const c = this.grid().slice(); c[i] = 0;
    return !ok(c, i, v);
  }

  enter() { this.g.entry = Array(81).fill(0); this.sel = 0; this.checked = false; this.hi = this.msg = null; this.save(); }
  cancelEntry() { delete this.g.entry; this.save(); }

  startEntry() {
    const e = this.g.entry;
    if (e.some((_, i) => this.conflict(i))) return fail("Some digits clash. Fix the red ones first.");
    const { n, sol } = solve(e);
    if (!n) return fail("This puzzle has no solution. Check the digits against the paper.");
    if (n > 1) return fail("This puzzle has more than one solution. A digit is probably missing.");
    const { se, stuck } = rate(e);
    this.play({ puz: e, sol, cur: e.slice(), level: "custom", se, stuck });
    this.askDesc();
  }

  put(v) {
    if (this.g.entry) { this.g.entry[this.sel] = v; this.save(); return; }
    const i = this.sel, m = this.marks();
    if (this.g.puz[i] || this.won()) return;
    // Pencil mode: a digit toggles its mark in an empty cell; 0 clears the cell's marks.
    if (this.pencil && !this.g.cur[i]) {
      if (v ? false : !m[i]) return;
      this.remember();
      m[i] = v ? m[i] ^ (1 << v) : 0;
      this.save();
      return;
    }
    if (this.g.cur[i] === v) return;
    this.remember();
    this.place(i, v);
    this.checked = false;
    this.save();
  }

  // The next digit by technique, with its reason drawn on the board; a guess when no technique works.
  step() {
    const g = this.g;
    if (g.entry || this.won() || this.ask || this.waiting) return;
    const wrong = g.cur.findIndex((v, i) => v && v !== g.sol[i]);
    if (wrong >= 0) {
      this.sel = wrong; this.hi = { [wrong]: "wrong" };
      this.explain(`${rc(wrong)} is wrong`, `The digit in ${rc(wrong)} doesn't fit the answer. Clear it (0), then take a step again.`);
      return;
    }
    const s = nextStep(g.cur);
    this.remember();
    if (s.kind === "stuck") {
      const bits = (m) => m.toString(2).replace(/0/g, "").length;
      const cell = s.cand.reduce((b, m, i) => (m && (b < 0 || bits(m) < bits(s.cand[b])) ? i : b), -1);
      this.hi = { [cell]: "target" };
      this.place(cell, g.sol[cell]); this.sel = cell;
      this.explain(`A guess: ${rc(cell)} is ${g.sol[cell]}`, `No technique this game knows works here (it would take unique rectangles or chains). The solver guesses in ${rc(cell)}, which has the fewest marks, and backtracks on a contradiction. The right digit is ${g.sol[cell]}.`);
    } else {
      this.hi = marksOf(s);
      this.place(s.cell, s.digit); this.sel = s.cell;
      this.explain(`${rc(s.cell)} is ${s.digit}`, [...s.elims.map((e) => `Marks: ${e.text}`), s.text].join(" "));
    }
    this.checked = false;
    this.save();
  }

  // Step's reason, and the questions Hint and Solve ask, show as a card laid over the side panel. It is
  // drawn in this pane, so it never covers the grid (a step's highlights stay visible) and nothing moves.
  // The game takes no other input until it is answered; Step's needs "Got it", since reading it is the point.
  explain(title, body) {
    this.msg = body; this.waiting = true;
    this.card = { title, body, cancel: () => this.ack(),
      buttons: [{ id: "ok", label: "Got it", key: "enter", primary: true, run: () => this.ack() }] };
  }
  ack() { this.waiting = false; this.card = null; this.dismiss(); }

  // Hint and Solve show answers without the reasoning, so each asks first and offers Step instead.
  askFirst(kind) {
    const hint = kind === "hint", cell = this.sel, no = () => { this.ask = null; this.card = null; };
    this.ask = { kind, cell };
    this.card = hint ? {
      title: `Show the digit in ${rc(cell)}?`,
      body: "Hint shows the digit without the reasoning. Step finds the next digit you can work out and explains why, so try that first.",
      cancel: no,
      buttons: [{ id: "step", label: "Take a step", key: "s", primary: true, run: () => { no(); this.step(); } },
        { id: "show", label: "Show the digit", key: "h", run: () => this.answerYes() }],
    } : {
      title: "Solve the whole puzzle?",
      body: "Solve fills in every cell and ends this game. To learn, Step shows one move at a time, with its reason.",
      cancel: no,
      buttons: [{ id: "keep", label: "Keep playing", key: "escape", primary: true, run: no },
        { id: "solve", label: "Solve it", run: () => this.answerYes() }],
    };
  }

  // A "yes" on the card: Hint shows the digit in the cell it asked about; Solve finishes the game.
  answerYes() {
    const a = this.ask;
    this.ask = null; this.card = null;
    if (a?.kind === "hint") { this.remember(); this.place(a.cell, this.g.sol[a.cell]); this.sel = a.cell; this.checked = false; this.save(); }
    if (a?.kind === "solve") this.solveNow();
  }

  solveAll() {
    if (this.g.entry || this.won() || this.ask || this.waiting) return;
    this.askFirst("solve");
  }
  solveNow() {
    this.remember();
    this.g.cur = this.g.sol.slice(); this.g.marks = Array(81).fill(0); this.g.auto = true; this.hi = this.msg = null; this.save();
  }

  lib() { const l = shared(LIB); return Array.isArray(l) ? l : []; }
  askDesc() {
    const old = this.lib().find((x) => x.puz === this.g.puz.join(""));
    this.input.set_value(old?.desc ?? this.g.desc ?? "");
    this.saveTags.set_value((old?.tags ?? []).join(", "));
    this.view = "save";
    this.input.focus();
  }
  saveDesc() {
    const desc = this.input.value().trim(), puz = this.g.puz.join(""), lib = this.lib();
    const old = lib.find((x) => x.puz === puz);
    const item = { ...old, id: old?.id ?? Date.now(), desc, puz, sol: this.g.sol.join(""), saved: old?.saved ?? today(),
      se: this.g.se, stuck: !!this.g.stuck, tags: parseTags(this.saveTags.value()) };
    setShared(LIB, old ? lib.map((x) => (x.id === old.id ? item : x)) : [...lib, item]);
    this.g.desc = desc; this.save();
    this.go("play");
  }
  load(x) {
    const nums = (s) => [...s].map(Number), puz = nums(x.puz);
    const { se, stuck } = rate(puz);
    this.play({ puz, sol: nums(x.sol), cur: puz.slice(), level: "saved", desc: x.desc, se, stuck });
    this.go("play");
  }

  // Naming: a sheet's id is its time (2026-11-17-104512), the same as its PDF file; the paper prints
  // "2026-11-17 10:45" in its corner. The library names its puzzles after the optional label
  // ("weekend for the kids #1".."#9"), else after the time ("sheet 2026-11-17 10:45 #1").
  async makePdf(cx) {
    if (this.busy) return;
    const d = new Date(), hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const sheet = `${today(d)}-${hm.replace(":", "")}${pad(d.getSeconds())}`, label = `${today(d)} ${hm}`;
    const name = this.printLabel.value().trim() || `sheet ${label}`;
    const path = `${home()}/Downloads/sudoku-${sheet}.pdf`, tags = parseTags(this.printTags.value());
    this.busy = "Making puzzles"; cx.notify();
    try {
      const made = await Promise.all(this.rows.map(({ level, extra }) => newPuzzles(level, 3, extra)));
      const rows = this.rows.map(({ level }, r) => ({ rank: rankOf(level), games: made[r] }));
      this.busy = "Saving PDF"; cx.notify();
      await writeTextFile(path, sheetPdf(rows, label, this.printLabel.value()), null);
      setShared(LIB, [...this.lib(), ...rows.flatMap((row, r) => row.games.map((g, c) => {
        const pos = r * 3 + c + 1;
        return { id: d.getTime() + pos, desc: `${name} #${pos}`, puz: g.puz.join(""), sol: g.sol.join(""),
          saved: today(d), se: g.se, stuck: !!g.stuck, sheet, sheetName: name, pos, tags };
      }))]);
      await exec("open", [path]);
      notify({ level: "info", title: "Sudoku sheet saved", body: `${path}\nIts 9 puzzles are in the library as "${name}".`, timeout: 6000 });
    } catch (e) {
      fail(`Could not write ${path}: ${String(e) || "unknown error"}`);
    } finally { this.busy = null; cx.notify(); }
  }

  // Hint asks first (askFirst); a "yes" shows the digit in the cell under the cursor.
  hint() {
    const s = this.sel;
    if (this.g.puz[s] || this.g.cur[s] === this.g.sol[s] || this.g.entry || this.won() || this.ask || this.waiting) return;
    this.askFirst("hint");
  }
  // Step's explanation and its highlights go once it is acknowledged.
  dismiss() { this.msg = this.hi = null; }

  onKey(e, cx) {
    const k = e.key, s = this.sel, r = (s / 9) | 0, c = s % 9;
    // While a card is open, keys answer it: a button's key, Enter for the main one, Esc to cancel.
    if (this.card && this.view === "play") {
      const card = this.card, b = card.buttons.find((x) => x.key === k || (k === "enter" && x.primary));
      if (b) b.run(); else if (k === "escape") card.cancel(); else return;
      cx.stop_propagation(); cx.notify();
      return;
    }
    if (this.view !== "play") {
      const last = guidePages().length - 1;
      if (k === "escape") this.go("play");
      else if (this.view === "guide" && k === "right") this.page = Math.min(this.page + 1, last);
      else if (this.view === "guide" && k === "left") this.page = Math.max(this.page - 1, 0);
      else return;
    }
    else if (/^[1-9]$/.test(k)) this.put(+k);
    else if (k === "0" || k === "backspace" || k === "delete") this.put(0);
    else if (k === "left") this.sel = r * 9 + (c + 8) % 9;
    else if (k === "right") this.sel = r * 9 + (c + 1) % 9;
    else if (k === "up" || k === "k") this.sel = ((r + 8) % 9) * 9 + c;
    else if (k === "down" || k === "j") this.sel = ((r + 1) % 9) * 9 + c;
    else if (this.g.entry && k === "enter") this.startEntry();
    else if (this.g.entry && k === "escape") this.cancelEntry();
    else if (this.g.entry) return;
    else if (k === "e") this.enter();
    else if (k === "h") this.hint();
    else if (k === "s") this.step();
    else if (k === "n") { const level = this.nextLevel(); cx.spawn(async (cx) => this.fresh(level, cx)); }
    else if (k === "c") this.checked = !this.checked;
    else if (k === "p") this.pencil = !this.pencil;
    else if (k === "u") this.undoLast();
    else return;
    cx.stop_propagation();
    cx.notify();
  }

  cell(t, i, size) {
    const g = this.g, v = this.grid()[i], given = g.entry ? !!v : !!g.puz[i];
    const r = (i / 9) | 0, c = i % 9, sv = this.grid()[this.sel];
    const sr = (this.sel / 9) | 0, sc = this.sel % 9;
    const peer = r === sr || c === sc || ((r / 3) | 0) === ((sr / 3) | 0) && ((c / 3) | 0) === ((sc / 3) | 0);
    const bad = this.conflict(i) || (this.checked && v && v !== g.sol[i]);
    let bg = cellBg(t, i);
    // An explanation's marks stay while it shows; the selection's usual highlights fill the rest.
    const mark = this.hi && markBg(t, this.hi[i]);
    if (i === this.sel) bg = t.accent + "55";
    else if (mark) bg = mark;
    else if (sv && v === sv) bg = t.accent + "30";
    else if (peer) bg = t.accent + "14";
    return div().id(`sd-${i}`).w(size).h(size).flex_none().flex().items_center().justify_center()
      .bg(bg).cursor_pointer()
      .border_color(t.input)
      .border_r(c < 8 ? (c % 3 === 2 ? 4 : 1) : 0).border_b(r < 8 ? (r % 3 === 2 ? 4 : 1) : 0)
      .text_size(size * 0.55)
      .text_color(bad ? t.blocked : given ? t.foreground : t.accent)
      .when(given, (e) => e.font_bold())
      .on_click((_e, cx) => { this.sel = i; this.handle.focus(); cx.notify(); })
      .child(v ? String(v) : !g.entry && this.marks()[i] ? this.pencilMarks(t, i, size, sv) : "");
  }

  // An empty cell's pencil marks in a 3×3 grid; the selected cell's digit stands out.
  pencilMarks(t, i, size, sv) {
    const m = this.marks()[i], s = size / 3;
    return v_flex().children([0, 1, 2].map((r) => h_flex().children([1, 2, 3].map((k) => {
      const v = r * 3 + k, on = (m >> v) & 1;
      return div().w(s).h(s).flex().items_center().justify_center().text_size(s * 0.75)
        .text_color(v === sv ? t.accent : t.muted).when(v === sv, (e) => e.font_bold()).child(on ? String(v) : "");
    }))));
  }

  btn(t, id, label, fn, on, busy) {
    return h_flex().id(id).gap(6).px(10).py(4).rounded(6).text_size(12).cursor_pointer()
      .border_1().border_color(on ? t.accent : t.border).text_color(on ? t.accent : t.muted)
      .hover((s) => s.bg(t.hover).text_color(t.foreground))
      .on_click((_e, cx) => {
        // While a card is open only its own buttons work; the panel under it waits.
        if (this.card && !id.startsWith("card-")) return;
        fn(cx); if (this.view === "play") this.handle.focus(); cx.notify();
      })
      .when(!!busy, (e) => e.child(spinner(t)))
      .child(label);
  }

  help(t, text) { return div().text_size(11).text_color(t.dim).child(text); }

  // A button's label with its key beside it, so the keys need no separate help line.
  kbd(t, label, key) {
    return h_flex().gap(6).items_center().child(label)
      .child(div().px(4).rounded(3).bg(t.raised).text_size(10).text_color(t.dim).child(key));
  }

  // The controls, grouped by what they are for; beside the board when the pane is wide enough.
  panel(t, w) {
    const section = (title, ...kids) => v_flex().w(w).gap(6)
      .child(div().text_size(10).text_color(t.dim).child(title))
      .child(h_flex().flex_wrap().gap(6).children(kids));
    if (this.g.entry) return v_flex().w(w).gap(14)
      .child(section("ENTER FROM PAPER",
        this.btn(t, "sd-go", this.kbd(t, "Play", "enter"), () => this.startEntry(), true),
        this.btn(t, "sd-x", this.kbd(t, "Cancel", "esc"), () => this.cancelEntry())))
      .child(this.help(t, "Type the given digits from the paper. 0 clears, arrows move."));
    const asking = this.ask?.kind;
    const controls = v_flex().w(w).gap(14)
      .child(section("NEW PUZZLE", ...LEVELS.map((l) => this.btn(t, `sd-n-${l}`, bars(t, rankOf(l), this.g.level === l ? t.accent : t.muted),
        (cx) => cx.spawn(async (cx) => this.fresh(l, cx)), this.g.level === l, this.busy === l))))
      .child(section("PLAY",
        this.btn(t, "sd-s", this.kbd(t, "Step", "s"), () => this.step(), true),
        this.btn(t, "sd-pen", this.kbd(t, this.pencil ? "Pencil on" : "Pencil", "p"), () => { this.pencil = !this.pencil; }, this.pencil),
        this.btn(t, "sd-u", this.kbd(t, "Undo", "u"), () => this.undoLast()),
        this.btn(t, "sd-c", this.kbd(t, "Check", "c"), () => { this.checked = !this.checked; }, this.checked)))
      .child(section("SPOILERS",
        this.btn(t, "sd-t", this.kbd(t, "Hint", "h"), () => this.hint(), asking === "hint"),
        this.btn(t, "sd-a", "Solve", () => this.solveAll(), asking === "solve")))
      .child(section("PUZZLES",
        this.btn(t, "sd-i", this.kbd(t, "From paper", "e"), () => this.enter()),
        this.btn(t, "sd-v", "Save", () => this.askDesc()),
        this.btn(t, "sd-l", `Library (${this.lib().length})`, () => this.go("library")),
        this.btn(t, "sd-p", "Print", () => this.go("print"))))
      .child(section("LEARN", this.btn(t, "sd-g", "Guide", () => this.go("guide"))))
      .child(this.help(t, `1–9 ${this.pencil ? "mark" : "fill"} · 0 clear · arrows move · n new`));
    // An open card lies over the panel's top (see explain()); the panel keeps its size, so nothing moves.
    return div().relative().w(w).child(controls)
      .when(!!this.card, (e) => e.child(this.cardView(t, w).absolute().top(0).left(0)));
  }

  // Step's explanation or a question: title, text, and its buttons with their keys.
  cardView(t, w) {
    const c = this.card;
    return v_flex().id("sd-card").w(w).gap(12).p(14).rounded(8).border_1().border_color(t.accent).bg(t.popover).shadow_lg()
      .child(div().text_size(14).font_semibold().child(c.title))
      .child(div().text_size(13).text_color(t.muted).child(c.body))
      .child(h_flex().flex_wrap().gap(6).children(c.buttons.map((b) =>
        this.btn(t, `card-${b.id}`, b.key ? this.kbd(t, b.label, b.key === "escape" ? "esc" : b.key) : b.label, () => b.run(), b.primary))));
  }

  // top: the title line(s), centred over the grid; the panel starts level with the grid.
  playView(t, top) {
    const size = 44, rows = [];
    for (let r = 0; r < 9; r++) {
      const cells = [];
      for (let c = 0; c < 9; c++) cells.push(this.cell(t, r * 9 + c, size));
      rows.push(h_flex().flex_none().border_color(t.border).border_b(0).children(cells));
    }
    const grid = v_flex().flex_none().rounded(6).overflow_hidden().border(4).border_color(t.input).children(rows);
    // Board 396 + gap 24 + panel 280 + padding: beside it from about 720 px, below it otherwise.
    const wide = this.width >= 730, board = v_flex().items_center().gap(12).children([...top, grid]);
    return wide
      ? [h_flex().items_start().gap(24).child(board).child(div().pt(top.length * (TITLE_H + 12)).child(this.panel(t, 280)))]
      : [board, this.panel(t, size * 9)];
  }

  saveView(t) {
    return [
      div().w(420).text_size(12).text_color(t.muted).child("Where is this puzzle from? (source, date, page, position)"),
      this.field(t, this.input, t.accent),
      this.field(t, this.saveTags, t.input),
      h_flex().gap(6)
        .child(this.btn(t, "sd-sv", "Save", () => this.saveDesc(), true))
        .child(this.btn(t, "sd-sx", "Skip", () => this.go("play"))),
      this.help(t, "enter save · esc skip")];
  }

  field(t, state, border) {
    return Input.new(state).w(420).h(34).px(10).rounded(8).border_1().border_color(border).bg(t.background).text_size(13).text_color(t.foreground);
  }

  // A small clickable label: a tag, a sheet, or the active filter.
  chip(t, id, label, fn) {
    return div().id(id).px(6).rounded(4).text_size(11).bg(t.raised).text_color(t.muted).cursor_pointer()
      .hover((s) => s.bg(t.hover).text_color(t.foreground))
      .on_click((_e, cx) => { fn(); cx.notify(); }).child(label);
  }

  libraryView(t) {
    const all = this.lib(), cur = this.g.puz.join(""), f = this.libFilter;
    const shown = all.filter((x) => !f || (f.tag ? x.tags?.includes(f.tag) : x.sheet === f.sheet));
    const sheetName = (x) => x.sheetName ?? `sheet ${x.sheet}`;
    const rows = shown.slice().reverse().map((x) => h_flex().id(`lib-${x.id}`).w_full().gap(10).px(10).py(8).rounded(6)
      .bg(x.puz === cur ? t.selected : t.background)
      .child(v_flex().flex_1().min_w(0).gap(2)
        .child(div().text_size(13).truncate().text_color(x.desc ? t.foreground : t.dim).child(x.desc || "No description"))
        .child(div().text_size(11).text_color(t.dim).child(`saved ${x.saved} · ${[...x.puz].filter((c) => c !== "0").length} givens${x.se ? ` · ${seLabel(x)}` : ""}`))
        .when(!!(x.sheet || x.tags?.length), (e) => e.child(h_flex().gap(4).flex_wrap()
          .when(!!x.sheet, (e) => e.child(this.chip(t, `lib-s-${x.id}`, sheetName(x), () => { this.libFilter = { sheet: x.sheet, name: sheetName(x) }; })))
          .children((x.tags ?? []).map((tag) => this.chip(t, `lib-t-${x.id}-${tag}`, `#${tag}`, () => { this.libFilter = { tag }; }))))))
      .child(this.btn(t, `lib-p-${x.id}`, "Play", () => this.load(x)))
      .child(this.btn(t, `lib-d-${x.id}`, this.del === x.id ? "Delete?" : "Delete", () => {
        if (this.del !== x.id) { this.del = x.id; return; }
        setShared(LIB, this.lib().filter((y) => y.id !== x.id)); this.del = null;
      }, this.del === x.id)));
    const tags = [...new Set(all.flatMap((x) => x.tags ?? []))].sort();
    return [
      // The active filter (click to clear), else every tag to filter by.
      h_flex().w(520).gap(4).flex_wrap().items_center()
        .child(div().text_size(11).text_color(t.dim).child(f ? `showing ${shown.length} of ${all.length}:` : `${all.length} saved${tags.length ? " · filter:" : ""}`))
        .when(!!f, (e) => e.child(this.chip(t, "lib-f-x", `${f.tag ? `#${f.tag}` : f.name} ×`, () => { this.libFilter = null; })))
        .when(!f, (e) => e.children(tags.map((tag) => this.chip(t, `lib-f-${tag}`, `#${tag}`, () => { this.libFilter = { tag }; })))),
      v_flex().id("sd-lib").w(520).max_h(440).overflow_y_scroll().gap(4)
        .children(rows.length ? rows : [div().p(10).text_size(12).text_color(t.dim).child("Nothing saved yet. Enter a puzzle from paper, press Save in a game, or print a sheet.")]),
      h_flex().gap(6).child(this.btn(t, "sd-lb", "Back", () => this.go("play"))),
      this.help(t, "esc back")];
  }

  printView(t) {
    const set = (r, patch) => {
      this.rows = this.rows.map((x, k) => (k === r ? { ...x, ...patch } : x));
      localStorage.setItem(PRINT, JSON.stringify(this.rows));
    };
    const rows = this.rows.map(({ level, extra }, r) => h_flex().gap(6).items_center()
      .child(div().w(60).text_size(12).text_color(t.muted).child(`Row ${r + 1}`))
      .children(LEVELS.map((l) => this.btn(t, `pr-${r}-${l}`, bars(t, rankOf(l), level === l ? t.accent : t.muted), () => set(r, { level: l }), level === l)))
      .child(div().w(12))
      .child(this.btn(t, `pr-${r}-less`, "−", () => set(r, { extra: Math.max(extra - EXTRA_STEP, MIN_EXTRA) })))
      .child(div().w(84).text_size(12).text_color(extra ? t.foreground : t.dim).flex().justify_center()
        .child(`${extra < 0 ? "−" : "+"}${Math.abs(extra)} hints`))
      .child(this.btn(t, `pr-${r}-more`, "+", () => set(r, { extra: Math.min(extra + EXTRA_STEP, MAX_EXTRA) }))));
    return [
      div().text_size(12).text_color(t.muted).child("A4 sheet: 3 puzzles per row, solutions on page 2. Saved to Downloads."),
      div().text_size(12).text_color(t.muted).child("+ hints fill random cells from the answer (easier); − hides given digits, keeping one answer (harder)."),
      v_flex().gap(8).children(rows),
      tierKey(t),
      div().w(420).text_size(12).text_color(t.muted).child("The label prints at the top of the sheet. The 9 puzzles also go to the library, named after the label, or the date and time without one."),
      this.field(t, this.printLabel, t.input),
      this.field(t, this.printTags, t.input),
      h_flex().gap(6)
        .child(this.btn(t, "sd-pdf", this.busy ? `${this.busy}…` : "Make PDF", (cx) => { if (!this.busy) cx.spawn(async (cx) => this.makePdf(cx)); }, true, !!this.busy))
        .child(this.btn(t, "sd-pb", "Back", () => this.go("play"))),
      this.help(t, "esc back")];
  }

  guideView(t) {
    const pages = guidePages(), p = pages[this.page], last = pages.length - 1, w = 470;
    const para = (s) => div().w(w).text_size(13).text_color(t.foreground).child(s);
    return [
      div().w(w).text_size(16).font_semibold().child(p.title),
      ...p.body.map(para),
      ...(p.tiers ? [div().w(w).child(tierKey(t))] : []),
      ...(p.flow ? [v_flex().w(w).gap(4).children(p.flow.map((s, k) => h_flex().gap(8).items_start()
        .child(div().w(22).h(22).flex_none().rounded(11).bg(t.accent).text_color(t.accent_foreground).text_size(12).flex().items_center().justify_center().child(String(k + 1)))
        .child(div().flex_1().text_size(13).child(s))))
        .child(div().pl(30).text_size(12).text_color(t.accent).child("↺ repeat until the grid is full"))] : []),
      ...(p.diagram ? [board(t, p.diagram, p.diagram.cand ? 40 : 32), legend(t, p.diagram)] : []),
      ...(p.caption ? [div().w(w).text_size(12).italic().text_color(t.muted).child(p.caption)] : []),
      h_flex().gap(6).items_center()
        .child(this.btn(t, "gd-prev", "← Back", () => { this.page = Math.max(this.page - 1, 0); }))
        .child(div().text_size(12).text_color(t.dim).child(`${this.page + 1} / ${pages.length}`))
        .child(this.btn(t, "gd-next", "Next →", () => { this.page = Math.min(this.page + 1, last); }, this.page < last))
        .child(this.btn(t, "gd-close", "Close", () => this.go("play"))),
      this.help(t, "← → pages · esc close")];
  }

  // Herdr sends "focus" only for pane.go; opening the tab or clicking its header doesn't. So take the
  // keyboard when the focused pane becomes a Sudoku pane. Runs from a timer: focus() is refused in render.
  // ponytail: two Sudoku panes in one tab would both reach for it; identify the own pane if that happens.
  takeKeyboard() {
    const f = focused(), mine = !!f?.pane && panes().some((p) => p.pane === f.pane && p.mod === "sudoku");
    if (mine && !this.wasMine && this.view !== "save") this.handle.focus();
    this.wasMine = mine;
  }

  render() {
    const t = theme(), entry = !!this.g.entry, won = this.view === "play" && !entry && this.won();
    const secs = Math.floor((won ? (this.g.elapsed || 0) : Date.now() - this.started) / 1000);
    if (won && !this.g.done) { this.g.done = true; this.g.elapsed = Date.now() - this.started; this.save(); }
    const time = `${(secs / 60) | 0}:${String(secs % 60).padStart(2, "0")}`;
    const sub = { play: entry ? "enter the puzzle" : `${seLabel(this.g)}${this.g.offTier ? " (closest found)" : ""} · ${time}`, save: "save to library", library: "library", print: "print a sheet", guide: "how to solve" }[this.view];
    // Title, rating and timer; on the game screen it sits over the grid, elsewhere over the page.
    const head = [h_flex().h(TITLE_H).gap(8).items_center()
      .child(div().font_semibold().text_size(15).child("Sudoku"))
      .when(this.view === "play" && !entry, (e) => e.child(div().text_size(12).text_color(t.dim).child(levelMark(t, this.g.level))))
      .child(div().text_size(12).text_color(t.dim).child(sub))
      .when(won, (e) => e.child(div().text_size(13).font_bold().text_color(t.done).child(this.g.auto ? "Solved by the computer" : "Solved! 🎉"))),
      ...(this.view === "play" && !entry && this.g.desc ? [div().h(TITLE_H).max_w(396).truncate().text_size(12).text_color(t.muted).child(this.g.desc)] : [])];
    const body = this.view === "play" ? this.playView(t, head)
      : [...head, ...{ save: () => this.saveView(t), library: () => this.libraryView(t), print: () => this.printView(t), guide: () => this.guideView(t) }[this.view]()];
    return v_flex().id("sudoku").size_full().overflow_y_scroll().bg(t.surface).text_color(t.foreground)
      .track_focus(this.handle).on_key_down((e, cx) => this.onKey(e, cx))
      .on_size_change((size, cx) => { if (Math.abs(size.width - this.width) > 1) { this.width = size.width; cx.notify(); } })
      // A click anywhere in the pane takes the keyboard, except on screens with a text box (save, print).
      .on_mouse_down("left", () => { if (this.view !== "save" && this.view !== "print") this.handle.focus(); })
      .child(v_flex().w_full().min_h_full().flex_none().items_center().justify_center().gap(12).p(12)
        .children(body));
  }
}
