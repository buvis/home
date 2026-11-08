import { View, div, svg, image } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { theme, spaces, panes, machines, knownAgents, run, openOverlay, closeOverlay, props, window, keys, shared, setShared, hc } from "herdr";

// The last agents each machine reported, shown at once while knownAgents() checks again.
const KNOWN = "new-menu.agents";
// The last machine list from herdr-core, so the picker can show instantly next time.
const MACHINES = "new-menu.machines";

function shortcut(name) {
  const k = keys().find(b => b.section === "global" && b.action === name);
  if (!k?.keys.trim()) return "";
  const mac = window()?.platform === "macos";
  const names = mac ? { ctrl: "⌃", alt: "⌥", shift: "⇧", cmd: "⌘", fn: "fn" } : { ctrl: "Ctrl", alt: "Alt", shift: "Shift", cmd: "Super", fn: "Fn" };
  const alias = { secondary: mac ? "cmd" : "ctrl", super: "cmd", win: "cmd" };
  return k.keys.trim().split(/\s+/).map(stroke => {
    const parts = stroke.split("-");
    let key = parts.pop();
    if (key === "") { key = "-"; parts.pop(); }
    const held = new Set(parts.map(m => alias[m.toLowerCase()] ?? m.toLowerCase()));
    if (/^[A-Z]$/.test(key)) held.add("shift");
    const label = key.length === 1 ? key.toUpperCase() : key[0].toUpperCase() + key.slice(1).toLowerCase();
    return [...Object.keys(names).filter(m => held.has(m)).map(m => names[m]), label].join(mac ? "" : "+");
  }).join(" ");
}

export default class NewMenu extends View {
  init(_props, cx) {
    this.handle = cx.focus_handle();
    this.handle.focus();
    // All machines known to herdr-core, not just those with a loaded layout
    // document. An empty remote you've never opened still shows up here.
    this.remotes = (shared(MACHINES) ?? []);
    cx.spawn(async cx => {
      try {
        const r = await hc(["machine", "ls", "--json"]);
        if (r.code === 0) {
          this.remotes = (JSON.parse(r.stdout).machines ?? []).filter(m => !m.temporary).map(m => m.name);
          setShared(MACHINES, this.remotes);
        }
      } catch {}
      cx.notify();
    });
    if (props()?.pick) return; // machine picker variant: no agents to load
    const machine = spaces().find(s => s.active)?.machine;
    const where = machine ?? "";
    this.agents = shared(KNOWN)?.[where] ?? [];
    cx.spawn(async cx => {
      try {
        this.agents = await knownAgents({ on: machine });
        setShared(KNOWN, { ...shared(KNOWN), [where]: this.agents });
      }
      catch { this.failed = true; }
      cx.notify();
    });
  }
  row(id, icon, name, action, hint = "", enabled = true) {
    const t = theme();
    return h_flex().id(id).h(31).px(9).gap(10).rounded(7).items_center().flex_none()
      .text_color(enabled ? t.foreground : t.dim).when(enabled, el => el.hover(s => s.bg(t.selected)))
      .on_click(() => { if (enabled) { closeOverlay(props().overlay); action(); } })
      .child(icon).child(div().flex_1().child(name)).child(div().text_size(11).text_color(t.dim).child(hint));
  }
  // Every known machine, this computer first. Sources merged so an empty remote
  // still appears: herdr-core's machine list, machines() layout docs, and any
  // machine that currently owns a space.
  machineNames() {
    const names = new Set([
      ...(this.remotes ?? []),
      ...machines().map(m => m.name).filter(Boolean),
      ...spaces().map(s => s.machine).filter(Boolean),
    ]);
    return [...names].sort();
  }
  machineList() {
    return [{ name: null, label: "This computer" }, ...this.machineNames().map(n => ({ name: n, label: n }))];
  }
  // Create a space on a machine. null is this computer (space.new with no
  // machine), a name is a remote.
  newSpace(machine) {
    run("space.new", machine == null ? {} : { machine });
  }
  renderPicker(t) {
    const list = this.machineList();
    return v_flex().min_h(0).w_full().h(Math.min(420, 20 + list.length * 31)).bg(t.popover).p(5).text_size(12.8)
      .id("machine-pick").track_focus(this.handle)
      .on_key_down((e) => {
        if (e.modifiers.control || e.modifiers.platform || e.modifiers.alt) return;
        const m = /^[1-9]$/.test(e.key) ? list[Number(e.key) - 1] : null;
        if (!m) return;
        closeOverlay(props().overlay);
        this.newSpace(m.name);
      })
      .child(div().px(9).pt(4).pb(6).text_size(11).text_color(t.dim).child("New space on\u2026"))
      .child(v_flex().flex_1().min_h(0).overflow_y_scrollbar()
        .children(list.map((m, i) => this.row(
          `machine-${m.name ?? "local"}`,
          svg(`mods/workspace-chrome/${m.name ? "server" : "monitor"}.svg`).size(14),
          m.label,
          () => this.newSpace(m.name),
          i < 9 ? String(i + 1) : ""))));
  }
  render() {
    const t = theme();
    if (props()?.pick || this.picking) return this.renderPicker(t);
    const space = spaces().find(s => s.active);
    const installed = this.agents.filter(a => a.installed);
    const choices = [...installed, ...this.agents.filter(a => !a.installed).slice(0, 2)];
    return v_flex().min_h(0).w_full().h(Math.min(491, 167 + Math.max(1, choices.length) * 31)).bg(t.popover).p(5).text_size(12.8)
      .id("new-menu").track_focus(this.handle)
      .on_key_down((e) => {
        if (e.modifiers.control || e.modifiers.platform || e.modifiers.alt) return;
        const agent = /^[1-9]$/.test(e.key) ? installed[Number(e.key) - 1] : null;
        if (!agent) return;
        closeOverlay(props().overlay);
        run("tab.new", { name: agent.name, space: space?.id, argv: agent.run });
      })
      .child(this.row("terminal", svg("icons/shell.svg").size(14), "Terminal", () => run("tab.new", { space: space?.id }), shortcut("tab.new")))
      .child(div().px(9).pt(8).pb(4).text_size(11).text_color(t.dim).child("Start an agent"))
      .child(v_flex().flex_1().min_h(0).overflow_y_scrollbar()
        .children(choices.map((a, i) => this.row(a.key, a.tint ? svg(a.icon).size(14).text_color(t.foreground) : image(a.icon).size(14), a.name,
          () => run("tab.new", { name: a.name, space: space?.id, argv: a.run }), a.installed ? (i < 9 ? String(i + 1) : "") : "not installed", a.installed)))
        .when(this.agents.length === 0, el => el.child(div().px(9).py(6).text_color(t.dim).child(this.failed ? "Could not load agents" : "Checking installed agents…"))))
      .child(div().h(1).mx(4).my(5).bg(t.border))
      .child(h_flex().id("space").h(31).px(9).gap(10).rounded(7).items_center().flex_none()
        .text_color(t.foreground).hover(s => s.bg(t.selected))
        .on_click((_e, cx) => { this.picking = true; this.handle.focus(); cx.notify(); })
        .child(div().w(14).child("+")).child(div().flex_1().child("New space"))
        .child(div().text_size(11).text_color(t.dim).child(shortcut("space.new"))))
      .child(this.row("worktree", svg("mods/workspace-chrome/branch.svg").size(14), "New worktree…", () => openOverlay({ mod: "my-worktree", kind: "dialog", width: 460, height: 280, props: { space: space?.id, folder: panes().find(p => p.focused)?.cwd, action: "new" } }), "", Boolean(space)))
      .child(this.row("worktree-open", svg("mods/workspace-chrome/branch.svg").size(14), "Open worktree\u2026", () => openOverlay({ mod: "my-worktree", kind: "dialog", width: 560, height: 480, props: { space: space?.id, folder: panes().find(p => p.focused)?.cwd, action: "open" } }), "", Boolean(space)));
  }
}
