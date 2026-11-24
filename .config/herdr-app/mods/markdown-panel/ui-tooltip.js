import { window, keys } from "herdr";

export const MAC = { ctrl: "⌃", alt: "⌥", shift: "⇧", cmd: "⌘", fn: "fn" };
export const OTHER = { ctrl: "Ctrl", alt: "Alt", shift: "Shift", cmd: "Win", fn: "Fn" };
export const LINUX = { ...OTHER, cmd: "Super" };
export const modifierGlyphs = (platform) => platform === "macos" ? MAC : platform === "linux" ? LINUX : OTHER;
const NAMES = { space: "Space", left: "←", right: "→", up: "↑", down: "↓", enter: "↩", escape: "Esc", tab: "⇥", backspace: "⌫", delete: "⌦", insert: "Insert", home: "Home", end: "End", pageup: "PgUp", pagedown: "PgDn" };
const WORDS = { ...NAMES, enter: "Enter", tab: "Tab", backspace: "Backspace", delete: "Delete" };
const ORDER = ["ctrl", "alt", "shift", "cmd", "fn"];
export const chordParts = (chord) => {
  const all = String(chord).split("-");
  return { mods: ORDER.filter((m) => all.slice(0, -1).includes(m)), key: all.at(-1) || "-" };
};
export function glyphs(chord, platform = window()?.platform ?? "macos") {
  const { mods, key } = chordParts(chord), labels = modifierGlyphs(platform);
  const name = (labels === MAC ? NAMES : WORDS)[key] ?? (key.length === 1 ? key.toUpperCase() : key);
  return labels === MAC ? `${mods.map((m) => labels[m]).join("")}${name}` : [...mods.map((m) => labels[m]), name].join("+");
}

const typed = (chord) => !/(^|-)(insert|delete)$/.test(chord);
const shadowed = (binding, bindings) => binding.section === "global"
  && bindings.some((other) => other.section === "layout:kanso" && other.keys === binding.keys && other.action !== binding.action);
export const boundChord = (action, bindings = keys()) => {
  const bound = bindings.filter((binding) => binding.action === action && !shadowed(binding, bindings)).map((binding) => binding.keys);
  return bound.find(typed) ?? bound[0] ?? "";
};

export const chordOf = (action, platform) => glyphs(boundChord(action), platform);

export const hintOf = (action, bindings = keys()) => {
  const chord = action ? boundChord(action, bindings) : "";
  return chord ? glyphs(chord) : null;
};

export const tipText = ({ label, detail = "", chord = "" }, platform) => [String(label ?? ""), chord ? glyphs(chord, platform) : "", detail ? `· ${detail}` : ""]
  .filter(Boolean).join(" ");
