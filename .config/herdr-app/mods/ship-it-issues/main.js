// Issues: every open issue of the repo, in the side panel (GitHub, GitLab and
// Bitbucket). A row opens to its details and actions: start an agent on it, open
// its worktree, the host's page, copy link. Starting an agent first makes sure
// the issue has a worktree (a new branch <number>-<title> from the default
// branch, unless it has one) and opens it as a space; the agent starts only
// when that checkout exists.
//
// Its logic (forge, worktrees, agents) is in issues.js. data.js is a copy of
// ship-it-prs's.

import { View, div, svg } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { exec, shared, setShared, notify, theme, nextCommand } from "herdr";
import { READ, location, ago, panelShown, Recent, tilde } from "./data.js";
import { forgeOf, FORGE_NAME, listIssues, worktrees, issueTree, places, spaceAt, ensureWorktree, installedAgents, openWorktree } from "./issues.js";

const ICON = (name) => `mods/ship-it/icons/${name}.svg`;
const FILTERS = [["all", "All"], ["mine", "Assigned to me"]];
const PAGE = 15;

export default class Issues extends View {
  init(_p, cx) {
    this.issues = []; this.filter = "all"; this.last = null; this.limit = PAGE; this.trees = {};
    this.expanded = null; this.agents = {}; // installed agents by machine
    this.memo = new Recent(12);
    this.bumpSeen = shared("ship-it.bump"); // the bar saw a PR or an issue appear, merge or close: ask again
    this.refresh(cx);
    cx.timer.every(120000, (cx) => this.refresh(cx));
    cx.spawn(async (cx) => { for (;;) { this.command(await nextCommand(), cx); cx.notify(); } });
  }

  // ship-it-issues.more, .refresh, .all, .mine: bindable to keys.
  command(name) {
    const c = String(name).replace(/^ship-it-issues[.:]/, "");
    if (c === "more") { if (this.more) this.loadMore(this.cx); }
    else if (c === "refresh") this.refresh(this.cx, true);
    else if (FILTERS.some(([id]) => id === c)) this.pick(c, this.cx);
  }

  key() {
    this.last = location(this.last);
    return JSON.stringify([this.last.cwd, this.last.on]);
  }

  shown() { return panelShown("ship-it-issues"); }

  refresh(cx, force, rendering) {
    this.cx = cx;
    if (!this.shown()) { this.stale = true; return; }
    if (this.loading && !force && Date.now() - this.loading < 30000) return;
    const context = this.key(), { cwd, on } = this.last;
    if (context !== this.context) { this.context = context; this.limit = PAGE; this.recall(); }
    if (!cwd) return;
    const filter = this.filter, limit = this.limit, memo = this.memoKey();
    const started = this.loading = Date.now(); this.stale = false;
    if (!rendering) cx.notify();
    cx.spawn(async (cx) => {
      try {
        const top = await exec("git", [...READ, "rev-parse", "--show-toplevel"], { cwd, on });
        if (this.key() !== context) return;
        if (top.code !== 0) { this.error = "Not a git repository"; return; }
        const root = top.stdout.trim();
        const forge = await forgeOf(root, on);
        if (!forge) { this.root = root; this.issues = []; this.error = "No supported remote"; return; }
        const [list, trees] = await Promise.all([listIssues(forge, root, on, filter === "mine", limit), worktrees(root, on)]);
        if (this.key() !== context || this.filter !== filter) return;
        this.root = root; this.on = on; this.forge = forge; this.trees = trees;
        if (list.error) { this.error = list.error; this.issues = []; return; }
        this.issues = list.issues; this.more = this.issues.length >= limit; this.error = null;
        this.memo.set(memo, { root, on, forge, trees, issues: this.issues, more: this.more, limit });
        // Shared state redraws every mod: write it only when it changes.
        const count = this.issues.length, was = shared("ship-it.issues");
        if (filter === "all" && (was?.root !== root || (was?.on ?? null) !== (on ?? null) || was?.count !== count || was?.more !== this.more)) setShared("ship-it.issues", { root, on: on ?? null, count, more: this.more });
      } catch (e) { if (this.key() === context) this.error = String(e); }
      finally { if (this.loading === started) this.loading = 0; cx.notify(); }
    });
    // The agents this machine has, once.
    if (this.agents[on ?? ""] === undefined) {
      this.agents[on ?? ""] = [];
      installedAgents(on).then((a) => { this.agents[on ?? ""] = a; cx.notify(); }).catch(() => { delete this.agents[on ?? ""]; });
    }
  }

  memoKey() { return `${this.context}#${this.filter}`; }

  recall() {
    this.root = null; this.issues = []; this.error = null; this.more = false; this.trees = {}; this.forge = null;
    const m = this.memo.get(this.memoKey());
    if (m) Object.assign(this, m);
  }

  pick(filter, cx) {
    if (filter === this.filter) return;
    this.filter = filter; this.limit = PAGE; this.recall();
    this.refresh(cx, true);
  }

  loadMore(cx) {
    if (this.loading) return;
    this.limit = this.issues.length + PAGE;
    this.refresh(cx, true);
  }

  // Make sure the issue's worktree exists, then show its space; with an agent, start it there.
  work(issue, agent, cx) {
    if (this.busy || !this.root) return;
    const root = this.root, on = this.on;
    this.busy = { number: issue.number, step: "Checking out…" }; cx.notify();
    cx.spawn(async (cx) => {
      try {
        const wt = await ensureWorktree(root, on, issue);
        if (this.root === root) this.trees = wt.trees;
        if (wt.created) notify({ title: `Worktree for #${issue.number}`, body: `${wt.branch} · ${tilde(wt.path)}`, level: "info", timeout: 3 });
        openWorktree(wt.path, on, wt.trees, issue, wt.branch, agent);
      } catch (e) { notify({ title: `Couldn't start #${issue.number}`, body: String(e.message ?? e), level: "error", timeout: 8 }); }
      finally { this.busy = null; cx.notify(); }
    });
  }

  icon(name, color, size = 14) { return svg(ICON(name)).size(size).flex_none().text_color(color); }

  row(issue, t, where) {
    const path = issueTree(this.trees, issue), space = spaceAt(path, where, Object.values(this.trees)), busy = this.busy?.number === issue.number;
    const open = this.expanded === issue.number;
    return v_flex().id(`issue-${issue.number}`).flex_none().px(10).py(7).gap(3).rounded(7).cursor_pointer()
      .hover((s) => s.bg(t.hover)).when(open, (e) => e.bg(t.hover))
      .on_click((_e, cx) => { this.expanded = open ? null : issue.number; cx.notify(); })
      .child(h_flex().gap(8).items_center().min_w(0)
        .child(this.icon("circle-dot", t.ansi2, 13))
        .child(div().flex_1().min_w(0).truncate().text_color(t.foreground).child(issue.title)))
      .child(h_flex().pl(21).gap(6).items_center().min_w(0).text_size(11).text_color(t.dim)
        .child(div().id(`issue-n-${issue.number}`).flex_none().text_color(t.muted).rounded(4).px(2).hover((s) => s.bg(t.raised)).tooltip("Copy link")
          .on_click((_e, cx) => { cx.stop_propagation(); this.copy(issue, cx); }).child(`#${issue.number}`))
        .child(div().min_w(0).truncate().child(issue.author))
        .child(div().flex_none().child(`· ${ago(issue.updatedAt)}`))
        .child(div().flex_1())
        .when(issue.labels.length > 0, (e) => e.child(div().min_w(0).truncate().child(issue.labels.slice(0, 2).join(", "))))
        .when(Boolean(path), (e) => e.child(div().flex_none().tooltip(space ? `Worktree open in a space: ${tilde(path)}` : `Worktree: ${tilde(path)}`)
          .child(this.icon(space ? "git-branch" : "folder", t.accent, 12))))
        .when(busy, (e) => e.child(this.icon("loader", t.muted, 12).spin(800))))
      .when(open, (e) => e.child(this.details(issue, path, space, t)));
  }

  copy(issue) {
    this.cx.write_to_clipboard(issue.url);
    notify({ title: `#${issue.number} link copied`, body: issue.url, level: "info", timeout: 2 });
  }

  details(issue, path, space, t) {
    const busy = this.busy?.number === issue.number, agents = this.agents[this.on ?? ""] ?? [];
    const body = (issue.body || "").replace(/\r/g, "").replace(/<!--[\s\S]*?-->/g, "").trim();
    const line = (icon, ...kids) => h_flex().gap(6).items_center().min_w(0).child(this.icon(icon, t.dim, 12)).children(kids);
    const button = (id, icon, label, primary, click) => h_flex().id(`issue-${id}-${issue.number}`).h(26).px(9).gap(6).items_center().flex_none().rounded(6).cursor_pointer().text_size(12)
      .when(primary, (e) => e.bg(t.accent).text_color(t.background)).when(!primary, (e) => e.border_1().border_color(t.border).text_color(t.foreground).hover((s) => s.bg(t.raised)))
      .when(Boolean(this.busy), (e) => e.opacity(0.5))
      .on_click((_e, cx) => { cx.stop_propagation(); click(cx); })
      .child(this.icon(icon, primary ? t.background : t.muted, 12)).child(label);
    const assigned = issue.assignees.length ? `assigned: ${issue.assignees.join(", ")}` : "unassigned";
    return v_flex().pl(21).pt(6).gap(5).text_size(11).text_color(t.muted)
      .child(div().text_size(12).text_color(t.foreground).child(issue.title))
      .child(line("circle-dot", div().min_w(0).truncate().child(`${issue.author} · ${assigned}`)))
      .when(issue.labels.length > 0, (e) => e.child(line("square", div().min_w(0).truncate().child(issue.labels.join(", ")))))
      .child(line("folder", div().min_w(0).truncate().child(path ? `${tilde(path)}${space ? "" : " · no space open"}` : "No worktree yet")))
      .when(Boolean(body), (e) => e.child(div().whitespace_normal().text_color(t.dim).max_h(120).overflow_hidden().child(body.length > 500 ? body.slice(0, 500).trimEnd() + "…" : body)))
      .child(h_flex().pt(3).gap(6).flex_wrap()
        .children(agents.map((a, i) => button(`agent-${a.key}`, busy ? "loader" : "rocket", busy ? this.busy.step : i === 0 ? `Start ${a.name}` : a.name, i === 0, (cx) => this.work(issue, a, cx))))
        .when(!agents.length, (e) => e.child(button("agent", "rocket", "No agent installed", false, () => {})))
        .child(button("tree", path ? "folder" : "git-branch-plus", path ? (space ? "Go to space" : "Open worktree") : "Create worktree", false, (cx) => this.work(issue, null, cx)))
        .child(button("host", "external-link", FORGE_NAME[this.forge] ?? "Open", false, (cx) => cx.open_url(issue.url)))
        .child(button("copy", "copy", "Copy link", false, () => this.copy(issue))));
  }

  render(cx) {
    const bump = shared("ship-it.bump");
    if (bump !== this.bumpSeen) { this.bumpSeen = bump; if (this.shown()) this.refresh(cx, true, true); else this.stale = true; }
    this.cx = cx;
    if (this.shown() && (this.stale || this.key() !== this.context)) this.refresh(cx, false, true);
    const t = theme(), list = this.issues, where = list.length ? places(this.on) : [];
    const empty = this.error || (this.loading ? "Loading issues…" : this.filter === "all" ? "No open issues" : "No open issues assigned to you");
    return v_flex().id("ship-it-issues").size_full().min_h(0).rounded(10).overflow_hidden().bg(t.background).border_1().border_color(t.border).text_color(t.foreground).text_size(13)
      .child(h_flex().h(42).flex_none().px(14).gap(8).items_center().border_b(1).border_color(t.border)
        .child(div().font_semibold().whitespace_nowrap().child("Issues"))
        .child(div().px(5).py(1).rounded(4).border_1().border_color(t.border).text_size(10).text_color(t.muted).whitespace_nowrap().child(`${list.length}${this.more ? "+" : ""} open`))
        .when(Boolean(this.forge), (e) => e.child(div().text_size(10).text_color(t.dim).whitespace_nowrap().child(FORGE_NAME[this.forge])))
        .child(div().flex_1())
        .child(div().id("issues-refresh").size(22).flex_none().flex().items_center().justify_center().rounded(5).cursor_pointer().hover((s) => s.bg(t.hover)).tooltip("Refresh")
          .on_click((_e, cx) => this.refresh(cx, true)).child(this.icon(this.loading ? "loader" : "refresh-cw", t.dim, 12))))
      .child(h_flex().flex_none().px(10).py(8).gap(4).border_b(1).border_color(t.border).children(FILTERS.map(([id, label]) => {
        const on = this.filter === id;
        return div().id(`issues-filter-${id}`).h(24).px(9).flex().items_center().rounded(6).cursor_pointer().text_size(12)
          .when(on, (e) => e.bg(t.selected).text_color(t.foreground)).when(!on, (e) => e.text_color(t.muted).hover((s) => s.bg(t.hover)))
          .on_click((_e, cx) => this.pick(id, cx)).child(label);
      })))
      .child(v_flex().id("issues-list").flex_1().min_h(0).overflow_y_scrollbar().p(6).gap(2)
        .children(list.map((i) => this.row(i, t, where)))
        .when(this.more && list.length > 0, (e) => e.child(div().id("issues-more").mx(4).my(6).h(28).flex_none().flex().items_center().justify_center().rounded(7)
          .border_1().border_color(t.border).text_size(12).text_color(t.muted).cursor_pointer().hover((s) => s.bg(t.hover))
          .on_click((_e, cx) => this.loadMore(cx)).child(this.loading ? "Loading…" : `Load ${PAGE} more`)))
        .when(!list.length, (e) => e.child(div().p(8).text_color(t.dim).child(empty))));
  }
}
