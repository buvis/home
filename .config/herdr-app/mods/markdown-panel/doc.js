import { serviceOn } from "./platform-host.js";
import { paths } from "./platform-paths.js";
import { fileApi } from "./platform-files.js";
import { div, image } from "gpui-kit";
import { v_flex, h_flex, Editor, EditorState, Textarea, TextareaState } from "gpui-base";
import { readTextFile, writeTextFile, theme, settings, home, appHome } from "herdr";
import { parseBlocks, joinBlocks, headingOf, headingLine, parseTable, tableLines } from "./blocks.js";
import { G, H, R, T, W, tokens } from "./ui.js";
import { button } from "./ui-button.js";
import { button as kitButton, skeletonOf, tooltip, emptyState, failureLine, markdownBlock, markdownWords, row } from "./kit.js";
import { bring, appRelative, markdownParts, staleView, bytesLabel, copyFailure, quietError } from "./remote-file.js";
import { EDIT_LIMIT, drafts, draftKey, remember, opened, restore, seenDisk, typed, beginSave, commitText, applied, word, didFail, keepMine, takeTheirs, tooLarge, wholeText, overRead } from "./edit.js";

// Where text is about to be: a preview's few lines, a Markdown document's more.
export const readingLines = (t, count = 4) => v_flex().w_full().px(G.lg).pt(G.md).child(skeletonOf({ shape: "line", count })("kanso-skeleton", t));

const AUTOSAVE_MS = 700;
// A heading being edited, by its level: the Storybook's heading and subheading, then the body.
const HEADING_SIZE = [undefined, T.page, T.title];

// Front matter shown as a code block, so it reads as data instead of running into the first paragraph.
export function readable(text) {
  const m = /^-{3}\r?\n([\s\S]*?)\r?\n-{3}[ \t]*(\r?\n|$)/.exec(text);
  const body = m ? "```yaml\n" + m[1] + "\n```\n\n" + text.slice(m[0].length) : text;
  return body.length > EDIT_LIMIT ? body.slice(0, EDIT_LIMIT) + "\n\n… (file truncated)" : body;
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
    this.phase = "clean"; this.disk = null; this.note = null; this.seq = 0;
    this.error = null; this.big = false; this.shots = new Map(); this.shotSeq = 0;
  }

  get canEdit() { return this.saved !== null && !this.big; }
  get dirty() { return this.text !== null && this.text !== this.saved; }
  get conflict() { return this.phase === "conflict"; }
  get saving() { return this.phase === "saving"; }
  get editing() { return this.active !== null || Boolean(this.source); }

  snapshot() {
    return { saved: this.saved, text: this.text, phase: this.phase, disk: this.disk ?? null, note: this.note ?? null, big: Boolean(this.big) };
  }

  apply(next) {
    if (!next) return;
    this.saved = next.saved; this.text = next.text; this.phase = next.phase;
    this.disk = next.disk; this.note = next.note; this.big = next.big;
  }

  remember() { remember(drafts, draftKey(this.path, this.on), this.snapshot()); }

  dropDraft() {
    drafts.drop(draftKey(this.path, this.on));
    if (this.saved == null) return;
    this.apply(opened(this.saved));
    this.setText(this.saved);
  }

  load(cx) {
    const path = this.path;
    cx.spawn(async (cx) => {
      const draft = this.saved === null && this.text === null ? drafts.peek(draftKey(path, this.on)) : null;
      try {
        const got = await readWhole(path, this.on);
        if (this.path !== path) return;
        if (got.big) { this.error = null; this.keep(tooLarge()); return; }
        const text = got.text;
        if (text == null) {
          if (draft) { this.keep(didFail(restore(draft), "This file is no longer available")); return; }
          this.miss("This file is no longer available"); return;
        }
        if (String(text).includes("\0")) { this.miss("Binary file: nothing to show"); return; }
        this.error = null; this.held = null; this.fresh = Date.now();
        const base = this.text !== null || this.saved !== null ? this.snapshot() : (draft ? restore(draft) : null);
        const next = base ? seenDisk(base, text) : opened(text);
        this.keep(next);
        if (this.on && next.phase !== "conflict") this.pictures(cx);
      } catch (e) {
        if (this.path !== path) return;
        const note = this.on ? copyFailure(e, this.on) : `Cannot read this file: ${e?.message ?? e}`;
        const held = draft ?? (this.dirty ? { text: this.text, saved: this.saved } : null);
        if (held) this.keep(didFail(restore(held), note));
        else this.miss(note);
      } finally { cx.notify(); }
    });
  }

  keep(next) {
    if (next.big) {
      this.apply(next);
      this.close();
      if (this.source) { this.source.release(); this.source = null; }
      this.text = null;
      this.blocks = [];
      this.remember();
      return;
    }
    const same = next.text === this.text && this.blocks.length > 0;
    this.apply(next);
    if (!same) this.setText(next.text);
    this.remember();
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
    if (this.source) this.source.set_value(text);
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
    this.apply(typed(this.snapshot(), joinBlocks(this.blocks)));
    this.remember();
    this.later(cx);
    cx.notify();
  }

  later(cx) {
    if (this.on || this.phase === "failed" || this.phase === "conflict" || this.phase === "saving" || this.big || this.text === this.saved) return;
    const seq = this.seq + 1;
    this.seq = seq;
    cx.timer.after(AUTOSAVE_MS, (cx) => { if (seq === this.seq && this.phase !== "failed" && this.phase !== "conflict") this.save(cx); });
  }

  async settle(saving, path) {
    const outcome = await commitText(saving, textIo(path, this.on));
    const next = applied(this.path === path ? this.snapshot() : saving, outcome.written, outcome.result);
    if (this.path === path) {
      this.apply(next);
      if (this.phase === "saved") this.savedAt = Date.now();
    }
    remember(drafts, draftKey(path, this.on), next);
    return next;
  }

  save(cx) {
    const saving = beginSave(this.snapshot());
    if (!saving) return;
    this.seq = this.seq + 1;
    this.apply(saving);
    cx.notify();
    const path = this.path;
    cx.spawn(async (cx) => {
      await this.settle(saving, path);
      if (this.path === path && this.dirty && this.phase !== "conflict" && this.phase !== "failed") this.later(cx);
      cx.notify();
    });
  }

  // The draft stays when the write cannot finish, and the panel may move on.
  async flush() {
    this.seq = this.seq + 1;
    this.remember();
    const saving = beginSave(this.snapshot());
    if (!saving) return true;
    this.apply(saving);
    await this.settle(saving, this.path);
    return true;
  }

  keepMine(cx) {
    const next = keepMine(this.snapshot());
    if (next.phase === "conflict") return;
    this.apply(next);
    this.save(cx);
  }

  takeTheirs(cx) {
    if (!this.conflict) return;
    const next = takeTheirs(this.snapshot());
    this.apply(next);
    this.setText(next.text);
    this.remember();
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
      this.source.on("change", (_e, cx) => { this.apply(typed(this.snapshot(), this.source.value())); this.remember(); this.later(cx); cx.notify(); });
    }
    cx.notify();
  }

  key(e, cx) {
    if (e.key === "escape" && this.active !== null) { this.close(); cx.notify(); cx.stop_propagation(); }
  }

  follow(url, cx) {
    const to = linkTarget(url, this.path);
    if (to?.web) { try { cx.open_url(to.web); } catch {} }
    else if (to?.file && this.onOpen) this.onOpen(to.file);
  }

  controls(t, prefix) {
    const state = word(this.snapshot()), c = tokens(t);
    return [
      ...(state ? [div().text_size(T.body).text_color(c.dim).child(state)] : []),
      ...(this.canEdit ? [button(`${prefix}-source`, this.source ? "Formatted" : "Source", (cx) => this.toggleSource(cx), c, { kind: "quiet", small: true, active: Boolean(this.source), color: this.source ? null : c.muted })
        .tooltip(tooltip({ label: this.source ? "Back to the formatted document" : "Edit the whole file as Markdown" }))] : []),
    ];
  }

  body(t, id) {
    const c = tokens(t);
    if (this.big) return emptyState({ text: "Too large to edit" })(`${id}-big`, c);
    if (this.error) return failureLine({ text: this.error })(`${id}-error`, c);
    if (this.text === null) return readingLines(t, 6);
    const conflict = this.conflict ? conflictBar(id, t, (cx) => this.keepMine(cx), (cx) => this.takeTheirs(cx)) : null;
    const main = this.source
      ? div().flex_1().min_h(0).p(G.xs).child(Editor.new(this.source).size_full())
      : div().id(`${id}-scroll`).flex_1().min_h(0).overflow_y_scrollbar()
        .child(v_flex().flex_none().w_full().max_w(W.prose).px(G.sm).pt(G.md).pb(G.sm).gap(G.xs)
          .children(this.blocks.map((b, i) => this.block(b, i, c, id)).filter(Boolean)))
        .when(this.canEdit, (el) => el.child(h_flex().flex_none().w_full().max_w(W.prose).px(G.sm)
          .child(button(`${id}-add`, "Add paragraph", (cx) => this.append(cx), c, { kind: "quiet", small: true, icon: "plus", disabled: this.conflict })))
          .child(div().id(`${id}-append`).flex_none().h(H.append).w_full()
            .on_mouse_down("left", (e, cx) => { if (e.click_count === 2) this.append(cx); })));
    return v_flex().flex_1().min_h(0).when(Boolean(conflict), (el) => el.child(conflict)).child(main);
  }

  // A link's press: the web, or a file beside the document.
  links() { return { onLink: (url, cx) => this.follow(url, cx) }; }

  block(b, i, c, id) {
    if (b.kind === "blank") return null;
    const key = `${id}-b${i}`;
    if (i === this.active && this.cells) return markdownBlock({ state: "editing", content: [this.tableEditor(c, id)] })(key, c);
    if (i === this.active && this.box) {
      const mono = b.kind === "code" || b.kind === "front";
      const level = b.kind === "heading" ? headingOf(b.lines[0]).level : 0;
      const field = Textarea.new(this.box).w_full().text_size(HEADING_SIZE[level] ?? (mono ? T.value : T.card)).text_color(c.text)
        .when(level > 0, (el) => el.font_semibold()).when(mono, (el) => el.font_family(settings().font_family));
      return markdownBlock({ state: "editing", content: [field] })(key, c);
    }
    const md = b.kind === "front" ? readable(b.lines.join("\n")) : b.lines.join("\n");
    const parts = this.on ? markdownParts(md) : null;
    const editable = this.canEdit && !this.conflict;
    const press = (e, cx) => { if (e.click_count === 2) { this.open(i, cx); cx.stop_propagation(); } };
    const content = parts?.some((part) => part.kind === "image") ? this.pictureParts(parts, key, c) : [];
    return markdownBlock({ source: md, content })(key, c, { ...this.links(), onPress: editable ? press : undefined, onOpen: editable ? (cx) => this.open(i, cx) : undefined });
  }

  // A block with pictures: its words drawn by the kit, each picture loading, waiting for Load, failed or drawn.
  pictureParts(parts, key, c) {
    return parts.map((part, k) => {
      const at = `${key}-${k}`;
      if (part.kind === "text") return part.text.trim() ? markdownWords({ source: part.text })(at, c, this.links()) : null;
      const file = linkTarget(part.url, this.path)?.file;
      const shot = file && this.shots?.has(file) ? this.shots.get(file) : undefined;
      if (shot === undefined) return skeletonOf({ shape: "picture" })(at, c);
      if (shot?.deferred) return row({ name: paths.basename(file), meta: bytesLabel(shot.size), action: { kind: "quiet", label: "Load" } })(at, c, { on: { Load: (cx) => this.loadShot(file, cx) } });
      if (!shot) return failureLine({ text: "Cannot show this picture" })(at, c);
      return image(shot).w_full();
    }).filter(Boolean);
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
    this.shotTask(cx, async (cx, { seq, path, on }) => {
      await files.reduce(async (done, file) => {
        await done;
        if (this.shotSeq !== seq || this.path !== path) return;
        const shot = await bring(file, on).then((got) => got.deferred ? { deferred: true, size: got.size, file } : appRelative(got.path, appHome())).catch(() => null);
        this.keepShot(file, shot, seq, path, cx);
      }, Promise.resolve());
    });
  }

  shotTask(cx, work) {
    const address = { seq: this.shotSeq, path: this.path, on: this.on };
    cx.spawn((next) => work(next, address));
  }

  keepShot(file, shot, seq, path, cx) {
    if (this.shotSeq !== seq || this.path !== path) return;
    this.shots = new Map([...this.shots, [file, shot]]);
    cx.notify();
  }

  loadShot(file, cx) {
    this.shotTask(cx, async (cx, { seq, path, on }) => {
      const shot = await bring(file, on, { ask: true }).then((got) => appRelative(got.path, appHome())).catch(() => null);
      this.keepShot(file, shot, seq, path, cx);
    });
  }

  tableEditor(c, id) {
    const { head, rows } = this.cells;
    const n = head.length;
    const quiet = { kind: "quiet", small: true, color: c.muted };
    // The kit's small icon button: its tip is its label, Tab reaches it, Enter and Space press it.
    const icon = (key, tip, action) => kitButton({ label: tip, kind: "icon", size: "sm", icon: `${this.icons}/x.svg` })(key, c, { onClick: action });
    const cell = (s, key, strong) => div().id(key).flex_1().min_w(W.tableCell).border_r(1).border_color(c.border)
      .child(Textarea.new(s).w_full().px(G.sm).py(G.xs).text_size(T.value).text_color(c.text).when(strong, (el) => el.font_semibold()));
    const line = (cells, key, strong, end) => h_flex().id(key).w_full().items_start().border_b(1).border_color(c.border)
      .when(strong, (el) => el.bg(c.raised)).children(cells).child(div().w(H.icon).flex_none().pt(G.xs).flex().justify_center().child(end));
    const removeCol = h_flex().w_full().children(head.map((_s, col) => div().flex_1().min_w(W.tableCell).flex().justify_center()
      .child(n > 1 ? icon(`${id}-col-x-${col}`, "Remove this column", (cx) => this.reshape((tb) => ({ ...tb, head: tb.head.toSpliced(col, 1), align: tb.align.toSpliced(col, 1), rows: tb.rows.map((r) => r.toSpliced(col, 1)) }), cx)) : div())))
      .child(div().w(H.icon).flex_none());
    return v_flex().w_full().gap(G.xs)
      .child(div().id(`${id}-grid`).w_full().overflow_x_scrollbar()
        .child(v_flex().flex_none().min_w(n * W.tableCell + H.icon).child(removeCol)
          .child(v_flex().rounded(R.control).border_1().border_color(c.input).overflow_hidden()
            .child(line(head.map((s, col) => cell(s, `${id}-h${col}`, true)), `${id}-hrow`, true, div()))
            .children(rows.map((r, ri) => line(r.map((s, col) => cell(s, `${id}-c${ri}-${col}`)), `${id}-row${ri}`, false,
              icon(`${id}-row-x-${ri}`, "Remove this row", (cx) => this.reshape((tb) => ({ ...tb, rows: tb.rows.toSpliced(ri, 1) }), cx))))))))
      .child(h_flex().gap(G.xs)
        .child(button(`${id}-add-row`, "Add row", (cx) => this.reshape((tb) => ({ ...tb, rows: [...tb.rows, Array.from({ length: n }, () => "")] }), cx), c, quiet))
        .child(button(`${id}-add-col`, "Add column", (cx) => this.reshape((tb) => ({ ...tb, head: [...tb.head, ""], align: [...tb.align, null], rows: tb.rows.map((r) => [...r, ""]) }), cx), c, quiet))
        .child(div().flex_1())
        .child(button(`${id}-done`, "Done", (cx) => { this.close(); cx.notify(); }, c, quiet)));
  }

  release() { this.close(); this.source?.release(); this.source = null; }
}

export async function readWhole(path, on) {
  if (!on) {
    try { return wholeText(null, await readTextFile(path)); }
    catch (error) { if (overRead(error)) return { big: true }; throw error; }
  }
  const api = await serviceOn(fileApi, on);
  const info = await api.stat(path);
  const size = Number(info.size);
  if (size > EDIT_LIMIT) return { big: true };
  return wholeText(size, await api.read(path, EDIT_LIMIT));
}

export const textIo = (path, on) => ({
  put: async (text, expected) => on ? (await serviceOn(fileApi, on)).write(path, text, expected) : writeTextFile(path, text, expected),
  read: async () => {
    const got = await readWhole(path, on);
    if (got.big) throw new Error("Text file exceeds 1 MiB");
    return got.text;
  },
  quiet: quietError,
  note: (error) => on ? copyFailure(error, on) : (quietError(error) ? "This computer did not answer" : "Could not save"),
});

export function conflictBar(id, t, onMine, onTheirs) {
  const c = tokens(t);
  return h_flex().flex_none().px(G.lg).py(G.sm).gap(G.sm).items_center().border_b(1).border_color(c.border)
    .child(div().flex_1().min_w(0).text_size(T.body).text_color(c.blocked).child("The file changed on disk while you edited it."))
    .child(button(`${id}-mine`, "Keep mine", onMine, c, { small: true }))
    .child(button(`${id}-theirs`, "Take the file's", onTheirs, c, { kind: "tonal", small: true }));
}

export const tildePath = (dir, on) => {
  const h = home();
  if (on) return `${on}: ${dir}`;
  return paths.shorten(dir, h);
};
