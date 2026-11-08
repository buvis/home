// Notes and agents: putting a note into an agent's prompt, and reading an agent's
// last reply back out.
import { agents, exec, focused, hc, home, notify, readTextFile, run, setShared, shared, terminals } from "herdr";

// ---- Which agent ------------------------------------------------------------------

// Every view calls this when it draws. Herdr redraws mods whenever focus moves, so
// shared "obsidian.agent" always holds the agent terminal that had the keyboard last.
export function track() {
  const t = focused()?.terminal;
  if (!t || !agents().some((a) => a.address === t)) return;
  if (shared("obsidian.agent")?.terminal !== t) setShared("obsidian.agent", { terminal: t, at: Date.now() });
}

// The agent a note goes to, or a reply comes from. Clicking a viewer button gives
// the viewer the keyboard, so "focused" means: the agent terminal focused now (the
// popup opens over it), else the one focused last, else the only agent in this tab,
// else the agent an agent block shows. Null when none of those exists.
export function target() {
  const list = agents(), f = focused();
  const by = (address) => (address ? list.find((a) => a.address === address) : undefined);
  const inTab = list.filter((a) => a.tab === f?.tab);
  return by(f?.terminal) ?? by(shared("obsidian.agent")?.terminal) ?? (inTab.length === 1 ? inTab[0] : null) ?? by(f?.agent) ?? null;
}

// What to call an agent: its terminal title without Claude Code's status glyphs.
export function nameOf(a) {
  const title = (a?.title ?? "").replace(/^[^\p{L}\p{N}]+/u, "").trim();
  return title || a?.program?.name || a?.address || "agent";
}

// ---- Sending a note ----------------------------------------------------------------

// Puts text into the agent's prompt as one paste, without pressing Enter. hc send
// would wrap it in <hc> tags and submit it, so this goes through Herdr's own paste:
// the clipboard holds the text for a moment, the agent's pane takes the keyboard,
// and terminal.paste pastes it the way Cmd+V does (bracketed paste, so a program
// that asks for it gets the lines as one paste). The clipboard's text is put back
// afterwards. Runs in a spawned task: cx must outlive the awaits.
export async function paste(agent, text, cx) {
  const before = cx.read_from_clipboard();
  cx.write_to_clipboard(text);
  run("pane.focus", { terminal: agent.address });
  run("terminal.paste");
  await cx.sleep(400);
  if (before !== undefined && cx.read_from_clipboard() === text) cx.write_to_clipboard(before);
}

// "From my note ..." plus the note, into the focused agent's prompt.
export async function sendNote(rel, body, cx, agent = target()) {
  if (!agent) return notify({ title: "No agent to send to", body: "Click into an agent's terminal first", level: "info", timeout: 3000 });
  const title = rel.split("/").pop().replace(/\.md$/i, "");
  const text = `From my note "${title}" (${rel}):\n\n${body.replace(/\s+$/, "")}\n`;
  await paste(agent, text, cx);
  notify({ title: `Sent to ${nameOf(agent)}`, body: "In its prompt, not submitted", level: "success", timeout: 2500 });
}

// ---- An agent's last reply ---------------------------------------------------------

const claudeDir = () => `${home()}/.claude`;

// Claude Code's session for an agent terminal. Its foreground process is Claude
// Code, which records itself in ~/.claude/sessions/<pid>.json.
async function transcriptOf(agent) {
  const term = terminals().find((t) => t.address === agent.address);
  const pid = term?.foreground?.pid;
  let session = null;
  if (pid) {
    const text = await readTextFile(`${claudeDir()}/sessions/${pid}.json`).catch(() => null);
    try { session = text ? JSON.parse(text).sessionId : null; } catch { session = null; }
  }
  if (session) {
    const r = await exec("sh", ["-c", 'ls "$1"/projects/*/"$2".jsonl 2>/dev/null | head -n 1', "sh", claudeDir(), session]).catch(() => null);
    const path = r?.stdout.trim();
    if (path) return path;
  }
  // Claude Code is running a tool, so the foreground is the tool: the newest
  // transcript in the project folder for the terminal's folder.
  const cwd = term?.foreground?.cwd ?? term?.cwd;
  if (!cwd) return null;
  const r = await exec("sh", ["-c", 'ls -t "$1"/*.jsonl 2>/dev/null | head -n 1', "sh", `${claudeDir()}/projects/${cwd.replace(/[^A-Za-z0-9]/g, "-")}`]).catch(() => null);
  return r?.stdout.trim() || null;
}

const textOf = (content) => typeof content === "string" ? content
  : Array.isArray(content) ? content.filter((b) => b?.type === "text").map((b) => b.text).join("\n\n") : "";

// The last reply in a transcript: the assistant's text since the person last wrote.
// Transcripts outgrow readTextFile's 1 MiB, so this reads the tail.
async function lastReplyIn(path) {
  const r = await exec("tail", ["-c", "1500000", path]).catch(() => null);
  if (!r || r.code !== 0) return null;
  const lines = r.stdout.split("\n").slice(1);
  const parts = [];
  for (let i = lines.length - 1; i >= 0; i--) {
    let entry;
    try { entry = JSON.parse(lines[i]); } catch { continue; }
    if (entry.isSidechain) continue;
    if (entry.type === "user") {
      const c = entry.message?.content;
      const toolResult = Array.isArray(c) && c.every((b) => b?.type === "tool_result");
      if (!toolResult && !entry.isMeta && textOf(c).trim()) { if (parts.length) break; }
      continue;
    }
    if (entry.type !== "assistant") continue;
    const text = textOf(entry.message?.content).trim();
    if (text) parts.unshift(text);
  }
  return parts.length ? parts.join("\n\n") : null;
}

// { agent, text, from: "transcript" | "screen" } for the focused agent, or { error }.
export async function lastReply(agent = target()) {
  if (!agent) return { error: "No agent: click into an agent's terminal first" };
  if (!agent.address.includes("/")) {
    const path = await transcriptOf(agent).catch(() => null);
    const text = path ? await lastReplyIn(path).catch(() => null) : null;
    if (text) return { agent, text, from: "transcript" };
  }
  // No transcript (another agent, another machine): what its screen shows.
  const r = await hc(["read", agent.address, "--lines", "120"]).catch(() => null);
  const text = r?.code === 0 ? r.stdout.replace(/\s+$/, "") : "";
  return text ? { agent, text, from: "screen" } : { error: `Couldn't read ${nameOf(agent)}` };
}
