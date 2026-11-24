// Human solving techniques and a Sudoku Explainer (SE) style rating.
// Grids are 81 numbers, 0 = empty; candidates are bitmasks (bit v = digit v).
// SE values: github.com/SudokuMonster/SukakuExplainer/wiki/SE121---FAQ
// ponytail: techniques stop at SE 5.4. Unique rectangles, BUG and chains (SE 4.5+) are not built in;
// a puzzle that needs them is rated "4.5+" (stuck). Add them if expert ratings must be exact.
const idx = (r, c) => r * 9 + c;
const range = [0, 1, 2, 3, 4, 5, 6, 7, 8];
const boxCells = (b) => range.map((k) => idx(((b / 3) | 0) * 3 + ((k / 3) | 0), (b % 3) * 3 + (k % 3)));

export const BOXES = range.map((b) => ({ name: `box ${b + 1}`, cells: boxCells(b) }));
export const ROWS = range.map((r) => ({ name: `row ${r + 1}`, cells: range.map((c) => idx(r, c)) }));
export const COLS = range.map((c) => ({ name: `column ${c + 1}`, cells: range.map((r) => idx(r, c)) }));
const LINES = [...ROWS, ...COLS];
const UNITS = [...BOXES, ...LINES];
export const boxOf = (i) => ((i / 27) | 0) * 3 + (((i % 9) / 3) | 0);
const unitsOf = (i) => [BOXES[boxOf(i)], ROWS[(i / 9) | 0], COLS[i % 9]];
export const PEERS = Array.from({ length: 81 }, (_, i) => [...new Set(unitsOf(i).flatMap((u) => u.cells))].filter((j) => j !== i));
const SEES = PEERS.map((p) => new Set(p));

export const rc = (i) => `r${((i / 9) | 0) + 1}c${(i % 9) + 1}`;
const has = (m, v) => (m >> v) & 1;
const pop = (m) => { let n = 0; for (; m; m &= m - 1) n++; return n; };
const digitsOf = (m) => range.map((k) => k + 1).filter((v) => has(m, v));
const list = (a) => (a.length < 2 ? `${a[0]}` : `${a.slice(0, -1).join(", ")} and ${a.at(-1)}`);
const cap = (s) => s[0].toUpperCase() + s.slice(1);
const an = (v) => (v === 8 ? "an" : "a");
const combos = (a, n) => (n === 0 ? [[]] : a.flatMap((x, i) => combos(a.slice(i + 1), n - 1).map((c) => [x, ...c])));
const SIZE = { 2: "pair", 3: "triple", 4: "quad" };
const FISH = { 2: "X-wing", 3: "Swordfish", 4: "Jellyfish" };

export function candidates(g) {
  return g.map((v, i) => (v ? 0 : PEERS[i].reduce((m, p) => m & ~(1 << g[p]), 0x3fe)));
}

// ---- Placements. Each finder returns every instance it sees (an empty array when none).

function fullHouse(g) {
  const out = [];
  for (const u of UNITS) {
    const empty = u.cells.filter((i) => !g[i]);
    if (empty.length !== 1) continue;
    const v = range.map((k) => k + 1).find((d) => !u.cells.some((i) => g[i] === d));
    out.push({ kind: "full", cell: empty[0], digit: v, unit: u, cause: [], elim: [],
      text: `${cap(u.name)} has one empty cell left, so ${rc(empty[0])} is ${v}.` });
  }
  return out;
}

// A digit with one place left in a unit. The cause: the placed copies that rule out the unit's other cells.
export function hiddenSingles(g, cand, units = UNITS) {
  const out = [];
  for (const u of units) for (let v = 1; v <= 9; v++) {
    if (u.cells.some((i) => g[i] === v)) continue;
    const at = u.cells.filter((i) => has(cand[i], v));
    if (at.length !== 1) continue;
    const cell = at[0], cause = new Set();
    for (const j of u.cells) if (!g[j] && j !== cell) {
      const p = PEERS[j].find((p) => g[p] === v && !u.cells.includes(p));
      if (p !== undefined) cause.add(p);
    }
    out.push({ kind: "hidden", cell, digit: v, unit: u, cause: [...cause], elim: [],
      text: `${cap(u.name)} needs ${an(v)} ${v}. Every other empty cell there is ruled out, so ${v} goes in ${rc(cell)}.` });
  }
  return out;
}

// A cell with one candidate left.
export function nakedSingles(g, cand) {
  const out = [];
  cand.forEach((m, cell) => {
    if (!m || m & (m - 1)) return;
    const v = digitsOf(m)[0];
    const seen = [...new Set(PEERS[cell].map((p) => g[p]).filter(Boolean))].sort();
    out.push({ kind: "naked", cell, digit: v, unit: null, cause: PEERS[cell].filter((p) => g[p]), elim: [],
      text: seen.length === 8
        ? `${rc(cell)} sees ${list(seen)} in its row, column and box. Only ${v} is left.`
        : `Only ${v} is still possible in ${rc(cell)}.` });
  });
  return out;
}

// An elimination that at once leaves a hidden single: SE's "direct" variants, solvable without pencil marks.
function direct(g, cand, found) {
  for (const e of found) {
    const after = cand.slice();
    for (const x of e.elim) after[x.cell] &= ~(1 << x.digit);
    const h = hiddenSingles(g, after)[0];
    if (h) return [{ ...h, kind: `direct-${e.kind}`, other: e.unit, area: e.area, cause: [...e.cause, ...h.cause],
      elim: e.elim, via: e, text: `${e.text} That leaves one place: ${h.text}` }];
  }
  return [];
}

// ---- Eliminations.

// In a box, a digit's places all lie on one line: the rest of that line can't hold it ("pointing").
// In a line, a digit's places all lie in one box: the rest of that box can't hold it ("claiming").
function lockedCandidates(g, cand, from, to, kind) {
  const out = [];
  for (const u of from) for (let v = 1; v <= 9; v++) {
    const at = u.cells.filter((i) => has(cand[i], v));
    if (at.length < 2) continue;
    for (const b of to) {
      if (!at.every((i) => b.cells.includes(i))) continue;
      const elim = b.cells.filter((i) => !u.cells.includes(i) && has(cand[i], v)).map((cell) => ({ cell, digit: v }));
      if (elim.length) out.push({ kind, digit: v, unit: u, other: b, cause: at, elim,
        text: `In ${u.name}, the ${v} can only go where it meets ${b.name}. So the rest of ${b.name} can't be ${v}.` });
    }
  }
  return out;
}
export const pointings = (g, cand) => lockedCandidates(g, cand, BOXES, LINES, "pointing");
export const claimings = (g, cand) => lockedCandidates(g, cand, LINES, BOXES, "claiming");

// n cells of a unit that together hold only n digits: the unit's other cells can't hold them.
export function nakedSubsets(g, cand, n) {
  const out = [];
  for (const u of UNITS) {
    const pool = u.cells.filter((i) => cand[i] && pop(cand[i]) <= n);
    for (const cells of combos(pool, n)) {
      const m = cells.reduce((a, i) => a | cand[i], 0);
      if (pop(m) !== n) continue;
      const elim = u.cells.filter((i) => !cells.includes(i)).flatMap((cell) => digitsOf(cand[cell] & m).map((digit) => ({ cell, digit })));
      const ds = digitsOf(m);
      if (elim.length) out.push({ kind: `naked-${SIZE[n]}`, digit: ds[0], digits: ds, unit: u, cause: cells, elim,
        text: `${list(cells.map(rc))} can only hold ${list(ds)}. So no other cell in ${u.name} can.` });
    }
  }
  return out;
}

// n digits that fit only in the same n cells of a unit: those cells can't hold anything else.
function hiddenSubsets(g, cand, n) {
  const out = [];
  for (const u of UNITS) {
    const where = {};
    for (let v = 1; v <= 9; v++) {
      const at = u.cells.filter((i) => has(cand[i], v));
      if (at.length >= 2 && at.length <= n) where[v] = at;
    }
    for (const ds of combos(Object.keys(where).map(Number), n)) {
      const cells = [...new Set(ds.flatMap((v) => where[v]))];
      if (cells.length !== n) continue;
      const m = ds.reduce((a, v) => a | (1 << v), 0);
      const elim = cells.flatMap((cell) => digitsOf(cand[cell] & ~m).map((digit) => ({ cell, digit })));
      if (elim.length) out.push({ kind: `hidden-${SIZE[n]}`, digit: ds[0], digits: ds, unit: u, cause: cells, elim,
        text: `In ${u.name}, ${list(ds)} fit only in ${list(cells.map(rc))}. So those cells can't hold anything else.` });
    }
  }
  return out;
}

// X-wing (n=2), Swordfish (3), Jellyfish (4): a digit's places in n lines all sit in the same n crossing lines.
function fish(g, cand, n) {
  const out = [];
  for (const [base, cover] of [[ROWS, COLS], [COLS, ROWS]]) for (let v = 1; v <= 9; v++) {
    const lines = base.map((u) => ({ u, at: u.cells.filter((i) => has(cand[i], v)) }))
      .filter((l) => l.at.length >= 2 && l.at.length <= n);
    for (const set of combos(lines, n)) {
      const crossing = [...new Set(set.flatMap((l) => l.at.map((i) => cover.findIndex((c) => c.cells.includes(i)))))];
      if (crossing.length !== n) continue;
      const inBase = new Set(set.flatMap((l) => l.u.cells));
      const elim = crossing.flatMap((k) => cover[k].cells).filter((i) => !inBase.has(i) && has(cand[i], v)).map((cell) => ({ cell, digit: v }));
      if (elim.length) out.push({ kind: FISH[n], digit: v, area: [...inBase], cause: set.flatMap((l) => l.at), elim,
        text: `${FISH[n]} on ${v}: in ${list(set.map((l) => l.u.name))}, the ${v} can only go in ${list(crossing.map((k) => cover[k].name))}. So the rest of those can't be ${v}.` });
    }
  }
  return out;
}

// XY-wing: pivot {x,y} sees pincers {x,z} and {y,z}; one pincer is z, so cells seeing both can't be z.
function xyWing(g, cand) {
  const out = [];
  for (let p = 0; p < 81; p++) {
    if (pop(cand[p]) !== 2) continue;
    const wings = PEERS[p].filter((a) => pop(cand[a]) === 2 && pop(cand[a] & cand[p]) === 1);
    for (const [a, b] of combos(wings, 2)) {
      const z = cand[a] & ~cand[p];
      if (z !== (cand[b] & ~cand[p]) || (cand[a] & cand[p]) === (cand[b] & cand[p])) continue;
      const v = digitsOf(z)[0];
      const elim = PEERS[a].filter((i) => i !== p && SEES[b].has(i) && cand[i] & z).map((cell) => ({ cell, digit: v }));
      const [x, y] = digitsOf(cand[p]);
      if (elim.length) out.push({ kind: "XY-wing", digit: v, cause: [p, a, b], elim,
        text: `XY-wing: ${rc(p)} is ${x} or ${y}. Either way ${rc(a)} or ${rc(b)} is ${v}, so cells that see both can't be ${v}.` });
    }
  }
  return out;
}

// XYZ-wing: pivot {x,y,z} sees pincers {x,z} and {y,z}; cells seeing all three can't be z.
function xyzWing(g, cand) {
  const out = [];
  for (let p = 0; p < 81; p++) {
    if (pop(cand[p]) !== 3) continue;
    const wings = PEERS[p].filter((a) => pop(cand[a]) === 2 && (cand[a] & ~cand[p]) === 0);
    for (const [a, b] of combos(wings, 2)) {
      const z = cand[a] & cand[b];
      if (pop(z) !== 1 || (cand[a] | cand[b]) !== cand[p]) continue;
      const v = digitsOf(z)[0];
      const elim = PEERS[p].filter((i) => i !== a && i !== b && SEES[a].has(i) && SEES[b].has(i) && cand[i] & z).map((cell) => ({ cell, digit: v }));
      if (elim.length) out.push({ kind: "XYZ-wing", digit: v, cause: [p, a, b], elim,
        text: `XYZ-wing: one of ${rc(p)}, ${rc(a)} and ${rc(b)} must be ${v}, so cells that see all three can't be ${v}.` });
    }
  }
  return out;
}

// Easiest first, as Sudoku Explainer orders them.
const TECHS = [
  [1.0, (g) => fullHouse(g)],
  [1.2, (g, c) => hiddenSingles(g, c, BOXES)],
  [1.5, (g, c) => hiddenSingles(g, c, LINES)],
  [1.7, (g, c) => direct(g, c, pointings(g, c))],
  [1.9, (g, c) => direct(g, c, claimings(g, c))],
  [2.0, (g, c) => direct(g, c, hiddenSubsets(g, c, 2))],
  [2.3, (g, c) => nakedSingles(g, c)],
  [2.5, (g, c) => direct(g, c, hiddenSubsets(g, c, 3))],
  [2.6, (g, c) => pointings(g, c)],
  [2.8, (g, c) => claimings(g, c)],
  [3.0, (g, c) => nakedSubsets(g, c, 2)],
  [3.2, (g, c) => fish(g, c, 2)],
  [3.4, (g, c) => hiddenSubsets(g, c, 2)],
  [3.6, (g, c) => nakedSubsets(g, c, 3)],
  [3.8, (g, c) => fish(g, c, 3)],
  [4.0, (g, c) => hiddenSubsets(g, c, 3)],
  [4.2, (g, c) => xyWing(g, c)],
  [4.4, (g, c) => xyzWing(g, c)],
  [5.0, (g, c) => nakedSubsets(g, c, 4)],
  [5.2, (g, c) => fish(g, c, 4)],
  [5.4, (g, c) => hiddenSubsets(g, c, 4)],
];

// cap: skip techniques rated above it (a cheaper check when only "is it at most X" matters).
export function findStep(g, cand, cap = Infinity) {
  for (const [se, find] of TECHS) {
    if (se > cap) break;
    const r = find(g, cand);
    if (r.length) return { ...r[0], se };
  }
  return null;
}

// The next placement a person can find, with the pencil-mark eliminations needed to see it.
// kind "stuck": no built-in technique works; the solver must guess (cand is returned for picking the guess).
export function nextStep(g) {
  const cand = candidates(g), elims = [];
  for (;;) {
    const s = findStep(g, cand);
    if (!s) return { kind: "stuck", elims, cand };
    if (s.cell !== undefined) return { ...s, elims };
    elims.push({ ...s, cand: cand.slice() });
    for (const x of s.elim) cand[x.cell] &= ~(1 << x.digit);
  }
}

// A scanning player's path, the same however the grid is shuffled: each round places every single
// (hidden or naked) visible at once. singles: this alone solves the puzzle. width: average moves open
// per round while more than 10 cells are empty (low = the player must search).
export function scan(puz) {
  const g = puz.slice(), widths = [];
  for (;;) {
    const cand = candidates(g), found = new Map();
    for (const s of [...nakedSingles(g, cand), ...hiddenSingles(g, cand)]) found.set(s.cell, s.digit);
    if (!found.size) break;
    if (g.filter((v) => !v).length > 10) widths.push(found.size);
    for (const [cell, digit] of found) g[cell] = digit;
  }
  return { singles: !g.includes(0), width: widths.length ? widths.reduce((a, b) => a + b, 0) / widths.length : 81 };
}

// SE-style rating: always the easiest technique, candidates kept between steps, rating = hardest step.
// Finishing without getting stuck also proves the puzzle has exactly one solution (every step is forced).
// cap: stop at techniques above it; "stuck" then means "needs more than cap".
export function rate(puz, cap = Infinity) {
  const g = puz.slice(), cand = candidates(g), kinds = new Set();
  let se = 0, stuck = false;
  while (g.includes(0)) {
    const s = findStep(g, cand, cap);
    if (!s) { stuck = true; break; }
    se = Math.max(se, s.se);
    kinds.add(s.kind);
    if (s.cell === undefined) { for (const x of s.elim) cand[x.cell] &= ~(1 << x.digit); continue; }
    g[s.cell] = s.digit; cand[s.cell] = 0;
    for (const p of PEERS[s.cell]) cand[p] &= ~(1 << s.digit);
  }
  // The scan is skipped for capped (yes/no) checks: they don't need it and it costs as much again.
  return { se: stuck ? Math.max(se, 4.5) : se, stuck, kinds: [...kinds], ...(cap === Infinity ? scan(puz) : {}), solved: g };
}
export const seLabel = (r) => `SE ${r.se.toFixed(1)}${r.stuck ? "+" : ""}`;

// One real, instructive example of each technique the guide teaches, found by replaying the pool.
export function findExamples(pool) {
  const ex = {};
  const empties = (u, g) => u.cells.filter((i) => !g[i]).length;
  for (const level of Object.keys(pool)) for (const [p, s] of pool[level]) {
    ex.rules ??= { g: [...s].map(Number) };
    const g = [...p].map(Number);
    while (g.includes(0)) {
      const cand = candidates(g);
      const h = hiddenSingles(g, cand, BOXES).find((x) => empties(x.unit, g) >= 4 && x.cause.length >= 3);
      const n = nakedSingles(g, cand).find((x) => new Set(x.cause.map((i) => g[i])).size === 8);
      const pt = pointings(g, cand)[0], cl = claimings(g, cand)[0], pr = nakedSubsets(g, cand, 2)[0];
      if (h && !ex.hidden) ex.hidden = { ...h, g: g.slice(), cand };
      if (n && !ex.naked) ex.naked = { ...n, g: g.slice(), cand };
      if (pt && !ex.pointing) ex.pointing = { ...pt, g: g.slice(), cand };
      if (cl && !ex.claiming) ex.claiming = { ...cl, g: g.slice(), cand };
      if (pr && !ex.pair) ex.pair = { ...pr, g: g.slice(), cand };
      if (ex.hidden && ex.naked && ex.pointing && ex.claiming && ex.pair) return ex;
      const st = nextStep(g);
      if (st.kind === "stuck") break;
      g[st.cell] = st.digit;
    }
  }
  return ex;
}
