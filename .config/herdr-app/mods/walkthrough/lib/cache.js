// Names for what is kept on disk. An entry is named by what decides its
// content (the code, the model, the language, the prompt and the reader's
// preferences), so a hit is by definition about exactly this code and needs no
// freshness check. Putting the working tree back the way it was brings the
// earlier walkthrough back free. An earlier walkthrough handed on for revision
// is not part of it: it only exists for code that has since changed.

import { longHash, hash } from "./hash.js";
import { VERSION, PROMPT_VERSION } from "./walkthrough.js";

/**
 * The code alone: what the model reads, in order. Only what is sent counts: a
 * lockfile or an unread file changing doesn't change the walkthrough. Stored
 * with each entry, so a miss on the same code can say it was the preferences
 * or a newer prompt that changed, not the code.
 */
export const codeKey = (files) => longHash(JSON.stringify(
  files.filter((f) => !f.generated && !f.unread).map((f) => [f.path, f.status, f.hunks.map((h) => h.id)])));

/** `task`: lib/task.js taskKey, "" for none, so a walkthrough without a task keeps the key it always had. */
export function cacheKey({ top, source, model, language, preferences = "", files, task = "" }) {
  return longHash(JSON.stringify([VERSION, PROMPT_VERSION, top, source, model, language, hash(String(preferences).trim()), codeKey(files), ...(task ? [task] : [])]));
}

/** One pointer (the walkthrough shown last) and one running job per repository and source. */
export const placeKey = (top, source) => longHash(`${top}\n${source}`);

/**
 * A generation's time limit: it guards against a hang and grows with the diff.
 * The base covers the recap, blueprint and contracts written before any step,
 * which a small diff needs as much as a large one.
 */
export const deadline = (hunkCount) => Math.min(15 * 60, 240 + 2 * hunkCount) * 1000;

/** Rough tokens for text: enough to say "≈ 12k tokens" and to refuse a diff that can't fit. */
export const estimateTokens = (chars) => Math.ceil(chars / 3.6);

/** A prompt above this is refused rather than clipped: about 200k tokens, which every Claude model takes. */
export const MAX_PROMPT_CHARS = 640_000;

export const shortKey = (text) => hash(text).slice(-6);
