// What pi's and omp's extensions share: running the engine's hook, one at a
// time, and noticing a SIGTERM or SIGHUP before the session ends. Extensions
// only (Node's child_process): the dialog and the engine never import it.
//
// Each extension imports this file by its real path, so it is found next to
// the engine however the extension was linked. What differs per agent (its
// events, what an end means) stays in the extension.

import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// The engine is in the mod folder above this file.
const ENGINE = join(dirname(fileURLToPath(import.meta.url)), "..", "revive.mjs");
const SIGNALS = ["SIGTERM", "SIGHUP"];

/** Runs `revive.mjs hook` with the payload on stdin; never fails, gives up after 10 seconds. */
function hook(args, payload) {
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn("node", [ENGINE, "hook", ...args], { stdio: ["pipe", "ignore", "ignore"] });
    } catch { resolve(); return; }
    const timer = setTimeout(() => child.kill(), 10_000);
    const done = () => { clearTimeout(timer); resolve(); };
    child.on("error", done);
    child.on("close", done);
    child.stdin.on("error", () => {});
    child.stdin.end(JSON.stringify(payload));
  });
}

/**
 * One extension's link to the engine.
 * - `agent` the program name the agent gives its process, sent as `argv[0]`
 *   (pi and omp rename their process, so ps no longer shows their flags)
 * - `args`  extra arguments to `revive.mjs hook`
 */
export function revive({ agent, args = [] }) {
  let queue = Promise.resolve();
  let signalled = false;
  let listening = false;
  const onSignal = () => { signalled = true; };

  return {
    /** Queues a hook with the session's fields; nothing for a session without a file (--no-session). */
    send(ctx, fields) {
      const transcript_path = ctx.sessionManager.getSessionFile();
      if (!transcript_path) return queue;
      queue = queue.then(() => hook(args, {
        ...fields,
        session_id: ctx.sessionManager.getSessionId(),
        transcript_path,
        cwd: ctx.cwd,
        argv: [agent, ...process.argv.slice(2)],
      }));
      return queue;
    },

    /** Starts noticing SIGTERM and SIGHUP; once, however often a session starts. */
    listen() {
      if (listening) return;
      for (const s of SIGNALS) process.on(s, onSignal);
      listening = true;
    },

    /**
     * At the session's end: lets the agent's own signal handler, registered
     * before ours, run first, stops listening and tells whether a signal came.
     */
    async ended() {
      await new Promise((r) => setImmediate(r));
      if (listening) { for (const s of SIGNALS) process.off(s, onSignal); listening = false; }
      return signalled;
    },

    /** The hooks sent so far, done. */
    get queue() { return queue; },
  };
}
