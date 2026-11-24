import { contractStrings } from "./contract-language.js";
import { recapStrings } from "./recap-language.js";

/** Recap is always first; specialized pages are conditional, before code steps. */
export function reportPages(walkthrough, view, language = "en", { task = Array.isArray(walkthrough?.asks) } = {}) {
  if (!view) return [];
  return [
    { kind: "recap", title: recapStrings(language).recap },
    ...(task ? [{ kind: "task", title: "Task" }] : []),
    ...(walkthrough?.contracts ?? []).map((contract, index) => ({ kind: "contract", title: contractStrings(language).kinds[contract.kind], contract, index })),
    ...view.steps.map((step) => ({ kind: "step", title: step.title, step })),
    { kind: "tail", title: "Not covered" },
  ];
}

/** File buttons prefer steps owning the component's hunks, then other uses of
 * the same exact path. Page indices include all conditional contract pages. */
export function blueprintFileTargets(walkthrough, view, files, component, path, language = "en") {
  if (!component?.paths.includes(path) || !view) return [];
  const componentIds = new Set(component.hunkIds);
  const pathIds = new Set(files.filter((f) => f.path === path).flatMap((f) => f.hunks.map((h) => h.id)).filter((id) => componentIds.has(id)));
  // A single-file component retains an unambiguous saved destination even if
  // the live diff has changed. Its step already explains outdated fragments.
  if (component.paths.length === 1) for (const id of componentIds) pathIds.add(id);
  const overlaps = (ids) => ids.some((id) => pathIds.has(id));
  return reportPages(walkthrough, view, language).flatMap((page, index) => {
    if (page.kind === "step") {
      if (overlaps(page.step.hunkIds)) return [{ index, title: page.title, kind: page.kind, priority: 0 }];
      if (page.step.found.some((hit) => hit.file.path === path)) return [{ index, title: page.title, kind: page.kind, priority: 1 }];
    }
    if (page.kind === "contract" && overlaps(page.contract.changes.flatMap((c) => c.hunkIds))) {
      return [{ index, title: page.title, kind: page.kind, priority: 2 }];
    }
    if (page.kind === "tail" && view.uncovered.some((u) => u.file.path === path)) {
      return [{ index, title: page.title, kind: page.kind, priority: 3 }];
    }
    return [];
  }).sort((a, b) => a.priority - b.priority || a.index - b.index);
}
