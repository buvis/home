import { graphOf, safeId } from "./diagram.js";
import { filesByAlias, resolveHunks, plainLabel } from "./alias.js";

export const GROUP_SCHEMA = {
  type: "array",
  items: {
    type: "object", additionalProperties: false,
    required: ["id", "title", "nodes", "reason", "hunks"],
    properties: {
      id: { type: "string" }, title: { type: "string" },
      nodes: { type: "array", items: { type: "string" } },
      reason: { type: "string" }, hunks: { type: "array", items: { type: "string" } },
    },
  },
};
const MAX_GROUPS = 8;

/**
 * Model proposes boundaries; node membership and evidence are checked locally.
 * A member its own component's evidence doesn't support is left ungrouped; a
 * boundary left with no member, no reason or no real evidence is left out.
 * Each is counted in `omit.count`, and the rest of the blueprint stands.
 */
export function normalizeGroups(raw, source, components, aliases, files, omit = { count: 0 }) {
  if (raw === undefined) return undefined;
  if (!Array.isArray(raw)) { omit.count++; return []; }
  const nodeIds = new Set(graphOf(source).nodes.map((n) => n.id));
  const groupIds = new Set(), assigned = new Set();
  const componentById = new Map((components ?? []).map((c) => [c.id, c]));
  const fileByAlias = filesByAlias(files);
  const out = [];
  for (const g of raw) {
    if (out.length >= MAX_GROUPS) { omit.count++; continue; }
    const id = typeof g?.id === "string" ? safeId(g.id.trim()) : "";
    const title = plainLabel(g?.title, 48), reason = typeof g?.reason === "string" ? g.reason.trim() : "";
    const hits = resolveHunks(g?.hunks, aliases, fileByAlias, (f) => f.status !== "deleted");
    if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(id) || nodeIds.has(id) || groupIds.has(id) || !title || !reason || !hits.length) { omit.count++; continue; }
    const hunkIds = new Set(hits.map((h) => h.id));
    const nodes = [];
    for (const raw of Array.isArray(g.nodes) ? g.nodes : []) {
      const node = typeof raw === "string" ? safeId(raw.trim()) : "";
      // A component belongs to one boundary, and only when the boundary's evidence includes its own.
      const supported = componentById.get(node)?.hunkIds.some((h) => hunkIds.has(h));
      if (!nodeIds.has(node) || assigned.has(node) || nodes.includes(node) || !supported) { omit.count++; continue; }
      nodes.push(node);
    }
    if (!nodes.length) { omit.count++; continue; }
    for (const node of nodes) assigned.add(node);
    groupIds.add(id);
    out.push({ id, title, nodes, reason, paths: [...new Set(hits.map((h) => h.file.path))], hunkIds: [...hunkIds] });
  }
  return out;
}
