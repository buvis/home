// Ctrl+H/J/K/L: move between nvim splits (smart-splits) when the focused pane runs
// nvim, else between herdr-app panes. Keys: "nav.left" etc. in keys.json. Invisible:
// lives as an empty floating block in layouts/buvis.json (commands reach shown mods only).
import { View, div } from "gpui-kit";
import { exec, focused, home, nextCommand, panes, run, spaces } from "herdr";

const DIRS = ["left", "down", "up", "right"];

export default class Nav extends View {
  init(_props, cx) {
    cx.spawn(async () => {
      for (;;) {
        const dir = await nextCommand();
        if (dir === "tab-left" || dir === "tab-right") {
          this.moveTab(dir === "tab-left" ? -1 : 1);
        }
        if (DIRS.includes(dir)) await this.go(dir);
      }
    });
  }

  moveTab(delta) {
    const f = focused();
    const tabs = spaces().find((s) => s.id === f?.space)?.tabs;
    const tab = tabs?.find((t) => t.id === f?.tab);
    if (!tab) return;
    const index = tab.index + delta;
    if (index >= 1 && index <= tabs.length) {
      run("tab.move", { id: tab.id, index });
    }
  }

  async go(dir) {
    const f = focused();
    const pane = f?.pane && panes().find((p) => p.pane === f.pane);
    // ponytail: local terminals only; a remote nvim falls through to pane.go
    if (pane?.terminal && !pane.terminal.includes("/") && pane.program.key === "nvim") {
      const sock = `${home()}/.cache/nvim/herdr-${pane.terminal}.sock`;
      try {
        const r = await exec("nvim", ["--server", sock, "--remote-expr", `v:lua.herdr_nav('${dir}')`]);
        if (r.code === 0) return;
      } catch (_) {
        // nvim not reachable: fall back to moving the herdr-app pane
      }
    }
    run("pane.go", { direction: dir });
  }

  render() {
    return div();
  }
}
