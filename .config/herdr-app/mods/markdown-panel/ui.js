// Kanso's panel kit, the base every piece uses: sizes, colours and timing, by jlopezlira (https://github.com/jlopezlira/herdr-kanso). Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui.js. Each piece is its own ui-<piece>.js.
import { shared, settings } from "herdr";

// Sizes generated from kanso/tokens.json by npm run build:ui-tokens.
export const G = { hair: 2, xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };
export const H = { bar: 28, control: 32, compact: 24, tabBar: 48, icon: 28, row: 40, line: 32, two: 52, badge: 20, petPicture: 84, petStage: 128, append: 120 };
export const R = { sm: 4, control: 6, card: 8, full: 999 };
export const W = { paneName: 256, paneSegment: 224, menu: 252, question: 260, tabLabel: 170, tabSkeleton: 92, tabSkeletonShort: 64, keyTile: 78, petTile: 104, buttonLabel: 170, prose: 760, tableCell: 96 };
export const T = { display: 48, page: 20, title: 16, card: 14, value: 13, body: 12, mono: 12, micro: 11 };
export const ICON = 16;
export const ICON_ROW = 16;
export const ICON_INLINE = 12;
export const ICON_CHROME = 18;
export const ICON_EMPTY = 20;
export const CHROME_SQUARE = 36;
export const DRAG_START = 4;
export const DAWN_H = 56;
export const DAWN_W = 256;
export const LINE = 1;
export const FOCUS = 2;
export const GLINT = { run: 240, wide: 44, mid: 26, narrow: 12 };
export const SWITCH = { w: 28, h: 16, knob: 12 };
export const PAGE = { w: 1080, toolbar: 42, toolbarX: 14, note: 12, markdown: 13, unitGap: 8, unitY: 3, findList: 300 };
export const SIDEBAR = { w: 256, narrow: 240, min: 120, railRow: 48, tile: 36, guideX: 12, agentX: 34, elbowGap: 8, gap: 0, gutter: 16, groupGap: 12, computerGap: 16, threadGap: 8 };
export const PANE = { edge: 28, gap: 6, minW: 140, minH: 90, pills: 110 };
export const KEY = { x: 4, text: 11, unit: 40, gap: 5 };
export const DIALOG = { wide: 480, small: 340, sidebar: 460, worktree: 440, prompt: 420, list: 202, pad: 20, settingsW: 860, settingsH: 680, computers: 440 };
export const PR = { title: 17, titleMax: 44, fold: 150, ages: 40 };
export const SKELETON = { text: 9, meta: 11 };
export const HEATMAP_GAP = 3;
export const DOJO_CELL = 30;
export const DOJO = { gap: 3, pad: 14, char: 12, wide: 560, w: 980 };
export const CODE = { line: 20, gutter: 36 };
export const LH = { body: 1.5 };
export const SPIN = 900;
export const GLINT_MS = 2200;
export const GLINT_STAGGER = 160;
export const LIT_MS = 650;
export const EASE = { duration: 180, easing: "ease-out" };
export const GLIDE = { duration: 220, easing: "ease-out" };
export const GLINT_EASE = "linear";
export const BEAT = { working: { from: 0.35, to: 1, period: 1800 }, blocked: { from: 0.45, to: 1, period: 1600 } };
export const OPACITY = { away: 0.55, held: 0.4, hover: 0.75, quiet: 0.55, idle: 0.7, thumb: 0.7, trace: 0.6, pending: 0.8, part: 0.85, pet: 0.85, blockedWash: 0.4, blockedRow: 0.08, glintFaint: 0.35, glintMid: 0.6 };
export const TINT = { board: 0.02, chip: 0.024, cell: 0.03, hover: 0.04, row: 0.047, card: 0.063, tab: 0.07, pill: 0.08, diff: 0.094, faint: 0.1, key: 0.11, control: 0.12, goal: 0.133, bound: 0.14, soft: 0.15, strong: 0.25, frame: 0.314, boundLine: 0.44, ring: 0.5, line: 0.55 };
export const WASHES = { dark: { w4: 0.04, w7: 0.07, w12: 0.12, w14: 0.14 }, light: { w4: 0.05, w7: 0.095, w12: 0.18, w14: 0.21 } };
export const DAWN = { dark: { top: "#262339", star: "#d9d3e6", art: "mods/kanso-chrome/dawn-dark.svg" }, light: { top: "#aeb0d6", star: "#fbf6ea", art: "mods/kanso-chrome/dawn-light.svg" } };
export const DAWN_MOTION = {"night":{"duration":2600,"delay":0,"easing":"ease-in-out","opacity":{"from":0.92,"to":0}},"glow":{"duration":2200,"delay":500,"easing":"ease-out","opacity":{"from":0,"to":1}},"sun":{"duration":2600,"delay":200,"easing":"ease-out","top":{"from":17,"to":0}},"circle":{"duration":1400,"delay":1500,"easing":"ease-in-out","opacity":{"from":0,"to":1},"dash":true,"opacityBy":0.2},"clouds":{"duration":1600,"delay":1500,"easing":"ease-out","opacity":{"from":0,"to":1}},"horizon":{"duration":1800,"delay":300,"easing":"ease-out","opacity":{"from":0,"to":0.55}}};
export const INK = { faint: "#8a867d", fallback: "#888888", dojoFur: "#e8963a", dojoCream: "#f6ece0", dojoInk: "#161615" };
// End of the generated sizes.
/** The sidebar is seen to end PANE.gap past its block, where the work column's padding (kanso.json's `work`) shows its chrome;
 * the Storybook's sidebar meets the work area. Each of its blocks (header, list, footer, the pill) sets `inset` on its `edges`,
 * the start in full and the end PANE.gap less, so what it draws sits as far from either side seen. */
export const sidebarSides = (el, inset, [start, end] = ["pl", "pr"]) => el[start](inset)[end](inset - PANE.gap);
/** A second press within this long confirms what cannot be undone. */
export const ARM_MS = 4000;
export const BREATH = { from: 0.35, to: 0.8, period: 1800 };
// A native loop: it keeps going behind other windows, where a still mark reads as a stalled agent.
export const breathe = (el, policy = BREATH) => el.loop("opacity", policy);
// A native loop redraws the whole window about 30 times a second, so on battery motion steps instead of gliding.
export const onBattery = () => shared("kanso.battery") === true;
/** The terminal's own mono family: a tool's words are drawn in it. */
export const monoFont = () => settings().font_family ?? "JetBrains Mono";
export const ICONS = "mods/kanso-chrome/icons/";
/** A name in kanso-chrome's icons, or a path. */
export const glyphOf = (icon) => (icon.includes("/") ? icon : `${ICONS}${icon}.svg`);

export function tokens(t = {}) {
  const canvas = t.canvas ?? t.background, selected = t.selected ?? t.hover ?? t.raised, subtle = t.hover ?? t.raised;
  const blue = t.blue ?? t.ansi4, done = t.done ?? t.ansi2;
  return {
    canvas, text: t.foreground, muted: t.muted ?? t.dim, dim: t.dim,
    border: t.border ?? t.input, input: t.input ?? t.border, subtle, raised: t.raised ?? canvas,
    selected, popover: t.popover ?? t.surface ?? canvas,
    primary: t.solid ?? t.foreground, primaryText: t.solid_foreground ?? t.background,
    accent: t.accent ?? t.foreground, accentText: t.accent_foreground ?? t.background,
    background: t.background ?? canvas,
    blocked: t.blocked ?? t.ansi1, working: t.working ?? t.ansi3, done, idle: t.idle ?? t.dim, chrome: t.chrome,
    highlight: t.selection ?? t.selected ?? t.hover,
    red: t.ansi1, green: t.ansi2, yellow: t.ansi3, violet: t.ansi5, blue,
    // A host's teal: blue and done, half each.
    teal: mix(blue, done, 0.5),
    ...(washes(t) ?? { w4: subtle, w7: subtle, w12: selected, w14: selected }),
    // Dawn Mode's inks and its sky's art, in this theme.
    dawn: DAWN[isDay(t) ? "light" : "dark"],
  };
}

const TONE = {
  red: "blocked", blocked: "blocked",
  yellow: "working", working: "working",
  green: "done", done: "done",
  violet: "violet", dim: "dim", muted: "muted", fg: "text", accent: "accent",
  blue: "blue", teal: "teal",
};
export const toneColor = (c, tone) => c[TONE[tone] ?? "dim"];

const RGB = /^#[0-9a-f]{6}/i;
// The kit's color-mix: `a` over an opaque `b`, `share` of the way.
export function mix(a, b, share) {
  if (!RGB.test(a ?? "") || !RGB.test(b ?? "")) return a;
  const at = (hex, i) => parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16);
  return `#${[0, 1, 2].map((i) => Math.round(at(a, i) * share + at(b, i) * (1 - share)).toString(16).padStart(2, "0")).join("")}`;
}

const HEX = /^#[0-9a-f]{6}(?:[0-9a-f]{2})?$/i;
// `hex` at `share` opacity: it lets the ground below show through; any other colour stays as it is.
export const alpha = (hex, share) => (RGB.test(hex ?? "") ? `${hex.slice(0, 7)}${Math.round(share * 255).toString(16).padStart(2, "0")}` : hex);
const lightness = (hex) => [0, 1, 2].reduce((sum, i) => sum + parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16), 0);
// A light theme: its ground is lighter than its ink.
const isDay = (t) => {
  const fg = t.foreground, bg = t.background ?? t.canvas;
  return HEX.test(fg ?? "") && HEX.test(bg ?? "") && lightness(bg) > lightness(fg);
};
/** The foreground washes w4, w7, w12, w14 at the light or the dark theme's shares; null without a #rrggbb foreground, so a caller keeps its opaque token. */
export function washes(t = {}) {
  const fg = t.foreground;
  if (!HEX.test(fg ?? "")) return null;
  return Object.fromEntries(Object.entries(isDay(t) ? WASHES.light : WASHES.dark).map(([name, share]) => [name, alpha(fg, share)]));
}

export const WASH = { off: 0.04, hover: 0.88, press: 0.76 };
// A focus ring is a border kept this colour at rest.
export const CLEAR = "#00000000";
// The 4% wash: a disabled control's ground.
export const well = (c) => mix(c.text, c.background, WASH.off);
