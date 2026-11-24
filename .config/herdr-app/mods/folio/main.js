import { View, div, image } from "gpui-kit";
import { h_flex, v_flex, TextView, Editor, EditorState, ScrollHandle } from "gpui-base";
import { props, readTextFile, writeTextFile, watchFolder, exec, focused, panes, appHome, notify, checking } from "herdr";
import { contentParts } from "./content.js";
import { diagram, DIAGRAM_LIMIT } from "./mermaid.js";
import { sourcePosition } from "./link-target.js";

const folderOf = path => path.replace(/\/[^/]*$/, "") || "/";
const BODY_PADDING = 16;
const SOLARIZED_LIGHT = {
  background: "#fdf6e3", foreground: "#657b83", hover: "#eee8d5",
  border: "#93a1a1", dim: "#657b83", muted: "#586e75",
};
const SYNTAX = {
  keyword: "#859900", string: "#2aa198", comment: "#93a1a1", function: "#268bd2",
  type: "#b58900", number: "#d33682", constant: "#cb4b16", boolean: "#cb4b16",
  variable: "#657b83", operator: "#859900", punctuation: "#657b83", "string.escape": "#dc322f",
};
const LANGUAGES = { js: "javascript", py: "python", rs: "rust", sh: "bash", shell: "bash", yml: "yaml",
  csharp: "cs", "c#": "cs", "c++": "cpp", rb: "ruby", txt: "text", plaintext: "text" };

export default class Folio extends View {
  init(_props, cx) {
    const { path, line, column } = props() || {};
    this.path = path;
    this.position = sourcePosition(line, column);
    this.text = null;
    this.error = null;
    this.busy = false;
    this.codeStates = new Map();
    this.headings = new Map();
    this.scroll = ScrollHandle.new();
    this.readId = 0;
    this.closed = false;
    this.contentsOpen = false;
    this.bodyWidth = 0;
    if (!this.path || checking()) return;
    this.load(cx);
    cx.spawn(async cx => {
      try {
        const folder = folderOf(this.path);
        while (!this.closed) {
          this.watch = watchFolder(folder);
          const paths = await this.watch;
          if (!this.closed && paths.some(path => path === folder || path === this.path)) this.load(cx);
        }
      } catch (error) {
        if (!this.closed) notify({ title: "Folio file watch stopped", body: String(error), level: "warning" });
      } finally { this.watch = null; }
    });
  }

  load(cx) {
    if (!this.path) return;
    const readId = ++this.readId;
    cx.spawn(async cx => {
      try {
        const text = await readTextFile(this.path);
        if (this.closed || readId !== this.readId) return;
        if (text === null) throw new Error("This file is no longer available.");
        if (text.includes("\0")) throw new Error("This file contains binary data. Open it in its default app.");
        // Bound native Markdown layout; the editor always receives the complete file.
        const clipped = text.length > 400000 ? text.slice(0, 400000) + "\n\n… Preview truncated. Open Neovim to read the whole file." : text;
        if (clipped !== this.text) this.setDocument(clipped, cx);
        this.error = null;
      } catch (error) {
        if (this.closed || readId !== this.readId) return;
        this.error = String(error?.message ?? error);
      }
      cx.notify();
    });
  }

  setDocument(text, cx) {
    let diagramCount = 0;
    const parts = contentParts(text).map(part => {
      if (part.language !== "mermaid") return part;
      if (!part.closed) return { ...part, diagramError: "Unclosed Mermaid fence." };
      if (++diagramCount > DIAGRAM_LIMIT)
        return { ...part, diagramError: `This preview renders up to ${DIAGRAM_LIMIT} Mermaid diagrams.` };
      return part;
    });
    const firstLoad = this.text === null;
    this.releaseCode();
    this.headings.clear();
    parts.forEach((part, i) => {
      if (part.heading) this.headings.set(part.heading.slug, { ...part.heading, index: i });
      if (part.code === undefined || part.language === "mermaid" || this.codeStates.size >= 128) return;
      this.codeStates.set(i, EditorState.new({
        value: part.code, language: LANGUAGES[part.language] || part.language,
        readonly: true, line_numbers: false, folding: false, soft_wrap: false,
        font_family: "JetBrains Mono", font_size: 13, syntax: SYNTAX,
      }));
    });
    this.text = text;
    this.parts = parts;
    this.diagramResults = new Map();
    if (this.selectedSlug) this.position = sourcePosition(this.headings.get(this.selectedSlug)?.line, 1);
    if (firstLoad && this.position.line && parts.length) {
      const index = parts.findLastIndex(part => part.line <= this.position.line);
      this.scroll.scroll_to_item(Math.max(0, index));
    }
    if (diagramCount) this.loadDiagrams(parts, cx);
  }

  loadDiagrams(parts, cx) {
    cx.spawn(async cx => {
      for (const [index, part] of parts.entries()) {
        if (part.language !== "mermaid" || part.diagramError) continue;
        if (this.closed || this.parts !== parts) return;
        let result;
        try { result = { media: await diagram(part.code, appHome(), readTextFile, writeTextFile) }; }
        catch (error) { result = { diagramError: String(error?.message ?? error).slice(0, 300) }; }
        if (this.closed || this.parts !== parts) return;
        this.diagramResults = new Map(this.diagramResults).set(index, result);
        cx.notify();
      }
    });
  }

  jump(heading, cx) {
    this.selectedSlug = heading?.slug;
    this.position = heading ? sourcePosition(heading.line, 1) : {};
    this.contentsOpen = false;
    this.scroll.scroll_to_item(heading?.index ?? 0);
    cx.notify();
  }

  follow(url, cx) {
    if (!url.startsWith("#")) return cx.open_url(url);
    if (url === "#") return this.jump(null, cx);
    let heading;
    try { heading = this.headings.get(decodeURIComponent(url.slice(1))); }
    catch { /* A malformed percent escape has no heading target. */ }
    if (heading) this.jump(heading, cx);
    else notify({ title: "Folio heading not found", body: url, level: "warning" });
  }

  edit(cx) {
    const pane = focused()?.pane;
    if (!this.path || this.busy || !pane || panes().find(p => p.pane === pane)?.mod !== "folio") return;
    const { line, column } = this.position;
    this.busy = true;
    cx.notify();
    cx.spawn(async cx => {
      try {
        const check = await exec("sh", [`${appHome()}/mods/folio/nvim.sh`, "--check"]);
        if (check.code !== 0) throw new Error("Neovim, jq and herdr-app must be on PATH.");
        if (this.closed) return;
        const result = await exec(check.stdout.trim(), ["do", "pane.split", JSON.stringify({
          pane, direction: "right",
          argv: ["env", `HERDR_APP_HOME=${appHome()}`, "sh", `${appHome()}/mods/folio/nvim.sh`, this.path, pane, String(line || ""), String(column || "")],
        })]);
        if (result.code !== 0) throw new Error(result.stderr || result.stdout);
      } catch (error) {
        notify({ title: "Could not open Neovim", body: String(error), level: "error" });
      } finally { this.busy = false; if (!this.closed) cx.notify(); }
    });
  }

  releaseCode() {
    for (const state of this.codeStates.values()) state.release();
    this.codeStates.clear();
  }

  close() {
    this.closed = true;
    this.watch?.cancel();
    this.releaseCode();
    this.scroll.release();
  }

  markdown(id, text, t) {
    return TextView.markdown(id, text).text_color(t.foreground).selectable(true).scrollable(false).w_full()
      .on_link_click((url, cx) => this.follow(url, cx));
  }

  mermaid(part, i, t) {
    const { media, diagramError } = this.diagramResults.get(i) ?? part;
    if (!media) {
      return v_flex().gap(6)
        .child(div().text_color(diagramError ? SYNTAX["string.escape"] : t.muted)
          .child(diagramError ? `Mermaid: ${diagramError}` : "Rendering Mermaid…"))
        .child(this.markdown(`folio-diagram-source-${i}`, part.original, t));
    }
    const { width, height, path } = media;
    const available = Math.max(1, this.bodyWidth - BODY_PADDING * 2 - 8);
    const scale = Math.min(1, 560 / height, available / width);
    return image(path).w(width * scale).h(height * scale).flex_none();
  }

  contents(t) {
    const rowHeight = 28;
    return v_flex().id("folio-contents-list").h(Math.min(210, this.headings.size * rowHeight + 1)).flex_none().overflow_y_scrollbar()
      .border_b(1).border_color(t.border).children([...this.headings.values()].map(heading =>
        h_flex().id(`folio-contents-${heading.index}`).pl(12 + (heading.level - 1) * 10).pr(8)
          .h(rowHeight).items_center().flex_none().cursor_pointer().hover(s => s.bg(t.hover))
          .on_click((_e, cx) => this.jump(heading, cx)).child(div().min_w(0).truncate().child(heading.title))));
  }

  content(part, i, t) {
    if (part.markdown !== undefined) return this.markdown(`folio-document-${i}`, part.markdown, t);
    if (part.language === "mermaid") return this.mermaid(part, i, t);
    if (part.code !== undefined) {
      if (!this.codeStates.has(i))
        return this.markdown(`folio-code-fallback-${i}`, part.original, t);
      return v_flex().flex_none().min_w(0).bg(t.hover).rounded(5).overflow_hidden()
        .child(div().px(10).py(4).text_size(11).text_color(t.muted).child(part.language || "text"))
        .child(Editor.new(this.codeStates.get(i)).h(Math.min(360, Math.max(60, part.code.split("\n").length * 22 + 24)))
          .flex_none().bg(t.hover).text_color(t.foreground));
    }
    return v_flex().border_1().border_color(t.border).children(part.rows.map((row, r) =>
      h_flex().bg(r === 0 ? t.hover : t.background).when(r > 0, el => el.border_t(1).border_color(t.border))
        .children(row.map((cell, c) => div().flex_1().min_w(0).p(8)
          .when(c > 0, el => el.border_l(1).border_color(t.border))
          .when(r === 0, el => el.font_semibold())
          .when(part.align[c] === "right", el => el.text_right())
          .when(part.align[c] === "center", el => el.text_center())
          .child(this.markdown(`folio-table-${i}-${r}-${c}`, cell, t))))));
  }

  render() {
    const t = SOLARIZED_LIGHT;
    const button = (id, label, action) => div().id(id).px(8).py(4).rounded(5).flex_none().cursor_pointer()
      .hover(s => s.bg(t.hover)).on_click((_e, cx) => action(cx)).child(label);
    return v_flex().id("folio").size_full().min_h(0).bg(t.background).text_color(t.foreground).text_size(13)
      .child(h_flex().h(38).flex_none().px(10).gap(4).items_center().border_b(1).border_color(t.border)
        .child(div().flex_1().min_w(0).truncate().tooltip(this.path || "").font_semibold().child(this.path?.split("/").at(-1) || "Markdown preview"))
        .when(this.headings.size > 0 && !this.error, row => row.child(button("folio-toggle-contents", "Contents", cx => {
          this.contentsOpen = !this.contentsOpen;
          cx.notify();
        })))
        .child(button("folio-refresh", "Reload", cx => this.load(cx)))
        .child(button("folio-edit", this.busy ? "Opening…" : this.position.line ? `Neovim · ${this.position.line}` : "Neovim", cx => this.edit(cx))))
      .child(div().flex_none().px(16).py(5).text_size(11).text_color(t.dim).child("Read-only preview · Quit Neovim to return here"))
      .when(this.contentsOpen && !this.error, root => root.child(this.contents(t)))
      .child(v_flex().id("folio-scroll").flex_1().min_h(0).min_w(0).overflow_y_scrollbar()
        .track_scroll(this.scroll).p(BODY_PADDING).gap(12)
        .on_size_change(({ width }, cx) => {
          if (this.bodyWidth === width) return;
          this.bodyWidth = width;
          cx.notify();
        })
        .children(this.error || this.text === null
          ? [div().text_color(t.muted).child(this.error || (this.path ? "Reading…" : "No file selected"))]
          : this.parts.map((part, i) => div().flex_none().min_w(0).child(this.content(part, i, t)))));
  }
}
