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
export const KEYS = ["agent", "session", "cwd", "flags", "env", "needs", "transcript", "shell", "since", "at", "ended", "resumed", "failed", "auto", "restore"];

/**
 * How an agent's SessionEnd reason is taken: "ignore" (the same process starts
 * another session at once, and its SessionStart records it), "keep" (a signal,
 * a crash: worth bringing back), "forget" (the person ended it) or "settle"
 * (the reason can't tell those apart: the engine forgets the session only if
 * the terminal's shell is still alive a moment later, see revive.mjs).
 * Claude Code's reasons, which Codex, Factory Droid and pi's extension share.
 */
/** A value flag that names one of the person's own profiles, not a path. */
const NAME = { arg: 1, ok: (v) => /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(v) };
/** One agent definition by name (`reviewer`, a plugin's `plugin:reviewer`), never a path. */
const AGENT_NAME = { arg: 1, ok: (v) => /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(v) && !v.includes("..") };
/** A comma-separated list of names (`commit,review`), never a path. */
const NAMES = { arg: 1, ok: (v) => /^[A-Za-z0-9][A-Za-z0-9_.:-]*(,[A-Za-z0-9][A-Za-z0-9_.:-]*)*$/.test(v) && v.length <= 512 && !v.includes("..") };
/** An `unattended` rule for a value flag: dropped unless its value is one of `keep`. */
const unless = (...keep) => (v) => !keep.includes(v);


const claudeEnd = (reason) => (reason === "clear" || reason === "resume" ? "ignore" : reason === "other" ? "keep" : "forget");

// Codex accepts options before its subcommand. Skip their values too: a
// profile or model named `exec` is still an interactive launch.
const CODEX_VALUE_FLAGS = new Set([
  "-c", "--config", "--enable", "--disable", "--remote", "--remote-auth-token-env",
  "-i", "--image", "-m", "--model", "--local-provider", "-p", "--profile",
  "-s", "--sandbox", "-a", "--ask-for-approval", "-C", "--cd", "--add-dir",
]);
function codexOneShot(args) {
  for (let i = 0; i < args.length; i++) {
    const word = args[i];
    if (word === "--") return false;
    if (CODEX_VALUE_FLAGS.has(word)) { i++; continue; }
    if (word.startsWith("-")) continue;
    return word === "exec" || word === "e";
  }
  return false;
}

/**
 * The agents Revive can bring back, one entry each:
 * - `name`     what the person reads
 * - `bin`      the program a resume or fork runs
 * - `bins`     the program names it is known by on a command line (default: `bin`)
 * - `match`    optional: a stricter test of one command-line word, for a name
 *              too generic to trust on its own; called as (word, i, argv)
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
 * - `unattended` the carried flags an automatic resume (after a reboot or a
 *              core restart, with nobody watching) leaves out: the ones that
 *              lift approvals or the sandbox. `true` drops the flag, a
 *              function drops it when it returns true for the flag's value.
 *              A resume the person starts from the dialog keeps them.
 *
 * What is carried and what never is, and why: the flags travel through a
 * terminal label, which anything that can talk to herdr-core can write, and
 * they come back unattended after a reboot.
 * - Permission and sandbox modes that lift approvals or the sandbox
 *   (`--dangerously-skip-permissions`, `--permission-mode bypassPermissions`,
 *   Codex's `--yolo` and `-a never`, `--force`, `--auto-approve`, ...) are
 *   carried only into a resume the person starts from the dialog. An
 *   automatic resume leaves them out (`unattended`) and says so: a label
 *   writer may be an agent running under restricted permissions, and a
 *   bypass written into a label must not come back unrestricted after a
 *   reboot, with nobody watching it start.
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
 * `interpreterOnly` also counts it as the second word after an interpreter
 * (`node …/bin/copilot`), and nowhere else (`gh copilot`).
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
      "--agent": AGENT_NAME,
    },
    unattended: {
      "--dangerously-skip-permissions": true,
      "--allow-dangerously-skip-permissions": true,
      "--permission-mode": unless("default", "manual", "plan", "dontAsk"),
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
    oneShot: codexOneShot,
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
    unattended: {
      "--dangerously-bypass-approvals-and-sandbox": true,
      "--yolo": true,
      "--approve-for-me": true,
      "-a": (v) => v === "never",
      "--ask-for-approval": (v) => v === "never",
      "-s": (v) => v === "danger-full-access",
      "--sandbox": (v) => v === "danger-full-access",
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
    unattended: { "-a": true, "--approve": true },
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
    // Opt-in per terminal (`revive.mjs restore T on`): reopens the session as
    // --resume does, then goes on with the turn and the subagents its last
    // process left unfinished, running again a batch of tool calls that was
    // cut off. Since omp 18.16; interactive only, no prompt.
    restore: (id, flags) => ["omp", ...flags, "--restore", id],
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
      "--skills": NAMES,
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
    // --approval-mode's values aren't pinned down here: any of them is left
    // out, which at worst brings the session back asking more, not less.
    unattended: { "--approval-mode": true, "--auto-approve": true, "--plan-yolo": true },
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
    unattended: { "--auto": true },
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
      const dirs = dirsOf(word);
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
    unattended: { "-f": true, "--force": true, "--yolo": true, "--sandbox": unless("enabled") },
  },
  // GitHub Copilot CLI, checked against copilot 1.0.109 and 1.0.111: hooks in
  // ~/.copilot/hooks/*.json get SessionStart (at a session's first message,
  // and again on `--resume`) and SessionEnd with `session_id`; `--resume <id>`
  // reopens the same session. It has no fork on the command line (`/fork`
  // inside does). `copilot` counts as the first word, or as the script an
  // interpreter runs (`node …/bin/copilot`), never as an argument: `gh
  // copilot` is gh's own command. Extra folders, MCP configs, plugins and
  // sharing (`--add-dir`, `--additional-mcp-config`, `--plugin-dir`,
  // `--enable-mcp-server`, `--share…`) are never carried.
  copilot: {
    name: "Copilot CLI",
    bin: "copilot",
    interpreterOnly: true,
    apps: ["copilot", "copilot-cli", "github-copilot"],
    resume: (id, flags) => ["copilot", ...flags, "--resume", id],
    fork: null,
    // complete: a `-p` run finished. user_exit is sent for /exit and Ctrl+C,
    // but also for SIGTERM and SIGHUP (a core restart, a reboot), so it is
    // settled by whether the terminal outlived it. abort, error, timeout: kept.
    end: (reason) => (reason === "complete" ? "forget" : reason === "user_exit" ? "settle" : "keep"),
    env: ["COPILOT_HOME"],
    oneShot: (args) => args.some((w) => w === "-p" || w === "--prompt" || w.startsWith("--prompt=") || w === "--acp" || w === "--connect" || w.startsWith("--connect="))
      || COPILOT_COMMANDS.has(args[0]),
    carry: {
      "--plan": 0,
      "--autopilot": 0,
      "--allow-all": 0,
      "--yolo": 0,
      "--allow-all-tools": 0,
      "--allow-all-paths": 0,
      "--allow-all-urls": 0,
      "--allow-tool": 2,
      "--deny-tool": 2,
      "--allow-url": 2,
      "--deny-url": 2,
      "--available-tools": 2,
      "--excluded-tools": 2,
      "--no-ask-user": 0,
      "--experimental": 0,
      "--no-experimental": 0,
      "--disable-builtin-mcps": 0,
      "--disable-mcp-server": 1,
      "--no-custom-instructions": 0,
      "--disallow-temp-dir": 0,
      "--screen-reader": 0,
      "--plain-diff": 0,
      "--no-mouse": 0,
      "--model": 1,
      "--mode": 1,
      "--reasoning-effort": 1,
      "--max-autopilot-continues": 1,
      "--agent": AGENT_NAME,
    },
    unattended: {
      "--allow-all": true,
      "--yolo": true,
      "--allow-all-tools": true,
      "--allow-all-paths": true,
      "--allow-all-urls": true,
      "--allow-tool": true,
      "--allow-url": true,
    },
  },
};

/** Copilot CLI's subcommands: each runs once and quits, with no session to resume. */
const COPILOT_COMMANDS = new Set(["login", "logout", "help", "init", "config", "update", "version", "workflow", "sessions", "memories", "plugin", "mcp", "skill", "instruction", "lsp", "sandbox", "completion", "app"]);

/**
 * A program's name from one command-line word: the last part of its path. On
 * Windows a path uses `\` and a program ends in `.exe` (or is a `.cmd`,
 * `.bat` or `.ps1` shim, as npm writes): `C:\Users\me\.local\bin\claude.exe`
 * is `claude`. Windows names don't tell case apart, so a Windows-style word is
 * compared in lower case.
 */
const WIN_EXT = /\.(exe|cmd|bat|com|ps1)$/i;
const base = (path) => {
  const word = String(path ?? "");
  const name = word.split(/[\\/]/).pop();
  return word.includes("\\") || WIN_EXT.test(name) ? name.replace(WIN_EXT, "").toLowerCase() : name;
};
/** The folders of a path, whichever separator it uses. */
const dirsOf = (path) => String(path ?? "").split(/[\\/]/).slice(0, -1);
const own = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);

/** Whether one command-line word is this agent's program. */
const isBin = (agent, word) => (agent.match ? agent.match(word) : (agent.bins ?? [agent.bin]).includes(base(word)));

const INTERPRETERS = ["node", "bun", "deno"];

/** The agent behind an OSC 7501 report (`claude-code`) or a command line, or null. */
export function agentKey(app, argv = []) {
  for (const [key, agent] of Object.entries(AGENTS)) {
    if (app && agent.apps.includes(app)) return key;
  }
  // `claude …`, or a script run by its interpreter: `node …/bin/codex …`.
  for (const [i, word] of argv.slice(0, 2).entries()) {
    for (const [key, agent] of Object.entries(AGENTS)) {
      const firstOnly = agent.argv0Only || (agent.interpreterOnly && !INTERPRETERS.includes(base(argv[0])));
      if (isBin(agent, word) && !(i > 0 && firstOnly)) return key;
    }
  }
  return null;
}

/** Whether the agent can go on with an interrupted turn when it resumes (omp's --restore). */
export const canRestore = (key) => typeof AGENTS[key]?.restore === "function";

/** Whether this record's resume goes on with the interrupted turn: the terminal opted in, and the agent can. */
export const restores = (rec) => Boolean(rec?.restore) && canRestore(rec.agent);

/** Whether the agent can copy a session into a new one. */
export const canFork = (key) => typeof AGENTS[key]?.fork === "function";

/** What a SessionEnd with this reason means for the record: "ignore", "keep", "forget" or "settle". */
export const endAction = (key, reason) => (AGENTS[key]?.end ?? claudeEnd)(reason);

/**
 * A hook's input, the same for every agent. Claude Code, Codex, Droid,
 * pi's extension and Copilot CLI send `SessionStart` with `session_id` and
 * `cwd` (Copilot only to hooks registered under that PascalCase name: a
 * `sessionStart` hook gets camelCase fields and no event name); Cursor sends
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
  // A Windows path (`C:\Users\me\.claude\projects\…`) is read like a POSIX one.
  const path = String(p.transcript_path ?? "").replace(/\\/g, "/");
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
 * Carried flags split for an automatic resume: `kept` go on the command line,
 * `dropped` (each a flag with its value, as one string) are the ones the
 * agent's `unattended` rules leave out. `flags` come from `safeFlags`, so
 * every value sits right after its flag.
 */
export function attendedFlags(key, flags = []) {
  const agent = AGENTS[key];
  const carry = agent?.carry ?? {};
  const rules = agent?.unattended ?? {};
  const kept = [], dropped = [];
  for (let i = 0; i < flags.length; i++) {
    const word = String(flags[i]);
    const eq = word.startsWith("--") ? word.indexOf("=") : -1;
    const name = eq > 0 ? word.slice(0, eq) : word;
    const unit = [word];
    let value = eq > 0 ? word.slice(eq + 1) : null;
    if (eq < 0 && own(carry, name)) {
      const n = arity(carry[name]);
      if (n === 1 && i + 1 < flags.length) { value = String(flags[++i]); unit.push(value); }
      if (n === 2) while (i + 1 < flags.length && !String(flags[i + 1]).startsWith("-")) unit.push(String(flags[++i]));
    }
    const rule = own(rules, name) ? rules[name] : null;
    const drop = rule === true || (typeof rule === "function" && rule(value));
    if (drop) dropped.push(unit.join(" "));
    else kept.push(...unit);
  }
  return { kept, dropped };
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

// pwsh (PowerShell 7), powershell (Windows PowerShell 5.1) and cmd: the shells
// herdr-core starts on Windows.
const SHELLS = new Set(["sh", "bash", "zsh", "fish", "dash", "ksh", "mksh", "yash", "csh", "tcsh", "nu", "elvish", "xonsh", "pwsh", "powershell", "cmd"]);
/** Whether a command line is a shell's: `zsh`, `-zsh` (a login shell), `/bin/bash --login`, `C:\…\pwsh.exe`. */
export const isShell = (argv) => SHELLS.has(base(String(argv?.[0] ?? "").replace(/^-/, "")));

/** Whether a command line is PowerShell's (7 or 5.1). */
export const isPowerShell = (argv) => ["pwsh", "powershell"].includes(base(argv?.[0]));

/**
 * Whether a PowerShell or cmd command line waits at its own prompt. herdr-core
 * starts PowerShell as `pwsh -NoExit -Command <its prompt hook>`: with
 * -NoExit it is interactive whatever it runs first. Without, a -Command or
 * -File runs and quits. cmd: `/k` stays, `/c` quits. Parameter names are
 * case-insensitive and may be shortened (`-noe`, `-c`, `-f`).
 */
function windowsPromptShell(argv) {
  const words = argv.slice(1).map((w) => String(w).toLowerCase());
  if (base(argv[0]) === "cmd") return !words.some((w) => w === "/c" || w === "/r");
  const param = (w, name, min) => w.startsWith("-") && w.length - 1 >= min && name.startsWith(w.slice(1));
  if (words.some((w) => param(w, "noexit", 3))) return true;
  return !words.some((w) => param(w, "command", 1) || param(w, "file", 1) || param(w, "encodedcommand", 1) || w === "-ec");
}

/**
 * Whether the shell `shellPid` is the terminal's own: the terminal's program
 * itself, or a shell that program runs as its child instead of `exec`ing it
 * (Kiro CLI's and Amazon Q's pty wrapper, `script`, a recorder started from
 * a profile). The walk goes up from the shell and must reach `terminalPid`
 * without passing another shell. `marker` is REVIVE_SHELL, the pid of a shell
 * that ran Revive's block and exported it: on the way up, it is a shell
 * started by hand inside the terminal's own one. A marker that isn't on the
 * way (one a core kept from the shell that started it) is ignored.
 */
export function ownShell(table, shellPid, terminalPid, marker = null) {
  if (!terminalPid) return { own: false, why: "not the terminal's own shell" };
  if (shellPid === terminalPid) return { own: true };
  const outer = Number(marker) || null;
  let pid = table.get(shellPid)?.ppid;
  for (let hops = 0; pid > 1 && hops < 64; hops++) {
    if (pid === outer) return { own: false, why: "a shell started inside the terminal's own shell" };
    if (pid === terminalPid) return { own: true };
    const proc = table.get(pid);
    if (!proc) break;
    if (isShell(proc.argv)) return { own: false, why: "a shell started inside another shell" };
    pid = proc.ppid;
  }
  return { own: false, why: "not the terminal's own shell" };
}

/**
 * A shell waiting at its own prompt: no script or `-c` command. One with an
 * operand may be launching an agent.
 */
export const promptShell = (argv) => isShell(argv) && (["pwsh", "powershell", "cmd"].includes(base(argv[0]))
  ? windowsPromptShell(argv)
  : argv.slice(1).every((w) => String(w).startsWith("-")
    && (String(w).startsWith("--") ? w !== "--command" : !String(w).slice(1).includes("c"))));

/**
 * Whether a manual Resume may type into the foreground shell `fg` of a
 * terminal whose program is `terminalPid`: only a wrapper's idle child shell.
 * When the terminal's program is itself an interactive shell, any other shell
 * in front was started inside it by hand (`zsh`, `sudo -s`, `su`), and typing
 * there would run the agent as someone else or in a different environment.
 */
export function idleWrappedShell(table, fg, terminalPid) {
  if (!fg?.pid || !terminalPid || fg.pid === terminalPid) return false;
  if (!promptShell(fg.argv ?? [])) return false;
  if (promptShell(table.get(terminalPid)?.argv ?? [])) return false;
  return ownShell(table, fg.pid, terminalPid).own;
}

/** Session ids are UUIDs (Droid's docs show `session-abc123`); anything else is refused rather than quoted. */
export const validId = (id) => typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(id);

export const shortId = (id) => (id ? String(id).slice(0, 8) : "");

/**
 * The command line that resumes or forks a session. `unattended`: for an
 * automatic resume, without the flags that lift approvals or the sandbox.
 */
export function command(rec, kind = "resume", { unattended = false } = {}) {
  const agent = AGENTS[rec?.agent];
  if (kind === "resume" && restores(rec)) kind = "restore";
  if (!agent || typeof agent[kind] !== "function" || !validId(rec.session)) return null;
  const flags = safeFlags(rec.agent, rec.flags ?? []);
  // No variables: a resume runs with the shell's own (see `needs`).
  return agent[kind](rec.session, unattended ? attendedFlags(rec.agent, flags).kept : flags);
}

/**
 * The command to run by hand for a record with needs: variables are set by
 * the person; a flag goes right after the agent's name, with a placeholder
 * for its value, which was never recorded.
 */
export function needsCommand(rec, { dialect = "posix" } = {}) {
  const argv = command(rec, "resume");
  if (!argv) return null;
  const added = rec.needs.filter((n) => n.startsWith("-")).map((f) => ` ${f} <folder>`).join("");
  if (dialectOf(dialect) === "pwsh") {
    const cd = rec.cwd ? `Set-Location -LiteralPath ${psQuote(rec.cwd)}; ` : "";
    return `${cd}& ${psQuote(argv[0])}${added}${argv.length > 1 ? ` ${argv.slice(1).map(psQuote).join(" ")}` : ""}`;
  }
  const cd = rec.cwd ? `cd -- ${shQuote(rec.cwd)} && ` : "";
  return `${cd}${shJoin(argv.slice(0, 1))}${added}${argv.length > 1 ? ` ${shJoin(argv.slice(1))}` : ""}`;
}

/** What to do by hand for a record with needs, as one sentence ending in the command. */
export function needsHint(rec, { dialect = "posix" } = {}) {
  const vars = rec.needs.filter((n) => !n.startsWith("-"));
  const flags = rec.needs.filter((n) => n.startsWith("-"));
  const how = [vars.length ? `set ${vars.join(", ")}` : "", flags.length ? `fill in ${flags.join(", ")}` : ""].filter(Boolean).join(" and ");
  return `${how[0].toUpperCase()}${how.slice(1)}, then run: ${needsCommand(rec, { dialect })}`;
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

/**
 * One word for PowerShell, quoted only when it needs to be. In a single-quoted
 * string PowerShell ends the string at `'` and also at the typographic quotes
 * U+2018–U+201B, so each of them is doubled, as PowerShell's own escaping does.
 * A bare word must not start what PowerShell reads as an operator (`@` splats,
 * `$` is a variable, `,` builds an array), hence the short list.
 *
 * A word that starts with `-` is bare only when it is a plain flag name
 * (`--model`, `-m`): both PowerShells (7.6 and 5.1, checked) pass `-m.x`,
 * `-Dfoo.bar=1` or `-v1.2` to a native program split at the `.`, as `-m`
 * `.x`. Quoted, every such word arrives whole.
 */
export function psQuote(word) {
  const s = String(word);
  const bare = /^[A-Za-z0-9_./:=+-]+$/.test(s) && !/^[-+]{0,2}$/.test(s) && (!s.startsWith("-") || /^--?[A-Za-z0-9][A-Za-z0-9-]*$/.test(s));
  return bare ? s : `'${s.replace(/['‘’‚‛]/g, "$&$&")}'`;
}

/**
 * A PowerShell string literal, always quoted: for text inside an expression
 * (`'a' + 'b'`), where a bare word is a syntax error, not an argument.
 */
export const psString = (text) => `'${String(text).replace(/['‘’‚‛]/g, "$&$&")}'`;

/** A command line PowerShell runs with `&`: the program, then its arguments. */
export const psJoin = (argv) => `& ${psQuote(argv[0])}${argv.length > 1 ? ` ${argv.slice(1).map(psQuote).join(" ")}` : ""}`;

/** The two shell dialects Revive writes: POSIX sh (zsh, bash) and PowerShell (Windows). */
export const DIALECTS = ["posix", "pwsh"];
const dialectOf = (d) => (d === "pwsh" ? "pwsh" : "posix");

/**
 * How the shell's notes are drawn: ANSI's own colors, so they follow the
 * terminal's theme. `accent` (bold blue) names Revive, `warn` (bold yellow)
 * when it won't resume, `caution` (yellow) for what an automatic resume left
 * out, `strong` for the agent, `dim` for what's said only in passing.
 */
const SGR = { accent: "\\033[1;34m", warn: "\\033[1;33m", caution: "\\033[33m", strong: "\\033[1m", dim: "\\033[2m" };

/**
 * A `printf` command that prints one line of styled parts, each `[style, text]`
 * (style null for plain). The texts go in as quoted arguments, never in the
 * format, so a `%` or a quote in them prints as it is.
 */
export function printfLine(parts) {
  const format = parts.map(([style]) => (style ? `${SGR[style]}%s\\033[0m` : "%s")).join("");
  return `printf '${format}\\n' ${parts.map(([, text]) => shQuote(text)).join(" ")}`;
}

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
    restore: get("restore") === "on",
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

/** The labels that are the person's choice for that terminal, not part of a session. */
const CHOICES = ["auto", "restore"];

/** Every Revive label, removed. `auto` and `restore` stay: they are the person's choice for that terminal. */
export const clearArgs = () => labelArgs(Object.fromEntries(KEYS.filter((k) => !CHOICES.includes(k)).map((k) => [k, null])));

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

/**
 * `cd -- <folder> && <agent> … --resume <id>`, one line, or "". In PowerShell
 * (`dialect: "pwsh"`): `Set-Location -LiteralPath <folder>; & <agent> …`. A
 * PowerShell line carries no REVIVE_RESUME: it has no `VAR=x cmd` form, so
 * resumeScriptPwsh sets and unsets it around the agent instead.
 */
export function resumeLine(rec, { unattended = false, dialect = "posix" } = {}) {
  const argv = command(rec, "resume", { unattended });
  if (!argv) return "";
  if (dialectOf(dialect) === "pwsh") return `${rec.cwd ? `Set-Location -LiteralPath ${psQuote(rec.cwd)}; ` : ""}${psJoin(argv)}`;
  // Only this agent process inherits the original flags, so its SessionStart
  // (and compaction hooks) won't erase the flags omitted from its argv. A
  // later manual launch has its own environment and records its own flags.
  const context = unattended ? `REVIVE_RESUME=${shQuote(JSON.stringify({ agent: rec.agent, session: rec.session, flags: safeFlags(rec.agent, rec.flags ?? []) }))} ` : "";
  return `${rec.cwd ? `cd -- ${shQuote(rec.cwd)} && ` : ""}${context}${shJoin(argv)}`;
}

/**
 * What the recovered shell runs: say what is happening, go back to the
 * session's folder, start the agent, and mark the terminal failed when the
 * agent quits within a few seconds with an error (a session it can't find).
 * Nobody is watching it start, so the flags that lift approvals or the
 * sandbox are left out, and the note says which.
 */
/** Under the resume note when it restores: it goes on with work, not only the conversation. */
const RESTORE_NOTE = "  and going on with its unfinished turn (--restore): it may run its tools again";

export function resumeScript(rec, engine) {
  const line = resumeLine(rec, { unattended: true });
  if (!line) return "";
  const name = AGENTS[rec.agent].name;
  const { dropped } = attendedFlags(rec.agent, safeFlags(rec.agent, rec.flags ?? []));
  // `↻ Revive  resuming Claude Code session 9e458eb4 · REVIVE_AUTO=0 skips this`,
  // and under it, in yellow, any flag an automatic resume left out.
  const notes = [printfLine([
    ["accent", "↻ Revive"], [null, "  resuming "], ["strong", name], [null, ` session ${shortId(rec.session)}`],
    ["dim", " · REVIVE_AUTO=0 skips this"],
  ])];
  if (restores(rec)) notes.push(printfLine([["caution", RESTORE_NOTE]]));
  if (dropped.length) {
    notes.push(printfLine([["caution", `  without ${dropped.join(", ")} (only a resume from the Revive dialog keeps ${dropped.length > 1 ? "them" : "it"})`]]));
  }
  const body = [
    ...notes.map((n) => `  ${n}`),
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

/**
 * PowerShell's `printfLine`: one line of styled parts, each `[style, text]`.
 * The texts are single-quoted strings, joined with the escape character
 * built at run time (`[char]27`; Windows PowerShell 5.1 has no `` `e ``).
 */
const PS_SGR = { accent: "[1;34m", warn: "[1;33m", caution: "[33m", strong: "[1m", dim: "[2m" };
export function psLine(parts) {
  const pieces = parts.map(([style, text]) => (style
    ? `$__revive_e + ${psString(PS_SGR[style])} + ${psString(text)} + $__revive_e + '[0m'`
    : psString(text)));
  return `[Console]::Out.WriteLine(${pieces.join(" + ") || "''"})`;
}

/**
 * A Windows console writes in its code page (437, 850, …), where `↻` and `·`
 * become `?`: Revive's notes are written as UTF-8, and the console's own
 * encoding is put back before the agent starts. Setting it fails without a
 * console (output to a pipe), which is fine: then there is no code page to fix.
 */
const PS_UTF8_ON = [
  "  $__revive_e = [string][char]27",
  "  $__revive_oe = [Console]::OutputEncoding",
  "  try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}",
];
const PS_UTF8_OFF = "try { [Console]::OutputEncoding = $__revive_oe } catch {}";

/** What `check` prints for a session it won't resume by itself, in either dialect. */
export function notResumingLine(rec, why, { dialect = "posix" } = {}) {
  const parts = [
    ["warn", "↻ Revive"], [null, `  not resuming ${AGENTS[rec.agent].name} session ${shortId(rec.session)}: ${why}.`],
    ["dim", " Resume it by hand from the Revive dialog."],
  ];
  return dialectOf(dialect) === "pwsh" ? ["& {", ...PS_UTF8_ON, `  ${psLine(parts)}`, `  ${PS_UTF8_OFF}`, "}"].join("\n") : printfLine(parts);
}

/**
 * resumeScript for PowerShell (pwsh 7 and Windows PowerShell 5.1), run by
 * Revive's block in the profile. Same steps: the note, the folder, the agent
 * with the flags an automatic resume keeps, and `failed` when the agent quits
 * with an error within 15 seconds. REVIVE_RESUME is set for the agent's process
 * only, and taken away again when it ends. There is no /dev/tty to hand over:
 * on Windows the console is the shell's while its profile runs, and the agent
 * inherits it. Everything runs in a script block, so its variables don't stay
 * in the person's session; a folder that can't be entered stops it before
 * the agent starts.
 */
export function resumeScriptPwsh(rec, engine) {
  const argv = command(rec, "resume", { unattended: true });
  if (!argv) return "";
  const name = AGENTS[rec.agent].name;
  const { dropped } = attendedFlags(rec.agent, safeFlags(rec.agent, rec.flags ?? []));
  const notes = [psLine([
    ["accent", "↻ Revive"], [null, "  resuming "], ["strong", name], [null, ` session ${shortId(rec.session)}`],
    ["dim", " · $env:REVIVE_AUTO = 0 skips this"],
  ])];
  if (restores(rec)) notes.push(psLine([["caution", RESTORE_NOTE]]));
  if (dropped.length) {
    notes.push(psLine([["caution", `  without ${dropped.join(", ")} (only a resume from the Revive dialog keeps ${dropped.length > 1 ? "them" : "it"})`]]));
  }
  const context = JSON.stringify({ agent: rec.agent, session: rec.session, flags: safeFlags(rec.agent, rec.flags ?? []) });
  return [
    "& {",
    ...PS_UTF8_ON,
    ...notes.map((n) => `  ${n}`),
    // A folder that is gone since `check` vetted it: say so and leave this block, not the shell.
    ...(rec.cwd ? [
      `  try { Set-Location -LiteralPath ${psQuote(rec.cwd)} -ErrorAction Stop }`,
      `  catch { ${psLine([["warn", "↻ Revive"], [null, `  not resuming ${name} session ${shortId(rec.session)}: its folder is gone.`]])}; ${PS_UTF8_OFF}; return }`,
    ] : []),
    `  ${PS_UTF8_OFF}`,
    `  $env:REVIVE_RESUME = ${psString(context)}`,
    "  $__revive_t = [DateTime]::UtcNow",
    "  $global:LASTEXITCODE = 0",
    "  try {",
    `    ${psJoin(argv)}`,
    "    $__revive_ok = $? -and $LASTEXITCODE -eq 0",
    "  } catch { $__revive_ok = $false }",
    "  Remove-Item Env:REVIVE_RESUME -ErrorAction SilentlyContinue",
    "  if (-not $__revive_ok -and ([DateTime]::UtcNow - $__revive_t).TotalSeconds -lt 15) {",
    `    & node ${psQuote(engine)} failed`,
    "  }",
    "}",
  ].join("\n");
}

/**
 * A Windows command line split into words the way programs read it
 * (CommandLineToArgvW and the C runtime): spaces separate words outside double
 * quotes; 2n backslashes before a quote are n backslashes and the quote opens
 * or closes; 2n+1 are n backslashes and a literal quote; other backslashes are
 * themselves; `""` inside quotes is a literal quote.
 */
export function splitCommandLine(line) {
  const s = String(line ?? "");
  const out = [];
  let word = "", inWord = false, quoted = false;
  for (let i = 0; i < s.length;) {
    const c = s[i];
    if (c === "\\") {
      let n = 0;
      while (s[i] === "\\") { n++; i++; }
      inWord = true;
      if (s[i] === '"') {
        word += "\\".repeat(n >> 1);
        // An odd count escapes the quote; an even one leaves it to open or close.
        if (n % 2) { word += '"'; i++; }
      } else word += "\\".repeat(n);
      continue;
    }
    if (c === '"') {
      if (quoted && s[i + 1] === '"') { word += '"'; i += 2; }
      else { quoted = !quoted; i++; }
      inWord = true;
      continue;
    }
    if ((c === " " || c === "\t") && !quoted) {
      if (inWord) { out.push(word); word = ""; inWord = false; }
      i++;
      continue;
    }
    word += c;
    inWord = true;
    i++;
  }
  if (inWord) out.push(word);
  return out;
}

/**
 * Windows' process table, as the engine reads it from Win32_Process (see
 * `processes` in revive.mjs), in the same shape as parseProcesses: pid →
 * { ppid, since, argv }. `since` is the creation time in ISO form, which tells a
 * new process from an old one that had the same pid before a reboot. Takes the
 * JSON array (or the one object PowerShell prints for a single process).
 */
export function parseWinProcesses(text) {
  const table = new Map();
  let rows;
  try { rows = JSON.parse(String(text ?? "").trim() || "[]"); } catch { return table; }
  for (const row of Array.isArray(rows) ? rows : [rows]) {
    const pid = Number(row?.p);
    if (!Number.isInteger(pid) || pid <= 0) continue;
    table.set(pid, { ppid: Number(row.pp) || 0, since: typeof row.s === "string" && row.s ? row.s : null, argv: splitCommandLine(row.c ?? "") });
  }
  return table;
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

/** How long the dialog says sessions came back: long enough to open it after a restart. */
export const CAME_BACK_MS = 15 * 60 * 1000;

/**
 * The sessions that came back lately (a resume within CAME_BACK_MS, still
 * running), newest first, and when the latest did. `seen` is the latest one
 * the person already dismissed: a batch no newer than that isn't shown again.
 */
export function cameBack(entries = [], { now = Date.now(), seen = 0 } = {}) {
  const list = entries
    .filter((e) => e?.state === "running" && Number.isFinite(e?.rec?.resumed) && now - e.rec.resumed >= 0 && now - e.rec.resumed < CAME_BACK_MS)
    .sort((a, b) => b.rec.resumed - a.rec.resumed);
  const latest = list[0]?.rec.resumed ?? null;
  return latest !== null && latest > (Number(seen) || 0) ? { list, latest } : { list: [], latest: null };
}
