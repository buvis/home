// The Issues panel's logic, apart from its drawing: which forge the repo is on,
// how to list its issues (GitHub and Bitbucket through ghx, GitLab through glab),
// and the work an issue starts: a branch in its own worktree, then an agent in it.
//
// data.js is a copy of ship-it-prs's: keep them the same.

import { exec, run, spaces, panes, appHome, knownAgents, readTextFile } from "herdr";
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

const slug = (s) => s.replace(/[^\p{L}\p{M}\p{N}._-]+/gu, "-").replace(/^-+|-+$/g, "");

export const branchFor = (issue) => {
  const bug = issue.labels.some((label) => /\b(bug|defect|regression)\b/i.test(label))
    || /\b(bug|crash(?:es|ed|ing)?|regression|broken|fails?|failure)\b/i.test(issue.title);
  const words = issue.title.toLowerCase().normalize("NFKD").replace(/\p{M}/gu, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  // Keep the flattened checkout folder within Git's file name limits.
  const title = words.length <= 200 ? words : words.slice(0, 201).replace(/-[^-]*$/, "").slice(0, 200);
  return `${bug ? "bugfix" : "feature"}/${issue.number}${title ? `-${title}` : ""}`;
};

// The repo's checkouts and explicit issue links, including edited branch names.
export async function checkoutState(root, on) {
  const [list, config] = await Promise.all([
    exec("git", [...READ, "worktree", "list", "--porcelain", "-z"], { cwd: root, on }),
    exec("git", [...READ, "config", "--local", "--null", "--get-regexp", "^branch\\..*\\.herdr-issue$"], { cwd: root, on }),
  ]);
  if (list.code !== 0) throw new Error(list.stderr.trim() || "Couldn't list worktrees");
  if (config.code !== 0 && config.code !== 1) throw new Error(config.stderr.trim() || "Couldn't read issue branch links");
  const trees = Object.create(null), links = Object.create(null);
  for (const block of list.stdout.split("\0\0")) {
    const fields = block.split("\0");
    const path = fields.find((field) => field.startsWith("worktree "))?.slice(9);
    const branch = fields.find((field) => field.startsWith("branch refs/heads/"))?.slice(18);
    if (path && branch) trees[branch] = path;
  }
  for (const item of config.stdout.split("\0")) {
    const match = /^branch\.(.+)\.herdr-issue\n(\d+)$/.exec(item);
    if (match) links[match[1]] = match[2];
  }
  return { trees, links };
}

function issueBranch(branches, issue, links) {
  const number = String(issue.number);
  return branches.find((branch) => links[branch] === number)
    ?? branches.find((branch) => !links[branch] && (branch === number || branch.startsWith(`${number}-`)));
}

export function issueTree(trees, issue, links) {
  const branch = issueBranch(Object.keys(trees), issue, links);
  return branch === undefined ? null : trees[branch];
}

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

async function worktreeDirectory(on) {
  const raw = await readTextFile(`${appHome()}/settings.json`);
  const directory = (raw === null ? {} : JSON.parse(raw))?.worktrees?.directory ?? "~/.herdr/worktrees";
  if (typeof directory !== "string" || !directory.trim()) throw new Error("worktrees.directory must be a non-empty path");
  let path = directory.replace(/\\/g, "/");
  if (path === "~" || path.startsWith("~/")) {
    const result = await exec("sh", ["-c", 'printf %s "$HOME"'], { on });
    const home = result.stdout.trim();
    if (result.code !== 0 || !home) throw new Error("Couldn't find the home folder");
    path = home.replace(/\/$/, "") + path.slice(1);
  }
  if (!path.startsWith("/") && !/^[A-Za-z]:\//.test(path)) throw new Error("worktrees.directory must be absolute or start with ~/");
  return path.replace(/\/+$/, "");
}

// Reuse an open checkout. When one needs to be created, ask which branch to use.
export async function ensureWorktree(root, on, issue, name) {
  const git = async (args, what) => {
    const r = await exec("git", args, { cwd: root, on });
    if (r.code !== 0) throw new Error((r.stderr || `${what} failed`).trim().split("\n").pop());
    return r.stdout.trim();
  };
  const ok = async (args) => (await exec("git", [...READ, ...args], { cwd: root, on })).code === 0;
  const { trees, links } = await checkoutState(root, on);
  let branch = issueBranch(Object.keys(trees), issue, links);
  let path = branch ? trees[branch] : null, created = false;
  if (path && name !== undefined && name !== branch) throw new Error(`This issue already has a worktree on ${branch}`);
  if (!path) {
    const refs = (await git([...READ, "for-each-ref", "--format=%(refname:lstrip=2)", "refs/heads"], "git for-each-ref")).split("\n").filter(Boolean);
    const existing = issueBranch(refs, issue, links) ?? null;
    if (name === undefined) return { existing };
    branch = name;
    const reuse = branch === existing;
    if (!reuse) {
      const check = await exec("git", [...READ, "check-ref-format", "--branch", branch], { cwd: root, on });
      if (check.code !== 0 || check.stdout.trim() !== branch) throw new Error("Enter a valid Git branch name");
      if (refs.includes(branch)) throw new Error(`Branch ${branch} already exists`);
    }
    const common = await git(["rev-parse", "--path-format=absolute", "--git-common-dir"], "git rev-parse");
    const main = common.endsWith("/.git") ? common.slice(0, -5) : common;
    const directory = await worktreeDirectory(on);
    // Git permits names made entirely of symbols. Use the issue number as their folder name.
    const folder = slug(branch);
    path = `${directory}/${main.split("/").pop()}/${folder && folder !== "." && folder !== ".." ? folder : issue.number}`;
    if (reuse) await git(["worktree", "add", "--", path, branch], "git worktree add");
    else {
      const head = (await exec("git", [...READ, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], { cwd: root, on })).stdout.trim();
      const base = head ? head.replace(/^origin\//, "") : (await ok(["show-ref", "--verify", "--quiet", "refs/remotes/origin/master"])) ? "master"
        : (await ok(["show-ref", "--verify", "--quiet", "refs/remotes/origin/main"])) ? "main" : "master";
      const fetched = (await exec("git", ["fetch", "origin", base], { cwd: root, on })).code === 0;
      const from = (await ok(["show-ref", "--verify", "--quiet", `refs/remotes/origin/${base}`])) ? `origin/${base}` : base;
      if (!fetched && from === base && !(await ok(["show-ref", "--verify", "--quiet", `refs/heads/${base}`]))) throw new Error(`Couldn't find ${base} to branch from`);
      await git(["worktree", "add", "--no-track", "-b", branch, "--", path, from], "git worktree add");
      try {
        await git(["config", "--local", `branch.${branch}.herdr-issue`, String(issue.number)], "git config");
      } catch (error) {
        throw new Error(`Created ${path}, but couldn't link it to issue #${issue.number}: ${error.message}`);
      }
      links[branch] = String(issue.number);
    }
    created = true;
  }
  const inside = await exec("git", [...READ, "rev-parse", "--is-inside-work-tree"], { cwd: path, on });
  if (inside.code !== 0 || inside.stdout.trim() !== "true") throw new Error(`The worktree ${path} isn't there`);
  return { path, branch, created, trees: { ...trees, [branch]: path }, links };
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
  const task = {};
  if (agent) {
    const argv = [...agent.run];
    if (!/(^|[/\\])run-agent$/.test(argv[0])) argv.unshift("run-agent");
    // The shim is argv[0], so supply Codex's terminal-local mode explicitly.
    if (agent.key === "codex" && !argv.includes("--no-daemon")) {
      argv.splice(argv[1] === "--no-sandbox" ? 3 : 2, 0, "--no-daemon");
    }
    // Copilot takes its first prompt after -i.
    if (agent.key === "copilot" && !argv.includes("-i")) argv.push("-i");
    Object.assign(task, { argv, task: taskFor(issue, branch) });
  }
  const tab = agent ? `#${issue.number} ${agent.name}` : undefined;
  if (s) {
    run("space.select", { id: s.id });
    if (agent) run("tab.new", { space: s.id, folder: path, name: tab, ...task });
  } else run("space.new", { folder: path, ...(tab ? { tab } : {}), ...(on ? { machine: on } : {}), ...task });
}
