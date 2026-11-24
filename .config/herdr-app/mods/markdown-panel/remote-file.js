// A file on another machine, copied into the app folder so a picture can be drawn here.
import { appHome } from "herdr";
import { exists, mkdir, readFile, readdir, unlink, writeFile } from "fs/promises";
import { localService, serviceOn } from "./platform-host.js";
import { fileApi, pairEntries } from "./platform-files.js";
import { paths } from "./platform-paths.js";
import { extOf } from "./pure.js";

export const BYTE_CAP = 20 * 1024 * 1024;
export const ASK_BYTES = 2 * 1024 * 1024;
export const CHECK_MS = 5000;
export const SLOW_MS = 30000;
export const QUIET_LIMIT = 3;
// 2097150 is a multiple of 3, so only the last slice's base64 is padded, and it stays under the exec cap.
export const CHUNK = 2097150;
export const REMOTE_DIR = "data/kanso-panel/remote";
const DAY = 86400000;
const QUIET = /unreachable|did not answer|timed out|timeout|econnrefused|connection refused|offline|no route|was lost/i;
const DENIED = /permission denied|access is denied|eacces/i;
const MISSING = /no such file|cannot find (the )?path|not found|enoent/i;
const IMAGE = /!\[([^\]]*)\]\(([^)\s]+)\)|<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>/gi;

export const fileId = (machine, path) => [...`${machine}\0${path}`].reduce((h, ch) => Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0, 2166136261).toString(36);

export const copyName = (machine, path, mtime, size, ext) => `${fileId(machine, path)}-${mtime}-${size}${ext ? `.${ext}` : ""}`;

export const tooBig = (size) => !Number.isFinite(size) || size < 0 || size > BYTE_CAP;

export const slices = (size, chunk = CHUNK) => Number.isFinite(size) && size >= 0
  ? Array.from({ length: size === 0 ? 0 : Math.ceil(size / chunk) }, (_, i) => ({ offset: i * chunk, length: Math.min(chunk, size - i * chunk) }))
  : null;

export const cutShort = (result) => Boolean(result?.truncated) || /truncat/i.test(`${result?.stdout ?? ""}${result?.stderr ?? ""}`);

export const dropCopies = (entries, { id, keep, now, maxAge = DAY }) => entries
  .filter((entry) => entry.name !== keep && (entry.name.startsWith(`${id}-`) || now - entry.mtime > maxAge))
  .map((entry) => entry.name);

export const lookStamp = (name) => {
  const ms = Number(/-(\d+)\.[^.]+$/.exec(name)?.[1]);
  return Number.isFinite(ms) ? ms : 0;
};

export const sweepLook = async (root, id, keep) => {
  const names = await readdir(root).catch(() => []);
  const now = Date.now();
  const drop = dropCopies(names.map((name) => ({ name, mtime: lookStamp(name) })), { id, keep, now });
  await Promise.all(drop.map((old) => unlink(paths.join(root, old)).catch(() => {})));
};

export const said = (error) => String(error?.message ?? error ?? "").replace(/^Error:\s*/, "").trim();

export const copyFailure = (error, machine) => {
  const text = said(error);
  if (/over 20 MB/i.test(text)) return "This file is over 20 MB";
  if (/cut short|truncat/i.test(text)) return "The copy was cut short";
  if (DENIED.test(text)) return "Cannot read this file: permission denied";
  if (MISSING.test(text)) return "This file is no longer available";
  if (!text || QUIET.test(text)) return `${machine} did not answer`;
  return text;
};

export const listFailure = (error, machine) => {
  const text = said(error);
  if (DENIED.test(text)) return "Cannot list this folder: permission denied";
  if (!text || QUIET.test(text)) return machine ? `${machine} did not answer` : "This computer did not answer";
  return text || "Cannot list this folder";
};

export const remoteDue = (on, active, hidden) => Boolean(on) && active !== false && hidden !== true;

export const pollStart = () => ({ quiet: 0, wait: CHECK_MS });

export const pollNext = (poll, outcome) => {
  if (outcome === "changed" || outcome === "seen") return { quiet: 0, wait: CHECK_MS };
  if (outcome === "failed") return { quiet: poll?.quiet ?? 0, wait: SLOW_MS };
  const quiet = (poll?.quiet ?? 0) + 1;
  return { quiet, wait: quiet >= QUIET_LIMIT ? SLOW_MS : CHECK_MS };
};

export const stampOf = (size, mtime) => Number.isFinite(size) && Number.isFinite(mtime) ? { size, mtime } : null;

export const checkOutcome = (previous, next) => !next ? "failed" : !previous ? "seen" : previous.size === next.size && previous.mtime === next.mtime ? "same" : "changed";

export const asOf = (then, now) => {
  const min = Math.round(Math.max(0, now - then) / 60000);
  return min < 1 ? "as of just now" : `as of ${min} min ago`;
};

export const staleView = (had, fresh, now, error) => had
  ? { keep: true, hold: { at: fresh ?? now }, error: null, loading: false }
  : { keep: false, hold: null, error, loading: false };

export const askPicture = (size) => Number.isFinite(size) && size > ASK_BYTES;

export const bytesLabel = (size) => {
  if (!Number.isFinite(size) || size < 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1048576) return `${Math.max(1, Math.round(size / 1024))} KB`;
  const mb = size / 1048576;
  const text = mb >= 10 ? String(Math.round(mb)) : String(Math.round(mb * 10) / 10);
  return `${text} MB`;
};

export class ArmPoll {
  constructor(host) { this.host = host; }
  start(cx, probe) {
    if (this.host.arm) return;
    const wait = (this.host.poll ?? pollStart()).wait;
    this.host.arm = cx.timer.after(wait, (tick) => {
      this.host.arm = null;
      probe(tick);
    });
  }
}

export async function takeStamp(stat, previous) {
  try {
    const info = await stat();
    const next = stampOf(info?.size, info?.mtime);
    return { outcome: checkOutcome(previous, next), next };
  } catch {
    return { outcome: "failed", next: null };
  }
}

const winEntry = (chunk) => (chunk[0] === "d" || chunk[0] === "f") && chunk[1] === "\t" ? { name: chunk.slice(2), dir: chunk[0] === "d" } : null;

const entriesOf = (names) => names[0]?.startsWith("./") || !names.length
  ? pairEntries(names)
  : names.slice(0, 501).flatMap((chunk) => { const row = winEntry(chunk); return row ? [row] : []; });

const foldTree = (state, chunk) => {
  if (chunk.startsWith("\x05")) {
    const [size, mtime] = chunk.slice(1).trim().split(/\s+/).map(Number);
    return { ...state, stamp: stampOf(size, mtime) };
  }
  if (chunk.startsWith("\x01")) return { ...state, rel: chunk.slice(1), names: [], mode: "list" };
  if (chunk === "\x02") return { ...state, folders: [...state.folders, { rel: state.rel ?? "", entries: entriesOf(state.names) }], names: [], mode: null };
  if (chunk.startsWith("\x03")) return { ...state, mode: "git", git: chunk.length > 1 ? { top: chunk.slice(1), text: "" } : null };
  if (chunk === "\x04") return { ...state, mode: null };
  if (state.mode === "list") return { ...state, names: [...state.names, chunk] };
  if (state.mode === "git" && state.git && chunk) return { ...state, git: { ...state.git, text: state.git.text + chunk } };
  return state;
};

export function parseTree(stdout) {
  const text = String(stdout ?? "");
  const chunks = text.endsWith("\0") ? text.slice(0, -1).split("\0") : text.split("\0");
  const state = chunks.reduce(foldTree, { folders: [], names: [], rel: null, mode: null, stamp: null, git: null });
  // Porcelain is already text: the shell turned its NULs into newlines.
  const rows = state.git ? state.git.text.split(/\r?\n/).filter(Boolean) : [];
  return { folders: state.folders, stamp: state.stamp, top: state.git?.top ?? null, rows };
}

export const machineOf = (address) => {
  const at = String(address ?? "").indexOf("/");
  return at > 0 ? String(address).slice(0, at) : null;
};

export const appRelative = (file, root) => {
  const base = String(root).replaceAll("\\", "/").replace(/\/$/, "");
  const full = String(file).replaceAll("\\", "/");
  return full === base || full.startsWith(`${base}/`) ? full.slice(base.length + 1) : null;
};

export const drawablePath = (machine, image, path) => machine ? (image || null) : path;

export const svgPixels = (text) => {
  const tag = /<svg\b([^>]*)>/i.exec(String(text));
  const attr = (name) => {
    const n = Number(String(new RegExp(`\\b${name}\\s*=\\s*["']([^"']+)["']`, "i").exec(tag?.[1] ?? "")?.[1] ?? "").replace(/px$/i, ""));
    return Number.isFinite(n) && n > 0 ? Math.round(n) : null;
  };
  const raw = /\bviewBox\s*=\s*["']([^"']+)["']/i.exec(tag?.[1] ?? "");
  const box = raw ? raw[1].trim().split(/[\s,]+/).map(Number) : [];
  const width = attr("width") ?? (box.length === 4 && box[2] > 0 ? Math.round(box[2]) : null);
  const height = attr("height") ?? (box.length === 4 && box[3] > 0 ? Math.round(box[3]) : null);
  return tag && width && height ? { width, height } : null;
};

const localImage = (url) => url && !/^(https?:|data:|mailto:)/i.test(url);

export const markdownImages = (text) => [...String(text).matchAll(new RegExp(IMAGE.source, "gi"))].map((m) => ({ alt: m[1] ?? "", url: m[2] || m[3], at: m.index, length: m[0].length }));

export const markdownParts = (text) => {
  const images = markdownImages(text).filter((image) => localImage(image.url));
  const parts = images.reduce((out, image) => {
    const at = out.at(-1)?.end ?? 0;
    return [...out, ...(image.at > at ? [{ kind: "text", text: String(text).slice(at, image.at) }] : []), { kind: "image", alt: image.alt, url: image.url, end: image.at + image.length }];
  }, []);
  const end = parts.at(-1)?.end ?? 0;
  const rest = String(text).slice(end);
  return [...parts.map(({ end: _end, ...part }) => part), ...(rest ? [{ kind: "text", text: rest }] : [])];
};

const keptFile = (root) => paths.join(paths.dirname(root), "remote.kept");

// Remote mtime sits in the name; the kept list is when this computer wrote the copy.
const stampAt = (name) => {
  const sec = Number(/-(\d+)-\d+(?:\.[^.]+)?$/.exec(name)?.[1]);
  return Number.isFinite(sec) ? sec * 1000 : 0;
};

const readKept = async (file) => (await readFile(file, "utf8").catch(() => "")).split("\n").flatMap((line) => {
  const tab = line.indexOf("\t");
  if (tab < 1) return [];
  const at = Number(line.slice(tab + 1));
  return Number.isFinite(at) ? [[line.slice(0, tab), at]] : [];
});

const atOf = (rows, name) => rows.find((row) => row[0] === name)?.[1];

const sweep = async (root, id, keep) => {
  const names = await readdir(root).catch(() => []);
  const now = Date.now();
  const rows = await readKept(keptFile(root));
  const known = atOf(rows, keep) === undefined ? [...rows, [keep, now]] : rows;
  const drop = dropCopies(names.map((entry) => ({ name: entry, mtime: atOf(known, entry) ?? stampAt(entry) })), { id, keep, now });
  await Promise.all(drop.map((old) => unlink(paths.join(root, old)).catch(() => {})));
  const gone = new Set(drop);
  const live = names.filter((entry) => !gone.has(entry)).map((entry) => [entry, atOf(known, entry) ?? now]);
  const listed = live.some((row) => row[0] === keep) ? live : [...live, [keep, atOf(known, keep) ?? now]];
  await writeFile(keptFile(root), listed.map((row) => `${row[0]}\t${row[1]}`).join("\n"));
};

// QuickJS has no JIT: the base64 stays text and this computer's own tool writes the bytes.
const place = async (files, file, info, dest) => {
  const here = localService(fileApi);
  const parts = slices(info.size);
  if (!parts) throw new Error("The copy was cut short");
  const text = `${dest}.b64`;
  const staging = `${dest}.part`;
  try {
    if (!parts.length) await writeFile(staging, "");
    else {
      await parts.reduce(async (acc, slice, index) => {
        await acc;
        const encoded = await files.encode(file, parts.length === 1 ? undefined : slice);
        if (!encoded || cutShort(encoded) || encoded.code !== 0) throw new Error(encoded?.stderr || "The copy was cut short");
        const body = String(encoded.stdout ?? "");
        if (index === 0) await writeFile(text, body);
        else {
          const part = `${text}.${index}`;
          await writeFile(part, body);
          await here.decodeBase64File(text, null, { append: part });
          await unlink(part);
        }
      }, Promise.resolve());
      await here.decodeBase64File(text, staging);
    }
    const wrote = await here.stat(staging);
    if (wrote.size !== info.size) throw new Error("The copy was cut short");
    const moved = await here.move(staging, dest);
    if (moved?.code !== 0) throw new Error(moved?.stderr || "The copy was cut short");
  } finally {
    await unlink(text).catch(() => {});
    await unlink(staging).catch(() => {});
  }
};

export async function bring(file, on, { ask = false } = {}) {
  if (!on) return { path: file };
  try {
    const files = await serviceOn(fileApi, on);
    const info = await files.stat(file);
    if (tooBig(info.size)) throw new Error("This file is over 20 MB");
    const name = copyName(on, file, info.mtime, info.size, extOf(file));
    const root = paths.join(appHome(), REMOTE_DIR);
    const dest = paths.join(root, name);
    await mkdir(root, { recursive: true });
    const have = await exists(dest);
    if (!have && !ask && askPicture(info.size)) return { deferred: true, size: info.size, mtime: info.mtime };
    if (!have) await place(files, file, info, dest);
    await sweep(root, fileId(on, file), name);
    return { path: dest, size: info.size, mtime: info.mtime };
  } catch (e) {
    throw new Error(copyFailure(e, on));
  }
}
