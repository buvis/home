// Kanso's panel kit: code, the lines where exact characters matter: a diff, a snippet, a log, or a source in Herdr's editor. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-code.js.
import { div } from "gpui-kit";
import { h_flex, v_flex, EditorState } from "gpui-base";
import { theme } from "herdr";
import { G, T, CODE, ICON_ROW, TINT, alpha, monoFont, tokens } from "./ui.js";
import { extOf, diffNumbers } from "./pure.js";

const SIGNS = { "+": "added", "-": "deleted", "@": "hunk" };
const MARKS = { added: "+", deleted: "-" };
const FAILURE = /\b(fail(ed|ure)?|\w*error|\w*exception)\b|^\s*>/i;
const GROUNDS = { added: (c) => alpha(c.done, TINT.diff), deleted: (c) => alpha(c.blocked, TINT.diff), hunk: (c) => c.w4 };

const lineOf = (c, kind) => (source, { number, on }) => {
  const sign = kind === "diff" ? SIGNS[source[0]] : undefined;
  const ground = on ? c.w7 : GROUNDS[sign]?.(c) ?? null;
  const base = h_flex().w_full().h(CODE.line).flex_none().items_center().pr(G.lg).when(Boolean(ground), (el) => el.bg(ground));
  if (sign === "hunk") return base.pl(G.lg).text_color(c.dim).child(div().min_w(0).truncate().child(source));
  const text = sign || (kind === "diff" && source[0] === " ") ? source.slice(1) : source;
  return base
    .child(div().w(CODE.gutter).flex_none().pr(G.sm).text_right().text_color(c.dim).child(kind === "log" || number === undefined ? "" : String(number)))
    .child(div().w(ICON_ROW).flex_none().text_color(c.dim).child(MARKS[sign] ?? " "))
    .child(div().flex_1().min_w(0).truncate().text_color(kind === "log" && FAILURE.test(source) ? c.blocked : c.text).child(text));
};

/** `kind`: diff, snippet or log (a source is Herdr's editor, from `sourceState`); `first`: the first line's number; `line`: the one on the 7% wash. */
export const code = (id, c, { text, kind = "snippet", first = 1, line = 0 }) => {
  const lines = String(text).split("\n");
  const numbers = kind === "diff" ? diffNumbers(lines, first) : lines.map((_, i) => first + i);
  const draw = lineOf(c, kind);
  return v_flex().id(id).w_full().overflow_hidden().font_family(monoFont()).text_size(T.mono)
    .children(lines.map((source, i) => draw(source, { number: numbers[i], on: numbers[i] === line })));
};

const LANG = { ts: "js", tsx: "js", mts: "js", cts: "js", jsx: "js", mjs: "js", toml: "yaml", jsonc: "json", svelte: "html", vue: "html" };

/** The source kind: Herdr's editor state in the terminal's mono and the kit's code tones. Past `limit` it is cut and read only. Release it when done. */
export function sourceState(path, text, { limit, readonly = true, onChange = null }) {
  const c = tokens(theme()), language = extOf(path) || "txt";
  const big = text.length > limit;
  const locked = readonly || big;
  const state = EditorState.new({ language: LANG[language] ?? language, readonly: locked,
    value: big ? `${text.slice(0, limit)}\n… (file truncated)` : text,
    line_numbers: true, folding: true, font_family: monoFont(), font_size: T.value,
    syntax: { keyword: c.violet, string: c.done, comment: c.dim, function: c.blue, type: c.blue, number: c.working, constant: c.working } });
  if (onChange && !locked) state.on("change", (_e, cx) => onChange(state.value(), cx));
  return state;
}
