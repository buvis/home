const PAGE = 50;

export function queueTargets(spaces, panes, machines) {
  const ready = new Set(machines.filter((m) => m.layout === "ready").map((m) => m.name));
  const targets = new Map();
  for (const space of [...spaces].sort((a, b) => Number(b.active) - Number(a.active))) {
    if (!ready.has(space.machine)) continue;
    const tabs = new Set(space.tabs.map((tab) => tab.id));
    for (const pane of panes) {
      if (!pane.terminal || !pane.cwd || !tabs.has(pane.tab)) continue;
      const key = JSON.stringify([space.machine, pane.cwd]);
      if (!targets.has(key)) targets.set(key, { cwd: pane.cwd, on: space.machine, space: space.id });
    }
  }
  return [...targets.values()];
}

// Normalize SSH and HTTPS remotes without putting credentials into the queue.
export function repositoryOf(remote) {
  const address = /^(?:https?|ssh|git):\/\/(?:[^/@\s]+@)?([\w.-]+(?::\d+)?)\/([^?#\s]+)$/i.exec(remote)
    ?? /^(?:[^/@\s]+@)?([\w.-]+):([^/\s][^\s]*)$/.exec(remote);
  if (!address) return null;
  const host = address[1].toLowerCase();
  const name = address[2].replace(/\/+$/g, "").replace(/\.git$/, "");
  return name.includes("/") ? { host, name } : null;
}

async function batches(items, work) {
  const results = [];
  for (let i = 0; i < items.length; i += 4) results.push(...await Promise.all(items.slice(i, i + 4).map(work)));
  return results;
}

export async function readQueue(targets, filter, { exec, ghx, fields, checkState, isCurrent }) {
  const candidates = await batches(targets, async (target) => {
    if (!isCurrent()) return null;
    try {
      const result = await exec("git", ["remote", "get-url", "origin"], { cwd: target.cwd, on: target.on });
      const repository = result.code === 0 ? repositoryOf(result.stdout.trim()) : null;
      return repository ? { ...target, ...repository } : null;
    } catch { return null; }
  });
  if (!isCurrent()) return null;

  const repos = new Map();
  for (const repo of candidates.filter(Boolean)) {
    const key = JSON.stringify([repo.on, repo.host, repo.name]);
    if (!repos.has(key)) repos.set(key, { ...repo, key });
  }
  const projects = [...repos.values()];
  const gitLabSkipped = projects.filter(({ host }) => /(?:^|\.)gitlab(?:\.|:|$)/i.test(host)).length;
  const supported = projects.filter(({ host }) => !/(?:^|\.)gitlab(?:\.|:|$)/i.test(host));
  const results = await batches(supported, async (repo) => {
    if (!isCurrent()) return null;
    const search = filter === "review" ? "review-requested:@me sort:updated-desc" : "sort:updated-desc";
    try {
      const command = repo.on ? (repo.host === "bitbucket.org" ? "ghx" : "gh") : ghx;
      const repoArg = repo.host === "bitbucket.org" ? [] : ["--repo", `${repo.host}/${repo.name}`];
      const result = await exec(command, ["pr", "list", ...repoArg, "--state", "open", "--limit", String(PAGE), "--search", search, "--json", fields], { cwd: repo.cwd, on: repo.on });
      if (result.code !== 0) return { repo, error: true, prs: [] };
      const prs = JSON.parse(result.stdout);
      if (!Array.isArray(prs)) return { repo, error: true, prs: [] };
      return { repo, prs, command, limited: prs.length >= PAGE };
    } catch { return { repo, error: true, prs: [] }; }
  });
  if (!isCurrent()) return null;
  const checks = filter === "failed" ? await batches(results.filter(({ repo }) => repo.host === "bitbucket.org")
    .flatMap((result) => result.prs.map((pr) => ({ ...result, pr }))), async ({ repo, pr, command }) => {
    if (!isCurrent()) return null;
    const key = `${repo.key}:${pr.number}`;
    if (!/^[a-f\d]{7,64}$/i.test(pr.headRefOid ?? "")) return [key, null];
    try {
      const result = await exec(command, ["pr", "checks", "--commit", pr.headRefOid, "--json", "bucket"], { cwd: repo.cwd, on: repo.on });
      if (result.code !== 0) return [key, null];
      return [key, JSON.parse(result.stdout).some(({ bucket }) => bucket === "fail")];
    } catch { return [key, null]; }
  }) : [];
  if (!isCurrent()) return null;
  const byPr = new Map(checks);
  const errors = new Set();
  const rows = [];
  for (const { repo, prs, error } of results) {
    const label = [repo.name, repo.on].filter(Boolean).join(" · ");
    if (error) errors.add(label);
    for (const pr of prs) {
      const key = `${repo.key}:${pr.number}`;
      if (byPr.has(key) && byPr.get(key) === null) errors.add(label);
      if (filter !== "failed" || (byPr.has(key) ? byPr.get(key) : checkState(pr.statusCheckRollup) === "fail")) rows.push({ ...pr, repo, key });
    }
  }
  return {
    rows: rows.sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt))),
    errors: [...errors],
    gitLabSkipped,
    limited: results.some((r) => r.limited),
  };
}
