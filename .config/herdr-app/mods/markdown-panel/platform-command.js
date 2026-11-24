export const platformName = (name) => ({ darwin: "macos", win32: "windows" }[name] ?? name);

export function psQuote(value) {
  const text = String(value);
  if (/[\r\n\0]/.test(text)) throw new Error("Invalid path or argument");
  return `'${text.replace(/['\u2018-\u201b]/g, (quote) => quote + quote)}'`;
}

export const windowsArg = (value) => '"' + String(value).replace(/(\\*)"/g, (_match, slashes) => slashes + slashes + '\\"').replace(/\\+$/g, (slashes) => slashes + slashes) + '"';
export const shellQuote = (value) => /^[\w@%+=:,./-]+$/.test(String(value)) ? String(value) : `'${String(value).replace(/'/g, `'\\''`)}'`;
export const unavailable = (feature) => ({ state: "unavailable", reason: `${feature} requires a Herdr API on Windows` });
export const validPid = (pid) => { if (!Number.isSafeInteger(Number(pid)) || Number(pid) <= 0) throw new Error("Invalid process id"); return String(pid); };
export const jsonRows = (text) => { const value = JSON.parse(String(text).replace(/^\uFEFF/, "") || "[]"); return value == null ? [] : Array.isArray(value) ? value : [value]; };

export async function powershell(run, script, options) {
  const args = ["-NoProfile", "-NonInteractive", "-Command", "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); " + script];
  const result = await run("pwsh", args, options).catch((error) => {
    if (error?.code === "ENOENT" || /not found|no such file|cannot find|could not find/i.test(String(error?.message ?? error))) return null;
    throw error;
  });
  if (result && result.code !== "ENOENT" && result.code !== 127 && result.code !== 9009) return result;
  return run("powershell", args, options);
}

export const checked = (result) => {
  if (result.code !== 0) throw new Error(String(result.stderr || `Command failed (${result.code})`).trim());
  return result;
};

export function elapsedSeconds(value) {
  const [days, rest] = String(value).includes("-") ? String(value).split("-") : [0, String(value)];
  const parts = rest.split(":").map(Number).toReversed();
  return Number(days) * 86400 + (parts[0] ?? 0) + (parts[1] ?? 0) * 60 + (parts[2] ?? 0) * 3600;
}
