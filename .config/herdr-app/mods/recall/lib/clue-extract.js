// The Clues category: find a pane by what it runs, what it
// printed, or the port or process it owns. Pure functions; main.js fetches
// the data (herdr-core, ps, lsof) and hands it in.
//
// Filter prefixes need one space after the label, `.` searches buffers.
// The text after a prefix uses the query syntax of every list (fuzzy.js):
// on state rows as anywhere, and on buffers line by line with plain terms
// read literally.

import { literalGroups, literalMayHold, matchFields, matchLiteralGroups, parseQuery } from "./fuzzy.js";

export const CLUE_ORDER = { ssh: 0, cmd: 1, term: 2, file: 3, port: 4, pid: 5 };
const CLUE_LABELS = ["ssh", "cmd", "term", "file", "port", "pid"];

const SHELLS = new Set(["zsh", "bash", "sh", "dash", "ksh", "tcsh", "fish", "csh", "ash", "nu", "elvish", "xonsh", "pwsh", "powershell"]);
const EDITORS = new Set(["nvim", "vim", "vi", "code", "cursor", "neovim", "emacs", "helix", "hx", "nano", "micro", "sublime", "kak", "lvim", "zed"]);
const SSH_BINS = new Set(["ssh", "mosh", "rsh", "rlogin", "tssh"]);
const SSH_VALUE_OPTS = ["-p", "-l", "-b", "-E", "-e", "-F", "-G", "-J", "-W", "-Q", "-S", "-D", "-L", "-R", "-O", "-o", "-c", "-i", "-I", "-w", "-B", "-K", "-M", "-P", "-U"];
const EDITOR_SKIP_NEXT = new Set(["-u", "-U", "-i", "-S", "-c", "-l", "-f", "--cmd"]);
const SHELL_RESIDUE = /['"`();|&$]/;

export const EXCERPT_PRE = 14;
export const EXCERPT_POST = 80;
export const CONTENT_CAP = 256 * 1024;

function tokens(cmd) {
  return (cmd ?? "").trim().split(/\s+/u).filter(Boolean);
}

function programOf(cmd) {
  const first = tokens(cmd)[0];
  if (!first) return "";
  const bare = first.startsWith("-") ? first.slice(1) : first;
  return bare.slice(bare.lastIndexOf("/") + 1);
}

/** A bare shell (`-zsh`, `/bin/bash`) says nothing a cwd row doesn't. */
export function commandIsShell(cmd) {
  return SHELLS.has(programOf(cmd));
}

export function commandIsEditor(cmd) {
  return EDITORS.has(programOf(cmd));
}

/**
 * Where an ssh-like command connects: `user@host`, `host:port`, or null.
 * Options that take a value are skipped with it, so `-J jump` is not the
 * destination; only `-p` and `-l` are kept.
 */
export function parseSshTarget(cmd) {
  const ts = tokens(cmd);
  if (ts.length < 2 || !SSH_BINS.has(programOf(cmd))) return null;
  let port = null;
  let user = null;
  let dest = null;
  const keep = (opt, value) => {
    if (opt === "-p") port = value;
    else if (opt === "-l") user = value;
  };
  for (let i = 1; i < ts.length; i++) {
    const t = ts[i];
    if (t === "--") { dest = ts[i + 1] ?? null; break; }
    if (t.startsWith("-") && t.length > 1) {
      const joined = SSH_VALUE_OPTS.find((o) => t.startsWith(o) && t.length > o.length);
      if (joined) { keep(joined, t.slice(joined.length)); continue; }
      if (SSH_VALUE_OPTS.includes(t)) { keep(t, ts[i + 1]); i++; continue; }
      continue;
    }
    dest = t;
    break;
  }
  if (!dest) return null;
  let target = user && !dest.includes("@") ? `${user}@${dest}` : dest;
  if (port && !target.includes(":")) target = `${target}:${port}`;
  return target;
}

/** The host part of an ssh target: after the last `@`, port kept. */
export function sshHost(target) {
  return target.slice(target.lastIndexOf("@") + 1);
}

/** A title shaped like a shell prompt (`me@mac:~/x`) means the editor has exited. */
export function isShellPromptTitle(title) {
  const t = (title ?? "").trim();
  const at = t.indexOf("@");
  if (at <= 0 || /\s/u.test(t.slice(0, at))) return false;
  const colon = t.indexOf(":", at + 1);
  if (colon <= 0 || /\s/u.test(t.slice(at + 1, colon))) return false;
  const after = t.slice(colon + 1).trimStart();
  return after.startsWith("~") || after.startsWith("/") || after.startsWith(".");
}

/** The file an editor command opens: `{ path, line }`, or null. */
export function parseEditorTarget(cmd) {
  const ts = tokens(cmd);
  if (ts.length < 2) return null;
  let line = null;
  let path = null;
  for (let i = 1; i < ts.length; i++) {
    const t = ts[i];
    if (/^\+\d+$/u.test(t)) { line = Number(t.slice(1)); continue; }
    if (t.startsWith("+")) continue;
    if (t.startsWith("-")) { if (EDITOR_SKIP_NEXT.has(t)) i++; continue; }
    if (SHELL_RESIDUE.test(t)) continue;
    path = t;
    break;
  }
  if (!path) return null;
  const m = /^(.*):(\d+)$/u.exec(path);
  if (m && m[1]) return { path: m[1], line: Number(m[2]) };
  return { path, line };
}

function absolute(path, cwd) {
  if (path.startsWith("/") || path.startsWith("~") || !cwd) return path;
  return `${cwd.replace(/\/+$/u, "")}/${path}`;
}

/**
 * Whether a pane's buffer counts as a file or a terminal, and what to show
 * as its context: the edited file (absolute, `:line`) or the pane's cwd.
 */
export function bufferKind(state, title) {
  const editor = state?.command != null
    ? (commandIsEditor(state.command) ? state.command : null)
    : (commandIsEditor(title) ? title : null);
  if (editor && !isShellPromptTitle(title)) {
    const target = parseEditorTarget(editor);
    if (target) return { kind: "file", file: absolute(target.path, state?.cwd), context: absolute(target.path, state?.cwd) + (target.line ? `:${target.line}` : "") };
    return { kind: "file", file: null, context: state?.cwd || "-" };
  }
  return { kind: "term", file: null, context: state?.cwd || "-" };
}

/** Escape sequences out of terminal text: CSI, OSC and charset selects. */
export function stripAnsi(text) {
  return (text ?? "")
    .replace(/\u001b\[[0-?]*[ -/]*[@-~]/gu, "")
    .replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)/gu, "")
    .replace(/\u001b[()][A-Za-z0-9]/gu, "");
}

/** Terminal text as kept for searching: no escapes, capped, null when blank. */
export function cleanBuffer(text) {
  const plain = stripAnsi(text);
  if (!plain.trim()) return null;
  const cs = Array.from(plain);
  return cs.length > CONTENT_CAP ? cs.slice(0, CONTENT_CAP).join("") : plain;
}

/**
 * The first line of `content` where the query `needle` holds, read
 * literally (see literalGroups): a line where every term matches its case
 * exactly wins, else the first under smart case. Keeps 14 characters before
 * the first matched term and 80 after its end, with `…` where the line was
 * cut. Returns `{ text, hit: [start, end), line }` with `hit` in code points
 * of `text` and `line` the whole line, or null.
 */
export function contentExcerpt(content, needle) {
  if (!content || parseQuery(needle).length === 0) return null;
  const lines = content.split("\n").filter((l) => l.trim());
  for (const exactCase of [true, false]) {
    const groups = literalGroups(needle, exactCase);
    if (!literalMayHold(content, groups)) continue; // no line can hold it
    for (const line of lines) {
      const hit = matchLiteralGroups(line, groups);
      if (hit) return excerpt(line, hit[0] ?? 0, hit.length);
    }
  }
  return null;
}

function excerpt(line, at, length) {
  const cs = Array.from(line);
  const clean = (c) => (c === "\t" || /\p{Cc}/u.test(c) ? " " : c);
  const preFrom = Math.max(0, at - EXCERPT_PRE);
  const postTo = Math.min(cs.length, at + length + EXCERPT_POST);
  const left = preFrom > 0 ? "…" : "";
  const right = postTo < cs.length ? "…" : "";
  const pre = cs.slice(preFrom, at).map(clean).join("");
  const body = cs.slice(at, postTo).map(clean).join("");
  const hitStart = Array.from(left + pre).length;
  return { text: left + pre + body + right, hit: [hitStart, hitStart + length], line };
}

/**
 * Clues' filter prefix. Returns `{ filter, needle }` where filter is
 * null (plain query), "content" (a leading `.`), a clue label (ssh, cmd,
 * term, file, port or pid). A label must be followed by exactly one space; the
 * needle is the rest, untrimmed. `.file x` is the same as `file x`.
 */
export function parseFilter(query) {
  let rest = query ?? "";
  let content = false;
  if (rest.startsWith(".")) { rest = rest.slice(1); content = true; }
  for (const label of CLUE_LABELS) {
    if (rest.startsWith(`${label} `)) return { filter: label, label, needle: rest.slice(label.length + 1) };
  }
  return { filter: content ? "content" : null, label: content ? "." : null, needle: rest };
}

/** `ps -eo pid=,ppid=,command=` as a Map pid → { ppid, command }. */
export function parsePs(text) {
  const procs = new Map();
  for (const line of (text ?? "").split("\n")) {
    const m = /^\s*(\d+)\s+(\d+)?\s*(.*)$/u.exec(line);
    if (!m) continue;
    procs.set(Number(m[1]), { ppid: m[2] === undefined ? null : Number(m[2]), command: m[3].trim() });
  }
  return procs;
}

/** `lsof -nP -iTCP -sTCP:LISTEN -F pn` as `[{ port, pid, addr }]`, duplicates dropped. */
export function parseLsof(text) {
  const out = [];
  const seen = new Set();
  let pid = null;
  for (const line of (text ?? "").split("\n")) {
    if (line.startsWith("p")) { pid = Number(line.slice(1)); continue; }
    if (!line.startsWith("n") || pid === null) continue;
    const addr = line.slice(1);
    const port = Number(addr.slice(addr.lastIndexOf(":") + 1));
    if (!Number.isInteger(port) || port < 0 || port > 65535) continue;
    const key = `${port}|${pid}|${addr}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ port, pid, addr });
  }
  return out;
}

/**
 * The pane whose shell started `pid`: the pid itself is a pane's shell, or
 * one of its ancestors is. `shells` maps shell pid → pane id.
 */
export function paneForPid(pid, shells, procs) {
  if (shells.has(pid)) return shells.get(pid);
  const seen = new Set();
  let cur = pid;
  for (;;) {
    const ppid = procs.get(cur)?.ppid;
    if (ppid === null || ppid === undefined) return null;
    if (shells.has(ppid)) return shells.get(ppid);
    if (seen.has(cur)) return null;
    seen.add(cur);
    cur = ppid;
  }
}

/** Orders Clues rows: a detail hit outranks hits elsewhere; ties keep recency. */
export function rankClues(rows, query) {
  if (!parseQuery(query).length) return rows.map((item) => ({ item, hits: {} }));
  const out = [];
  rows.forEach((item, order) => {
    const full = matchFields(item.fields, query);
    if (!full) return;
    const detail = matchFields(item.fields.filter((f) => f.key === "title"), query);
    out.push({ item, hits: full.hits, primary: detail?.score ?? 0, secondary: full.score, order });
  });
  out.sort((a, b) => b.primary - a.primary || b.secondary - a.secondary || a.order - b.order);
  return out.map(({ item, hits }) => ({ item, hits }));
}
