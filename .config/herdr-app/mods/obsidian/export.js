// Export a note to PDF. Steps: expand embeds and image paths here (needs the vault), turn
// the markdown into a styled HTML page with markdown-it (pdf/convert.mjs, run by node), and
// print that page with a headless Chromium-based browser (Chrome, Chromium, Edge, Brave).
import { appHome, exec, home, readTextFile, window, writeTextFile } from "herdr";
import * as vault from "./vault.js";

const MAC = ["Google Chrome", "Chromium", "Microsoft Edge", "Brave Browser"]
  .map((n) => `/Applications/${n}.app/Contents/MacOS/${n}`);
const LINUX = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser"];

async function findBrowser() {
  const mac = (window()?.platform ?? "macos") === "macos";
  for (const c of mac ? MAC : LINUX) {
    const r = mac ? await exec("test", ["-x", c]) : await exec("sh", ["-c", `command -v ${c}`]);
    if (r.code === 0) return mac ? c : r.stdout.trim();
  }
  throw new Error("No Chrome, Chromium, Edge or Brave found to print the PDF with");
}

const safeName = (s) => s.replace(/[\\/:*?"<>|\u0000-\u001f]/g, "-").replace(/\s+/g, " ").trim().slice(0, 120) || "note";

// ---- Turning a note into one self-contained markdown text -------------------------------
// Embedded notes are put in as ::: embed containers, images become file: URLs, and Dataview
// and Tasks queries (which need Obsidian's plugins) become a ::: missing notice.

const IMAGE = /\.(png|jpe?g|gif|webp|svg|bmp|avif)$/i;
const MAX_DEPTH = 3;
const FENCE = /^\s*(```|~~~)\s*([\w-]*)/;
const frontMatter = (t) => t.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, "");

async function replaceAsync(text, re, fn) {
  const parts = [];
  let last = 0;
  for (const m of text.matchAll(re)) { parts.push(text.slice(last, m.index), fn(...m)); last = m.index + m[0].length; }
  parts.push(text.slice(last));
  return (await Promise.all(parts)).join("");
}

const fileUrl = (root, rel) => `file://${encodeURI(`${root}/${rel}`).replace(/\(/g, "%28").replace(/\)/g, "%29")}`;

// From "## Heading" to the next heading of the same or a higher level.
function section(text, heading) {
  const lines = text.split("\n"), want = heading.trim().toLowerCase();
  const level = (l) => l.match(/^(#{1,6})\s+(.*?)\s*#*\s*$/);
  const at = lines.findIndex((l) => level(l)?.[2].toLowerCase() === want);
  if (at < 0) return null;
  const depth = level(lines[at])[1].length;
  let end = lines.length;
  for (let i = at + 1; i < lines.length; i++) if (level(lines[i]) && level(lines[i])[1].length <= depth) { end = i; break; }
  return lines.slice(at, end).join("\n").trim();
}

// The paragraph or list that ends in "^id".
function block(text, id) {
  const lines = text.split("\n");
  const at = lines.findIndex((l) => l.trimEnd().endsWith(`^${id}`));
  if (at < 0) return null;
  let a = at, b = at;
  while (a > 0 && lines[a - 1].trim() && !/^#{1,6}\s/.test(lines[a - 1])) a--;
  while (b < lines.length - 1 && lines[b + 1].trim()) b++;
  return lines.slice(a, b + 1).join("\n").replace(new RegExp(`\\s*\\^${id}\\s*$`, "m"), "").trim();
}

async function embedOf(target, from, depth, seen, root) {
  const [ref, opt] = target.split("|");
  const [name, sub] = ref.split("#");
  const rel = name.trim() ? await vault.resolve(name.trim(), from) : from;
  if (!rel) return `*[${ref.trim() || "embed"} not found]*`;
  if (IMAGE.test(rel)) {
    const size = (opt ?? "").trim().match(/^\d+(x\d+)?$/)?.[0];
    return `![${size ? "|" + size : ""}](${fileUrl(root, rel)})`;
  }
  if (!vault.isNote(rel)) return `*[${rel.split("/").pop()}]*`;
  if (depth >= MAX_DEPTH || seen.includes(rel)) return `*[${vault.title(rel)}: embedded note left out (nested too deep or a loop)]*`;
  let text = frontMatter((await readTextFile(`${root}/${rel}`)) ?? "");
  let label = vault.title(rel);
  if (sub) {
    const cut = sub.startsWith("^") ? block(text, sub.slice(1)) : section(text, sub);
    if (cut === null) return `*[${label}: “${sub}” not found]*`;
    text = cut;
    label += ` › ${sub.replace(/^\^/, "")}`;
  }
  // Outer containers need a longer marker than the ones inside them.
  const mark = ":".repeat(3 + MAX_DEPTH - depth);
  return `\n${mark} embed ${label}\n${await expand(text, rel, depth + 1, [...seen, rel], root)}\n${mark}\n`;
}

async function expand(markdown, from, depth, seen, root) {
  const out = [];
  let fence = null, skipping = null;
  for (const line of markdown.replace(/\r\n?/g, "\n").split("\n")) {
    const f = line.match(FENCE);
    if (skipping) { if (f && line.trim().startsWith(skipping)) skipping = null; continue; }
    if (f && !fence && /^(dataview|dataviewjs|tasks)$/i.test(f[2])) {
      skipping = f[1];
      const kind = { dataview: "Dataview query", dataviewjs: "DataviewJS query", tasks: "Tasks query" }[f[2].toLowerCase()];
      out.push("", `::: missing ${kind} not shown`, "It runs inside Obsidian. Open the note there to see its result.", ":::", "");
      continue;
    }
    if (f) { fence = fence ? null : f[1]; out.push(line); continue; }
    if (fence) { out.push(line); continue; }
    // Block ids (" ^id" at the end of a line) are Obsidian bookkeeping.
    let l = line.replace(/%%.*?%%/g, "").replace(/\s\^[\w-]+\s*$/, "");
    const quote = l.match(/^(\s*>[> ]*)/)?.[1] ?? "";
    l = await replaceAsync(l, /!\[\[([^\]]+)\]\]/g, (_m, target) => embedOf(target, from, depth, seen, root));
    l = await replaceAsync(l, /!\[([^\]]*)\]\(\s*(<[^>]+>|[^)]+?)\s*\)/g, async (m, alt, url) => {
      url = url.replace(/^<|>$/g, "");
      if (/^(https?|data|file):/i.test(url)) return m;
      let path = url;
      try { path = decodeURIComponent(url); } catch { /* keep as written */ }
      const rel = await vault.resolve(path, from);
      return rel && IMAGE.test(rel) ? `![${alt}](${fileUrl(root, rel)})` : m;
    });
    // An embed brings its own lines; keep them inside the callout or list they came from.
    out.push(...l.split("\n").map((p, i) => (i && quote ? quote + p : p)));
  }
  return out.join("\n");
}

// Writes ~/Downloads/<title>.pdf and returns its path.
export async function exportPdf(rel) {
  if (window()?.platform === "windows") throw new Error("PDF export isn't available on Windows yet");
  const { root } = await vault.config();
  await vault.files(); // loads the titles of ID-named notes
  const title = vault.title(rel);
  const source = frontMatter((await readTextFile(`${root}/${rel}`)) ?? "");
  const markdown = await expand(source, rel, 0, [rel], root);
  const browser = await findBrowser();
  const tmp = (await exec("mktemp", ["-d"])).stdout.trim();
  if (!tmp) throw new Error("Couldn't make a temporary folder");
  const out = `${home()}/Downloads/${safeName(title)}.pdf`;
  try {
    await writeTextFile(`${tmp}/note.md`, markdown, null);
    const conv = await exec("sh", ["-c", 'export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"; exec node "$@"', "node", `${appHome()}/mods/obsidian/pdf/convert.mjs`, `${tmp}/note.md`, `${tmp}/note.html`, title], { timeout: 60000 });
    if (conv.code !== 0) throw new Error(`Markdown conversion failed: ${conv.stderr.trim().split("\n").pop() || "node not found"}`);
    // Diagrams are drawn by a script; let the page run it before printing.
    const wait = /^\s*(```|~~~)\s*mermaid/im.test(markdown) ? ["--virtual-time-budget=20000"] : [];
    const print = (extra) => exec(browser, ["--headless=new", "--disable-gpu", "--no-pdf-header-footer", ...wait, ...extra, `--user-data-dir=${tmp}/profile`, `--print-to-pdf=${out}`, `file://${tmp}/note.html`], { timeout: 60000 });
    await exec("rm", ["-f", out]);
    let r = await print([]);
    let made = (await exec("test", ["-s", out])).code === 0;
    // Some setups (a sandboxed launcher, containers) can't start the browser's own sandbox.
    if (!made) { r = await print(["--no-sandbox"]); made = (await exec("test", ["-s", out])).code === 0; }
    if (!made) throw new Error(r.stderr?.trim().split("\n").pop() || "The browser made no PDF");
    return out;
  } finally {
    await exec("rm", ["-rf", tmp]).catch(() => {});
  }
}
