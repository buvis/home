import { createHash } from "crypto";
import { mkdir } from "fs/promises";
import { flattenSvg } from "./svg-colors.js";

export const DIAGRAM_LIMIT = 12;
const OPTIONS = {
  bg: "#fdf6e3", fg: "#586e75", line: "#657b83", accent: "#268bd2",
  muted: "#657b83", border: "#93a1a1", font: "Helvetica Neue, Arial, sans-serif",
};
const CACHE_DIR = "data/folio-diagrams";
const CACHE_VERSION = 1;
const cache = new Map();

function diagramSize(svg) {
  const root = /^<svg\b[^>]*>/.exec(svg)?.[0] || "";
  const width = Number(/\swidth="([\d.]+)"/.exec(root)?.[1]);
  const height = Number(/\sheight="([\d.]+)"/.exec(root)?.[1]);
  if (!(width > 0 && height > 0)) throw new Error("Invalid or empty Mermaid diagram.");
  if (width > 4096 || height > 4096 || svg.length > 256000)
    throw new Error("Diagram exceeds the native preview size limit.");
  return { width, height };
}

export async function diagram(source, home, read, write) {
  if (source.length > 8000 || source.split("\n").length > 160)
    throw new Error("Diagram exceeds 8,000 characters or 160 lines.");
  const header = source.split("\n").map(line => line.trim()).find(line => line && !line.startsWith("%%")) || "";
  if (!/^(?:(?:graph|flowchart)\s+(?:TD|TB|BT|LR|RL)\b|sequenceDiagram\b|stateDiagram(?:-v2)?\b|classDiagram\b|erDiagram\b)/.test(header))
    throw new Error("Supported diagrams are flowchart, sequence, state, class and ER.");

  const hash = createHash("sha256").update(JSON.stringify([CACHE_VERSION, OPTIONS, source])).digest("hex");
  const path = `${CACHE_DIR}/${hash}.svg`, file = `${home}/${path}`;
  let pending = cache.get(file);
  if (!pending) {
    pending = (async () => {
      let svg = await read(file);
      if (svg === null) {
        const { renderMermaidSVG } = await import("./mermaid.bundle.js");
        svg = flattenSvg(renderMermaidSVG(source, OPTIONS), OPTIONS.font);
        const size = diagramSize(svg);
        await mkdir(`${home}/${CACHE_DIR}`, { recursive: true });
        try { await write(file, svg, null); }
        catch (error) { if (await read(file) !== svg) throw error; }
        return { path, ...size };
      }
      return { path, ...diagramSize(svg) };
    })();
  }
  cache.delete(file);
  cache.set(file, pending);
  if (cache.size > 24) cache.delete(cache.keys().next().value);
  try { return await pending; }
  catch (error) {
    if (cache.get(file) === pending) cache.delete(file);
    throw error;
  }
}
