// Settings: ~/.config/herdr-app/recall.json, every key optional. The module also
// holds the category ids, which open commands (`parseOpenCommand`) name too.
//
//   {
//     "categories": ["all", "spaces", "tabs", "panes", "agents", "clues"],
//     "keybindings": { "move_up": ["k", "up"], "move_down": ["j", "down"] },
//     "font": "JetBrains Mono",
//     "font_size": 15
//   }
//
// `categories` is both the order of the categories and which ones show;
// `tabs`, its earlier name, is read only when `categories` is absent.
// `font` and `font_size` are the dialog's own, spelled as Herdr's
// settings.json spells the terminals'; lib/look.js turns them into a look.
// Keys use Herdr's keys.json spelling ("ctrl-p", "shift-tab", "escape");
// the herdr-recent-navigator spelling ("C-p", "S-Tab", "Esc") works too, so
// a config can move over as it is.

// "all" lists every space, tab, pane and agent; "clues" is the clue search,
// which herdr-recent-navigator called "others" (see docs/adr/0001).
export const CATEGORY_IDS = ["all", "spaces", "tabs", "panes", "agents", "clues"];
const CATEGORY_ALIASES = { workspaces: "spaces", workspace: "spaces", ws: "spaces", others: "clues" };

export const ACTIONS = ["next_category", "previous_category", "move_up", "move_down", "select", "dismiss", "force_quit", "backspace"];
export const DEFAULT_KEYS = {
  next_category: ["tab"],
  previous_category: ["shift-tab"],
  move_up: ["up", "ctrl-p"],
  move_down: ["down", "ctrl-n"],
  select: ["enter"],
  dismiss: ["escape"],
  force_quit: ["ctrl-c"],
  backspace: ["backspace"],
};
const MODAL_ACTIONS = ["move_up", "move_down", "next_category", "previous_category"];

function defaults() {
  return Object.fromEntries(ACTIONS.map((a) => [a, [...DEFAULT_KEYS[a]]]));
}

/** A category name as written (any case, an alias) as its id; unknown names stay as they are. */
function categoryId(name) {
  const n = name.trim().toLowerCase();
  return CATEGORY_ALIASES[n] ?? n;
}

/**
 * The visible categories in order. Names are trimmed and lowercased,
 * aliases resolve, unknown names drop, duplicates keep the first. A list
 * left empty shows only "all"; no list at all shows every category.
 */
export function normalizeCategories(value) {
  if (!Array.isArray(value)) return [...CATEGORY_IDS];
  const out = [];
  for (const raw of value) {
    if (typeof raw !== "string") continue;
    const id = categoryId(raw);
    if (CATEGORY_IDS.includes(id) && !out.includes(id)) out.push(id);
  }
  return out.length ? out : ["all"];
}

const AGENT_SORT_ALIASES = { recent: "mru", mru: "mru", priority: "priority", grouped: "grouped" };

/**
 * What a `recall.open…` command asks for: "open", "open-tabs",
 * "open-others", "open-agents-priority" → { category, sort }, each null
 * when not given. The category resolves aliases as recall.json does.
 */
export function parseOpenCommand(command) {
  const [, category, sort] = command.split("-");
  return { category: category ? categoryId(category) : null, sort: AGENT_SORT_ALIASES[sort] ?? null };
}

const NAMED = {
  tab: "tab", backtab: "shift-tab", up: "up", down: "down", left: "left", right: "right",
  enter: "enter", return: "enter", esc: "escape", escape: "escape", backspace: "backspace",
  space: "space", delete: "delete", home: "home", end: "end", pageup: "pageup", pagedown: "pagedown",
};
const MODS = { c: "ctrl", ctrl: "ctrl", control: "ctrl", s: "shift", shift: "shift", m: "alt", a: "alt", alt: "alt", option: "alt", cmd: "cmd", super: "cmd", d: "cmd" };
const MOD_ORDER = ["ctrl", "alt", "shift", "cmd"];

/**
 * One key in Herdr's keystroke spelling, as GPUI reports it in
 * `event.keystroke`: modifiers ctrl, alt, shift, cmd in that order, then
 * the key in lowercase. "J" means shift-j. Returns null for nonsense.
 */
export function normalizeKey(spec) {
  if (typeof spec !== "string" || !spec.trim()) return null;
  const s = spec.trim();
  // "-" alone, or a chord ending in "-" ("ctrl--"), names the minus key.
  const parts = s === "-" ? ["-"] : s.endsWith("--") ? [...s.slice(0, -2).split("-"), "-"] : s.split("-");
  const key = parts.pop();
  const mods = new Set();
  for (const m of parts) {
    const mod = MODS[m.toLowerCase()];
    if (!mod) return null;
    mods.add(mod);
  }
  let name;
  if (NAMED[key.toLowerCase()]) name = NAMED[key.toLowerCase()];
  else if ([...key].length === 1) {
    if (key !== key.toLowerCase()) mods.add("shift");
    name = key.toLowerCase();
  } else return null;
  if (name === "shift-tab") { mods.add("shift"); name = "tab"; }
  return [...MOD_ORDER.filter((m) => mods.has(m)), name].join("-");
}

/** True for a key that types a character: a plain or shifted single character, or space. */
export function isPrintable(keystroke) {
  const parts = keystroke.split("-");
  const key = keystroke.endsWith("--") ? "-" : parts[parts.length - 1];
  const mods = keystroke.endsWith("--") ? parts.slice(0, -2) : parts.slice(0, -1);
  if (mods.some((m) => m !== "shift")) return false;
  return key === "space" || [...key].length === 1;
}

/**
 * Keybindings, each action defaulting on its own. A malformed table (not an
 * object, or an action that is not a list of strings) falls back to every
 * default, as the navigator does.
 */
export function normalizeKeys(value) {
  if (value === undefined || value === null) return defaults();
  if (typeof value !== "object" || Array.isArray(value)) return defaults();
  const out = {};
  for (const action of ACTIONS) {
    const list = value[action];
    if (list === undefined) { out[action] = [...DEFAULT_KEYS[action]]; continue; }
    if (!Array.isArray(list) || list.some((k) => typeof k !== "string")) return defaults();
    out[action] = list.map(normalizeKey).filter(Boolean);
  }
  return out;
}

/** Modal (vim-style) input is on when a movement or category key types a character. */
export function isModal(keys) {
  return MODAL_ACTIONS.some((a) => keys[a].some(isPrintable));
}

/** The action a keystroke is bound to, first match in ACTIONS order, or null. */
export function actionFor(keys, keystroke) {
  for (const a of ACTIONS) if (keys[a].includes(keystroke)) return a;
  return null;
}

/** The font family asked for, trimmed; null when none is: Recall then uses Herdr's interface font. */
function normalizeFont(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** The text size asked for, in px at zoom 1; null when none is: Recall then follows Herdr's. */
function normalizeFontSize(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

const asObject = (raw) => (raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {});

/**
 * The font and text size a settings object asks for, each null when it
 * asks for none. The object is recall.json's, or what the dialog kept of
 * it for its next open, in the same spelling.
 */
export function normalizeLook(raw) {
  const obj = asObject(raw);
  return { font: normalizeFont(obj.font), fontSize: normalizeFontSize(obj.font_size) };
}

/** A whole settings object from recall.json's parsed contents (or null). */
export function normalizeConfig(raw) {
  const obj = asObject(raw);
  const keys = normalizeKeys(obj.keybindings);
  return {
    categories: normalizeCategories(obj.categories !== undefined ? obj.categories : obj.tabs),
    keys,
    modal: isModal(keys),
    ...normalizeLook(obj),
  };
}

/** Parses recall.json text; invalid JSON reads as no settings, with the error. */
export function parseConfig(text) {
  if (text === null || text === undefined || !text.trim()) return { config: normalizeConfig(null), error: null };
  try {
    return { config: normalizeConfig(JSON.parse(text)), error: null };
  } catch (e) {
    return { config: normalizeConfig(null), error: `recall.json: ${e.message}` };
  }
}
