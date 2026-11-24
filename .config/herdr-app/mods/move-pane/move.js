// Moves a running terminal to another tab (any space on this computer) or to a NEW tab
// in a space: park, select, keep. Pure logic with injected I/O (no imports), so Node can
// test it. Destination is `{ tab }` (existing tab, keep "right") or `{ space }` (new tab:
// keep without `place` opens one in the focused space). Both proven by spike2.mjs.

export const POLL_MS = 100;
export const TIMEOUT_MS = 5000;

let busy = false;

// Polls until `done()` is truthy or TIMEOUT_MS of sleeping has passed.
async function waitFor(done, io) {
  let elapsed = 0;
  while (!done()) {
    if (elapsed >= TIMEOUT_MS) return false;
    await io.sleep(POLL_MS);
    elapsed += POLL_MS;
  }
  return true;
}

const paneOf = (io, terminal) => io.panes().find((p) => p.terminal === terminal);
const spaceOfTab = (io, tab) => io.spaces().find((s) => (s.tabs ?? []).some((t) => t.id === tab));

async function recover(terminal, io) {
  await io.run("terminal.keep", { terminal });
  if (await waitFor(() => paneOf(io, terminal), io)) throw new Error("Could not place the terminal there; it is in a new tab");
  throw new Error(`Terminal ${terminal} runs without a pane. Run: herdr-app do terminal.keep --terminal ${terminal}`);
}

const REMOTE = "Moves to or from another machine are not supported";

export async function movePane({ terminal, tab, space }, io) {
  if (busy) throw new Error("A move is already running");
  const pane = io.panes().find((p) => p.terminal === terminal && terminal);
  if (!pane) throw new Error("Not a terminal pane");
  const from = spaceOfTab(io, pane.tab);
  if (!from) throw new Error("Not a terminal pane");
  if (from.machine) throw new Error(REMOTE);
  let to;
  if (tab) {
    to = spaceOfTab(io, tab);
    if (tab === pane.tab || !to) throw new Error("Pick another tab");
  } else {
    to = io.spaces().find((s) => s.id === space);
    if (!to) throw new Error("Pick another space");
    const here = from.tabs.find((t) => t.id === pane.tab);
    if (to.id === from.id && (here?.panes ?? 2) <= 1) throw new Error("That pane is already alone in its tab");
  }
  if (to.machine) throw new Error(REMOTE);
  busy = true;
  try {
    await io.run("terminal.park", { terminal });
    if (!(await waitFor(() => !paneOf(io, terminal), io))) throw new Error("Terminal did not leave its tab; nothing moved");
    if (tab) {
      await io.run("tab.select", { id: tab });
      if (io.focused()?.tab !== tab) return await recover(terminal, io);
    } else if (io.focused()?.space !== to.id) {
      await io.run("space.select", { id: to.id });
      if (io.focused()?.space !== to.id) return await recover(terminal, io);
    }
    await io.run("terminal.keep", tab ? { terminal, place: "right" } : { terminal });
    if (!(await waitFor(() => paneOf(io, terminal), io))) return await recover(terminal, io);
    const landed = paneOf(io, terminal);
    if (tab ? landed.tab !== tab : spaceOfTab(io, landed.tab)?.id !== to.id) {
      throw new Error(tab ? "Terminal landed in another tab" : "Terminal landed in another space");
    }
    return { pane: landed.pane, tab: landed.tab, space: to.id };
  } finally {
    busy = false;
  }
}
