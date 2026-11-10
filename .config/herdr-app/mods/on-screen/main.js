// On screen: Herdr's terminal right-click menu with the files and folders on screen at
// the top, and beside them the actions for the selected one: Markdown preview, the
// default app, Reveal in Finder, and every code editor found here. Right/Below/Tab
// chooses placement for previews and terminal editors; GUI apps open externally. A web link on
// screen is a row too: Enter opens it in the default browser, letters in the other browsers
// found here (config.json: b Brave, s Safari, f Firefox, ...). Commands on screen (a `$ ` or
// `! ` line, a fenced block, an indented line starting with a program) are rows too: Enter
// runs one in a new terminal beside the pane (config.json picks the Enter action), `n` pastes it there instead, `p`
// pastes it into the pane, `y` copies it; `y` copies a path or link as well. Only paths under
// home are listed unless config.json says otherwise. Hovering a path row selects it. Cmd+Shift+O (`mod.open:on-screen`) opens the same menu for the
// focused terminal, so the whole flow works from the keyboard: 1-9 select a path (the first
// is selected already), Enter opens it, a letter picks an action (config.json: o reveal,
// z Zed, v Neovim or Vim, ...), Esc closes. Without paths on screen it is Herdr's menu.
//
// Built on Path menu (Lakris2407/herdr-path-menu, Apache-2.0: paths.js verbatim, this file
// extended) and Open with (jlopezlira/herdr-kanso: editors.js). Herdr's own items stay below.
// ↑/↓ move, Enter runs, Esc closes. An item is [label, command, args].

import { View, div, svg } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { run, props, closeOverlay, openOverlay, theme, keys, terminals, spaces, panes, exec, window, home, notify, shared, setShared, focused, readTextFile, appHome } from "herdr";
import { pathsOnScreen } from "./paths.js";
import { FOUND, detectEditors, editorsFound, browsersFound, openIn, openPreview, isMarkdown } from "./editors.js";

const MOD = "on-screen";
const CONFIG = `${MOD}.config`;
const DEFAULT_KEYS = { reveal: "o", copy: "y", paste: "p", "paste-split": "n", "run-split": "r", zed: "z", xcode: "x", nvim: "v", hx: "h", vim: "v", cursor: "c", vscode: "c", sublime: "s" };
const DEFAULT_CONFIG = { paths: { home_only: true, ignore: ["/tmp", "/private/tmp", "~/Library", "~/.cache", "~/.Trash"] }, commands: { enter: "run-split" }, letters: {} };
// The key's popup (mod.json names no size) follows its content, but Herdr caps a content-sized
// popup near 418 px wide, so the two columns fit under that; a right-click popup is reopened
// at the same width.
const NARROW = 320, LEFT = 215, RIGHT = 180, WIDE = LEFT + RIGHT + 19;
const TILES = ["#5b8def", "#22a99a", "#8b7cf6", "#e3814f", "#3fae6a", "#d9649a"];

// Where a space is now: its first terminal's live folder, else where it was made.
function place(s) {
  const tabs = new Set((s.tabs ?? []).map((c) => c.id));
  return panes().find((p) => tabs.has(p.tab) && p.cwd)?.cwd || s.folder;
}

// A space's checkout: "main" (a repo's own), "linked" (a worktree), or null.
async function checkout(folder, on) {
  const top = await exec("git", ["rev-parse", "--show-toplevel"], { cwd: folder, on });
  const common = await exec("git", ["rev-parse", "--path-format=absolute", "--git-common-dir"], { cwd: folder, on });
  if (top.code !== 0 || common.code !== 0) return null;
  return common.stdout.trim() === `${top.stdout.trim()}/.git` ? "main" : "linked";
}

function items(p, git) {
  p = p ?? {};
  const tg = p.target ?? {};
  switch (p.tab) {
    case "pane": {
      // A kept sub-agent can go back under its parent, still running.
      const all = terminals();
      const term = all.find((t) => t.address === tg.terminal);
      const parent = term?.parent && all.find((t) => t.address === term.parent);
      // Once they go to the program, Shift+right-click still opens this menu.
      const toProgram = term?.labels?.["herdr.right-click"] === "program";
      const here = panes().find((x) => x.pane === tg.pane || (tg.terminal && x.terminal === tg.terminal));
      const found = (p.paths ?? []).map((f) => [f.cmd ? f.path : f.url ? f.path.replace(/^https?:\/\//i, "") : f.path.split("/").pop() + (f.dir ? "/" : ""), "pick", f]);
      return [
        ...found,
        ["Split right", "pane.split", { direction: "right", pane: tg.pane }],
        ["Split down", "pane.split", { direction: "down", pane: tg.pane }],
        ["Zoom", "pane.zoom", { pane: tg.pane }],
        ...(here?.cwd ? [["Copy path", "copy", { text: here.cwd }]] : []),
        ...(here?.branch ? [["Copy branch name", "copy", { text: here.branch }]] : []),
        ...(term
          ? [
              toProgram
                ? ["Use Herdr right-click menu", "terminal.right_click", { terminal: term.address, to: "menu" }]
                : ["Send right-clicks to pane", "terminal.right_click", { terminal: term.address, to: "program" }],
            ]
          : []),
        ...(parent ? [[`Send back to ${parent.name || parent.address}`, "terminal.park", { terminal: term.address }]] : []),
        ["Close pane", "pane.close", { pane: tg.pane }],
      ];
    }
    case "tab":
      return [
        ["Rename", "tab.rename", { id: tg.id }],
        ["New tab", "tab.new", { space: tg.space }],
        ["Close", "tab.close", { id: tg.id }],
      ];
    case "space":
      return [
        ["Rename", "space.rename", { id: tg.id }],
        ...(git ? [["New worktree", "worktree", { space: tg.id, action: "new" }], ["Open worktree", "worktree", { space: tg.id, action: "open" }]] : []),
        ...(git === "linked" ? [["Remove worktree", "worktree", { space: tg.id, action: "remove" }]] : []),
        ["Close", "space.close", { id: tg.id }],
      ];
    default:
      return [
        ["New space", "space.new", {}],
        ["Keybinds", "app.help", {}],
        ["Theme: graphite", "app.theme", { name: "graphite" }],
        ["Theme: ink", "app.theme", { name: "ink" }],
        ["Theme: moss", "app.theme", { name: "moss" }],
        ["Theme: atom one dark", "app.theme", { name: "atom-one-dark" }],
      ];
  }
}

// config.json over the built-in defaults.
const config = () => ({ ...DEFAULT_CONFIG, ...(shared(CONFIG) ?? {}) });
const keyMap = () => ({ ...DEFAULT_KEYS, ...(config().letters ?? {}) });

// Whether a found path is listed: under home when `home_only`, and never in an ignored folder.
function pathAllowed(path) {
  const h = home(), c = config().paths ?? {};
  const under = (p, dir) => p === dir || p.startsWith(dir.endsWith("/") ? dir : dir + "/");
  if (c.home_only !== false && !under(path, h)) return false;
  for (const ig of c.ignore ?? []) if (under(path, ig.startsWith("~") ? h + ig.slice(1) : ig)) return false;
  return true;
}

// The actions for one path: [label, kind, arg, key]. Each editor found gets its letter unless
// an earlier one (catalog order) took it, so `v` is Neovim when both Neovim and Vim are here.
// A link: the default browser on Enter, then the other browsers found. A command: copy, paste.
function actions(f) {
  const km = keyMap();
  if (f.cmd) {
    const all = {
      "run-split": ["Run in a split", "run-split", f, km["run-split"]],
      "paste-split": ["Paste in a split", "paste-split", f, km["paste-split"]],
      paste: ["Paste in pane", "paste", f, km.paste],
      copy: ["Copy", "copy", f, km.copy],
    };
    const first = all[config().commands?.enter] ? config().commands.enter : "run-split";
    all[first][3] = "enter";
    return [all[first], ...Object.keys(all).filter((k) => k !== first).map((k) => all[k])];
  }
  const taken = new Set(f.url ? [km.copy] : [km.reveal, km.copy]);
  const letter = (e) => { const k = km[e.id] && !taken.has(km[e.id]) ? km[e.id] : null; if (k) taken.add(k); return k; };
  if (f.url) return [["Open in browser", "open", f, "enter"], ["Copy link", "copy", f, km.copy], ...(browsersFound() ?? []).map((b) => [b.name, "editor", b, letter(b)])];
  const list = [
    ...(isMarkdown(f) ? [["Preview Markdown", "preview", f, "enter"]] : []),
    ["Default app", "open", f, isMarkdown(f) ? null : "enter"],
    [window()?.platform === "macos" ? "Reveal in Finder" : "Show in folder", "reveal", f, km.reveal],
    ["Copy path", "copy", f, km.copy],
  ];
  for (const e of editorsFound() ?? []) list.push([e.name, e.tui ? "split" : "editor", e, letter(e)]);
  return list;
}

function menuIcon(command, args) {
  if (command === "pick" || command === "open" || command === "preview") return args.cmd ? "mods/workspace-chrome/terminal.svg" : args.url ? `mods/${MOD}/globe.svg` : `mods/files/${args.dir ? "folder" : "file"}.svg`;
  if (command === "reveal") return "mods/workspace-chrome/folder.svg";
  if (command === "copy") return "mods/workspace-chrome/files.svg";
  if (command === "paste") return "mods/workspace-chrome/terminal.svg";
  if (command === "paste-split") return "mods/workspace-chrome/panel-right.svg";
  if (command === "run-split") return "mods/workspace-chrome/terminal.svg";
  const name = command.endsWith(".close") ? "x" : command.endsWith(".rename") ? "square-pen" : command.endsWith(".new") ? "plus" : command === "worktree" ? "git-branch" : command === "app.help" ? "terminal" : command === "app.theme" ? "settings" : command === "pane.split" ? "panel-right" : command === "pane.zoom" ? "square" : "terminal";
  return `mods/workspace-chrome/${name}.svg`;
}

// The key bound to a command, for the hint on the right.
function shortcut(name, args) {
  // `pane.split:right` binds pane.split with { direction: "right" }.
  const value = args && Object.values(args)[0];
  const k = keys().find((b) => b.section === "global" && (b.action === name || b.action === `${name}:${value}`));
  return k ? k.keys : "";
}

// Opens a file with its app, a folder in the file manager; reveal shows the item in its folder.
function openPath(f, reveal) {
  const platform = window()?.platform;
  const [cmd, args] = platform === "windows" ? ["explorer", reveal ? [`/select,${f.path}`] : [f.path]]
    : platform === "linux" ? ["xdg-open", [reveal ? f.path.replace(/\/[^/]*$/, "") || "/" : f.path]]
    : ["open", reveal ? ["-R", f.path] : [f.path]];
  exec(cmd, args).then(result => {
    if (result.code !== 0) throw new Error(result.stderr || result.stdout || `Exit ${result.code}`);
  }).catch(error => notify({ title: "Could not open file", body: String(error), level: "error" }));
}

const shortPath = (p) => { const h = home(); return p === h ? "~" : p.startsWith(h + "/") ? "~" + p.slice(h.length) : p; };
const dirname = (p) => p.replace(/\/[^/]*$/, "") || "/";

// Pixel heights: rows, dividers, headings and padding, so the popup fits what it shows.
function leftHeight(list) {
  const rows = list.length * 31, dividers = list.filter((it, i) => i > 0 && (it[1].endsWith(".close") || it[1] === "pane.split" && list[i - 1][1] === "pick")).length * 9;
  const cmds = list.some((it) => it[1] === "pick" && it[2].cmd) ? 24 : 0;
  const onScreen = list.some((it) => it[1] === "pick" && !it[2].cmd) ? 24 : 0;
  return rows + dividers + onScreen + cmds + 12;
}
function rightHeight(acts) {
  const editors = acts.some((a) => a[1] === "editor" || a[1] === "split"), split = acts.some((a) => a[1] === "split");
  if (acts.some((a) => a[1] === "run-split")) return 50 + 9 + acts.length * 31 + 9 + 12;
  return 50 + 9 + acts.length * 31 + (editors ? 9 : 0) + (split ? 24 : 0) + 12 + 38;
}

// Reopens the menu in place with new props (a popup's size is fixed when it opens). Opened by
// the key, it stays at the top of the window; by right-click, at the pointer.
function reopen(p, next, width, height) {
  delete next.overlay;
  closeOverlay(p.overlay);
  openOverlay({ mod: MOD, kind: "popup", width, height, props: next, ...(next.via === "key" ? { at: "top", offset: 40 } : {}) });
}

async function readConfig() {
  try {
    const text = await readTextFile(`${appHome()}/mods/${MOD}/config.json`);
    const c = text ? JSON.parse(text) : {};
    const letters = Object.fromEntries(Object.entries(c.letters ?? {}).filter(([, v]) => typeof v === "string" && v.length === 1));
    setShared(CONFIG, { paths: { ...DEFAULT_CONFIG.paths, ...(c.paths ?? {}) }, commands: { ...DEFAULT_CONFIG.commands, ...(c.commands ?? {}) }, letters });
  } catch { setShared(CONFIG, DEFAULT_CONFIG); }
}

export default class Menu extends View {
  init(_props, cx) {
    this.at = 0;
    this.sel = 0;
    this.git = null;
    this.destination = "right";
    this.handle = cx.focus_handle();
    this.handle.focus();
    // Opened by the key (mod.open, no props): act on the focused terminal, as a right-click on it would.
    const o = props() ?? {};
    if (!o.tab) {
      const f = focused();
      // A focused layout terminal block has no pane id; its model pane is found by terminal.
      const pane = f?.pane ?? panes().find((x) => x.terminal === f?.terminal)?.pane ?? null;
      this.synth = f?.terminal ? { tab: "pane", target: { pane, terminal: f.terminal }, via: "key", cwd: f.cwd } : { via: "key" };
    }
    const p = this.p();
    // First open: look for paths on screen, for editors and for the key map, then reopen in
    // place, two columns wide and sized for them.
    const term = p.tab === "pane" && !p.paths && p.target?.terminal;
    const local = term && !String(term).includes("/");
    if (local)
      cx.spawn(async (cx) => {
        const cwd = p.cwd ?? panes().find((x) => x.pane === p.target.pane)?.cwd;
        await readConfig();
        const [paths] = await Promise.all([pathsOnScreen(term, cwd, { allow: pathAllowed }).catch(() => []), shared(FOUND) ? null : detectEditors()]);
        if (!paths.length) return;
        // Opened by the key, the popup has no fixed size (mod.json names none), so it grows in
        // place and Herdr's mod.open keeps tracking it: the key pressed again closes it. A
        // right-click popup comes at Herdr's fixed size, so that one reopens, sized for its rows.
        if (p.via === "key") { this.paths = paths; cx.notify(); return; }
        const next = { ...p, paths };
        reopen(p, next, WIDE, Math.max(leftHeight(items(next, null)), ...paths.map(path => rightHeight(actions(path)))));
      });
    const space = p.tab === "space" && spaces().find((s) => s.id === p.target?.id);
    const folder = space && place(space);
    if (folder)
      cx.spawn(async (cx) => {
        this.git = await checkout(folder, space.machine).catch(() => null);
        cx.notify();
      });
  }

  // The clicked terminal's model pane, by id or, for a layout block, by its terminal.
  targetPane(p) {
    return p.target?.pane ?? panes().find((x) => x.terminal === p.target?.terminal)?.pane ?? null;
  }

  // This copy's props: Herdr's for a right-click, the focused terminal's for the key.
  p() {
    const o = props() ?? {};
    return o.tab || !this.synth ? o : { ...this.synth, overlay: o.overlay, ...(this.paths ? { paths: this.paths } : {}) };
  }

  // Runs one action on a path, then the menu is gone. Launching is a plain promise, not on
  // this copy's cx: the overlay is closing.
  act(a, p, cx) {
    if (a[1] === "copy" || a[1] === "paste" || a[1] === "paste-split") cx.write_to_clipboard(a[2].path);
    if (a[1] === "run-split" || a[1] === "paste" || a[1] === "paste-split") {
      // The model pane of the clicked terminal: a split opens beside the focused model pane,
      // and a layout terminal block does not count, so focus the pane itself first. The close
      // goes through the same queue, so nothing refocuses between these steps.
      const pane = this.targetPane(p);
      const folder = p.cwd ?? panes().find((x) => x.pane === pane)?.cwd;
      run("overlay.close", { id: p.overlay });
      if (pane) run("pane.focus", { pane });
      // run-split: a new terminal to the right that runs the command, then your shell, so ssh
      // and logins work and the pane stays. paste-split: the same terminal, the command pasted
      // into it and not run (commands queue in order, so the paste reaches its input).
      if (a[1] === "run-split") run("terminal.open", { argv: ["sh", "-c", `${a[2].path}\nexec "\${SHELL:-/bin/sh}" -l`], folder, place: "right" });
      else if (a[1] === "paste-split") {
        run("terminal.open", { folder, place: "right" });
        // The new terminal takes the keyboard a moment later than the open is queued, and a
        // paste queued right behind it is lost. A helper process pastes half a second later;
        // an exec already started outlives this closing copy. The paste goes to the focused
        // terminal, which is the new split by then.
        exec("sh", ["-c", 'sleep 0.5; for b in herdr-app "$HOME/.local/bin/herdr-app" "$HOME/Applications/Herdr.app/Contents/MacOS/Herdr" /Applications/Herdr.app/Contents/MacOS/Herdr; do command -v "$b" >/dev/null 2>&1 && exec "$b" do terminal.paste "{}"; done']).catch(() => null);
      }
      else run("terminal.paste", {});
      return;
    }
    closeOverlay(p.overlay);
    if (a[1] === "copy") return;
    if (a[1] === "preview") {
      try { openPreview(a[2], this.targetPane(p), this.destination); }
      catch (error) { notify({ title: "Could not open preview", body: String(error), level: "error" }); }
    }
    else if (a[1] === "open") openPath(a[2], false);
    else if (a[1] === "reveal") openPath(a[2], true);
    else openIn(a[2], p.paths[this.sel], this.targetPane(p), this.destination).catch((err) => notify({ title: `Could not open ${a[2].name}`, body: String(err?.message ?? err).slice(0, 300), level: "error" }));
  }

  choose(i, cx) {
    const p = this.p();
    const it = items(p, this.git)[i];
    if (!it) return;
    if (it[1] === "pick") return this.act(actions(it[2])[0], p, cx);
    closeOverlay(p.overlay);
    if (it[1] === "copy") { cx.write_to_clipboard(it[2].text); notify({ title: "Copied", body: it[2].text, level: "info", timeout: 2 }); }
    else if (it[1] === "worktree") openOverlay({ mod: "worktree", kind: "dialog", ...(it[2].action === "open" ? { width: 560, height: 480 } : { width: 440, height: 260 }), props: it[2] });
    else run(it[1], it[2]);
  }

  // An editor's glyph: Herdr's shipped icon, else a colored tile with its first letter.
  glyph(e, t) {
    if (e.icon) return svg(e.icon).size(14).flex_none().text_color(t.muted);
    const c = TILES[e.name.charCodeAt(0) % TILES.length];
    return div().size(14).flex_none().rounded(4).bg(c).flex().items_center().justify_center()
      .text_size(9).font_bold().text_color("#ffffff").child(e.name[0]);
  }

  // One 31 px row: icon, label, a dim hint on the right.
  row(id, icon, label, hint, selected, t) {
    return h_flex().id(id).h(31).px(8).gap(9).rounded(7).items_center().justify_between().text_color(t.foreground)
      .when(selected, (el) => el.bg(t.selected))
      .hover((s) => s.bg(t.hover))
      .child(icon)
      .child(div().flex_1().min_w(0).truncate().child(label))
      .child(div().flex_none().text_size(11).text_color(t.dim).child(hint ?? ""));
  }

  divider(t) { return div().mx(7).my(4).h(1).bg(t.border); }
  heading(text, t) { return div().px(8).pt(4).pb(5).text_size(11).text_color(t.dim).child(text); }

  render(cx) {
    const t = theme();
    const p = this.p();
    const list = items(p, this.git), paths = p.paths ?? [], n = paths.length;
    if (this.sel >= n) this.sel = 0;
    const f = paths[this.sel];
    const acts = f ? actions(f) : [];
    const left = list.map((it, i) =>
      v_flex()
        // Dividers: before Herdr's pane items, before Close, before Keybinds, before the themes.
        .when(i > 0 && (it[1] === "pane.split" && list[i - 1][1] === "pick" || it[1].endsWith(".close") || it[1] === "app.help" || (it[1] === "app.theme" && list[i - 1][1] !== "app.theme")), (el) => el.child(this.divider(t)))
        .when(it[1] === "pick" && it[2].cmd && !(list[i - 1]?.[1] === "pick" && list[i - 1][2].cmd), (el) => el.child(this.heading("Commands", t)))
        .child(
          it[1] === "pick"
            ? this.row(`mi-${i}`, svg(menuIcon(it[1], it[2])).size(14).flex_none().text_color(t.muted), it[0], i < 9 ? String(i + 1) : "", i === this.sel, t)
                .tooltip(it[2].path)
                .on_hover((h, cx) => { if (h && this.sel !== i) { this.sel = i; this.at = i; cx.notify(); } })
                .on_click((_e, cx) => this.choose(i, cx))
            : this.row(`mi-${i}`, svg(menuIcon(it[1], it[2])).size(14).flex_none().text_color(t.muted), it[0], shortcut(it[1], it[2]), i === this.at && i >= n, t)
                .on_click((_e, cx) => this.choose(i, cx))));
    return v_flex()
      .id("menu")
      .track_focus(this.handle)
      .w(f ? WIDE : NARROW)
      .min_h(0)
      .p(5)
      .bg(t.popover)
      .text_size(12.8)
      .on_key_down((e, cx) => {
        const m = e.modifiers ?? {};
        if (m.platform || m.control || m.alt) return;
        const k = String(e.key).toLowerCase();
        if (k === "down") { this.at = (this.at + 1) % list.length; if (this.at < n) this.sel = this.at; }
        else if (k === "up") { this.at = (this.at + list.length - 1) % list.length; if (this.at < n) this.sel = this.at; }
        else if (k === "escape") closeOverlay(p.overlay);
        else if (k === "enter") { if (n && this.at < n) this.act(acts[0], p, cx); else this.choose(this.at, cx); }
        else if (n && /^[1-9]$/.test(k) && +k <= n) { this.sel = +k - 1; this.at = this.sel; }
        else if (n) { const a = acts.find((a) => a[3] === k); if (!a) return; this.act(a, p, cx); }
        else return;
        cx.notify();
      })
      // Without paths: Herdr's menu, one column.
      .when(!f, (el) => el.children(left))
      // With paths: the list on the left, the selected path's actions on the right.
      .when(f, (el) => el.child(h_flex().items_start()
        .child(v_flex().w(LEFT).flex_none().when(!paths[0]?.cmd, (el) => el.child(this.heading("On screen", t))).children(left))
        .child(div().w(1).mx(4).self_stretch().bg(t.border))
        .child(v_flex().w(RIGHT).flex_none().min_w(0)
          .child(v_flex().id("head").px(8).pt(4).pb(6).tooltip(f.path)
            .child(div().text_size(14).font_semibold().truncate().child(f.cmd ? f.path : f.url ? f.path.replace(/^https?:\/\//i, "").split("/")[0] : f.path.split("/").pop() + (f.dir ? "/" : "")))
            .child(div().text_size(11).text_color(t.dim).truncate().child(f.cmd ? "command" : f.url ? f.path : shortPath(dirname(f.path)))))
          .child(this.divider(t))
          .when(!f.url && !f.cmd, el => el.child(h_flex().px(6).pb(6).gap(3)
            .children([["right", "Right"], ["down", "Below"], ["tab", "Tab"]].map(([place, label]) =>
              div().id(`destination-${place}`).flex_1().py(4).rounded(5).text_center().cursor_pointer()
                .tooltip("Placement for Markdown preview and terminal editors")
                .when(this.destination === place, el => el.bg(t.selected))
                .hover(s => s.bg(t.hover)).on_click((_e, cx) => { this.destination = place; cx.notify(); }).child(label)))))
          .children(acts.map((a, i) =>
            v_flex()
              .when(i > 0 && (a[1] === "editor" || a[1] === "split") && (acts[i - 1][1] === "reveal" || acts[i - 1][1] === "open") || (i === 1 && f.cmd), (el) => el.child(this.divider(t)))
              .when(a[1] === "split" && acts[i - 1]?.[1] !== "split", (el) => el.child(this.heading(this.destination === "tab" ? "In a new tab" : "In a split", t)))
              .child(this.row(`act-${i}`,
                a[1] === "editor" || a[1] === "split" ? this.glyph(a[2], t) : svg(menuIcon(a[1], a[2])).size(14).flex_none().text_color(t.muted),
                a[0], a[3] === "enter" ? "↵" : a[3] ?? "", false, t)
                .on_click((_e, cx) => this.act(a, p, cx))))))));
  }
}
