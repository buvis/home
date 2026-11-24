// The newcomer's guide: one page per technique, each drawn from a real puzzle where it applies.
import { div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { POOL } from "./puzzles.js";
import { findExamples, ROWS, COLS, BOXES, boxOf } from "./logic.js";
import { TIERS } from "./solver.js";

// Difficulty as a signal-strength icon: five rising bars, the first `rank` filled (1 = easiest).
export const rankOf = (level) => Object.keys(TIERS).indexOf(level) + 1;
export function bars(t, rank, color) {
  return h_flex().items_end().gap(2).h(14).children([1, 2, 3, 4, 5].map((k) =>
    div().w(4).h(4 + k * 2).rounded(1).bg(k <= rank ? color : t.border)));
}

// Boxes 1, 3, 5, 7 and 9 are shaded, like a checkerboard, so box edges stand out.
export const shaded = (i) => boxOf(i) % 2 === 0;
// A veil of the text colour shows in light and dark themes alike.
export const cellBg = (t, i) => (shaded(i) ? t.foreground + "1c" : t.background);

// What a highlighted cell means, shared with the game board.
export const MARKS = {
  unit: ["the area to look at", (t) => t.ansi3 + "30"],
  cause: ["the reason", (t) => t.accent + "60"],
  target: ["the answer", (t) => t.ansi2 + "80"],
  elim: ["a mark that goes away", (t) => t.ansi1 + "50"],
  wrong: ["a wrong digit", (t) => t.ansi1 + "70"],
};
export const markBg = (t, m) => MARKS[m]?.[1](t);

// The area, the reason and the answer of a technique result as cell marks.
export function marksOf(e) {
  const mark = {};
  for (const u of [e.other, e.unit]) for (const i of u?.cells ?? []) mark[i] = "unit";
  for (const i of e.cause) mark[i] = "cause";
  for (const x of e.elim) mark[x.cell] = "elim";
  if (e.cell !== undefined) mark[e.cell] = "target";
  return mark;
}

const diagram = (e, cand) => ({ g: e.g, cand: cand ? e.cand : null, mark: marksOf(e), elim: e.elim,
  digits: e.digits ?? [e.digit], cell: e.cell, digit: e.digit });

let pages = null;
export function guidePages() {
  if (pages) return pages;
  const ex = findExamples(POOL);
  const rules = { g: ex.rules.g, mark: {}, labels: { unit: "a row", cause: "a column", target: "a box" } };
  for (const i of BOXES[6].cells) rules.mark[i] = "target";
  for (const i of COLS[8].cells) rules.mark[i] = "cause";
  for (const i of ROWS[0].cells) rules.mark[i] = "unit";
  pages = [
    { title: "The goal", diagram: rules, body: [
      "Fill the grid so that every row, every column and every 3×3 box holds the digits 1 to 9, each exactly once.",
      "A good puzzle has one answer, and you never need to guess: each new digit follows from the ones already there. The method below finds them in a fixed order.",
      "Cells are named by row and column: r1c9 is the top-right cell. Boxes are numbered 1 to 9, left to right, top to bottom." ] },
    { title: "1. Scan one digit (hidden single)", diagram: diagram(ex.hidden), caption: ex.hidden.text, body: [
      "Pick a digit and a box that still needs it. Every copy of that digit in a crossing row or column rules out that whole row or column of the box.",
      "When only one cell of the box is left, the digit goes there. Scan 1 to 9 through all nine boxes: in easy puzzles this alone finds most digits.",
      "The same works for a row or a column: if a digit fits in only one of its cells, it goes there." ] },
    { title: "2. Count what a cell sees (naked single)", diagram: diagram(ex.naked), caption: ex.naked.text, body: [
      "Look at one empty cell. Its row, its column and its box together hold some digits. If they hold eight different digits, the ninth is the answer.",
      "Check this on cells in nearly full rows, columns and boxes: they see the most digits." ] },
    { title: "3. Pencil marks (candidates)", diagram: { ...diagram(ex.pointing, true), mark: {}, elim: [], cell: undefined }, body: [
      "When scanning finds nothing, write in each empty cell the small digits that are still possible there: every digit its row, column and box don't already hold.",
      "Now steps 1 and 2 become easy to see: a cell with one mark left, or a digit with one mark left in a row, column or box, is a placement.",
      "The next three patterns don't place a digit. They remove marks, until a single appears." ] },
    { title: "4. Pointing", diagram: diagram(ex.pointing, true), caption: ex.pointing.text, body: [
      "Inside one box, all the marks for a digit may sit on a single row or column. The digit must go in that box, so it is somewhere on that line inside the box.",
      "Remove that digit's marks from the rest of the line, outside the box." ] },
    { title: "5. Claiming (box-line)", diagram: diagram(ex.claiming, true), caption: ex.claiming.text, body: [
      "The mirror of pointing: in one row or column, all the marks for a digit may sit inside a single box.",
      "The line's copy of the digit is then inside that box, so the box's other cells can't have it. Remove those marks." ] },
    { title: "6. Naked pair", diagram: diagram(ex.pair, true), caption: ex.pair.text, body: [
      "Two cells in the same row, column or box with the same two marks, and nothing else: those two digits must go in those two cells, in some order.",
      "No other cell of that row, column or box can hold either digit. Remove those marks. (Three cells sharing three digits work the same way.)" ] },
    { title: "7. When nothing works", body: [
      "Harder puzzles need more patterns: X-wing, swordfish, XY-wing and others. Learn them later. Steps 1 and 2 solve every puzzle of the first two levels. The third level also needs one deeper look: pointing or claiming (steps 4–5), or a hidden pair: two digits that fit only in the same two cells of a row, column or box, so those cells hold nothing else. Step knows the harder patterns too and explains each one when it uses it.",
      "Top-level puzzles can need patterns this game does not know (unique rectangles, chains). As a last resort, guess with care. Choose a cell with only two marks and try one of them, in pencil. If that leads to a contradiction (a cell with no marks left, or a digit twice in a unit), the other mark is the answer.",
      "That is what the computer's Solve does: it guesses in the cell with the fewest marks and goes back when it hits a contradiction (backtracking)." ] },
    { title: "How hard is a puzzle?", body: [
      "Every puzzle here gets a rating on the Sudoku Explainer (SE) scale, which puzzle makers use. The solver always takes the easiest technique that works; the rating is the hardest one it needed.",
      "1.0–1.5 scanning (step 1) · 1.7–2.5 no pencil marks, but a deeper look: a cell that sees eight digits (2.3), or pointing or a hidden pair that leaves one place (1.7–2.0) · 2.6–3.4 pencil marks: pointing, claiming, pairs, X-wing · 3.6–5.4 triples, swordfish, wings, quads · 4.5+ patterns this game does not know, or guessing.",
      "A puzzle never needs a guess below the top level. Second-level puzzles also keep few moves open at a time, so you must search, but the next digit always follows from what you see.",
      "The game's five levels, shown by the bars:" ],
      tiers: true },
    { title: "The routine", flow: [
      "Scan digits 1 to 9 through every box, then every row and column (step 1).",
      "Check cells in nearly full rows, columns and boxes (step 2).",
      "Still stuck? Write pencil marks in every empty cell (step 3).",
      "Remove marks with pointing, claiming and pairs (steps 4–6).",
      "Place every cell or digit that has one mark left.",
      "After each placement, erase that digit from the marks of its row, column and box. Go back to the top." ],
      body: ["Practice: in a game, press Step (or s). It finds the next digit with this routine, shows the reason on the board and writes it below."] },
  ];
  return pages;
}

// A 9×9 board for the guide: digits, optional pencil marks, highlights, and the answer in the target cell.
export function board(t, d, size) {
  const rows = [];
  for (let r = 0; r < 9; r++) {
    const cells = [];
    for (let c = 0; c < 9; c++) {
      const i = r * 9 + c, v = d.g[i];
      let content = v ? String(v) : "", color = t.foreground;
      if (i === d.cell) { content = String(d.digit); color = t.foreground; }
      else if (!v && d.cand?.[i]) content = pencil(t, d, i, size);
      cells.push(div().w(size).h(size).flex_none().flex().items_center().justify_center()
        .bg(markBg(t, d.mark[i]) ?? cellBg(t, i)).border_color(t.input)
        .border_r(c < 8 ? (c % 3 === 2 ? 3 : 1) : 0).border_b(r < 8 ? (r % 3 === 2 ? 3 : 1) : 0)
        .text_size(size * 0.5).text_color(color).when(!!v || i === d.cell, (e) => e.font_semibold()).child(content));
    }
    rows.push(h_flex().flex_none().children(cells));
  }
  return v_flex().flex_none().rounded(4).overflow_hidden().border(3).border_color(t.input).children(rows);
}

function pencil(t, d, i, size) {
  const s = size / 3, rows = [];
  for (let r = 0; r < 3; r++) {
    const ds = [];
    for (let c = 0; c < 3; c++) {
      const v = r * 3 + c + 1, on = (d.cand[i] >> v) & 1;
      const gone = d.elim?.some((x) => x.cell === i && x.digit === v);
      const key = d.digits?.includes(v) && d.mark[i] === "cause";
      ds.push(div().w(s).h(s).flex().items_center().justify_center().text_size(s * 0.8)
        .text_color(gone ? t.blocked : key ? t.accent : t.dim).when(gone || key, (e) => e.font_bold())
        .child(on ? String(v) : ""));
    }
    rows.push(h_flex().children(ds));
  }
  return v_flex().children(rows);
}

export function legend(t, d) {
  const used = new Set(Object.values(d.mark));
  return h_flex().gap(10).flex_wrap().children(Object.entries(MARKS).filter(([k]) => used.has(k)).map(([k, [label]]) =>
    h_flex().gap(4).child(div().w(10).h(10).rounded(2).bg(markBg(t, k))).child(div().text_size(11).text_color(t.muted).child(d.labels?.[k] ?? label))));
}
