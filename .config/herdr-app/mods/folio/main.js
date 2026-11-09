import { View, div } from "gpui-kit";
import { h_flex, v_flex, TextView, Editor, EditorState } from "gpui-base";
import { props, readTextFile, watchFolder, exec, focused, panes, appHome, notify } from "herdr";
import { contentParts } from "./content.js";

const folderOf = path => path.replace(/\/[^/]*$/, "") || "/";
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
    this.path = props()?.path;
    this.text = null;
    this.error = null;
    this.busy = false;
    this.codeStates = new Map();
    if (!this.path) return;
    this.load(cx);
    cx.spawn(async cx => {
      try {
        for (;;) {
          await watchFolder(folderOf(this.path));
          this.load(cx);
        }
      } catch (error) { this.error = String(error); cx.notify(); }
    });
  }

  load(cx) {
    cx.spawn(async cx => {
      try {
        const text = await readTextFile(this.path);
        if (text === null) throw new Error("This file is no longer available.");
        if (text.includes("\0")) throw new Error("This file contains binary data. Open it in its default app.");
        // Bound native Markdown layout; the editor always receives the complete file.
        const clipped = text.length > 400000 ? text.slice(0, 400000) + "\n\n… Preview truncated. Open Neovim to read the whole file." : text;
        const markdown = clipped.replace(/^---\r?\n([\s\S]*?)\r?\n---[ \t]*(\r?\n|$)/, "```yaml\n$1\n```\n\n");
        if (markdown !== this.text) {
          this.releaseCode();
          this.text = markdown;
          this.parts = contentParts(markdown);
          this.parts.forEach((part, i) => {
            // Bound retained native editors for documents with hundreds of tiny fences.
            if (part.code === undefined || this.codeStates.size >= 128) return;
            this.codeStates.set(i, EditorState.new({
              value: part.code, language: LANGUAGES[part.language] || part.language,
              readonly: true, line_numbers: false, folding: false, soft_wrap: false,
              font_family: "JetBrains Mono", font_size: 13, syntax: SYNTAX,
            }));
          });
        }
        this.error = null;
      } catch (error) { this.error = String(error?.message ?? error); }
      cx.notify();
    });
  }

  edit(cx) {
    const pane = focused()?.pane;
    if (this.busy || !pane || panes().find(p => p.pane === pane)?.mod !== "folio") return;
    this.busy = true;
    cx.notify();
    cx.spawn(async cx => {
      try {
        const check = await exec("sh", [`${appHome()}/mods/folio/nvim.sh`, "--check"]);
        if (check.code !== 0) throw new Error("Neovim, jq and herdr-app must be on PATH.");
        const result = await exec(check.stdout.trim(), ["do", "pane.split", JSON.stringify({
          pane, direction: "right",
          argv: ["env", `HERDR_APP_HOME=${appHome()}`, "sh", `${appHome()}/mods/folio/nvim.sh`, this.path, pane],
        })]);
        if (result.code !== 0) throw new Error(result.stderr || result.stdout);
      } catch (error) {
        notify({ title: "Could not open Neovim", body: String(error), level: "error" });
      } finally { this.busy = false; cx.notify(); }
    });
  }

  releaseCode() {
    for (const state of this.codeStates.values()) state.release();
    this.codeStates.clear();
  }

  release() { this.releaseCode(); }

  content(part, i, t) {
    if (part.markdown !== undefined) return TextView.markdown(`folio-document-${i}`, part.markdown).text_color(t.foreground).selectable(true);
    if (part.code !== undefined) {
      if (!this.codeStates.has(i))
        return TextView.markdown(`folio-code-fallback-${i}`, part.original).text_color(t.foreground).selectable(true);
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
          .child(TextView.markdown(`folio-table-${i}-${r}-${c}`, cell).text_color(t.foreground).selectable(true))))));
  }

  render() {
    const t = SOLARIZED_LIGHT;
    const button = (id, label, action) => div().id(id).px(8).py(4).rounded(5).flex_none().cursor_pointer()
      .hover(s => s.bg(t.hover)).on_click((_e, cx) => action(cx)).child(label);
    return v_flex().id("folio").size_full().min_h(0).bg(t.background).text_color(t.foreground).text_size(13)
      .child(h_flex().h(38).flex_none().px(10).gap(4).items_center().border_b(1).border_color(t.border)
        .child(div().flex_1().min_w(0).truncate().tooltip(this.path || "").font_semibold().child(this.path?.split("/").at(-1) || "Markdown preview"))
        .child(button("folio-refresh", "Reload", cx => this.load(cx)))
        .child(button("folio-edit", this.busy ? "Opening…" : "Neovim", cx => this.edit(cx))))
      .child(div().flex_none().px(16).py(5).text_size(11).text_color(t.dim).child("Read-only preview · Quit Neovim to return here"))
      .child(div().id("folio-scroll").flex_1().min_h(0).overflow_y_scrollbar().p(16)
        .child(this.error || this.text === null
          ? div().text_color(t.muted).child(this.error || (this.path ? "Reading…" : "No file selected"))
          : v_flex().gap(12).children(this.parts.map((part, i) => this.content(part, i, t)))));
  }
}
