// What was typed into pi, codex or opencode working in a repository: the
// prompts a change is matched against, and the turns recorded for agents that
// have no hooks. Claude Code is read apart (lib/task.js). Plain functions over
// text; reading the files and the database is engine.js's.
//
// Everything is local: pi's and codex's session files, and opencode's SQLite
// database (read by lib/opencode-prompts.py).

import { isNoise, clip, MAX_MESSAGE_CHARS } from "./task.js";

const cap = (t) => clip(t, MAX_MESSAGE_CHARS);
const textOf = (content) => {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.filter((b) => b && typeof b.text === "string" &&
    (b.type === "text" || b.type === "input_text" || b.type === "output_text")).map((b) => b.text).join("\n");
};

/** Whether a path is the repository's top folder or inside it. */
export const inRepo = (path, top) => typeof path === "string" && (path === top || path.startsWith(`${top}/`));

/** Whether a message is something a person asked for. */
const asked = (text) => {
  const t = String(text ?? "").trim();
  if (!t || isNoise(t)) return false;
  // codex sends the repository's instructions as the first user message.
  if (/^# AGENTS\.md instructions/i.test(t) || /^<INSTRUCTIONS>/i.test(t)) return false;
  if (t.includes("<user_instructions>") || t.startsWith("<environment_context>")) return false;
  return true;
};

/**
 * The script engine.js runs to find the sessions written in the last $0
 * minutes under the folders it is given ($1…), newest 300 per folder: per file
 * "\x1e<path>\n<mtime seconds>\n<its first line, up to 64 KB>\n". The first
 * line of a pi or codex session names its working folder.
 */
export const SESSION_HEADS = `m="$0"
for root; do
  [ -d "$root" ] || continue
  find "$root" -name '*.jsonl' -type f -mmin "-$m" 2>/dev/null | head -300 | while IFS= read -r f; do
    printf '\\036%s\\n%s\\n' "$f" "$(date -r "$f" +%s 2>/dev/null)"
    head -n 1 "$f" | head -c 65536
    printf '\\n'
  done
done
exit 0`;

/**
 * SESSION_HEADS' output → { path, mtime (ms), cwd }. The working folder is
 * found in the text, so a first line cut at 64 KB still gives it.
 */
export function parseSessionHeads(out) {
  const heads = [];
  for (const record of String(out ?? "").split("\x1e").slice(1)) {
    const [path, mtime, ...rest] = record.split("\n");
    const m = /"cwd"\s*:\s*"((?:[^"\\]|\\.)*)"/.exec(rest.join("\n"));
    let cwd = null;
    if (m) { try { cwd = JSON.parse(`"${m[1]}"`); } catch { cwd = m[1]; } }
    if (path) heads.push({ path, mtime: (Number(mtime) || 0) * 1000, cwd });
  }
  return heads;
}

/** pi: a JSONL session whose first line ("type":"session") has the cwd. */
export function parsePiSession(text, { top, since = 0, session = null }) {
  let cwd = null;
  const out = [];
  for (const line of String(text ?? "").split("\n")) {
    if (!line.trim()) continue;
    let o;
    try { o = JSON.parse(line); } catch { continue; }
    if (o?.type === "session") { cwd = typeof o.cwd === "string" ? o.cwd : cwd; continue; }
    if (o?.type !== "message" || o.message?.role !== "user") continue;
    const body = textOf(o.message.content).trim();
    if (!asked(body)) continue;
    const at = Date.parse(o.timestamp ?? "") || Number(o.message?.timestamp) || 0;
    if (at < since) continue;
    out.push({ at, text: cap(body), session, agent: "pi" });
  }
  return inRepo(cwd, top) ? out : [];
}

/** codex: a JSONL rollout; session_meta.payload.cwd, and response_item messages with role "user". */
export function parseCodexSession(text, { top, since = 0, session = null }) {
  let cwd = null;
  const out = [];
  for (const line of String(text ?? "").split("\n")) {
    if (!line.trim()) continue;
    let o;
    try { o = JSON.parse(line); } catch { continue; }
    if (o?.type === "session_meta") { cwd = o.payload?.cwd ?? cwd; continue; }
    if (o?.type !== "response_item" || o.payload?.type !== "message" || o.payload?.role !== "user") continue;
    const body = textOf(o.payload.content).trim();
    if (!asked(body)) continue;
    const at = Date.parse(o.timestamp ?? "") || 0;
    if (at < since) continue;
    out.push({ at, text: cap(body), session, agent: "codex" });
  }
  return inRepo(cwd, top) ? out : [];
}

/**
 * lib/opencode-prompts.py's output → { prompts, active, error }. `error`: the
 * database is there but couldn't be read as expected (its schema changed),
 * told apart from having no prompts.
 */
export function parseOpencode(text, since = 0) {
  let o;
  try { o = JSON.parse(text || "{}"); } catch { return { prompts: [], active: 0, error: "unreadable output" }; }
  if (o?.error) return { prompts: [], active: 0, error: String(o.error) };
  const rows = Array.isArray(o?.prompts) ? o.prompts : [];
  const prompts = rows.filter((r) => asked(r?.text))
    .map((r) => ({ at: Number(r.at) || 0, text: cap(r.text), session: r.session ? `opencode:${r.session}` : null, agent: "opencode" }))
    .filter((r) => r.at >= since);
  return { prompts, active: Number(o?.active) || 0, error: null };
}

/** Several agents' prompts in one list, oldest first, the same text at the same moment once. */
export function mergePrompts(lists) {
  const seen = new Set();
  const out = [];
  for (const m of lists.flat()) {
    const key = `${m.at}\n${m.text}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(m);
  }
  return out.sort((a, b) => a.at - b.at);
}
