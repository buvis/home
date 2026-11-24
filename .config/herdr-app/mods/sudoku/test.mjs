// Engine self-check, outside the app: mise exec -- node ~/.config/herdr-app/mods/sudoku/test.mjs
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { POOL } from "./puzzles.js";
import { solve, make, generate, adjustHints, puzzleRank, TIERS } from "./solver.js";
import { rate, nextStep, findExamples } from "./logic.js";
import { sheetPdf } from "./pdf.js";

const nums = (s) => [...s].map(Number), givens = (a) => a.filter(Boolean).length;

// Techniques are sound: the rater never places a wrong digit, Step never removes the answer.
for (const [level, list] of Object.entries(POOL)) for (const [p, s] of list) {
  const sol = nums(s), b = solve(nums(p));
  assert.equal(b.n, 1, `brute force finds one solution (${level})`);
  assert.deepEqual(b.sol, sol);
  const r = rate(nums(p));
  r.solved.forEach((v, i) => assert.ok(!v || v === sol[i], `rating places only right digits (${level})`));
  const g = nums(p);
  for (;;) {
    const st = nextStep(g);
    if (st.kind === "stuck" || !g.includes(0)) break;
    for (const e of st.elims) for (const x of e.elim) assert.notEqual(sol[x.cell], x.digit, `${e.kind} never removes the answer`);
    assert.equal(st.digit, sol[st.cell], `${st.kind} places the right digit`);
    g[st.cell] = st.digit;
  }
}
assert.equal(solve(Array(81).fill(0)).n, 2, "an empty grid is reported as not unique");

// Every tier makes unique, symmetric, random puzzles inside its own band.
const inTier = (tier, p) => tier.check(p) && tier.accept(rate(p));
for (const [level, tier] of Object.entries(TIERS)) for (let k = 0; k < 5; k++) {
  const g = make(level), r = rate(g.puz);
  assert.equal(solve(g.puz).n, 1, `${level} puzzle has one solution`);
  assert.deepEqual(solve(g.puz).sol, g.sol, `${level} puzzle comes with its own solution`);
  assert.ok(!g.offTier && inTier(tier, g.puz), `${level} puzzle is in its tier (SE ${r.se}, width ${r.width})`);
  g.puz.forEach((v, i) => assert.equal(g.puz[80 - i] === 0, v === 0, `${level} puzzle is symmetric`));
}
assert.notDeepEqual(make("easy").sol, make("easy").sol, "full grids are random, not reused");

// The app's call: node make.mjs <tier> <count> prints that many puzzles as JSON.
const cli = spawnSync(process.execPath, [new URL("./make.mjs", import.meta.url).pathname, "beginner", "2"], { encoding: "utf8" });
assert.equal(cli.status, 0, `make.mjs exits cleanly: ${cli.stderr}`);
const printed = JSON.parse(cli.stdout);
assert.equal(printed.length, 2, "make.mjs prints the asked count");
for (const x of printed) assert.ok(/^\d{81}$/.test(x.puz) && inTier(TIERS.beginner, nums(x.puz)), "make.mjs prints beginner puzzles");
assert.notEqual(spawnSync(process.execPath, [new URL("./make.mjs", import.meta.url).pathname, "nope"]).status, 0, "make.mjs rejects an unknown tier");

// The fallback pool (pool + shuffle) keeps its stored rating, tier and symmetry.
for (const [level, tier] of Object.entries(TIERS)) for (let k = 0; k < 10; k++) {
  const g = generate(level), r = rate(g.puz);
  assert.equal(solve(g.puz).n, 1, `${level} pool puzzle has one solution`);
  assert.deepEqual(solve(g.puz).sol, g.sol, `${level} shuffle keeps puzzle and solution together`);
  assert.equal(r.se, g.se, `${level} shuffle keeps the SE rating`);
  assert.ok(inTier(tier, g.puz), `${level} shuffled puzzle stays in its tier (SE ${r.se}, width ${r.width})`);
  g.puz.forEach((v, i) => assert.equal(g.puz[80 - i] === 0, v === 0, `${level} shuffle keeps symmetry`));
}

// Added hints only make a puzzle easier, never break it.
const base = make("beginner"), more = adjustHints(base, 15);
assert.equal(givens(more.puz), givens(base.puz) + 15, "added hints add exactly that many givens");
assert.equal(more.delta, 15, "added hints report the change");
more.puz.forEach((v, i) => assert.ok(!v || v === base.sol[i], "added hints come from the answer"));
assert.equal(solve(more.puz).n, 1, "added hints keep one solution");
assert.ok(more.se <= base.se, "added hints never raise the rating");
assert.equal(givens(adjustHints(base, 99).puz), 81, "more hints than empty cells fills the grid, no crash");

// Hidden hints make a puzzle harder but keep one answer; past the minimum, they stop early.
// Made puzzles can be near the minimum already; 20 added givens make sure 5 can go.
const easy = adjustHints(make("easy"), 20), fewer = adjustHints(easy, -5);
assert.equal(fewer.delta, -5, "hiding 5 of many givens hides 5");
fewer.puz.forEach((v, i) => assert.ok(!v || v === easy.puz[i], "hiding only empties cells, never adds"));
assert.deepEqual(solve(fewer.puz), { n: 1, sol: easy.sol }, "hidden hints keep the same single answer");
const bare = adjustHints(easy, -81);
assert.equal(solve(bare.puz).n, 1, "hiding everything stops at a minimal puzzle that still has one answer");
assert.ok(bare.puz.every((v, i) => !v || (bare.puz[i] = 0, solve(bare.puz).n > 1) && (bare.puz[i] = v)), "every given left is needed");

// A puzzle's rank is its own tier's; added hints never raise it, hidden ones never lower it.
Object.keys(TIERS).forEach((level, k) => {
  const g = generate(level);
  assert.equal(puzzleRank(g.puz), k + 1, `${level} puzzle ranks as its own tier`);
  assert.ok(adjustHints(g, 20).rank <= k + 1, `${level} puzzle with added hints never ranks higher`);
  assert.ok(adjustHints(g, -5).rank >= k + 1, `${level} puzzle with hidden hints never ranks lower`);
});
assert.equal(adjustHints(generate("hard"), 81).rank, 1, "a full grid ranks easiest");

// The app's call with a hint change: node make.mjs <tier> <count> <hints>.
const hinted = JSON.parse(spawnSync(process.execPath, [new URL("./make.mjs", import.meta.url).pathname, "medium", "2", "-5"], { encoding: "utf8" }).stdout);
// Medium puzzles are dug close to the minimum, so hiding may stop before 5; the real count comes back.
assert.ok(hinted.every((x) => x.delta >= -5 && x.delta <= 0 && x.rank >= 3), "make.mjs applies the hint change and reports level and change");

const ex = findExamples(POOL);
for (const k of ["rules", "hidden", "naked", "pointing", "claiming", "pair"]) assert.ok(ex[k], `guide has a ${k} example`);

// Rows chosen at level 3; 15 added hints brought each puzzle down to level 1.
const eased = { ...base, rank: 1, delta: 15 };
const pdf = sheetPdf([0, 1, 2].map(() => ({ rank: 3, games: [eased, eased, eased] })), "2026-01-01");
assert.ok(/^%PDF-1\.4[\x00-\x7f]*%%EOF\n$/.test(pdf), "pdf is ascii and complete");
const xref = +pdf.match(/startxref\n(\d+)/)[1];
assert.equal(pdf.slice(xref, xref + 4), "xref", "startxref points at the xref table");
assert.equal(pdf.match(/re f/g).length, 2 * 9 * (5 + 1 + 2 + 1), "per grid: five shaded boxes, one black and two grey bars, the badge's centre, two pages");
assert.equal(pdf.match(/0\.72 g [\d. ]+ re f/g).length, 2 * 9 * 2, "per grid: two grey bars for the level the hints took away");
assert.equal(pdf.match(/re S/g).length, 2 * 9 * (2 + 1), "per grid: two empty bars above the chosen level and the badge's cell");
assert.equal(pdf.match(/\(\+15\) Tj/g).length, 2 * 9, "every puzzle shows its +15 badge");
const words = [...pdf.matchAll(/\((.*?)\) Tj/g)].map((m) => m[1]).filter((s) => /[A-Za-z]/.test(s));
assert.deepEqual([...new Set(words)], ["Sudoku"], "the sheet's only word is the puzzle's name");
// A label in Czech prints through font F3: still an ASCII file, every letter named, nothing unknown.
const labelled = sheetPdf([0, 1, 2].map(() => ({ rank: 3, games: [eased, eased, eased] })), "2026-01-01 10:45", "Víkend pro Šárku: řeč, ďábel, ůl (ěščřžýáíé)");
assert.ok(/^%PDF-1\.4[\x00-\x7f]*%%EOF\n$/.test(labelled), "a labelled pdf is still ascii and complete");
for (const g of ["iacute", "Scaron", "aacute", "rcaron", "ecaron", "dcaron", "uring", "scaron", "ccaron", "zcaron", "yacute", "eacute"])
  assert.ok(labelled.includes(`/${g}`), `the label font names ${g}`);
assert.equal((labelled.match(/\/F3 14 Tf/g) ?? []).length, 2, "the label prints on both pages");
assert.ok(!/\/F3 14 Tf [\d. ]+ Td \([^)]*\?/.test(labelled), "no label letter falls back to ?");
console.log("sudoku engine ok");
