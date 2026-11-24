// Adapted from Preview Plus (MIT); see THIRD_PARTY.md.
const titleText = value => value.replace(/!?(\[([^\]]*)\])\([^)]*\)/g, "$2")
  .replace(/<[^>]*>/g, "").replace(/(^|\s)__?([^_]+)__?(?=\s|$)/g, "$1$2")
  .replace(/[`*~]/g, "").replace(/\\([\p{P}\p{S}])/gu, "$1")
  .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').trim();

const columns = whitespace => [...whitespace].reduce((column, char) => char === "\t" ? column + 4 - column % 4 : column + 1, 0);
const ATX = /^ {0,3}(#{1,6})(?:[ \t]+(.*?)|[ \t]*)$/;
const FENCE = /^ {0,3}(`{3,}|~{3,})(.*)$/;
const LIST = /^( {0,3})(?:[-+*]|\d{1,9}[.)])([ \t]+|$)/;
const THEMATIC = /^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$/;

function listItem(value, marker) {
  const prefix = marker[0].length - marker[2].length, gap = columns(marker[0]) - prefix;
  const padding = gap >= 1 && gap <= 4 ? gap : 1;
  return { indent: prefix + padding, text: " ".repeat(Math.max(0, gap - padding)) + value.slice(marker[0].length) };
}

export function headingIndex() {
  const used = new Set(), counts = new Map();
  return (raw, level, line) => {
    const title = titleText(raw);
    const base = title.toLowerCase().replace(/[^\p{L}\p{N}\p{M}\s_-]/gu, "").replace(/\s/g, "-") || "section";
    let suffix = counts.get(base) || 0;
    let slug = suffix ? `${base}-${suffix}` : base;
    while (used.has(slug)) slug = `${base}-${++suffix}`;
    counts.set(base, suffix + 1);
    used.add(slug);
    return { title: title || "Untitled", level, slug, line };
  };
}

// Based on Preview Plus's list/container scan. Keep lazy continuation with its
// list so extracting a heading or diagram cannot split a native list item.
export function listContext() {
  let indent = null, paragraph = false, fence = null;
  const consume = value => {
    for (;;) {
      const quote = /^ {0,3}>[ \t]?/.exec(value), nested = !fence && LIST.exec(value);
      if (quote) value = value.slice(quote[0].length);
      else if (nested && !THEMATIC.test(value)) {
        value = listItem(value, nested).text;
        paragraph = false;
      } else break;
    }
    const marker = fenceMarker(value);
    if (fence || marker) {
      fence = fence ? (closesFence(value, fence) ? null : fence) : marker[1];
      paragraph = false;
      return;
    }
    paragraph = Boolean(value.trim()) && !ATX.test(value) && !THEMATIC.test(value) &&
      !(paragraph && SETEXT.test(value)) && !REFERENCE.test(value) &&
      (paragraph || !/^(?: {4}|\t)/.test(value));
  };
  return value => {
    const list = LIST.exec(value), thematic = THEMATIC.test(value);
    const whitespace = /^[ \t]*/.exec(value)[0];
    const width = columns(whitespace);
    if (indent !== null) {
      if (!value.trim() || width >= indent) {
        consume((" ".repeat(width) + value.slice(whitespace.length)).slice(indent));
        return true;
      }
      if (paragraph && !list && !fenceMarker(value) && !ATX.test(value) && !thematic && !/^ {0,3}>/.test(value)) return true;
    }
    indent = null;
    paragraph = false;
    fence = null;
    if (!list || thematic) return false;
    const item = listItem(value, list);
    indent = item.indent;
    consume(item.text);
    return true;
  };
}

export const SETEXT = /^ {0,3}(?:=+|-+)[ \t]*$/;
export const REFERENCE = /^ {0,3}\[(?!\^)[^\]]+\]:[ \t]*(.*)$/;
export { ATX, THEMATIC };
export const startsList = line => LIST.test(line) && !THEMATIC.test(line);

export function fenceMarker(line) {
  const marker = FENCE.exec(line);
  return marker && !(marker[1][0] === "`" && marker[2].includes("`")) ? marker : null;
}

export function closesFence(line, fence) {
  const marker = FENCE.exec(line);
  return marker && marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim();
}
