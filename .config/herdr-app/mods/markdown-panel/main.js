// Markdown panel, by jlopezlira (https://github.com/jlopezlira/herdr-kanso). Apache-2.0.
// Reviews (md-review and Done), Escape and "From this terminal" by Johannes Hund (https://github.com/h0ru5),
// from his remix https://github.com/h0ru5/herdr-md-review.
// markdown-handler.sh leaves .md paths opened from outside in data/kanso-open; bin/md-review leaves
// the ones to review in data/markdown-review; watchOpens picks both up.
// doc.js and blocks.js are synced copies of kanso-panel's; edit those.
import { View, div, svg } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { appHome, exec, watchFolder, focused, spaces, props, closeOverlay, theme, home } from "herdr";
import { MarkdownDoc, tildePath } from "./doc.js";

const ICONS = "mods/markdown-panel/icons";
const isMarkdown = (path) => /\.(md|markdown|mdx)$/i.test(path);
const folderOf = (path) => path.replace(/[\\/][^\\/]*$/, "") || "/";
const nameOf = (path) => path.split(/[\\/]/).at(-1);
const REMOTE_READ_MS = 3000;
const OPEN_DIR = "data/kanso-open", REVIEW_DIR = "data/markdown-review", WAITING_DIR = "data/markdown-review-waiting", DONE_DIR = "data/markdown-review-done";
const RECENT_MAX = 15;

// Reads and removes the paths waiting in the inbox, oldest first.
export async function takeAllOpens(dir) {
  const r = await exec("sh", ["-c", 'for f in "$1"/*.path; do [ -f "$f" ] || continue; cat "$f"; printf "\\0"; rm -f "$f"; done', "sh", dir]);
  return (r.stdout ?? "").split("\0").map((p) => p.trim()).filter((p) => p.startsWith("/"));
}
// The newest of them.
export async function takeOpens(dir) { return (await takeAllOpens(dir)).at(-1) ?? null; }

// The reviews `md-review` still waits on, as [{ id, path }]: one file per waiting process,
// named by its pid; one whose process is gone is removed.
export async function waitingReviews(dir) {
  const r = await exec("sh", ["-c", 'for f in "$1"/*.path; do [ -f "$f" ] || continue; id=$(basename "$f" .path); if kill -0 "$id" 2>/dev/null; then printf "%s\\t" "$id"; cat "$f"; printf "\\0"; else rm -f "$f"; fi; done', "sh", dir]);
  return reviewsIn(r.stdout ?? "");
}
export const reviewsIn = (out) => out.split("\0").map((l) => l.split("\t")).filter(([id, path]) => /^\d+$/.test(id ?? "") && path?.startsWith("/")).map(([id, path]) => ({ id, path: path.trim() }));

export function markdownIn(listing) {
  return listing.split("\n").map((l) => l.trim()).filter((l) => /\.(md|markdown|mdx)$/i.test(l))
    .toSorted((a, b) => a.split("/").length - b.split("/").length || a.localeCompare(b)).slice(0, 40);
}

// The focused pane's machine (null: this one) and folder. A pane on an SSH
// machine has a folder on that machine, so its files are listed and read there.
export function placeOf(focus, list, localHome) {
  const space = list.find((s) => s.id === focus?.space);
  const on = space?.machine ?? null;
  return { on, folder: focus?.cwd || space?.folder || (on ? "" : localHome) };
}

// "From this terminal": what recent.sh printed, existing absolute Markdown paths, once each, best first.
export function recentIn(listing) {
  return [...new Set(listing.split("\n").map((l) => l.trim()).filter((l) => l.startsWith("/") && isMarkdown(l)))].slice(0, RECENT_MAX);
}

export default class MarkdownPanel extends View {
  init(_props, cx) {
    this.doc = null; this.files = null; this.recent = [];
    this.reviewing = []; // the reviews `md-review` waits on ({ id, path }); their files show Done
    this.notice = null;
    const { on, folder } = placeOf(focused(), spaces(), home());
    this.on = on; this.folder = folder;
    this.handle = cx.focus_handle();
    // A binding, not on_key_down: a focused Textarea takes Escape first.
    cx.bind_keys(["MarkdownPanel", "MarkdownPanel > Input"].map((context) => ({ keystroke: "escape", action: "markdown_panel_escape", context })));
    this.watchOpens(cx, OPEN_DIR, false);
    this.watchOpens(cx, REVIEW_DIR, true);
    this.watchReviews(cx);
    this.list(cx);
    this.findRecent(focused()?.terminal ?? null, cx);
  }

  findRecent(terminal, cx) {
    if (this.on) return;
    cx.spawn(async (cx) => {
      const r = await exec("sh", [`${appHome()}/mods/markdown-panel/recent.sh`, terminal ?? ""]).catch(() => null);
      this.recent = recentIn(r?.stdout ?? "");
      cx.notify();
    });
  }

  list(cx) {
    const on = this.on;
    cx.spawn(async (cx) => {
      // A machine's home when its pane told no folder: where its commands start.
      const folder = this.folder || (await exec("pwd", [], { on }).catch(() => null))?.stdout.trim() || "";
      this.folder = folder;
      const where = { cwd: folder || undefined, on };
      const git = await exec("git", ["ls-files", "--", "*.md", "*.markdown", "*.mdx"], where).catch(() => null);
      const out = git?.code === 0 && git.stdout.trim() ? git.stdout
        : (await exec("find", [".", "-maxdepth", "3", "-name", "node_modules", "-prune", "-o", "-type", "f", "(", "-iname", "*.md", "-o", "-iname", "*.mdx", ")", "-print"], where).catch(() => null))?.stdout ?? "";
      this.files = markdownIn(out.replace(/^\.\//gm, ""));
      cx.notify();
    });
  }

  watchOpens(cx, inbox, review) {
    const dir = `${appHome()}/${inbox}`;
    cx.spawn(async (cx) => {
      try {
        await exec("mkdir", ["-p", dir]);
        for (;;) {
          const paths = (await takeAllOpens(dir)).filter(isMarkdown);
          if (paths.length) this.open(paths.at(-1), cx, null, review);
          await watchFolder(dir);
        }
      } catch { /* no inbox: nothing opens from outside */ }
    });
  }

  // What waits is kept by md-review itself, so closing the window or many agents asking at once loses none.
  watchReviews(cx) {
    const dir = `${appHome()}/${WAITING_DIR}`;
    cx.spawn(async (cx) => {
      try {
        await exec("mkdir", ["-p", dir]);
        for (;;) {
          this.reviewing = await waitingReviews(dir);
          cx.notify();
          await watchFolder(dir);
        }
      } catch { /* no folder: no reviews */ }
    });
  }

  // Saves what you typed in the file shown before, then shows this one.
  // on: the machine the file is on (null: this one); paths opened from outside are here.
  // review: `md-review` waits on it. While the file shown before can't be saved (a conflict
  // to settle), a review waits for it instead of being dropped, since an agent waits on it.
  open(path, cx, on = null, review = false) {
    const before = this.doc;
    cx.spawn(async (cx) => {
      if (before && !(await before.flush())) {
        cx.notify();
        if (!review) return;
        await cx.sleep(1000);
        this.open(path, cx, on, review);
        return;
      }
      before?.release();
      this.notice = null;
      this.doc = new MarkdownDoc(path, on, (to) => { if (isMarkdown(to)) this.open(to, cx, on); }, ICONS);
      this.doc.load(cx);
      this.watch(path, cx);
      cx.notify();
    });
  }

  // Another machine's folder can't be watched from here: read it every few seconds.
  watch(path, cx) {
    const doc = this.doc, dir = folderOf(path);
    const next = () => (doc.on ? cx.sleep(REMOTE_READ_MS) : watchFolder(dir));
    cx.spawn(async (cx) => {
      try { while (this.doc === doc) { await next(); if (this.doc === doc) doc.load(cx); } } catch {}
    });
  }

  close(cx) {
    const doc = this.doc, id = props()?.overlay;
    const done = () => { if (id) closeOverlay(id); };
    if (!doc) { done(); return; }
    cx.spawn(async (cx) => {
      if (!(await doc.flush())) { cx.notify(); return; }
      doc.release(); this.doc = null;
      done();
    });
  }

  // Saves, tells `md-review` the review is finished, closes.
  done(cx) {
    const doc = this.doc;
    if (!doc) return;
    cx.spawn(async (cx) => {
      if (!(await doc.flush())) { cx.notify(); return; }
      // Every md-review waiting on this file is answered.
      const ids = this.reviewing.filter((x) => x.path === doc.path).map((x) => x.id);
      const r = await exec("sh", ["-c", 'd=$1; shift; mkdir -p "$d" && for id in "$@"; do : > "$d/$id" || exit 1; done', "sh", `${appHome()}/${DONE_DIR}`, ...ids]).catch((e) => ({ code: 1, stderr: String(e?.message ?? e) }));
      if (r.code !== 0) { this.notice = `md-review was not told: ${(r.stderr || "the marker could not be written").trim()}`; cx.notify(); return; }
      this.reviewing = this.reviewing.filter((x) => x.path !== doc.path); this.notice = null;
      // Another review still waits: show it rather than close.
      if (this.reviewing.length) this.open(this.reviewing.at(-1).path, cx, null, true); else this.close(cx);
    });
  }

  back(cx) {
    const doc = this.doc;
    if (!doc) return;
    cx.spawn(async (cx) => {
      if (!(await doc.flush())) { cx.notify(); return; }
      doc.release(); this.doc = null;
      cx.notify();
    });
  }

  render() {
    const t = theme();
    const doc = this.doc;
    const button = (id, icon, tip, action) => div().id(id).p(4).rounded(6).cursor_pointer().text_color(t.muted).tooltip(tip)
      .hover((s) => s.bg(t.hover).text_color(t.foreground)).on_click((_e, cx) => action(cx))
      .child(svg(`${ICONS}/${icon}.svg`).size(14));
    const reviewing = Boolean(doc) && !doc.on && this.reviewing.some((x) => x.path === doc.path);
    return v_flex().id("markdown-panel").key_context("MarkdownPanel").track_focus(this.handle)
      .on_action("markdown_panel_escape", (_e, cx) => { if (doc && doc.active !== null) { doc.close(); cx.notify(); } else this.close(cx); })
      .size_full().min_h(0).bg(t.background).text_color(t.foreground).text_size(13)
      .on_key_down((e, cx) => doc?.key(e, cx))
      .child(h_flex().h(42).flex_none().px(10).gap(6).items_center().border_b(1).border_color(t.border)
        .when(Boolean(doc), (el) => el.child(button("md-back", "chevron-left", "Markdown in this folder", (cx) => this.back(cx))))
        .child(v_flex().flex_1().min_w(0).pl(doc ? 0 : 4)
          .child(div().truncate().font_semibold().child(doc ? nameOf(doc.path) : "Markdown"))
          .child(div().truncate().text_size(11).text_color(t.dim).child(tildePath(doc ? folderOf(doc.path) : this.folder, doc ? doc.on : this.on))))
        .children(doc ? doc.controls(t, "md") : [])
        .when(Boolean(doc) && !doc.editing, (el) => el.child(button("md-refresh", "refresh", "Read again", (cx) => doc.load(cx))))
        .when(reviewing, (el) => el.child(div().id("md-done").flex_none().px(8).py(3).rounded(6).cursor_pointer().text_size(12)
          .bg(t.raised).border_1().border_color(t.border).tooltip("Review done: tell the agent").hover((s) => s.bg(t.hover))
          .on_click((_e, cx) => this.done(cx)).child("Done")))
        .child(button("md-close", "close", "Close", (cx) => this.close(cx))))
      .when(Boolean(this.notice), (el) => el.child(div().flex_none().px(14).py(6).text_size(12).text_color(t.blocked).border_b(1).border_color(t.border).child(this.notice ?? "")))
      .child(doc ? doc.body(t, "md-doc") : this.listView(t));
  }

  listView(t) {
    const files = this.files ?? [], recent = this.recent;
    // Reviews still waiting come first, so one closed by mistake is never out of reach.
    const waiting = [...new Set(this.reviewing.map((x) => x.path))];
    const row = (id, name, sub, open) => h_flex().id(id).flex_none().h(30).px(10).gap(8).items_center().rounded(6).cursor_pointer()
      .hover((s) => s.bg(t.hover)).on_click((_e, cx) => open(cx))
      .child(div().flex_none().truncate().child(name))
      .child(div().flex_1().min_w(0).truncate().text_size(11.5).text_color(t.dim).child(sub));
    const heading = (text) => div().flex_none().px(10).pt(8).pb(2).text_size(11).text_color(t.dim).child(text);
    const empty = this.files === null ? "Looking for Markdown…" : "No Markdown files in this folder. Cmd-click a .md path in a terminal to read it here.";
    return div().id("md-files").flex_1().min_h(0).overflow_y_scrollbar().p(6)
      .when(waiting.length > 0, (el) => el.child(heading("Waiting for your review"))
        .children(waiting.map((p, i) => row(`md-waiting-${i}`, nameOf(p), tildePath(folderOf(p), null), (cx) => this.open(p, cx)))))
      .when(recent.length > 0, (el) => el.child(heading("From this terminal"))
        .children(recent.map((p, i) => row(`md-recent-${i}`, nameOf(p), tildePath(folderOf(p), null), (cx) => this.open(p, cx)))))
      .when(recent.length > 0 || waiting.length > 0, (el) => el.child(heading("In this folder")))
      .when(!files.length, (el) => el.child(div().flex_none().px(10).py(6).text_size(12.5).text_color(t.dim).child(empty)))
      .children(files.map((f, i) => row(`md-file-${i}`, nameOf(f), f.includes("/") ? folderOf(f) : "", (cx) => this.open(`${this.folder}/${f}`, cx, this.on))));
  }
}
