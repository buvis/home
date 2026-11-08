// Sudoku. Open as a pane: herdr-app do pane.split '{"direction":"right","mod":"sudoku"}'
// Keys: 1-9 fill, 0/backspace/delete clear, arrows or hjkl move, h hint, n new game, c check.
import { View, div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { theme } from "herdr";
import { POOL } from "./puzzles.js";

const KEY = "sudoku-v1";

const shuffle = (a) => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

function ok(g, i, v) {
  const r = (i / 9) | 0, c = i % 9, br = r - (r % 3), bc = c - (c % 3);
  for (let k = 0; k < 9; k++) {
    if (g[r * 9 + k] === v || g[k * 9 + c] === v) return false;
    if (g[(br + ((k / 3) | 0)) * 9 + bc + (k % 3)] === v) return false;
  }
  return true;
}


const pick = (a) => a[Math.floor(Math.random() * a.length)];

// Validity-preserving shuffle: relabel digits, permute rows/cols within bands, permute bands, transpose.
function generate(level) {
  const [p, s] = pick(POOL[level]);
  const dig = shuffle([1, 2, 3, 4, 5, 6, 7, 8, 9]);
  const perm = () => shuffle([0, 1, 2]).flatMap((b) => shuffle([0, 1, 2]).map((k) => b * 3 + k));
  const rp = perm(), cp = perm(), tr = Math.random() < 0.5;
  const map = (str) => {
    const out = Array(81);
    for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) {
      const v = +str[rp[r] * 9 + cp[c]];
      out[tr ? c * 9 + r : r * 9 + c] = v ? dig[v - 1] : 0;
    }
    return out;
  };
  const puz = map(p);
  return { sol: map(s), puz, cur: puz.slice(), level };
}

export default class Sudoku extends View {
  init(_p, cx) {
    this.handle = cx.focus_handle();
    this.sel = 40;
    this.checked = false;
    try { this.g = JSON.parse(localStorage.getItem(KEY) || "null"); } catch { this.g = null; }
    const g = this.g;
    if (!g || g.cur?.length !== 81 || g.sol?.includes(0) || !g.puz?.some((v) => v)) this.g = generate("medium");
    this.started = Date.now() - (this.g.elapsed || 0);
    cx.timer.every(1000, (cx) => { if (!this.won()) cx.notify(); });
  }

  save() { this.g.elapsed = Date.now() - this.started; localStorage.setItem(KEY, JSON.stringify(this.g)); }
  won() { return this.g.cur.every((v, i) => v === this.g.sol[i]); }
  fresh(level) { this.g = generate(level); this.started = Date.now(); this.checked = false; this.save(); }

  conflict(i) {
    const v = this.g.cur[i];
    if (!v) return false;
    const c = this.g.cur.slice(); c[i] = 0;
    return !ok(c, i, v);
  }

  put(v) {
    if (this.g.puz[this.sel] || this.won()) return;
    this.g.cur[this.sel] = v;
    this.checked = false;
    this.save();
  }

  onKey(e, cx) {
    const k = e.key, s = this.sel, r = (s / 9) | 0, c = s % 9;
    if (/^[1-9]$/.test(k)) this.put(+k);
    else if (k === "0" || k === "backspace" || k === "delete") this.put(0);
    else if (k === "left") this.sel = r * 9 + (c + 8) % 9;
    else if (k === "right") this.sel = r * 9 + (c + 1) % 9;
    else if (k === "up" || k === "k") this.sel = ((r + 8) % 9) * 9 + c;
    else if (k === "down" || k === "j") this.sel = ((r + 1) % 9) * 9 + c;
    else if (k === "h") { if (!this.g.puz[s]) this.put(this.g.sol[s]); }
    else if (k === "n") this.fresh(this.g.level);
    else if (k === "c") this.checked = !this.checked;
    else return;
    cx.stop_propagation();
    cx.notify();
  }

  cell(t, i, size) {
    const g = this.g, v = g.cur[i], given = !!g.puz[i];
    const r = (i / 9) | 0, c = i % 9, sv = g.cur[this.sel];
    const sr = (this.sel / 9) | 0, sc = this.sel % 9;
    const peer = r === sr || c === sc || ((r / 3) | 0) === ((sr / 3) | 0) && ((c / 3) | 0) === ((sc / 3) | 0);
    const bad = this.conflict(i) || (this.checked && v && v !== g.sol[i]);
    let bg = t.background;
    if (i === this.sel) bg = t.accent + "55";
    else if (sv && v === sv) bg = t.accent + "30";
    else if (peer) bg = t.hover;
    return div().id(`sd-${i}`).w(size).h(size).flex_none().flex().items_center().justify_center()
      .bg(bg).cursor_pointer()
      .border_color(t.input)
      .border_r(c < 8 ? (c % 3 === 2 ? 3 : 1) : 0).border_b(r < 8 ? (r % 3 === 2 ? 3 : 1) : 0)
      .text_size(size * 0.55)
      .text_color(bad ? t.blocked : given ? t.foreground : t.accent)
      .when(given, (e) => e.font_bold())
      .on_click((_e, cx) => { this.sel = i; this.handle.focus(); cx.notify(); })
      .child(v ? String(v) : "");
  }

  btn(t, id, label, fn, on) {
    return div().id(id).px(10).py(4).rounded(6).text_size(12).cursor_pointer()
      .border_1().border_color(on ? t.accent : t.border).text_color(on ? t.accent : t.muted)
      .hover((s) => s.bg(t.hover).text_color(t.foreground))
      .on_click((_e, cx) => { fn(); this.handle.focus(); cx.notify(); })
      .child(label);
  }

  render() {
    const t = theme(), size = 44, won = this.won();
    const secs = Math.floor((won ? (this.g.elapsed || 0) : Date.now() - this.started) / 1000);
    if (won && !this.g.done) { this.g.done = true; this.g.elapsed = Date.now() - this.started; this.save(); }
    const time = `${(secs / 60) | 0}:${String(secs % 60).padStart(2, "0")}`;
    const rows = [];
    for (let r = 0; r < 9; r++) {
      const cells = [];
      for (let c = 0; c < 9; c++) cells.push(this.cell(t, r * 9 + c, size));
      rows.push(h_flex().flex_none().border_color(t.border).border_b(0).children(cells));
    }
    return v_flex().id("sudoku").size_full().items_center().justify_center().gap(12).p(12)
      .bg(t.surface).text_color(t.foreground).track_focus(this.handle)
      .on_key_down((e, cx) => this.onKey(e, cx))
      .child(h_flex().gap(8).items_center()
        .child(div().font_semibold().text_size(15).child("Sudoku"))
        .child(div().text_size(12).text_color(t.dim).child(`${this.g.level} · ${time}`))
        .when(won, (e) => e.child(div().text_size(13).font_bold().text_color(t.done).child("Solved! 🎉"))))
      .child(v_flex().flex_none().rounded(6).overflow_hidden().border(4).border_color(t.input).children(rows))
      .child(h_flex().gap(6)
        .child(this.btn(t, "sd-e", "Easy", () => this.fresh("easy"), this.g.level === "easy"))
        .child(this.btn(t, "sd-m", "Medium", () => this.fresh("medium"), this.g.level === "medium"))
        .child(this.btn(t, "sd-h", "Hard", () => this.fresh("hard"), this.g.level === "hard"))
        .child(this.btn(t, "sd-c", "Check", () => { this.checked = !this.checked; }, this.checked))
        .child(this.btn(t, "sd-t", "Hint", () => { if (!this.g.puz[this.sel]) this.put(this.g.sol[this.sel]); })))
      .child(div().text_size(11).text_color(t.dim).child("1-9 fill · 0 clear · arrows move · h hint · c check · n new"));
  }
}
