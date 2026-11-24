// A small, deterministic string hash. Hunk ids and cache keys only need to
// agree with themselves (one implementation decides them), not with any other
// tool, so a fast non-cryptographic hash is enough and needs no host crypto.

/** 53 bits of hash as 14 hex digits; `seed` gives an independent hash. */
export function hash(text, seed = 0) {
  let h1 = 0xdeadbeef ^ seed, h2 = 0x41c6ce57 ^ seed;
  const s = String(text);
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 2654435761);
    h2 = Math.imul(h2 ^ c, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16).padStart(14, "0");
}

/** Eight hex digits: a hunk's identity inside one file. */
export const shortHash = (text) => hash(text).slice(-8);

/** Two independent hashes side by side, for keys that name files on disk. */
export const longHash = (text) => hash(text, 1) + hash(text, 2);
