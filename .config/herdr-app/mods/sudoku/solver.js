// Puzzle generation and brute-force solving. Grids are 81 numbers, 0 = empty.
import { POOL } from "./puzzles.js";
import { rate, scan } from "./logic.js";

const shuffle = (a) => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const pick = (a) => a[Math.floor(Math.random() * a.length)];

export function ok(g, i, v) {
  const r = (i / 9) | 0, c = i % 9, br = r - (r % 3), bc = c - (c % 3);
  for (let k = 0; k < 9; k++) {
    if (g[r * 9 + k] === v || g[k * 9 + c] === v) return false;
    if (g[(br + ((k / 3) | 0)) * 9 + bc + (k % 3)] === v) return false;
  }
  return true;
}

// Backtracking with fewest-candidates-first; stops at 2 solutions (enough to know it isn't unique).
export function solve(g) {
  const a = g.slice();
  let n = 0, sol = null;
  const go = () => {
    let best = -1, cands = null;
    for (let i = 0; i < 81; i++) if (!a[i]) {
      const cs = [];
      for (let v = 1; v <= 9; v++) if (ok(a, i, v)) cs.push(v);
      if (!cs.length) return;
      if (!cands || cs.length < cands.length) { best = i; cands = cs; }
    }
    if (best < 0) { if (!n++) sol = a.slice(); return; }
    for (const v of cands) { a[best] = v; go(); a[best] = 0; if (n > 1) return; }
  };
  go();
  return { n, sol };
}

// Changes how many digits are given. n > 0 reveals that many more cells of the answer (easier; the
// answer stays unique). n < 0 hides that many givens, keeping each only-if-needed for a unique answer
// (harder; stops early when no given can go). Returns the new level (rank) and the actual change (delta).
export function adjustHints(g, n) {
  const puz = g.puz.slice(), cells = (want) => puz.flatMap((v, i) => (!!v === want ? [i] : []));
  if (n > 0) for (const i of shuffle(cells(false)).slice(0, n)) puz[i] = g.sol[i];
  let left = Math.max(-n, 0);
  for (const i of left ? shuffle(cells(true)) : []) {
    puz[i] = 0;
    if (solve(puz).n === 1) { if (!--left) break; } else puz[i] = g.sol[i];
  }
  const r = rate(puz), count = (a) => a.filter(Boolean).length;
  return { ...g, puz, cur: puz.slice(), se: r.se, stuck: r.stuck, delta: count(puz) - count(g.puz), rank: puzzleRank(puz) };
}

// Tiers on the Sudoku Explainer scale.
// check(puz): run after every removed digit, as cheap as the tier allows; true also means one solution
//   (a finished rating or scan is forced all the way; Expert asks the brute-force solver).
// accept(r): the full rating of the finished puzzle. singles and width come from the shuffle-proof scan.
// ponytail: width thresholds are first guesses; tune them after people play.
// The order is the difficulty rank the UI draws as bars (1 to 5); the keys are internal names only.
export const TIERS = {
  easy: { about: "scan boxes only, many moves open",
    check: (p) => !rate(p, 1.2).stuck && scan(p).width >= 8, accept: () => true },
  beginner: { about: "no pencil marks, no guessing, few moves open at once",
    check: (p) => scan(p).singles, accept: (r) => r.se >= 1.5 && r.width <= 4.5 },
  medium: { about: "no pencil marks, but needs a deeper look",
    check: (p) => !rate(p, 2.5).stuck, accept: (r) => r.se >= 1.7 && !r.singles },
  hard: { about: "pencil marks and patterns",
    check: (p) => !rate(p, 4.4).stuck, accept: (r) => r.se >= 2.6 },
  expert: { about: "advanced patterns or chains",
    check: (p) => solve(p).n === 1, accept: (r) => r.se >= 4.5 },
};

// The easiest tier whose ceiling a puzzle fits, as a rank (1 = easiest). Extra hints can lower it.
export const puzzleRank = (puz) => Object.values(TIERS).findIndex((t) => t.check(puz)) + 1;

// A random full grid: fill cells in order, digits in random order, back up on a dead end.
function randomGrid() {
  const a = Array(81).fill(0);
  const fill = (i) => {
    if (i === 81) return true;
    for (const v of shuffle([1, 2, 3, 4, 5, 6, 7, 8, 9])) {
      if (!ok(a, i, v)) continue;
      a[i] = v;
      if (fill(i + 1)) return true;
    }
    a[i] = 0;
    return false;
  };
  fill(0);
  return a;
}

// Digs a new puzzle for a tier: from a random full grid, removes digit pairs (keeping 180° symmetry)
// while the tier's check holds. Tries new grids until the result is in the tier; after `attempts`,
// returns the closest one, marked offTier.
// Runs in node (make.mjs): Herdr's own engine is ~12× slower and would take seconds per puzzle.
// attempts: a single try succeeds 8% (Hard) to 100% (Easy) of the time, at 2–12 ms each in node;
// 200 tries make giving up about one in 17 million for Hard.
export function make(level, attempts = 200) {
  const tier = TIERS[level];
  let best = null;
  for (let k = 0; k < attempts; k++) {
    const sol = randomGrid(), puz = sol.slice();
    for (const i of shuffle([...Array(41).keys()])) {
      const cells = i === 40 ? [40] : [i, 80 - i];
      for (const c of cells) puz[c] = 0;
      if (!tier.check(puz)) for (const c of cells) puz[c] = sol[c];
    }
    const r = rate(puz), g = { puz, sol, cur: puz.slice(), level, se: r.se, stuck: r.stuck };
    if (tier.accept(r)) return g;
    if (!best || r.se > best.se) best = { ...g, offTier: true };
  }
  return best;
}

// A row (or column) order that keeps 180° symmetry: outer bands swap or not, mirrored inside;
// the middle band's outer rows swap or not.
function symPerm() {
  const p = Array(9), flip = Math.random() < 0.5, q = shuffle([0, 1, 2]);
  for (let k = 0; k < 3; k++) { p[k] = (flip ? 6 : 0) + q[k]; p[8 - k] = 8 - p[k]; }
  p[3] = Math.random() < 0.5 ? 5 : 3; p[4] = 4; p[5] = 8 - p[3];
  return p;
}

// A rated pool puzzle in a new disguise: relabel digits, reorder rows, columns and bands, transpose.
// The rating and the symmetry stay the same, so this is instant.
export function generate(level) {
  const [p, s, se, stuck] = pick(POOL[level]);
  const dig = shuffle([1, 2, 3, 4, 5, 6, 7, 8, 9]);
  const rp = symPerm(), cp = symPerm(), tr = Math.random() < 0.5;
  const map = (str) => {
    const out = Array(81);
    for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) {
      const v = +str[rp[r] * 9 + cp[c]];
      out[tr ? c * 9 + r : r * 9 + c] = v ? dig[v - 1] : 0;
    }
    return out;
  };
  const puz = map(p);
  return { sol: map(s), puz, cur: puz.slice(), level, se, stuck: !!stuck };
}
