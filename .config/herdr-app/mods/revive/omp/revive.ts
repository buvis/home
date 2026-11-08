// herdr-revive: omp extension. oh-my-pi (omp) has no hooks file, so this runs
// Revive's engine the way Claude Code's SessionStart and SessionEnd hooks do,
// with the same payload. `revive.mjs install` links it into
// ~/.omp/agent/extensions/. What it shares with pi's extension is in
// ../lib/extension.js.
//
// It differs from pi's in two ways, both checked against omp 18.16.0:
// - omp's `session_shutdown` carries no reason. A person's /exit, Ctrl+C or
//   Ctrl+D reaches it without a signal; a reboot, a core restart or a closed
//   terminal sends SIGTERM or SIGHUP first. Only the first forgets the session.
// - /new, /resume and /fork switch sessions in the same process and report
//   `session_switch`, which is recorded like a start.

import { realpathSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// The helper is in the mod folder above this file; omp loads this file through a link.
const HELPER = pathToFileURL(join(dirname(realpathSync(fileURLToPath(import.meta.url))), "..", "lib", "extension.js")).href;

export default async function (pi: any) {
  if (!process.env.HC_TERMINAL_ID) return;
  const { revive } = await import(HELPER);
  const engine = revive({ agent: "omp", args: ["--agent", "omp"] });

  // Only the interactive omp in a terminal: -p, --mode json/rpc and subagents answer and quit.
  pi.on("session_start", (_event: any, ctx: any) => {
    if (ctx.mode !== "tui") return;
    engine.listen();
    // Not awaited: omp starts while the engine records it.
    void engine.send(ctx, { hook_event_name: "SessionStart", source: "startup" });
  });

  pi.on("session_switch", (event: any, ctx: any) => {
    if (ctx.mode !== "tui") return;
    void engine.send(ctx, { hook_event_name: "SessionStart", source: event?.reason ?? "switch" });
  });

  pi.on("session_shutdown", async (_event: any, ctx: any) => {
    if (ctx.mode !== "tui") return;
    // A signal handler registered after omp's own runs after it: let it run first.
    // A reboot, a core restart or a kill (Claude Code's reason "other") keeps the record.
    if (await engine.ended()) return engine.queue;
    // /exit, Ctrl+C twice, Ctrl+D: the person ended it.
    return engine.send(ctx, { hook_event_name: "SessionEnd", reason: "prompt_input_exit" });
  });
}
