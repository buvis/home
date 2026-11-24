// Reading the diff, the cache and the background job, against this machine.
//
// ~/.herdr/walkthrough/
//   entries/<key>.json     a finished walkthrough, named by everything that decides it
//   pointers/<place>.json  the one shown last for a repository and source
//   jobs/<place>/          a generation in progress (run.sh, prompt, answer)
//   turns/<repo>/<turn>/   an agent's turn, written by hooks/turn.sh or the recorder (see lib/turns.js)
//   recorders/<repo>/      which open walkthrough records a repository's turns without hooks
//   failed/<job>/          a failed generation's files, kept for a day to see why
//   read/<repo>.json       the hunks read in a repository, by content
//   preferences.md         optional: the reader's own wishes, added to every prompt

import { exec, home, appHome, readTextFile, writeTextFile, notify } from "herdr";
import { loadSections, sourceKey, describe, git, worthReading, ghError, turnsKey, snapshotTree } from "./lib/sources.js";
import { buildDigest } from "./lib/digest.js";
import { buildPrompt } from "./lib/prompt.js";
import { schemaFor, normalize, VERSION } from "./lib/walkthrough.js";
import { cacheKey, codeKey, placeKey, deadline, MAX_PROMPT_CHARS } from "./lib/cache.js";
import { longHash } from "./lib/hash.js";
import { mergeRead } from "./lib/read.js";
import { jobScript, readOutcome, isRunCommand, backendOf, modelOf } from "./lib/job.js";
import { parseListing, resolveEnds, LISTING, RECORDER_LOCK } from "./lib/turns.js";
import { taskKey, taskCacheKey, parseTranscript, projectSlug, jsonPath, TRANSCRIPTS } from "./lib/task.js";
import { parseSessionHeads, parsePiSession, parseCodexSession, parseOpencode, mergePrompts, inRepo, SESSION_HEADS } from "./lib/agents.js";

const MAX_ENTRIES = 200;
export const dataDir = () => `${home()}/.herdr/walkthrough`;
const entryPath = (key) => `${dataDir()}/entries/${key}.json`;
const pointerPath = (place) => `${dataDir()}/pointers/${place}.json`;
const jobDir = (place) => `${dataDir()}/jobs/${place}`;
const readPath = (top) => `${dataDir()}/read/${longHash(top)}.json`;

/** A file of several MB (a job's out.json, a session): readTextFile falls short on those, so cat first. */
async function readBig(path) {
  const r = await exec("cat", [path]).catch(() => null);
  if (r?.code === 0 && r.stdout !== "") return r.stdout;
  return readTextFile(path).catch(() => null);
}

async function readJson(path) {
  try {
    const text = await readTextFile(path);
    return text ? JSON.parse(text) : null;
  } catch { return null; }
}

/** Replaces a file whatever it holds now (writeTextFile wants the old text). */
async function write(path, text) {
  const old = await readTextFile(path).catch(() => null);
  await writeTextFile(path, text, old);
}

export async function ensureDirs() {
  const d = dataDir();
  await exec("mkdir", ["-p", `${d}/entries`, `${d}/pointers`, `${d}/jobs`, `${d}/read`]);
}

/**
 * Puts text on the system clipboard. `exec` takes no input, so the text goes
 * through a file: pbcopy on macOS, else wl-copy or xclip.
 */
export async function copyText(text) {
  const path = `${dataDir()}/clipboard.md`;
  await write(path, text);
  const r = await exec("sh", ["-c", COPY, "sh", path]);
  if (r.code !== 0) throw new Error((r.stderr || "No clipboard program found (pbcopy, wl-copy or xclip).").trim());
}

// The text is UTF-8, said so to each program: started from an app, pbcopy sees no UTF-8 locale
// and reads the bytes as Mac Roman, so "ş" or "日" land on the clipboard garbled.
const COPY = 'if command -v pbcopy >/dev/null; then LC_ALL=en_US.UTF-8 pbcopy < "$1"; elif command -v wl-copy >/dev/null; then wl-copy --type "text/plain;charset=utf-8" < "$1"; elif command -v xclip >/dev/null; then xclip -selection clipboard -target UTF8_STRING < "$1"; else echo "No clipboard program found (pbcopy, wl-copy or xclip)." >&2; exit 1; fi';

// GitHub refuses a comment longer than this.
export const MAX_COMMENT_CHARS = 65536;

/**
 * Posts text as a comment on a pull request, through a file like the clipboard.
 * @returns {Promise<string>} the comment's URL, as gh prints it
 */
export async function postComment(top, number, text) {
  if (text.length > MAX_COMMENT_CHARS) throw new Error(`It's too long for a GitHub comment (${text.length.toLocaleString("en")} characters; the limit is ${MAX_COMMENT_CHARS.toLocaleString("en")}).`);
  const path = `${dataDir()}/pr-comment.md`;
  await write(path, text);
  let r;
  try { r = await exec("gh", ["pr", "comment", String(number), "--body-file", path], { cwd: top }); } catch { throw new Error("The GitHub CLI (gh) isn't installed."); }
  if (r.code !== 0) throw new Error(ghError(r.stderr || r.stdout));
  return (r.stdout ?? "").trim().split("\n").pop() ?? "";
}

/** The program a backend's runs start: pi through the PATH Herdr sees, else fnm's default alias. */
export async function programOf(backend) {
  // local: the setup-token wrapper, not a bare `claude` (Herdr's exec has no long-lived token, and the OAuth login expires).
  if (backendOf(backend).key !== "pi") return `${appHome()}/bin/run-claude-pat`;
  const r = await exec("sh", ["-c", 'command -v pi 2>/dev/null || printf %s "$HOME/.local/share/fnm/aliases/default/bin/pi"']).catch(() => null);
  return (r?.stdout ?? "").trim().split("\n")[0] || "pi";
}

/** Whether a backend's program can be started: its version, or null. */
export async function backendVersion(backend) {
  try {
    const r = await exec(await programOf(backend), ["--version"]);
    return r.code === 0 ? r.stdout.trim() : null;
  } catch { return null; }
}

/**
 * The diff of a source as it is now, parsed, with what the model would read.
 * @returns {Promise<any>}
 */
export async function readDiff(repo, source) {
  const { sections, unread } = await loadSections(exec, repo.top, source);
  const digest = buildDigest(sections);
  for (const u of unread) digest.files.push({ path: u.path, oldPath: null, status: "added", binary: false, scope: "unread", hunks: [], generated: false, unread: u.why });
  return { ...digest, unread, sk: sourceKey(source), what: describe(source, repo) };
}

/** The key the walkthrough of this diff would have, in this model and language, under these preferences, matched against this task. */
export const keyFor = (repo, diff, model, language, preferences = "", task = null) =>
  cacheKey({ top: repo.top, source: diff.sk, model, language, preferences, files: diff.files, task: taskCacheKey(task) });

// Sessions read at once: enough to overlap the waits, few enough not to flood a busy machine.
const READ_AT_ONCE = 4;

/** `fn` over `items`, at most `limit` at a time, in order. */
async function mapLimit(items, limit, fn) {
  const out = new Array(items.length);
  let next = 0;
  const worker = async () => { while (next < items.length) { const i = next++; out[i] = await fn(items[i]); } };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return out;
}

// opencode's database is undocumented; a schema it no longer matches is said once, not silently read as no prompts.
let opencodeWarned = false;

/**
 * The sessions of agents without hooks (pi, codex, opencode) working in a
 * repository: what was typed into them since `since` (ms), oldest first, and
 * when any of them last wrote (`active`, ms; 0 when none did). Only session
 * files written since `since` are opened, and only those whose first line puts
 * them in this repository are read whole.
 * @returns {Promise<{ prompts: { at: number, text: string, session: string|null, agent: string }[], active: number }>}
 */
export async function agentSessions(top, since) {
  const minutes = String(Math.min(43_200, Math.max(1, Math.ceil((Date.now() - since) / 60_000) + 1)));
  const roots = { pi: `${home()}/.pi/agent/sessions`, codex: `${home()}/.codex/sessions` };
  const script = `${appHome()}/mods/walkthrough/lib/opencode-prompts.py`;
  const [heads, oc] = await Promise.all([
    exec("sh", ["-c", SESSION_HEADS, minutes, roots.pi, roots.codex]).catch(() => null),
    exec("python3", [script, top, String(Math.floor(since))]).catch(() => null),
  ]);
  const mine = parseSessionHeads(heads?.stdout ?? "").filter((h) => inRepo(h.cwd, top))
    .map((h) => ({ ...h, agent: h.path.startsWith(`${roots.pi}/`) ? "pi" : "codex" }));
  const read = await mapLimit(mine, READ_AT_ONCE, async (h) => {
    const text = (await readBig(h.path)) ?? "";
    return h.agent === "pi" ? parsePiSession(text, { top, since, session: `pi:${h.path}` }) : parseCodexSession(text, { top, since, session: `codex:${h.path}` });
  });
  const opencode = parseOpencode(oc?.stdout ?? "", since);
  if (opencode.error && !opencodeWarned) {
    opencodeWarned = true;
    notify({ title: "Walkthrough", body: `Couldn't read opencode's sessions (its database may have changed): ${opencode.error}`, level: "warning" });
  }
  const active = Math.max(0, opencode.active, ...mine.map((h) => h.mtime));
  return { prompts: mergePrompts([...read, opencode.prompts]), active };
}

/**
 * What people typed into the agents working in a repository since `since`
 * (ms), oldest first: the task of a change made without the hooks that record
 * turns. Read from Claude Code's transcripts (its folder names the project by
 * its path; a session started in a subfolder counts too), and from pi, codex
 * and opencode sessions.
 */
export async function transcriptMessages(top, since) {
  // Claude Code shortens very long folder names; the prefix finds them, and each line's cwd decides.
  const prefix = projectSlug(top).slice(0, 120);
  const [claude, others] = await Promise.all([
    exec("sh", ["-c", TRANSCRIPTS, prefix, String(Math.floor(since / 1000)), jsonPath(top)]).catch(() => null),
    agentSessions(top, since).catch(() => ({ prompts: [] })),
  ]);
  return mergePrompts([parseTranscript(claude?.stdout ?? "", { top, since }), others.prompts]);
}

/** The reader's own wishes for every walkthrough, or "". */
export const readPreferences = async () => (await readTextFile(`${dataDir()}/preferences.md`).catch(() => null)) ?? "";

/**
 * Whether paths a folder watch reported can change a diff: anything but
 * node_modules, git's own bookkeeping (its index, HEAD and refs do count) and
 * files git ignores. A build or an install would otherwise re-read the diff
 * every second.
 */
export async function matters(top, paths, gitDir) {
  const candidates = worthReading(top, paths, gitDir);
  if (candidates === true) return true;
  if (!candidates.length) return false;
  const sample = candidates.slice(0, 200);
  const ignored = await git(exec, top, ["check-ignore", "--", ...sample]);
  // 1: none of them is ignored.
  if (ignored.code === 1) return true;
  if (!ignored.ok) return true;
  const out = new Set(ignored.out.split("\n").filter(Boolean));
  return sample.some((p) => !out.has(p)) || candidates.length > sample.length;
}

/**
 * What to show for a diff: the walkthrough written for exactly it, else the
 * last one shown here (older code, or another model or language).
 * @returns {Promise<{ entry: any, exact: boolean } | null>}
 */
export async function findShown(repo, diff, key) {
  const exact = await readJson(entryPath(key));
  const place = placeKey(repo.top, diff.sk);
  if (exact?.version === VERSION) {
    await touch(entryPath(key));
    const pointer = await readJson(pointerPath(place));
    // Showing it makes it the last one shown, so a regeneration builds on what the reader sees.
    if (pointer?.key !== key) await write(pointerPath(place), JSON.stringify({ key, top: repo.top, source: diff.sk })).catch(() => undefined);
    return { entry: exact, exact: true };
  }
  const pointer = await readJson(pointerPath(place));
  const last = pointer?.key ? await readJson(entryPath(pointer.key)) : null;
  if (last?.version !== VERSION) return null;
  await touch(entryPath(pointer.key));
  return { entry: last, exact: false };
}

// Eviction keeps the newest files, so showing an entry marks it new: the one a reader keeps
// coming back to outlives two hundred they looked at once. Once per entry per session is enough.
const touched = new Set();
async function touch(path) {
  if (touched.has(path)) return;
  touched.add(path);
  await exec("touch", [path]).catch(() => undefined);
}

/** Whether a walkthrough with exactly this key is stored. */
export const hasEntry = async (key) => (await readJson(entryPath(key)))?.version === VERSION;

/** Where the installed hook script is, for the settings snippet: the mod's own folder. */
// Under the home folder it is written from $HOME, as the README gives it: shorter, and the hook's shell expands it.
export const hookScript = () => {
  const path = `${appHome()}/mods/walkthrough/hooks/turn.sh`;
  return path.startsWith(`${home()}/`) ? `$HOME${path.slice(home().length)}` : path;
};

/** A repository's turns folder, named as hooks/turn.sh names it. Made here so it can be watched before the first turn. */
export async function turnsFolder(top) {
  const key = await turnsKey(exec, top);
  if (!key) return null;
  const dir = `${dataDir()}/turns/${key}`;
  await exec("mkdir", ["-p", dir]).catch(() => undefined);
  return dir;
}

/**
 * A turn recorded by the walkthrough itself, for an agent with no hooks: the
 * working tree when its prompt was seen, in the format hooks/turn.sh writes
 * (id `<startedSeconds>-<random>`; `recorder=1` in start.meta tells it apart).
 */
export async function startTurn(folder, top, { prompt, session = null, started = Date.now() } = {}) {
  if (!folder) return null;
  const id = `${Math.floor(started / 1000)}-${Math.floor(Math.random() * 90000 + 10000)}`;
  const dir = `${folder}/${id}`;
  await exec("mkdir", ["-p", `${dir}/objects`]).catch(() => undefined);
  let snap;
  try { snap = await snapshotTree(exec, top, { index: `${dir}/index`, objects: `${dir}/objects` }); }
  catch { await exec("rm", ["-rf", dir]).catch(() => undefined); return null; }
  await write(`${dir}/start.json`, JSON.stringify({ prompt, session_id: session, cwd: top, hook_event_name: "UserPromptSubmit" }));
  await write(`${dir}/start.big`, snap.big.map((p) => `${p}\n`).join(""));
  // Written last: a turn is listed once its start.meta names a tree.
  await write(`${dir}/start.meta`, `tree=${snap.tree}\nstarted=${Math.floor(started / 1000)}\nsession=${session ?? ""}\nrecorder=1\n`);
  return { id, dir, started, session };
}

/**
 * Ends a turn the recorder started: the working tree now. `interrupted`: its
 * end wasn't seen (the next prompt came while it worked, or the walkthrough
 * was closed in the middle), as closeTurn marks one.
 */
export async function endTurn(top, turn, { interrupted = false } = {}) {
  if (!turn?.dir) return;
  const { tree, big } = await snapshotTree(exec, top, { index: `${turn.dir}/now.index`, objects: `${turn.dir}/objects` });
  await write(`${turn.dir}/end.big`, big.map((p) => `${p}\n`).join(""));
  await write(`${turn.dir}/end.meta`, `tree=${tree}\nended=${Math.floor(Date.now() / 1000)}\n${interrupted ? "interrupted=1\n" : ""}`);
}

/**
 * Whether this window (`owner`) records a repository's turns: one walkthrough
 * per repository does, so two open on it don't record each prompt twice. The
 * claim is renewed on every look and lapses a minute after its window stops
 * renewing it (closed, or gone with Herdr).
 */
export async function claimRecorder(folder, owner) {
  if (!folder) return false;
  const lock = `${dataDir()}/recorders/${longHash(folder)}`;
  await exec("mkdir", ["-p", `${dataDir()}/recorders`]).catch(() => undefined);
  const r = await exec("sh", ["-c", RECORDER_LOCK, lock, owner]).catch(() => null);
  return (r?.stdout ?? "").trim() === "ok";
}

/** A repository's turns, newest first, each with where it ended (lib/turns.js; `ends`: resolveEnds' options). */
export async function listTurns(folder, ends = {}) {
  if (!folder) return [];
  const r = await exec("sh", ["-c", LISTING, folder]).catch(() => null);
  return resolveEnds(parseListing(r?.stdout ?? "", folder), ends);
}

/**
 * Ends a turn no Stop hook ended and whose agent has gone quiet (it was quit,
 * or stopped and left): its end is the working tree now, marked interrupted,
 * so it stops following later edits. A Stop hook arriving after all ends it again.
 */
export async function closeTurn(top, turn) {
  const { tree, big } = await snapshotTree(exec, top, { index: `${turn.dir}/now.index`, objects: `${turn.dir}/objects` });
  await write(`${turn.dir}/end.big`, big.map((p) => `${p}\n`).join(""));
  await write(`${turn.dir}/end.meta`, `tree=${tree}\nended=${Math.floor(Date.now() / 1000)}\ninterrupted=1\n`);
}

/** The hunks read in a repository: { "<path>:<digest>": ms }, empty when none are. */
export async function loadRead(top) {
  const read = await readJson(readPath(top));
  return read && typeof read === "object" && !Array.isArray(read) ? read : {};
}

/**
 * Writes this window's marks (the `keys` it changed, as `read` has them) over
 * what is on disk now, so two windows on one repository keep each other's.
 * @returns {Promise<Record<string, number>>} the record as written
 */
export async function saveRead(top, read, keys) {
  await ensureDirs();
  const merged = mergeRead(await readJson(readPath(top)), read, keys);
  await write(readPath(top), JSON.stringify(merged));
  return merged;
}

/** Files that changed but whose contents aren't sent: generated ones, and ones not read (too many or too large), with why. */
const unseenFiles = (diff) => [
  ...diff.generatedPaths.map((path) => ({ path, why: "generated" })),
  ...(diff.unread ?? []).map((u) => ({ path: u.path, why: u.why || "not read" })),
];

/** The prompt that would be sent, to size it before anything is spent. */
export function preparePrompt(diff, { language, previous, preferences = "", task = null }) {
  const unseen = unseenFiles(diff);
  const listed = unseen.length ? "\n\nFiles changed whose contents were not sent (include them and their limited visibility in recap; never describe their contents):\n" + unseen.map((f) => `${JSON.stringify(f.path)} (${f.why})`).join("\n") : "";
  return buildPrompt({ digest: diff.text + listed, fileCount: diff.fileCount, hunkCount: diff.hunkCount, what: diff.what, language, previous, preferences, task });
}

export const promptChars = (p) => p.system.length + p.prompt.length;
export const fits = (p) => promptChars(p) <= MAX_PROMPT_CHARS;

/** The running or finished-but-unread job of a repository and source, or null. */
export async function jobOf(repo, sk) {
  const dir = jobDir(placeKey(repo.top, sk));
  const meta = await readJson(`${dir}/meta.json`);
  if (!meta) return null;
  const code = await readTextFile(`${dir}/code`).catch(() => null);
  return { dir, meta, done: code !== null, code };
}

/** Starts a generation in the background and returns its job. */
export async function startJob(repo, diff, { key, model, language, prompt, source, auto = false, before = [], task = null }) {
  // The model decides the backend: its key is unique across them (lib/job.js).
  const { backend, model: runModel } = modelOf(model);
  await ensureDirs();
  const dir = jobDir(placeKey(repo.top, diff.sk));
  // A run still going there (another window started it) is stopped, not orphaned.
  await stopRun(dir);
  await exec("rm", ["-rf", dir]);
  await exec("mkdir", ["-p", dir]);
  const meta = {
    key, code: codeKey(diff.files), model, backend, language, top: repo.top, source, sk: diff.sk, started: Date.now(), deadline: Date.now() + deadline(diff.hunkCount),
    idByAlias: diff.idByAlias, digestFiles: [...diff.digestFiles, ...unseenFiles(diff).map(({ path }) => ({ path, aliases: [] }))], hunkCount: diff.hunkCount, auto, before,
    // Kept with the walkthrough: where its task came from, and the key that tells when the task has changed since.
    task: task ? { from: task.from, label: task.label, short: task.short, text: task.text, context: task.context ?? "", key: taskKey(task) } : null,
  };
  const schema = schemaFor(Boolean(task));
  // Claude Code holds the answer to the schema (--json-schema). pi can't, so the schema goes in its
  // system prompt and the answer is parsed from text.
  const system = backend === "pi" ? `${prompt.system}\n\nAnswer with ONE JSON object that matches this JSON Schema exactly, and nothing else:\n${JSON.stringify(schema)}` : prompt.system;
  await writeTextFile(`${dir}/system.txt`, system, null);
  await writeTextFile(`${dir}/prompt.txt`, prompt.prompt, null);
  await writeTextFile(`${dir}/schema.json`, JSON.stringify(schema), null);
  await writeTextFile(`${dir}/run.sh`, jobScript(backend), null);
  await writeTextFile(`${dir}/meta.json`, JSON.stringify(meta), null);
  // Detached: exec returns at once, and the run outlives this window.
  // run.sh stops the run itself at the deadline, so a hung run ends even with no window open.
  const seconds = String(Math.ceil((meta.deadline - meta.started) / 1000));
  const launched = await exec("sh", ["-c", "nohup sh \"$0\" \"$1\" \"$2\" \"$3\" >/dev/null 2>&1 &", `${dir}/run.sh`, await programOf(backend), runModel, seconds]);
  if (launched.code !== 0) {
    await exec("rm", ["-rf", dir]);
    throw new Error((launched.stderr || launched.stdout || `sh exited with ${launched.code}`).trim());
  }
  return { dir, meta, done: false, code: null };
}

/**
 * The pid a job folder recorded, only while it is still that folder's run. After a reboot the number can belong to anything; it is never signalled
 * on the strength of the file alone.
 */
async function runPid(dir, known = null) {
  const pid = known ?? (await readTextFile(`${dir}/pid`).catch(() => null))?.trim();
  if (!pid || !/^\d+$/.test(pid)) return null;
  // pi rewrites its process title (ps shows only "pi"): the start time run.sh
  // recorded tells whether the number is still that process.
  const started = (await readTextFile(`${dir}/started`).catch(() => null))?.trim();
  const ps = await exec("ps", ["-o", "lstart=", "-p", pid]).catch(() => null);
  const now = ps?.code === 0 ? String(ps.stdout ?? "").trim() : "";
  if (!now) return null;
  if (started) return now.replace(/\s+/g, " ") === started.replace(/\s+/g, " ") ? pid : null;
  const r = await exec("ps", ["-o", "command=", "-p", pid]).catch(() => null);
  return r?.code === 0 && isRunCommand(r.stdout) ? pid : null;
}

async function stopRun(dir) {
  const pid = await runPid(dir);
  if (pid) await exec("kill", [pid]).catch(() => undefined);
}

/**
 * Whether a job's run is still going (a reboot leaves a job with no
 * answer and no process). The pid is read once and kept on the job.
 */
export async function alive(job) {
  job.pid ??= (await readTextFile(`${job.dir}/pid`).catch(() => null))?.trim() || null;
  if (!job.pid) return Date.now() - job.meta.started < 10_000; // not started yet
  if (await runPid(job.dir, job.pid)) return true;
  // run.sh writes pid, then started, just after the launch: a run isn't given up in between.
  return Date.now() - job.meta.started < 15_000;
}

/** The cheap look taken every second: the job, finished, once its code is there; else null. */
export async function finished(job) {
  const code = await readTextFile(`${job.dir}/code`).catch(() => null);
  return code === null ? null : { ...job, done: true, code };
}

export async function cancelJob(job) {
  await stopRun(job.dir);
  await exec("rm", ["-rf", job.dir]);
}

/** A failed job's files (out, err, code, meta) are kept for a day, to see why; older ones go. */
const FAILED_TTL_MIN = 24 * 60;
async function keepFailedJob(place, claimed) {
  const rootFailed = `${dataDir()}/failed`;
  await exec("mkdir", ["-p", rootFailed]).catch(() => undefined);
  const name = `${place}-${Date.now().toString(36)}`;
  const to = `${rootFailed}/${name}`;
  const moved = await exec("mv", [claimed, to]).catch(() => ({ code: 1 }));
  if (moved.code !== 0) { await exec("rm", ["-rf", claimed]).catch(() => undefined); return null; }
  await exec("sh", ["-c", `cd "$0" && find . -mindepth 1 -maxdepth 1 -mmin +${FAILED_TTL_MIN} -exec rm -rf {} + 2>/dev/null`, rootFailed]).catch(() => undefined);
  return `~/.herdr/walkthrough/failed/${name}`;
}

/**
 * A finished job → a stored walkthrough (and the pointer at it). The job's
 * folder goes either way; a failure is thrown with the reason. Two windows on
 * one repository both see the answer arrive: the folder is claimed by renaming
 * it (atomic), and the window that loses gets null and simply reads again.
 */
export async function finishJob(job) {
  const claimed = `${job.dir}.taken-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  const moved = await exec("mv", [job.dir, claimed]).catch(() => ({ code: 1 }));
  if (moved.code !== 0) return null;
  const read = (name) => readBig(`${claimed}/${name}`);
  try {
    const { raw, cost } = readOutcome({ backend: job.meta.backend, out: await read("out.json"), err: await read("err.txt"), code: job.code });
    const walkthrough = normalize(raw, job.meta.idByAlias, job.meta.digestFiles, { asks: Boolean(job.meta.task) });
    const { key, model, language, top, source, sk } = job.meta;
    // `before`: the hunks of the walkthrough shown when this one was asked for, to tell what changed since it was read.
    const entry = { version: VERSION, key, code: job.meta.code, model, language, top, source, sk, generatedAt: Date.now(), took: Date.now() - job.meta.started, cost, walkthrough, before: job.meta.before ?? [], task: job.meta.task ?? null };
    await ensureDirs();
    await write(entryPath(key), JSON.stringify(entry));
    await write(pointerPath(placeKey(top, sk)), JSON.stringify({ key, top, source: sk }));
    await evict();
    await exec("rm", ["-rf", claimed]);
    return entry;
  } catch (e) {
    // A failure leaves the job's folder for a day, to see why.
    const kept = await keepFailedJob(job.dir.split("/").pop(), claimed);
    if (kept) e.message = `${e.message} · files in ${kept}`;
    throw e;
  }
}

/** Keeps the newest entries. An entry is a few KB; nothing goes for being merely old. */
async function evict() {
  await exec("sh", ["-c", `cd "$0" && ls -t -- *.json 2>/dev/null | tail -n +${MAX_ENTRIES + 1} | while read -r f; do rm -f -- "$f"; done`, `${dataDir()}/entries`]).catch(() => undefined);
}

/** The system's preferred language (macOS), for the first walkthrough. */
export async function systemLocale() {
  const r = await exec("defaults", ["read", "-g", "AppleLanguages"]).catch(() => null);
  const first = /"?([A-Za-z]{2}[-_A-Za-z]*)"?/.exec(r?.stdout ?? "")?.[1];
  return first ?? (await exec("sh", ["-c", "echo ${LC_ALL:-${LANG:-}}"]).catch(() => null))?.stdout?.trim() ?? "";
}
