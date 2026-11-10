// Editors on this computer. A trimmed copy of the Open with mod's catalog, detection and
// launch (jlopezlira/herdr-kanso, open-with, Apache-2.0): macOS app bundles and CLIs on PATH
// only, since Path menu scans local terminals and there is no remote case here.
import { exec, run, shared, setShared, panes, spaces, focused, appHome } from "herdr";

export const isMarkdown = target => !target.dir && !target.url && !target.cmd && /\.(md|markdown|mdx)$/i.test(target.path);

function openContent(content, pane, place = "right") {
  const source = panes().find(p => p.pane === pane);
  if (place === "tab") {
    const space = spaces().find(s => s.tabs.some(t => t.id === source?.tab))?.id ?? focused()?.space;
    run("tab.new", { ...content, ...(space ? { space } : {}) });
  } else {
    if (!source) throw new Error("This terminal has no pane to split. Choose Tab instead.");
    run("pane.split", { pane: source.pane, direction: place, ...content });
  }
}

export function openPreview(target, pane, place = "right") {
  openContent({ mod: "folio", props: { path: target.path }, ...(place === "tab" ? { name: target.path.split("/").at(-1) } : {}) }, pane, place);
}

export const FOUND = "on-screen.found.v2";

// Catalog order is the order shown. mac: app bundle names; cli: commands on PATH;
// tui: opens in a terminal split; icon: one of Herdr's shipped icons.
export const EDITORS = [
  { id: "cursor", name: "Cursor", mac: ["Cursor.app"], cli: ["cursor"], icon: "icons/cursor.svg" },
  { id: "vscode", name: "VS Code", mac: ["Visual Studio Code.app"], cli: ["code"] },
  { id: "vscode-insiders", name: "VS Code Insiders", mac: ["Visual Studio Code - Insiders.app"], cli: ["code-insiders"] },
  { id: "windsurf", name: "Windsurf", mac: ["Windsurf.app"], cli: ["windsurf"] },
  { id: "antigravity", name: "Antigravity", mac: ["Antigravity.app"], cli: ["antigravity", "agy"], icon: "icons/antigravity.svg" },
  { id: "kiro", name: "Kiro", mac: ["Kiro.app"], cli: ["kiro"], icon: "icons/kiro.svg" },
  { id: "trae", name: "Trae", mac: ["Trae.app"], cli: ["trae"] },
  { id: "vscodium", name: "VSCodium", mac: ["VSCodium.app"], cli: ["codium"] },
  { id: "positron", name: "Positron", mac: ["Positron.app"], cli: ["positron"] },
  { id: "zed", name: "Zed", mac: ["Zed.app", "Zed Preview.app"], cli: ["zed", "zeditor"] },
  { id: "sublime", name: "Sublime Text", mac: ["Sublime Text.app"], cli: ["subl"] },
  { id: "idea", name: "IntelliJ IDEA", mac: ["IntelliJ IDEA.app", "IntelliJ IDEA Ultimate.app", "IntelliJ IDEA CE.app"], cli: ["idea"] },
  { id: "webstorm", name: "WebStorm", mac: ["WebStorm.app"], cli: ["webstorm"] },
  { id: "pycharm", name: "PyCharm", mac: ["PyCharm.app", "PyCharm Professional Edition.app", "PyCharm CE.app"], cli: ["pycharm"] },
  { id: "goland", name: "GoLand", mac: ["GoLand.app"], cli: ["goland"] },
  { id: "phpstorm", name: "PhpStorm", mac: ["PhpStorm.app"], cli: ["phpstorm"] },
  { id: "rustrover", name: "RustRover", mac: ["RustRover.app"], cli: ["rustrover"] },
  { id: "clion", name: "CLion", mac: ["CLion.app"], cli: ["clion"] },
  { id: "rider", name: "Rider", mac: ["Rider.app"], cli: ["rider"] },
  { id: "fleet", name: "Fleet", mac: ["Fleet.app"], cli: ["fleet"] },
  { id: "nova", name: "Nova", mac: ["Nova.app"], cli: ["nova"] },
  { id: "bbedit", name: "BBEdit", mac: ["BBEdit.app"], cli: ["bbedit"] },
  { id: "textmate", name: "TextMate", mac: ["TextMate.app"], cli: ["mate"] },
  { id: "xcode", name: "Xcode", mac: ["Xcode.app"] },
  { id: "nvim", name: "Neovim", cli: ["nvim"], tui: true, icon: "icons/nvim.svg" },
  { id: "hx", name: "Helix", cli: ["hx", "helix"], tui: true, icon: "icons/hx.svg" },
  { id: "vim", name: "Vim", cli: ["vim"], tui: true, icon: "icons/vim.svg" },
];

// Browsers, for web links: Enter opens the default one (`open <url>`), these the others.
export const BROWSERS = [
  { id: "safari", name: "Safari", mac: ["Safari.app"] },
  { id: "brave", name: "Brave", mac: ["Brave Browser.app"] },
  { id: "chrome", name: "Chrome", mac: ["Google Chrome.app"] },
  { id: "chromium", name: "Chromium", mac: ["Chromium.app"] },
  { id: "firefox", name: "Firefox", mac: ["Firefox.app"] },
  { id: "arc", name: "Arc", mac: ["Arc.app"] },
  { id: "edge", name: "Edge", mac: ["Microsoft Edge.app"] },
  { id: "zen", name: "Zen", mac: ["Zen.app", "Zen Browser.app"] },
  { id: "vivaldi", name: "Vivaldi", mac: ["Vivaldi.app"] },
  { id: "opera", name: "Opera", mac: ["Opera.app"] },
  { id: "orion", name: "Orion", mac: ["Orion.app"] },
  { id: "duckduckgo", name: "DuckDuckGo", mac: ["DuckDuckGo.app"] },
  { id: "tor", name: "Tor Browser", mac: ["Tor Browser.app"] },
];

// One shell pass: prints `app|cli <tab> name <tab> path` per hit. Names are arguments, never script text.
const DETECT = `
export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"
for a in "$@"; do
  case "$a" in
    app:*) n=\${a#app:}
      for d in /Applications "$HOME/Applications" /Applications/Setapp "$HOME/Applications/JetBrains Toolbox"; do
        if [ -d "$d/$n" ]; then printf 'app\\t%s\\t%s\\n' "$n" "$d/$n"; break; fi
      done;;
    cli:*) n=\${a#cli:}
      p=$(command -v "$n" 2>/dev/null) && case "$p" in /*) printf 'cli\\t%s\\t%s\\n' "$n" "$p";; esac;;
  esac
done
exit 0`;

// Starts a GUI program from its CLI and returns at once.
const DETACH = `if command -v setsid >/dev/null 2>&1; then setsid -f "$@" >/dev/null 2>&1; else nohup "$@" >/dev/null 2>&1 & fi`;

// Looks once; the result is shared so every reopened copy of the menu sees it.
export async function detectEditors() {
  const args = [];
  for (const e of [...EDITORS, ...BROWSERS]) {
    for (const m of e.mac ?? []) args.push(`app:${m}`);
    for (const c of e.cli ?? []) args.push(`cli:${c}`);
  }
  const found = {};
  try {
    const r = await exec("sh", ["-c", DETECT, "sh", ...args]);
    const hits = r.stdout.split("\n").filter(Boolean).map((l) => l.split("\t"));
    for (const e of [...EDITORS, ...BROWSERS]) {
      const app = hits.find(([k, n]) => k === "app" && e.mac?.includes(n));
      const cli = hits.find(([k, n]) => k === "cli" && e.cli?.includes(n));
      if (app || cli) found[e.id] = { app: app?.[2], cli: cli?.[2] };
    }
  } catch {}
  setShared(FOUND, found);
  return found;
}

// The editors (or browsers) found, in catalog order; null until the first look finished.
export function editorsFound() {
  const f = shared(FOUND);
  return f ? EDITORS.filter((e) => f[e.id]) : null;
}
export function browsersFound() {
  const f = shared(FOUND);
  return f ? BROWSERS.filter((e) => f[e.id]) : null;
}

const dirname = (p) => p.replace(/\/[^/]*$/, "") || "/";

// GUI editors open externally; terminal editors use the menu's selected placement.
// Explicit pane/space targets keep an asynchronous action attached to its source.
export async function openIn(e, target, pane, place = "right") {
  const how = shared(FOUND)?.[e.id];
  if (!how) throw new Error(`${e.name} was not found`);
  if (e.tui) {
    const argv = e.id === "nvim" && isMarkdown(target)
      ? ["env", `HERDR_APP_HOME=${appHome()}`, "sh", `${appHome()}/mods/folio/nvim.sh`, target.path]
      : [how.cli ?? e.cli[0], "--", target.path];
    openContent({ argv, ...(place === "tab" ? { folder: target.dir ? target.path : dirname(target.path) } : {}) }, pane, place);
    return;
  }
  const r = how.app ? await exec("open", ["-a", how.app, target.path]) : await exec("sh", ["-c", DETACH, "sh", how.cli, target.path]);
  if (r.code !== 0) throw new Error((r.stderr || r.stdout).trim() || `exit ${r.code}`);
}
