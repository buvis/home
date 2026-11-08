// Each block is a run of whole lines; joining the blocks' lines gives back the file byte for byte.

const FENCE = /^\s{0,3}(`{3,}|~{3,})/;
const HEADING = /^\s{0,3}#{1,6}(\s|$)/;
const RULE = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
const ITEM = /^\s*([-*+]|\d{1,9}[.)])(\s|$)/;
const QUOTE = /^\s{0,3}>/;
const DIVIDER = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;

import { range } from "./pure.js";

const isTableStart = (lines, i) => lines[i].includes("|") && i + 1 < lines.length && DIVIDER.test(lines[i + 1]) && lines[i + 1].includes("-");
const startsBlock = (lines, i) => FENCE.test(lines[i]) || HEADING.test(lines[i]) || RULE.test(lines[i]) || isTableStart(lines, i);

// step(state, j) answers { state, emit }; emits go in runs of 64 so the array is not copied once per item.
const RUN = 64;
function collect(n, step, init) {
  const done = range(Math.ceil(n / RUN)).reduce((acc, r) => {
    const run = range(Math.min(RUN, n - r * RUN), r * RUN).reduce((inner, j) => {
      const next = step(inner.state, j);
      return { state: next.state, items: next.emit ? [...inner.items, next.emit] : inner.items };
    }, { state: acc.state, items: [] });
    return { state: run.state, runs: [...acc.runs, run.items] };
  }, { state: init, runs: [] });
  return done.runs.flat();
}

// A block's continuation: given the next line's index, the continuation after it, or null when the block ended.
const ended = () => null;
const whileLine = (test) => {
  const more = (j) => (test(j) ? more : null);
  return more;
};

function opening(lines, i) {
  const line = lines[i];
  if (!line.trim()) return { kind: "blank", next: ended };
  const fence = FENCE.exec(line);
  if (fence) {
    const closing = new RegExp(`^\\s{0,3}\\${fence[1][0]}{${fence[1].length},}\\s*$`);
    const inside = (j) => (closing.test(lines[j]) ? ended : inside);
    return { kind: "code", next: inside };
  }
  if (HEADING.test(line)) return { kind: "heading", next: ended };
  if (RULE.test(line)) return { kind: "rule", next: ended };
  if (isTableStart(lines, i)) return { kind: "table", next: () => whileLine((j) => lines[j].trim() && lines[j].includes("|")) };
  if (QUOTE.test(line)) return { kind: "quote", next: whileLine((j) => lines[j].trim() && QUOTE.test(lines[j])) };
  if (ITEM.test(line)) return { kind: "list", next: whileLine((j) => lines[j].trim() && (ITEM.test(lines[j]) || /^\s/.test(lines[j])) && !startsBlock(lines, j)) };
  return { kind: "paragraph", next: whileLine((j) => lines[j].trim() && !startsBlock(lines, j) && !QUOTE.test(lines[j]) && !ITEM.test(lines[j])) };
}

export function parseBlocks(text) {
  const lines = text.split("\n");
  const frontEnd = lines[0] === "---" ? lines.indexOf("---", 1) : -1;
  const front = frontEnd > 0;
  const starts = collect(lines.length, (next, j) => {
    const more = next(j);
    if (more) return { state: more };
    const b = opening(lines, j);
    return { state: b.next, emit: { kind: b.kind, start: j } };
  }, front ? whileLine((j) => j <= frontEnd) : ended);
  const all = front ? [{ kind: "front", start: 0 }, ...starts] : starts;
  return all.map((b, k) => ({ kind: b.kind, lines: lines.slice(b.start, k + 1 < all.length ? all[k + 1].start : lines.length) }));
}

export const joinBlocks = (blocks) => blocks.flatMap((b) => b.lines).join("\n");

export function headingOf(line) {
  const m = /^\s{0,3}(#{1,6})\s*(.*?)\s*#*\s*$/.exec(line);
  return m ? { level: m[1].length, text: m[2] } : { level: 1, text: line };
}
export const headingLine = (level, text) => `${"#".repeat(level)} ${text.replace(/\n+/g, " ").trim()}`;

export function cellsOf(line) {
  const trimmed = line.trim();
  const opened = trimmed.startsWith("|") ? trimmed.slice(1) : trimmed;
  const s = opened.endsWith("|") && !opened.endsWith("\\|") ? opened.slice(0, -1) : opened;
  // A pipe right after a backslash is the cell's own; the backslash goes.
  return s.split(/(?<!\\)\|/).map((cell) => cell.replace(/\\\|/g, "|").trim());
}

export function parseTable(lines) {
  const head = cellsOf(lines[0]);
  const align = cellsOf(lines[1]).map((c) => (c.startsWith(":") && c.endsWith(":") ? "center" : c.endsWith(":") ? "right" : c.startsWith(":") ? "left" : null));
  const rows = lines.slice(2).map(cellsOf);
  const n = Math.max(head.length, ...rows.map((r) => r.length));
  const filler = (length, value) => Array.from({ length: Math.max(0, length) }, () => value);
  const pad = (r) => [...r, ...filler(n - r.length, "")];
  return { head: pad(head), align: [...align, ...filler(n - align.length, null)].slice(0, n), rows: rows.map(pad) };
}

const cellText = (c) => String(c ?? "").replace(/\n+/g, " ").trim().replace(/\|/g, "\\|");
const dashes = (a) => (a === "center" ? ":---:" : a === "right" ? "---:" : a === "left" ? ":---" : "---");

export function tableLines(table) {
  const row = (cells) => `| ${cells.map(cellText).join(" | ")} |`;
  return [row(table.head), `|${table.align.map((a) => ` ${dashes(a)} `).join("|")}|`, ...table.rows.map(row)];
}
