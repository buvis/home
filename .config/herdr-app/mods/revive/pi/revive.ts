// herdr-revive: pi extension. pi has no hooks file, so this runs Revive's engine
// the way Claude Code's SessionStart and SessionEnd hooks do, with the same payload.
// `revive.mjs install` links it into ~/.pi/agent/extensions/. What it shares with
// omp's extension is in ../lib/extension.js.

import { realpathSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// The helper is in the mod folder above this file; pi loads this file through a link.
const HELPER = pathToFileURL(join(dirname(realpathSync(fileURLToPath(import.meta.url))), "..", "lib", "extension.js")).href;

export default async function (pi: any) {
  if (!process.env.HC_TERMINAL_ID) return;
  const { revive } = await import(HELPER);
  const engine = revive({ agent: "pi" });

  // Only the interactive pi in a terminal: -p, --mode json/rpc and subagents answer and quit.
  pi.on("session_start", (event: any, ctx: any) => {
    if (ctx.mode !== "tui") return;
    engine.listen();
    // Not awaited: pi starts while the engine records it.
    void engine.send(ctx, { hook_event_name: "SessionStart", source: event.reason });
  });

  pi.on("session_shutdown", async (event: any, ctx: any) => {
    if (ctx.mode !== "tui") return;
    // On SIGTERM or SIGHUP, pi's own handler reports "quit" before ours runs: let it run first.
    const signalled = await engine.ended();
    // A reboot, a core restart or a kill (Claude Code's reason "other") keeps the record,
    // and so do /new, /resume, /fork and reload, whose next session records itself.
    if (event.reason !== "quit" || signalled) return engine.queue;
    // /quit, Ctrl+C twice, Ctrl+D: the person ended it.
    return engine.send(ctx, { hook_event_name: "SessionEnd", reason: "prompt_input_exit" });
  });
}
