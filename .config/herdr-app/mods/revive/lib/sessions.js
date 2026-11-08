// Finding a running agent's session from the files it writes, for one started
// before Revive's hooks were installed: the dialog can then fork it (where the
// agent forks) and show it, though it won't come back by itself. The hooks
// stay the record; this is only the fallback. Engine-only (Node's fs): the
// dialog never imports it.
//
// An agent without a finder here finds nothing, and that is fine: adding an
// agent to Revive is its entry in core.js's AGENTS, its hook target in
// revive.mjs, and optionally a finder below.

import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { validId } from "./core.js";

/** Where each agent keeps its files, from the environment. */
export function agentDirs(env = process.env) {
  const home = env.HOME || "";
  return {
    claude: env.CLAUDE_CONFIG_DIR || join(home, ".claude"),
    factory: join(home, ".factory"),
    cursor: join(home, ".cursor"),
  };
}

/**
 * The folder an agent keeps one working folder's sessions in, or null.
 * - droid:  ~/.factory/sessions/<cwd, every non-alphanumeric a dash>/<id>.jsonl
 * - cursor: ~/.cursor/chats/<md5 of the cwd>/<chat id>/store.db
 * Neither layout is documented: both were read off installed copies of those
 * CLIs, and checked by hand on macOS with droid 1.1.0 and cursor-agent
 * 2026.10.22, against sessions those versions wrote. Other versions may differ.
 */
export function sessionDir(key, dirs, cwd) {
  if (!cwd) return null;
  if (key === "droid") return join(dirs.factory, "sessions", cwd.replace(/[^A-Za-z0-9]/g, "-"));
  if (key === "cursor") return join(dirs.cursor, "chats", createHash("md5").update(cwd).digest("hex"));
  return null;
}

const mtime = (path) => { try { return statSync(path).mtimeMs; } catch { return 0; } };
const list = (dir) => { try { return readdirSync(dir); } catch { return []; } };

/**
 * The newest of `candidates` ([id, mtime]) written since the agent started.
 * `ps` gives start times to the second, so a second of slack.
 */
function newest(candidates, startedMs) {
  const since = Number.isFinite(startedMs) ? startedMs - 1000 : -Infinity;
  let best = null;
  for (const [id, ms] of candidates) {
    if (!validId(id) || ms < since) continue;
    if (!best || ms > best[1]) best = [id, ms];
  }
  return best?.[0] ?? null;
}

const FINDERS = {
  /** Claude Code keeps `sessions/<pid>.json` for each interactive process. */
  claude: ({ dirs, pid }) => {
    try {
      const id = JSON.parse(readFileSync(join(dirs.claude, "sessions", `${pid}.json`), "utf8")).sessionId;
      return validId(id) ? id : null;
    } catch { return null; }
  },
  droid: ({ dirs, cwd, startedMs }) => {
    const dir = sessionDir("droid", dirs, cwd);
    if (!dir) return null;
    const files = list(dir).filter((f) => f.endsWith(".jsonl"));
    return newest(files.map((f) => [f.slice(0, -".jsonl".length), mtime(join(dir, f))]), startedMs);
  },
  // A chat's folder is made once; its store.db is written as the chat goes on.
  cursor: ({ dirs, cwd, startedMs }) => {
    const dir = sessionDir("cursor", dirs, cwd);
    if (!dir) return null;
    return newest(list(dir).map((id) => [id, Math.max(mtime(join(dir, id)), mtime(join(dir, id, "store.db")))]), startedMs);
  },
};

/**
 * The session a running agent holds, or null. `pid` is the agent's process,
 * `cwd` its folder, `startedMs` when it started.
 */
export function findSession(key, { dirs = agentDirs(), pid = null, cwd = null, startedMs = null } = {}) {
  const find = Object.prototype.hasOwnProperty.call(FINDERS, key) ? FINDERS[key] : null;
  return find ? find({ dirs, pid, cwd, startedMs }) : null;
}
