// Shared checked-state for todos, keyed by stable todo id.
// ponytail: localStorage-on-file:// is one shared bucket; fine for one user
const KEY = 'brief-portfolio-done'

export const loadDone = () => new Set(JSON.parse(localStorage.getItem(KEY) ?? '[]'))
export const saveDone = (s) => localStorage.setItem(KEY, JSON.stringify([...s]))

// Drop ids that no longer exist in the payload so the set can't grow forever.
export function pruneDone(validIds) {
  const done = loadDone()
  const kept = new Set([...done].filter((id) => validIds.has(id)))
  if (kept.size !== done.size) saveDone(kept)
  return kept
}
