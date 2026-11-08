// Like tmux's last-pane, kept to the shown space: remembers each space's
// previously focused pane and goes back to it on last-pane.go
// (ctrl-t ctrl-t), switching tabs within the space when needed. Lives in an
// empty floating block so it runs all the time and draws nothing.
import { View, div } from "gpui-kit";
import { panes, focused, run, nextCommand } from "herdr";

export default class LastPane extends View {
  init(_props, cx) {
    // space id -> { current, previous } pane ids
    this.history = {};
    // Focus can change between redraws (or while the window isn't drawing),
    // so look now and then too; it reads in-memory state and redraws nothing.
    cx.timer.every(300, () => this.track());
    cx.spawn(async (cx) => {
      for (;;) {
        if ((await nextCommand()) === "go") this.go();
        cx.notify();
      }
    });
  }

  track() {
    const f = focused();
    if (!f?.space || !f.pane) return;
    const h = (this.history[f.space] ??= { current: null, previous: null });
    if (f.pane === h.current) return;
    if (h.current) h.previous = h.current;
    h.current = f.pane;
  }

  go() {
    this.track();
    const f = focused();
    const h = f && this.history[f.space];
    const target = h?.previous && panes().find((p) => p.pane === h.previous);
    if (!target) return;
    if (target.tab !== f.tab) run("tab.select", { id: target.tab });
    run("pane.focus", { pane: target.pane });
  }

  render() {
    this.track();
    return div();
  }
}
