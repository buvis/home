// The side panel: the vault's name, Search and Today, the notes changed last, and
// the vault's folders as a tree. Follows the vault on disk.
import { div, svg } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { nextCommand, notify, run, theme, watchFolder } from "herdr";
import * as vault from "./vault.js";

const ICON = (name) => `mods/obsidian/${name}.svg`;
const RECENT = 8;
const ROW = 26;

const remember = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
const keep = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} };

// { folders: Map<path, {folders: string[], notes: string[]}> } from a flat list.
function tree(list) {
  const folders = new Map([["", { folders: new Set(), notes: [] }]]);
  const folder = (p) => {
    if (!folders.has(p)) {
      folders.set(p, { folders: new Set(), notes: [] });
      folder(vault.folderOf(p)).folders.add(p);
    }
    return folders.get(p);
  };
  for (const p of list) folder(vault.folderOf(p)).notes.push(p);
  for (const f of folders.values()) {
    f.folders = [...f.folders].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
    f.notes.sort((a, b) => vault.title(a).localeCompare(vault.title(b), undefined, { sensitivity: "base", numeric: true }));
  }
  return folders;
}

export class Panel {
  init(cx) {
    this.list = null;
    this.open = new Set(remember("open", []));
    this.recentOpen = remember("recent", true);
    this.at = -1;
    this.handle = cx.focus_handle();
    this.reload(cx, true);
    cx.spawn(async (cx) => {
      for (;;) {
        const c = await nextCommand();
        if (c === "focus") { this.handle.focus(); if (this.at < 0) this.at = 0; cx.notify(); }
      }
    });
  }

  reload(cx, first = false) {
    cx.spawn(async (cx) => {
      try {
        const c = await vault.config();
        this.name = c.name;
        this.list = await vault.notes(true);
        this.folders = tree(this.list);
        this.error = null;
        if (first) this.watch(c.root, cx);
      } catch (e) { this.error = String(e?.message ?? e); }
      cx.notify();
    });
  }

  // Obsidian writes .obsidian/ all the time; only notes changing counts.
  watch(root, cx) {
    cx.spawn(async (cx) => {
      try {
        for (;;) {
          const changed = await watchFolder(root);
          const real = changed.some((p) => p === root || (!/\/\.(obsidian|git|trash)(\/|$)/.test(p) && /\.md$|\/[^./]+$/i.test(p)));
          if (!real) continue;
          const n = (this.n = (this.n ?? 0) + 1);
          cx.timer.after(400, (cx) => { if (n === this.n) this.reload(cx); });
        }
      } catch {
        cx.timer.every(15000, (cx) => this.reload(cx));
      }
    });
  }

  toggle(path) {
    this.open.has(path) ? this.open.delete(path) : this.open.add(path);
    keep("open", [...this.open]);
  }

  // Everything shown, in order, for drawing and for the keyboard.
  rows() {
    const out = [];
    out.push({ kind: "section", id: "recent", label: "Recent", open: this.recentOpen });
    if (this.recentOpen) for (const p of (this.list ?? []).slice(0, RECENT)) out.push({ kind: "note", id: `r:${p}`, path: p, depth: 0, recent: true });
    out.push({ kind: "section", id: "files", label: "Files", count: this.list?.length });
    const walk = (folder, depth) => {
      const f = this.folders?.get(folder);
      if (!f) return;
      for (const sub of f.folders) {
        const open = this.open.has(sub);
        out.push({ kind: "folder", id: `f:${sub}`, path: sub, depth, open });
        if (open) walk(sub, depth + 1);
      }
      for (const p of f.notes) out.push({ kind: "note", id: `n:${p}`, path: p, depth });
    };
    walk("", 0);
    return out;
  }

  activate(row, how = "viewer") {
    if (!row) return;
    if (row.kind === "section") {
      if (row.id === "recent") { this.recentOpen = !this.recentOpen; keep("recent", this.recentOpen); }
    } else if (row.kind === "folder") this.toggle(row.path);
    else vault.open(row.path, how);
  }

  key(e, cx) {
    const rows = this.rows();
    const row = rows[this.at];
    if (e.key === "down" || e.keystroke === "ctrl-j") this.at = Math.min(rows.length - 1, this.at + 1);
    else if (e.key === "up" || e.keystroke === "ctrl-k") this.at = Math.max(0, this.at - 1);
    else if (e.key === "enter") this.activate(row, e.modifiers.platform || e.modifiers.control ? "obsidian" : e.modifiers.shift ? "editor" : "viewer");
    else if (e.key === "right" && row?.kind === "folder" && !row.open) this.toggle(row.path);
    else if (e.key === "left" && row?.kind === "folder" && row.open) this.toggle(row.path);
    else if (e.key === "left" && row?.depth > 0) {
      const parent = vault.folderOf(row.path.replace(/^[rnf]:/, ""));
      const target = row.kind === "folder" ? vault.folderOf(row.path) : parent;
      const i = rows.findIndex((r) => r.kind === "folder" && r.path === target);
      if (i >= 0) this.at = i;
    } else if (e.key === "escape") return run("pane.go", { direction: "left" });
    else return;
    cx.stop_propagation();
    cx.notify();
  }

  async today() {
    try { vault.open(await vault.today()); }
    catch (e) { notify({ title: "Couldn't open today's note", body: String(e?.message ?? e), level: "error" }); }
  }

  render() {
    const t = theme();
    const button = (id, icon, label, onClick) => h_flex().id(id).h(26).px(8).gap(6).items_center().rounded(6).cursor_pointer()
      .border_1().border_color(t.border).text_size(12).text_color(t.muted)
      .hover((s) => s.bg(t.hover).text_color(t.foreground))
      .on_click(() => onClick())
      .child(svg(ICON(icon)).size(13)).child(label);
    const header = v_flex().flex_none().px(12).pt(10).pb(8).gap(8).border_b_1().border_color(t.border)
      .child(h_flex().items_center().gap(6)
        .child(div().flex_1().min_w(0).truncate().text_size(13).font_semibold().text_color(t.foreground).child(this.name ?? "Obsidian")))
      .child(h_flex().gap(6)
        .child(button("search", "search", "Search", () => run("mod.open", { name: "obsidian" })))
        .child(button("today", "calendar", "Today", () => this.today())));
    if (this.error) return v_flex().size_full().bg(t.chrome).child(header).child(div().p(12).text_size(12.5).text_color(t.blocked).child(this.error));
    if (this.list === null) return v_flex().size_full().bg(t.chrome).child(header).child(div().p(12).text_size(12.5).text_color(t.muted).child("Loading…"));
    const rows = this.rows();
    return v_flex().id("obsidian-panel").size_full().min_h(0).bg(t.chrome).text_size(12.5)
      .track_focus(this.handle).on_key_down((e, cx) => this.key(e, cx))
      .child(header)
      .child(v_flex().id("panel-scroll").flex_1().min_h(0).overflow_y_scrollbar().py(6).px(6)
        .children(rows.map((row, i) => {
          const base = h_flex().id(row.id).h(ROW).flex_none().gap(6).items_center().rounded(6).cursor_pointer()
            .pl(8 + row.depth * 14 || 8).pr(8)
            .when(i === this.at && this.handle.is_focused?.(), (el) => el.bg(t.selected))
            .hover((s) => s.bg(t.hover))
            .on_click((e, cx) => { this.at = i; this.activate(row, e.modifiers.platform || e.modifiers.control ? "obsidian" : e.modifiers.shift ? "editor" : "viewer"); cx.notify(); });
          if (row.kind === "section") {
            return base.mt(i ? 8 : 0)
              .child(svg(ICON(row.id === "files" || row.open ? "chevron-down" : "chevron-right")).size(12).flex_none().text_color(t.dim))
              .child(div().flex_1().text_size(11).font_semibold().text_color(t.muted).child(row.label.toUpperCase()))
              .child(div().text_size(11).text_color(t.dim).child(row.count != null ? String(row.count) : ""));
          }
          if (row.kind === "folder") {
            return base
              .child(svg(ICON(row.open ? "chevron-down" : "chevron-right")).size(12).flex_none().text_color(t.dim))
              .child(svg(ICON("folder")).size(13).flex_none().text_color(t.muted))
              .child(div().flex_1().min_w(0).truncate().text_color(t.foreground).child(row.path.split("/").pop()));
          }
          return base
            .child(div().w(12).flex_none())
            .child(svg(ICON(row.recent ? "clock" : "file-text")).size(13).flex_none().text_color(t.dim))
            .child(div().flex_1().min_w(0).truncate().text_color(t.foreground).child(vault.title(row.path)))
            .when(Boolean(row.recent), (el) => el.child(div().flex_none().max_w(110).truncate().text_size(11).text_color(t.dim).child(vault.folderOf(row.path))));
        })));
  }
}
