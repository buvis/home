import { fileApi } from "./platform-files.js";
import { processApi } from "./platform-processes.js";
import { systemApi } from "./platform-system.js";
import { paths } from "./platform-paths.js";

export const markdownMentions = (text) => [...String(text ?? "").matchAll(/(?:[A-Za-z]:[\\/]|\\\\|~[\\/]|\/)[^\r\n"'`<>|]*?\.(?:markdown|mdx|md)(?=$|[\s"'`),;])/gim)].map((match) => match[0]);

export function markdownApi(platform, run) {
  const files = fileApi(platform, run), processes = processApi(platform, run);
  const waiting = async (dir) => {
    if (!await files.test(dir, "directory")) return { code: 0, stdout: "" };
    const entries = (await files.directory(dir)).filter((entry) => !entry.dir && /^\d+\.path$/.test(entry.name));
    const rows = await Promise.all(entries.map(async (entry) => {
      const id = entry.name.slice(0, -5), file = paths.join(dir, entry.name), alive = await processes.exists(Number(id));
      if (alive === false) { await files.remove([file]); return ""; }
      if (alive === null) throw new Error(`Process ${id} could not be checked`);
      return `${id}\t${await files.read(file)}\0`;
    }));
    return { code: 0, stdout: rows.join("") };
  };
  const recent = async (terminal, home, appHome, clipboard = "") => {
    if (platform !== "windows") return run("sh", [paths.join(appHome, "mods", "markdown-panel", "recent.sh"), terminal || ""]);
    const screen = terminal ? await run("hc", ["read", terminal]).catch(() => null) : null;
    const candidates = [...markdownMentions(String(clipboard).slice(0, 4096)), ...markdownMentions(screen?.stdout).toReversed()];
    const got = terminal ? await run("hc", ["get", terminal, "--json"]).catch(() => null) : null;
    const foreground = got?.code === 0 ? JSON.parse(got.stdout).foreground : null;
    const recordPath = foreground?.pid ? paths.join(home, ".claude", "sessions", `${foreground.pid}.json`) : null;
    const record = recordPath && await files.test(recordPath) ? JSON.parse(await files.read(recordPath)) : null;
    const temp = record?.sessionId ? await systemApi(platform, run).temporary() : [];
    const scratch = temp.length ? await files.walk(temp, { depth: 5 }) : [];
    const found = scratch.filter((file) => file.split(/[\\/]/).includes(record.sessionId) && paths.basename(paths.dirname(file)) === "scratchpad" && /\.md$/i.test(file));
    const expanded = candidates.map((file) => /^~[\\/]/.test(file) ? paths.join(home, file.slice(2)) : file);
    return { code: 0, stdout: (await files.existing([...new Set([...expanded, ...found])])).slice(0, 15).join("\n") };
  };
  return { waiting, recent };
}
