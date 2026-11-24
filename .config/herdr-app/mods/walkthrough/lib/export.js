import { mermaidWithConnections } from "./diagram.js";
import { recapStrings } from "./recap-language.js";
import { contractStrings } from "./contract-language.js";
// A walkthrough as Markdown, to paste where people read changes: a pull
// request's description, a review comment, a chat. Steps keep their order,
// weights and notes; the code itself stays out, since wherever this is pasted
// the diff is already beside it.

import { fileTotals } from "./walkthrough.js";

const NOTE_LABEL = { choice: "Decision", upkeep: "Upkeep", gap: "Limitation", divergence: "Divergence", untested: "Untested" };

/** Model text on one line, for a heading, a bold title or a list item. */
const line = (s) => String(s ?? "").replace(/\s+/g, " ").trim();

/** A path in backticks, whatever backticks it holds. */
const code = (s) => {
  const t = String(s);
  const fence = "`".repeat((t.match(/`+/g) ?? []).reduce((n, m) => Math.max(n, m.length), 0) + 1);
  return fence.length > 1 ? `${fence} ${t} ${fence}` : `\`${t}\``;
};

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Shared by the report page and Markdown export. Its own words are in the report's language, like the contracts'. */
export function recapMarkdown(recap, { diagram = true, architecture = true, language = "en" } = {}) {
  const w = recapStrings(language);
  if (!recap) return `### ${w.recap}\n\nThis saved report predates recaps. Regenerate it to include all changes, motivations and architecture.\n`;
  const out = [`### ${w.recap}`, ""];
  for (const c of recap.changes) {
    out.push(`- **${w.change}:** ${line(c.description)}\n  **${w.motivation}:** ${line(c.motivation)}\n  **${w.files}:** ${c.paths.map(code).join(", ")}`, "");
  }
  if (recap.other?.length) out.push(`- **${w.other}:** ${recap.other.map(code).join(", ")}`, "");
  if (architecture && recap.architecture.description) out.push(`#### ${w.architecture}`, "", line(recap.architecture.description), "");
  if (diagram && recap.architecture.mermaid) out.push("```mermaid", mermaidWithConnections(recap.architecture.mermaid, recap.architecture.connections, recap.architecture.groups), "```", "");
  if (architecture && recap.architecture.components?.length) {
    out.push(`#### ${w.components}`, "");
    for (const c of recap.architecture.components) {
      out.push(`- **${line(c.id)} · ${w.status[c.status]}:** ${line(c.responsibility)}`);
      if (c.change) out.push(`  **${w.change}:** ${line(c.change)}`);
      if (c.paths.length) out.push(`  **${w.files}:** ${c.paths.map(code).join(", ")}`);
    }
    out.push("");
  }
  if (architecture && recap.architecture.groups?.length) {
    out.push(`#### ${w.groups}`, "");
    for (const g of recap.architecture.groups) out.push(`- **${line(g.title)}:** ${line(g.reason)}\n  **${w.components}:** ${g.nodes.map(code).join(", ")}`, "");
  }
  return out.join("\n");
}

/** Full excerpts use fences longer than any backticks in the source. */
const block = (s) => {
  const fence = "`".repeat(Math.max(3, ...(String(s).match(/`+/g) ?? []).map((m) => m.length + 1)));
  return `${fence}\n${s}\n${fence}`;
};
export function contractMarkdown(page, language = "en") {
  const words = contractStrings(language);
  const out = [`### ${words.kinds[page.kind]}: ${line(page.title)}`, "", page.summary, "", `**${words.compatibility[page.compatibility]}:** ${page.impact}`, ""];
  for (const c of page.changes) {
    out.push(`#### ${line(c.name)} · ${words.operations[c.operation]}`, "", `**${words.before}:**`, "", block(c.before || words.absent), "", `**${words.after}:**`, "", block(c.after || words.removed), "", c.detail, "");
  }
  out.push(`#### ${words.rollout}`, "");
  if (page.rollout.length) page.rollout.forEach((s, i) => out.push(`${i + 1}. ${line(s)}`));
  else out.push(words.noRollout);
  out.push("", page.paths.map(code).join(" · "), "");
  return out.join("\n");
}

/**
 * @param {ReturnType<typeof import("./walkthrough.js").overlay>} view the walkthrough over the diff as it is now
 * @param {{ title: string, summary: string }} walkthrough the stored walkthrough
 * @param {{ what?: string, model?: string, language?: string, cost?: number | null }} meta
 * @param {ReturnType<typeof import("./walkthrough.js").overlayAsks>} [task] the task's requests over the same view; null leaves them out
 * @param {string} [taskLabel] where the task came from, for the reader
 */
export function toMarkdown(view, walkthrough, { what = "", model = "", language = "", cost = null } = {}, task = null, taskLabel = "") {
  // The bounds let a walkthrough pasted into a pull request's description be left out when that description is read as a task.
  const out = [MARK_START, `## ${line(walkthrough.title) || "Walkthrough"}`, ""];
  if (walkthrough.summary?.trim()) out.push(walkthrough.summary.trim(), "");
  const about = [what && line(what), model, language, typeof cost === "number" ? `$${cost.toFixed(cost < 0.1 ? 3 : 2)}` : ""].filter(Boolean);
  if (about.length) out.push(`<sub>${about.join(" · ")}</sub>`, "");
  if (walkthrough.recap) out.push(recapMarkdown(walkthrough.recap, { language }));
  if (task) out.push(...taskMarkdown(task, taskLabel));
  for (const page of walkthrough.contracts ?? []) out.push(contractMarkdown(page, language));

  for (const part of view.parts) {
    out.push(`### ${line(part.title)}`, "");
    if (part.blurb?.trim()) out.push(part.blurb.trim(), "");
    for (const s of part.steps) {
      const marks = [s.weight === "key" ? "**Key change**" : s.weight === "skim" ? "_Context_" : "", s.outdated ? "_Outdated_" : ""].filter(Boolean);
      out.push(`**${s.position}. ${line(s.title)}**${marks.length ? ` · ${marks.join(" · ")}` : ""}`, "");
      out.push(s.text.trim(), "");
      for (const n of s.notes) out.push(`> **${NOTE_LABEL[n.kind] ?? n.kind}:** ${line(n.text)}`, "");
      if (s.outdated) out.push(`_${s.missing} of the ${plural(s.hunkIds.length, "hunk")} this step described changed or are gone._`, "");
      const files = fileTotals(s.found);
      if (files.length) out.push(files.map((f) => `${code(f.path)} +${f.added} −${f.deleted}`).join(" · "), "");
    }
  }

  if (view.uncovered.length) {
    out.push("### Not covered", "", `Edits in ${plural(view.uncovered.length, "file")} that no step explains:`, "");
    for (const u of view.uncovered) {
      const size = u.hunks.length ? ` (${plural(u.hunks.length, "hunk")})` : "";
      out.push(`- ${code(u.file.path)}${size}${u.note ? ` — ${line(u.note)}` : ""}`);
    }
    out.push("");
  }
  return `${out.join("\n").trimEnd()}\n${MARK_END}\n`;
}

export const MARK_START = "<!-- walkthrough -->", MARK_END = "<!-- /walkthrough -->";

const stepList = (steps) => (steps.length === 1 ? `step ${steps[0].position}` : `steps ${steps.map((s) => s.position).join(", ")}`);

/** The task's requests, each with where it shows up; then the steps no request points at. */
function taskMarkdown(task, label) {
  const out = ["### Task", ""];
  if (label) out.push(`<sub>${line(label)}</sub>`, "");
  if (!task.asks.length) return [...out, "_The task names nothing concrete to match against the change._", ""];
  for (const a of task.asks) {
    const where = [
      a.coverage === "absent" ? "not in this diff" : a.coverage === "partly" ? "partly" : "",
      a.steps.length ? stepList(a.steps) : "",
      a.tail ? "Not covered" : "",
      a.outdated ? "_outdated_" : "",
    ].filter(Boolean);
    out.push(`- ${a.coverage === "seen" ? "✓" : a.coverage === "partly" ? "◐" : "○"} ${line(a.text)}${where.length ? ` — ${where.join(", ")}` : ""}`);
  }
  out.push("");
  if (task.outside.length) out.push(`Not tied to any request: ${stepList(task.outside)}.`, "");
  return out;
}

