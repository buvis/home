import { View, div, svg } from "gpui-kit";
import { v_flex, h_flex, Input, InputState } from "gpui-base";
import { run, exec, appHome, readTextFile, notify as notifyRaw, openOverlay, theme, watchFolder, focused, checking } from "herdr";
import { notify, home, window, props, shared, setShared } from "herdr";
import { ownItems, toCard, scanRefs, parseFrontmatter, jumpFor } from "./model.js";
import { snapshot, texts, repos, location, panelShown, places, spaceAt, installedAgents, specflowHosts } from "./read.js";
import { pickOf, startLabel, startFor } from "./start.js";
import { laneBranch, planLane, openLane, actionFor } from "./lane.js";

const GH = () => `${appHome()}/bin/ghx`; // gh, with Bitbucket Cloud support (fixed path; exec takes argv, no shell)
const KIND_NAMES = { prd: "PRD", spec: "Spec", idea: "Idea" };
const ring = (t) => svg("mods/workspace-chrome/spinner.svg").size(12).flex_none().text_color(t.working).spin(900);
const busy = (t, text) => h_flex().p(8).gap(6).items_center().text_color(t.dim).child(ring(t)).child(text);
const idOf = (s) => s.replace(/[^A-Za-z0-9_-]/g, "_");
const PRDS = "docs/dev/project-management/prds";
const LOOP = { name: "autoclaude", argv: ["autoclaude"] };

// Mutations take paths after "--"; a nonzero exit is an error with the program's message.
// Only status 1 means absent; any other failure is unknown, never treated as absent.
async function there(path, on) {
  const r = await exec("test", ["-e", path], { on });
  if (r.code !== 0 && r.code !== 1) throw new Error(r.stderr.trim() || `Could not check ${path}`);
  return r.code === 0;
}
async function checked(cmd, args, options) {
  const r = await exec(cmd, args, options);
  if (r.code !== 0) throw new Error(r.stderr.trim() || `${cmd} failed`);
  return r;
}
// Lanes open on this computer only.
const LANE_IO = {
  exists: (path) => there(path, null),
  git: (args, cwd) => exec("git", ["-C", cwd, ...args], { timeout: 300000 }),
  mkdir: (path) => checked("mkdir", ["-p", "--", path]),
  move: (from, to) => checked("mv", ["-n", "--", from, to]),
  remove: (path) => checked("rm", ["-f", "--", path]),
};
const failure = (e) => notify({ title: "Runway", body: String(e?.message ?? e), level: "error" });
const countKey = ({ cwd, on }) => JSON.stringify([cwd, on ?? null]);

function publishCount(loc, count) {
  const key = countKey(loc);
  const old = shared("runway.count");
  if (old?.key !== key || old?.count !== count) setShared("runway.count", { key, count });
}

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
  // Each checkout's own .agents/specflow.json decides its intake action; a failed probe reads as no config.
  const configs = new Map(await Promise.all(snap.checkouts.map(async (c) =>
    [c, await there(`${c.path}/.agents/specflow.json`, snap.on).catch(() => false)])));
  return items.map((i, k) => {
    const t = text[bare[k].file] ?? "";
    const card = toCard(i, t, i.checkout);
    return { ...card, chips: scanRefs(card, t, ctx), main: i.checkout.main, pick: picks.get(i.checkout) ?? null,
      fm: parseFrontmatter(t), config: configs.get(i.checkout) ?? false };
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
    this.busy = new Set(); // `${root}:${card id}` while its lane or un-park runs
    this.laning = false;
    this.countOnly = Boolean(props()?.countOnly);
    if (checking()) return;
    if (this.countOnly) {
      cx.timer.every(30000, (cx) => this.refreshCount(cx));
      return;
    }
    this.refresh(cx);
    cx.timer.every(30000, (cx) => this.onTick(cx));
  }

  refreshCount(cx) {
    if (checking() || window()?.visible === false) return;
    const loc = this.loc = location(this.loc);
    const key = countKey(loc), now = Date.now();
    if (!loc.cwd || (this.countKey === key && now - this.countAt < (loc.on ? 120000 : 30000))) return;
    this.countKey = key; this.countAt = now;
    cx.spawn(async () => {
      try {
        const snap = await snapshot(loc.cwd, loc.on);
        if (this.countKey !== key || this.countAt !== now) return;
        const count = snap ? ownItems(snap.checkouts)
          .filter((item) => toCard(item, "", item.checkout).group !== "parked").length : 0;
        publishCount(loc, count);
      } catch {
        // A failed read is unknown until the next poll.
        if (this.countKey === key && this.countAt === now) publishCount(loc, null);
      }
    });
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
    // No poll while the window is hidden (minimized, covered, on another Space): render catches up.
    if (window()?.visible === false) { this.stale = true; return; }
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
      if (countKey(location(this.loc)) === countKey(loc)) publishCount(loc, cards.filter((card) => card.group !== "parked").length);
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

  startAgent(card, start, snap, agent) {
    const task = start.task ? { task: start.task } : {};
    const argv = [...start.argv];
    // autocodex and the whole-queue autoclaude are shell functions that call run-agent themselves.
    const direct = agent && argv[0] !== "autocodex";
    if (direct && !/(^|[/\\])run-agent$/.test(argv[0])) argv.unshift("run-agent");
    if (direct && agent.key === "codex" && !argv.includes("--no-daemon")) {
      argv.splice(argv[1] === "--no-sandbox" ? 3 : 2, 0, "--no-daemon");
    }
    const s = spaceAt(card.checkout, places(snap.on), snap.checkouts.map((c) => c.path));
    if (s) {
      run("space.select", { id: s.id });
      run("tab.new", { space: s.id, folder: card.checkout, name: start.name, argv, ...task });
    } else {
      run("space.new", { folder: card.checkout, tab: start.name, machine: snap.on ?? "", argv, ...task });
    }
  }

  askLane(card, snap, key, cx) {
    if (this.laning) return;
    const input = InputState.new({ value: laneBranch(card), placeholder: "Branch name" });
    const draft = this.laneDraft = { key, input };
    this.pickingAgent = null;
    input.on("submit", (_e, cx) => this.openLaneFor(card, snap, draft, cx));
    cx.timer.after(0, () => { if (this.laneDraft === draft) input.focus(); });
    cx.notify();
  }

  openLaneFor(card, snap, draft, cx) {
    if (this.laning || this.laneDraft !== draft) return;
    const branch = draft.input.value().trim();
    this.laning = true;
    this.busy.add(draft.key);
    cx.notify();
    cx.spawn(async (cx) => {
      try {
        const raw = await readTextFile(`${appHome()}/settings.json`);
        const directory = (raw === null ? {} : JSON.parse(raw))?.worktrees?.directory ?? "~/.herdr/worktrees";
        if (typeof directory !== "string" || !directory.trim()) throw new Error("worktrees.directory must be a non-empty path");
        const pathRoot = directory === "~" || directory.startsWith("~/") ? home() + directory.slice(1) : directory;
        if (!pathRoot.startsWith("/")) throw new Error("worktrees.directory must be absolute or start with ~/");
        const main = snap.checkouts.find((c) => c.main).path;
        const plan = planLane(card, { name: snap.repo, main, branches: snap.branches, worktrees: snap.checkouts },
          home(), branch, pathRoot.replace(/\/+$/, ""));
        if (plan.error) throw new Error(plan.error);
        const check = await LANE_IO.git(["check-ref-format", "--branch", branch], main);
        if (check.code !== 0 || check.stdout.trim() !== branch) throw new Error("Enter a valid Git branch name");
        const { path } = await openLane(plan, LANE_IO);
        this.laneDraft = null;
        run("space.new", { folder: path, machine: "" });
        notify({ title: "Runway", body: `${card.file.split("/").pop()}: new worktree at ${path}` });
      } catch (e) {
        failure(e);
      } finally {
        this.laning = false;
        this.busy.delete(draft.key);
        cx.notify();
        this.refresh(cx);
      }
    });
  }

  // hold -> backlog on the card's machine, never over a queued PRD, then checked.
  unpark(card, snap, key, cx) {
    if (this.busy.has(key)) return;
    const name = card.file.split("/").pop();
    const dst = `${card.checkout}/${PRDS}/backlog/${name}`;
    const on = snap.on;
    this.busy.add(key);
    cx.notify();
    cx.spawn(async (cx) => {
      try {
        if (await there(dst, on)) throw new Error(`${name} is already in backlog; nothing moved`);
        await checked("mv", ["-n", "--", card.file, dst], { on });
        if (!(await there(dst, on)) || (await there(card.file, on))) {
          notify({ title: "Runway", body: `Un-park did not complete for ${name}`, level: "error" });
        }
      } catch (e) {
        failure(e);
      } finally {
        this.busy.delete(key);
        cx.notify();
        this.refresh(cx);
      }
    });
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
    // Errors lead back to where the click came from (my-toast's Go to terminal).
    const f = focused(), at = f?.terminal ? { terminal: f.terminal } : f?.pane ? { pane: f.pane } : null;
    const notify = (n) => notifyRaw({ ...n, ...(at ? { action: { name: "pane.focus", args: at } } : {}) });
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

  clickChip(chip, card, snap, cx, modifiers) {
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
      const jump = jumpFor(chip, this.scope, modifiers);
      if (jump === "browser") {
        this.openRef(chip, card, snap, cx);
        return;
      }
      setShared("runway.show", { kind: jump.kind, number: jump.number, at: Date.now() });
      run("layout.select", { stack: "panel-body", child: jump.panel });
      run("layout.show", { id: "panel" });
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
      .on_click((e, cx) => {
        cx.stop_propagation();
        this.clickChip(chip, card, snap, cx, e?.modifiers);
      })
      .child(chip.label);
  }

  renderCard(card, snap, t) {
    const isParked = card.group === "parked";
    const kind = KIND_NAMES[card.kind] ?? card.kind;
    const checkoutName = card.main ? "main" : card.checkout.split("/").pop();
    const meta = [card.stage, card.detail, card.next ? `next: ${card.next}` : null, checkoutName].filter(Boolean).join(" · ");
    const rootId = idOf(snap.root);
    const controls = this.renderControls(card, snap, t);

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
      .when(Boolean(controls), (e) => e.child(controls))
      .when(Boolean(startLabel(card)) && this.laneDraft?.key !== this.cardKey(card, snap), (e) => e.child(this.renderStart(card, snap, t)));
  }

  // Worktree and housekeeping actions, with a busy ring during changes.
  renderControls(card, snap, t) {
    const key = this.cardKey(card, snap);
    const claude = this.agentsBy.get(snap.on)?.list?.find((a) => a.key === "claude");
    const local = snap.on === null;
    const action = actionFor(card, card.fm, { specflow: card.config });
    const needsClaude = action?.kind === "agent" && !claude;
    const button = (id, label, act, disabled) =>
      div().id(idOf(`${id}-${snap.root}-${card.id}`)).px(6).py(2).rounded(4)
        .border_1().border_color(t.border).bg(t.raised).text_color(t.foreground)
        .when(disabled, (e) => e.opacity(0.5))
        .when(!disabled, (e) => e.cursor_pointer().hover((st) => st.bg(t.hover)))
        .on_click((_e, cx) => {
          cx.stop_propagation();
          if (!disabled) act(cx);
        })
        .child(label);
    // A held main spec is still a main spec; parked PRDs get Un-park, not a lane.
    const lane = local && card.main &&
      (card.kind === "spec" || (card.kind === "prd" && card.stage === "backlog" && card.group !== "parked"));
    const draft = lane && this.laneDraft?.key === key ? this.laneDraft : null;
    const buttons = [
      lane && !draft && button("lane", "Create worktree", (cx) => this.askLane(card, snap, key, cx), this.laning),
      action && button("action", action.label, (cx) => (action.kind === "move"
        ? this.unpark(card, snap, key, cx)
        : this.startAgent(card, { name: `${card.number} ${claude.name}`, argv: claude.run, task: action.task }, snap, claude)),
      Boolean(action.disabled || needsClaude)),
    ].filter(Boolean);
    if (!buttons.length && !draft) return null;
    const tip = action?.tip ?? (needsClaude ? "Needs Claude Code" : null);
    return v_flex().gap(3).pt(2).text_size(11)
      .child(h_flex().gap(4).flex_wrap().items_center().children(buttons)
        .when(this.busy.has(key), (e) => e.child(ring(t))))
      .when(Boolean(draft), (e) => e.child(v_flex().gap(4)
        .on_click((_e, cx) => cx.stop_propagation())
        .on_key_down((event, cx) => {
          if (event.key !== "escape" || this.laning) return;
          this.laneDraft = null; cx.stop_propagation(); cx.notify();
        })
        .child(div().text_color(t.muted).child("Branch name"))
        .child(Input.new(draft.input).w_full().h(30).px(8).rounded(6).border_1().border_color(t.accent).bg(t.background).text_color(t.foreground))
        .child(h_flex().gap(4)
          .child(button("cancel-lane", "Cancel", (cx) => { this.laneDraft = null; cx.notify(); }, this.laning))
          .child(button("confirm-lane", "Create worktree", (cx) => this.openLaneFor(card, snap, draft, cx), this.laning)))))
      .when(Boolean(tip), (e) => e.child(div().text_color(t.dim).child(tip)));
  }

  cardKey(card, snap) {
    return JSON.stringify([snap.on, snap.root, card.checkout, card.id]);
  }

  renderStart(card, snap, t) {
    const got = this.agentsBy.get(snap.on);
    const key = this.cardKey(card, snap);
    const picking = this.pickingAgent === key;
    const env = { on: snap.on, pick: card.pick, specflow: got?.hosts ?? {} };
    const starts = (got?.list ?? []).map((a) => [a, startFor(card, a, env)]);
    const tips = picking ? [...new Set(starts.map(([, s]) => s.tip).filter(Boolean))] : [];
    return v_flex().gap(3).pt(2).text_size(11)
      .child(h_flex().gap(4).flex_wrap().items_center()
        .child(div().text_color(t.dim).child(startLabel(card)))
        .child(div().id(idOf(`send-${key}`)).px(6).py(2).rounded(4)
          .border_1().border_color(t.border).bg(t.raised).text_color(t.foreground)
          .cursor_pointer().hover((st) => st.bg(t.hover))
          .on_click((_e, cx) => {
            cx.stop_propagation();
            this.pickingAgent = picking ? null : key; cx.notify();
          }).child(picking ? "Cancel" : "Send to agent…")))
      .when(picking, (e) => e.child(v_flex().gap(4).p(6).rounded(6).border_1().border_color(t.border).bg(t.popover)
        .child(div().px(4).child("Choose an agent"))
        .when(!got || got.loading, (list) => list.child(busy(t, "Checking installed agents…")))
        .when(Boolean(got?.error), (list) => list.child(div().text_color(t.dim).child("Could not list agents")))
        .when(got?.list?.length === 0, (list) => list.child(div().text_color(t.dim).child("No agents available")))
        .children(starts.map(([a, s]) =>
          div().id(idOf(`start-${snap.root}-${card.id}-${a.key}`)).px(6).py(2).rounded(4)
            .border_1().border_color(t.border).bg(t.raised).text_color(t.foreground)
            .when(s.disabled, (e) => e.opacity(0.5))
            .when(!s.disabled, (e) => e.cursor_pointer().hover((st) => st.bg(t.hover)))
            .on_click((_e, cx) => {
              cx.stop_propagation();
              if (!s.disabled && this.pickingAgent === key) {
                this.pickingAgent = null;
                this.startAgent(card, s, snap, a);
                cx.notify();
              }
            })
            .child(s.gated ? a.name : `${a.name} · ungated`)))))
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

  renderRepoHeader(snap, cards, t) {
    const next = snap.on === null && cards.find((card) =>
      card.main && card.kind === "prd" && card.pick === card.file.split("/").pop());
    return h_flex().id(`repo-${idOf(snap.root)}`).px(10).pt(8).pb(2).gap(8).items_center()
      .child(div().flex_1().min_w(0).truncate().font_semibold().text_size(13).text_color(t.foreground).child(snap.repo))
      .when(Boolean(next), (e) => e.child(div().id(`run-queue-${idOf(snap.root)}`).flex_none().px(6).py(2).rounded(4)
        .border_1().border_color(t.border).bg(t.raised).text_size(11).text_color(t.foreground)
        .cursor_pointer().hover((st) => st.bg(t.hover))
        .tooltip(`Resumes work in progress, then implements backlog PRDs in ${next.checkout}`)
        .on_click(() => this.startAgent(next, LOOP, snap))
        .child("Implement backlog")));
  }

  renderContent(t) {
    if (this.scope === "all") {
      if (this.allData?.error) return [div().p(8).text_color(t.dim).child(this.allData.error)];
      if (!this.allData && this.loading) return [busy(t, "Reading every repo…")];
      if (this.allData?.emptyMsg) return [div().p(8).text_color(t.dim).child(this.allData.emptyMsg)];
      const repos = this.allData?.repos ?? [];
      if (!repos.length) return [div().p(8).text_color(t.dim).child("Nothing waiting")];
      return repos.flatMap((r) => [
        this.renderRepoHeader(r.snap, r.cards, t),
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
    return [this.renderRepoHeader(snap, cards, t), ...this.renderGroups(snap, cards, t)];
  }

  render(cx) {
    if (this.countOnly) {
      this.refreshCount(cx);
      return div();
    }
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
