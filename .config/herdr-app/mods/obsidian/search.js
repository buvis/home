// The popup: find a note by name, search inside notes (/text), list a tag (#tag),
// add a line to today's note (+text), make a new note from what was typed, save an
// agent's last reply (>title), or send a note to an agent (Alt+Enter).
import { div, svg } from "gpui-kit";
import { v_flex, h_flex, InputState, Input } from "gpui-base";
import { closeOverlay, nextCommand, notify, props, readTextFile, theme } from "herdr";
import * as vault from "./vault.js";
import * as agent from "./agent.js";

const ICON = (name) => `mods/obsidian/${name}.svg`;
const WINDOW = 10;

// A note title from a reply: its first line's first sentence, without markdown,
// at most 60 characters, cut at a word.
function titleFrom(text) {
  const line = (text.split("\n").find((l) => l.trim()) ?? "").replace(/^[#>*\-\s]+|[*_`"“”]+/g, "").trim();
  let title = line.match(/^(.{12,}?)[.!?:](\s|$)/)?.[1] ?? line;
  if (title.length > 60) title = title.slice(0, 60).replace(/\s+\S*$/, "");
  return title.replace(/[.!?:,;\s]+$/, "") || "Reply";
}

export class Search {
  init(cx) {
    this.query = props()?.query ?? "";
    this.at = 0;
    this.rows = null;
    this.error = null;
    this.all = [];
    this.n = 0;
    this.input = InputState.new({ placeholder: "Find a note…   /text inside   #tag   +text adds to today   >title saves a reply" });
    if (this.query) this.input.set_value(this.query);
    this.input.on("change", (_e, cx) => { this.query = this.input.value(); this.at = 0; this.update(cx); });
    this.input.on("submit", (e, cx) => this.submit(e?.secondary ? "obsidian" : e?.shift ? "editor" : "viewer", cx));
    // The agent Send and Save act on, chosen while the popup opens over it.
    this.agent = agent.target();
    this.input.focus();
    cx.timer.after(400, () => this.input.focus());
    cx.spawn(async (cx) => {
      try { this.all = await vault.notes(true); this.name = (await vault.config()).name; }
      catch (e) { this.error = String(e?.message ?? e); }
      this.update(cx);
    });
    cx.spawn(async (cx) => {
      for (;;) {
        const c = await nextCommand();
        if (c === "next") this.move(1);
        else if (c === "prev") this.move(-1);
        else if (c === "app") this.submit("obsidian", cx);
        else if (c === "edit") this.submit("editor", cx);
        else if (c === "send") this.submit("agent", cx);
        else continue;
        cx.notify();
      }
    });
  }

  mode() {
    const q = this.query;
    if (q.startsWith("/")) return "text";
    if (q.startsWith("#") && q.length > 1 && !q.includes(" ")) return "tag";
    if (q.startsWith("+")) return "capture";
    if (q.startsWith(">")) return "reply";
    return "name";
  }

  noteRow(p) {
    const folder = vault.folderOf(p);
    return { key: p, title: vault.title(p), detail: folder, path: p, icon: "file-text" };
  }

  // Name and capture rows are instant; text and tag searches wait for typing to pause.
  update(cx) {
    const n = ++this.n, q = this.query, mode = this.mode();
    if (mode === "capture") {
      const text = q.slice(1).trim();
      this.rows = text ? [{ key: "capture", title: `Add to today's note: ${text}`, detail: "Enter", icon: "calendar", capture: text }] : [];
      return cx.notify();
    }
    if (mode === "reply") return this.replyRows(cx);
    if (mode === "name") {
      const hits = vault.match(this.all, q).slice(0, 200).map((p) => this.noteRow(p));
      const exact = hits.some((r) => r.title.toLowerCase() === q.trim().toLowerCase());
      if (q.trim() && !exact) hits.push({ key: "create", title: `Create “${q.trim()}”`, detail: "new note", icon: "plus", create: q.trim() });
      if (!q.trim()) {
        if (this.agent) hits.unshift({ key: "reply", title: `Save last reply from ${agent.nameOf(this.agent)}`, detail: ">", icon: "bot", toReply: true });
        hits.unshift({ key: "today", title: "Today's note", detail: vault.formatDate("dddd D MMMM"), icon: "calendar", today: true });
      }
      this.rows = hits;
      return cx.notify();
    }
    const term = q.slice(1);
    if (!term.trim()) { this.rows = []; return cx.notify(); }
    this.searching = true;
    cx.notify();
    cx.timer.after(160, (cx) => {
      if (n !== this.n) return;
      cx.spawn(async (cx) => {
        try {
          const rows = mode === "text"
            ? (await vault.searchText(term)).map((h) => ({ key: `${h.path}:${h.line}`, title: vault.title(h.path), detail: vault.folderOf(h.path), snippet: h.text, path: h.path, line: h.line, icon: "search" }))
            : (await vault.searchTag(term)).map((p) => this.noteRow(p));
          if (n !== this.n) return;
          this.rows = rows; this.error = null;
        } catch (e) { if (n === this.n) this.error = String(e?.message ?? e); }
        this.searching = false;
        cx.notify();
      });
    });
  }

  // >title: the agent's last reply as a new note (titled, or its first line), or
  // appended to today's note. The reply is read once per popup.
  replyRows(cx) {
    const a = this.agent;
    if (!a) { this.rows = []; this.replyError = "No agent: click into an agent's terminal, then open this again"; return cx.notify(); }
    if (!this.reply) {
      this.reply = { loading: true };
      this.rows = null;
      cx.spawn(async (cx) => {
        try { this.reply = await agent.lastReply(a); } catch (e) { this.reply = { error: String(e?.message ?? e) }; }
        if (this.mode() === "reply") this.replyRows(cx);
      });
      return cx.notify();
    }
    if (this.reply.loading) return cx.notify();
    if (this.reply.error) { this.rows = []; this.replyError = this.reply.error; return cx.notify(); }
    this.replyError = null;
    const text = this.reply.text, name = agent.nameOf(a);
    const given = this.query.slice(1).trim();
    const first = titleFrom(text);
    const snippet = text.replace(/\s+/g, " ").slice(0, 160);
    const from = this.reply.from === "screen" ? "screen text" : "last reply";
    this.rows = [
      { key: "reply-new", title: `New note “${given || first}”`, detail: from, snippet, icon: "plus", saveReply: { title: given || first } },
      { key: "reply-today", title: `Append to today's note under “## From ${name}”`, detail: from, snippet, icon: "calendar", saveReply: { today: true } },
    ];
    return cx.notify();
  }

  close() {
    closeOverlay(props()?.overlay);
  }

  move(step) {
    const count = this.rows?.length ?? 0;
    if (count) this.at = (this.at + step + count) % count;
  }

  // Runs in its own task: the handler's cx would die at the first await.
  submit(how, cx) {
    const row = this.rows?.[this.at];
    if (!row) return;
    if (row.toReply) {
      this.input.set_value(">");
      this.query = ">"; this.at = 0;
      return this.update(cx);
    }
    cx.spawn((cx) => this.act(row, how, cx));
  }

  async act(row, how, cx) {
    // Closing the popup ends its tasks, so it closes only once the work is done.
    try {
      if (how === "agent") {
        if (!row.path && !row.today) return;
        if (!this.agent) return notify({ title: "No agent to send to", body: "Click into an agent's terminal first", level: "info", timeout: 3000 });
        const rel = row.today ? await vault.today() : row.path;
        const { root } = await vault.config();
        const text = await readTextFile(`${root}/${rel}`);
        if (text !== null) await agent.sendNote(rel, text, cx, this.agent);
        return;
      }
      if (row.saveReply) {
        const { text } = this.reply, name = agent.nameOf(this.agent);
        if (row.saveReply.today) {
          await vault.appendSection(`From ${name}`, text);
          return notify({ title: "Added to today's note", body: `Reply from ${name}`, level: "success", timeout: 2500 });
        }
        const rel = await vault.createWith(row.saveReply.title, `${text.replace(/\s+$/, "")}\n`);
        notify({ title: "Saved the reply", body: rel, level: "success", timeout: 2500 });
        return vault.open(rel, how);
      }
      if (row.capture) {
        await vault.capture(row.capture);
        return notify({ title: "Added to today's note", body: row.capture, level: "success", timeout: 2500 });
      }
      if (row.today) return vault.open(await vault.today(), how);
      if (row.create) return vault.open(await vault.create(row.create), how === "viewer" ? "editor" : how);
      vault.open(row.path, how, row.line);
    } catch (e) {
      notify({ title: "Obsidian", body: String(e?.message ?? e), level: "error" });
    } finally {
      this.close();
    }
  }

  key(e, cx) {
    if (e.key === "escape") return this.close();
    if (e.key === "enter" && e.modifiers.alt) this.submit("agent", cx);
    else if (e.key === "down") this.move(1);
    else if (e.key === "up") this.move(-1);
    else if (e.key === "tab") {
      // Tab flips between finding by name and searching inside notes.
      const next = this.query.startsWith("/") ? this.query.slice(1) : `/${this.query}`;
      this.input.set_value(next);
      this.query = next; this.at = 0; this.update(cx);
    } else return;
    cx.stop_propagation();
    cx.notify();
  }

  render() {
    const t = theme(), rows = this.rows ?? [], mode = this.mode();
    const first = Math.max(0, Math.min(this.at - Math.floor(WINDOW / 2), rows.length - WINDOW));
    const shown = rows.slice(first, first + WINDOW);
    const status = this.error ?? (mode === "reply" ? this.replyError : null) ?? (this.rows === null ? (mode === "reply" ? "Reading the agent's last reply…" : "Loading…")
      : this.searching && !rows.length ? "Searching…"
      : rows.length ? null
      : mode === "text" ? (this.query.length > 1 ? "No matches" : "Type to search inside notes")
      : mode === "tag" ? "No notes with that tag" : "No notes");
    const heading = { name: "Notes", text: "Search in notes", tag: "Tag", capture: "Today's note", reply: "Save a reply" }[mode];
    const footer = mode === "capture" ? "Enter adds the line · Esc closes"
      : mode === "reply" ? `From ${this.agent ? agent.nameOf(this.agent) : "no agent"} · type a title after > · Enter saves`
      : "Enter opens · ⌘/Ctrl+Enter in Obsidian · Shift+Enter in editor · ⌥Enter sends to agent · Tab searches inside";
    return v_flex().id("obsidian-search").size_full().min_h(0).p(14).gap(10).bg(t.popover).text_size(13)
      .on_key_down((e, cx) => this.key(e, cx))
      .child(h_flex().justify_between().items_center()
        .child(h_flex().gap(8).items_center()
          .child(div().text_size(15).font_semibold().text_color(t.foreground).child(heading))
          .child(div().text_size(12).text_color(t.dim).child(this.name ?? "")))
        .child(div().text_size(12).text_color(t.muted).child(rows.length ? `${rows.length}${rows.length >= 200 ? "+" : ""}` : "")))
      .child(h_flex().h(36).flex_none().px(10).gap(8).items_center().rounded(9).border_1().border_color(t.accent).bg(t.raised)
        .child(svg(ICON(mode === "reply" ? "bot" : mode === "capture" || mode === "tag" ? "calendar" : "search")).size(14).flex_none().text_color(t.muted))
        .child(Input.new(this.input).flex_1().h_full().text_size(12.8).text_color(t.foreground)))
      .child(v_flex().flex_1().min_h(0).gap(2)
        .when(Boolean(status), (el) => el.child(div().p(8).text_color(this.error || (mode === "reply" && this.replyError) ? t.blocked : t.muted).child(status ?? "")))
        .children(shown.map((row, i) => {
          const index = first + i, two = Boolean(row.snippet);
          return h_flex().id(`row-${row.key}`).h(two ? 46 : 34).flex_none().px(10).gap(10).items_center().rounded(7).cursor_pointer()
            .when(index === this.at, (el) => el.bg(t.selected))
            .hover((s) => s.bg(t.hover))
            .on_click((e, cx) => { this.at = index; this.submit(e.modifiers.alt ? "agent" : e.modifiers.platform || e.modifiers.control ? "obsidian" : e.modifiers.shift ? "editor" : "viewer", cx); })
            .child(svg(ICON(row.icon)).size(14).flex_none().text_color(row.create || row.capture || row.today || row.toReply || row.saveReply ? t.accent : t.muted))
            .child(v_flex().flex_1().min_w(0).gap(2)
              .child(div().truncate().text_color(t.foreground).child(row.title))
              .when(two, (el) => el.child(div().truncate().text_size(12).text_color(t.muted).child(row.snippet))))
            .child(div().flex_none().max_w(260).truncate().text_size(12).text_color(t.dim).child(row.line ? `${row.detail ? row.detail + " · " : ""}${row.line}` : row.detail ?? ""));
        })))
      .child(div().flex_none().text_size(12).text_color(t.dim).child(footer));
  }
}
