// Which spaces are linked git worktrees, and of which main checkout.
//
// Each probe is one space's `git rev-parse --path-format=absolute
// --show-toplevel --git-common-dir` answer: { id, name, branch, toplevel,
// common }. A checkout whose common dir is not its own `.git` is a linked
// worktree; its main checkout is the space whose toplevel owns that `.git`.

function trim(path) {
  return path.replace(/\/+$/u, "");
}

function dirname(path) {
  const p = trim(path);
  return p.slice(0, p.lastIndexOf("/")) || "/";
}

function basename(path) {
  const p = trim(path);
  return p.slice(p.lastIndexOf("/") + 1);
}

/** Two lines of rev-parse output as { toplevel, common }, or null. */
export function parseRevParse(stdout) {
  const [toplevel, common] = (stdout ?? "").split("\n").map((l) => l.trim());
  if (!toplevel || !common) return null;
  return { toplevel: trim(toplevel), common: trim(common) };
}

/** Map space id → { linked, main, repo, branch } for every probed space. */
export function resolveWorktrees(probes) {
  const isLinked = (p) => p.common !== `${p.toplevel}/.git`;
  const out = new Map();
  for (const p of probes) {
    if (!isLinked(p)) {
      out.set(p.id, { linked: false, main: null, repo: p.name, branch: p.branch ?? null });
      continue;
    }
    const mainRoot = basename(p.common) === ".git" ? dirname(p.common) : null;
    const main = probes.find((q) => q !== p && !isLinked(q) && q.toplevel === mainRoot);
    out.set(p.id, {
      linked: true,
      main: main?.id ?? null,
      repo: main?.name ?? basename(mainRoot ?? p.common.replace(/\.git$/u, "")),
      branch: p.branch ?? null,
    });
  }
  return out;
}
