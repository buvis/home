import { CONTRACT_SCHEMA, normalizeContracts } from "./contracts.js";
import { COMPONENT_SCHEMA, normalizeComponents } from "./blueprint.js";
import { CONNECTION_SCHEMA, normalizeConnections } from "./connections.js";
import { GROUP_SCHEMA, normalizeGroups } from "./groups.js";
import { parseMermaid, canonicalMermaid } from "./diagram.js";
import { idOf } from "./alias.js";

// The walkthrough's shape, how a model's answer is made safe, and how a stored
// walkthrough is laid over the diff as it is now.
//
// The model is trusted for grouping and prose only. Every alias it returns is
// looked up in the digest it was given; one that isn't there is dropped, never
// drawn as a step pointing at nothing.

export const VERSION = 1;
// Part of every cache key: a different prompt writes a different walkthrough.
export const PROMPT_VERSION = 3;

export const LIMITS = { parts: 6, steps: 16, hunksPerStep: 14, partTitle: 28, notes: 6, notesPerStep: 2, skipped: 200, asks: 12, askText: 200 };
export const WEIGHTS = ["key", "normal", "skim"];
export const NOTE_KINDS = ["choice", "upkeep", "gap", "divergence", "untested"];
// How much of a request in the task the diff carries out: all of it, part of it, or none of it that can be seen here.
export const COVERAGE = ["seen", "partly", "absent"];

const str = { type: "string" };
export const SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["title", "summary", "recap", "contracts", "parts", "skipped"],
  properties: {
    title: str,
    summary: str,
    contracts: CONTRACT_SCHEMA,
    recap: {
      type: "object", additionalProperties: false,
      required: ["changes", "architecture"],
      properties: {
        changes: { type: "array", items: {
          type: "object", additionalProperties: false,
          required: ["description", "motivation", "paths"],
          properties: { description: str, motivation: str, paths: { type: "array", items: str } },
        } },
        architecture: {
          type: "object", additionalProperties: false,
          required: ["description", "mermaid", "components", "connections", "groups"],
          properties: { description: str, mermaid: str, components: COMPONENT_SCHEMA, connections: CONNECTION_SCHEMA, groups: GROUP_SCHEMA },
        },
      },
    },
    parts: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["title", "blurb", "steps"],
        properties: {
          title: str,
          blurb: str,
          steps: {
            type: "array",
            items: {
              type: "object",
              additionalProperties: false,
              required: ["title", "hunks", "weight", "text", "notes"],
              properties: {
                title: str,
                hunks: { type: "array", items: str },
                weight: { type: "string", enum: WEIGHTS },
                text: str,
                notes: {
                  type: "array",
                  items: {
                    type: "object",
                    additionalProperties: false,
                    required: ["kind", "text"],
                    properties: { kind: { type: "string", enum: NOTE_KINDS }, text: str },
                  },
                },
              },
            },
          },
        },
      },
    },
    skipped: {
      type: "array",
      items: { type: "object", additionalProperties: false, required: ["path", "note"], properties: { path: str, note: str } },
    },
  },
};

/** The shape asked for: with a task, the requests it makes and the hunks that carry each out. */
export function schemaFor(withTask) {
  if (!withTask) return SCHEMA;
  return {
    ...SCHEMA,
    required: [...SCHEMA.required, "asks"],
    properties: {
      ...SCHEMA.properties,
      asks: {
        type: "array",
        items: {
          type: "object",
          additionalProperties: false,
          required: ["text", "hunks", "coverage"],
          properties: { text: str, hunks: { type: "array", items: str }, coverage: { type: "string", enum: COVERAGE } },
        },
      },
    },
  };
}

const text = (value, max = 0) => {
  if (typeof value !== "string") return "";
  const t = value.trim();
  return max && t.length > max ? `${t.slice(0, max - 1)}…` : t;
};

const fail = (message) => Object.assign(new Error(message), { code: "invalid" });

/**
 * A model's answer → a walkthrough whose steps hold real hunk ids.
 * @param {any} raw the parsed answer
 * @param {Record<string, string>} idByAlias from the digest
 * @param {{ path: string, aliases: string[] }[]} digestFiles from the digest, to place skipped notes
 * @param {{ asks?: boolean }} options asks: a task was given, so its requests are read (else `asks` is null)
 */
export function normalize(raw, idByAlias, digestFiles = [], { asks: withTask = false } = {}) {
  if (!raw || typeof raw !== "object") throw fail("The model returned no walkthrough.");
  const used = new Set();
  let steps = 0, notes = 0, dropped = 0;
  const parts = [];

  for (const rawPart of Array.isArray(raw.parts) ? raw.parts : []) {
    if (parts.length >= LIMITS.parts) break;
    if (!rawPart || typeof rawPart !== "object") continue;
    const partSteps = [];
    for (const rawStep of Array.isArray(rawPart.steps) ? rawPart.steps : []) {
      if (steps >= LIMITS.steps) break;
      if (!rawStep || typeof rawStep !== "object") continue;
      const hunkIds = [];
      for (const alias of Array.isArray(rawStep.hunks) ? rawStep.hunks : []) {
        const id = idOf(idByAlias, alias);
        if (!id) { dropped++; continue; }
        // A hunk is told once; a second mention would draw the same code twice.
        if (used.has(id) || hunkIds.includes(id) || hunkIds.length >= LIMITS.hunksPerStep) continue;
        hunkIds.push(id);
      }
      const body = text(rawStep.text);
      // A step that is dropped claims nothing: its hunks stay free for a later step or a skipped note.
      if (!hunkIds.length || !body) continue;
      for (const id of hunkIds) used.add(id);
      const stepNotes = [];
      for (const n of Array.isArray(rawStep.notes) ? rawStep.notes : []) {
        if (stepNotes.length >= LIMITS.notesPerStep || notes >= LIMITS.notes) break;
        const t = text(n?.text);
        if (!t || !NOTE_KINDS.includes(n.kind)) continue;
        stepNotes.push({ kind: n.kind, text: t });
        notes++;
      }
      steps++;
      partSteps.push({
        id: `s${steps}`,
        title: text(rawStep.title, 120) || `Step ${steps}`,
        weight: WEIGHTS.includes(rawStep.weight) ? rawStep.weight : "normal",
        text: body,
        notes: stepNotes,
        hunkIds,
      });
    }
    if (!partSteps.length) continue;
    parts.push({ title: text(rawPart.title, LIMITS.partTitle) || `Part ${parts.length + 1}`, blurb: text(rawPart.blurb), steps: partSteps });
  }
  if (!parts.length) throw fail("The model's answer had no usable steps for this diff.");

  // A skipped note belongs to a file the model read and some step left partly out.
  const leftOut = new Set(digestFiles.filter((f) => f.aliases.some((a) => !used.has(idByAlias[a]))).map((f) => f.path));
  const skipped = [];
  const noted = new Set();
  for (const s of Array.isArray(raw.skipped) ? raw.skipped : []) {
    if (skipped.length >= LIMITS.skipped) break;
    const path = text(s?.path), note = text(s?.note, 200);
    if (!note || !leftOut.has(path) || noted.has(path)) continue;
    noted.add(path);
    skipped.push({ path, note });
  }

  // Steps are the only part an answer must have. A recap, blueprint or contract
  // detail that doesn't hold up is left out and counted, never failing the run.
  const recapOmit = { count: 0 }, contractOmit = { count: 0 };
  const recap = normalizeRecap(raw.recap, digestFiles, idByAlias, recapOmit);
  const contracts = normalizeContracts(raw.contracts, idByAlias, digestFiles, contractOmit);
  const asks = withTask ? normalizeAsks(raw.asks, idByAlias) : null;
  const omitted = { recap: recapOmit.count, contracts: contractOmit.count };
  return {
    recap, contracts, asks, title: text(raw.title, 140) || "Walkthrough", summary: text(raw.summary), parts, skipped, dropped,
    ...(omitted.recap || omitted.contracts ? { omitted } : {}),
  };
}

/**
 * The recap: what changed and why, and the architecture it lands in. Every
 * part is checked against the digest, and what doesn't hold up is left out and
 * counted in `omit.count`: a change without its reason
 * or real files, a diagram outside the drawn subset (the blueprint then goes
 * with it, the description stays), a component, label or boundary without
 * evidence. Files no change names are listed under `other`, never lost.
 */
function normalizeRecap(raw, files, idByAlias, omit = { count: 0 }) {
  // None at all reads as a report from before recaps: the page offers to regenerate.
  if (!raw || typeof raw !== "object") return null;
  const known = new Set(files.map((f) => f.path));
  const changes = [];
  for (const c of Array.isArray(raw?.changes) ? raw.changes : []) {
    const description = text(c?.description), motivation = text(c?.motivation);
    const paths = [...new Set((Array.isArray(c?.paths) ? c.paths : []).map((p) => text(p)).filter((p) => known.has(p)))];
    if (!description || !motivation || !paths.length) { omit.count++; continue; }
    changes.push({ description, motivation, paths });
  }
  const covered = new Set(changes.flatMap((c) => c.paths));
  const other = [...known].filter((path) => !covered.has(path));
  const rawArchitecture = raw?.architecture;
  const architecture = { description: text(rawArchitecture?.description), mermaid: "" };
  try {
    architecture.mermaid = canonicalMermaid(rawArchitecture?.mermaid);
  } catch {
    omit.count++;
  }
  if (architecture.mermaid) {
    const graph = parseMermaid(architecture.mermaid);
    const components = normalizeComponents(rawArchitecture?.components, graph, idByAlias, files, omit);
    const connections = normalizeConnections(rawArchitecture?.connections, graph, idByAlias, files, omit);
    const groups = normalizeGroups(rawArchitecture?.groups, graph, components, idByAlias, files, omit);
    if (components !== undefined) architecture.components = components;
    if (connections !== undefined) architecture.connections = connections;
    if (groups !== undefined) architecture.groups = groups;
  }
  return { changes, ...(other.length ? { other } : {}), architecture };
}


/**
 * The task's requests, each with real hunk ids. Coverage follows the hunks,
 * not the model's word alone: a request with no hunk found in the digest is
 * "absent" whatever it was called, and one called absent that names hunks
 * is "partly". A hunk may serve several requests.
 */
function normalizeAsks(rawAsks, idByAlias) {
  const asks = [];
  for (const a of Array.isArray(rawAsks) ? rawAsks : []) {
    if (asks.length >= LIMITS.asks) break;
    const body = text(a?.text, LIMITS.askText);
    if (!body) continue;
    const hunkIds = [];
    for (const alias of Array.isArray(a.hunks) ? a.hunks : []) {
      const id = idOf(idByAlias, alias);
      if (id && !hunkIds.includes(id)) hunkIds.push(id);
    }
    const said = COVERAGE.includes(a.coverage) ? a.coverage : "seen";
    const coverage = !hunkIds.length ? "absent" : said === "absent" ? "partly" : said;
    asks.push({ id: `a${asks.length + 1}`, text: body, coverage, hunkIds });
  }
  return asks;
}

/**
 * A walkthrough's requests over the diff as it is now (an `overlay` view):
 * each with the steps that carry it out, how many of its hunks only show
 * under Not covered, and whether its code has changed since; then the steps
 * no request points at. Null when the walkthrough was written without a task.
 */
export function overlayAsks(asks, view) {
  if (!Array.isArray(asks)) return null;
  const stepOf = new Map();
  for (const s of view.steps) for (const f of s.found) stepOf.set(f.hunk.id, s);
  const current = new Set(stepOf.keys());
  for (const u of view.uncovered) for (const h of u.hunks) current.add(h.id);
  const tied = new Set();
  const list = asks.map((a) => {
    const steps = [];
    let tail = 0, missing = 0;
    for (const id of a.hunkIds) {
      const s = stepOf.get(id);
      if (s) { tied.add(s.id); if (!steps.includes(s)) steps.push(s); } else if (current.has(id)) tail++; else missing++;
    }
    steps.sort((x, y) => x.position - y.position);
    return { ...a, steps, tail, missing, outdated: missing > 0 };
  });
  // With no requests to tie steps to, no step is outside them.
  const outside = asks.length ? view.steps.filter((s) => !tied.has(s.id)) : [];
  const met = list.filter((a) => a.coverage !== "absent").length;
  return { asks: list, outside, met, total: list.length };
}

/** The requests a step carries out, in the task's order. */
export const asksOf = (task, step) => (task ? task.asks.filter((a) => a.steps.includes(step)) : []);

/** The JSON object in a model's text answer, also when wrapped in a fence or prose. */
export function parseJson(answer) {
  if (answer && typeof answer === "object") return answer;
  const t = String(answer ?? "").trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  if (!t) throw fail("The model's answer was empty.");
  try { return JSON.parse(t); } catch { /* look for the outermost object */ }
  const start = t.indexOf("{");
  for (let end = t.lastIndexOf("}"); start !== -1 && end > start; end = t.lastIndexOf("}", end - 1)) {
    try { return JSON.parse(t.slice(start, end + 1)); } catch { /* shrink from the right */ }
  }
  throw fail("The model's answer was not JSON.");
}

/**
 * A stored walkthrough over the current diff: each step with the hunks it
 * still finds, marked outdated when one is gone, and every hunk no step
 * covers, file by file, with the model's note for that file.
 *
 * @param {any} walkthrough a normalized walkthrough
 * @param {any[]} files the current diff's files (with `generated`)
 */
export function overlay(walkthrough, files) {
  const index = new Map();
  for (const f of files) for (const h of f.hunks) index.set(h.id, { hunk: h, file: f });
  const covered = new Set();
  const steps = [];
  const parts = walkthrough.parts.map((part, p) => ({
    ...part,
    steps: part.steps.map((step) => {
      const found = [], missing = [];
      for (const id of step.hunkIds) {
        const hit = index.get(id);
        if (hit) { found.push(hit); covered.add(id); } else missing.push(id);
      }
      const view = { ...step, part: p, position: steps.length + 1, found, missing: missing.length, outdated: missing.length > 0 };
      steps.push(view);
      return view;
    }),
  }));
  const notes = new Map(walkthrough.skipped.map((s) => [s.path, s.note]));
  const uncovered = files
    .map((f) => ({ file: f, hunks: f.hunks.filter((h) => !covered.has(h.id)) }))
    // A file with no hunks (binary, a bare rename, a mode change) is only ever here.
    .filter(({ file, hunks }) => hunks.length > 0 || file.hunks.length === 0)
    .map(({ file, hunks }) => ({
      file, hunks,
      note: notes.get(file.path) ?? (file.status === "conflicted" ? "Merge conflict: not read. Resolve it, and it is read again."
        : file.generated ? "Generated file, not sent to the model." : file.binary ? "Binary file." : ""),
    }));
  return { parts, steps, uncovered, outdated: steps.filter((s) => s.outdated).length };
}

/** Lines added and removed per file across a set of hunks, in order of appearance. */
export function fileTotals(found) {
  const by = new Map();
  for (const { hunk, file } of found) {
    const t = by.get(file.path) ?? { path: file.path, added: 0, deleted: 0 };
    t.added += hunk.added;
    t.deleted += hunk.deleted;
    by.set(file.path, t);
  }
  return [...by.values()];
}
