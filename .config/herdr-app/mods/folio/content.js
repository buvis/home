// Native TextView tables use the application palette, even on a light surface.
// Keep ordinary Markdown native; describe top-level tables and fences separately.
const cells = line => line.trim().replace(/^\|/, "").replace(/(?<!\\)\|$/, "")
  .split(/(?<!\\)\|/).map(cell => cell.trim());

export function contentParts(text) {
  const lines = text.replace(/\r\n/g, "\n").split("\n"), parts = [], references = [];
  let pending = [], nativeFence = null;
  const flush = () => { if (pending.length) parts.push({ markdown: pending.join("\n") }); pending = []; };
  for (let i = 0; i < lines.length; i++) {
    const marker = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(lines[i]);
    // Leave indented fences with their surrounding list/container in TextView.
    if (nativeFence) {
      pending.push(lines[i]);
      if (marker && marker[1][0] === nativeFence[0] && marker[1].length >= nativeFence.length && !marker[2].trim()) nativeFence = null;
      continue;
    }
    if (marker && lines[i].startsWith(" ") && !(marker[1][0] === "`" && marker[2].includes("`"))) {
      nativeFence = marker[1]; pending.push(lines[i]); continue;
    }
    if (marker && !(marker[1][0] === "`" && marker[2].includes("`"))) {
      flush();
      const start = i, code = [];
      while (++i < lines.length) {
        const close = /^ {0,3}(`{3,}|~{3,})[ \t]*$/.exec(lines[i]);
        if (close && close[1][0] === marker[1][0] && close[1].length >= marker[1].length) break;
        code.push(lines[i]);
      }
      parts.push({ code: code.join("\n"), language: marker[2].trim().split(/\s+/)[0].toLowerCase(),
        original: lines.slice(start, Math.min(i + 1, lines.length)).join("\n") });
      continue;
    }
    if (/^ {0,3}\[[^\]]+\]:\s*\S/.test(lines[i])) references.push(lines[i]);
    const header = cells(lines[i]), separator = cells(lines[i + 1] || "");
    if (!/^ {0,3}\S/.test(lines[i]) || !lines[i].includes("|") || header.length !== separator.length
        || !separator.every(cell => /^:?-+:?$/.test(cell))) {
      pending.push(lines[i]); continue;
    }
    flush();
    const rows = [header];
    i++;
    while (i + 1 < lines.length && /^ {0,3}\S.*\|/.test(lines[i + 1]) && !/^ {0,3}(`{3,}|~{3,})/.test(lines[i + 1])) {
      const row = cells(lines[++i]);
      rows.push(header.map((_, column) => row[column] || ""));
    }
    parts.push({ rows, align: separator.map(cell => cell.endsWith(":") ? (cell.startsWith(":") ? "center" : "right") : "left") });
  }
  flush();
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
