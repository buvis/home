import { serviceOn } from "./platform-host.js";
import { paths } from "./platform-paths.js";
import { fileApi } from "./platform-files.js";
import { div, svg, image } from "gpui-kit";
import { v_flex, h_flex, Editor, EditorState, TextView, Textarea, TextareaState } from "gpui-base";
import { readTextFile, writeTextFile, theme, settings, home, appHome } from "herdr";
import { parseBlocks, joinBlocks, headingOf, headingLine, parseTable, tableLines } from "./blocks.js";
import { skeleton, breathe, quietLink, tokens } from "./ui.js";
import { bring, appRelative, markdownParts, staleView, bytesLabel, copyFailure } from "./remote-file.js";

export function readingLines(t) {
  const { line } = skeleton({ border: t.border });
  return breathe(v_flex().id("kanso-skeleton").w_full().max_w(760).px(16).pt(14).gap(10))
    .children([280, 200, 240, 120, 220, 160, 190].map((w) => line(w, 12)));
}

const MAX_TEXT = 400000;
const AUTOSAVE_MS = 700;
const HEADING_SIZE = [0, 22, 18, 16, 15, 14, 13.5];

// Front matter shown as a code block, so it reads as data instead of running into the first paragraph.
export function readable(text) {
  const m = /^-{3}\r?\n([\s\S]*?)\r?\n-{3}[ \t]*(\r?\n|$)/.exec(text);
  const body = m ? "```yaml\n" + m[1] + "\n```\n\n" + text.slice(m[0].length) : text;
  return body.length > MAX_TEXT ? body.slice(0, MAX_TEXT) + "\n\n… (file truncated)" : body;
}

export function linkTarget(url, docPath) {
  if (/^(https?:|mailto:)/i.test(url)) return { web: url };
  if (/^[a-z][a-z0-9+.-]*:/i.test(url) && !/^file:/i.test(url) && !/^[a-z]:[\\/]/i.test(url)) return null;
  const raw = url.replace(/[?#].*$/, "");
  const given = /^file:/i.test(raw) ? paths.fromFileUrl(raw) : decodeURIComponent(raw);
  if (!given) return null;
  return { file: paths.isAbsolute(given) ? paths.normalize(given) : paths.join(paths.dirname(docPath), given) };
}

export class MarkdownDoc {
  // path: absolute; on: a remote machine (null here); without onOpen, links to files do nothing.
  constructor(path, on, onOpen, icons = "mods/kanso-chrome/icons") {
    this.path = path; this.on = on ?? null; this.onOpen = onOpen ?? null; this.icons = icons;
    this.saved = null;
    this.text = null;
    this.blocks = [];
    this.active = null;  // the block being edited
    this.box = null;     // its text, or a table's cells
    this.cells = null;
    this.source = null;  // the whole file as Markdown, while "Source" is on
    this.conflict = false; this.saving = false; this.seq = 0;
    this.error = null; this.big = false; this.shots = new Map(); this.shotSeq = 0;
  }

  get canEdit() { return !this.on && this.saved !== null && !this.big; }
  get dirty() { return this.text !== null && this.text !== this.saved; }
  get editing() { return this.active !== null || Boolean(this.source); }

  load(cx) {
    const path = this.path;
    cx.spawn(async (cx) => {
      try {
        const text = this.on
          ? await (await serviceOn(fileApi, this.on)).read(path)
          : await readTextFile(path);
        if (this.path !== path) return;
        if (text == null) { this.miss("This file is no longer available"); return; }
        if (String(text).includes("\0")) { this.miss("Binary file: nothing to show"); return; }
        this.error = null; this.held = null; this.fresh = Date.now();
        if (text === this.saved) { if (this.on) this.pictures(cx); return; }
        // Yours, not saved yet, and the file moved on: you choose which stays.
        if (this.dirty) { this.conflict = true; this.disk = text; return; }
        this.saved = text; this.big = text.length > MAX_TEXT;
        this.setText(text);
        if (this.on) this.pictures(cx);
      } catch (e) {
        if (this.path === path) this.miss(this.on ? copyFailure(e, this.on) : `Cannot read this file: ${e?.message ?? e}`);
      } finally { cx.notify(); }
    });
  }

  // A later miss keeps the document; the panel shows its age.
  miss(message) {
    const view = this.on ? staleView(this.saved != null, this.fresh, Date.now(), message) : null;
    if (view?.keep) { this.held = view.hold; this.error = null; return; }
    this.error = message;
  }

  setText(text) {
    this.close();
    this.text = text;
    this.blocks = parseBlocks(text);
    this.source?.set_value(text);
  }

  open(i, cx) {
    if (!this.canEdit || this.conflict) return;
    if (this.active === i) return;
    this.close();
    const b = this.blocks[i];
    if (!b) return;
    this.active = i;
    if (b.kind === "table") this.openTable(i, cx);
    else {
      const value = b.kind === "heading" ? headingOf(b.lines[0]).text : b.lines.join("\n");
      const box = TextareaState.new({ value, placeholder: b.kind === "heading" ? "Heading" : "Write…" });
      box.set_auto_grow(1, 40);
      box.on("change", (_e, cx) => {
        const v = box.value();
        this.setLines(i, b.kind === "heading" ? [headingLine(headingOf(b.lines[0]).level, v)] : v.split("\n"), cx);
      });
      this.box = box;
      box.focus();
    }
    cx.notify();
  }

  setLines(i, lines, cx) {
    this.blocks = this.blocks.with(i, { ...this.blocks[i], lines });
    this.changed(cx);
  }

  openTable(i, cx) {
    const table = parseTable(this.blocks[i].lines);
    const cell = (value, put) => {
      const s = TextareaState.new({ value });
      s.set_auto_grow(1, 8);
      s.on("change", (_e, cx) => {
        if (!this.cells) return;
        this.cells = { ...this.cells, table: put(this.cells.table, s.value()) };
        this.setLines(i, tableLines(this.cells.table), cx);
      });
      return s;
    };
    this.cells = {
      table, block: i,
      head: table.head.map((v, c) => cell(v, (tb, x) => ({ ...tb, head: tb.head.with(c, x) }))),
      rows: table.rows.map((r, ri) => r.map((v, c) => cell(v, (tb, x) => ({ ...tb, rows: tb.rows.with(ri, tb.rows[ri].with(c, x)) })))),
    };
    this.cells.head[0]?.focus();
  }

  // fn gets a copy of the table, so the open one is never changed in place.
  reshape(fn, cx) {
    const { table, block } = this.cells;
    const copy = { ...table, head: [...table.head], align: [...table.align], rows: table.rows.map((r) => [...r]) };
    const next = fn(copy) ?? copy;
    this.blocks = this.blocks.with(block, { ...this.blocks[block], lines: tableLines(next) });
    this.releaseCells();
    this.openTable(block, cx);
    this.changed(cx);
  }

  releaseCells() {
    if (!this.cells) return;
    for (const s of [...this.cells.head, ...this.cells.rows.flat()]) s.release();
    this.cells = null;
  }

  // Reparsed on close, so a paragraph split with an empty line becomes two.
  close() {
    this.box?.release(); this.box = null;
    this.releaseCells();
    if (this.active !== null && this.text !== null) this.blocks = parseBlocks(this.text);
    this.active = null;
  }

  append(cx) {
    if (!this.canEdit || this.conflict) return;
    this.close();
    const last = this.blocks.at(-1);
    this.blocks = [
      ...this.blocks,
      ...(last && last.kind !== "blank" ? [{ kind: "blank", lines: [""] }] : []),
      { kind: "paragraph", lines: [""] },
      { kind: "blank", lines: [""] }, // the file ends with a newline
    ];
    this.open(this.blocks.length - 2, cx);
  }

  changed(cx) {
    this.text = joinBlocks(this.blocks);
    this.later(cx);
    cx.notify();
  }

  later(cx) {
    const seq = this.seq + 1;
    this.seq = seq;
    cx.timer.after(AUTOSAVE_MS, (cx) => { if (seq === this.seq) this.save(cx); });
  }

  save(cx) {
    if (!this.dirty || this.saving || this.conflict || this.on) return;
    const text = this.text, expected = this.saved;
    this.saving = true; cx.notify();
    cx.spawn(async (cx) => {
      try {
        await writeTextFile(this.path, text, expected);
        this.saved = text; this.savedAt = Date.now();
      } catch {
        // The file changed on disk after it was read: read it to show the choice.
        const disk = await readTextFile(this.path, { on: this.on }).catch(() => null);
        if (disk !== null && disk !== expected) { this.conflict = true; this.disk = disk; }
      } finally {
        this.saving = false;
        if (this.dirty && !this.conflict) this.later(cx);
        cx.notify();
      }
    });
  }

  // False when it could not save: the file changed on disk and the choice is shown.
  async flush() {
    this.seq = this.seq + 1;
    if (!this.dirty || this.on) return !this.conflict;
    if (this.conflict) return false;
    try { await writeTextFile(this.path, this.text, this.saved); this.saved = this.text; return true; }
    catch {
      const disk = await readTextFile(this.path, { on: this.on }).catch(() => null);
      if (disk !== null) { this.conflict = true; this.disk = disk; }
      return false;
    }
  }

  keepMine(cx) {
    if (!this.conflict) return;
    this.saved = this.disk; this.conflict = false; this.disk = null;
    this.save(cx);
  }

  takeTheirs(cx) {
    if (!this.conflict) return;
    this.saved = this.disk; this.conflict = false; this.disk = null;
    this.setText(this.saved);
    cx.notify();
  }

  toggleSource(cx) {
    if (!this.canEdit) return;
    if (this.source) {
      this.source.release(); this.source = null;
      this.blocks = parseBlocks(this.text);
    } else {
      this.close();
      const t = theme();
      this.source = EditorState.new({ language: "markdown", value: this.text, soft_wrap: true, line_numbers: false, folding: false,
        font_family: settings().font_family, font_size: 12.5,
        syntax: { keyword: t.ansi5, string: t.ansi2, comment: t.dim, function: t.ansi4, type: t.ansi3, number: t.ansi1, constant: t.ansi6, punctuation: t.dim } });
      this.source.on("change", (_e, cx) => { this.text = this.source.value(); this.later(cx); cx.notify(); });
    }
    cx.notify();
  }

  key(e, cx) {
    const cmd = e.modifiers?.platform || e.modifiers?.control;
    if (cmd && e.key === "s") { this.seq = this.seq + 1; this.save(cx); cx.stop_propagation(); }
    else if (e.key === "escape" && this.active !== null) { this.close(); cx.notify(); cx.stop_propagation(); }
  }

  follow(url, cx) {
    const to = linkTarget(url, this.path);
    if (to?.web) { try { cx.open_url(to.web); } catch {} }
    else if (to?.file && this.onOpen) this.onOpen(to.file);
  }

  controls(t, prefix) {
    const state = this.on ? "Read only" : this.big ? "Too large to edit" : this.conflict ? "" : this.saving ? "Saving…" : this.dirty ? "Edited" : this.savedAt ? "Saved" : "";
    return [
      ...(state ? [div().text_size(11.5).text_color(t.dim).child(state)] : []),
      ...(this.canEdit ? [div().id(`${prefix}-source`).h(24).px(9).flex().items_center().rounded(6).cursor_pointer().text_size(12).font_medium()
        .when(Boolean(this.source), (el) => el.bg(t.selected).text_color(t.foreground))
        .when(!this.source, (el) => el.text_color(t.muted))
        .hover((s) => s.bg(t.hover).text_color(t.foreground))
        .tooltip(this.source ? "Back to the formatted document" : "Edit the whole file as Markdown")
        .on_click((_e, cx) => this.toggleSource(cx)).child(this.source ? "Formatted" : "Source")] : []),
    ];
  }

  body(t, id) {
    if (this.error) return div().p(16).text_color(t.dim).child(this.error);
    if (this.text === null) return readingLines(t);
    const conflict = this.conflict ? h_flex().flex_none().px(16).py(8).gap(8).items_center().border_b(1).border_color(t.border)
      .child(div().flex_1().min_w(0).text_size(12).text_color(t.blocked).child("The file changed on disk while you edited it."))
      .child(this.pill(`${id}-mine`, "Keep mine", t, (cx) => this.keepMine(cx), true))
      .child(this.pill(`${id}-theirs`, "Take the file's", t, (cx) => this.takeTheirs(cx))) : null;
    const main = this.source
      ? div().flex_1().min_h(0).px(6).py(4).child(Editor.new(this.source).size_full())
      : div().id(`${id}-scroll`).flex_1().min_h(0).overflow_y_scrollbar()
        .child(v_flex().flex_none().w_full().max_w(760).px(16).pt(14).pb(8).gap(10)
          .children(this.blocks.map((b, i) => this.block(b, i, t, id)).filter(Boolean)))
        .when(this.canEdit, (el) => el.child(div().id(`${id}-append`).flex_none().h(120).w_full()
          .on_mouse_down("left", (e, cx) => { if (e.click_count === 2) this.append(cx); })));
    return v_flex().flex_1().min_h(0).when(Boolean(conflict), (el) => el.child(conflict)).child(main);
  }

  pill(id, label, t, action, strong) {
    return div().id(id).h(24).px(9).flex().items_center().rounded(6).cursor_pointer().text_size(12).font_medium()
      .when(strong, (el) => el.bg(t.solid).text_color(t.solid_foreground).hover((s) => s.opacity(0.88)))
      .when(!strong, (el) => el.text_color(t.muted).hover((s) => s.bg(t.hover).text_color(t.foreground)))
      .on_click((_e, cx) => action(cx)).child(label);
  }

  block(b, i, t, id) {
    if (b.kind === "blank") return null;
    if (i === this.active && this.cells) return this.tableEditor(t, id);
    if (i === this.active && this.box) {
      const mono = b.kind === "code" || b.kind === "front";
      const size = b.kind === "heading" ? HEADING_SIZE[headingOf(b.lines[0]).level] : mono ? 12.5 : 13.5;
      return Textarea.new(this.box).w_full().px(8).py(6).rounded(6).border_1().border_color(t.input).bg(t.raised)
        .text_size(size).text_color(t.foreground).when(b.kind === "heading", (el) => el.font_semibold())
        .when(mono, (el) => el.font_family(settings().font_family));
    }
    const md = b.kind === "front" ? readable(b.lines.join("\n")) : b.lines.join("\n");
    const parts = this.on ? markdownParts(md) : null;
    return div().id(`${id}-b${i}`).w_full().px(8).py(2).rounded(6).text_size(13.5).text_color(t.foreground)
      .when(this.canEdit && !this.conflict, (el) => el.hover((s) => s.bg(t.hover))
        .on_mouse_down("left", (e, cx) => { if (e.click_count === 2) { this.open(i, cx); cx.stop_propagation(); } }))
      .child(parts?.some((part) => part.kind === "image") ? this.pictureBlock(parts, i, t, id) : TextView.markdown(`${id}-v${i}`, md).on_link_click((url, cx) => this.follow(url, cx)));
  }

  pictureBlock(parts, i, t, id) {
    return v_flex().w_full().gap(8).children(parts.map((part, k) => {
      if (part.kind === "text") return part.text.trim() ? TextView.markdown(`${id}-v${i}-${k}`, part.text).on_link_click((url, cx) => this.follow(url, cx)) : null;
      const file = linkTarget(part.url, this.path)?.file;
      const shot = file && this.shots?.has(file) ? this.shots.get(file) : undefined;
      if (shot === undefined) return breathe(div().id(`${id}-shot-${k}`)).child(skeleton({ border: t.border }).block(240, 140, 8));
      if (shot?.deferred) return h_flex().id(`${id}-shot-${k}`).gap(8).items_center()
        .child(div().text_size(12).text_color(t.foreground).child(paths.basename(file)))
        .child(div().text_size(12).text_color(t.dim).child(bytesLabel(shot.size)))
        .child(quietLink(`${id}-load-${k}`, "Load", (cx) => this.loadShot(file, cx), tokens(t)));
      if (!shot) return div().id(`${id}-shot-${k}`).text_size(12).text_color(t.dim).child("Cannot show this picture");
      return div().id(`${id}-shot-${k}`).w_full().child(image(shot).w_full());
    }).filter(Boolean));
  }

  pictures(cx) {
    const files = [...new Set(this.blocks.flatMap((b) => b.kind === "code" ? [] : markdownParts(b.lines.join("\n")).flatMap((part) => {
      if (part.kind !== "image") return [];
      const file = linkTarget(part.url, this.path)?.file;
      return file ? [file] : [];
    })))];
    const prior = this.shots ?? new Map();
    this.shots = new Map(files.map((file) => [file, prior.has(file) ? prior.get(file) : undefined]));
    this.shotSeq = (this.shotSeq ?? 0) + 1;
    const seq = this.shotSeq, path = this.path, on = this.on;
    cx.spawn(async (cx) => {
      await files.reduce(async (done, file) => {
        await done;
        if (this.shotSeq !== seq || this.path !== path) return;
        const shot = await bring(file, on).then((got) => got.deferred ? { deferred: true, size: got.size, file } : appRelative(got.path, appHome())).catch(() => null);
        if (this.shotSeq !== seq || this.path !== path) return;
        this.shots = new Map([...this.shots, [file, shot]]);
        cx.notify();
      }, Promise.resolve());
    });
  }

  loadShot(file, cx) {
    const seq = this.shotSeq, path = this.path, on = this.on;
    cx.spawn(async (cx) => {
      const shot = await bring(file, on, { ask: true }).then((got) => appRelative(got.path, appHome())).catch(() => null);
      if (this.shotSeq !== seq || this.path !== path) return;
      this.shots = new Map([...this.shots, [file, shot]]);
      cx.notify();
    });
  }

  tableEditor(t, id) {
    const { head, rows, table } = this.cells;
    const n = head.length;
    const icon = (key, tip, action) => div().id(key).size(20).flex_none().flex().items_center().justify_center().rounded(4).cursor_pointer()
      .text_color(t.dim).hover((s) => s.bg(t.hover).text_color(t.foreground)).tooltip(tip).on_click((_e, cx) => action(cx))
      .child(svg(`${this.icons}/close.svg`).size(11));
    const cell = (s, key, strong) => div().id(key).flex_1().min_w(96).border_r(1).border_color(t.border)
      .child(Textarea.new(s).w_full().px(8).py(5).text_size(12.5).text_color(t.foreground).when(strong, (el) => el.font_semibold()));
    const line = (cells, key, strong, end) => h_flex().id(key).w_full().items_start().border_b(1).border_color(t.border)
      .when(strong, (el) => el.bg(t.raised)).children(cells).child(div().w(26).flex_none().pt(4).flex().justify_center().child(end));
    const removeCol = h_flex().w_full().children(head.map((_s, c) => div().flex_1().min_w(96).flex().justify_center()
      .child(n > 1 ? icon(`${id}-col-x-${c}`, "Remove this column", (cx) => this.reshape((tb) => ({ ...tb, head: tb.head.toSpliced(c, 1), align: tb.align.toSpliced(c, 1), rows: tb.rows.map((r) => r.toSpliced(c, 1)) }), cx)) : div())))
      .child(div().w(26).flex_none());
    return v_flex().w_full().gap(6)
      .child(div().id(`${id}-grid`).w_full().overflow_x_scrollbar()
        .child(v_flex().flex_none().min_w(n * 96 + 26).child(removeCol)
          .child(v_flex().rounded(6).border_1().border_color(t.input).overflow_hidden()
            .child(line(head.map((s, c) => cell(s, `${id}-h${c}`, true)), `${id}-hrow`, true, div()))
            .children(rows.map((r, ri) => line(r.map((s, c) => cell(s, `${id}-c${ri}-${c}`)), `${id}-row${ri}`, false,
              icon(`${id}-row-x-${ri}`, "Remove this row", (cx) => this.reshape((tb) => ({ ...tb, rows: tb.rows.toSpliced(ri, 1) }), cx))))))))
      .child(h_flex().gap(6)
        .child(this.pill(`${id}-add-row`, "Add row", t, (cx) => this.reshape((tb) => ({ ...tb, rows: [...tb.rows, Array.from({ length: n }, () => "")] }), cx)))
        .child(this.pill(`${id}-add-col`, "Add column", t, (cx) => this.reshape((tb) => ({ ...tb, head: [...tb.head, ""], align: [...tb.align, null], rows: tb.rows.map((r) => [...r, ""]) }), cx)))
        .child(div().flex_1())
        .child(this.pill(`${id}-done`, "Done", t, (cx) => { this.close(); cx.notify(); })));
  }

  release() { this.close(); this.source?.release(); this.source = null; }
}

export const tildePath = (dir, on) => {
  const h = home();
  if (on) return `${on}: ${dir}`;
  return paths.shorten(dir, h);
};
