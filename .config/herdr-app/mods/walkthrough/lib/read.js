// What the reader has read, kept per repository: one entry per hunk read, by
// its content, so it survives a walkthrough being regenerated, a scope being
// switched, and a hunk being staged.
//
// A read record is a plain object, { "<path>:<digest>": ms }, the time each
// hunk was marked. A hunk id is `<scope>:<path>:<digest>`; the scope is
// dropped, so the same edit staged or unstaged, or seen on its branch, is the
// same hunk read. Its digest is of its content, so an edit makes it unread.

/** A hunk id without its scope: `staged:a.js:1f2e3d4c` → `a.js:1f2e3d4c`. Scopes never hold a colon. */
export const readKey = (hunkId) => {
  const at = String(hunkId).indexOf(":");
  return at === -1 ? String(hunkId) : String(hunkId).slice(at + 1);
};

/** The path in a read key (a path may hold a colon; a digest never does). */
export const pathOf = (key) => key.slice(0, Math.max(0, key.lastIndexOf(":")));

/** Whether one hunk is read. */
export const hunkRead = (hunkId, read) => Object.hasOwn(read, readKey(hunkId));

/** Whether every hunk of a step is read. A step with no hunks is never read. */
export const stepRead = (step, read) => step.hunkIds.length > 0 && step.hunkIds.every((id) => hunkRead(id, read));

/** A new record with every hunk of a step (or any `{ hunkIds }`) marked read now. */
export function markStep(step, read, now = Date.now()) {
  const next = { ...read };
  for (const id of step.hunkIds) next[readKey(id)] = now;
  return next;
}

/** A new record with every hunk of a step marked unread. */
export function unmarkStep(step, read) {
  const next = { ...read };
  for (const id of step.hunkIds) delete next[readKey(id)];
  return next;
}

/** At most `max` entries, the oldest marks going first. A hunk read long ago is likely long committed. */
export function prune(read, max = 5000) {
  const keys = Object.keys(read);
  if (keys.length <= max) return read;
  return Object.fromEntries(Object.entries(read).sort((a, b) => b[1] - a[1]).slice(0, max));
}

/**
 * The record on disk with this window's changes laid over it: another window
 * may have marked other hunks since it was read. `keys` are the keys this
 * window changed; each is taken from `mine`, as read or as gone.
 */
export function mergeRead(disk, mine, keys, max = 5000) {
  const next = { ...(disk && typeof disk === "object" ? disk : {}) };
  for (const k of keys) {
    if (Object.hasOwn(mine, k)) next[k] = mine[k];
    else delete next[k];
  }
  return prune(next, max);
}

/**
 * The steps read before whose code has changed since. A step counts when it
 * isn't read now and either part of it was read (outdated, or one hunk of
 * several edited), or it holds a file in which a hunk read in the walkthrough
 * this one revised (`before`, its hunk ids) is no longer in the diff: a step
 * of one hunk, edited and regenerated, has a new digest and nothing else to
 * tell it by.
 *
 * @param {{ hunkIds: string[], outdated?: boolean }[]} steps
 * @param {Record<string, number>} read
 * @param {{ before?: string[], current?: Iterable<string> }} opts `current`: the hunk ids in the diff now
 */
export function changedSince(steps, read, { before = [], current = [] } = {}) {
  const now = new Set([...current].map(readKey));
  const gone = new Set(before.map(readKey).filter((k) => Object.hasOwn(read, k) && !now.has(k)).map(pathOf));
  return steps.filter((s) => !isRead(s, read)
    && s.hunkIds.some((id) => hunkRead(id, read) || gone.has(pathOf(readKey(id)))));
}

/** A step as the reader sees it: read only when all its hunks are, and none of them has changed since. */
export const isRead = (step, read) => !step.outdated && stepRead(step, read);
