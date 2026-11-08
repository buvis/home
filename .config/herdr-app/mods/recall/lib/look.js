// The dialog's look: how large it is drawn against its design, and in
// which font. It follows Herdr's interface text size and font unless
// recall.json asks for its own (`font_size`, `font`).

/** The interface text size the dialog is designed at, in px: a row's name. */
export const DESIGN_TEXT = 13;

/** The range of Herdr's own zoom: past it the dialog stops being usable. */
const MIN_SCALE = 0.5;
const MAX_SCALE = 3;

const usable = (size) => typeof size === "number" && Number.isFinite(size) && size > 0;

/**
 * How many times its design size the dialog is drawn: the size asked for,
 * else Herdr's interface text size, against the design's. A Herdr that
 * reports no size leaves the dialog as designed.
 */
export function textScale(fontSize, interfaceSize) {
  const size = fontSize ?? (usable(interfaceSize) ? interfaceSize : DESIGN_TEXT);
  return Math.max(MIN_SCALE, Math.min(MAX_SCALE, size / DESIGN_TEXT));
}

/**
 * The font family to draw in: the one asked for, as this machine spells
 * it (`installed`: its font families), or null for Herdr's interface font
 * when none is asked for or the machine has no such font.
 */
export function pickFont(font, installed) {
  if (!font || !Array.isArray(installed)) return null;
  const wanted = font.toLowerCase();
  return installed.find((name) => typeof name === "string" && name.toLowerCase() === wanted) ?? null;
}
