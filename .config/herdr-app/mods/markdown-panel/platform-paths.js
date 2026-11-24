const windowsPath = (value) => /^(?:[A-Za-z]:|\\\\)/.test(String(value));
const rootOf = (value, windows) => windows ? /^(?:[A-Za-z]:[\\/]|[\\/]{2}[^\\/]+[\\/][^\\/]+[\\/]?)/.exec(value)?.[0] ?? (/^[\\/]/.test(value) ? "\\" : "") : value.startsWith("/") ? "/" : "";

export function pathApi(platform = "macos") {
  const win = (value) => windowsPath(value) || (platform === "windows" && !String(value).startsWith("/"));
  const normalize = (value) => {
    const text = String(value ?? ""), windows = win(text), sep = windows ? "\\" : "/", root = rootOf(text, windows);
    const parts = text.slice(root.length).split(windows ? /[\\/]+/ : /\/+/).filter(Boolean);
    const clean = parts.reduce((out, part) => part === "." ? out : part === ".." && out.at(-1) !== ".." && out.length ? out.slice(0, -1) : part === ".." && root ? out : [...out, part], []);
    const prefix = root.replace(/[\\/]/g, sep);
    return prefix + (prefix && !prefix.endsWith(sep) && clean.length ? sep : "") + clean.join(sep) || ".";
  };
  const join = (...values) => {
    const parts = values.filter((v) => v != null && String(v) !== "").map(String);
    return normalize(parts.join(win(parts[0] ?? "") ? "\\" : "/"));
  };
  const basename = (value) => { const text = normalize(value), root = rootOf(text, win(text)); return text === root ? "" : text.split(win(text) ? /[\\/]/ : "/").at(-1); };
  const dirname = (value) => { const text = normalize(value), root = rootOf(text, win(text)), name = basename(text), parent = name ? text.slice(0, -name.length) : root; return normalize(parent.length <= root.length ? root || "." : parent); };
  const isAbsolute = (value) => Boolean(rootOf(String(value), win(value)));
  const equal = (a, b) => win(a) ? normalize(a).toLowerCase() === normalize(b).toLowerCase() : normalize(a) === normalize(b);
  const within = (value, root) => {
    const a = normalize(value), b = normalize(root), sep = win(b) ? "\\" : "/";
    return equal(a, b) || (win(b) ? a.toLowerCase().startsWith((b.endsWith(sep) ? b : b + sep).toLowerCase()) : a.startsWith(b.endsWith(sep) ? b : b + sep));
  };
  const relative = (root, value) => {
    if (!within(value, root)) return null;
    return equal(root, value) ? "" : normalize(value).slice(normalize(root).replace(/[\\/]$/, "").length + 1);
  };
  const fileUrl = (value) => {
    const text = normalize(value).replace(/\\/g, "/");
    return (text.startsWith("//") ? "file:" : "file://" + (text.startsWith("/") ? "" : "/")) + text.split("/").map((part, i) => i === 0 && /^[A-Za-z]:$/.test(part) ? part : encodeURIComponent(part)).join("/");
  };
  const fromFileUrl = (value) => {
    const text = String(value).replace(/^file:\/\/(?:localhost(?=\/))?/i, "");
    const decoded = decodeURIComponent(text);
    return normalize(/^\/[A-Za-z]:\//.test(decoded) ? decoded.slice(1) : !decoded.startsWith("/") ? "\\\\" + decoded : decoded);
  };
  return { normalize, join, basename, dirname, isAbsolute, equal, within, relative, fileUrl, fromFileUrl, sqliteRead: (value) => `.read ${JSON.stringify(String(value).replace(/\\/g, "/"))}`,
    canonical: (value) => normalize(String(value ?? "").replace(/^\/(tmp|var)(\/|$)/, "/private/$1$2")),
    shorten: (value, home) => { const rel = relative(home, value); return rel == null ? value : rel ? "~" + (win(value) ? "\\" : "/") + rel : "~"; } };
}

export const paths = pathApi();

// That computer's own default app home. A custom HERDR_APP_HOME there is not followed.
export function appHomeDir(platform, home) {
  const api = pathApi(platform === "windows" ? "windows" : "macos");
  const parts = platform === "windows" ? ["AppData", "Roaming", "herdr-app"] : [".config", "herdr-app"];
  return api.join(home, ...parts);
}
