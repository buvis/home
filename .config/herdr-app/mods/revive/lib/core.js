// What Revive knows about agents, sessions and terminals, as plain functions.
// Shared by the dialog (main.js) and the engine (revive.mjs), so nothing here
// may touch herdr, node or the file system.
//
// A session is remembered as labels on the herdr-core terminal it runs in.
// Labels live in the core, next to the terminal, so they survive the app
// closing, the core restarting and the machine rebooting, and they go away
// with the terminal.

export const PREFIX = "revive.";
// `ended` is no longer written; it stays here so clearing removes it from older records.
export const KEYS = ["agent", "session", "cwd", "flags", "env", "needs", "transcript", "shell", "since", "at", "ended", "resumed", "failed", "auto"];

/**
 * How an agent's SessionEnd reason is taken: "ignore" (the same process starts
 * another session at once, and its SessionStart records it), "keep" (a signal,
 * a crash: worth bringing back) or "forget" (the person ended it).
 * Claude Code's reasons, which Codex, Factory Droid and pi's extension share.
 */
/** A value flag that names one of the person's own profiles, not a path. */
const NAME = { arg: 1, ok: (v) => /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(v) };


const claudeEnd = (reason) => (reason === "clear" || reason === "resume" ? "ignore" : reason === "other" ? "keep" : "forget");

/**
 * The agents Revive can bring back, one entry each:
 * - `name`     what the person reads
 * - `bin`      the program a resume or fork runs
 * - `bins`     the program names it is known by on a command line (default: `bin`)
 * - `match`    optional: a stricter test of one command-line word, for a name
 *              too generic to trust on its own
 * - `apps`     the names it reports itself by (OSC 7501 `app`)
 * - `resume`   the command line that resumes a session
 * - `fork`     the one that copies it into a new session, or null when the
 *              agent can't (the dialog then offers no fork)
 * - `end`      how its SessionEnd reasons are taken (default: claudeEnd)
 * - `carry`    the launch flags a resume or fork keeps, so a session that ran
 *              with another model comes back the way it was: 0 for a switch,
 *              1 for a flag that takes a value, 2 for one that takes every
 *              value up to the next flag, or `{ arg: 1, ok }` for a value
 *              flag whose value `ok(value)` must accept. Anything else on the
 *              original command line (a first prompt, `--resume` itself, a
 *              secret) is left behind. The same list filters the flags read
 *              back from the terminal's labels (see `readRecord`).
 *
 * What is carried and what never is, and why: the flags travel through a
 * terminal label, which anything that can talk to herdr-core can write, and
 * they come back unattended after a reboot.
 * - Permission and sandbox modes are carried as recorded
 *   (`--dangerously-skip-permissions`, `--permission-mode`, Codex's
 *   approval and sandbox flags, `--force`, `--auto-approve`, ...). A label
 *   writer already runs as the person, and a resumed agent waits for input
 *   before it acts: the session comes back the way it ran.
 * - Never carried: flags that make the agent load something it would not
 *   load otherwise, because that runs code or instructions at once on
 *   resume: settings, hooks, extensions, plugins or MCP servers
 *   (`--settings`, `--mcp-config`, `--plugin-dir`, `-e/--extension`,
 *   `--hook`, `--config`, `--approve-mcps`, Codex's
 *   `--dangerously-bypass-hook-trust`), extra instructions
 *   (`--system-prompt`, `--append-system-prompt`, `--skill`) and extra
 *   folders (`--add-dir`, omp's `--allow-home`, Cursor's `--workspace`).
 * The agent's `env` variables and `--session-dir` name the folder it loads its
 * settings, hooks, extensions or sessions from. Their values are never taken
 * from a label: a label could name any folder, and a check of that folder
 * proves nothing, since whoever writes labels can also put a matching file
 * there. Only their names are recorded (`needs`): such a session resumes by
 * itself only when the resuming shell sets the variable on its own, and never
 * when it ran with `--session-dir`. The dialog still offers it by hand.
 * A session started with one of these comes back without it; the person adds
 * it again if they want it.
 * The engine (revive.mjs) has the other half: where each agent's hooks are
 * installed, and lib/sessions.js how to find a session nobody recorded.
 *
 * `env` lists the variables that say where the agent keeps its sessions: a
 * session started under `CLAUDE_CONFIG_DIR=~/.claude-work` is found, and
 * resumed, only under that same folder. The hook records their names, not
 * their values (see `needs` below). `findIn` lists flags of the same kind.
 * `oneShot` tells a run that answers and quits (`claude -p`, `codex exec`)
 * from an interactive session, given the words after the program's name:
 * such a run has hooks too, and must not replace the session on record.
 * `argv0Only` recognizes the agent by the first word of a command line only:
 * a short name like `pi` is often an argument (`ssh pi`, `vim pi`).
 */
export const AGENTS = {
  claude: {
    name: "Claude Code",
    bin: "claude",
    apps: ["claude-code", "claude"],
    resume: (id, flags) => ["claude", ...flags, "--resume", id],
    fork: (id, flags) => ["claude", ...flags, "--resume", id, "--fork-session"],
    end: claudeEnd,
    env: ["CLAUDE_CONFIG_DIR"],
    oneShot: (args) => args.some((w) => w === "-p" || w === "--print"),
    carry: {
      "--dangerously-skip-permissions": 0,
      "--allow-dangerously-skip-permissions": 0,
      "--permission-mode": 1,
      "--model": 1,
      "--agent": 1,
    },
  },
  codex: {
    name: "Codex",
    bin: "codex",
    apps: ["codex"],
    resume: (id, flags) => ["codex", "resume", ...flags, id],
    fork: (id, flags) => ["codex", "fork", ...flags, id],
    end: claudeEnd,
    env: ["CODEX_HOME"],
    oneShot: (args) => args[0] === "exec" || args[0] === "e",
    carry: {
      "--no-daemon": 0,
      "--dangerously-bypass-approvals-and-sandbox": 0,
      "--yolo": 0,
      "--full-auto": 0,
      "--approve-for-me": 0,
      "--search": 0,
      "-m": 1,
      "--model": 1,
      "-s": 1,
      "--sandbox": 1,
      "-a": 1,
      "--ask-for-approval": 1,
      "-p": NAME,
      "--profile": NAME,
    },
  },
  pi: {
    name: "pi",
    bin: "pi",
    apps: ["pi"],
    // pi sets its process title to `pi`, so the first word is always its own.
    argv0Only: true,
    resume: (id, flags) => ["pi", ...flags, "--session", id],
    fork: (id, flags) => ["pi", ...flags, "--fork", id],
    env: ["PI_CODING_AGENT_DIR", "PI_CODING_AGENT_SESSION_DIR"],
    findIn: ["--session-dir"],
    oneShot: (args) => args.some((w, i) => w === "-p" || w === "--print" || w === "--no-session"
      || /^--mode=(json|rpc)$/.test(w) || (w === "--mode" && /^(json|rpc)$/.test(args[i + 1] ?? ""))),
    carry: {
      "--provider": 1,
      "--model": 1,
      "--models": 1,
      "--thinking": 1,
      "-t": 1,
      "--tools": 1,
      "-xt": 1,
      "--exclude-tools": 1,
      "-nt": 0,
      "--no-tools": 0,
      "-nbt": 0,
      "--no-builtin-tools": 0,
      "-ne": 0,
      "--no-extensions": 0,
      "--no-mcp": 0,
      "-ns": 0,
      "--no-skills": 0,
      "-nc": 0,
      "--no-context-files": 0,
      "-a": 0,
      "--approve": 0,
      "-na": 0,
      "--no-approve": 0,
      "--offline": 0,
    },
  },
  // oh-my-pi (omp), checked against omp 18.16.0: a fork of pi with its own
  // home (~/.omp/agent) and its own extension folder, and `--resume <id>`
  // where pi has `--session`. Like pi it renames its process (`omp`), so its
  // extension (omp/revive.ts) sends its command line, and it reports itself
  // to Herdr as `omp`. Its `session_shutdown` carries no reason, so the
  // extension tells a person's /exit from a signal itself.
  omp: {
    name: "omp",
    bin: "omp",
    apps: ["omp", "oh-my-pi"],
    argv0Only: true,
    resume: (id, flags) => ["omp", ...flags, "--resume", id],
    fork: (id, flags) => ["omp", ...flags, "--fork", id],
    env: ["PI_CODING_AGENT_DIR"],
    findIn: ["--session-dir"],
    oneShot: (args) => args.some((w, i) => w === "-p" || w === "--print" || w === "--no-session" || w.startsWith("--export")
      || /^--mode=(json|rpc|rpc-ui)$/.test(w) || (w === "--mode" && /^(json|rpc|rpc-ui)$/.test(args[i + 1] ?? ""))),
    carry: {
      "--model": 1,
      "--smol": 1,
      "--slow": 1,
      "--plan": 1,
      "--provider": 1,
      "--models": 1,
      "--thinking": 1,
      "--service-tier": 1,
      "--tools": 1,
      "--skills": 1,
      "--no-tools": 0,
      "--no-lsp": 0,
      "--no-pty": 0,
      "--no-extensions": 0,
      "--no-skills": 0,
      "--no-rules": 0,
      "--no-context-files": 0,
      "--no-title": 0,
      "--hide-thinking": 0,
      "--profile": NAME,
      "--approval-mode": 1,
      "--auto-approve": 0,
      "--plan-yolo": 0,
    },
  },
  // Factory Droid, checked against droid 1.1.0: `--resume <id>` reopens the
  // same session id; `--fork <id>` opens an interactive copy under a new id; it
  // reports itself to Herdr as `droid`. Only interactive flags are carried:
  // --skip-permissions-unsafe, -m and the reasoning/tool flags exist only in
  // `droid exec`, and interactive droid reads them as the prompt. `-r` is left
  // behind on purpose: it means --resume in interactive mode.
  droid: {
    name: "Droid",
    bin: "droid",
    apps: ["droid", "factory-droid"],
    resume: (id, flags) => ["droid", ...flags, "--resume", id],
    fork: (id, flags) => ["droid", ...flags, "--fork", id],
    end: claudeEnd,
    oneShot: (args) => args[0] === "exec",
    carry: {
      "--auto": 1,
      "--use-spec": 0,
      "--disable-builtin-skills": 0,
    },
  },
  // Cursor CLI, checked against cursor-agent 2026.10.22: the sessionStart
  // hook's `conversation_id` is the chat id `--resume` takes, and resuming
  // reopens that same chat. sessionStart fires for a new chat, not when one is
  // resumed, so the record a resume leaves on the terminal is what carries it
  // to the next restart. It installs as both `cursor-agent` and `agent`;
  // `agent` is too generic a name, so it counts only under a path that says
  // Cursor (~/.local/share/cursor-agent/versions/…) or with a Cursor report.
  // It has no fork and no `-m` (only --model). `--api-key` and `-H` are never
  // carried: labels are readable by anything that asks hc. `--workspace` isn't
  // either: Cursor loads that folder's rules, MCP config and hooks, and the
  // resume already runs in the recorded folder.
  cursor: {
    name: "Cursor",
    bin: "cursor-agent",
    bins: ["cursor-agent", "agent"],
    match: (word) => {
      const name = base(word);
      if (name === "cursor-agent") return true;
      const dirs = String(word).split("/").slice(0, -1);
      return ["agent", "node", "index.js"].includes(name) && dirs.some((d) => /^cursor(-agent)?$/i.test(d));
    },
    apps: ["cursor", "cursor-agent"],
    resume: (id, flags) => ["cursor-agent", ...flags, "--resume", id],
    fork: null,
    // completed: the CLI's normal end; user_close: the IDE's. Anything else
    // (aborted, error, window_close) is kept, to be offered back. Checked with
    // cursor-agent 2026.10.22: /exit and Ctrl+C twice send "completed"; SIGTERM
    // (a shutdown) sends "aborted"; SIGHUP (the terminal closing) sends no
    // sessionEnd at all, so the record stays, which also means keep.
    end: (reason) => (reason === "completed" || reason === "user_close" ? "forget" : "keep"),
    oneShot: (args) => args.some((w) => w === "-p" || w === "--print"),
    carry: {
      "-f": 0,
      "--force": 0,
      "--yolo": 0,
      "--model": 1,
      "--sandbox": 1,
      "--mode": 1,
      "--plan": 0,
    },
  },
};

const base = (path) => String(path ?? "").split("/").pop();
const own = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);

/** Whether one command-line word is this agent's program. */
const isBin = (agent, word) => (agent.match ? agent.match(word) : (agent.bins ?? [agent.bin]).includes(base(word)));

/** The agent behind an OSC 7501 report (`claude-code`) or a command line, or null. */
export function agentKey(app, argv = []) {
  for (const [key, agent] of Object.entries(AGENTS)) {
    if (app && agent.apps.includes(app)) return key;
  }
  // `claude …`, or a script run by its interpreter: `node …/bin/codex …`.
  for (const [i, word] of argv.slice(0, 2).entries()) {
    for (const [key, agent] of Object.entries(AGENTS)) {
      if (isBin(agent, word) && !(i > 0 && agent.argv0Only)) return key;
    }
  }
  return null;
}

/** Whether the agent can copy a session into a new one. */
export const canFork = (key) => typeof AGENTS[key]?.fork === "function";

/** What a SessionEnd with this reason means for the record: "ignore", "keep" or "forget". */
export const endAction = (key, reason) => (AGENTS[key]?.end ?? claudeEnd)(reason);

/**
 * A hook's input, the same for every agent. Claude Code, Codex, Droid and
 * pi's extension send `SessionStart` with `session_id` and `cwd`; Cursor sends
 * `sessionStart` with `conversation_id` and `workspace_roots`. `agent` is what
 * the payload itself says (its transcript path, Cursor's version field), or
 * null. `argv` is the command line pi's extension sends, or null.
 */
export function hookPayload(payload) {
  const p = payload && typeof payload === "object" ? payload : {};
  const name = typeof p.hook_event_name === "string" ? p.hook_event_name : "";
  const roots = Array.isArray(p.workspace_roots) ? p.workspace_roots : [];
  return {
    event: name ? name[0].toUpperCase() + name.slice(1) : null,
    session: p.session_id ?? p.conversation_id ?? null,
    cwd: p.cwd || roots[0] || null,
    reason: p.reason ?? null,
    transcript: typeof p.transcript_path === "string" ? p.transcript_path : null,
    argv: Array.isArray(p.argv) ? p.argv.map(String) : null,
    agent: payloadAgent(p),
  };
}

function payloadAgent(p) {
  const path = String(p.transcript_path ?? "");
  if (path.includes("/.codex/")) return "codex";
  if (path.includes("/.omp/")) return "omp";
  if (path.includes("/.pi/")) return "pi";
  if (path.includes("/.factory/")) return "droid";
  if (path.includes("/.cursor/") || p.cursor_version !== undefined) return "cursor";
  if (path.includes("/.claude/") || path.includes("/projects/")) return "claude";
  return null;
}

/** Where the agent's own words start: after its program's name, else after the first word. */
const argsStart = (key, argv) => {
  const start = argv.findIndex((word) => isBin(AGENTS[key], word));
  return start < 0 ? 1 : start + 1;
};

/** Whether a command line runs the agent once, without a session to bring back. */
export function isOneShot(key, argv = []) {
  const agent = AGENTS[key];
  return Boolean(agent?.oneShot?.(argv.slice(argsStart(key, argv)).map(String)));
}

const arity = (spec) => (typeof spec === "object" ? spec.arg : spec);
/** Whether a value may go with a value flag: not another flag, and what the flag accepts. */
const accepts = (spec, value) => typeof value === "string" && !value.startsWith("-") && (typeof spec !== "object" || spec.ok(value));

/**
 * The launch flags worth keeping, in their original order. A value flag whose
 * value is missing, looks like another flag or isn't accepted is dropped,
 * value and all, so nothing rides along as a value that wouldn't pass alone.
 */
export function carriedFlags(key, argv = []) {
  const carry = AGENTS[key]?.carry;
  if (!carry) return [];
  const out = [];
  for (let i = argsStart(key, argv); i < argv.length; i++) {
    const word = String(argv[i]);
    const eq = word.indexOf("=");
    if (word.startsWith("--") && eq > 0 && own(carry, word.slice(0, eq))) {
      const spec = carry[word.slice(0, eq)];
      if (arity(spec) >= 1 && accepts(spec, word.slice(eq + 1))) out.push(word);
      continue;
    }
    // Own keys only: a first prompt like `constructor` is not a flag.
    if (!own(carry, word)) continue;
    const spec = carry[word];
    const n = arity(spec);
    if (n === 1) {
      if (!accepts(spec, argv[i + 1])) continue;
      out.push(word, String(argv[++i]));
      continue;
    }
    out.push(word);
    if (n === 2) while (i + 1 < argv.length && accepts(spec, argv[i + 1])) out.push(String(argv[++i]));
  }
  return out;
}

/**
 * Flags read back from a label, filtered again as if they were a command line:
 * a label is not proof that `carriedFlags` wrote it.
 */
export function safeFlags(key, flags) {
  const agent = AGENTS[key];
  if (!agent || !Array.isArray(flags)) return [];
  return carriedFlags(key, [agent.bin, ...flags.map(String)]);
}

/**
 * Whether a hook belongs to the agent in the terminal's foreground (`target`).
 * `table` maps pid → { ppid, argv }; the walk goes up from the hook's parent
 * and must reach `target`. On the way, the agent processes must sit next to
 * each other: an agent and the wrapper that started it (`node …/bin/codex`
 * running the native `codex`, a launcher script whose own name is something
 * else) are one agent. An agent, then a shell, then another agent is a tool
 * call: a `claude -p` the foreground agent ran, whose hooks are not its own.
 * The first agent found above the hook is returned with the verdict.
 */
export function hookOwner(table, start, target) {
  let first = null, ended = false;
  for (let pid = start, hops = 0; pid > 1 && hops < 64; hops++) {
    const proc = table.get(pid);
    if (!proc) return { owned: false, agent: first };
    const isAgent = Boolean(agentKey(null, proc.argv));
    if (isAgent && ended) return { owned: false, agent: first };
    if (isAgent && first === null) first = pid;
    if (!isAgent && first !== null) ended = true;
    if (pid === target) return { owned: true, agent: first };
    pid = proc.ppid;
  }
  return { owned: false, agent: first };
}

/** Session ids are UUIDs (Droid's docs show `session-abc123`); anything else is refused rather than quoted. */
export const validId = (id) => typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(id);

export const shortId = (id) => (id ? String(id).slice(0, 8) : "");

/**
 * The command line that resumes or forks a session.
 */
export function command(rec, kind = "resume") {
  const agent = AGENTS[rec?.agent];
  if (!agent || typeof agent[kind] !== "function" || !validId(rec.session)) return null;
  // No variables: a resume runs with the shell's own (see `needs`).
  return agent[kind](rec.session, safeFlags(rec.agent, rec.flags ?? []));
}

/**
 * The command to run by hand for a record with needs: variables are set by
 * the person; a flag goes right after the agent's name, with a placeholder
 * for its value, which was never recorded.
 */
export function needsCommand(rec) {
  const argv = command(rec, "resume");
  if (!argv) return null;
  const added = rec.needs.filter((n) => n.startsWith("-")).map((f) => ` ${f} <folder>`).join("");
  const cd = rec.cwd ? `cd -- ${shQuote(rec.cwd)} && ` : "";
  return `${cd}${shJoin(argv.slice(0, 1))}${added}${argv.length > 1 ? ` ${shJoin(argv.slice(1))}` : ""}`;
}

/** What to do by hand for a record with needs, as one sentence ending in the command. */
export function needsHint(rec) {
  const vars = rec.needs.filter((n) => !n.startsWith("-"));
  const flags = rec.needs.filter((n) => n.startsWith("-"));
  const how = [vars.length ? `set ${vars.join(", ")}` : "", flags.length ? `fill in ${flags.join(", ")}` : ""].filter(Boolean).join(" and ");
  return `${how[0].toUpperCase()}${how.slice(1)}, then run: ${needsCommand(rec)}`;
}

/**
 * Why a remembered session isn't resumed by hand, or null: its folder failed
 * the check (`folder`, the recorded path), or it needs something Revive doesn't
 * carry (`needs`). The engine refuses these, and the dialog disables Resume.
 */
export function unresumable(rec) {
  if (rec?.cwdRefused) return { folder: rec.cwdRefused };
  if (rec?.needs?.length) return { needs: rec.needs };
  return null;
}

/**
 * The needs the shell doesn't meet: a variable it doesn't set, a `findIn`
 * flag always. The session then isn't resumed by itself.
 */
export const unmet = (rec, env = {}) => (rec?.needs ?? []).filter((n) => n.startsWith("-") || typeof env[n] !== "string" || env[n] === "");

/** One word for a POSIX shell, quoted only when it needs to be. */
export function shQuote(word) {
  const s = String(word);
  return /^[A-Za-z0-9_@%+=:,./-]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`;
}

export const shJoin = (argv) => argv.map(shQuote).join(" ");

const num = (v) => (v === undefined || v === "" || v === null ? null : Number.isFinite(Number(v)) ? Number(v) : null);

/**
 * What a session needs that Revive won't carry: the agent's `env` variables
 * set in `env`, and its `findIn` flags on the command line `argv`.
 */
export function needsOf(key, argv = [], env = {}) {
  const agent = AGENTS[key];
  if (!agent) return [];
  const words = argv.slice(argsStart(key, argv)).map(String);
  const flags = (agent.findIn ?? []).filter((f) => words.some((w) => w === f || w.startsWith(`${f}=`)));
  const set = (agent.env ?? []).filter((n) => typeof env[n] === "string" && env[n] !== "");
  return [...set, ...flags];
}

/** A terminal's labels as a record, or null when it carries no session. */
export function readRecord(labels) {
  const get = (k) => labels?.[PREFIX + k];
  const session = get("session");
  if (!session) return null;
  const agent = AGENTS[get("agent")];
  const needs = new Set();
  let flags = [];
  try {
    const raw = JSON.parse(get("flags") || "[]");
    // Only the flags the agent's carry list lets through, as on the way in.
    flags = safeFlags(get("agent"), raw);
    // 0.4.0 carried `--session-dir X` in the flags: such a record needs it.
    const words = Array.isArray(raw) ? raw.map(String) : [];
    for (const f of agent?.findIn ?? []) if (words.some((w) => w === f || w.startsWith(`${f}=`))) needs.add(f);
  } catch { /* a hand-edited label: carry nothing */ }
  // Names only, and only those the agent declares. `env`, from earlier
  // versions, held values too: they are not used, its names count as needs.
  const known = new Set([...(agent?.env ?? []), ...(agent?.findIn ?? [])]);
  for (const key of ["needs", "env"]) {
    try {
      const parsed = JSON.parse(get(key) || "[]");
      const names = Array.isArray(parsed) ? parsed : parsed && typeof parsed === "object" ? Object.keys(parsed) : [];
      for (const n of names) if (known.has(n)) needs.add(n);
    } catch { /* a hand-edited label: nothing */ }
  }
  return {
    agent: get("agent") || null,
    session,
    cwd: get("cwd") || null,
    flags,
    needs: [...needs],
    transcript: get("transcript") || null,
    shell: num(get("shell")),
    since: get("since") || null,
    at: num(get("at")),
    resumed: num(get("resumed")),
    failed: num(get("failed")),
    auto: get("auto") !== "off",
  };
}

/** `k=v` arguments for `hc label`. A null or "" value removes that label. */
export function labelArgs(fields) {
  return Object.entries(fields).map(([k, v]) => `${PREFIX}${k}=${v === null || v === undefined ? "" : v}`);
}

/**
 * The labels a resume writes, by hand or after a restart: the terminal's
 * program now, and when. Written before the agent starts, so a second shell
 * can't resume the same session again.
 */
export const resumedArgs = ({ pid, since, now = Date.now() }) =>
  labelArgs({ shell: pid, since, resumed: now, failed: null, ended: null });

/** Every Revive label, removed. `auto` stays: it is the person's choice for that terminal. */
export const clearArgs = () => labelArgs(Object.fromEntries(KEYS.filter((k) => k !== "auto").map((k) => [k, null])));

/**
 * Where a remembered session stands, given its terminal now:
 * - running      the agent is in the terminal's foreground
 * - lost         the terminal's program was replaced (a restart or reboot)
 *                and the session did not come back
 * - interrupted  the agent died under a shell that survived (a signal, a crash)
 * - failed       a resume was tried and the agent gave up at once
 * A session the person ended themselves is never remembered, so it has no state.
 */
export function stateOf(rec, terminal) {
  if (!rec) return null;
  if (terminal.live) return "running";
  if (rec.failed) return "failed";
  if (rec.shell !== null && terminal.pid !== null && !sameShell(rec, terminal)) return "lost";
  return "interrupted";
}

/**
 * Whether the terminal still runs the program the session was recorded under.
 * Pids start over after a reboot, so a new shell can get the old one's pid;
 * its start time tells them apart. A record without one compares pids only.
 */
export function sameShell(rec, { pid, since = null }) {
  if (rec.shell !== pid) return false;
  return !rec.since || !since || rec.since === since;
}

/**
 * Whether a shell that just started should resume its terminal's session.
 * Only the terminal's own shell (not one started inside it), only after the
 * program it held was replaced, and only when nobody turned it off.
 */
export function shouldResume(rec, { pid, since = null, shellPid, env = {} }) {
  if (!rec) return { go: false, why: "nothing remembered" };
  if (!AGENTS[rec.agent]) return { go: false, why: `unknown agent ${rec.agent}` };
  if (!validId(rec.session)) return { go: false, why: "malformed session id" };
  if (pid === null || shellPid !== pid) return { go: false, why: "not the terminal's own shell" };
  if (env.REVIVE_AUTO === "0") return { go: false, why: "REVIVE_AUTO=0" };
  if (!rec.auto) return { go: false, why: "turned off for this terminal" };
  // It was tried after the last restart and the agent gave up at once (its
  // folder is gone, the session can't be found): trying at every restart would
  // fail the same way. The dialog still offers it by hand.
  if (rec.failed) return { go: false, why: "the last resume failed" };
  if (sameShell(rec, { pid, since })) return { go: false, why: "same shell as before" };
  // The engine found the folder missing or not the person's (vetRecord).
  if (rec.cwdRefused) return { go: false, why: "its folder is missing or not yours", hint: true };
  const missing = unmet(rec, env);
  if (missing.length) return { go: false, why: `it was started with ${missing.join(", ")}`, hint: true };
  return { go: true, why: "the terminal's program was replaced" };
}

/** `cd -- <folder> && <agent> … --resume <id>`, one line, or "". */
export function resumeLine(rec) {
  const argv = command(rec, "resume");
  if (!argv) return "";
  return `${rec.cwd ? `cd -- ${shQuote(rec.cwd)} && ` : ""}${shJoin(argv)}`;
}

/**
 * What the recovered shell runs: say what is happening, go back to the
 * session's folder, start the agent, and mark the terminal failed when the
 * agent quits within a few seconds with an error (a session it can't find).
 */
export function resumeScript(rec, engine) {
  const line = resumeLine(rec);
  if (!line) return "";
  const name = AGENTS[rec.agent].name;
  const note = `↻ Revive: resuming ${name} session ${shortId(rec.session)}. REVIVE_AUTO=0 skips this.`;
  const body = [
    `  printf '\\033[2m%s\\033[0m\\n' ${shQuote(note)}`,
    `  __revive_t=$SECONDS`,
    `  ${line}`,
    `  if [ $? -ne 0 ] && [ $((SECONDS - __revive_t)) -lt 15 ]; then node ${shQuote(engine)} failed; fi`,
    `  unset __revive_t`,
  ];
  // The agent gets the terminal itself: while a shell starts, its input and
  // output may be held by something else (an instant prompt), and an agent
  // that doesn't see a terminal runs non-interactively and quits. It is the
  // terminal's own device (/dev/ttys004), found from the shell's process: an
  // agent on /dev/tty crashes on macOS, where kqueue can't watch that alias.
  // REVIVE_TTY: another device, for tests.
  return [
    `__revive_tty="\${REVIVE_TTY:-/dev/$(ps -o tty= -p $$ 2>/dev/null | tr -d ' ')}"`,
    `case "$__revive_tty" in /dev/|/dev/\\?*|/dev/-*) __revive_tty= ;; esac`,
    `if [ -n "$__revive_tty" ] && { : >"$__revive_tty"; } 2>/dev/null; then {`,
    ...body,
    `} <"$__revive_tty" >"$__revive_tty" 2>&1; else {`,
    ...body,
    `}; fi`,
    `unset __revive_tty`,
  ].join("\n");
}

/** "3m ago", for a timestamp in ms. */
export function ago(ms, now = Date.now()) {
  if (!ms) return "";
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
