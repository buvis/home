import { filesByAlias, resolveHunks } from "./alias.js";
// Evidence-anchored contract changes, kept separate from the reading order.
export const CONTRACT_KINDS = ["database", "protobuf", "api"];
export const COMPATIBILITY = ["additive", "breaking", "mixed", "unknown"];
export const OPERATIONS = ["added", "removed", "modified"];
const str = { type: "string" };
export const CONTRACT_SCHEMA = {
  type: "array",
  items: {
    type: "object", additionalProperties: false,
    required: ["kind", "title", "summary", "compatibility", "impact", "changes", "rollout"],
    properties: {
      kind: { type: "string", enum: CONTRACT_KINDS }, title: str, summary: str,
      compatibility: { type: "string", enum: COMPATIBILITY }, impact: str,
      changes: { type: "array", items: {
        type: "object", additionalProperties: false,
        required: ["name", "operation", "before", "after", "detail", "hunks"],
        properties: {
          name: str, operation: { type: "string", enum: OPERATIONS }, before: str, after: str, detail: str,
          hunks: { type: "array", items: str },
        },
      } },
      rollout: { type: "array", items: str },
    },
  },
};
const text = (v) => typeof v === "string" ? v.trim() : "";

/**
 * Contract pages, each change anchored to the hunks that show it. Forgiving
 * like steps: a change with no real evidence, or with no state to compare, is
 * left out; a page left with no change, or without its explanation, is left
 * out; a duplicate kind keeps its first page. Each is counted in `omit.count`.
 * A state the operation rules out (a "before" for something added) is cleared
 * rather than refused: models write "(none)" there.
 */
export function normalizeContracts(raw, idByAlias, files, omit = { count: 0 }) {
  if (raw === undefined) return []; // Earlier saved reports remain readable.
  if (!Array.isArray(raw)) { omit.count++; return []; }
  const seen = new Set(), fileByAlias = filesByAlias(files), pages = [];
  for (const page of raw) {
    const kind = page?.kind, title = text(page?.title), summary = text(page?.summary), impact = text(page?.impact);
    if (!CONTRACT_KINDS.includes(kind) || seen.has(kind) || !title || !summary || !impact) { omit.count++; continue; }
    const paths = new Set(), changes = [];
    for (const c of Array.isArray(page.changes) ? page.changes : []) {
      const name = text(c?.name), detail = text(c?.detail), operation = c?.operation;
      const before = operation === "added" ? "" : text(c?.before), after = operation === "removed" ? "" : text(c?.after);
      const hits = resolveHunks(c?.hunks, idByAlias, fileByAlias);
      if (!name || !detail || !OPERATIONS.includes(operation) || (operation !== "added" && !before) || (operation !== "removed" && !after) || !hits.length) { omit.count++; continue; }
      for (const h of hits) paths.add(h.file.path);
      changes.push({ name, operation, before, after, detail, hunkIds: hits.map((h) => h.id) });
    }
    if (!changes.length) { omit.count++; continue; }
    seen.add(kind);
    const compatibility = COMPATIBILITY.includes(page.compatibility) ? page.compatibility : "unknown";
    const rollout = (Array.isArray(page.rollout) ? page.rollout : []).map(text).filter(Boolean);
    pages.push({ kind, title, summary, compatibility, impact, changes, rollout, paths: [...paths] });
  }
  return pages.sort((a, b) => CONTRACT_KINDS.indexOf(a.kind) - CONTRACT_KINDS.indexOf(b.kind));
}

