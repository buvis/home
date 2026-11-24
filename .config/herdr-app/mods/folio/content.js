import { ATX, SETEXT, THEMATIC, REFERENCE, fenceMarker, closesFence, headingIndex, listContext, startsList } from "./headings.js";

// Native TextView tables use the application palette, even on a light surface.
const cells = line => line.trim().replace(/^\|/, "").replace(/(?<!\\)\|$/, "")
  .split(/(?<!\\)\|/).map(cell => cell.trim());

function htmlBlockEnd(line, inParagraph) {
  if (/^ {0,3}<!--/.test(line)) return /-->/;
  if (/^ {0,3}<\?/.test(line)) return /\?>/;
  if (/^ {0,3}<!\[CDATA\[/.test(line)) return /\]\]>/;
  if (/^ {0,3}<![A-Z]/.test(line)) return />/;
  const raw = /^ {0,3}<(script|pre|style|textarea)(?:[\t >]|$)/i.exec(line);
  if (raw) return new RegExp(`</${raw[1]}>`, "i");
  if (!inParagraph && /^ {0,3}<\/?[a-z][\w-]*(?:[ \t]+[^<>]*)?\s*\/?>[ \t]*$/i.test(line)) return /^\s*$/;
  return null;
}

function referenceEnd(lines, i, remainder) {
  const destination = /^(?:<[^<>]*>|[^<>\s]+)(?:[ \t]+(?:"[^"]*"|'[^']*'|\([^()]*\)))?$/;
  const next = lines[i + 1]?.trim();
  if (!remainder) {
    if (!next || !destination.test(next) || fenceMarker(next) || ATX.test(next) || THEMATIC.test(next)) return -1;
    i++;
  }
  const title = lines[i + 1]?.trim();
  if (title && /^(?:"[^"]*"|'[^']*'|\([^()]*\))$/.test(title)) i++;
  return i;
}

export function contentParts(text) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n"), parts = [], references = [];
  const makeHeading = headingIndex(), inList = listContext();
  let start = 0, paragraph = null;
  const flush = end => {
    if (end > start && lines.slice(start, end).some(line => line.trim()))
      parts.push({ markdown: lines.slice(start, end).join("\n"), line: start + 1 });
    start = end;
    paragraph = null;
  };

  const addHeading = (begin, end, title, level) => {
    flush(begin);
    const heading = makeHeading(title, level, begin + 1);
    parts.push({ markdown: lines.slice(begin, end).join("\n"), line: heading.line, heading });
    start = end;
  };

  // Render YAML with the normal code block, while keeping all source line numbers.
  if (lines[0] === "---") {
    const end = lines.findIndex((line, i) => i > 0 && /^---[ \t]*$/.test(line));
    if (end > 1) {
      const code = lines.slice(1, end).join("\n");
      parts.push({ code, language: "yaml", original: "```yaml\n" + code + "\n```", line: 1, closed: true });
      start = end + 1;
    }
  }
  for (let i = start; i < lines.length; i++) {
    const line = lines[i];
    if (inList(line)) { paragraph = null; continue; }

    const htmlEnd = htmlBlockEnd(line, paragraph !== null);
    if (htmlEnd) {
      while (!htmlEnd.test(lines[i]) && i + 1 < lines.length) i++;
      paragraph = null;
      continue;
    }

    const marker = fenceMarker(line);
    if (marker) {
      const begin = i, indent = line.indexOf(marker[1]), language = marker[2].trim().split(/\s+/)[0].toLowerCase();
      while (++i < lines.length && !closesFence(lines[i], marker[1])) {}
      if (!indent || language === "mermaid") {
        flush(begin);
        const padding = new RegExp(`^ {0,${indent}}`);
        const code = lines.slice(begin + 1, i).map(line => line.replace(padding, "")).join("\n");
        parts.push({ code, language, original: lines.slice(begin, i + 1).join("\n"), line: begin + 1, closed: i < lines.length });
        start = i + 1;
      }
      paragraph = null;
      continue;
    }

    const atx = ATX.exec(line);
    if (atx) {
      addHeading(i, i + 1, (atx[2] || "").replace(/(?:^|[ \t]+)#+[ \t]*$/, ""), atx[1].length);
      continue;
    }
    if (paragraph !== null && SETEXT.test(line)) {
      const begin = paragraph;
      addHeading(begin, i + 1, lines.slice(begin, i).map(line => line.trim()).join(" "), line.trim()[0] === "=" ? 1 : 2);
      continue;
    }

    const reference = REFERENCE.exec(line);
    const endReference = reference && referenceEnd(lines, i, reference[1]);
    if (reference && endReference >= i) {
      references.push(lines.slice(i, endReference + 1).join("\n"));
      i = endReference;
      paragraph = null;
      continue;
    }
    const header = cells(line), separator = cells(lines[i + 1] || "");
    if (/^ {0,3}[^>\s]/.test(line) && line.includes("|") && header.length === separator.length &&
        separator.every(cell => /^:?-+:?$/.test(cell))) {
      flush(i);
      const rows = [header], first = ++i;
      while (i + 1 < lines.length && /^ {0,3}[^>\s].*\|/.test(lines[i + 1]) &&
          !fenceMarker(lines[i + 1]) && !ATX.test(lines[i + 1]) && !startsList(lines[i + 1])) {
        const row = cells(lines[++i]);
        rows.push(header.map((_, column) => row[column] || ""));
      }
      parts.push({ rows, align: separator.map(cell => cell.endsWith(":") ? (cell.startsWith(":") ? "center" : "right") : "left"), line: first });
      start = i + 1;
      continue;
    }
    if (!line.trim() || THEMATIC.test(line) || /^ {0,3}>/.test(line)) paragraph = null;
    else if (paragraph === null && /^ {0,3}\S/.test(line)) paragraph = i;
  }
  flush(lines.length);
  // Each native fragment needs the document's reference-link definitions.
  if (parts.length > 1 && references.length) {
    const definitions = "\n\n" + references.join("\n");
    for (const part of parts) {
      if (part.markdown !== undefined) part.markdown += definitions;
      else if (part.rows) part.rows = part.rows.map(row => row.map(cell => cell + definitions));
    }
  }
  return parts;
}
