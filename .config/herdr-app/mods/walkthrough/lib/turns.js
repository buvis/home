// An agent's turns, as hooks/turn.sh records them (or the walkthrough itself,
// for an agent with no hooks: turnview.js): what the working tree was when a
// prompt was sent, and when the agent stopped. Plain functions over
// text; reading the folder is engine.js's.
//
// A turn's folder: start.json and end.json (the hook's input, as sent),
// start.meta and end.meta (`key=value` lines, written last), start.big and
// end.big (the new files over 1 MB each snapshot left out), objects/.

/** The hook's JSON → { prompt, session, cwd, event }. A prompt cut short (the listing reads a bounded head) is still recovered. */
export function parseHook(text) {
  const s = String(text ?? "");
  let j = null;
  try { j = JSON.parse(s); } catch { j = null; }
  const get = (name) => {
    if (j && typeof j[name] === "string") return j[name];
    // The string up to where the text was cut, or its closing quote.
    const m = new RegExp(`"${name}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)`).exec(s);
    if (!m) return null;
    try { return JSON.parse(`"${m[1].replace(/\\(u[0-9a-fA-F]{0,3})?$/, "")}"`); } catch { return m[1]; }
  };
  return { prompt: unwrap(get("prompt") ?? ""), session: get("session_id"), cwd: get("cwd"), event: get("hook_event_name") };
}

/** A prompt pasted in by `hc send` (another agent, or the walkthrough's own comments) comes wrapped as <hc from="t3">…</hc>. */
export const unwrap = (prompt) => /^<hc from="[^"]*">([\s\S]*?)(?:<\/hc>\s*)?$/.exec(prompt)?.[1] ?? prompt;

/** `key=value` lines → an object. */
export function parseMeta(text) {
  const out = {};
  for (const line of String(text ?? "").split("\n")) {
    const i = line.indexOf("=");
    if (i > 0) out[line.slice(0, i)] = line.slice(i + 1).trim();
  }
  return out;
}

const SHA = /^[0-9a-f]{40,64}$/;

// The listing engine.js prints: per turn "\x1e<name>\n", then per file "\x1f<file>\n<its text>".
// Claude Code's JSON escapes control characters, so neither separator can come from a prompt.
export const RECORD = "\x1e", FILE = "\x1f";

const lines = (text) => (text == null ? [] : String(text).split("\n").filter(Boolean));

/**
 * The folder's listing → turns, newest first: { id, dir, started, ended,
 * startTree, endTree, frozen, startBig, endBig, session, terminal, prompt }.
 * A turn whose start snapshot isn't written yet (or failed) is left out.
 * `frozen`: the end was taken by the walkthrough, not by a Stop hook.
 * `recorded`: the walkthrough recorded the whole turn (no hooks).
 */
export function parseListing(out, folder) {
  const turns = [];
  for (const record of String(out ?? "").split(RECORD).slice(1)) {
    const nl = record.indexOf("\n");
    const id = (nl < 0 ? record : record.slice(0, nl)).trim();
    if (!/^\d+-\d+$/.test(id)) continue;
    const files = {};
    for (const part of (nl < 0 ? "" : record.slice(nl + 1)).split(FILE).slice(1)) {
      const at = part.indexOf("\n");
      files[at < 0 ? part : part.slice(0, at)] = at < 0 ? "" : part.slice(at + 1);
    }
    const start = parseMeta(files["start.meta"]), end = parseMeta(files["end.meta"]);
    if (!SHA.test(start.tree ?? "")) continue;
    const hook = parseHook(files["start.json"]);
    turns.push({
      id, dir: `${folder}/${id}`,
      started: Number(start.started) * 1000 || Number(id.split("-")[0]) * 1000,
      ended: SHA.test(end.tree ?? "") ? Number(end.ended) * 1000 || null : null,
      startTree: start.tree, endTree: SHA.test(end.tree ?? "") ? end.tree : null, frozen: end.interrupted === "1",
      startBig: lines(files["start.big"]), endBig: lines(files["end.big"]),
      session: start.session || hook.session || null, terminal: start.terminal || null, prompt: hook.prompt,
      recorded: start.recorder === "1",
    });
  }
  return sortTurns(turns);
}

/** Newest first, by when they started, then by name. */
export const sortTurns = (turns) => [...turns].sort((a, b) => b.started - a.started || b.id.localeCompare(a.id));

// How long Claude Code lets each hook run (hookSettings): a Stop hook has written end.meta by then, or never will.
export const HOOK_TIMEOUT = 30;
export const HOOK_WAIT = HOOK_TIMEOUT * 1000 + 15_000;

// A turn without an end is taken as over once its agent has been quiet this long (or, with no
// agent to ask, once it is this old). Kept short: its end is frozen then, and edits made after
// the agent stopped would be counted as the agent's.
export const QUIET = HOOK_WAIT;
export const UNKNOWN = 12 * 3600_000;

/**
 * Where each turn ended. Claude Code runs no Stop hook for a turn stopped with
 * Esc, or for an agent quit mid-turn, so a turn without an end ended when the
 * next prompt of its session, or of its terminal (`/clear` starts a new
 * session there), was sent. Without one it is still running and read up to
 * now, until its agent has been quiet for QUIET: then it is "stale", and the
 * walkthrough freezes its end (engine.js closeTurn).
 *
 * `idleSince(terminal)`: null while that agent works (or waits on the person),
 * the time it was first seen otherwise, undefined when there is no agent to ask.
 * @returns {any[]} the turns, each with `endTree`, `endDir` (whose objects hold it),
 *   `endBig` and `state`: "done" | "interrupted" | "running" | "stale"
 */
export function resolveEnds(turns, { idleSince = () => undefined, now = Date.now() } = {}) {
  const sorted = sortTurns(turns);
  return sorted.map((t, i) => {
    if (t.endTree) return { ...t, endDir: t.dir, state: t.frozen ? "interrupted" : "done" };
    const next = sorted.slice(0, i).reverse().find((n) => (t.session && n.session === t.session) || (t.terminal && n.terminal === t.terminal));
    if (next) return { ...t, endTree: next.startTree, endDir: next.dir, endBig: next.startBig, ended: next.started, state: "interrupted" };
    const since = t.terminal ? idleSince(t.terminal) : undefined;
    const over = typeof since === "number" ? now - Math.max(since, t.started) > QUIET : since === undefined && now - t.started > UNKNOWN;
    return { ...t, endDir: null, endBig: null, state: over ? "stale" : "running" };
  });
}

/** Whether a turn is still open: read up to now, never written up without a click. */
export const isOpen = (t) => t.state === "running" || t.state === "stale";

/**
 * Whether a turn's walkthrough may be written without a click: finished, and
 * ended by its agent. A turn the walkthrough froze (no Stop hook came) ends
 * when the walkthrough noticed, so it may hold edits made after the agent
 * stopped; it is written only on Generate.
 */
export const autoWritable = (t) => Boolean(t) && !isOpen(t) && !t.frozen;

/**
 * The turn to show after listing again: the one picked by hand while it is
 * still listed, else the one pickTurn picks (and it no longer counts as picked).
 * @returns {{ turn: any, pinned: boolean }}
 */
export function keepTurn(turns, shown, pinned, terminal = null) {
  const kept = pinned && shown ? turns.find((t) => t.id === shown.id) : null;
  return kept ? { turn: kept, pinned: true } : { turn: pickTurn(turns, terminal), pinned: false };
}

/** The turn to show first: the newest of the terminal it was opened over, else the newest. */
export function pickTurn(turns, terminal = null) {
  return (terminal && turns.find((t) => t.terminal === terminal)) || turns[0] || null;
}

/** The newest finished turn, of these terminals when given; null when the newest is still open. */
export function lastFinished(turns, terminals = null) {
  const mine = terminals ? turns.filter((t) => terminals.includes(t.terminal)) : turns;
  return mine[0] && !isOpen(mine[0]) ? mine[0] : null;
}

/** A prompt's first line with text in it, cut to `max` characters. */
export function firstLine(prompt, max = 80) {
  const line = String(prompt ?? "").split("\n").map((l) => l.trim()).find(Boolean) ?? "";
  return line.length > max ? `${line.slice(0, max - 1).trimEnd()}…` : line;
}

/** "just now", "5 min ago", "3 h ago", "2 days ago". */
export function ago(ms, now = Date.now()) {
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

/** The source a turn is read as (see sources.js). */
export const turnSource = (t) => ({
  kind: "turn", id: t.id, dir: t.dir, startTree: t.startTree, endTree: isOpen(t) ? null : t.endTree, endDir: t.endDir,
  startBig: t.startBig ?? [], endBig: isOpen(t) ? null : t.endBig ?? [], prompt: t.prompt,
});

/** The listing script engine.js runs in a repository's turns folder ($0). Prompts are read up to 64 KB. */
export const LISTING = `cd "$0" 2>/dev/null || exit 0
for d in $(ls -1 | grep -E '^[0-9]+-[0-9]+$'); do
  printf '\\036%s\\n' "$d"
  for f in start.meta end.meta start.big end.big; do [ -f "$d/$f" ] && { printf '\\037%s\\n' "$f"; cat "$d/$f"; }; done
  [ -f "$d/start.json" ] && { printf '\\037start.json\\n'; head -c 65536 "$d/start.json"; }
done
exit 0`;

/**
 * The hooks to add to ~/.claude/settings.json, for a turn.sh at `script`.
 * `compact`: one line per hook, as the README shows them; the same JSON.
 */
export function hookSettings(script, { compact = false } = {}) {
  const command = (event) => `sh "${script}" ${event}`;
  if (compact) {
    const line = (event) => `[{ "hooks": [{ "type": "command", "command": ${JSON.stringify(command(event))}, "timeout": ${HOOK_TIMEOUT} }] }]`;
    return `{\n  "hooks": {\n    "UserPromptSubmit": ${line("start")},\n    "Stop": ${line("stop")}\n  }\n}`;
  }
  const hook = (event) => [{ hooks: [{ type: "command", command: command(event), timeout: HOOK_TIMEOUT }] }];
  return JSON.stringify({ hooks: { UserPromptSubmit: hook("start"), Stop: hook("stop") } }, null, 2);
}

/**
 * The script engine.js runs to claim recording a repository's turns: $0 the
 * lock folder, $1 this window. Prints "ok" while the claim is this window's.
 * mkdir is atomic, so two windows can't both take a free lock; a claim not
 * renewed for a minute (its window closed) is taken over.
 */
export const RECORDER_LOCK = `d="$0"
if mkdir "$d" 2>/dev/null; then echo "$1" > "$d/owner"; echo ok; exit 0; fi
if [ "$(cat "$d/owner" 2>/dev/null)" = "$1" ]; then touch "$d/owner"; echo ok; exit 0; fi
[ -n "$(find "$d" "$d/owner" -maxdepth 0 -mmin -1 2>/dev/null)" ] && exit 0
rm -rf "$d"
mkdir "$d" 2>/dev/null && { echo "$1" > "$d/owner"; echo ok; }
exit 0`;
