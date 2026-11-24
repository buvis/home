// A unified diff split into files and hunks, each hunk with a stable id.
//
// This is the only place that decides what a hunk is and what it is called.
// A step of a walkthrough points at hunk ids; reading it later, a step whose
// ids are no longer in the diff is a step whose code changed. The id is a hash
// of the hunk's lines and the function name git puts after its @@, not of the
// line numbers: a line added above a hunk moves it without changing it, and
// only the hunk that was edited gets a new id.

import { shortHash } from "./hash.js";

const HUNK = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$/;

/** Git's C-style quoted path ("a/caf\303\251 x") back to text. */
export function unquote(path) {
  if (!path.startsWith("\"") || !path.endsWith("\"") || path.length < 2) return path;
  const bytes = [];
  const body = path.slice(1, -1);
  const simple = { n: 10, t: 9, r: 13, b: 8, f: 12, v: 11, a: 7, "\\": 92, "\"": 34 };
  for (let i = 0; i < body.length; i++) {
    const c = body[i];
    if (c !== "\\") { pushUtf8(bytes, body.codePointAt(i)); if (body.codePointAt(i) > 0xffff) i++; continue; }
    const next = body[i + 1];
    if (/[0-7]/.test(next)) { bytes.push(parseInt(body.slice(i + 1, i + 4), 8)); i += 3; continue; }
    bytes.push(simple[next] ?? next.charCodeAt(0));
    i++;
  }
  return decodeUtf8(bytes);
}

function pushUtf8(bytes, cp) {
  if (cp < 0x80) bytes.push(cp);
  else if (cp < 0x800) bytes.push(0xc0 | (cp >> 6), 0x80 | (cp & 63));
  else if (cp < 0x10000) bytes.push(0xe0 | (cp >> 12), 0x80 | ((cp >> 6) & 63), 0x80 | (cp & 63));
  else bytes.push(0xf0 | (cp >> 18), 0x80 | ((cp >> 12) & 63), 0x80 | ((cp >> 6) & 63), 0x80 | (cp & 63));
}

function decodeUtf8(bytes) {
  let out = "";
  for (let i = 0; i < bytes.length;) {
    const b = bytes[i];
    const n = b < 0x80 ? 1 : b >= 0xf0 ? 4 : b >= 0xe0 ? 3 : b >= 0xc0 ? 2 : 1;
    let cp = n === 1 ? b : b & (0xff >> (n + 1));
    for (let k = 1; k < n; k++) cp = (cp << 6) | ((bytes[i + k] ?? 0) & 63);
    out += String.fromCodePoint(cp);
    i += n;
  }
  return out;
}

const strip = (side, path) => {
  const p = unquote(path.replace(/\t$/, ""));
  return p.startsWith(`${side}/`) ? p.slice(2) : p;
};

/**
 * The path from `diff --git a/x b/x`. Unquoted paths may hold spaces, so when
 * both sides name the same file the line is split in its middle.
 */
export function headerPath(line) {
  const rest = line.slice("diff --git ".length);
  if (rest.startsWith("\"")) {
    const end = rest.indexOf("\" ", 1);
    const second = end === -1 ? "" : rest.slice(end + 2);
    return strip("b", second || rest);
  }
  const half = (rest.length - 1) / 2;
  if (Number.isInteger(half) && rest[half] === " " && rest.slice(2, half) === rest.slice(half + 3)) return rest.slice(half + 3);
  const at = rest.lastIndexOf(" b/");
  return at === -1 ? rest : rest.slice(at + 3);
}

/**
 * @param {string} patch `git diff` output covering any number of files
 * @param {string} scope keeps ids of two diffs of the same lines apart (staged, working)
 * @returns {{ path: string, oldPath: string|null, status: string, binary: boolean, scope: string,
 *   hunks: { id: string, header: string, oldStart: number, oldLines: number, newStart: number,
 *   newLines: number, added: number, deleted: number, lines: string[] }[] }[]}
 */
export function parseDiff(patch, scope = "diff") {
  const files = [];
  let file = null, hunk = null, seen = null, oldLeft = 0, newLeft = 0;
  // A merge conflict comes as a combined diff ("diff --cc", "@@@" hunks) in another
  // format: the file is listed, unread, and nothing in its block is parsed.
  let conflict = false;

  const closeHunk = () => {
    if (!hunk) return;
    const digest = shortHash(`${hunk.context}\n${hunk.lines.join("\n")}`);
    const n = (seen.get(digest) ?? 0) + 1;
    seen.set(digest, n);
    // Byte-identical hunks in one file (the same boilerplate edit twice) are told apart by occurrence.
    hunk.id = `${scope}:${file.path}:${digest}${n > 1 ? `-${n}` : ""}`;
    file.hunks.push(hunk);
    hunk = null;
  };
  const closeFile = () => {
    closeHunk();
    if (file?.path) files.push(file);
    file = null;
  };

  for (const line of String(patch ?? "").split("\n")) {
    // Inside a hunk every line is content, whatever it starts with: a removed "-- x" is not a header.
    if (hunk && (oldLeft > 0 || newLeft > 0)) {
      const kind = line[0];
      if (kind === "+" ) { hunk.lines.push(line); hunk.added++; newLeft--; continue; }
      if (kind === "-") { hunk.lines.push(line); hunk.deleted++; oldLeft--; continue; }
      if (kind === " " || line === "") { hunk.lines.push(line || " "); oldLeft--; newLeft--; continue; }
    }
    if (hunk && line.startsWith("\\")) { hunk.lines.push(line); continue; }
    if (line.startsWith("diff --git ")) {
      closeFile();
      conflict = false;
      file = { path: headerPath(line), oldPath: null, status: "modified", binary: false, scope, hunks: [] };
      seen = new Map();
      continue;
    }
    const combined = /^diff --(?:cc|combined) (.*)$/.exec(line);
    if (combined) {
      closeFile();
      conflict = true;
      file = { path: unquote(combined[1]), oldPath: null, status: "conflicted", binary: false, scope, hunks: [] };
      continue;
    }
    if (!file || conflict) continue;
    const m = HUNK.exec(line);
    if (m) {
      closeHunk();
      hunk = {
        id: "", header: line, context: m[5].trim(), oldStart: +m[1], oldLines: m[2] === undefined ? 1 : +m[2],
        newStart: +m[3], newLines: m[4] === undefined ? 1 : +m[4], added: 0, deleted: 0, lines: [],
      };
      oldLeft = hunk.oldLines;
      newLeft = hunk.newLines;
      continue;
    }
    closeHunk();
    if (line.startsWith("new file mode")) file.status = "added";
    else if (line.startsWith("deleted file mode")) file.status = "deleted";
    else if (line.startsWith("rename from ")) { file.status = "renamed"; file.oldPath = unquote(line.slice(12)); }
    else if (line.startsWith("rename to ")) file.path = unquote(line.slice(10));
    else if (line.startsWith("Binary files ") || line.startsWith("GIT binary patch")) file.binary = true;
    else if (line.startsWith("+++ ") && !line.startsWith("+++ /dev/null")) file.path = strip("b", line.slice(4));
    else if (line.startsWith("--- ") && !line.startsWith("--- /dev/null") && file.status !== "renamed" && !file.oldPath) {
      const old = strip("a", line.slice(4));
      if (old !== file.path) file.oldPath = old;
    }
  }
  closeFile();
  return files;
}

/** Every hunk by id, with its file's path and status. */
export function indexHunks(files) {
  const index = new Map();
  for (const file of files) for (const h of file.hunks) index.set(h.id, { ...h, path: file.path, status: file.status });
  return index;
}

/** Each diff line numbered for drawing: old number for removed lines, new for the rest. */
export function numberLines(hunk) {
  let old = hunk.oldStart, next = hunk.newStart;
  return hunk.lines.map((line) => {
    const kind = line[0];
    if (kind === "+") return { kind, number: next++, text: line.slice(1) };
    if (kind === "-") return { kind, number: old++, text: line.slice(1) };
    if (kind === "\\") return { kind: "meta", text: line };
    old++;
    return { kind: " ", number: next++, text: line.slice(1) };
  });
}

/**
 * What a hunk's header says, in words: where it starts in the new file, the
 * lines skipped since the previous hunk of the same file (null for the
 * first), and git's context line (the function or class it sits in).
 * @returns {{ at: string, skipped: number | null, context: string }}
 */
export function hunkLabel(hunk, previous = null) {
  const start = hunk.newLines === 0 ? hunk.oldStart : hunk.newStart;
  const end = previous ? previous.newStart + previous.newLines : null;
  const skipped = end === null ? null : Math.max(0, hunk.newStart - end);
  return { at: `Line ${start}`, skipped: skipped || null, context: hunk.context ?? "" };
}

/** The digits of the largest line number among these hunks: the line-number column is that wide. */
export function numberDigits(hunks) {
  let max = 1;
  for (const h of hunks) max = Math.max(max, h.oldStart + h.oldLines, h.newStart + h.newLines);
  return String(max).length;
}
