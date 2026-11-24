// What the model reads: every reviewable hunk, in full, under a short alias.
//
// Nothing is clipped. A diff too big for the model is refused before it is
// sent, because a walkthrough of half a diff reads as confidently as one of
// the whole and nobody can tell them apart.
//
// Aliases (h1, h2, …) instead of real ids: they cost a few tokens, and a model
// cannot invent a believable alias for a hunk that does not exist.

import { parseDiff } from "./hunks.js";
import { isGenerated } from "./generated.js";

/**
 * @param {{ scope: string, patch: string }[]} sections
 * @returns {{ files: any[], text: string, idByAlias: Record<string, string>,
 *   digestFiles: { path: string, aliases: string[] }[], hunkCount: number, fileCount: number,
 *   generatedPaths: string[] }}
 */
export function buildDigest(sections) {
  const files = [];
  for (const section of sections) {
    for (const file of parseDiff(section.patch, section.scope)) files.push({ ...file, generated: isGenerated(file.path) });
  }

  const idByAlias = {};
  const digestFiles = [];
  const blocks = [];
  let n = 0;
  for (const file of files) {
    if (file.generated) continue;
    const aliases = [];
    const head = [`=== ${file.path}`, file.status !== "modified" ? `(${file.status}${file.oldPath ? ` from ${file.oldPath}` : ""})` : "",
      // Two scopes can hold the same file; say which one a block is.
      file.scope === "staged" || file.scope === "working" ? `[${file.scope}]` : "", file.binary ? "(binary)" : ""].filter(Boolean).join(" ");
    const body = [head];
    for (const hunk of file.hunks) {
      const alias = `h${++n}`;
      idByAlias[alias] = hunk.id;
      aliases.push(alias);
      body.push(`[${alias}] ${hunk.header}`, ...hunk.lines);
    }
    blocks.push(body.join("\n"));
    digestFiles.push({ path: file.path, aliases, status: file.status });
  }

  return {
    files,
    text: blocks.join("\n\n"),
    idByAlias,
    digestFiles,
    hunkCount: n,
    fileCount: digestFiles.length,
    generatedPaths: files.filter((f) => f.generated).map((f) => f.path),
  };
}
