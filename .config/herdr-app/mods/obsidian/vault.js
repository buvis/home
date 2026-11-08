// The vault on disk: where it is, its notes, searching them, daily notes, and the
// three ways to open a note (the viewer pane, the Obsidian app, an editor split).
import { appHome, exec, focused, home, notify, panes, readTextFile, run, setShared, shared, window, writeTextFile } from "herdr";

const platform = () => window()?.platform ?? "macos";
const expand = (p) => (p.startsWith("~/") || p === "~" ? home() + p.slice(1) : p);
const parse = (text, file) => {
  if (text === null) return null;
  try { return JSON.parse(text); } catch (e) { throw new Error(`${file}: ${e.message}`); }
};

// ---- Where the vault is -------------------------------------------------------------

// Obsidian's own list of vaults, per platform and package.
function registries() {
  const h = home();
  if (platform() === "macos") return [`${h}/Library/Application Support/obsidian/obsidian.json`];
  if (platform() === "windows") return [`${h}/AppData/Roaming/obsidian/obsidian.json`];
  return [
    `${h}/.config/obsidian/obsidian.json`,
    `${h}/.var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json`,
    `${h}/snap/obsidian/current/.config/obsidian/obsidian.json`,
  ];
}

async function registeredVault() {
  for (const file of registries()) {
    const reg = parse(await readTextFile(file).catch(() => null), file);
    const vaults = Object.values(reg?.vaults ?? {}).filter((v) => typeof v?.path === "string");
    if (!vaults.length) continue;
    // The one Obsidian has open, else the one opened last.
    return (vaults.find((v) => v.open) ?? vaults.sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0))[0]).path;
  }
  return null;
}

let configured = null;

// { root, name, editor, daily: { folder, format, template }, newFolder }
export async function config() {
  if (configured && Date.now() - configured.at < 5000) return configured.value;
  const file = `${appHome()}/obsidian.json`;
  const own = parse(await readTextFile(file), file) ?? {};
  const root = own.vault ? expand(own.vault) : await registeredVault();
  if (!root) throw new Error(`No vault found. Put {"vault": "~/path/to/vault"} in ${file}`);
  const dot = `${root}/.obsidian`;
  const daily = parse(await readTextFile(`${dot}/daily-notes.json`).catch(() => null), "daily-notes.json") ?? {};
  const app = parse(await readTextFile(`${dot}/app.json`).catch(() => null), "app.json") ?? {};
  const trim = (p) => (p ?? "").replace(/^\/+|\/+$/g, "");
  const value = {
    root: root.replace(/\/+$/, ""),
    name: root.replace(/\/+$/, "").split(/[\\/]/).pop(),
    editor: Array.isArray(own.editor) ? own.editor : null,
    daily: {
      folder: trim(own.dailyFolder ?? daily.folder),
      format: own.dailyFormat ?? daily.format ?? "YYYY-MM-DD",
      template: trim(own.dailyTemplate ?? daily.template),
    },
    newFolder: app.newFileLocation === "folder" ? trim(app.newFileFolderPath) : "",
  };
  configured = { at: Date.now(), value };
  return value;
}

// ---- Notes --------------------------------------------------------------------------

let listed = null;

// Every file in the vault, relative, newest first when ripgrep is there. Hidden
// folders (.obsidian, .trash, .git) are left out.
export async function files(force = false) {
  const { root } = await config();
  if (!force && listed?.root === root && Date.now() - listed.at < 4000) return listed.files;
  let out;
  try {
    const r = await exec("rg", ["--files", "--sortr", "modified"], { cwd: root });
    if (r.code > 1) throw new Error(r.stderr.trim());
    out = r.stdout;
  } catch {
    const r = await exec("find", [".", "-type", "f", "-not", "-path", "*/.*"], { cwd: root });
    if (r.code !== 0) throw new Error(r.stderr.trim() || `Can't list ${root}`);
    out = r.stdout.replace(/^\.\//gm, "");
  }
  const list = out.split("\n").filter(Boolean).map((p) => p.replace(/\\/g, "/"));
  listed = { root, at: Date.now(), files: list };
  return list;
}

export const isNote = (p) => p.toLowerCase().endsWith(".md");
export const notes = async (force) => (await files(force)).filter(isNote);
export const title = (p) => p.split("/").pop().replace(/\.md$/i, "");
export const folderOf = (p) => (p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "");

// Title and path matching: every word must appear; a title that starts with the
// query beats one that contains it, which beats a path match. Ties keep recency.
export function match(list, query) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return list;
  const q = query.toLowerCase().trim();
  return list
    .map((p, i) => {
      const t = title(p).toLowerCase(), path = p.toLowerCase();
      if (!words.every((w) => path.includes(w))) return null;
      const rank = t === q ? 0 : t.startsWith(q) ? 1 : t.includes(q) ? 2 : words.every((w) => t.includes(w)) ? 3 : 4;
      return { p, rank, i };
    })
    .filter(Boolean)
    .sort((a, b) => a.rank - b.rank || a.i - b.i)
    .map((m) => m.p);
}

// What [[target]] points at, as Obsidian resolves it: a path, else the shortest
// path with that file name. Null when nothing matches.
export async function resolve(target, from = "") {
  const list = await files();
  let name = target.split("#")[0].split("|")[0].trim().replace(/\\/g, "/");
  if (!name) return from || null;
  const withMd = /\.[a-z0-9]{1,5}$/i.test(name) && !name.toLowerCase().endsWith(".md") ? [name] : [`${name}.md`, name];
  const lower = list.map((p) => p.toLowerCase());
  for (const n of withMd) {
    const rel = folderOf(from) ? `${folderOf(from)}/${n}` : n;
    for (const c of [n, rel]) {
      const i = lower.indexOf(c.toLowerCase());
      if (i >= 0) return list[i];
    }
  }
  const base = withMd.map((n) => n.split("/").pop().toLowerCase());
  const hits = list.filter((p) => base.includes(p.split("/").pop().toLowerCase()));
  return hits.sort((a, b) => a.length - b.length)[0] ?? null;
}

const rx = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Lines that contain the text, three per note at most.
export async function searchText(query) {
  const { root } = await config();
  let r;
  try {
    r = await exec("rg", ["-n", "-i", "-F", "--max-count", "3", "--max-columns", "300", "--max-columns-preview", "-g", "*.md", "--", query], { cwd: root });
  } catch {
    r = await exec("grep", ["-rniF", "--include=*.md", "--exclude-dir=.*", "-m", "3", "--", query, "."], { cwd: root });
  }
  if (r.code > 1) throw new Error(r.stderr.trim());
  return r.stdout.split("\n").flatMap((line) => {
    const m = line.match(/^(?:\.\/)?(.+?\.md):(\d+):(.*)$/i);
    return m ? [{ path: m[1].replace(/\\/g, "/"), line: Number(m[2]), text: m[3].trim() }] : [];
  }).slice(0, 400);
}

// Notes with #tag (or #tag/child) in the text or under tags: in the front matter.
export async function searchTag(tag) {
  const { root } = await config();
  const t = rx(tag.replace(/^#/, ""));
  let r;
  try {
    r = await exec("rg", ["-l", "-i", "-U", "-g", "*.md",
      "-e", `(^|[ \\t])#${t}([^\\w/-]|/|$)`,
      "-e", `(?m)^tags:[^\\n]*\\b${t}\\b`,
      "-e", `(?m)^tags:[ \\t]*\\n([ \\t]+-[^\\n]*\\n)*?[ \\t]+-[ \\t]+#?${t}[ \\t]*$`], { cwd: root });
  } catch {
    r = await exec("grep", ["-rliE", "--include=*.md", "--exclude-dir=.*", `(^|[[:space:]])#${t}([^[:alnum:]_/-]|/|$)`, "."], { cwd: root });
  }
  if (r.code > 1) throw new Error(r.stderr.trim());
  const hits = new Set(r.stdout.split("\n").filter(Boolean).map((p) => p.replace(/^\.\//, "").replace(/\\/g, "/")));
  return (await notes()).filter((p) => hits.has(p));
}

// Notes that link here with [[name]], [[name|..]], [[name#..]] or [[folder/name]].
export async function backlinks(path) {
  const { root } = await config();
  const name = rx(title(path)), full = rx(path.replace(/\.md$/i, ""));
  const pattern = `\\[\\[(${full}|([^\\]|#]*/)?${name})(\\.md)?([|#][^\\]]*)?\\]\\]`;
  let r;
  try { r = await exec("rg", ["-l", "-i", "-g", "*.md", "-e", pattern], { cwd: root }); }
  catch { r = await exec("grep", ["-rliE", "--include=*.md", "--exclude-dir=.*", pattern, "."], { cwd: root }); }
  if (r.code > 1) return [];
  return r.stdout.split("\n").filter(Boolean).map((p) => p.replace(/^\.\//, "").replace(/\\/g, "/")).filter((p) => p !== path);
}

// ---- Daily notes and new notes -------------------------------------------------------

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const pad = (n, w = 2) => String(n).padStart(w, "0");
const ordinal = (n) => n + (["th", "st", "nd", "rd"][(n % 100 >= 11 && n % 100 <= 13) || n % 10 > 3 ? 0 : n % 10]);

// The moment.js tokens daily-note formats use; [text] is literal.
export function formatDate(format, d = new Date()) {
  const tokens = {
    YYYY: () => d.getFullYear(), YY: () => pad(d.getFullYear() % 100),
    MMMM: () => MONTHS[d.getMonth()], MMM: () => MONTHS[d.getMonth()].slice(0, 3),
    MM: () => pad(d.getMonth() + 1), M: () => d.getMonth() + 1,
    Do: () => ordinal(d.getDate()), DD: () => pad(d.getDate()), D: () => d.getDate(),
    dddd: () => DAYS[d.getDay()], ddd: () => DAYS[d.getDay()].slice(0, 3),
    HH: () => pad(d.getHours()), H: () => d.getHours(), mm: () => pad(d.getMinutes()), ss: () => pad(d.getSeconds()),
  };
  return format.replace(/\[([^\]]*)\]|YYYY|YY|MMMM|MMM|MM|M|Do|DD|D|dddd|ddd|HH|H|mm|ss/g, (t, literal) => literal ?? String(tokens[t]()));
}

async function ensureFolder(abs) {
  const dir = abs.slice(0, abs.lastIndexOf("/"));
  if (platform() === "windows") await exec("cmd", ["/c", "if not exist", dir, "mkdir", dir]).catch(() => {});
  else await exec("mkdir", ["-p", dir]).catch(() => {});
}

// Today's note, made from the daily template the first time. Returns its path.
export async function today() {
  const c = await config();
  const name = formatDate(c.daily.format);
  const rel = `${c.daily.folder ? c.daily.folder + "/" : ""}${name}.md`;
  const abs = `${c.root}/${rel}`;
  if ((await readTextFile(abs)) === null) {
    let body = "";
    if (c.daily.template) {
      const tpl = await readTextFile(`${c.root}/${c.daily.template.replace(/\.md$/i, "")}.md`);
      body = (tpl ?? "")
        .replace(/\{\{date:([^}]+)\}\}/g, (_m, f) => formatDate(f.trim()))
        .replace(/\{\{time:([^}]+)\}\}/g, (_m, f) => formatDate(f.trim()))
        .replace(/\{\{date\}\}/g, name).replace(/\{\{time\}\}/g, formatDate("HH:mm")).replace(/\{\{title\}\}/g, name);
    }
    await ensureFolder(abs);
    await writeTextFile(abs, body, null);
    listed = null;
  }
  return rel;
}

// Adds text to the end of today's note, retrying if the note changes meanwhile.
// Returns the note's path.
async function appendToday(text) {
  const { root } = await config();
  const rel = await today();
  const abs = `${root}/${rel}`;
  for (let attempt = 0; attempt < 3; attempt++) {
    const before = (await readTextFile(abs)) ?? "";
    const sep = before && !before.endsWith("\n") ? "\n" : "";
    try { await writeTextFile(abs, `${before}${sep}${text}`, before); return rel; }
    catch (e) { if (attempt === 2) throw e; }
  }
}

// Adds "- text" to the end of today's note.
export const capture = (text) => appendToday(`- ${text}\n`);

// Adds a "## heading" section with the text to the end of today's note.
export const appendSection = (heading, text) => appendToday(`\n## ${heading}\n\n${text.replace(/\s+$/, "")}\n`);

const cleanName = (name) => name.trim().replace(/\.md$/i, "").replace(/[\\:*?"<>|#^[\]]/g, "-");
const newPath = (c, clean) => `${c.newFolder && !clean.includes("/") ? c.newFolder + "/" : ""}${clean}.md`;

// A new empty note where Obsidian puts new notes, or the one already there with
// that name. Returns its path.
export async function create(name) {
  const c = await config();
  const rel = newPath(c, cleanName(name));
  const abs = `${c.root}/${rel}`;
  if ((await readTextFile(abs)) === null) {
    await ensureFolder(abs);
    await writeTextFile(abs, "", null);
    listed = null;
  }
  return rel;
}

// A new note holding text, where Obsidian puts new notes. A name that's taken gets
// " 2", " 3", ... as Obsidian does; nothing is overwritten. Returns its path.
export async function createWith(name, text) {
  const c = await config();
  const clean = cleanName(name) || "Untitled";
  for (let n = 1; n < 100; n++) {
    const rel = newPath(c, n === 1 ? clean : `${clean} ${n}`);
    const abs = `${c.root}/${rel}`;
    if ((await readTextFile(abs)) !== null) continue;
    await ensureFolder(abs);
    try { await writeTextFile(abs, text, null); } catch { continue; }
    listed = null;
    return rel;
  }
  throw new Error(`Too many notes named ${clean}`);
}

// ---- Opening -------------------------------------------------------------------------

export async function openUrl(url) {
  const p = platform();
  const [cmd, args] = p === "macos" ? ["open", [url]] : p === "windows" ? ["cmd", ["/c", "start", "", url]] : ["xdg-open", [url]];
  const r = await exec(cmd, args).catch((e) => ({ code: 1, stderr: String(e) }));
  if (r.code !== 0) notify({ title: "Couldn't open it", body: r.stderr?.trim() || url, level: "error" });
}

export async function openInObsidian(rel) {
  const { root } = await config();
  return openUrl(`obsidian://open?path=${encodeURIComponent(`${root}/${rel}`)}`);
}

export async function openInEditor(rel, line) {
  const c = await config();
  const abs = `${c.root}/${rel}`;
  const at = line ? [`+${line}`] : [];
  // $VISUAL, else $EDITOR, else vi; +line only for editors that take it.
  const script = 'e="${VISUAL:-${EDITOR:-vi}}"; case "${e##*/}" in vi|vim|nvim|nano|emacs|micro|kak|hx) ;; *) [ "$#" -gt 1 ] && shift ;; esac; exec $e "$@"';
  const argv = c.editor ? [...c.editor, ...at, abs]
    : platform() === "windows" ? ["notepad", abs]
    : ["sh", "-c", script, "editor", ...at, abs];
  run("pane.split", { direction: "right", argv });
}

// Viewer panes list their tab under shared "obsidian.viewers" ({id: tab}). A note
// opens in this tab's viewer when there is one, else in a new split.
export function openInViewer(rel, line) {
  const tab = focused()?.tab;
  const registered = Object.values(shared("obsidian.viewers") ?? {}).includes(tab);
  const live = panes().some((p) => p.tab === tab && p.mod === "obsidian");
  if (tab && registered && live) {
    setShared("obsidian.show", { tab, note: rel, line: line ?? null, n: Date.now() });
  } else {
    run("pane.split", { direction: "right", mod: "obsidian", props: { note: rel, line: line ?? null } });
  }
}

// how: "viewer" (Enter), "obsidian" (Cmd/Ctrl+Enter), "editor" (Shift+Enter).
export function open(rel, how = "viewer", line) {
  if (how === "obsidian") return openInObsidian(rel);
  if (how === "editor") return openInEditor(rel, line);
  if (!isNote(rel)) return config().then((c) => openUrl(encodeURI(`file://${c.root}/${rel}`)));
  return openInViewer(rel, line);
}
