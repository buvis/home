// SVG conversion/build adaptation from jjongkwann/herdr-files-plus (MIT).
// See licenses/Herdr-Files-Plus-MIT.txt and THIRD_PARTY.md.

// ---- CSS variables and color-mix() → concrete colors (the SVG loader understands neither).

function hex(c) {
  const m = /^#([0-9a-f]{3,8})$/i.exec(c.trim());
  if (!m) return null;
  let h = m[1];
  if (h.length === 3 || h.length === 4) h = [...h].map(x => x + x).join("");
  if (h.length !== 6 && h.length !== 8) return null;
  return [...[0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)), h.length === 8 ? parseInt(h.slice(6), 16) : 255];
}
const toHex = rgb => "#" + rgb.map(v => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");

function args(s) {
  const out = [];
  let depth = 0, start = 0;
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "(") depth++;
    else if (s[i] === ")") depth--;
    else if (s[i] === "," && depth === 0) { out.push(s.slice(start, i)); start = i + 1; }
  }
  out.push(s.slice(start));
  return out.map(a => a.trim());
}
function closing(s, open) {
  let depth = 0;
  for (let i = open; i < s.length; i++) {
    if (s[i] === "(") depth++;
    else if (s[i] === ")" && --depth === 0) return i;
  }
  return -1;
}

function evaluate(expr, vars, depth = 0) {
  expr = expr.trim();
  const fn = /^(var|color-mix)\(/.exec(expr);
  if (!fn || depth > 16) return expr;
  const end = closing(expr, fn[0].length - 1);
  const [first, ...rest] = args(expr.slice(fn[0].length, end));
  if (fn[1] === "var") {
    if (vars.has(first)) return vars.get(first);
    return rest.length ? evaluate(rest.join(","), vars, depth + 1) : "currentColor";
  }
  // color-mix(in srgb, A p%, B [q%])
  const stop = s => { const m = /^(.*?)(?:\s+([\d.]+)%)?$/.exec(s); return [evaluate(m[1], vars, depth + 1), m[2] === undefined ? null : +m[2]]; };
  const [[a, pa], [b, pb]] = rest.map(stop);
  const ca = hex(a ?? ""), cb = hex(b ?? "");
  if (!ca || !cb) return ca ? a : b;
  const p = pa ?? (pb === null ? 50 : 100 - pb);
  return toHex(ca.map((v, i) => (v * p + cb[i] * (100 - p)) / 100));
}

// Replaces every var()/color-mix() in a piece of CSS.
function resolve(css, vars) {
  let out = "", i = 0;
  for (;;) {
    const at = css.slice(i).search(/(var|color-mix)\(/);
    if (at < 0) return out + css.slice(i);
    const start = i + at, end = closing(css, css.indexOf("(", start));
    if (end < 0) return out + css.slice(i);
    out += css.slice(i, start) + evaluate(css.slice(start, end + 1), vars);
    i = end + 1;
  }
}

const STYLE = /<style>([\s\S]*?)<\/style>/g, ROOT = /^<svg\b[^>]*>/, ATTR = /(\s[\w:-]+=")([^"]*)(")/g;

/**
 * Rewrites the renderer's SVG so every color is literal and no remote font is fetched.
 * Only its <style> block and attribute values are touched; diagram text is left alone.
 */
export function flattenSvg(svg, font) {
  font = font.split(",").map(f => f.trim()).map(f => /^[\w-]+$/.test(f) ? f : `'${f.replace(/['"]/g, "")}'`).join(", ");
  // Variables come only from the root element's style and the <style> block, resolved once each, in order.
  const vars = new Map();
  const declarations = [ROOT.exec(svg)?.[0] ?? "", ...[...svg.matchAll(STYLE)].map(m => m[1])].join("\n");
  for (const m of declarations.matchAll(/(--[\w-]+)\s*:\s*([^;}"]+)/g))
    if (!vars.has(m[1])) vars.set(m[1], evaluate(resolve(m[2].trim(), vars), vars));
  const css = text => resolve(text, vars)
    .replace(/@import\s+url\([^)]*\)[^;]*;/g, "")
    .replace(/\s*--[\w-]+\s*:\s*[^;}"]+;?/g, "")
    .replace(/font-family\s*:\s*[^;}"]+/g, `font-family: ${font}`);
  return svg
    .replace(STYLE, (_, body) => `<style>${css(body)}</style>`)
    .replace(/<[a-zA-Z][^>]*>/g, tag => tag.replace(ATTR, (_, pre, value, post) =>
      pre.trim().startsWith("font-family=") ? `${pre}${font.replaceAll('"', "'")}${post}` : pre + css(value) + post));
}
