#!/usr/bin/env node
// Revive's engine. The mod can't run for a terminal while the app is closed or
// the machine is rebooting, so the work happens where the session lives:
//
//   revive.mjs hook [--agent K]   an agent's SessionStart and SessionEnd (Claude Code, Codex,
//                                 Droid, Cursor, Copilot CLI, pi's through pi/revive.ts and omp's through
//                                 omp/revive.ts): remember the
//                                 session on its terminal, or forget it
//   revive.mjs check --shell PID  from the shell's rc file: print the commands that
//                                 resume a session lost to a restart, or nothing
//   revive.mjs failed             the resume printed by `check` gave up at once
//   revive.mjs list [--focus T]   every remembered session, as JSON, for the dialog
//   revive.mjs resume T           resume T's session in T's shell
//   revive.mjs auto T on|off      allow or stop automatic resume for T
//   revive.mjs restore T on|off   omp only: resume T's session with --restore, which goes
//                                 on with its unfinished turn, or with --resume (the default)
//   revive.mjs adopt [T] [--dry-run]
//                                 remember the running Claude Code sessions
//                                 nobody recorded (started before Revive was
//                                 installed), or only T's; --dry-run says what
//                                 it would write
//   revive.mjs install [--zsh] [--bash] [--no-shell] [--no-codex] [--no-pi] [--no-omp] [--no-droid] [--no-cursor] [--no-copilot]
//   revive.mjs uninstall
//   revive.mjs doctor             what is installed, as JSON
//
// Hooks never fail an agent: every error is swallowed and the exit code is 0.

import { execFile, execFileSync, spawn } from "node:child_process";
import { existsSync, readFileSync, readdirSync, writeFileSync, copyFileSync, mkdirSync, renameSync, realpathSync, rmSync, statSync, lstatSync, symlinkSync, chmodSync } from "node:fs";
import { createConnection } from "node:net";
import { homedir } from "node:os";
import { delimiter, dirname, isAbsolute, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import {
  AGENTS, agentKey, carriedFlags, safeFlags, hookOwner, hookPayload, endAction, isOneShot, readRecord, labelArgs, clearArgs, resumedArgs,
  stateOf, shouldResume, ownShell, promptShell, idleWrappedShell, resumeScript, resumeLine, shQuote, shJoin, validId, needsOf, shortId, needsHint, unresumable,
  isPowerShell, resumeScriptPwsh, notResumingLine, parseWinProcesses, psQuote, canRestore,
} from "./lib/core.js";
import { agentDirs, claudeProject, claudeStartFolder, findSession } from "./lib/sessions.js";

const run = promisify(execFile);

/**
 * Windows: herdr-core starts PowerShell there, there is no `ps`, and folders
 * have owners and ACLs rather than mode bits. Each place that differs checks
 * this; the decisions themselves stay in lib/core.js.
 */
export const IS_WIN = process.platform === "win32";

/**
 * Runs a PowerShell script and returns what it printed (UTF-8). Windows has no
 * `ps` and Node can't read another process's parent or command line, so the
 * process table and folder owners come from PowerShell, which every Windows has
 * (Windows PowerShell 5.1; pwsh 7 when installed). The script goes in encoded,
 * so nothing in it is read by a shell; values go in through the environment.
 * REVIVE_PS: another PowerShell, for tests.
 */
let psExe;
function powershell() {
  psExe ??= process.env.REVIVE_PS || (hasCli("pwsh") ? "pwsh" : "powershell");
  return psExe;
}
const psArgs = (script) => ["-NoProfile", "-NonInteractive", "-NoLogo", "-ExecutionPolicy", "Bypass", "-EncodedCommand",
  Buffer.from(`[Console]::OutputEncoding = [Text.Encoding]::UTF8\n${script}`, "utf16le").toString("base64")];
const runPs = async (script, env = {}) => (await run(powershell(), psArgs(script), { env: { ...process.env, ...env }, maxBuffer: 16 * 1024 * 1024, windowsHide: true, timeout: 15_000 })).stdout;
const runPsSync = (script, env = {}) => execFileSync(powershell(), psArgs(script), { env: { ...process.env, ...env }, encoding: "utf8", maxBuffer: 16 * 1024 * 1024, windowsHide: true, timeout: 15_000, stdio: ["ignore", "pipe", "ignore"] });
export const ENGINE = fileURLToPath(import.meta.url);
const HC = process.env.REVIVE_HC || "hc";

// ── herdr-core ──────────────────────────────────────────────────────────────

/**
 * The environment `hc` runs in, without the agent's own variables. An `hc`
 * that finds no core starts one, which keeps the environment it was started
 * in and hands it to every terminal: CLAUDE_CODE_CHILD_SESSION there makes
 * each Claude Code after it think it is nested, and it stops saving transcripts.
 */
export const hcEnv = (env) => Object.fromEntries(Object.entries(env).filter(([k]) => !k.startsWith("CLAUDE_CODE_") && k !== "CLAUDECODE"));

async function hc(args, env = process.env) {
  const { stdout } = await run(HC, args, { env: hcEnv(env), maxBuffer: 8 * 1024 * 1024, timeout: 10_000 });
  return stdout;
}

/**
 * Whether herdr-core answers on the terminal's socket. An `hc` older than
 * HC_TERMINAL_SOCKET says nothing: it is taken as up, as before.
 */
function coreUp(socket = process.env.HC_TERMINAL_SOCKET) {
  if (!socket) return Promise.resolve(true);
  return new Promise((resolve) => {
    const c = createConnection(socket);
    const done = (ok) => { c.destroy(); resolve(ok); };
    c.setTimeout(1000, () => done(false));
    c.once("connect", () => done(true));
    c.once("error", () => done(false));
  });
}

const getTerminal = async (t) => JSON.parse(await hc(["get", t, "--json"]));
const label = (t, args) => (args.length ? hc(["label", t, ...args]) : null);

async function listTerminals() {
  const { terminals = [] } = JSON.parse(await hc(["ls", "--json"]));
  const all = await Promise.all(terminals.map((x) => getTerminal(x.address).catch(() => null)));
  return all.filter((t) => t && t.state === "live");
}

/**
 * The agent in the terminal's foreground, or null. By its command line, or,
 * for an agent behind a wrapper with another name (`node …/cli.mjs`), by its
 * own report, which only counts while something other than a shell at its
 * prompt is in the foreground: a report outlives the agent that sent it. A
 * shell running a script or a command keeps it, the terminal's own program
 * too (`fish -ic 'claude --resume …'` runs the agent as its child).
 */
function liveAgent(t) {
  const fg = t.foreground;
  if (!fg?.argv) return null;
  return agentKey(null, fg.argv) ?? (fg.pid && !promptShell(fg.argv) ? agentKey(t.status?.app) : null);
}

// ── hooks ───────────────────────────────────────────────────────────────────

async function readStdin() {
  if (process.stdin.isTTY) return {};
  let text = "";
  for await (const chunk of process.stdin) text += chunk;
  try { return JSON.parse(text || "{}"); } catch { return {}; }
}

/**
 * Every process: pid → { ppid, since, argv }. `since` is its start time as ps
 * prints it (`lstart`, always five words), which tells a new process from an
 * old one that had the same pid before a reboot. argv is split on spaces,
 * which is enough to recognize an agent by its first two words.
 */
export function parseProcesses(text) {
  const table = new Map();
  for (const line of text.split("\n")) {
    const words = line.trim().split(/\s+/);
    if (words.length < 7) continue;
    const pid = Number(words[0]);
    if (!pid) continue;
    table.set(pid, { ppid: Number(words[1]), since: words.slice(2, 7).join(" "), argv: words.slice(7) });
  }
  return table;
}

// One -o per column: procps-ng 3.3 (Amazon Linux 2) reads "pid=,ppid=,..." as a
// single pid column titled ",ppid=,...", which leaves ppid and argv empty.
async function processes(pids = null) {
  if (IS_WIN) return winProcesses(pids);
  const args = pids ? ["-o", "pid=", "-o", "ppid=", "-o", "lstart=", "-o", "args=", "-p", pids.join(",")] : ["-A", "-o", "pid=", "-o", "ppid=", "-o", "lstart=", "-o", "args="];
  try {
    const { stdout } = await run("ps", args, { maxBuffer: 16 * 1024 * 1024, env: { ...process.env, LC_ALL: "C" } });
    return parseProcesses(stdout);
  } catch (err) {
    // ps exits 1 when none of the asked pids exist.
    return parseProcesses(err?.stdout ?? "");
  }
}

/**
 * Windows' process table from Win32_Process: pid, parent, creation time (ISO,
 * UTC) and command line, read by parseWinProcesses. Only `pids` when given.
 */
const WIN_PROCESSES = `
$f = if ($env:REVIVE_PIDS) { (($env:REVIVE_PIDS -split ',') | ForEach-Object { "ProcessId=$([int]$_)" }) -join ' OR ' } else { $null }
$q = @{ ClassName = 'Win32_Process'; Property = 'ProcessId','ParentProcessId','CreationDate','CommandLine' }
if ($f) { $q.Filter = $f }
$rows = @(Get-CimInstance @q -ErrorAction SilentlyContinue | ForEach-Object {
  [pscustomobject]@{ p = $_.ProcessId; pp = $_.ParentProcessId; s = $(if ($_.CreationDate) { $_.CreationDate.ToUniversalTime().ToString('o') } else { $null }); c = $_.CommandLine }
})
ConvertTo-Json -InputObject $rows -Compress -Depth 2`;
export async function winProcesses(pids) {
  const list = pids ? pids.map(Number).filter((p) => Number.isInteger(p) && p > 0) : null;
  if (list && !list.length) return new Map();
  try { return parseWinProcesses(await runPs(WIN_PROCESSES, { REVIVE_PIDS: list ? list.join(",") : "" })); }
  catch { return new Map(); }
}

/** When a terminal's program started, or null. */
async function startOf(pid) {
  if (!pid) return null;
  return (await processes([pid])).get(pid)?.since ?? null;
}

/**
 * `--agent K`: the agent the hook was installed for (Droid's and Cursor's
 * hooks say so; Claude Code's and Codex's, from earlier versions, don't).
 */
const hintOf = (args) => {
  const i = args.indexOf("--agent");
  return i >= 0 && Object.prototype.hasOwnProperty.call(AGENTS, args[i + 1]) ? args[i + 1] : null;
};

async function hook(args = []) {
  // REVIVE_DEBUG=1 in the agent's environment: why a hook recorded nothing, on stderr.
  const skip = (why) => { if (process.env.REVIVE_DEBUG) process.stderr.write(`revive hook: ${why}\n`); };
  const payload = hookPayload(await readStdin());
  const t = process.env.HC_TERMINAL_ID;
  const { event, session } = payload;
  if (!t || !validId(session)) return skip(!t ? "not in a herdr terminal" : "no valid session id");
  // The agent ends when the core stops, and its SessionEnd comes after: with
  // no core, there is no label to change, and `hc` would start a new core.
  if (!(await coreUp())) return skip("herdr-core is not up");
  const terminal = await getTerminal(t);
  // The hook must belong to the agent in the terminal's foreground, not to a
  // `claude -p` that agent ran as a tool (it inherits HC_TERMINAL_ID too).
  const target = terminal.foreground?.pid ?? terminal.pid;
  if (!target) return skip("no foreground process");
  const table = await processes();
  const owner = hookOwner(table, process.ppid, target);
  if (!owner.owned) return skip(`not the foreground agent's hook (from ${process.ppid} to ${target}, ${table.size} processes)`);
  const rec = readRecord(terminal.labels);

  if (event === "SessionStart") {
    // The command line: the foreground's (exact words), else the agent
    // process the hook came from, when a wrapper with another name runs it.
    const fgArgv = terminal.foreground?.argv ?? terminal.argv ?? [];
    // pi and omp rename their process, which hides their flags: their extension sends the command line.
    const sent = payload.argv;
    const argv = sent && agentKey(null, sent) ? sent : agentKey(null, fgArgv) ? fgArgv : table.get(owner.agent)?.argv ?? fgArgv;
    // The command line first: the terminal's last OSC report may still be a
    // previous agent's, sent before this one reported anything.
    const key = agentKey(null, argv) ?? hintOf(args) ?? payload.agent ?? agentKey(terminal.status?.app);
    if (!key) return skip(`no known agent in ${JSON.stringify(argv.slice(0, 2))}`);
    // `claude -p "…"` or `codex exec` typed in the terminal: it answers and
    // quits, and its SessionEnd ("other") would leave its session on record in
    // place of the interactive one. Neither is worth bringing back.
    if (isOneShot(key, argv)) return skip("a one-shot run");
    const same = rec?.session === session;
    let flags = carriedFlags(key, argv);
    try {
      const resumed = JSON.parse(process.env.REVIVE_RESUME ?? "null");
      if (resumed?.agent === key && resumed.session === session && Array.isArray(resumed.flags)) flags = safeFlags(key, resumed.flags);
    } catch { /* not an automatic resume, or malformed context: use argv */ }
    // The hook runs in the agent's environment: whether it keeps its sessions
    // somewhere else. Only the names are recorded (see `needs` in core.js).
    const needs = needsOf(key, argv, process.env);
    await label(t, labelArgs({
      agent: key,
      session,
      cwd: payload.cwd || terminal.foreground?.cwd || terminal.cwd || "",
      flags: JSON.stringify(flags),
      env: null,
      needs: needs.length ? JSON.stringify(needs) : null,
      // pi and omp keep sessions where their flags, environment or settings say: the file named is the one to check.
      transcript: EXTENSION_AGENTS.includes(key) && payload.transcript && isAbsolute(String(payload.transcript)) ? payload.transcript : null,
      shell: terminal.pid ?? "",
      since: table.get(terminal.pid)?.since ?? null,
      at: same ? rec.at ?? Date.now() : Date.now(),
      ended: null,
      failed: null,
      // The same session starting again (a resume, a compaction) keeps its
      // "resumed" mark; a new one starts without.
      resumed: same ? rec.resumed : null,
    }));
    return;
  }

  if (event === "SessionEnd") {
    if (!rec || rec.session !== session) return;
    // Claude Code's reasons (Codex, Droid and pi's extension share them):
    // `/clear` (and `/resume` from inside) ends one session to start another in
    // the same process; that one's SessionStart records it, and clearing here
    // could race it and erase the new record. A signal (a crash, a kill, a
    // shutdown) reports "other": the record stays, worth bringing back. `/exit`,
    // Ctrl+C, `/logout`: the person ended it. Cursor's and Copilot's are in
    // their AGENTS entries.
    const action = endAction(rec.agent, payload.reason);
    if (action === "forget") await label(t, clearArgs());
    else if (action === "settle") await settleLater(t, terminal.pid, session, target);
  }
}

const settleMs = () => {
  const ms = Number(process.env.REVIVE_SETTLE_MS ?? 1500);
  return Number.isFinite(ms) && ms > 0 ? ms : 0;
};

/**
 * The agent exits right after its SessionEnd and takes its hooks with it, so
 * the wait runs in a process of its own, in a new session with no terminal:
 * `revive.mjs settle <terminal> <session> <shell pid> <agent pid>`. With no
 * wait (tests), it runs here.
 */
async function settleLater(t, pid, session, agentPid) {
  const args = [t, session, String(pid), String(agentPid)];
  if (!settleMs()) return settle(args);
  // windowsHide: on Windows a detached process gets a console window of its own otherwise.
  spawn(process.execPath, [ENGINE, "settle", ...args], { detached: true, stdio: "ignore", windowsHide: true }).unref();
}

const isPid = (s) => /^[1-9][0-9]*$/.test(s ?? "");

async function settle([t, session, pid, agentPid] = []) {
  if (!t || !validId(session) || !isPid(pid) || !isPid(agentPid)) return;
  if (await outlived(t, Number(pid), session, Number(agentPid))) await label(t, clearArgs());
}

const alive = (pid) => {
  try { process.kill(pid, 0); return true; } catch (err) { return err?.code === "EPERM"; }
};

/**
 * For a SessionEnd whose reason can't tell the person's exit from a signal
 * (Copilot CLI's `user_exit`): whether the terminal outlived the agent, so
 * the person ended it. A core restart or a reboot closes the terminal, which
 * hangs up its shell, or stops the core; `/exit` leaves the shell at its
 * prompt. After REVIVE_SETTLE_MS, the core must still be up, the terminal live
 * with the same shell, and the same session on record. Copilot still in the
 * foreground as the same process (`agentPid`) means `/clear`: the person ended
 * this session for a new one. Another Copilot there may be resuming it, so it
 * stays. Any doubt keeps it.
 */
async function outlived(t, pid, session, agentPid) {
  await new Promise((resolve) => setTimeout(resolve, settleMs()));
  if (!(await coreUp())) return false;
  const now = await getTerminal(t).catch(() => null);
  if (!now || now.state !== "live" || !pid || now.pid !== pid || !alive(now.pid)) return false;
  if (readRecord(now.labels)?.session !== session) return false;
  return liveAgent(now) !== "copilot" || now.foreground?.pid === agentPid;
}

// ── records read back ───────────────────────────────────────────────────────

/**
 * A record read from labels, with its folder checked on disk: `cd` goes to
 * the folder's real path, and only to an existing folder that belongs to this
 * user and that nobody else can write to: not anyone, and not its group,
 * unless that group is the user's own private one (a Linux umask of 002 makes
 * folders group-writable, with a group named after the user and no one else
 * in it). Otherwise `cwdRefused` names the recorded folder, and neither an
 * automatic resume nor one by hand runs.
 */
export function vetRecord(rec, { uid = process.getuid?.(), gid = process.getgid?.(), win = IS_WIN, owners = winOwners } = {}) {
  if (!rec?.cwd) return rec;
  try {
    const real = realpathSync(rec.cwd);
    const st = statSync(real);
    // Windows has no mode bits to read (every folder says 0o666) and no uid:
    // the folder's ACL says who owns it and who may write to it (winOwners).
    if (win) return st.isDirectory() && owners([real]).get(real) === true ? { ...rec, cwd: real } : { ...rec, cwd: null, cwdRefused: rec.cwd };
    const groupOk = (st.mode & 0o020) === 0 || (uid !== undefined && st.gid === gid && gid === uid);
    if (st.isDirectory() && (uid === undefined || st.uid === uid) && (st.mode & 0o002) === 0 && groupOk) return { ...rec, cwd: real };
  } catch { /* gone */ }
  return { ...rec, cwd: null, cwdRefused: rec.cwd };
}

/**
 * Windows' half of vetRecord: for each folder, whether it is owned by this
 * user, the Administrators group or SYSTEM, and nobody anonymous or everyone
 * (Everyone, Anonymous Logon) may write to it. Other users' write access is not
 * refused: Windows gives Authenticated Users Modify on every folder made
 * outside the user profile (C:\\code, D:\\work), the place most code lives, so
 * refusing it would refuse nearly every project. Answers are kept for the
 * process: the dialog asks for many folders at once (see `list`).
 */
const WIN_OWNERS = `
$me = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$owners = @($me, 'S-1-5-32-544', 'S-1-5-18')
$open = @('S-1-1-0', 'S-1-5-7')
$res = @{}
foreach ($p in @(ConvertFrom-Json $env:REVIVE_PATHS)) {
  try {
    $acl = Get-Acl -LiteralPath $p
    $ok = $owners -contains $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    foreach ($r in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
      if ($r.AccessControlType -eq 'Allow' -and $open -contains $r.IdentityReference.Value -and ([int64]$r.FileSystemRights -band 0x500C0006)) { $ok = $false }
    }
    $res[$p] = $ok
  } catch { $res[$p] = $false }
}
ConvertTo-Json -InputObject $res -Compress`;
const ownerCache = new Map();
export function winOwners(paths) {
  const ask = [...new Set(paths)].filter((p) => !ownerCache.has(p));
  if (ask.length) {
    let got = {};
    try { got = JSON.parse(runPsSync(WIN_OWNERS, { REVIVE_PATHS: JSON.stringify(ask) }) || "{}"); } catch { /* unknown: refused */ }
    for (const p of ask) ownerCache.set(p, got[p] === true);
  }
  return new Map(paths.map((p) => [p, ownerCache.get(p) === true]));
}

/** Asks for every recorded folder at once (Windows), so the dialog makes one PowerShell call, not one per terminal. */
function primeOwners(terminals) {
  if (!IS_WIN) return;
  const real = (p) => { try { return realpathSync(p); } catch { return null; } };
  winOwners(terminals.map((t) => readRecord(t.labels)?.cwd).filter(Boolean).map(real).filter(Boolean));
}

const loadRecord = (labels) => vetRecord(readRecord(labels));

// ── the shell ───────────────────────────────────────────────────────────────

const claudeDir = (env = process.env) => env.CLAUDE_CONFIG_DIR || join(homedir(), ".claude");
const copilotDir = () => agentDirs({ ...process.env, HOME: homedir(), USERPROFILE: homedir() }).copilot;

/**
 * Claude Code writes a session's transcript only once it has a message, so a
 * session opened and left empty can't be resumed: `--resume` says "No
 * conversation found". Its folder is named after the cwd (`claudeProject`);
 * other folders are searched when the agent moved. Codex is not checked. Only this process's
 * `CLAUDE_CONFIG_DIR` is searched: a record with needs is never checked here
 * (see `resume`). pi and omp do the same; their record names the file, which
 * is all there is to check.
 */
export function hasTranscript(rec) {
  if (EXTENSION_AGENTS.includes(rec.agent)) return !rec.transcript || existsSync(rec.transcript);
  if (rec.agent === "copilot") return existsSync(join(copilotDir(), "session-state", rec.session));
  if (rec.agent !== "claude") return true;
  const projects = join(claudeDir(), "projects");
  const file = `${rec.session}.jsonl`;
  if (rec.cwd && existsSync(join(projects, claudeProject(rec.cwd), file))) return true;
  try { return readdirSync(projects).some((dir) => existsSync(join(projects, dir, file))); }
  catch { return false; }
}

async function check(args) {
  const t = process.env.HC_TERMINAL_ID;
  if (!t) return;
  const shellPid = Number(args[args.indexOf("--shell") + 1]);
  // Which shell reads what this prints: POSIX sh (zsh, bash) or PowerShell's block.
  const dialect = args.includes("--dialect") && args[args.indexOf("--dialect") + 1] === "pwsh" ? "pwsh" : "posix";
  const terminal = await getTerminal(t);
  const rec = loadRecord(terminal.labels);
  const debug = (why) => { if (process.env.REVIVE_DEBUG) process.stderr.write(`revive: ${why}\n`); };
  // The terminal's own shell is the common case and needs no ps. A shell a
  // wrapper runs as its child is the terminal's too (ownShell).
  const pid = terminal.pid ?? null;
  let own = pid !== null && shellPid === pid, since = null;
  if (own) since = await startOf(pid);
  else if (rec && pid !== null) {
    const table = await processes();
    const verdict = ownShell(table, shellPid, pid, process.env.REVIVE_SHELL);
    if (!verdict.own) { debug(verdict.why); return; }
    own = true;
    since = table.get(pid)?.since ?? null;
  }
  // shouldResume asks whether the shell is the terminal's: it is, when `own`.
  const verdict = shouldResume(rec, { pid, since, shellPid: own ? pid : shellPid, env: process.env });
  debug(verdict.why);
  if (!verdict.go && verdict.hint) {
    // Said once: marked failed, the next shell stays quiet; the dialog offers it by hand.
    await label(t, labelArgs({ failed: Date.now() }));
    process.stdout.write(`${notResumingLine(rec, verdict.why, { dialect })}\n`);
    return;
  }
  if (!verdict.go) return;
  if (!hasTranscript(rec)) { debug("the session has no transcript; forgot it"); await label(t, clearArgs()); return; }
  // Mark it first: a second shell started from this one must not resume it again.
  await label(t, resumedArgs({ pid, since }));
  process.stdout.write((dialect === "pwsh" ? resumeScriptPwsh(rec, ENGINE) : resumeScript(rec, ENGINE)) + "\n");
}

async function failed() {
  const t = process.env.HC_TERMINAL_ID;
  if (t) await label(t, labelArgs({ failed: Date.now() }));
}

// ── the dialog ──────────────────────────────────────────────────────────────

/** Claude Code keeps `sessions/<pid>.json` for each interactive process. */
function claudeSessionFor(pid) {
  const dir = join(claudeDir(), "sessions");
  try {
    const id = JSON.parse(readFileSync(join(dir, `${pid}.json`), "utf8")).sessionId;
    return validId(id) ? id : null;
  } catch { return null; }
}

/**
 * Whether a running session can be forked: a fork resumes it, so it needs a
 * transcript. Only a sure "no" says false. A record without the agent's
 * config folder (one from before Revive kept it) is checked against this
 * process's folder only when the agent's own `sessions/<pid>.json` is there,
 * which proves it is the same folder; otherwise the answer is unknown (null)
 * and the fork is let through.
 */
function forkable(rec, fgPid) {
  if (EXTENSION_AGENTS.includes(rec.agent)) return hasTranscript(rec);
  if (rec.agent !== "claude") return true;
  const known = fgPid && claudeSessionFor(fgPid) !== null;
  if (!known) return null;
  return hasTranscript(rec);
}

/** A `ps` start time (`Sat Oct 31 18:49:55 2026`, in LC_ALL=C) in ms, or null. */
const startMs = (since) => { const ms = Date.parse(since ?? ""); return Number.isFinite(ms) ? ms : null; };

/**
 * The session a live agent nobody recorded holds, from the files it writes
 * (lib/sessions.js), and the folder to resume or fork it in: `{ session, cwd }`,
 * with `why` when Claude Code's start folder can't be told (`cwd` is then the
 * one it runs in now), or null.
 */
function runningSession(t, agent, fgSince) {
  if (!t.foreground?.pid) return null;
  const dirs = agentDirs();
  const now = t.foreground.cwd ?? t.cwd ?? null;
  const session = findSession(agent, { dirs, pid: t.foreground.pid, cwd: now, startedMs: startMs(fgSince) });
  if (!session) return null;
  // Claude Code files a conversation under the folder it started in, and
  // finds it only from there; the agent may have moved since.
  if (agent !== "claude") return { session, cwd: now };
  const start = claudeStartFolder({ dirs, session, cwd: now });
  return start.why ? { session, cwd: now, why: start.why } : { session, cwd: start.cwd };
}

/**
 * Windows: herdr-core updates a terminal's foreground a moment after it changes,
 * so an agent that just died can still be named there. A foreground program
 * the process table no longer has is not running.
 */
const foregroundGone = (t, procs) => IS_WIN && Boolean(t.foreground?.pid) && t.foreground.pid !== t.pid && !procs.has(t.foreground.pid);

function describe(t, since, focus, fgSince = null, procs = null) {
  const rec = loadRecord(t.labels);
  const live = procs && foregroundGone(t, procs) ? null : liveAgent(t);
  const entry = {
    address: t.address,
    where: t.labels?.where ?? null,
    title: t.title ?? "",
    pid: t.pid ?? null,
    live,
    rec,
    state: rec ? stateOf(rec, { live: live === rec.agent, pid: t.pid ?? null, since }) : null,
  };
  // A live agent nobody recorded yet (started before Revive was installed),
  // found from the files it writes (lib/sessions.js).
  if (!rec && live) {
    const found = runningSession(t, live, fgSince);
    if (found) {
      entry.rec = { agent: live, session: found.session, cwd: found.cwd, flags: carriedFlags(live, t.foreground.argv), shell: t.pid, auto: true };
      entry.state = "running";
      entry.unrecorded = true;
      // Only Claude Code's can be remembered (`adopt`): false, with why, while
      // its start folder can't be told; absent for the others.
      if (live === "claude") entry.rememberable = !found.why;
      if (live === "claude" && found.why) entry.rememberWhy = found.why;
    }
  }
  // An agent running with nothing on record: the dialog still names it, and its folder.
  if (!entry.rec && live) entry.folder = t.foreground?.cwd ?? t.cwd ?? null;
  // Only the focused terminal's card offers Fork, so only it is checked.
  if (entry.rec && entry.state === "running" && t.address === focus) entry.forkable = forkable(entry.rec, t.foreground?.pid);
  return entry;
}

async function list(args) {
  const focus = args.includes("--focus") ? args[args.indexOf("--focus") + 1] : null;
  const terminals = await listTerminals();
  const pids = terminals.flatMap((t) => [t.pid, t.foreground?.pid]).filter(Boolean);
  const procs = pids.length ? await processes([...new Set(pids)]) : new Map();
  primeOwners(terminals);
  const since = (pid) => (pid ? procs.get(pid)?.since ?? null : null);
  const entries = terminals.map((t) => describe(t, since(t.pid), focus, since(t.foreground?.pid), procs)).filter((e) => e.rec || e.address === focus);
  // The setup only changes on install; the dialog asks for it when it opens and after.
  const out = { entries };
  if (args.includes("--setup")) out.setup = doctorReport();
  process.stdout.write(JSON.stringify(out) + "\n");
}

async function resume(args) {
  const t = args[0];
  const terminal = await getTerminal(t);
  const rec = loadRecord(terminal.labels);
  if (!rec) throw new Error(`${t} has no remembered session.`);
  // Herdr can show a killed agent as the foreground for a moment on Windows.
  const fgGone = IS_WIN && terminal.foreground?.pid ? foregroundGone(terminal, await processes([terminal.foreground.pid])) : false;
  const live = fgGone ? null : liveAgent(terminal);
  if (live === rec.agent) throw new Error(`${AGENTS[rec.agent].name} is already running in ${t}.`);
  // Another agent, even one the terminal's own program runs: the line would be its next message.
  if (live) throw new Error(`${t} is busy with ${AGENTS[live].name}. Quit it first.`);
  const fg = terminal.foreground;
  if (!fgGone && fg?.pid && terminal.pid && fg.pid !== terminal.pid) {
    // A wrapper's child shell is the terminal's shell too, just as in check.
    // An unrelated shell or any other foreground program is still busy.
    if (!idleWrappedShell(await processes(), fg, terminal.pid)) throw new Error(`${t} is busy with ${fg.argv?.[0] ?? "another program"}. Quit it first.`);
  }
  // Typed into the shell in front: PowerShell's own syntax there (Windows), else POSIX sh.
  const dialect = isPowerShell(fg?.argv ?? terminal.argv ?? []) ? "pwsh" : "posix";
  const line = resumeLine(rec, { dialect });
  if (!line) throw new Error(`Can't build a resume command for ${t}.`);
  // Not sent without its folder (the agent would start elsewhere, with its
  // flags), nor without what it needs, and not forgotten: its sessions are
  // somewhere this shell may not look. The dialog says the same before a click.
  const why = unresumable(rec);
  if (why?.folder) throw new Error(`Won't resume: its folder ${tilde(why.folder)} is missing, not yours, or writable by others.`);
  if (why?.needs) throw new Error(`Won't resume here: it ran with ${why.needs.join(", ")}, which Revive doesn't carry. ${needsHint(rec, { dialect })}`);
  if (!hasTranscript(rec)) {
    await label(t, clearArgs());
    throw new Error("That session never got a message, so there is nothing to resume. Forgot it.");
  }
  await label(t, resumedArgs({ pid: terminal.pid, since: await startOf(terminal.pid) }));
  // Run from inside a herdr terminal, `hc send` delivers the text as a note from
  // that terminal (`<hc from="t3">…</hc>`), which the shell can't run.
  const { HC_TERMINAL_ID: _, ...env } = process.env;
  await hc(["send", t, line], env);
}

async function auto(args) {
  const [t, value] = args;
  await label(t, labelArgs({ auto: value === "off" ? "off" : null }));
}

/**
 * Whether T's resume goes on with the interrupted turn (omp's --restore). Off
 * unless asked for: the turn may run its tools again. Like `auto`, the choice
 * stays with the terminal for its next sessions.
 */
async function restore(args) {
  const [t, value] = args;
  if (!t || !["on", "off"].includes(value)) throw new Error("usage: revive.mjs restore T on|off");
  if (value === "on") {
    const rec = loadRecord((await getTerminal(t)).labels);
    if (rec && !canRestore(rec.agent)) throw new Error(`${AGENTS[rec.agent]?.name ?? rec.agent} can't go on with an interrupted turn; only omp can.`);
  }
  await label(t, labelArgs({ restore: value === "on" ? "on" : null }));
}

// ── adopt ───────────────────────────────────────────────────────────────────

/**
 * What adopting a terminal would record: `{ agent, session, fields }`, the
 * labels its SessionStart hook would have written; `{ agent, why }` for an
 * agent Revive won't record; or null (no agent, or one already on record).
 * Every value comes from the agent's own process: its session file in this
 * user's Claude folder, its live command line, the transcript `--resume`
 * reads. A label is only asked whether a record exists, so none can make
 * adopt record anything, and what it writes is read back through the same
 * filters as a hook's (readRecord, vetRecord).
 */
function adoption(t, procs) {
  if (readRecord(t.labels)) return null;
  const agent = liveAgent(t);
  if (!agent) return null;
  const argv = t.foreground?.argv ?? [];
  // `claude -p` typed in the terminal: it answers and quits, as for the hook.
  if (isOneShot(agent, argv)) return { agent, why: "a one-shot run, with no session to bring back" };
  // Only Claude Code's sessions/<pid>.json names its session for sure. The
  // others are found by the newest file in their folder's store, good enough
  // to show but not to keep as a record.
  if (agent !== "claude") return { agent, why: "only a running Claude Code session can be remembered; start it again to record it" };
  const found = runningSession(t, agent, procs.get(t.foreground?.pid)?.since);
  if (!found || !validId(found.session)) return { agent, why: "Revive can't find its session from its files" };
  const { session, cwd } = found;
  if (found.why) return { agent, session, why: found.why };
  // The folder a resume would `cd` to, checked now as it will be then.
  if (vetRecord({ cwd }).cwdRefused) return { agent, session, why: `its folder ${tilde(cwd)} is missing, not yours, or writable by others` };
  // The session was found in the folder this process's variables name, so the
  // agent ran with the same ones: names only, as the hook records them.
  const needs = needsOf(agent, argv, process.env);
  return {
    agent,
    session,
    fields: {
      agent,
      session,
      cwd,
      flags: JSON.stringify(carriedFlags(agent, argv)),
      env: null,
      needs: needs.length ? JSON.stringify(needs) : null,
      // Only pi and omp name a session file.
      transcript: null,
      shell: t.pid ?? "",
      since: procs.get(t.pid)?.since ?? null,
      at: Date.now(),
      ended: null,
      failed: null,
      resumed: null,
    },
  };
}

/**
 * Adopts every local live terminal (or only `only`) running an agent nobody
 * recorded. One session, one terminal: an id already on record elsewhere, or
 * found in two terminals, would come back in two panes, so it is skipped.
 * Returns one result per agent, written unless `dry`.
 */
async function adoptRunning({ only = null, dry = false } = {}) {
  const all = await listTerminals();
  const local = all.filter((t) => !t.address.includes("/") && (!only || t.address === only));
  if (only && !local.length) throw new Error(`${only} is not a live terminal on this computer.`);
  const pids = local.flatMap((t) => [t.pid, t.foreground?.pid]).filter(Boolean);
  const procs = pids.length ? await processes([...new Set(pids)]) : new Map();
  primeOwners(local);
  const results = [];
  for (const t of local) {
    const plan = adoption(t, procs);
    if (only && !plan) throw new Error(readRecord(t.labels) ? `${only} already has a remembered session.` : `No agent session in ${only}.`);
    if (plan) results.push({ address: t.address, where: t.labels?.where ?? null, ...plan });
  }
  const taken = new Set(all.map((t) => readRecord(t.labels)?.session).filter(Boolean));
  const seen = new Map();
  for (const r of results) if (r.fields) seen.set(r.session, (seen.get(r.session) ?? 0) + 1);
  for (const r of results) {
    if (!r.fields) continue;
    r.why = taken.has(r.session) ? "its session is already remembered in another terminal"
      : seen.get(r.session) > 1 ? "another terminal holds the same session" : undefined;
    if (r.why) { delete r.fields; continue; }
    if (dry) continue;
    try { await label(r.address, labelArgs(r.fields)); }
    catch (err) { r.why = `hc label failed: ${String(err?.stderr || err?.message || err).trim()}`; r.failed = true; delete r.fields; }
  }
  if (only && results[0]?.why) throw new Error(`Won't remember ${AGENTS[results[0].agent].name} in ${only}: ${results[0].why}.`);
  return results;
}

/** What adopt did, or would do, as text: the sessions, and each agent left out with why. */
function adoptReport(results, { dry = false } = {}) {
  const at = (r) => (r.where ? `${r.address} (${r.where})` : r.address);
  const done = results.filter((r) => r.fields);
  const left = results.filter((r) => r.why);
  const lines = [];
  if (!done.length) lines.push("No running session to remember.");
  else {
    lines.push(`${dry ? "Would remember" : "Remembered"} ${done.length} running session${done.length === 1 ? "" : "s"}:`);
    for (const r of done) {
      lines.push(`  ${at(r)}  ${AGENTS[r.agent].name} ${shortId(r.session)}  ${tilde(r.fields.cwd)}`);
      if (dry) lines.push(`    ${shJoin([HC, "label", r.address, ...labelArgs(r.fields)])}`);
    }
  }
  if (left.length) lines.push("Not remembered:", ...left.map((r) => `  ${at(r)}  ${AGENTS[r.agent].name}: ${r.why}`));
  return `${lines.join("\n")}\n`;
}

async function adopt(args) {
  const dry = args.includes("--dry-run");
  const only = args.find((a) => !a.startsWith("-")) ?? null;
  const results = await adoptRunning({ only, dry });
  process.stdout.write(adoptReport(results, { dry }));
  if (results.some((r) => r.failed)) throw new Error("Some sessions weren't remembered: see above.");
}

/**
 * `doctor`: what is installed, and how many running sessions `adopt` could
 * remember (null when hc wasn't asked or failed). The dialog's setup is
 * doctorReport() alone: it lists the sessions itself.
 */
async function doctor() {
  let count = null;
  try { count = await unremembered(); } catch { /* no hc, or no core: unknown, said as null */ }
  process.stdout.write(JSON.stringify({ ...doctorReport(), unremembered: count }, null, 2) + "\n");
}

// ── install ─────────────────────────────────────────────────────────────────

/**
 * The engine as a hook runs it. Under the home folder it is written as
 * `"$HOME/…"` (Claude Code runs hooks through a shell): a settings file kept in
 * a dotfiles repository and copied to another machine, where home is another
 * folder, still finds the engine there. Elsewhere it is the quoted path.
 */
export function engineWord(engine = ENGINE, home = homedir(), win = IS_WIN) {
  // Windows: a hook may run through Git Bash (Claude Code does), cmd or
  // PowerShell; a double-quoted path reads the same in all three.
  if (win) return `"${engine}"`;
  const rest = home && engine.startsWith(`${home}/`) ? engine.slice(home.length) : null;
  return rest !== null && /^[A-Za-z0-9_@%+=:,./ -]+$/.test(rest) ? `"$HOME${rest}"` : shQuote(engine);
}
const HOOK_COMMAND = `node ${IS_WIN ? engineWord() : shQuote(ENGINE)} hook`;
const PORTABLE_HOOK_COMMAND = `node ${engineWord()} hook`;
const hookCommand = (agent = null, portable = false) => {
  const base = portable ? PORTABLE_HOOK_COMMAND : HOOK_COMMAND;
  return agent ? `${base} --agent ${agent}` : base;
};
const claudeSettings = () => join(claudeDir(), "settings.json");
const codexDir = () => process.env.CODEX_HOME || join(homedir(), ".codex");
const codexHooks = () => join(codexDir(), "hooks.json");
const piDir = () => process.env.PI_CODING_AGENT_DIR || join(homedir(), ".pi", "agent");
// omp reads PI_CODING_AGENT_DIR too, but a pi setup sets it for pi: omp's own folder is assumed.
const ompDir = () => join(homedir(), ".omp", "agent");
/**
 * pi and omp have no hooks file: their hooks come from an extension, kept in
 * the mod and linked where each loads extensions. It finds the engine from its
 * own place. `marker` is its first line; a copy placed by something else (a
 * Nix store path) counts too.
 */
const EXTENSIONS = {
  pi: { dir: piDir, flag: "--no-pi", source: join(dirname(ENGINE), "pi", "revive.ts"), marker: "herdr-revive: pi extension" },
  omp: { dir: ompDir, flag: "--no-omp", source: join(dirname(ENGINE), "omp", "revive.ts"), marker: "herdr-revive: omp extension" },
};
const EXTENSION_AGENTS = Object.keys(EXTENSIONS);
const extensionPath = (key) => join(EXTENSIONS[key].dir(), "extensions", "herdr-revive.ts");
const isExtension = (key, path) => readText(path).includes(EXTENSIONS[key].marker);
const factoryDir = () => agentDirs({ ...process.env, HOME: homedir(), USERPROFILE: homedir() }).factory;
const cursorDir = () => agentDirs({ ...process.env, HOME: homedir(), USERPROFILE: homedir() }).cursor;
const copilotHooks = () => join(copilotDir(), "hooks", "herdr-revive.json");

/**
 * Whether a CLI is installed: on PATH, or in ~/.local/bin, where the Droid and
 * cursor-agent installers put it, or in `extra` folders. The Herdr app may run Revive with a shorter
 * PATH than the person's shell has, hence the fallback.
 */
const hasCli = (bin, extra = []) => {
  // Windows: PATH is split by `;`, and a program is `bin.exe`, `bin.cmd`, … (PATHEXT).
  const exts = IS_WIN ? ["", ...(process.env.PATHEXT || ".COM;.EXE;.BAT;.CMD").split(";").filter(Boolean)] : [""];
  return [...(process.env.PATH ?? "").split(delimiter).filter(Boolean), join(homedir(), ".local", "bin"), ...extra]
    .some((dir) => exts.some((ext) => existsSync(join(dir, bin + ext))));
};

/**
 * On macOS herdr-core starts terminals as login shells (`zsh -l`, `bash -l`).
 * zsh reads .zshrc either way; a login bash reads the first of .bash_profile,
 * .bash_login and .profile, and not .bashrc. Creating .bash_profile where
 * only .profile exists would stop bash from reading .profile, so the block
 * goes into whichever bash reads.
 * On Linux herdr-core starts bash without `-l` (herdrdev/herdr-core#99): an
 * interactive bash that is no login shell reads only .bashrc, so the block
 * goes there. A login bash on Linux usually reaches it too: Debian's and
 * Ubuntu's .profile source .bashrc.
 */
const BASH_LOGIN = [".bash_profile", ".bash_login", ".profile"];
const bashLogin = () => {
  const found = BASH_LOGIN.map((f) => join(homedir(), f)).find((p) => existsSync(p));
  return found ?? join(homedir(), ".bash_profile");
};
const bashRc = (platform = process.env.REVIVE_PLATFORM || process.platform) => (platform === "darwin" ? bashLogin() : join(homedir(), ".bashrc"));
/**
 * zsh reads .zshrc from $ZDOTDIR, which people often set in ~/.zshenv. The
 * dialog's Install runs from the app, whose environment never read that
 * file, so zsh itself is asked: `zsh -c` reads .zshenv and nothing else.
 */
let zdotdir;
function zshDir() {
  if (zdotdir !== undefined) return zdotdir;
  zdotdir = process.env.ZDOTDIR || null;
  if (!zdotdir) {
    try {
      const out = execFileSync("zsh", ["-c", 'print -r -- "${ZDOTDIR:-$HOME}"'], { encoding: "utf8", timeout: 5000, stdio: ["ignore", "pipe", "ignore"] }).trim();
      if (out.startsWith("/")) zdotdir = out;
    } catch { /* no zsh: its rc file is moot */ }
  }
  zdotdir ||= homedir();
  return zdotdir;
}
/**
 * PowerShell's profile, which herdr-core's PowerShell (pwsh 7 when installed,
 * else Windows PowerShell 5.1) runs as it starts. Each one is asked where it
 * keeps it, as zsh is: Documents may be redirected (OneDrive), and the two
 * keep separate files. REVIVE_PWSH_PROFILE and REVIVE_POWERSHELL_PROFILE name
 * another file, for tests: a PowerShell finds Documents from Windows itself,
 * not from USERPROFILE, so a test home can't move it.
 */
const psProfiles = {};
function psProfile(kind) {
  const override = process.env[kind === "pwsh" ? "REVIVE_PWSH_PROFILE" : "REVIVE_POWERSHELL_PROFILE"];
  if (override) return override;
  if (psProfiles[kind] !== undefined) return psProfiles[kind];
  try {
    const out = execFileSync(kind === "pwsh" ? "pwsh" : "powershell", ["-NoProfile", "-NonInteractive", "-Command", "$PROFILE.CurrentUserCurrentHost"],
      { encoding: "utf8", timeout: 15_000, windowsHide: true, stdio: ["ignore", "pipe", "ignore"] }).trim();
    psProfiles[kind] = isAbsolute(out) ? out : null;
  } catch { psProfiles[kind] = null; /* that PowerShell isn't installed */ }
  return psProfiles[kind];
}
/** zsh and bash, or on Windows the two PowerShells. A shell whose file can't be found has none. */
const RC = IS_WIN
  ? { pwsh: () => psProfile("pwsh"), powershell: () => psProfile("powershell") }
  : { zsh: () => join(zshDir(), ".zshrc"), bash: () => bashRc() };
const PS_KINDS = ["pwsh", "powershell"];
// Every file a block may be in, for uninstall.
const ALL_RC = () => (IS_WIN ? PS_KINDS.map((k) => RC[k]()).filter(Boolean) : [RC.zsh(), ...BASH_LOGIN.map((f) => join(homedir(), f)), join(homedir(), ".bashrc")]);
const BEGIN = "# >>> herdr-revive >>>";
const END = "# <<< herdr-revive <<<";
const EVENTS = ["SessionStart", "SessionEnd"];

const isOurs = (h) => typeof h?.command === "string" && h.command.includes("revive.mjs") && /\bhook\b/.test(h.command);

export function shellBlock(engine = ENGINE) {
  const q = shQuote(engine);
  return [
    BEGIN,
    "# Resume the coding agent a herdr terminal lost to a restart or reboot.",
    "# REVIVE_DEBUG=1 says why it did or didn't.",
    `if [ -n "$HC_TERMINAL_ID" ] && [ -f ${q} ] && command -v node >/dev/null 2>&1; then`,
    `  __revive_j="$("\${REVIVE_HC:-hc}" get "$HC_TERMINAL_ID" --json 2>/dev/null)"`,
    // Two cheap tests before starting node: a session is remembered here, and
    // this shell wasn't started by hand from one that ran this block (its
    // REVIVE_SHELL). Whether it is the terminal's own (its program, or the
    // shell a wrapper runs as its child), `check` decides from the processes.
    `  case "$__revive_j" in *'"revive.session"'*) __revive_has=1 ;; *) __revive_has= ;; esac`,
    `  if [ -z "$__revive_has" ]; then`,
    `    if [ -n "$REVIVE_DEBUG" ]; then echo "revive: nothing remembered on $HC_TERMINAL_ID" >&2; fi`,
    `  elif [ "$REVIVE_SHELL" = "$PPID" ]; then`,
    `    if [ -n "$REVIVE_DEBUG" ]; then echo "revive: a shell started inside the terminal's own shell" >&2; fi`,
    `  else`,
    `    if [ -n "$REVIVE_DEBUG" ]; then __revive="$(node ${q} check --shell $$)"`,
    `    else __revive="$(node ${q} check --shell $$ 2>/dev/null)"; fi`,
    // The agent is interactive: start it at the first prompt, once the rc
    // files are done and the terminal is the shell's again (an instant
    // prompt, for one, holds on to it while they run).
    `    if [ -z "$__revive" ]; then unset __revive`,
    `    elif [ -n "$ZSH_VERSION" ]; then`,
    `      __revive_run() { add-zsh-hook -d precmd __revive_run; eval "$__revive"; unset __revive; unfunction __revive_run; }`,
    `      autoload -Uz add-zsh-hook && add-zsh-hook precmd __revive_run`,
    `    elif [ -n "$BASH_VERSION" ]; then`,
    `      __revive_run() { PROMPT_COMMAND="\${PROMPT_COMMAND#__revive_run;}"; eval "$__revive"; unset __revive; unset -f __revive_run; }`,
    `      PROMPT_COMMAND="__revive_run;\${PROMPT_COMMAND}"`,
    `    else eval "$__revive"; unset __revive; fi`,
    `  fi`,
    `  unset __revive_j __revive_has`,
    // Shells started from this one know it ran here (see ownShell).
    `  REVIVE_SHELL=$$; export REVIVE_SHELL`,
    `fi`,
    END,
  ].join("\n");
}

/**
 * shellBlock for PowerShell's profile, pwsh 7 and Windows PowerShell 5.1 alike
 * (so: no `??`, no `&&`, and ASCII only, since 5.1 reads a profile without a
 * byte-order mark as the ANSI code page). The same steps: two cheap tests
 * before starting node (a session is remembered here, and this isn't a shell
 * started by hand from one that ran this block), then `check`, whose output is
 * PowerShell (resumeScriptPwsh). It runs while the profile loads rather than at
 * the first prompt: PowerShell has no prompt hook to run an interactive
 * program from, and nothing holds the console while a profile runs. Nothing in
 * it may break the shell starting up, so it all sits in a try.
 */
export function pwshBlock(engine = ENGINE) {
  const q = psQuote(engine);
  return [
    BEGIN,
    "# Resume the coding agent a herdr terminal lost to a restart or reboot.",
    "# $env:REVIVE_DEBUG = 1 says why it did or didn't.",
    `if ($env:HC_TERMINAL_ID -and (Test-Path -LiteralPath ${q}) -and (Get-Command node -CommandType Application -ErrorAction Ignore)) {`,
    "  try {",
    "    $__revive_hc = if ($env:REVIVE_HC) { $env:REVIVE_HC } else { 'hc' }",
    '    $__revive_j = (& $__revive_hc get $env:HC_TERMINAL_ID --json 2>$null) -join "`n"',
    "    if ($__revive_j -notlike '*\"revive.session\"*') {",
    '      if ($env:REVIVE_DEBUG) { [Console]::Error.WriteLine("revive: nothing remembered on $env:HC_TERMINAL_ID") }',
    "    } elseif ($env:REVIVE_SHELL -and $env:REVIVE_SHELL -eq [string](Get-CimInstance Win32_Process -Filter \"ProcessId=$PID\" -Property ParentProcessId -ErrorAction Ignore).ParentProcessId) {",
    "      if ($env:REVIVE_DEBUG) { [Console]::Error.WriteLine(\"revive: a shell started inside the terminal's own shell\") }",
    "    } else {",
    "      $__revive_enc = [Console]::OutputEncoding",
    "      try {",
    "        [Console]::OutputEncoding = [Text.Encoding]::UTF8",
    `        if ($env:REVIVE_DEBUG) { $__revive = (& node ${q} check --shell $PID --dialect pwsh) -join "\`n" }`,
    `        else { $__revive = (& node ${q} check --shell $PID --dialect pwsh 2>$null) -join "\`n" }`,
    "      } finally { [Console]::OutputEncoding = $__revive_enc }",
    "      if ($__revive) { Invoke-Expression $__revive }",
    "    }",
    "  } catch {",
    '    if ($env:REVIVE_DEBUG) { [Console]::Error.WriteLine("revive: $_") }',
    "  }",
    "  Remove-Variable -Name __revive, __revive_j, __revive_hc, __revive_enc -ErrorAction Ignore",
    "  # Shells started from this one know it ran here.",
    "  $env:REVIVE_SHELL = [string]$PID",
    "}",
    END,
  ].join("\n");
}

/**
 * Adds (or, with remove, takes out) Revive's SessionStart/SessionEnd hooks, in
 * Claude Code's format, which Codex and Factory Droid share. An event that already has exactly Revive's hook is left as it is, wherever
 * it sits: other tools write this file too, and moving Revive's group back to
 * the end each time would rewrite it for nothing. `timeouts` sets an event's
 * timeout (Codex clamps SessionEnd to 3 seconds and warns about more).
 */
export function withHooks(settings, { remove = false, matcher = false, timeouts = {}, agent = null, portable = false } = {}) {
  const out = structuredClone(settings ?? {});
  out.hooks ??= {};
  const command = hookCommand(agent, portable);
  for (const event of EVENTS) {
    const timeout = timeouts[event] ?? 10;
    const ours = (out.hooks[event] ?? []).flatMap((g) => (g.hooks ?? []).filter(isOurs));
    if (!remove && ours.length === 1 && ours[0].command === command && ours[0].timeout === timeout) continue;
    const groups = (out.hooks[event] ?? [])
      .map((g) => ({ ...g, hooks: (g.hooks ?? []).filter((h) => !isOurs(h)) }))
      .filter((g) => g.hooks.length);
    if (!remove) groups.push({ ...(matcher ? { matcher: "" } : {}), hooks: [{ type: "command", command, timeout }] });
    if (groups.length) out.hooks[event] = groups;
    else delete out.hooks[event];
  }
  if (!Object.keys(out.hooks).length) delete out.hooks;
  return out;
}

export const hasHooks = (settings) => EVENTS.every((e) => (settings?.hooks?.[e] ?? []).some((g) => (g.hooks ?? []).some(isOurs)));

/**
 * Droid's standalone `~/.factory/hooks.json` holds the same event map with no
 * `hooks` wrapper around it.
 */
const unwrapped = (fn) => (doc, opts) => fn({ hooks: doc ?? {} }, opts).hooks ?? {};
const withBareHooks = unwrapped(withHooks);
const hasBareHooks = (doc) => hasHooks({ hooks: doc ?? {} });

/**
 * Cursor's `~/.cursor/hooks.json`: `{ version: 1, hooks: { sessionStart:
 * [{ command }], … } }`, camelCase events and no groups. No timeout is
 * written: the docs don't give its unit. Revive's entry, already right, is
 * left where it is.
 */
const CURSOR_EVENTS = ["sessionStart", "sessionEnd"];
export function withCursorHooks(doc, { remove = false } = {}) {
  const out = structuredClone(doc ?? {});
  if (!remove) out.version ??= 1;
  out.hooks ??= {};
  const command = hookCommand("cursor");
  for (const event of CURSOR_EVENTS) {
    const ours = (out.hooks[event] ?? []).filter(isOurs);
    if (!remove && ours.length === 1 && ours[0].command === command) continue;
    const list = (out.hooks[event] ?? []).filter((h) => !isOurs(h));
    if (!remove) list.push({ command });
    if (list.length) out.hooks[event] = list;
    else delete out.hooks[event];
  }
  if (!Object.keys(out.hooks).length) delete out.hooks;
  return out;
}
export const hasCursorHooks = (doc) => CURSOR_EVENTS.every((e) => (doc?.hooks?.[e] ?? []).some(isOurs));

/**
 * Copilot CLI's hooks file, `~/.copilot/hooks/herdr-revive.json`, Revive's
 * own (Copilot reads every `*.json` in that folder): `{ version: 1, hooks:
 * { SessionStart: [{ type: "command", bash, timeoutSec }], … } }`, flat
 * entries with no groups. Entries of anyone else's in it are kept.
 *
 * On Windows Copilot runs an entry's `powershell` command and ignores its
 * `bash` one (checked with copilot 1.0.112), so there the entry has both. The
 * engine is a single-quoted PowerShell word (`psQuote`), so a `$` or a
 * backtick in its path is never expanded.
 */
const isOursCopilot = (h) => [h?.bash, h?.powershell, h?.command].some((command) => isOurs({ command }));
const copilotPowershell = () => `node ${psQuote(ENGINE)} hook --agent copilot`;
export function withCopilotHooks(doc, { remove = false, win = IS_WIN } = {}) {
  const out = structuredClone(doc ?? {});
  if (!remove) out.version ??= 1;
  out.hooks ??= {};
  const bash = hookCommand("copilot");
  const powershell = win ? copilotPowershell() : undefined;
  for (const event of EVENTS) {
    const ours = (out.hooks[event] ?? []).filter(isOursCopilot);
    if (!remove && ours.length === 1 && ours[0].bash === bash && ours[0].powershell === powershell && ours[0].timeoutSec === 10) continue;
    const list = (out.hooks[event] ?? []).filter((h) => !isOursCopilot(h));
    if (!remove) list.push({ type: "command", bash, ...(powershell ? { powershell } : {}), timeoutSec: 10 });
    if (list.length) out.hooks[event] = list;
    else delete out.hooks[event];
  }
  if (!Object.keys(out.hooks).length) delete out.hooks;
  return out;
}
export const hasCopilotHooks = (doc) => EVENTS.every((e) => (doc?.hooks?.[e] ?? []).some(isOursCopilot));

/** `kind`: the shell whose file it is; PowerShell's get pwshBlock, zsh's and bash's shellBlock. */
export function withShellBlock(text, { remove = false, kind = null } = {}) {
  if (remove && !text.includes(BEGIN)) return text;
  const pattern = new RegExp(`\\r?\\n?${BEGIN}[\\s\\S]*?${END}\\r?\\n?`, "g");
  const stripped = text.replace(pattern, "\n").replace(/\n{3,}$/, "\n\n");
  if (remove) return stripped;
  if (!PS_KINDS.includes(kind)) return `${stripped.replace(/\n*$/, "")}\n\n${shellBlock()}\n`;
  const body = stripped.replace(/[\r\n]*$/, "");
  return `${body}${body ? "\n\n" : ""}${pwshBlock()}\n`;
}

function readJson(path) {
  if (!existsSync(path)) return {};
  const text = readFileSync(path, "utf8");
  if (!text.trim()) return {};
  try { return JSON.parse(text); }
  catch { throw new InvalidJson(path); }
}

class InvalidJson extends Error {
  constructor(path) {
    super(`${path} is not valid JSON; fix it first, Revive won't overwrite it.`);
    this.path = path;
  }
}

const tilde = (path) => (path.startsWith(`${homedir()}/`) || (IS_WIN && path.toLowerCase().startsWith(`${homedir().toLowerCase()}\\`)) ? `~${path.slice(homedir().length)}` : path);

/**
 * Writes a file atomically. The first time Revive changes it, the person's
 * original is copied to `<file>.revive-backup`; later changes keep that copy.
 * A symlinked file (a dotfiles repository) is written where the link points,
 * so the link stays; the file keeps its permissions.
 */
function save(path, text) {
  let target = path;
  try { target = realpathSync(path); } catch { /* not there yet */ }
  mkdirSync(dirname(target), { recursive: true });
  let mode = null;
  if (existsSync(target)) {
    if (readFileSync(target, "utf8") === text) return false;
    mode = statSync(target).mode & 0o7777;
    const backup = `${path}.revive-backup`;
    if (!existsSync(backup)) copyFileSync(target, backup);
  }
  const tmp = `${target}.revive-${process.pid}.tmp`;
  // Created with the file's own permissions, not the umask's: a 0600 settings
  // file (API keys under `env`) must not sit world-readable until the chmod.
  // The chmod stays for bits the umask takes away (0664 under umask 077).
  rmSync(tmp, { force: true });
  writeFileSync(tmp, text, mode !== null ? { mode } : undefined);
  if (mode !== null) chmodSync(tmp, mode);
  renameSync(tmp, target);
  return true;
}

const readText = (path) => (existsSync(path) ? readFileSync(path, "utf8") : "");

function shells(args) {
  const picked = Object.keys(RC).filter((s) => args.includes(`--${s}`));
  if (picked.length) return picked;
  // Windows: the PowerShell herdr-core starts, pwsh 7 when it is installed.
  if (IS_WIN) return [psProfile("pwsh") ? "pwsh" : "powershell"];
  const login = (process.env.SHELL ?? "").split("/").pop();
  return [RC[login] ? login : "zsh"];
}

/**
 * A file's byte-order mark stays as it was. Windows PowerShell 5.1 reads a
 * profile without one as the ANSI code page, so a new 5.1 profile whose block
 * names a non-ASCII path (a user folder like C:\\Users\\joão) gets one. pwsh 7
 * reads UTF-8 either way.
 */
const withBom = (kind, text, { existed, had }) => (had || (kind === "powershell" && !existed && /[^\x00-\x7f]/.test(text)) ? `\ufeff${text}` : text);

/**
 * Whether PowerShell will run a profile at all: with the Restricted or AllSigned
 * execution policy it won't, and Revive's block never runs. Said, not changed:
 * the policy is the person's (or their administrator's) choice.
 */
function executionPolicy() {
  if (!IS_WIN) return null;
  try { return runPsSync("Get-ExecutionPolicy").trim() || null; } catch { return null; }
}
const policyBlocks = (policy) => policy === "Restricted" || policy === "AllSigned";
const policyNote = (policy) => `PowerShell's execution policy is ${policy}, so it won't run your profile and Revive can't resume anything. To allow it: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`;

/** Codex clamps a SessionEnd hook's timeout to 3 seconds and warns at every start about more. */
const CODEX_HOOKS = { matcher: true, timeouts: { SessionEnd: 3 } };

/**
 * Where each agent's hooks are installed. `files` lists every file they may
 * be in; `target` is the one the agent reads now (Droid reads settings.json's
 * `hooks` only while there is no hooks.json). An agent is installed only when
 * `present`: Claude Code's and Codex's folder is there, Droid's, Cursor's and
 * Copilot's CLI is (not just their folder: Cursor's IDE makes ~/.cursor and
 * reads its hooks.json too). `flag` (`--no-…`) skips it. `own`: the file is
 * Revive's alone, removed whole on uninstall.
 */
const HOOK_TARGETS = {
  // Like Codex: only when Claude Code is there, so a Codex-only setup gets no ~/.claude.
  claude: { dir: claudeDir, present: () => existsSync(claudeDir()), files: () => [claudeSettings()], edit: (d, o) => withHooks(d, { ...o, portable: true }), has: hasHooks },
  codex: {
    dir: codexDir,
    present: () => existsSync(codexDir()),
    flag: "--no-codex",
    trust: "Codex asks to trust new hooks the next time it starts.",
    files: () => [codexHooks()],
    edit: (d, o) => withHooks(d, { ...o, ...CODEX_HOOKS }),
    has: hasHooks,
  },
  droid: {
    dir: factoryDir,
    present: () => existsSync(factoryDir()) && hasCli("droid"),
    flag: "--no-droid",
    files: () => [join(factoryDir(), "hooks.json"), join(factoryDir(), "settings.json")],
    target: (files) => (existsSync(files[0]) ? files[0] : files[1]),
    edit: (d, o, file) => (file.endsWith("hooks.json") ? withBareHooks(d, { ...o, agent: "droid" }) : withHooks(d, { ...o, agent: "droid" })),
    has: (d, file) => (file.endsWith("hooks.json") ? hasBareHooks(d) : hasHooks(d)),
  },
  cursor: {
    dir: cursorDir,
    present: () => hasCli("cursor-agent") || existsSync(join(homedir(), ".local", "share", "cursor-agent")),
    flag: "--no-cursor",
    files: () => [join(cursorDir(), "hooks.json")],
    edit: (d, o) => withCursorHooks(d, o),
    has: hasCursorHooks,
  },
  // The Copilot app and VS Code make ~/.copilot too: the CLI must be there.
  // Homebrew's and npm's folders count, for an app with a short PATH.
  copilot: {
    dir: copilotDir,
    present: () => existsSync(copilotDir()) && hasCli("copilot", ["/opt/homebrew/bin", "/usr/local/bin"]),
    flag: "--no-copilot",
    own: true,
    files: () => [copilotHooks()],
    edit: (d, o) => withCopilotHooks(d, o),
    has: hasCopilotHooks,
  },
};
const targetOf = (h) => (h.target ?? ((files) => files[0]))(h.files());

/**
 * Writes Revive's hooks into one JSON file. A file whose hooks are already
 * right is not written, even when another tool formatted it differently
 * (sorted its keys, say): only a real change rewrites it.
 */
function saveHooks(path, edit) {
  const before = readJson(path);
  const after = edit(before);
  if (existsSync(path) && JSON.stringify(after) === JSON.stringify(before)) return false;
  return save(path, JSON.stringify(after, null, 2) + "\n");
}

async function install(args, remove = false) {
  const changed = [];
  const notes = [];
  for (const [key, h] of Object.entries(HOOK_TARGETS)) {
    // Uninstall still cleans an agent whose CLI is gone, as long as its folder is there.
    if ((h.flag && args.includes(h.flag)) || !(remove ? existsSync(h.dir()) : h.present())) continue;
    const target = targetOf(h);
    try {
      for (const file of h.files()) {
        // Install into the file the agent reads; take Revive out of every other.
        // A file without Revive in it is left as it is, formatting and all.
        const off = remove || file !== target;
        if (off && !readText(file).includes("revive.mjs")) continue;
        // A file of Revive's own goes once nothing is left in it.
        if (off && h.own && !h.edit(readJson(file), { remove: true }, file).hooks) {
          rmSync(file);
          rmSync(`${file}.revive-backup`, { force: true });
          changed.push(file);
          continue;
        }
        if (saveHooks(file, (doc) => h.edit(doc, { remove: off }, file))) {
          changed.push(file);
          if (!off && h.trust) notes.push(h.trust);
        }
      }
    } catch (err) {
      // One unreadable file skips that agent only; the others and the shell go on.
      if (!(err instanceof InvalidJson)) throw err;
      notes.push(`Skipped ${AGENTS[key].name}: ${tilde(err.path)} is not valid JSON; fix it and run ${remove ? "uninstall" : "install"} again.`);
    }
  }
  // A file of someone else's at pi's or omp's path: say so, and still install the rest.
  const warnings = [];
  for (const key of EXTENSION_AGENTS) {
    if (args.includes(EXTENSIONS[key].flag) || !existsSync(EXTENSIONS[key].dir())) continue;
    try {
      if (linkExtension(key, remove)) {
        changed.push(extensionPath(key));
        // omp loads extensions only at start (its docs: modules are never re-evaluated).
        if (!remove) notes.push(`${AGENTS[key].name} loads the extension the next time it starts${key === "pi" ? " (or at /reload)" : ""}.`);
      }
    } catch (err) { warnings.push(err.message); }
  }
  if (!args.includes("--no-shell")) {
    const kindOf = (rc) => Object.keys(RC).find((k) => RC[k]() === rc) ?? null;
    for (const rc of remove ? ALL_RC() : shells(args).map((s) => RC[s]()).filter(Boolean)) {
      if (remove && !existsSync(rc)) continue;
      const kind = kindOf(rc);
      const before = readText(rc);
      const next = withShellBlock(before.replace(/^﻿/, ""), { remove, kind });
      if (save(rc, withBom(kind, next, { existed: existsSync(rc), had: before.startsWith("﻿") }))) changed.push(rc);
    }
    if (IS_WIN && !remove) {
      const policy = executionPolicy();
      if (policyBlocks(policy)) warnings.push(policyNote(policy));
    }
    // An earlier version put bash's block into another file (a login file,
    // on Linux): only one bash file keeps it.
    if (!remove && !IS_WIN && shells(args).includes("bash")) {
      const keep = RC.bash();
      for (const rc of [...BASH_LOGIN.map((f) => join(homedir(), f)), join(homedir(), ".bashrc")]) {
        if (rc === keep || !existsSync(rc) || !readText(rc).includes(BEGIN)) continue;
        if (save(rc, withShellBlock(readText(rc), { remove: true }))) changed.push(rc);
      }
    }
  }
  // Last, the sessions already running that `adopt` could remember: said,
  // never done. Install also runs on every update and from the dialog, and
  // writes nothing but its own files.
  if (!remove) {
    try {
      const n = await unremembered();
      if (n) notes.push(unrememberedNote(n));
    } catch (err) {
      warnings.push(`Couldn't count the running sessions Revive doesn't remember: ${hcFailure(err)}. revive.mjs adopt --dry-run lists them.`);
    }
  }
  process.stdout.write(changed.length ? `${remove ? "Removed from" : "Updated"}:\n${changed.map((p) => `  ${p}`).join("\n")}\n` : "Nothing to change.\n");
  // On stdout, beside what did change: the dialog shows that output as its note.
  for (const line of notes) process.stdout.write(`${line}\n`);
  for (const line of warnings) process.stderr.write(`${line}\n`);
}

/**
 * How many running sessions `adopt` would remember, or null when hc isn't
 * asked: only while the terminal's herdr-core answers, since an `hc` that
 * finds no core starts one.
 */
async function unremembered() {
  if (!(await coreUp())) return null;
  return (await adoptRunning({ dry: true })).filter((r) => r.fields).length;
}

const unrememberedNote = (n) => `${n} running Claude Code session${n === 1 ? " isn't" : "s aren't"} remembered yet: revive.mjs adopt --dry-run lists ${n === 1 ? "it" : "them"}, and revive.mjs adopt remembers ${n === 1 ? "it" : "them"}.`;

/** Why an `hc` call failed, in one line. */
const hcFailure = (err) => (err?.code === "ENOENT" ? `${HC} isn't on PATH` : String(err?.stderr || err?.message || err).trim().split("\n")[0]);

/**
 * Links pi's or omp's extension to the mod's, or, with remove, takes out that
 * link. An extension already there (this link, or a copy something else
 * manages) is left alone, and so is anything else by that name: it isn't
 * Revive's to replace.
 */
function linkExtension(key, remove, win = IS_WIN) {
  const target = extensionPath(key);
  const source = EXTENSIONS[key].source;
  const real = (p) => { try { return realpathSync(p); } catch { return null; } };
  if (remove) {
    if (win && readText(target) === extensionStub(key)) { rmSync(target); return true; }
    if (!lstatSync(target, { throwIfNoEntry: false })?.isSymbolicLink() || real(target) !== real(source)) return false;
    rmSync(target);
    return true;
  }
  if (isExtension(key, target)) return false;
  if (lstatSync(target, { throwIfNoEntry: false })) throw new Error(`${target} is not Revive's ${AGENTS[key].name} extension; Revive won't replace it.`);
  mkdirSync(dirname(target), { recursive: true });
  // Windows makes links only for administrators (or in Developer Mode): there,
  // a one-line file that loads the mod's extension stands in for the link.
  if (win) writeFileSync(target, extensionStub(key));
  else symlinkSync(source, target);
  return true;
}

/**
 * The stand-in for the link on Windows: its first line holds the marker, so it
 * counts as Revive's extension, and it loads the mod's own file, whose
 * `import.meta.url` still finds the engine next to it.
 */
const extensionStub = (key) => `// ${EXTENSIONS[key].marker} (Windows: a file that loads it, since making a link needs administrator rights)\nexport { default } from ${JSON.stringify(pathToFileURL(EXTENSIONS[key].source).href)};\n`;

export function doctorReport() {
  const safe = (fn) => { try { return fn(); } catch { return false; } };
  // Per agent: true or false, or null for an agent that isn't installed.
  const hooks = Object.fromEntries(Object.entries(HOOK_TARGETS).map(([key, h]) => {
    if (!h.present()) return [key, null];
    const file = targetOf(h);
    return [key, safe(() => h.has(readJson(file), file))];
  }));
  const report = {
    engine: ENGINE,
    ...hooks,
    ...Object.fromEntries(EXTENSION_AGENTS.map((key) => [key, existsSync(EXTENSIONS[key].dir()) ? safe(() => isExtension(key, extensionPath(key))) : null])),
    shell: Object.fromEntries(Object.entries(RC).map(([s, rc]) => [s, safe(() => { const f = rc(); return Boolean(f) && readText(f).includes(BEGIN); })])),
  };
  // Windows: whether PowerShell runs a profile at all (see executionPolicy).
  if (IS_WIN) report.executionPolicy = executionPolicy();
  return report;
}

// ── main ────────────────────────────────────────────────────────────────────

const COMMANDS = {
  hook: { run: (a) => hook(a), quiet: true },
  settle: { run: (a) => settle(a), quiet: true },
  check: { run: check, quiet: true },
  failed: { run: failed, quiet: true },
  list: { run: list },
  resume: { run: resume },
  auto: { run: auto },
  restore: { run: restore },
  adopt: { run: adopt },
  install: { run: (a) => install(a) },
  uninstall: { run: (a) => install(a, true) },
  doctor: { run: doctor },
};

async function main() {
  const [name, ...args] = process.argv.slice(2);
  const cmd = COMMANDS[name];
  if (!cmd) {
    process.stderr.write(`usage: revive.mjs ${Object.keys(COMMANDS).join("|")}\n`);
    process.exit(2);
  }
  try {
    await cmd.run(args);
  } catch (err) {
    if (cmd.quiet) {
      // Quiet commands never fail an agent or a shell; REVIVE_DEBUG=1 still says why they stopped.
      if (process.env.REVIVE_DEBUG) process.stderr.write(`revive ${name}: ${err?.stack ?? err}\n`);
      return;
    }
    process.stderr.write(`${err?.message ?? err}\n`);
    process.exit(1);
  }
}

// Run as a program, not when the tests import it (a linked mod folder resolves through the link).
const real = (p) => { try { return realpathSync(p); } catch { return p; } };
if (process.argv[1] && real(ENGINE) === real(process.argv[1])) await main();
