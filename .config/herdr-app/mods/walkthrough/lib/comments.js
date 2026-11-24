// Comments made on diff lines, gathered into one message for an agent. The
// line's code goes with each one, so the agent can find it even after the
// numbers have moved.

/**
 * @param {{ scope?: string, path: string, line: number, kind: string, code: string, text: string }[]} comments
 * @param {string} what the source they were made on
 * @param {{ mixed?: boolean }} options mixed: the diff holds staged and unstaged copies of files, so say which
 */
export function formatComments(comments, what, { mixed = false } = {}) {
  const items = comments.map((c) => {
    const notes = [c.kind === "-" ? "removed line" : "", mixed && c.scope === "staged" ? "staged version" : mixed && c.scope === "working" ? "unstaged version" : ""].filter(Boolean);
    const where = `${c.path}:${c.line}${notes.length ? ` (${notes.join(", ")})` : ""}`;
    const code = c.code.trim() ? ` \`${c.code.trim().slice(0, 160)}\`` : "";
    return `- ${where}${code}: ${c.text.trim()}`;
  });
  return `Comments from reading the walkthrough of ${what}\n${items.join("\n")}`;
}

/** One line of one diff: its source, its scope (staged or unstaged copy), path, number and side. */
export const sameSpot = (a, b) => a.sk === b.sk && a.scope === b.scope && a.path === b.path && a.line === b.line && a.kind === b.kind;

/** The same line is commented once; a new comment replaces the old one. */
export function addComment(comments, comment) {
  return [...comments.filter((c) => !sameSpot(c, comment)), comment];
}
