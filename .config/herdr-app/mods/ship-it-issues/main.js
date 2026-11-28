// Issues: every open issue of the repo, in the side panel (GitHub, GitLab and
// Bitbucket). A row opens to its details and actions: start an agent on it, open
// its worktree, the host's page, copy link. Starting an agent first makes sure
// the issue has a worktree and asks which branch to use before creating one. The agent
// starts only once the checkout exists and opens as a space.
//
// Its logic (forge, worktrees, agents) is in issues.js. data.js is a copy of
// ship-it-prs's.

import { View, div, svg } from "gpui-kit";
import { v_flex, h_flex, Input, InputState } from "gpui-base";
import { exec, shared, setShared, notify, theme, nextCommand, checking } from "herdr";
import { READ, location, ago, panelShown, Recent, tilde, backTo } from "./data.js";
import { forgeOf, FORGE_NAME, listIssues, checkoutState, issueTree, branchFor, places, spaceAt, ensureWorktree, installedAgents, openWorktree } from "./issues.js";

const ICON = (name) => `mods/ship-it/icons/${name}.svg`;
const FILTERS = [["all", "All"], ["mine", "Assigned to me"]];
const PAGE = 15;

export default class Issues extends View {
  init(_p, cx) {
    this.issues = []; this.filter = "all"; this.last = null; this.limit = PAGE; this.trees = {}; this.links = {};
    this.expanded = null; this.agents = {}; // installed agents by machine
    this.memo = new Recent(12);
    this.bumpSeen = shared("ship-it.bump"); // the bar saw a PR or an issue appear, merge or close: ask again
    if (checking()) return;
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
        const [list, { trees, links }] = await Promise.all([listIssues(forge, root, on, filter === "mine", limit), checkoutState(root, on)]);
        if (this.key() !== context || this.filter !== filter) return;
        this.root = root; this.on = on; this.forge = forge; this.trees = trees; this.links = links;
        if (list.error) { this.error = list.error; this.issues = []; return; }
        this.issues = list.issues; this.more = this.issues.length >= limit; this.error = null;
        this.memo.set(memo, { root, on, forge, trees, links, issues: this.issues, more: this.more, limit });
        // Shared state redraws every mod: write it only when it changes.
        const count = this.issues.length, was = shared("ship-it.issues");
        if (filter === "all" && (was?.root !== root || (was?.on ?? null) !== (on ?? null) || was?.count !== count || was?.more !== this.more)) setShared("ship-it.issues", { root, on: on ?? null, count, more: this.more });
      } catch (e) { if (this.key() === context) this.error = String(e); }
      finally { if (this.loading === started) this.loading = 0; cx.notify(); }
    });
    // The agents this machine has, once.
    if (this.agents[on ?? ""] === undefined) {
      this.agents[on ?? ""] = [];
      cx.spawn(async (cx) => {
        try { this.agents[on ?? ""] = await installedAgents(on); }
        catch (e) { delete this.agents[on ?? ""]; this.error = this.error ?? `Agents: ${e}`; }
        cx.notify();
      });
    }
  }

  memoKey() { return `${this.context}#${this.filter}`; }

  recall() {
    this.root = null; this.issues = []; this.error = null; this.more = false; this.trees = {}; this.links = {}; this.forge = null;
    this.draft = null; this.pickingAgent = null;
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
  work(issue, agent, cx, name) {
    if (this.busy || !this.root) return;
    const root = this.root, on = this.on, context = this.context, back = backTo();
    this.busy = { number: issue.number, step: name === undefined ? "Checking worktree…" : "Checking out…" }; cx.notify();
    cx.spawn(async (cx) => {
      try {
        const wt = await ensureWorktree(root, on, issue, name);
        const current = this.context === context && this.root === root && this.on === on;
        if (!wt.path) {
          if (current && this.expanded === issue.number) this.askBranch(issue, agent, wt.existing, cx);
          return;
        }
        if (current) {
          this.trees = wt.trees;
          this.links = wt.links;
          this.draft = null;
        }
        if (wt.created) notify({ title: `Worktree for #${issue.number}`, body: `${wt.branch} · ${tilde(wt.path)}`, level: "info", timeout: 3000 });
        openWorktree(wt.path, on, wt.trees, issue, wt.branch, agent);
      } catch (e) { notify({ title: `Couldn't start #${issue.number}`, body: String(e.message ?? e), level: "error", timeout: 8000, ...back }); }
      finally { this.busy = null; cx.notify(); }
    });
  }

  askBranch(issue, agent, existing, cx) {
    const input = InputState.new({ value: branchFor(issue), placeholder: "Branch name" });
    const draft = this.draft = { number: issue.number, input, agent, existing };
    input.on("submit", (_e, cx) => this.confirmBranch(issue, draft, cx));
    cx.timer.after(0, () => { if (this.draft === draft) input.focus(); });
  }

  confirmBranch(issue, draft, cx) {
    if (this.draft !== draft || this.expanded !== issue.number) return;
    this.work(issue, draft.agent, cx, draft.input.value().trim());
  }

  // "loader" is the shared busy ring (same as the tab bar, agents list and Ship bar).
  icon(name, color, size = 14) {
    if (name === "loader") return svg("mods/workspace-chrome/spinner.svg").size(size).flex_none().text_color(theme().working).spin(900);
    return svg(ICON(name)).size(size).flex_none().text_color(color);
  }

  row(issue, t, where) {
    const path = issueTree(this.trees, issue, this.links), space = spaceAt(path, where, Object.values(this.trees)), busy = this.busy?.number === issue.number;
    const open = this.expanded === issue.number;
    return v_flex().id(`issue-${issue.number}`).flex_none().px(10).py(7).gap(3).rounded(7).cursor_pointer()
      .hover((s) => s.bg(t.hover)).when(open, (e) => e.bg(t.hover))
      .on_click((_e, cx) => { this.expanded = open ? null : issue.number; this.draft = null; this.pickingAgent = null; cx.notify(); })
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
        .when(busy, (e) => e.child(this.icon("loader", t.muted, 12))))
      .when(open, (e) => e.child(this.details(issue, path, space, t)));
  }

  copy(issue) {
    this.cx.write_to_clipboard(issue.url);
    notify({ title: `#${issue.number} link copied`, body: issue.url, level: "info", timeout: 2000 });
  }

  details(issue, path, space, t) {
    const busy = this.busy?.number === issue.number, agents = this.agents[this.on ?? ""] ?? [];
    const draft = this.draft?.number === issue.number ? this.draft : null;
    const picking = this.pickingAgent === issue.number;
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
      .when(Boolean(draft), (e) => e.child(v_flex().gap(5)
        .on_click((_e, cx) => cx.stop_propagation())
        .on_key_down((event, cx) => {
          if (event.key !== "escape" || this.busy) return;
          this.draft = null; cx.stop_propagation(); cx.notify();
        })
        .child(div().child("Branch name"))
        .child(Input.new(draft.input).w_full().h(30).px(8).rounded(6).border_1().border_color(t.accent).bg(t.background).text_color(t.foreground))
        .when(draft.existing && draft.existing !== branchFor(issue), (e) => e.child(
          button("existing-branch", "git-branch", "Use existing branch", false, () => {
            if (!this.busy) { draft.input.set_value(draft.existing); draft.input.focus(); }
          }).tooltip(draft.existing)))
        .child(h_flex().gap(6).flex_wrap()
          .child(button("cancel-branch", "x", "Cancel", false, (cx) => {
            if (!this.busy) { this.draft = null; cx.notify(); }
          }))
          .child(button("confirm-branch", busy ? "loader" : "git-branch-plus",
            busy ? this.busy.step : draft.agent ? `Create and start ${draft.agent.name}` : "Create worktree", true,
            (cx) => this.confirmBranch(issue, draft, cx))))))
      .when(!draft, (e) => e.child(h_flex().pt(3).gap(6).flex_wrap()
        .child(button("send-to-agent", busy ? "loader" : picking ? "x" : "rocket", busy ? this.busy.step : picking ? "Cancel" : "Send to agent…", !picking, (cx) => {
          if (this.busy) return;
          this.pickingAgent = picking ? null : issue.number; cx.notify();
        }))
        .child(button("tree", path ? "folder" : "git-branch-plus", path ? (space ? "Go to space" : "Open worktree") : "Create worktree", false, (cx) => {
          this.pickingAgent = null; this.work(issue, null, cx);
        }))
        .child(button("host", "external-link", FORGE_NAME[this.forge] ?? "Open", false, (cx) => cx.open_url(issue.url)))
        .child(button("copy", "copy", "Copy link", false, () => this.copy(issue)))))
      .when(!draft && picking, (e) => e.child(v_flex().gap(4).p(6).rounded(6).border_1().border_color(t.border).bg(t.popover)
        .child(div().px(4).child("Choose an agent"))
        .children(agents.map((agent) => button(`agent-${agent.key}`, "rocket", agent.name, false, (cx) => {
          if (this.busy || this.pickingAgent !== issue.number) return;
          this.pickingAgent = null; this.work(issue, agent, cx);
        })))
        .when(!agents.length, (list) => list.child(div().px(4).child("No agents available")))));
  }

  render(cx) {
    const show = shared("runway.show"); if (show?.kind === "issue" && show.at !== this.showSeen && Date.now() - show.at < 5000) { this.showSeen = show.at; if (this.filter !== "all") { this.filter = "all"; this.limit = PAGE; this.recall(); this.stale = true; } this.expanded = show.number; this.draft = null; this.pickingAgent = null; }
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
