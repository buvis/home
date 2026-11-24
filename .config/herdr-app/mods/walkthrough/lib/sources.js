// What a walkthrough is of, and the git that reads it. Every function takes
// the mod's `exec`, so the same code runs in Herdr and under `node --test`.
//
// A source becomes one or more sections: a patch and the scope its hunk ids
// live in. Staged and unstaged edits of the same lines are different hunks, so
// a step written about the staged version is never quietly matched to an
// unstaged one.

import { firstLine } from "./turns.js";

// Reads write nothing under .git: no index refresh, no lock, no fsmonitor.
const READ = ["--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.quotePath=false", "-c", "diff.autoRefreshIndex=false"];
// The user's diff settings (no prefixes, external tools, color) must not change what is parsed.
const DIFF = ["--no-color", "--no-ext-diff", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/", "-M"];
const EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904";
// Untracked files are read one by one; past these, the rest are listed unread.
const MAX_UNTRACKED = 300;
export const MAX_UNTRACKED_BYTES = 1024 * 1024;

export const SCOPES = [
  { key: "uncommitted", label: "Uncommitted", about: "Everything not committed yet: staged, unstaged and new files" },
  { key: "staged", label: "Staged", about: "What the next commit would hold" },
  { key: "unstaged", label: "Unstaged", about: "The working tree and new files, not staged" },
  { key: "branch", label: "Branch", about: "Everything this branch adds to its base, committed or not" },
  { key: "commit", label: "Commit", about: "One commit, against its first parent" },
  { key: "pr", label: "Pull request", about: "An open pull request on GitHub, as GitHub shows its changes (needs gh)" },
  { key: "turn", label: "Last turn", about: "What an agent changed while answering one prompt (needs the turn hooks, or recording on for agents without them)" },
];

export async function git(exec, cwd, args) {
  const r = await exec("git", [...READ, ...args], { cwd });
  return { ok: r.code === 0, code: r.code, out: r.stdout ?? "", err: (r.stderr || "").trim() };
}

async function must(exec, cwd, args) {
  const r = await git(exec, cwd, args);
  if (!r.ok) throw new Error(r.err || `git ${args[0]} failed`);
  return r.out;
}

/** The repository a folder is in: { top, name, branch }, or null outside git. */
export async function repoAt(exec, folder) {
  const top = await git(exec, folder, ["rev-parse", "--show-toplevel"]);
  if (!top.ok) return null;
  const root = top.out.trim();
  const head = await git(exec, root, ["rev-parse", "--verify", "-q", "HEAD"]);
  const branch = (await git(exec, root, ["branch", "--show-current"])).out.trim();
  // A linked worktree keeps its index and HEAD outside its folder, under the main repository's .git.
  const gitDir = (await git(exec, root, ["rev-parse", "--absolute-git-dir"])).out.trim();
  return { top: root, name: root.split("/").pop(), branch: branch || null, born: head.ok, gitDir: gitDir || `${root}/.git` };
}

/** What HEAD is now: the branch, or "HEAD@<short hash>" when detached, so each one is a source of its own. */
export async function currentHead(exec, top) {
  const branch = (await git(exec, top, ["branch", "--show-current"])).out.trim();
  if (branch) return branch;
  const short = (await git(exec, top, ["rev-parse", "--short", "HEAD"])).out.trim();
  return short ? `HEAD@${short}` : "HEAD";
}

/** A source's stable name: part of its cache key and the name of its pointer. */
export function sourceKey(source) {
  // The branch being read is part of it: two branches against one base are two walkthroughs.
  if (source.kind === "branch") return `branch:${source.base}...${source.head ?? "HEAD"}`;
  if (source.kind === "commit") return `commit:${source.hash}`;
  // Not pinned to the head commit: when the pull request moves on, its last walkthrough is shown as outdated.
  if (source.kind === "pr") return `pr:${source.number}`;
  if (source.kind === "turn") return `turn:${source.id}`;
  return source.kind;
}

/** One line for the model and the header: what is being walked through. */
export function describe(source, repo) {
  switch (source.kind) {
    case "uncommitted": return "Uncommitted local changes, staged and unstaged, with new files.";
    case "staged": return "Staged changes: what the next commit would hold.";
    case "unstaged": return "Unstaged changes in the working tree, with new files.";
    case "branch": return `Everything branch "${source.head ?? repo?.branch ?? "HEAD"}" adds to "${source.base}", committed or not. Work that came in from ${source.base} is left out.`;
    case "commit": return `Commit ${source.hash.slice(0, 12)}${source.subject ? ` ("${source.subject}")` : ""}, against its first parent.`;
    case "turn": return `One turn of a coding agent: what changed in the working tree while it answered the prompt "${firstLine(source.prompt, 160)}"${source.endTree ? "" : " (still running: read up to now)"}.`;
    case "pr": return `Pull request #${source.number}${source.title ? ` ("${source.title}")` : ""}${source.head && source.base ? `, "${source.head}" into "${source.base}"` : ""}, as GitHub shows its changes.`;
    default: return "Local changes.";
  }
}

/**
 * New files git doesn't track yet, as patches. `git diff` never shows them,
 * and a walkthrough of local work without its new files would miss most of it.
 * @returns {Promise<{ patches: string[], unread: { path: string, why: string }[] }>}
 */
// Untracked patches by repository and path, with the size and modification time
// they were read at. A save re-reads the diff, and re-diffing every new file
// each time (up to 300 processes) would keep the CPU busy while an agent edits.
const memo = new Map();
const MEMO_LIMIT = 4000;

export async function untracked(exec, top) {
  const list = await must(exec, top, ["ls-files", "--others", "--exclude-standard", "-z"]);
  const paths = list.split("\0").filter(Boolean);
  const unread = paths.slice(MAX_UNTRACKED).map((path) => ({ path, why: `Not read: more than ${MAX_UNTRACKED} new files.` }));
  const take = paths.slice(0, MAX_UNTRACKED);
  if (!take.length) return { patches: [], unread };

  const results = new Array(take.length).fill(null);
  const queue = await stamps(exec, top, take);
  const problems = new Array(take.length).fill(null);
  const worker = async () => {
    for (let item = queue.shift(); item; item = queue.shift()) {
      if (!(item.size >= 0)) { problems[item.i] = "Not read: it can't be opened."; continue; }
      if (item.size > MAX_UNTRACKED_BYTES) { problems[item.i] = "Not read: larger than 1 MB."; continue; }
      const key = `${top}\0${item.path}`;
      const known = memo.get(key);
      if (known && known.stamp === item.stamp) { results[item.i] = known.patch; continue; }
      // --no-index exits 1 when the files differ, which is the point.
      const r = await git(exec, top, ["diff", "--no-index", ...DIFF, "--", "/dev/null", item.path]);
      if (r.code <= 1) {
        results[item.i] = r.out;
        if (memo.size >= MEMO_LIMIT) memo.clear();
        memo.set(key, { stamp: item.stamp, patch: r.out });
      } else problems[item.i] = `Not read: ${r.err || "git diff failed"}`;
    }
  };
  await Promise.all(Array.from({ length: Math.min(6, queue.length) }, worker));
  // Kept in the order git listed them, whichever worker finished first: the order is part of the cache key.
  const patches = results.filter((p) => typeof p === "string" && p.trim());
  take.forEach((path, i) => { if (problems[i]) unread.push({ path, why: problems[i] }); });
  return { patches, unread };
}

/**
 * Each file's size and modification time, in one call: a stray 40 MB log must
 * not reach the model or overflow exec. Exactly one line per file, in order
 * ("-1" when it can't be read), so no size lands on the wrong path. GNU stat
 * first: BSD's `stat -c` fails, while GNU's `stat -f` would succeed with something else.
 * @returns {Promise<{ path: string, i: number, stamp: string, size: number }[]>}
 */
async function stamps(exec, top, paths) {
  const stats = await exec("sh", ["-c", "for f; do s=$(stat -c '%s %.9Y' \"$f\" 2>/dev/null || stat -f '%z %Fm' \"$f\" 2>/dev/null) || s=-1; echo \"${s:--1}\"; done", "sh", ...paths], { cwd: top });
  const lines = (stats.stdout ?? "").split("\n");
  return paths.map((path, i) => {
    const stamp = (lines[i] ?? "-1").trim();
    return { path, i, stamp, size: Number(stamp.split(" ")[0]) };
  });
}

/**
 * The tree the working tree is now, as `git add -A && git write-tree` would
 * make it, against an index (a copy of the repository's) and an object folder
 * of its own: the same snapshot as hooks/turn.sh, for a turn still running.
 * The repository's objects are kept out of sight (git would update the time of
 * any it found again), so the tree may name blobs only the repository has:
 * a turn is always read with both. New files over 1 MB are left out, as a diff
 * leaves them unread, and named in `big`.
 * @returns {Promise<{ tree: string, big: string[] }>}
 */
export async function snapshotTree(exec, top, { index, objects }) {
  const real = (await must(exec, top, ["rev-parse", "--path-format=absolute", "--git-path", "index"])).trim();
  const big = await largeUntracked(exec, top);
  const env = [`GIT_INDEX_FILE=${index}`, `GIT_OBJECT_DIRECTORY=${objects}`];
  const run = async (args) => {
    const r = await exec("env", [...env, "git", "-c", "core.fsmonitor=false", "-c", "gc.auto=0", "-c", "maintenance.auto=false", ...args], { cwd: top });
    if (r.code !== 0) throw new Error((r.stderr || `git ${args[0]} failed`).trim());
    return (r.stdout ?? "").trim();
  };
  const snap = async (copy) => {
    // The repository's own index, copied once: its file stats spare re-reading every unchanged file.
    if (copy) await exec("sh", ["-c", '[ -f "$1" ] || [ ! -f "$0" ] || cp -p "$0" "$1"', real, index]);
    // A file small when the turn began is in this index already: out with it too, or its old content stays.
    if (big.length) await run(["update-index", "--force-remove", "--", ...big]);
    await run(["add", "-A", "--", ".", ...big.map((p) => `:(exclude,literal)${p}`)]);
    return run(["write-tree", "--missing-ok"]);
  };
  await exec("mkdir", ["-p", objects]);
  let tree;
  try { tree = await snap(true); } catch {
    // A copied index git can't use here (a split index, say) is dropped, and the snapshot starts over without it, as turn.sh's does.
    await exec("rm", ["-f", index]);
    tree = await snap(false).catch(async (e) => { await exec("rm", ["-f", index]); throw e; });
  }
  return { tree, big };
}

/**
 * New files over 1 MB, found by `find -size` in batches (xargs): no argument
 * list grows with the number of new files, and no process runs per file.
 */
async function largeUntracked(exec, top) {
  const script = `git ${READ.join(" ")} ls-files --others --exclude-standard -z | xargs -0 sh -c '[ $# -gt 0 ] && find "$@" -prune -type f -size +${MAX_UNTRACKED_BYTES}c' sh; exit 0`;
  const r = await exec("sh", ["-c", script], { cwd: top });
  return (r.stdout ?? "").split("\n").filter(Boolean);
}

/**
 * The name of a repository's turns folder, as hooks/turn.sh makes it: the
 * first 16 digits of git's hash of its path, hashed inside the repository so
 * a SHA-256 one names it the same way the hook does.
 */
export async function turnsKey(exec, top) {
  const r = await exec("sh", ["-c", 'printf %s "$0" | git hash-object --stdin', top], { cwd: top });
  const key = (r.stdout ?? "").trim().slice(0, 16);
  return r.code === 0 && /^[0-9a-f]{16}$/.test(key) ? key : null;
}

/**
 * Of the paths a folder watch reported, those that might change a diff,
 * relative to the repository, for `git check-ignore`; `true` when one of git's
 * own files that a diff depends on changed (the index, HEAD, a ref).
 */
export function worthReading(top, paths, gitDir = `${top}/.git`) {
  const out = [];
  for (const path of paths ?? []) {
    // A worktree's own git folder, watched beside it: its index, HEAD and their logs.
    if (gitDir !== `${top}/.git` && path.startsWith(`${gitDir}/`)) {
      if (/^(index|HEAD|logs\/HEAD|refs\/)/.test(path.slice(gitDir.length + 1))) return true;
      continue;
    }
    if (!path.startsWith(`${top}/`)) return true;
    const rel = path.slice(top.length + 1);
    if (rel === ".git" || rel.startsWith(".git/")) {
      if (/^\.git\/(index|HEAD|packed-refs|refs\/)/.test(rel)) return true;
      continue;
    }
    if (/(^|\/)node_modules(\/|$)/.test(rel)) continue;
    out.push(rel);
  }
  return out;
}

/**
 * A source → sections to parse, and files that could not be read.
 * @returns {Promise<{ sections: { scope: string, patch: string }[], unread: { path: string, why: string }[] }>}
 */
export async function loadSections(exec, top, source) {
  const sections = [];
  let unread = [];
  const add = (scope, ...patches) => {
    const patch = patches.filter((p) => p && p.trim()).join("\n");
    if (patch.trim()) sections.push({ scope, patch });
  };
  const withUntracked = async (scope, patch) => {
    const u = await untracked(exec, top);
    unread = u.unread;
    add(scope, patch, ...u.patches);
  };

  switch (source.kind) {
    case "uncommitted":
      add("staged", await must(exec, top, ["diff", "--cached", ...DIFF]));
      await withUntracked("working", await must(exec, top, ["diff", ...DIFF]));
      break;
    case "staged":
      add("staged", await must(exec, top, ["diff", "--cached", ...DIFF]));
      break;
    case "unstaged":
      await withUntracked("working", await must(exec, top, ["diff", ...DIFF]));
      break;
    case "branch": {
      // The merge base, so work that arrived on the base after branching is not counted as this branch's.
      const base = (await must(exec, top, ["merge-base", source.base, "HEAD"])).trim();
      await withUntracked("branch", await must(exec, top, ["diff", ...DIFF, base]));
      break;
    }
    case "commit": {
      const parents = (await must(exec, top, ["rev-list", "--parents", "-n", "1", source.hash])).trim().split(" ");
      add("commit", await must(exec, top, ["diff", ...DIFF, parents[1] ?? EMPTY_TREE, source.hash]));
      break;
    }
    case "pr":
      add("pr", await gh(exec, top, ["pr", "diff", String(source.number), "--color=never"]));
      break;
    case "turn": {
      // The snapshots' objects live in the turns' own folders; git reads them as alternates beside the repository's.
      let end = source.endTree, big = source.endBig ?? [];
      if (!end) ({ tree: end, big } = await snapshotTree(exec, top, { index: `${source.dir}/now.index`, objects: `${source.dir}/objects` }));
      const objects = [...new Set([source.dir, source.endDir ?? source.dir])].map((d) => `${d}/objects`).join(":");
      // A new file over 1 MB at the end is listed unread, as in every scope; one that was big at the start too is no news.
      const left = big.map((p) => `:(exclude,literal)${p}`);
      const r = await exec("env", [`GIT_ALTERNATE_OBJECT_DIRECTORIES=${objects}`, "git", ...READ, "diff", ...DIFF, source.startTree, end, ...(left.length ? ["--", ".", ...left] : [])], { cwd: top });
      const before = new Set(source.startBig ?? []);
      unread = big.filter((p) => !before.has(p)).map((path) => ({ path, why: "Not read: larger than 1 MB." }));
      if (r.code !== 0) throw new Error(await snapshotsGone(exec, top, source, r.stderr) ?? (r.stderr || "git diff failed").trim());
      add("turn", r.stdout ?? "");
      break;
    }
    default:
      throw new Error(`Unknown source "${source.kind}"`);
  }
  return { sections, unread };
}

/**
 * Why a turn's diff found something missing, or null when nothing was. A
 * turn's folder goes when 20 newer ones are kept; the files its snapshots left
 * to the repository's objects can go with `git gc`, once nothing there names them.
 */
async function snapshotsGone(exec, top, source, stderr) {
  if (!/bad object|not a tree|could not read|unable to read/i.test(stderr ?? "")) return null;
  const dirs = [...new Set([source.dir, source.endDir ?? source.dir])];
  const r = await exec("sh", ["-c", 'for d; do [ -d "$d/objects" ] || exit 1; done', "sh", ...dirs], { cwd: top });
  return r.code !== 0
    ? "This turn's snapshots are gone: only the newest 20 turns are kept."
    : "Part of this turn is gone from the repository: its snapshots point at file contents git keeps there, and git gc has removed some that no commit or index still names.";
}

/**
 * Where a branch most likely started from: its upstream remote's default
 * branch, else a local main, master, trunk or develop, never itself.
 */
export async function defaultBase(exec, top, current) {
  const head = await git(exec, top, ["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"]);
  const candidates = [head.ok ? head.out.trim() : "", "origin/main", "origin/master", "main", "master", "trunk", "develop"].filter(Boolean);
  for (const ref of candidates) {
    if (ref === current || ref === `origin/${current}`) continue;
    if ((await git(exec, top, ["rev-parse", "--verify", "-q", `${ref}^{commit}`])).ok) return ref;
  }
  return null;
}

/** Branches to compare against: local ones, then remote ones, most recent first, without the current one. */
export async function baseChoices(exec, top, current) {
  const r = await git(exec, top, ["for-each-ref", "--sort=-committerdate", "--format=%(refname:short)", "refs/heads", "refs/remotes"]);
  return r.out.split("\n").map((s) => s.trim()).filter((s) => s && s !== current && !s.endsWith("/HEAD") && s !== "origin");
}

/** The latest commits on HEAD: { hash, short, subject, author, when }. */
export async function recentCommits(exec, top, count = 40) {
  const r = await git(exec, top, ["log", `-n${count}`, "--format=%H%x1f%h%x1f%s%x1f%an%x1f%cr"]);
  if (!r.ok) return [];
  return r.out.split("\n").filter(Boolean).map((line) => {
    const [hash, short, subject, author, when] = line.split("\x1f");
    return { hash, short, subject, author, when };
  });
}

/** Runs the GitHub CLI; its failures come back as one readable sentence. */
async function gh(exec, top, args) {
  let r;
  try { r = await exec("gh", args, { cwd: top }); } catch { throw new Error(GH_MISSING); }
  if (r.code !== 0) throw new Error(ghError(r.stderr || r.stdout));
  return r.stdout ?? "";
}

const GH_MISSING = "Pull requests are read with the GitHub CLI (gh), and it isn't installed. Install it, then run gh auth login.";

/** gh's own words, made to say what to do. */
export function ghError(text) {
  const t = String(text ?? "").trim();
  if (/gh auth login|not logged in|authentication/i.test(t)) return "The GitHub CLI isn't logged in. Run gh auth login, then try again.";
  if (/no git remotes|none of the git remotes|not a github|could not determine base repo/i.test(t)) return "This repository has no GitHub remote, so it has no pull requests to read.";
  if (/HTTP 406|too_large|diff exceeded|maximum number of (lines|files)/i.test(t)) return "GitHub won't send a diff this large (about 300 files or 20,000 lines). Read it as a Branch instead.";
  if (/could not resolve to a pullrequest|no pull requests? found/i.test(t)) return "That pull request wasn't found.";
  return t.split("\n").filter(Boolean).pop() || "gh failed.";
}

/**
 * The repository's open pull requests, newest update first: { number, title,
 * body, head, base, author, draft, updated, current }. The description comes
 * with the list, so matching a pull request against it costs no other call.
 */
export async function pullRequests(exec, top, branch = null) {
  const out = await gh(exec, top, ["pr", "list", "--state", "open", "--limit", "50", "--json", "number,title,body,headRefName,baseRefName,author,isDraft,updatedAt"]);
  let list;
  try { list = JSON.parse(out || "[]"); } catch { throw new Error("gh answered with something other than a list of pull requests."); }
  return list
    .map((p) => ({ number: p.number, title: p.title ?? "", body: typeof p.body === "string" ? p.body : "", head: p.headRefName ?? "", base: p.baseRefName ?? "", author: p.author?.login ?? "",
      draft: Boolean(p.isDraft), updated: p.updatedAt ?? "", current: Boolean(branch) && p.headRefName === branch }))
    .sort((a, b) => b.updated.localeCompare(a.updated));
}

/** A commit's whole message, subject and body; null when git couldn't read it (so it can be asked again). */
export async function commitMessage(exec, top, hash) {
  const r = await git(exec, top, ["log", "-1", "--format=%B", hash, "--"]);
  return r.ok ? r.out.trim() : null;
}

/**
 * Since when (ms) the prompts sent to agents count as the task of a working
 * tree or branch source, and how to say so: the last commit for local
 * changes, where the branch left its base for a branch. 0 in a repository
 * with no commits.
 * @returns {Promise<{ since: number, label: string }>}
 */
export async function taskSince(exec, top, source) {
  let at = "HEAD", label = "the last commit";
  if (source.kind === "branch") {
    const base = await git(exec, top, ["merge-base", source.base, "HEAD"]);
    if (base.ok && base.out.trim()) { at = base.out.trim(); label = `the branch left ${source.base}`; }
  }
  const r = await git(exec, top, ["log", "-1", "--format=%ct", at, "--"]);
  const seconds = r.ok ? Number(r.out.trim()) : 0;
  return { since: Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : 0, label: seconds > 0 ? label : "the repository began" };
}
