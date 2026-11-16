import { View, div, svg } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { run, exec, appHome, notify, openOverlay, theme, watchFolder } from "herdr";
import { ownItems, toCard, scanRefs } from "./model.js";
import { snapshot, texts, repos, location, panelShown, places, spaceAt, installedAgents, specflowHosts } from "./read.js";
import { pickOf, startLabel, startFor } from "./start.js";

const GH = () => `${appHome()}/bin/ghx`; // gh, with Bitbucket Cloud support (fixed path; exec takes argv, no shell)
const KIND_NAMES = { prd: "PRD", spec: "Spec", idea: "Idea" };
const ring = (t) => svg("mods/workspace-chrome/spinner.svg").size(12).flex_none().text_color(t.working).spin(900);
const busy = (t, text) => h_flex().p(8).gap(6).items_center().text_color(t.dim).child(ring(t)).child(text);
const idOf = (s) => s.replace(/[^A-Za-z0-9_-]/g, "_");

async function buildCards(snap) {
  const items = ownItems(snap.checkouts);
  if (!items.length) return [];
  const bare = items.map((i) => toCard(i, "", i.checkout));
  const text = await texts(bare.map((c) => c.file), snap.on);
  const main = snap.checkouts.find((c) => c.main);
  const ctx = {
    branches: snap.branches,
    worktrees: snap.checkouts.map(({ path, branch, main }) => ({ path, branch, main })),
    lanes: main?.wave?.lanes ?? [],
  };
  // Each checkout's autopilot pick, from its raw folders: autopilot enters a stale wip name too.
  const picks = new Map(snap.checkouts.map((c) => [c, pickOf(c)]));
  return items.map((i, k) => {
    const t = text[bare[k].file] ?? "";
    const card = toCard(i, t, i.checkout);
    return { ...card, chips: scanRefs(card, t, ctx), main: i.checkout.main, pick: picks.get(i.checkout) ?? null };
  });
}

export default class Runway extends View {
  init(_props, cx) {
    this.scope = "this";
    this.loc = null;
    this.context = null;
    this.thisData = null;
    this.allData = null;
    this.watching = null;
    this.parkedOpen = new Set();
    this.ticks = 0;
    this.loading = false;
    this.again = false;
    this.stale = false;
    this.agentsBy = new Map(); // machine -> { loading } | { list, hosts } | { error }
    this.refresh(cx);
    cx.timer.every(30000, (cx) => this.onTick(cx));
  }

  toggleScope(cx) {
    this.scope = this.scope === "this" ? "all" : "this";
    this.refresh(cx);
  }

  // A folder inside the loaded repo keys as that repo's root: a cd within it does not reload.
  keyOf({ cwd, on }) {
    const snap = this.thisData?.snap;
    const inside = snap && snap.on === on && cwd && snap.checkouts.some((c) => cwd === c.path || cwd.startsWith(c.path + "/"));
    return JSON.stringify([inside ? snap.root : cwd, on]);
  }

  locKey() {
    this.loc = location(this.loc);
    return this.keyOf(this.loc);
  }

  onTick(cx) {
    this.ticks = (this.ticks + 1) % 4;
    const isRemote = Boolean(this.loc?.on);
    if (this.scope === "all" || isRemote) {
      if (this.ticks === 0) this.refresh(cx);
    } else {
      this.refresh(cx);
    }
  }

  refresh(cx, rendering) {
    if (!panelShown("runway")) {
      this.stale = true;
      return;
    }
    if (this.loading) {
      this.again = true;
      return;
    }
    this.loading = true;
    this.stale = false;
    if (!rendering) cx.notify();
    cx.spawn(async (cx) => {
      try {
        if (this.scope === "all") await this.loadAll(cx);
        else await this.loadThis(cx);
      } finally {
        this.loading = false;
        cx.notify();
        if (this.again) {
          this.again = false;
          this.refresh(cx);
        }
      }
    });
  }

  updateWatch(snap, cx) {
    if (snap.on !== null) {
      this.watching = null;
      return;
    }
    const main = snap.checkouts?.find((c) => c.main);
    const mainPath = main?.path ?? snap.root;
    const dir = `${mainPath}/docs/dev/project-management`;
    if (this.watching === dir) return;
    this.watching = dir;
    // A token, not the folder: going back to an earlier folder must not revive its old loop.
    const id = this.watchId = (this.watchId ?? 0) + 1;
    cx.spawn(async (cx) => {
      for (;;) {
        try {
          await watchFolder(dir);
        } catch {
          // The 30 s timer keeps refreshing; the next load starts a new watch.
          if (this.watchId === id) this.watching = null;
          return;
        }
        if (this.watchId !== id || this.watching !== dir) return;
        if (this.scope === "this") this.refresh(cx);
      }
    });
  }

  async loadThis(cx) {
    const loc = location(this.loc);
    this.loc = loc;
    if (!loc.cwd) {
      this.thisData = { snap: null, cards: [], error: null };
      this.watching = null;
      return;
    }
    try {
      const snap = await snapshot(loc.cwd, loc.on);
      if (!snap) {
        this.thisData = { snap: null, cards: [], error: null };
        this.watching = null;
        return;
      }
      this.loadAgents(snap.on, cx);
      const cards = await buildCards(snap);
      this.thisData = { snap, cards, error: null };
      this.context = this.keyOf(loc);
      this.updateWatch(snap, cx);
    } catch (e) {
      const msg = String(e?.message ?? e) || "Could not read the repository";
      this.thisData = { snap: null, cards: [], error: msg };
      this.watching = null;
    }
  }

  // Once per machine; a failed listing is retried on the next refresh.
  loadAgents(on, cx) {
    const got = this.agentsBy.get(on);
    if (got && !got.error) return;
    this.agentsBy.set(on, { loading: true });
    cx.spawn(async (cx) => {
      try {
        const [list, hosts] = await Promise.all([installedAgents(on), specflowHosts(on)]);
        this.agentsBy.set(on, { list, hosts });
      } catch {
        this.agentsBy.set(on, { error: true });
      }
      cx.notify();
    });
  }

  startAgent(card, start, snap) {
    const task = start.task ? { task: start.task } : {};
    const s = spaceAt(card.checkout, places(snap.on), snap.checkouts.map((c) => c.path));
    if (s) {
      run("space.select", { id: s.id });
      run("tab.new", { space: s.id, folder: card.checkout, name: start.name, argv: start.argv, ...task });
    } else {
      run("space.new", { folder: card.checkout, tab: start.name, machine: snap.on ?? "", argv: start.argv, ...task });
    }
  }

  async loadAll(cx) {
    this.loadAgents(null, cx);
    try {
      const list = await repos();
      if (!list.length) {
        this.allData = { repos: [], emptyMsg: "No repo list at ~/.config/gita/repos.csv", error: null };
        return;
      }
      const repoData = [];
      for (let i = 0; i < list.length; i += 6) {
        const chunk = list.slice(i, i + 6);
        const snaps = await Promise.all(chunk.map((p) => snapshot(p, null).catch(() => null)));
        for (const snap of snaps) {
          if (!snap) continue;
          const cards = await buildCards(snap);
          if (cards.length > 0) repoData.push({ snap, cards });
        }
      }
      this.allData = { repos: repoData, emptyMsg: null, error: null };
    } catch (e) {
      const msg = String(e?.message ?? e) || "Could not read the repository";
      this.allData = { repos: [], emptyMsg: null, error: msg };
    }
  }

  openCard(card) {
    const kind = KIND_NAMES[card.kind] ?? card.kind;
    const rel = card.file.startsWith(card.checkout + "/") ? card.file.slice(card.checkout.length + 1) : card.file;
    run("tab.new", {
      name: `${card.number} ${kind}`,
      folder: card.checkout,
      argv: ["nvim", rel],
    });
  }

  openRef(chip, card, snap, cx) {
    cx.spawn(async () => {
      const val = String(chip.value);
      if (val.startsWith("http")) {
        try {
          const r = await exec("open", [val]);
          if (r.code !== 0) notify({ title: "Runway", body: r.stderr.trim() || `Could not open ${val}`, level: "error" });
        } catch (e) {
          notify({ title: "Runway", body: String(e?.message ?? e) || `Could not open ${val}`, level: "error" });
        }
        return;
      }
      try {
        const r = await exec(GH(), ["browse", val, "--no-browser"], { cwd: card.checkout, on: snap.on });
        if (r.code !== 0) {
          notify({ title: "Runway", body: r.stderr.trim() || `Could not open #${val}`, level: "error" });
          return;
        }
        const url = r.stdout.trim();
        const o = url ? await exec("open", [url]) : null;
        if (o?.code !== 0) notify({ title: "Runway", body: o?.stderr.trim() || `Could not open #${val}`, level: "error" });
      } catch (e) {
        notify({ title: "Runway", body: e?.stderr?.trim() || String(e?.message ?? e) || `Could not open #${val}`, level: "error" });
      }
    });
  }

  clickChip(chip, card, snap, cx) {
    if ((chip.type === "branch" && chip.path) || chip.type === "worktree") {
      const allTrees = snap.checkouts.map((c) => c.path);
      const s = spaceAt(chip.path, places(snap.on), allTrees);
      if (s) {
        run("space.select", { id: s.id });
      } else {
        // "" is this computer; an omitted machine would follow the focused space.
        run("space.new", { folder: chip.path, machine: snap.on ?? "" });
      }
      return;
    }
    if (chip.type === "branch") {
      const main = snap.checkouts.find((c) => c.main);
      openOverlay({
        mod: "my-worktree",
        kind: "dialog",
        width: 440,
        height: 260,
        props: { folder: main?.path ?? snap.root, machine: snap.on, branch: chip.value },
      });
      return;
    }
    if (chip.type === "issue" || chip.type === "pr" || chip.type === "ref") {
      this.openRef(chip, card, snap, cx);
    }
  }

  renderChip(chip, card, snap, t) {
    const chipId = idOf(`chip-${snap.root}-${card.id}-${chip.type}-${chip.value}`);
    if (chip.type === "lane") {
      return div().id(chipId).px(6).py(2).rounded(4).text_size(10).border_1().border_color(t.border).bg(t.raised).text_color(t.muted)
        .child(chip.label);
    }
    return div().id(chipId).px(6).py(2).rounded(4).text_size(10).cursor_pointer().border_1().border_color(t.border).bg(t.raised).text_color(t.muted)
      .hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => {
        cx.stop_propagation();
        this.clickChip(chip, card, snap, cx);
      })
      .child(chip.label);
  }

  renderCard(card, snap, t) {
    const isParked = card.group === "parked";
    const kind = KIND_NAMES[card.kind] ?? card.kind;
    const checkoutName = card.main ? "main" : card.checkout.split("/").pop();
    const meta = [card.stage, card.detail, card.next ? `next: ${card.next}` : null, checkoutName].filter(Boolean).join(" · ");
    const rootId = idOf(snap.root);

    return v_flex().id(`card-${rootId}-${card.id}`).flex_none().px(10).py(7).gap(3).rounded(7).cursor_pointer()
      .hover((s) => s.bg(t.hover))
      .when(isParked, (e) => e.opacity(0.6))
      .on_click((_e, _cx) => this.openCard(card))
      .child(h_flex().gap(6).items_center().min_w(0)
        .child(div().flex_none().px(4).py(1).rounded(3).text_size(10).font_semibold().bg(t.raised).text_color(t.muted).child(kind))
        .child(div().flex_none().text_size(11).text_color(t.dim).child(card.number))
        .child(div().flex_1().min_w(0).truncate().font_semibold().text_color(t.foreground).child(card.title)))
      .child(h_flex().gap(6).items_center().min_w(0).text_size(11).text_color(t.dim)
        .child(div().min_w(0).truncate().child(meta)))
      .when(isParked && Boolean(card.reason), (e) =>
        e.child(div().text_size(11).text_color(t.dim).truncate().child(card.reason)))
      .when(card.chips.length > 0, (e) =>
        e.child(h_flex().gap(4).flex_wrap().items_center().pt(2)
          .children(card.chips.map((chip) => this.renderChip(chip, card, snap, t)))))
      .when(Boolean(startLabel(card)), (e) => e.child(this.renderStart(card, snap, t)));
  }

  // The card's next stage, one button per installed agent, then why any button is off.
  renderStart(card, snap, t) {
    const got = this.agentsBy.get(snap.on);
    const env = { on: snap.on, pick: card.pick, specflow: got?.hosts ?? {} };
    const starts = (got?.list ?? []).map((a) => [a, startFor(card, a, env)]);
    const tips = [...new Set(starts.map(([, s]) => s.tip).filter(Boolean))];
    return v_flex().gap(3).pt(2).text_size(11)
      .child(h_flex().gap(4).flex_wrap().items_center()
        .child(div().text_color(t.dim).child(startLabel(card)))
        .when(!got || got.loading, (e) => e.child(ring(t)))
        .when(Boolean(got?.error), (e) => e.child(div().text_color(t.dim).child("Could not list agents")))
        .children(starts.map(([a, s]) =>
          div().id(idOf(`start-${snap.root}-${card.id}-${a.key}`)).px(6).py(2).rounded(4)
            .border_1().border_color(t.border).bg(t.raised).text_color(t.foreground)
            .when(s.disabled, (e) => e.opacity(0.5))
            .when(!s.disabled, (e) => e.cursor_pointer().hover((st) => st.bg(t.hover)))
            .on_click((_e, cx) => {
              cx.stop_propagation();
              if (!s.disabled) this.startAgent(card, s, snap);
            })
            .child(s.gated ? a.name : `${a.name} · ungated`))))
      .children(tips.map((tip) => div().text_color(t.dim).child(tip)));
  }

  renderGroups(snap, cards, t) {
    const prds = cards.filter((c) => c.group === "prd");
    const specs = cards.filter((c) => c.group === "spec");
    const ideas = cards.filter((c) => c.group === "idea");
    const parked = cards.filter((c) => c.group === "parked");
    const elements = [];
    const rootId = idOf(snap.root);

    if (prds.length > 0) {
      elements.push(
        div().id(`group-prds-${rootId}`).px(10).pt(8).pb(2).text_size(11).font_semibold().text_color(t.muted).child("PRDs"),
        ...prds.map((c) => this.renderCard(c, snap, t))
      );
    }
    if (specs.length > 0 || snap.specflow === "missing") {
      elements.push(
        div().id(`group-specs-${rootId}`).px(10).pt(8).pb(2).text_size(11).font_semibold().text_color(t.muted).child("Specs")
      );
      if (snap.specflow === "missing") {
        elements.push(div().id(`missing-specflow-${rootId}`).px(10).py(4).text_size(12).text_color(t.dim).child("specflow not found"));
      }
      elements.push(...specs.map((c) => this.renderCard(c, snap, t)));
    }
    if (ideas.length > 0) {
      elements.push(
        div().id(`group-ideas-${rootId}`).px(10).pt(8).pb(2).text_size(11).font_semibold().text_color(t.muted).child("Ideas"),
        ...ideas.map((c) => this.renderCard(c, snap, t))
      );
    }
    if (parked.length > 0) {
      const open = this.parkedOpen.has(snap.root);
      elements.push(
        h_flex().id(`parked-toggle-${rootId}`).px(10).py(4).gap(6).items_center().rounded(5).cursor_pointer()
          .hover((s) => s.bg(t.hover))
          .on_click((_e, cx) => {
            if (this.parkedOpen.has(snap.root)) this.parkedOpen.delete(snap.root);
            else this.parkedOpen.add(snap.root);
            cx.notify();
          })
          .child(div().text_size(10).text_color(t.dim).child(open ? "▾" : "▸"))
          .child(div().text_size(11).font_semibold().text_color(t.muted).child(`Parked (${parked.length})`))
      );
      if (open) {
        elements.push(...parked.map((c) => this.renderCard(c, snap, t)));
      }
    }
    return elements;
  }

  renderContent(t) {
    if (this.scope === "all") {
      if (this.allData?.error) return [div().p(8).text_color(t.dim).child(this.allData.error)];
      if (!this.allData && this.loading) return [busy(t, "Reading every repo…")];
      if (this.allData?.emptyMsg) return [div().p(8).text_color(t.dim).child(this.allData.emptyMsg)];
      const repos = this.allData?.repos ?? [];
      if (!repos.length) return [div().p(8).text_color(t.dim).child("Nothing waiting")];
      return repos.flatMap((r) => [
        div().id(`repo-${idOf(r.snap.root)}`).px(10).pt(8).pb(2).font_semibold().text_size(13).text_color(t.foreground).child(r.snap.repo),
        ...this.renderGroups(r.snap, r.cards, t),
      ]);
    }
    if (this.thisData?.error) return [div().p(8).text_color(t.dim).child(this.thisData.error)];
    if (!this.thisData && this.loading) return [busy(t, "Reading the repository…")];
    if (this.thisData && this.thisData.snap === null) return [div().p(8).text_color(t.dim).child("Not in a repository")];
    const snap = this.thisData?.snap;
    const cards = this.thisData?.cards ?? [];
    // With no cards, renderGroups draws only the Specs "specflow not found" line, when it applies.
    if (!cards.length) return [...(snap ? this.renderGroups(snap, [], t) : []), div().p(8).text_color(t.dim).child("Nothing waiting")];
    return this.renderGroups(snap, cards, t);
  }

  render(cx) {
    if (panelShown("runway")) {
      const key = this.locKey();
      if (this.stale || (this.scope === "this" && key !== this.context)) {
        this.context = key;
        this.refresh(cx, true);
      }
    }
    const t = theme();
    const count = this.scope === "all"
      ? (this.allData?.repos ?? []).reduce((sum, r) => sum + r.cards.filter((c) => c.group !== "parked").length, 0)
      : (this.thisData?.cards ?? []).filter((c) => c.group !== "parked").length;

    return v_flex().id("runway").size_full().min_h(0).rounded(10).overflow_hidden().bg(t.background).border_1().border_color(t.border).text_color(t.foreground).text_size(13)
      .child(h_flex().h(42).flex_none().px(14).gap(8).items_center().border_b(1).border_color(t.border)
        .child(div().font_semibold().whitespace_nowrap().child("Runway"))
        .child(div().px(5).py(1).rounded(4).border_1().border_color(t.border).text_size(10).text_color(t.muted).whitespace_nowrap().child(String(count)))
        .child(div().flex_1())
        .when(this.loading, (e) => e.child(ring(t)))
        .child(div().id("runway-scope-chip").px(8).py(2).rounded(6).text_size(11).cursor_pointer()
          .border_1().border_color(t.border).bg(t.raised).text_color(t.foreground)
          .hover((s) => s.bg(t.hover))
          .on_click((_e, cx) => this.toggleScope(cx))
          .child(this.scope === "all" ? "All repos" : "This repo")))
      .child(v_flex().id("runway-list").flex_1().min_h(0).overflow_y_scrollbar().p(6).gap(2)
        .children(this.renderContent(t)));
  }
}
