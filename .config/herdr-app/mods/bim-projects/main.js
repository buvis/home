// bim-projects: search the bim vault's project notes and run the GTD consistency checks
// that were spread over dataview notes (20250121091528 "Check BIM consistency" and friends).
import { View, div } from "gpui-kit";
import { v_flex, h_flex, InputState, Input, Scrollbar } from "gpui-base";
import { exec, readTextFile, writeTextFile, watchFolder, home, theme, run, nextCommand, notify } from "herdr";
import * as fs from "fs/promises";
import { parseNote, check, KINDS, SOFT, localDate, completeNote, parkNote, rescheduleNote } from "./check.js";

const VAULT = `${home()}/bim`;

export default class Projects extends View {
  init(_props, cx) {
    this.projects = []; this.q = ""; this.kind = null; this.openOnly = true; this.selected = null; this.width = 0; this.height = 0; this.typing = false;
    this.handle = cx.focus_handle();
    this.input = InputState.new({ placeholder: "Search title, tags, text" });
    this.input.on("change", (_e, cx) => { this.q = this.input.value().toLowerCase(); cx.notify(); });
    this.input.on("focus", (_e, cx) => { this.typing = true; cx.notify(); });
    this.input.on("blur", (_e, cx) => { this.typing = false; cx.notify(); });
    this.reload(cx);
    cx.spawn(async (cx) => { for (;;) { await watchFolder(`${VAULT}/notes`); this.reload(cx); } });
    cx.spawn(async (cx) => { for (;;) { if ((await nextCommand()) === "focus") this.handle.focus(); cx.notify(); } });
  }

  reload(cx) {
    if (this.loading) { this.again = true; return; }
    this.loading = true;
    cx.spawn(async (cx) => {
      try {
        // Projects live directly in notes/ (projects.base: file.folder == "notes").
        const names = (await fs.readdir(`${VAULT}/notes`)).filter((n) => n.endsWith(".md"));
        const today = localDate(new Date());
        // Names a #gtd/wait task may use without a contact link. Private, so the
        // list lives in the vault (.bim-projects-ignored.json), not in this published mod.
        const ignored = JSON.parse((await readTextFile(`${VAULT}/.bim-projects-ignored.json`)) ?? "[]");
        const texts = await Promise.all(names.map((n) => readTextFile(`${VAULT}/notes/${n}`)));
        const notes = names.flatMap((n, i) => (/^type: project\s*$/m.test(texts[i] ?? "") ? [parseNote(`${VAULT}/notes/${n}`, texts[i])] : []));
        for (const n of notes) n.issues = check(n, today, ignored);
        this.projects = notes.sort((a, b) => b.id.localeCompare(a.id)); this.error = null;
        if (!this.selected) this.selected = this.visible()[0]?.path ?? null;
      } catch (e) { this.error = String(e); }
      finally { this.loading = false; cx.notify(); if (this.again) { this.again = false; this.reload(cx); } }
    });
    cx.notify();
  }

  visible() {
    const words = this.q.split(/\s+/).filter(Boolean);
    const rows = this.projects.filter((p) => (!this.openOnly || !p.completed) && (!this.kind || p.issues.some((i) => i.kind === this.kind)) && words.every((w) => p.lower.includes(w)));
    // The stale filter is a triage queue: quietest first.
    return this.kind === "stale" ? rows.sort((a, b) => (a.lastLog ?? "").localeCompare(b.lastLog ?? "")) : rows;
  }

  select(path, cx) {
    if (!path) return;
    this.selected = path;
    cx.notify();
  }

  rel(p) { return p.path.slice(VAULT.length + 1); }
  openNvim(p) { run("tab.new", { name: p.title, folder: VAULT, argv: ["nvim", this.rel(p)] }); }
  openObsidian(p) { exec("open", [`obsidian://open?vault=${encodeURIComponent(VAULT.split("/").pop())}&file=${encodeURIComponent(this.rel(p).replace(/\.md$/, ""))}`]).catch(() => {}); }

  // Triage keys: c completes the note (completed: true, open tasks cancelled), s parks it (open actions
  // to #gtd/act/someday, dates dropped, a Log line so the review counts as activity), r moves past due
  // and follow-up dates a week out. watchFolder reloads.
  triage(p, how, cx) {
    const rows = this.visible(), i = rows.findIndex((x) => x.path === p.path), next = rows[i + 1] ?? rows[i - 1];
    cx.spawn(async (cx) => {
      try {
        const text = await readTextFile(p.path), d = new Date(), today = localDate(d);
        const stamp = `${today} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
        const out = how === "complete" ? completeNote(text, today) : how === "park" ? parkNote(text, stamp) : rescheduleNote(text, today);
        await writeTextFile(p.path, out, text);
        this.selected = next?.path ?? p.path;
      } catch (e) { notify({ title: "Projects", body: String(e), level: "error" }); }
      cx.notify();
    });
  }

  onKey(e, cx) {
    if (this.typing) { if (e.key === "escape") { this.handle.focus(); cx.stop_propagation(); } return; }
    const rows = this.visible(), i = rows.findIndex((p) => p.path === this.selected);
    if (e.key === "down" || e.key === "j") this.select(rows[Math.min(i + 1, rows.length - 1)]?.path, cx);
    else if (e.key === "up" || e.key === "k") this.select(rows[Math.max(i - 1, 0)]?.path, cx);
    else if (e.key === "enter" && i >= 0) this.openNvim(rows[i]);
    else if (e.key === "c" && i >= 0) this.triage(rows[i], "complete", cx);
    else if (e.key === "s" && i >= 0) this.triage(rows[i], "park", cx);
    else if (e.key === "r" && i >= 0) this.triage(rows[i], "reschedule", cx);
    else if (e.key === "/") this.input.focus();
    else return;
    cx.stop_propagation();
  }

  chip(id, label, on, click, t) {
    return div().id(id).px(8).py(3).rounded(6).text_size(11).cursor_pointer().border_1().border_color(on ? t.accent : t.border).bg(on ? t.selected : t.raised).text_color(on ? t.foreground : t.muted).hover((s) => s.bg(t.hover)).on_click((_e, cx) => { click(); cx.notify(); }).child(label);
  }

  badge(kind, n, t) {
    const c = SOFT.has(kind) ? t.ansi3 : t.ansi1;
    return div().flex_none().px(5).rounded(4).text_size(10).bg(c + "22").text_color(c).child(n > 1 ? `${KINDS[kind]} ×${n}` : KINDS[kind]);
  }

  row(p, index, t) {
    const counts = {};
    for (const i of p.issues) counts[i.kind] = (counts[i.kind] || 0) + 1;
    return v_flex().id(`p-${index}`).h(52).flex_none().px(10).py(6).gap(3).rounded(7).cursor_pointer().when(this.selected === p.path, (e) => e.bg(t.selected)).hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => this.select(p.path, cx))
      .child(h_flex().gap(8).items_center().child(div().flex_1().min_w(0).truncate().font_semibold().text_color(p.completed ? t.muted : t.foreground).child((p.completed ? "✓ " : "") + p.title)).child(div().flex_none().text_size(11).text_color(t.dim).child(p.id)))
      .child(h_flex().gap(5).items_center().child(div().flex_1().min_w(0).truncate().text_size(11).text_color(t.dim).child(p.tags.join(" "))).children(Object.keys(counts).map((k) => this.badge(k, counts[k], t))));
  }

  button(id, label, click, t) {
    return div().id(id).flex_none().px(10).py(4).rounded(6).text_size(11).border_1().border_color(t.border).cursor_pointer().hover((s) => s.bg(t.hover)).on_click(() => click()).child(label);
  }

  detail(p, t) {
    if (!p) return div().flex_1().p(16).text_color(t.dim).child(this.projects.length ? "Select a project (↑ ↓, Enter opens it in nvim, c completes, s parks, r re-dates, / searches)" : "");
    const open = p.tasks.filter((x) => x.open);
    const line = (x) => div().text_size(11).text_color(t.dim).whitespace_normal().child(`${x.line}: ${x.text}`);
    return v_flex().flex_1().min_w(0).min_h(0)
      .child(h_flex().flex_none().px(12).h(42).gap(8).items_center().border_b(1).border_color(t.border)
        .child(div().flex_1().min_w(0).truncate().font_semibold().child(p.title))
        .child(div().flex_none().text_size(11).text_color(t.dim).child("c complete · s park · r re-date"))
        .child(this.button("open-nvim", "nvim", () => this.openNvim(p), t))
        .child(this.button("open-obsidian", "Obsidian", () => this.openObsidian(p), t)))
      .child(v_flex().id("detail").flex_1().min_h(0).overflow_y_scrollbar().p(12).gap(12)
        .child(div().text_size(11).text_color(t.dim).whitespace_normal().child(`${this.rel(p)} · ${p.completed ? "completed" : "open"} · ${p.fm.deliverable || "no deliverable"} · ${p.tags.length ? p.tags.join(" ") : "no tags"}`))
        .child(div().font_semibold().child(p.issues.length ? `Issues (${p.issues.length})` : "No issues"))
        .children(p.issues.map((i, n) => h_flex().id(`issue-${n}`).gap(8).items_start().child(this.badge(i.kind, 1, t)).child(v_flex().flex_1().min_w(0).gap(2).child(div().whitespace_normal().child(i.msg)).when(Boolean(i.task), (e) => e.child(line(i.task))))))
        .child(div().font_semibold().child(`Open tasks (${open.length})`))
        .children(open.map((x, n) => h_flex().id(`task-${n}`).gap(8).items_start().child(div().flex_none().w(110).text_size(11).text_color(t.muted).child(x.gtd[0] || x.section)).child(div().flex_1().min_w(0).whitespace_normal().child(x.action ?? x.text)))));
  }

  render(cx) {
    const t = theme(), rows = this.visible(), wide = this.width >= 760, selected = this.projects.find((p) => p.path === this.selected);
    const totals = {}, openCount = this.projects.filter((p) => !p.completed).length;
    for (const p of this.projects) for (const i of p.issues) totals[i.kind] = (totals[i.kind] || 0) + 1;
    // ponytail: a plain scroll list (a few hundred rows); switch to v_virtual_list if the vault grows past a few thousand projects.
    const list = div().flex_1().min_w(0).min_h(0).relative()
      .child(v_flex().id("projects").size_full().overflow_y_scroll().p(4).children(rows.map((p, i) => this.row(p, i, t)))
        .when(!rows.length, (e) => e.child(div().p(8).text_color(t.dim).child(this.error || (this.loading ? "Reading project notes…" : "Nothing matches")))))
      .child(Scrollbar.vertical("projects").absolute().inset_0());
    // h_flex centers its children vertically; stretch them so the two columns fill the body.
    const body = (wide ? h_flex().items_stretch() : v_flex()).flex_1().min_h(0).min_w(0)
      .child(wide ? list.flex_none().w(Math.round(this.width * 0.45)).border_r(1).border_color(t.border) : list.flex_none().h(Math.round(this.height * 0.45)).border_b(1).border_color(t.border))
      .child(this.detail(selected, t));
    return v_flex().id("root").size_full().min_h(0).bg(t.background).text_color(t.foreground).text_size(13).track_focus(this.handle)
      .on_size_change((s, cx) => { this.width = s.width; this.height = s.height; cx.notify(); })
      .on_key_down((e, cx) => this.onKey(e, cx))
      .child(h_flex().h(42).flex_none().px(14).gap(8).items_center().border_b(1).border_color(t.border)
        .child(div().font_semibold().child("Projects"))
        .child(div().px(5).py(1).rounded(4).border_1().border_color(t.border).text_size(10).text_color(t.muted).child(`${openCount} open · ${this.projects.length} total`))
        .child(div().flex_1())
        .when(this.loading, (e) => e.child(div().text_size(11).text_color(t.dim).child("Reading…")))
        .child(div().id("search").flex_1().min_w(100).max_w(220).h(28).px(8).flex().items_center().rounded(6).border_1().border_color(this.typing ? t.accent : t.border).cursor_text().on_mouse_down("left", (_e, cx) => cx.stop_propagation()).child(Input.new(this.input).h_full().text_size(12).text_color(t.foreground))))
      .child(h_flex().flex_none().px(10).py(8).gap(6).items_center().flex_wrap().border_b(1).border_color(t.border)
        .child(this.chip("chip-open", "Open only", this.openOnly, () => { this.openOnly = !this.openOnly; }, t))
        .children(Object.keys(KINDS).filter((k) => totals[k]).map((k) => this.chip(`chip-${k}`, `${KINDS[k]} ${totals[k]}`, this.kind === k, () => { this.kind = this.kind === k ? null : k; }, t))))
      .child(body);
  }
}
