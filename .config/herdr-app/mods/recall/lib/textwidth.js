// How wide a text is drawn. Herdr gives a mod no way to measure text, so
// the width is worked out from the characters, a little on the wide side: a
// column sized to it never cuts what it holds.

/**
 * Geist's printable ASCII, space to tilde, in thousandths of the text size,
 * as Herdr lays it out: each character drawn ten times over in Herdr 0.1.13
 * and read off a screenshot. Semibold is as wide as regular.
 */
const GEIST_ASCII = [
  244, 217, 350, 483, 633, 808, 625, 183, 275, 275, 433, 558, 208, 425, 208, 392,
  675, 350, 625, 617, 617, 633, 600, 550, 608, 600, 300, 300, 550, 542, 550, 567,
  908, 675, 675, 708, 708, 600, 575, 708, 700, 258, 575, 625, 558, 867, 733, 742,
  633, 733, 675, 642, 567, 692, 658, 942, 608, 600, 550, 350, 367, 350, 433, 558,
  250, 558, 592, 542, 592, 558, 325, 592, 583, 233, 258, 550, 258, 867, 567, 567,
  592, 592, 350, 517, 333, 583, 542, 825, 550, 542, 525, 392, 267, 392, 525,
];
/** The other characters Recall draws itself, measured the same way. */
const GEIST_OTHER = { "›": 333, "·": 208, "…": 575, "—": 908, "’": 208 };
/** A CJK character, as measured; any character without a measure is taken as wide as one. */
const WIDE = 1008;
/** A letter in a font without measures: a little over a fixed-width font's 0.6 of the text size. */
const UNMEASURED = 620;
/** Sums of the measures come out up to 1.5% under what Herdr draws: kerning, and rounding to whole px. */
const MARGIN = 1.02;

const GEIST = { ascii: (code) => GEIST_ASCII[code - 0x20], other: (ch) => GEIST_OTHER[ch] ?? WIDE };
const UNKNOWN = { ascii: () => UNMEASURED, other: () => WIDE };

/** The measures for a font family: Geist's, which is Herdr's interface font, or a fixed-width stand-in. */
export function metricsFor(family) {
  return family == null || String(family).toLowerCase() === "geist" ? GEIST : UNKNOWN;
}

/** The width of `text` at a text size, in the same px as the size; no text takes none. */
export function textWidth(text, size, metrics) {
  if (!text) return 0;
  let thousandths = 0;
  for (const ch of String(text)) {
    const code = ch.codePointAt(0);
    thousandths += code >= 0x20 && code < 0x7f ? metrics.ascii(code) : metrics.other(ch);
  }
  return Math.ceil((thousandths * size * MARGIN) / 1000) + 1;
}
