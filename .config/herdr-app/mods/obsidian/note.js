// The viewer pane: one note rendered as markdown, its [[links]] followed in place,
// with the notes that link to it underneath. Redraws when the file changes. Edit
// switches it to Herdr's editor in place; Send puts the note in an agent's prompt.
import { div, svg } from "gpui-kit";
import { v_flex, h_flex, TextView, EditorState, Editor } from "gpui-base";
import { focused, nextCommand, notify, props, readTextFile, setShared, settings, shared, spaces, theme, watchFolder, window, writeTextFile } from "herdr";
import * as vault from "./vault.js";
import * as agent from "./agent.js";

const ICON = (name) => `mods/obsidian/${name}.svg`;
// Wiki links become web links under a reserved host, the one kind of URL TextView
// is sure to hand to on_link_click unchanged; follow() catches them first.
const LINK = "https://obsidian-note.invalid/";
const IMAGE = /\.(png|jpe?g|gif|webp|svg|bmp)$/i;
const saveKey = () => (window()?.platform === "macos" ? "⌘S" : "Ctrl+S");

// Front matter out, Obsidian's own syntax turned into plain markdown.
export function toMarkdown(text) {
  let front = {};
  const fm = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  if (fm) {
    text = text.slice(fm[0].length);
    let key = null;
    for (const line of fm[1].split(/\r?\n/)) {
      const kv = line.match(/^([A-Za-z_][\w-]*):\s*(.*)$/);
      if (kv) { key = kv[1]; front[key] = kv[2].replace(/^\[|\]$/g, "").split(",").map((s) => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean); }
      else if (key && /^\s+-\s+/.test(line)) front[key].push(line.replace(/^\s+-\s+/, "").replace(/^["']|["']$/g, ""));
    }
  }
  const out = [];
  let fence = false;
  for (let line of text.split("\n")) {
    if (/^\s*(```|~~~)/.test(line)) { fence = !fence; out.push(line); continue; }
    if (fence) { out.push(line); continue; }
    line = line
      .replace(/%%.*?%%/g, "")
      .replace(/^(\s*>+\s*)\[!(\w+)\][+-]?\s*(.*)$/, (_m, q, type, rest) => `${q}**${type[0].toUpperCase()}${type.slice(1).toLowerCase()}${rest ? ": " + rest : ""}**\n${q.trimEnd()}`)
      .replace(/!\[\[([^\]]+)\]\]/g, (_m, target) => {
        const [name, alias] = target.split("|");
        return `[↳ ${alias || name}](${LINK}${encodeURIComponent(name)})`;
      })
      .replace(/\[\[([^\]]+)\]\]/g, (_m, target) => {
        const [name, alias] = target.split("|");
        const shown = alias || name.replace(/#\^?/, " › ");
        return `[${shown}](${LINK}${encodeURIComponent(name)})`;
      })
      .replace(/==([^=]+)==/g, "**$1**");
    out.push(line);
  }
  return { markdown: out.join("\n"), front };
}

export class Note {
  init(cx) {
    this.history = [];
    this.links = [];
    // Edit in place: `editor` holds the draft, `base` the file as it was when
    // editing started (the snapshot a save must still match), `dirty` whether the
    // draft differs from it. A draft outlives leaving edit mode until it's saved.
    this.editing = false;
    this.editor = null;
    this.base = null;
    this.dirty = false;
    this.conflict = false;
    // A mod pane isn't told its pane id, but a copy starts the first time its tab
    // shows, so the focused tab now is its own. The id survives a restart.
    this.tab = focused()?.tab ?? null;
    this.id = `${this.tab}|${props()?.note}`;
    this.show(props()?.note, cx);
    this.register();
    // Another view asks this tab's viewer to show a note through shared "obsidian.show".
    this.seen = shared("obsidian.show")?.n ?? 0;
    // Keys from the "mod:obsidian" section: save (cmd-s / ctrl-s). Every shown copy
    // gets them, so only a viewer that is editing acts.
    cx.spawn(async (cx) => {
      for (;;) {
        const c = await nextCommand();
        if (c === "save" && this.editing) await this.save(cx);
        else if (c === "view" && this.editing) this.leave();
        else continue;
        cx.notify();
      }
    });
  }

  // shared "obsidian.viewers": { id: tab }, so openers know a tab has a viewer.
  register() {
    if (!this.tab) return;
    const tabs = new Set(spaces().flatMap((s) => s.tabs.map((t) => t.id)));
    const all = Object.fromEntries(Object.entries(shared("obsidian.viewers") ?? {}).filter(([, tab]) => tabs.has(tab)));
    all[this.id] = this.tab;
    if (JSON.stringify(all) !== JSON.stringify(shared("obsidian.viewers") ?? {})) setShared("obsidian.viewers", all);
  }

  close() {
    const all = { ...(shared("obsidian.viewers") ?? {}) };
    delete all[this.id];
    setShared("obsidian.viewers", all);
  }

  show(rel, cx, back = false) {
    if (!rel) { this.error = "No note given"; return false; }
    // Moving to another note drops a clean draft and refuses to drop a dirty one.
    if (this.editor && rel !== this.path) {
      if (this.dirty) {
        notify({ title: "Unsaved edits", body: `Save or discard your edits to ${vault.title(this.path)} first`, level: "info", timeout: 3000 });
        return false;
      }
      this.drop();
    }
    if (this.path && !back && this.path !== rel) this.history.push(this.path);
    this.path = rel;
    this.raw = null;
    this.text = null; this.error = null; this.links = [];
    const gen = (this.gen = (this.gen ?? 0) + 1);
    cx.spawn(async (cx) => {
      await this.load(gen);
      cx.notify();
      try { this.links = await vault.backlinks(rel); } catch { this.links = []; }
      if (gen === this.gen) cx.notify();
    });
    cx.spawn(async (cx) => {
      // Obsidian rewrites .obsidian/ constantly; only this file matters.
      const { root } = await vault.config();
      const dir = `${root}/${vault.folderOf(rel)}`.replace(/\/$/, "");
      try {
        while (gen === this.gen) {
          const changed = await watchFolder(dir);
          if (gen !== this.gen) return;
          if (changed.some((p) => p === dir || p === root || p.endsWith(`/${rel}`))) { await this.load(gen); cx.notify(); }
        }
      } catch { /* not watchable: the content stays as loaded */ }
    });
    return true;
  }

  async load(gen) {
    try {
      const { root } = await vault.config();
      const text = await readTextFile(`${root}/${this.path}`);
      if (gen !== this.gen) return;
      if (text === null) { this.error = `${this.path} isn't there any more`; return; }
      if (text === this.raw) return;
      this.raw = text;
      const { markdown, front } = toMarkdown(text);
      this.text = markdown.trim() ? markdown : "_Empty note_";
      this.tags = [...(front.tags ?? []), ...(front.tag ?? [])].map((t) => t.replace(/^#/, ""));
      // The file changed under a draft. A clean draft follows it; a dirty one keeps
      // its snapshot, so its save is refused instead of overwriting the change.
      if (this.editor && !this.saving && text !== this.base) {
        if (this.dirty) this.conflict = true;
        else { this.base = text; this.editor.set_value(text); }
      }
    } catch (e) { this.error = String(e?.message ?? e); }
  }

  tick(cx) {
    this.register();
    const ask = shared("obsidian.show");
    if (ask && ask.n !== this.seen) {
      this.seen = ask.n;
      if (ask.tab === this.tab && ask.note !== this.path) this.show(ask.note, cx);
    }
  }

  // Runs in a spawned task: a click handler's cx is gone after the first await.
  async follow(url, cx) {
    try {
      const at = url.indexOf(LINK);
      if (at < 0 && /^(https?|mailto|obsidian):/i.test(url)) return vault.openUrl(url);
      const target = at >= 0 ? decodeURIComponent(url.slice(at + LINK.length)) : decodeURIComponent(url.replace(/^file:\/\//, ""));
      const rel = await vault.resolve(target, this.path);
      if (!rel) return notify({ title: `“${target.split("#")[0]}” doesn't exist yet`, body: "Create it from the search popup", level: "info", timeout: 3000 });
      if (!vault.isNote(rel) || IMAGE.test(rel)) return vault.open(rel);
      if (rel !== this.path) { this.show(rel, cx); cx.notify(); }
    } catch (e) { notify({ title: "Couldn't follow the link", body: String(e?.message ?? e), level: "error" }); }
  }

  // ---- Edit in place ----------------------------------------------------------------

  // Called from a click: EditorState needs a live host call.
  edit() {
    if (this.raw === null || this.raw === undefined) return;
    if (!this.editor) {
      const t = theme();
      this.base = this.raw;
      this.dirty = false;
      this.conflict = false;
      this.editor = EditorState.new({
        language: "markdown", value: this.raw, soft_wrap: true, line_numbers: false, folding: false,
        font_family: settings().font_family, font_size: 13,
        syntax: { keyword: t.ansi5, string: t.ansi2, comment: t.dim, function: t.ansi4, type: t.ansi3, number: t.ansi1, constant: t.ansi6, punctuation: t.muted },
      });
      this.editor.on("change", (_e, cx) => {
        const dirty = this.editor?.value() !== this.base;
        if (dirty !== this.dirty) { this.dirty = dirty; cx.notify(); }
      });
    }
    this.editing = true;
  }

  // Back to the rendered note. A dirty draft is kept for the next Edit.
  leave() {
    this.editing = false;
    if (!this.dirty) this.drop();
  }

  drop() {
    this.editor?.release();
    this.editor = null; this.base = null;
    this.editing = false; this.dirty = false; this.conflict = false;
  }

  // The draft goes back to the file as it is on disk now.
  discard(cx) {
    cx.spawn(async (cx) => {
      const { root } = await vault.config();
      const now = await readTextFile(`${root}/${this.path}`);
      if (now === null || !this.editor) return;
      this.base = now;
      this.editor.set_value(now);
      this.dirty = false; this.conflict = false;
      cx.notify();
    });
  }

  // Writes the draft only if the file still holds what editing started from.
  async save(cx) {
    if (!this.editor || this.saving) return;
    const text = this.editor.value();
    if (text === this.base) { this.dirty = false; return; }
    this.saving = true;
    const { root } = await vault.config();
    const abs = `${root}/${this.path}`;
    try {
      await writeTextFile(abs, text, this.base);
      this.base = text; this.dirty = false; this.conflict = false;
      notify({ title: "Saved", body: vault.title(this.path), level: "success", timeout: 1500 });
    } catch (e) {
      const now = await readTextFile(abs).catch(() => null);
      if (now !== this.base) {
        this.conflict = true;
        notify({ title: "Not saved", body: `${vault.title(this.path)} changed on disk since you started editing`, level: "error", timeout: 5000 });
      } else notify({ title: "Couldn't save", body: String(e?.message ?? e), level: "error" });
    } finally {
      this.saving = false;
      await this.load(this.gen);
      cx.notify();
    }
  }

  key(e, cx) {
    if (!this.editing) return;
    if (e.key === "escape") this.leave();
    else if (e.key === "s" && (e.modifiers.platform || e.modifiers.control) && !e.modifiers.shift && !e.modifiers.alt) cx.spawn((cx) => this.save(cx));
    else return;
    cx.stop_propagation();
    cx.notify();
  }

  // What Send puts in the agent's prompt: the draft while editing, else the file.
  send(cx) {
    const body = this.editing && this.editor ? this.editor.value() : this.raw;
    if (body === null || body === undefined) return;
    const path = this.path;
    cx.spawn((cx) => agent.sendNote(path, body, cx));
  }

  button(id, icon, label, onClick, tone) {
    const t = theme();
    return h_flex().id(id).h(24).px(7).gap(5).items_center().rounded(6).cursor_pointer().text_size(12).text_color(tone ?? t.muted)
      .hover((s) => s.bg(t.hover).text_color(tone ?? t.foreground))
      .on_click((_e, cx) => { onClick(cx); cx.notify(); })
      .child(svg(ICON(icon)).size(13))
      .when(Boolean(label), (el) => el.child(label));
  }

  render(cx) {
    this.tick(cx);
    const t = theme(), path = this.path ?? "";
    const editing = this.editing && this.editor;
    const header = h_flex().h(36).flex_none().px(8).gap(4).items_center().border_b_1().border_color(t.border).bg(t.chrome)
      .when(this.history.length > 0 && !editing, (el) => el.child(this.button("back", "chevron-left", null, (cx) => { if (this.show(this.history[this.history.length - 1], cx, true)) this.history.pop(); })))
      .child(svg(ICON(editing ? "pencil" : "file-text")).size(14).flex_none().ml(4).text_color(t.accent))
      .child(div().flex_none().max_w(320).truncate().text_size(13).font_semibold().text_color(t.foreground).child(vault.title(path)))
      .child(div().flex_1().min_w(0).truncate().text_size(12).text_color(t.dim).child(
        editing ? (this.dirty ? `edited · ${saveKey()} saves · Esc views` : "editing · Esc views") : this.editor && this.dirty ? "unsaved edits" : vault.folderOf(path)))
      .child(this.button("send", "send", "Send", (cx) => this.send(cx)))
      .when(Boolean(editing), (el) => el
        .when(this.dirty, (el) => el
          .child(this.button("revert", "undo", "Revert", (cx) => this.discard(cx)))
          .child(this.button("save", "save", "Save", (cx) => cx.spawn((cx) => this.save(cx)), t.accent)))
        .child(this.button("view", "eye", "View", () => this.leave())))
      .when(!editing, (el) => el.child(this.button("edit", "pencil", this.dirty ? "Edit •" : "Edit", () => this.edit())))
      .child(this.button("editor", "square-pen", "Editor", () => vault.open(path, "editor")))
      .child(this.button("app", "external", "Obsidian", () => vault.open(path, "obsidian")));
    if (editing) {
      const banner = this.conflict
        ? h_flex().flex_none().px(12).py(7).gap(10).items_center().bg(t.raised).border_b_1().border_color(t.border).text_size(12.5)
            .child(div().flex_1().min_w(0).text_color(t.blocked).child("This note changed on disk since you started editing. Saving is refused so the change isn't lost."))
            .child(this.button("reload", "file-text", "Load disk version", (cx) => this.discard(cx)))
        : null;
      return v_flex().id("obsidian-note").size_full().min_h(0).bg(t.background)
        .on_key_down((e, cx) => this.key(e, cx))
        .child(header)
        .when(Boolean(banner), (el) => el.child(banner))
        .child(div().flex_1().min_h(0).px(10).py(6).child(Editor.new(this.editor).size_full()));
    }
    const tags = (this.tags ?? []).length
      ? h_flex().flex_wrap().gap(6).children(this.tags.map((tag) =>
          div().px(7).py(1).rounded(10).bg(t.raised).text_size(11.5).text_color(t.accent).child(`#${tag}`)))
      : null;
    const links = this.links.length
      ? v_flex().gap(2).pt(14).mt(10).border_t_1().border_color(t.border)
          .child(div().pb(4).text_size(11.5).font_semibold().text_color(t.muted).child(`LINKED FROM  ${this.links.length}`))
          .children(this.links.slice(0, 50).map((p) =>
            h_flex().id(`bl-${p}`).h(26).px(6).gap(8).items_center().rounded(6).cursor_pointer()
              .hover((s) => s.bg(t.hover))
              .on_click((_e, cx) => { this.show(p, cx); cx.notify(); })
              .child(svg(ICON("file-text")).size(13).flex_none().text_color(t.dim))
              .child(div().flex_1().min_w(0).truncate().text_size(12.5).text_color(t.foreground).child(vault.title(p)))
              .child(div().flex_none().max_w(200).truncate().text_size(11.5).text_color(t.dim).child(vault.folderOf(p)))))
      : null;
    const body = this.error
      ? div().p(16).text_color(t.blocked).child(this.error)
      : this.text === null
        ? div().p(16).text_color(t.muted).child("Loading…")
        : v_flex().id("note-scroll").flex_1().min_h(0).overflow_y_scrollbar().px(22).py(16).gap(10)
            .when(Boolean(tags), (el) => el.child(tags))
            .child(TextView.markdown(`note-${this.gen}`, this.text).selectable(true).text_size(14).text_color(t.foreground)
              .on_link_click((url, cx) => cx.spawn((cx) => this.follow(url, cx))))
            .when(Boolean(links), (el) => el.child(links));
    return v_flex().id("obsidian-note").size_full().min_h(0).bg(t.background).child(header).child(body);
  }
}
