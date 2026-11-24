import test from "node:test";
import assert from "node:assert/strict";
import { movePane } from "./move.js";

// In-memory world: space s1 has tabs A (2 terminals + a mod pane), B; s2 has tab C;
// s3 lives on another machine (tab R). Keep without `place` makes a new tab in the selected space.
const SPACES = { s1: ["A", "B"], s2: ["C"], s3: ["R"] };
function world(opts = {}) {
  const w = {
    panes: [
      { pane: "p1", terminal: "t1", tab: "A" },
      { pane: "p2", terminal: "t2", tab: "A" },
      { pane: "pm", terminal: null, mod: "files", tab: "A" },
      { pane: "p3", terminal: "t3", tab: "B" },
    ],
    sel: "A",
    selSpace: "s1",
    extra: {},
    calls: [],
    n: 10,
  };
  const spaceOf = (tab) => Object.keys(SPACES).find((s) => [...SPACES[s], ...(w.extra[s] ?? [])].includes(tab));
  w.io = {
    run(name, args) {
      w.calls.push([name, args]);
      if (name === "terminal.park" && !opts.parkStuck) w.panes = w.panes.filter((p) => p.terminal !== args.terminal);
      if (name === "tab.select" && !opts.noSelect) (w.sel = args.id), (w.selSpace = spaceOf(args.id));
      if (name === "space.select" && !opts.noSelect) (w.selSpace = args.id), (w.sel = SPACES[args.id][0]);
      if (name === "terminal.keep") {
        const keepFails = args.place ? opts.keepStuck : opts.recoverStuck;
        if (!keepFails) {
          let tab = w.sel;
          if (!args.place) {
            tab = `N${w.n}`;
            (w.extra[w.selSpace] ??= []).push(tab);
          }
          w.panes.push({ pane: `p${w.n++}`, terminal: args.terminal, tab });
        }
      }
      return opts.slowRun ? new Promise((r) => setTimeout(r, 5)) : undefined;
    },
    panes: () => w.panes,
    spaces: () =>
      Object.entries(SPACES).map(([id, tabs]) => ({
        id,
        machine: id === "s3" ? "remote" : null,
        tabs: [...tabs, ...(w.extra[id] ?? [])].map((t) => ({ id: t, panes: w.panes.filter((p) => p.tab === t).length })),
      })),
    focused: () => ({ tab: w.sel, space: w.selSpace }),
    sleep: async () => {},
  };
  return w;
}

test("moves_terminal_to_destination_tab", async () => {
  const w = world();
  const r = await movePane({ terminal: "t1", tab: "B" }, w.io);
  assert.deepEqual(w.calls.map((c) => c[0]), ["terminal.park", "tab.select", "terminal.keep"]);
  assert.equal(w.calls[2][1].place, "right");
  assert.equal(r.tab, "B");
  assert.equal(r.pane, w.panes.find((p) => p.terminal === "t1").pane);
});

test("rejects_mod_pane", async () => {
  const w = world();
  await assert.rejects(movePane({ terminal: null, tab: "B" }, w.io), /Not a terminal pane/);
  await assert.rejects(movePane({ terminal: "files", tab: "B" }, w.io), /Not a terminal pane/);
  assert.equal(w.calls.length, 0);
});

test("rejects_same_tab", async () => {
  const w = world();
  await assert.rejects(movePane({ terminal: "t1", tab: "A" }, w.io), /Pick another tab/);
  assert.equal(w.calls.length, 0);
});

test("moves_terminal_to_tab_in_other_space", async () => {
  const w = world();
  const r = await movePane({ terminal: "t1", tab: "C" }, w.io);
  assert.deepEqual(w.calls.map((c) => c[0]), ["terminal.park", "tab.select", "terminal.keep"]);
  assert.deepEqual([r.tab, r.space], ["C", "s2"]);
});

test("moves_terminal_to_new_tab_in_other_space", async () => {
  const w = world();
  const r = await movePane({ terminal: "t1", space: "s2" }, w.io);
  assert.deepEqual(w.calls.map((c) => c[0]), ["terminal.park", "space.select", "terminal.keep"]);
  assert.deepEqual(w.calls[1][1], { id: "s2" });
  assert.equal("place" in w.calls[2][1], false);
  assert.equal(r.space, "s2");
  assert.notEqual(r.tab, "C");
});

test("moves_terminal_to_new_tab_in_current_space", async () => {
  const w = world();
  const r = await movePane({ terminal: "t1", space: "s1" }, w.io);
  assert.deepEqual(w.calls.map((c) => c[0]), ["terminal.park", "terminal.keep"]);
  assert.equal(r.space, "s1");
  assert.notEqual(r.tab, "A");
});

test("rejects_new_tab_for_lone_pane_in_its_own_space", async () => {
  const w = world();
  await assert.rejects(movePane({ terminal: "t3", space: "s1" }, w.io), /already alone in its tab/);
  assert.equal(w.calls.length, 0);
});

test("rejects_unknown_space_and_remote_machines", async () => {
  const w = world();
  await assert.rejects(movePane({ terminal: "t1", space: "nope" }, w.io), /Pick another space/);
  await assert.rejects(movePane({ terminal: "t1", space: "s3" }, w.io), /another machine/);
  await assert.rejects(movePane({ terminal: "t1", tab: "R" }, w.io), /another machine/);
  assert.equal(w.calls.length, 0);
});

test("recovers_to_new_tab_when_space_not_selected", async () => {
  const w = world({ noSelect: true });
  await assert.rejects(movePane({ terminal: "t1", space: "s2" }, w.io), /it is in a new tab/);
  assert.equal(w.calls.filter((c) => c[0] === "terminal.keep").length, 1);
});

test("rejects_second_move_while_one_runs", async () => {
  const w = world({ slowRun: true });
  const first = movePane({ terminal: "t1", tab: "B" }, w.io);
  await assert.rejects(movePane({ terminal: "t2", tab: "B" }, w.io), /A move is already running/);
  assert.equal((await first).tab, "B");
});

test("leaves_pane_when_park_times_out", async () => {
  const w = world({ parkStuck: true });
  await assert.rejects(movePane({ terminal: "t1", tab: "B" }, w.io), /Terminal did not leave its tab; nothing moved/);
  assert.deepEqual(w.calls.map((c) => c[0]), ["terminal.park"]);
});

test("recovers_to_new_tab_when_destination_not_selected", async () => {
  const w = world({ noSelect: true });
  await assert.rejects(movePane({ terminal: "t1", tab: "B" }, w.io), /Could not place the terminal there; it is in a new tab/);
  const keeps = w.calls.filter((c) => c[0] === "terminal.keep");
  assert.equal(keeps.length, 1);
  assert.equal("place" in keeps[0][1], false);
});

test("recovers_to_new_tab_when_keep_times_out", async () => {
  const w = world({ keepStuck: true });
  await assert.rejects(movePane({ terminal: "t1", tab: "B" }, w.io), /it is in a new tab/);
  const keeps = w.calls.filter((c) => c[0] === "terminal.keep");
  assert.equal(keeps.length, 2);
  assert.equal(keeps[0][1].place, "right");
  assert.equal("place" in keeps[1][1], false);
});

test("names_stranded_terminal_when_recovery_fails", async () => {
  const w = world({ keepStuck: true, recoverStuck: true });
  await assert.rejects(movePane({ terminal: "t1", tab: "B" }, w.io), (e) => {
    assert.match(e.message, /t1/);
    assert.match(e.message, /herdr-app do terminal\.keep --terminal t1/);
    return true;
  });
});

test("clears_busy_flag_after_failure", async () => {
  const w = world({ parkStuck: true });
  await assert.rejects(movePane({ terminal: "t1", tab: "B" }, w.io), /nothing moved/);
  await assert.rejects(movePane({ terminal: "t1", tab: "B" }, w.io), /nothing moved/);
});
