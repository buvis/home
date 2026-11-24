// Markdown (Obsidian flavour, embeds already expanded) to a printable HTML page.
//   node convert.mjs <in.md> <out.html> <title>
// Source of the bundled convert.mjs. To rebuild after editing:
//   cd pdf && npm install && bun build convert.src.mjs --target node --outfile convert.mjs
import fs from "node:fs";
import MarkdownIt from "markdown-it";
import footnote from "markdown-it-footnote";
import deflist from "markdown-it-deflist";
import sub from "markdown-it-sub";
import sup from "markdown-it-sup";
import mark from "markdown-it-mark";
import container from "markdown-it-container";
import hljs from "highlight.js/lib/common";

const [, , input, output, title = "Note"] = process.argv;
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const md = new MarkdownIt({
  html: false, // raw HTML in a note prints as text
  linkify: true,
  highlight(code, lang) {
    try {
      if (lang && hljs.getLanguage(lang)) return `<pre class="hljs"><code>${hljs.highlight(code, { language: lang, ignoreIllegals: true }).value}</code></pre>`;
    } catch { /* fall through to plain */ }
    return "";
  },
}).use(footnote).use(deflist).use(sub).use(sup).use(mark);

// ```mermaid blocks become diagrams: the page loads mermaid.min.js (next to this file) and draws them.
let hasDiagram = false;
const fence = md.renderer.rules.fence;
md.renderer.rules.fence = (tokens, i, options, env, self) => {
  const t = tokens[i];
  if (t.info.trim().split(/\s+/)[0].toLowerCase() !== "mermaid") return fence(tokens, i, options, env, self);
  hasDiagram = true;
  return `<div class="diagram"><pre class="mermaid">${esc(t.content)}</pre></div>\n`;
};

// Images come from the vault as file: URLs, which markdown-it refuses by default.
md.validateLink = (url) => !/^\s*(javascript|vbscript):/i.test(url);

// ---- Wiki links: print the alias, else the note name ("note › heading") --------------
md.inline.ruler.before("link", "wikilink", (state, silent) => {
  const src = state.src, start = state.pos;
  const bang = src[start] === "!" ? 1 : 0;
  if (src.slice(start + bang, start + bang + 2) !== "[[") return false;
  const end = src.indexOf("]]", start + bang + 2);
  if (end < 0) return false;
  if (!silent) {
    const [target, alias] = src.slice(start + bang + 2, end).split("|");
    const t = state.push("text", "", 0);
    t.content = (alias ?? target).replace(/#\^?/, " › ").trim();
  }
  state.pos = end + 2;
  return true;
});

// Links to anything but the web print as plain text; nobody can follow them on paper.
const linkOk = (href) => /^(https?:|mailto:|#)/i.test(href ?? "");
md.core.ruler.push("local-links", (state) => {
  for (const block of state.tokens) {
    if (block.type !== "inline") continue;
    let skip = false;
    for (const t of block.children) {
      if (t.type === "link_open") { skip = !linkOk(t.attrGet("href")); t.meta = { skip }; }
      else if (t.type === "link_close") { t.meta = { skip }; skip = false; }
    }
  }
});
for (const name of ["link_open", "link_close"]) {
  const base = md.renderer.rules[name] ?? ((tokens, i, options, _env, self) => self.renderToken(tokens, i, options));
  md.renderer.rules[name] = (tokens, i, options, env, self) => (tokens[i].meta?.skip ? "" : base(tokens, i, options, env, self));
}

// ---- Images: ![alt|240](url) and ![alt|240x100](url) ----------------------------------
md.renderer.rules.image = (tokens, i) => {
  const t = tokens[i];
  const alt = t.children?.map((c) => c.content).join("") ?? "";
  const cut = alt.lastIndexOf("|");
  const size = cut >= 0 ? alt.slice(cut + 1).match(/^(\d+)(?:x(\d+))?$/) : null;
  const text = size ? alt.slice(0, cut) : alt;
  return `<img src="${esc(t.attrGet("src"))}" alt="${esc(text)}"${size ? ` width="${size[1]}"` : ""}${size?.[2] ? ` height="${size[2]}"` : ""}>`;
};

// ---- Callouts: > [!type]+ Title ---------------------------------------------------------
const KIND = {
  note: "note", info: "info", todo: "info", abstract: "tip", summary: "tip", tldr: "tip", tip: "tip", hint: "tip", important: "tip",
  success: "success", check: "success", done: "success", question: "warning", help: "warning", faq: "warning", warning: "warning", caution: "warning", attention: "warning",
  failure: "danger", fail: "danger", missing: "danger", danger: "danger", error: "danger", bug: "danger", example: "example", quote: "quote", cite: "quote",
};
const ICON = { note: "✎", info: "ℹ", tip: "💡", success: "✔", warning: "⚠", danger: "✖", example: "☰", quote: "❝" };

md.core.ruler.push("callouts", (state) => {
  const tk = state.tokens;
  for (let i = 0; i < tk.length; i++) {
    if (tk[i].type !== "blockquote_open") continue;
    const inline = tk[i + 2];
    if (tk[i + 1]?.type !== "paragraph_open" || inline?.type !== "inline") continue;
    const m = inline.content.match(/^\[!([\w-]+)\][+-]?[ \t]*([^\n]*)/);
    if (!m) continue;
    const type = m[1].toLowerCase(), kind = KIND[type] ?? "note";
    // Drop the "[!type] Title" line from the body.
    const nl = inline.children.findIndex((c) => c.type === "softbreak");
    inline.children = nl < 0 ? [] : inline.children.slice(nl + 1);
    inline.content = inline.content.slice(m[0].length).replace(/^\n/, "");
    if (!inline.children.length) tk.splice(i + 1, 3); // the paragraph held only the title
    tk[i].meta = { callout: { kind, title: m[2] || type[0].toUpperCase() + type.slice(1) } };
    let depth = 0;
    for (let j = i; j < tk.length; j++) {
      if (tk[j].type === "blockquote_open") depth++;
      else if (tk[j].type === "blockquote_close" && --depth === 0) { tk[j].meta = { callout: true }; break; }
    }
  }
});
md.renderer.rules.blockquote_open = (tokens, i, options, _env, self) => {
  const c = tokens[i].meta?.callout;
  return c
    ? `<div class="callout ${c.kind}"><div class="callout-title"><span>${ICON[c.kind]}</span>${esc(c.title)}</div><div class="callout-body">\n`
    : self.renderToken(tokens, i, options);
};
md.renderer.rules.blockquote_close = (tokens, i, options, _env, self) =>
  tokens[i].meta?.callout ? "</div></div>\n" : self.renderToken(tokens, i, options);

// ---- Task list items: [ ] [x] and the Tasks plugin's other states -------------------------
const TASK = { " ": "☐", x: "☑", X: "☑", "-": "☒", "/": "◐", ">": "➜", "<": "⇦", i: "ℹ", "?": "?", "!": "❗", "*": "★" };
md.core.ruler.push("tasks", (state) => {
  const tk = state.tokens;
  for (let i = 2; i < tk.length; i++) {
    if (tk[i].type !== "inline" || tk[i - 1].type !== "paragraph_open" || tk[i - 2].type !== "list_item_open") continue;
    const m = tk[i].content.match(/^\[(.)\][ \t]+/);
    const first = tk[i].children[0];
    if (!m || !(m[1] in TASK) || first?.type !== "text") continue;
    first.content = first.content.replace(/^\[.\][ \t]+/, "");
    const glyph = new state.Token("html_inline", "", 0);
    glyph.content = `<span class="task task-${m[1] === "x" || m[1] === "X" ? "done" : m[1] === "-" ? "cancelled" : "open"}">${TASK[m[1]]}</span> `;
    tk[i].children.unshift(glyph);
    tk[i - 2].attrJoin("class", "task-item");
  }
});

// ---- ::: embed Title ... ::: and ::: missing ... ::: (written by the exporter) ----------
const parse = (info, name) => info.trim().slice(name.length).trim();
md.use(container, "embed", {
  validate: (p) => /^embed\s/.test(p.trim()),
  render: (tokens, i) => tokens[i].nesting === 1
    ? `<div class="embed"><div class="embed-title">${esc(parse(tokens[i].info, "embed"))}</div>\n`
    : "</div>\n",
});
md.use(container, "missing", {
  validate: (p) => /^missing\b/.test(p.trim()),
  render: (tokens, i) => tokens[i].nesting === 1
    ? `<div class="missing"><span>⚠</span> <b>${esc(parse(tokens[i].info, "missing"))}</b> — `
    : "</div>\n",
});

const CSS = `
@page { size: A4; margin: 18mm 16mm; }
body { font: 11pt/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1f2328; }
h1, h2, h3, h4, h5, h6 { line-height: 1.25; margin: 1.3em 0 0.4em; break-after: avoid; }
h1 { font-size: 1.9em; border-bottom: 1px solid #d0d7de; padding-bottom: 0.2em; margin-top: 0; }
h2 { font-size: 1.5em; border-bottom: 1px solid #eaeef2; padding-bottom: 0.15em; }
h3 { font-size: 1.25em; } h4, h5, h6 { font-size: 1.05em; }
p { margin: 0.5em 0; } ul, ol { margin: 0.4em 0; padding-left: 1.6em; }
li.task-item { list-style: none; margin-left: -1.3em; } .task-done { color: #2f8132; } .task-cancelled { color: #8c959f; }
a { color: #0969da; } code { font: 0.9em ui-monospace, Menlo, monospace; background: #eff1f3; padding: 0.1em 0.3em; border-radius: 3px; }
pre { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 10px 12px; white-space: pre-wrap; word-break: break-word; }
pre code { background: none; padding: 0; }
.hljs-comment, .hljs-quote { color: #6e7781; font-style: italic; } .hljs-keyword, .hljs-selector-tag, .hljs-literal, .hljs-doctag { color: #cf222e; }
.hljs-string, .hljs-regexp, .hljs-addition { color: #0a3069; } .hljs-number, .hljs-attr, .hljs-attribute, .hljs-variable, .hljs-template-variable { color: #0550ae; }
.hljs-title, .hljs-section, .hljs-built_in, .hljs-type, .hljs-class .hljs-title { color: #8250df; } .hljs-deletion { color: #82071e; }
blockquote { margin: 0.6em 0; padding: 0.1em 1em; border-left: 4px solid #d0d7de; color: #57606a; }
table { border-collapse: collapse; margin: 0.6em 0; } th, td { border: 1px solid #d0d7de; padding: 4px 10px; } th { background: #f6f8fa; }
hr { border: 0; border-top: 1px solid #d0d7de; margin: 1.2em 0; }
img { max-width: 100%; height: auto; break-inside: avoid; }
mark { background: #fff3a3; }
dt { font-weight: 600; margin-top: 0.5em; } dd { margin-left: 1.6em; }
.footnotes { font-size: 0.9em; color: #57606a; } .footnotes-sep { margin-top: 2em; }
.callout { margin: 0.8em 0; border-left: 4px solid var(--c); background: var(--bg); border-radius: 4px; padding: 0.5em 0.9em; break-inside: avoid; }
.callout-title { font-weight: 600; color: var(--c); display: flex; gap: 0.5em; align-items: center; }
.callout-body > :first-child { margin-top: 0.3em; } .callout-body > :last-child { margin-bottom: 0.1em; }
.callout.note { --c: #1f6feb; --bg: #eef4ff; } .callout.info { --c: #0b7285; --bg: #e8f7fa; } .callout.tip { --c: #0a7d6c; --bg: #e6f7f3; }
.callout.success { --c: #2f8132; --bg: #ebf7ec; } .callout.warning { --c: #b35900; --bg: #fff3e0; } .callout.danger { --c: #c62828; --bg: #fdecec; }
.callout.example { --c: #6f42c1; --bg: #f3edfb; } .callout.quote { --c: #6e7781; --bg: #f3f4f6; }
.embed { margin: 0.8em 0; border-left: 3px solid #8c959f; padding: 0.1em 0 0.1em 1em; background: #fafbfc; }
.embed-title { font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.04em; color: #6e7781; margin-top: 0.4em; }
.missing { margin: 0.8em 0; padding: 0.5em 0.9em; border: 1px dashed #b35900; background: #fff8ee; color: #7a3e00; border-radius: 4px; break-inside: avoid; }
.diagram { margin: 0.8em 0; text-align: center; break-inside: avoid; } .diagram svg { display: block; margin: 0 auto; max-width: 100%; max-height: 190mm; height: auto; }
pre.mermaid { background: none; border: 0; text-align: left; white-space: pre; }
.missing p { display: inline; margin: 0; }
`;

const body = md.render(fs.readFileSync(input, "utf8"));
// Diagrams that fail to parse stay as their source text instead of an error graphic.
const script = hasDiagram
  ? `<script src="${new URL("./mermaid.min.js", import.meta.url).href}"></script><script>mermaid.initialize({ startOnLoad: false, theme: "default" }); mermaid.run({ querySelector: "pre.mermaid", suppressErrors: true });</script>`
  : "";
fs.writeFileSync(output, `<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title><style>${CSS}</style></head><body>${body}${script}</body></html>`);
