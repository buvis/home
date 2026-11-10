// The Issues panel's logic, apart from its drawing: which forge the repo is on,
// how to list its issues (GitHub and Bitbucket through ghx, GitLab through glab),
// and the work an issue starts: a branch in its own worktree, then an agent in it.
//
// data.js is a copy of ship-it-prs's: keep them the same.

import { exec, run, spaces, panes, appHome, knownAgents } from "herdr";
import { READ } from "./data.js";

const GH = () => `${appHome()}/bin/ghx`; // gh, with Bitbucket Cloud support

// ---- forge

// "github", "gitlab" or "bitbucket", from origin; unknown hosts are tried as GitHub (gh knows enterprise hosts).
export async function forgeOf(root, on) {
  const r = await exec("git", [...READ, "remote", "get-url", "origin"], { cwd: root, on });
  if (r.code !== 0) return null;
  const url = r.stdout.trim();
  return /bitbucket\.org/.test(url) ? "bitbucket" : /gitlab/.test(url) ? "gitlab" : "github";
}
export const FORGE_NAME = { github: "GitHub", gitlab: "GitLab", bitbucket: "Bitbucket" };

const FIELDS = "number,title,author,labels,assignees,url,updatedAt,body";

// -> { issues: [{number,title,author,labels:[name],assignees:[login],url,updatedAt,body}], error? }
// Mine = assigned to me.
export async function listIssues(forge, root, on, mine, limit) {
  const fail = (r, tool) => {
    const err = (r.stderr || "").trim(), low = err.toLowerCase();
    return { issues: [], error: low.includes("auth") || low.includes("login") || low.includes("token") ? `${tool} is not logged in`
      : low.includes("disabled") || low.includes("has disabled issues") ? "Issues are disabled for this repository"
      : low.includes("no git remote") || low.includes("no default remote") || low.includes("none of the git remotes") ? "No supported remote"
      : err.split("\n")[0] || `${tool} failed` };
  };
  if (forge === "gitlab") {
    let r;
    try { r = await exec("glab", ["issue", "list", "-F", "json", "--per-page", String(limit), ...(mine ? ["--assignee=@me"] : [])], { cwd: root, on }); }
    catch { return { issues: [], error: "glab is not installed" }; }
    if (r.code !== 0) return fail(r, "glab");
    let rows; try { rows = JSON.parse(r.stdout || "[]") ?? []; } catch { return { issues: [], error: "glab gave no JSON" }; }
    return { issues: rows.filter((i) => i.state !== "closed").map((i) => ({
      number: i.iid, title: i.title, url: i.web_url, updatedAt: i.updated_at, body: i.description ?? "",
      author: i.author?.username ?? i.author?.name ?? "",
      labels: (i.labels ?? []).map((l) => l?.name ?? l), assignees: (i.assignees ?? []).map((a) => a.username),
    })) };
  }
  let r;
  try {
    r = await exec(GH(), ["issue", "list", "--state", "open", "--limit", String(limit), ...(mine ? ["--assignee", "@me"] : []), "--json", FIELDS], { cwd: root, on });
  } catch { return { issues: [], error: "gh is not installed" }; }
  if (r.code !== 0) return fail(r, forge === "bitbucket" ? "Bitbucket" : "gh");
  let rows; try { rows = JSON.parse(r.stdout || "[]"); } catch { return { issues: [], error: "gh gave no JSON" }; }
  return { issues: rows.map((i) => ({
    number: i.number, title: i.title, url: i.url, updatedAt: i.updatedAt, body: i.body ?? "",
    author: i.author?.login ?? "", labels: (i.labels ?? []).map((l) => l.name), assignees: (i.assignees ?? []).map((a) => a.login),
  })) };
}

// ---- worktrees

export const slug = (s) => s.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
// <number>-<words of the title>: git-safe, short.
export const branchFor = (issue) => {
  const words = issue.title.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40).replace(/-+$/, "");
  return words ? `${issue.number}-${words}` : String(issue.number);
};

// The repo's checkouts by branch: { branch: path }.
export async function worktrees(root, on) {
  const r = await exec("git", [...READ, "worktree", "list", "--porcelain"], { cwd: root, on });
  const out = {};
  for (const block of (r.code === 0 ? r.stdout : "").split("\n\n")) {
    const path = /^worktree (.+)$/m.exec(block)?.[1], branch = /^branch refs\/heads\/(.+)$/m.exec(block)?.[1];
    if (path && branch) out[branch] = path;
  }
  return out;
}

// The checkout that is already on an issue: a branch named <number>-… (whatever the title said then).
export const issueTree = (trees, issue) => Object.entries(trees).find(([b]) => b === String(issue.number) || b.startsWith(`${issue.number}-`))?.[1] ?? null;

export function places(on) {
  const ps = panes();
  return spaces().filter((s) => (s.machine ?? null) === (on ?? null)).map((s) => {
    const tabs = new Set((s.tabs ?? []).map((t) => t.id));
    return { s, at: ps.find((p) => tabs.has(p.tab) && p.cwd)?.cwd || s.folder || null };
  });
}
export function spaceAt(path, where, paths = []) {
  if (!path) return undefined;
  const inside = (p, dir) => p === dir || p?.startsWith(dir + "/");
  return where.find(({ at }) => inside(at, path) && !paths.some((c) => c.length > path.length && inside(at, c)))?.s;
}

// Make sure the issue has a worktree, and return { path, branch, created }. Reuses one that is there
// (or a local branch of the issue, checked out again); else a new branch from origin's default branch.
// Throws unless the checkout really is a working tree when it returns.
export async function ensureWorktree(root, on, issue) {
  const git = async (args, what) => {
    const r = await exec("git", args, { cwd: root, on });
    if (r.code !== 0) throw new Error((r.stderr || `${what} failed`).trim().split("\n").pop());
    return r.stdout.trim();
  };
  const ok = async (args) => (await exec("git", [...READ, ...args], { cwd: root, on })).code === 0;
  const trees = await worktrees(root, on), have = issueTree(trees, issue);
  let path = have, branch = have ? Object.keys(trees).find((b) => trees[b] === have) : null, created = false;
  if (!path) {
    const common = await git(["rev-parse", "--path-format=absolute", "--git-common-dir"], "git rev-parse");
    const main = common.endsWith("/.git") ? common.slice(0, -5) : common;
    const home = (await exec("sh", ["-c", 'printf %s "$HOME"'], { on })).stdout.trim();
    if (!home) throw new Error("Couldn't find the home folder");
    // A local branch of this issue, else origin's, else a new one.
    const refs = (await exec("git", [...READ, "for-each-ref", "--format=%(refname:short)", `refs/heads/${issue.number}-*`, `refs/heads/${issue.number}`], { cwd: root, on })).stdout.trim().split("\n").filter(Boolean);
    branch = refs[0] ?? branchFor(issue);
    path = `${home}/.herdr/worktrees/${main.split("/").pop()}/${slug(branch)}`;
    if (refs[0]) await git(["worktree", "add", path, branch], "git worktree add");
    else {
      const head = (await exec("git", [...READ, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], { cwd: root, on })).stdout.trim();
      const base = head ? head.replace(/^origin\//, "") : (await ok(["show-ref", "--verify", "--quiet", "refs/remotes/origin/main"])) ? "main" : "master";
      const fetched = (await exec("git", ["fetch", "origin", base], { cwd: root, on })).code === 0;
      const from = (await ok(["show-ref", "--verify", "--quiet", `refs/remotes/origin/${base}`])) ? `origin/${base}` : base;
      if (!fetched && from === base && !(await ok(["show-ref", "--verify", "--quiet", `refs/heads/${base}`]))) throw new Error(`Couldn't find ${base} to branch from`);
      await git(["worktree", "add", "--no-track", "-b", branch, path, from], "git worktree add");
    }
    created = true;
  }
  const inside = await exec("git", [...READ, "rev-parse", "--is-inside-work-tree"], { cwd: path, on });
  if (inside.code !== 0 || inside.stdout.trim() !== "true") throw new Error(`The worktree ${path} isn't there`);
  return { path, branch, created, trees: { ...trees, [branch]: path } };
}

// ---- agents

// The installed agents on a machine, the preferred one (Claude Code) first.
export async function installedAgents(on) {
  const all = (await knownAgents({ on })).filter((a) => a.installed && a.run?.length);
  return all.sort((a, b) => (b.key === "claude") - (a.key === "claude"));
}

export function taskFor(issue, branch) {
  const body = (issue.body || "").trim().slice(0, 6000);
  return `Work on issue #${issue.number}: ${issue.title}\n${issue.url}\n\n${body || "(no description)"}\n\n` +
    `You are in a dedicated git worktree on branch ${branch}. Implement the issue here and commit your work to this branch; leave other worktrees alone.`;
}

// Go to the worktree's space, or make one, and start the agent in it.
// `agent` null: only open the space.
export function openWorktree(path, on, trees, issue, branch, agent) {
  const s = spaceAt(path, places(on), Object.values(trees));
  const task = agent ? { argv: agent.run, task: taskFor(issue, branch) } : {};
  const tab = agent ? `#${issue.number} ${agent.name}` : undefined;
  if (s) {
    run("space.select", { id: s.id });
    if (agent) run("tab.new", { space: s.id, folder: path, name: tab, ...task });
  } else run("space.new", { folder: path, ...(tab ? { tab } : {}), ...(on ? { machine: on } : {}), ...task });
}
