import { graphOf, safeId } from "./diagram.js";
import { filesByAlias, resolveHunks } from "./alias.js";

export const COMPONENT_LABELS = { added: "Added", modified: "Modified", context: "Context" };
const str = { type: "string" };
export const COMPONENT_SCHEMA = {
  type: "array",
  items: {
    type: "object", additionalProperties: false,
    required: ["id", "status", "responsibility", "change", "paths", "hunks"],
    properties: {
      id: str, status: { type: "string", enum: Object.keys(COMPONENT_LABELS) },
      responsibility: str, change: str,
      paths: { type: "array", items: str }, hunks: { type: "array", items: str },
    },
  },
};
const text = (v) => typeof v === "string" ? v.trim() : "";

/**
 * Exact node identities and source anchors, never filename/label heuristics.
 * Forgiving like steps: a component that doesn't hold up against the diagram
 * or the digest is left out and counted in `omit.count`, never failing the
 * report. Its node is still drawn, without details. Paths follow the hunks
 * cited, so a component's files are always the ones its evidence is in.
 */
export function normalizeComponents(raw, mermaid, aliases, files, omit = { count: 0 }) {
  if (raw === undefined) return undefined; // Older reports retain an unclassified diagram.
  if (!Array.isArray(raw)) { omit.count++; return []; }
  const ids = new Set(graphOf(mermaid).nodes.map((n) => n.id)), seen = new Set();
  const fileByAlias = filesByAlias(files);
  const out = [];
  for (const c of raw) {
    const id = safeId(text(c?.id)), responsibility = text(c?.responsibility);
    let status = c?.status, change = text(c?.change);
    if (!ids.has(id) || seen.has(id) || !Object.hasOwn(COMPONENT_LABELS, status) || !responsibility) { omit.count++; continue; }
    // A component in the resulting architecture is shown by code that remains.
    const hits = status === "context" ? [] : resolveHunks(c.hunks, aliases, fileByAlias, (f) => f.status !== "deleted");
    if (status !== "context" && !hits.length) { omit.count++; continue; }
    // Added means every file it is shown in is new; any other evidence makes it Modified.
    if (status === "added" && hits.some((h) => h.file.status !== "added")) status = "modified";
    // Context is what the diff doesn't touch: it claims no change and no files.
    if (status === "context") change = "";
    seen.add(id);
    out.push({ id, status, responsibility, change, paths: [...new Set(hits.map((h) => h.file.path))], hunkIds: hits.map((h) => h.id) });
  }
  return out;
}

/** Resolve saved anchors against the current diff, including staged/working copies. */
export function componentEvidence(component, files = []) {
  const wanted = new Set(component?.hunkIds ?? []), found = [];
  for (const file of files) for (const hunk of file.hunks) {
    if (wanted.has(hunk.id) && component.paths.includes(file.path)) found.push({ file, hunk });
  }
  const resolved = new Set(found.map((hit) => hit.hunk.id));
  return { found, missing: [...wanted].filter((id) => !resolved.has(id)).length };
}
