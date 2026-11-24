// The hunk aliases a model writes ("h3", " h3 ", "[h3]"), read the same way
// wherever an answer cites a hunk: steps, asks, the blueprint and contracts.

/** The alias as the digest spells it, or "" for anything that isn't a string. */
export const aliasKey = (alias) => (typeof alias === "string" ? alias.trim().replace(/^\[|\]$/g, "").trim() : "");

/** The hunk id an alias stands for, or undefined. Only the digest's own keys count, never "toString". */
export function idOf(idByAlias, alias) {
  const key = aliasKey(alias);
  return key && Object.hasOwn(idByAlias, key) ? idByAlias[key] || undefined : undefined;
}

/** Digest files by alias: which file a cited hunk is in. */
export const filesByAlias = (files) => new Map(files.flatMap((f) => (f.aliases ?? []).map((a) => [a, f])));

/**
 * The hunks a model cited for one claim, resolved: each { id, file }, deduplicated.
 * `keep` filters by file (e.g. no deleted files); an alias that doesn't resolve is skipped.
 */
export function resolveHunks(aliases, idByAlias, fileByAlias, keep = () => true) {
  const out = [], seen = new Set();
  for (const alias of Array.isArray(aliases) ? aliases : []) {
    const id = idOf(idByAlias, alias), file = fileByAlias.get(aliasKey(alias));
    if (!id || !file || seen.has(id) || !keep(file)) continue;
    seen.add(id);
    out.push({ id, file });
  }
  return out;
}

/** Short plain text for a label or title: the characters a renderer could misread are dropped, never failed on. */
export function plainLabel(value, max) {
  if (typeof value !== "string") return "";
  const t = value.replace(/[<>`"|\\\x00-\x1f]/g, " ").replace(/\s+/g, " ").trim();
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t;
}
