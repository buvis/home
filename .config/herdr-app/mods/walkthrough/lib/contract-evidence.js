/** Resolve only this change's saved hunk identities, never whole files/pages. */
export function contractChangeEvidence(change, files = []) {
  const ids = new Set(change?.hunkIds ?? []), found = [];
  for (const file of files) for (const hunk of file.hunks) if (ids.has(hunk.id)) found.push({ file, hunk });
  const present = new Set(found.map((hit) => hit.hunk.id));
  return { found, missing: [...ids].filter((id) => !present.has(id)).length };
}

/** Saved step anchors remain navigable when the live source becomes stale. */
export function contractChangeTargets(pages, change) {
  const ids = new Set(change?.hunkIds ?? []);
  return pages.flatMap((page, index) => page.kind === 'step' && page.step.hunkIds.some((id) => ids.has(id))
    ? [{ index, title: page.title, stepId: page.step.id }] : []);
}
