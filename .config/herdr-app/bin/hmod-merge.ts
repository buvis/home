// hmod-merge: keeps an edited gallery mod current without losing the edits.
//
// hmod skips a mod with local edits, and `hmod update --force` replaces them. This
// merges instead, with git: base = the upstream commit hmod recorded at install,
// ours = the mod folder, theirs = the newest upstream commit that touches the
// folder. A clean merge is checked (`herdr-app check`), installed after a backup,
// and recorded in hmod's sources.json as the new baseline, the way `hmod update`
// records one. A conflict changes nothing and leaves the merge for review.
//
//   hmod-merge status [--json]   mods behind upstream, and what each needs
//   hmod-merge <mod>...          merge these now (running it is the review)
//   hmod-merge --auto            sysup: merge what's safe unattended; print what
//                                needs the person to stderr and exit 1
//
// Forks: mods hmod can't or shouldn't track (cloned_from, or rewritten here) are
// listed in forks.json in the Herdr home, {"<mod>": {repo, path, branch, commit}},
// commit = the upstream commit the fork last took. They merge the same way, but
// never unattended: --auto only says when upstream has moved.
//
// Reuses hmod's own code (sources lock, hashing, install rules), so it follows hmod
// exactly; HMOD_SRC points at it. HMOD_MERGE_REMOTE replaces the GitHub URL (tests).

import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const HOME = process.env.HOME!;
const SRC = process.env.HMOD_SRC ?? join(HOME, "git/src/github.com/jonathan-fielding/herdr-mod-updater/src");
const { loadSources, updateSources } = await import(`${SRC}/store.ts`);
const { hashTree, diffTrees } = await import(`${SRC}/fsutil.ts`);
const { installable, apply, herdrCheck } = await import(`${SRC}/update.ts`);
const { paths, hmodHome, herdrHome } = await import(`${SRC}/paths.ts`);

const FORKS = join(herdrHome(), "forks.json");
const readForks = (): Record<string, any> => (existsSync(FORKS) ? JSON.parse(readFileSync(FORKS, "utf8")) : {});
function recordFork(name: string, commit: string) {
  const all = readForks();
  all[name] = { ...all[name], commit };
  writeFileSync(`${FORKS}.tmp`, `${JSON.stringify(all, null, 2)}\n`);
  renameSync(`${FORKS}.tmp`, FORKS);
}

const CACHE = join(process.env.XDG_CACHE_HOME ?? join(HOME, ".cache"), "hmod-merge");
// No hooks, signing or identity from the person's git config in throwaway repos.
const GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=hmod-merge", "-c", "user.email=hmod-merge@localhost"];

function git(args: string[], cwd?: string, ok = false): string {
  const p = Bun.spawnSync([...GIT, ...args], { cwd, stderr: "pipe" });
  if (p.exitCode !== 0 && !ok) throw new Error(`git ${args.join(" ")}: ${p.stderr.toString().trim()}`);
  return p.stdout.toString().trim();
}

// A bare clone per repo, fetched on every use: full history, so any baseline resolves.
function cache(repo: string): string {
  const dir = join(CACHE, `${repo.replace("/", "__")}.git`);
  const url = process.env.HMOD_MERGE_REMOTE ?? `https://github.com/${repo}.git`;
  if (!existsSync(dir)) git(["clone", "--bare", "--quiet", url, dir]);
  else git(["--git-dir", dir, "fetch", "--quiet", "--prune", url, "+refs/heads/*:refs/heads/*"]);
  return dir;
}

// relpath -> blob sha of the files hmod would install from `path` at `commit`.
function files(dir: string, commit: string, path: string): Record<string, string> {
  const out = git(["--git-dir", dir, "ls-tree", "-r", "-t", "-z", `${commit}:${path}`]);
  const entries = out.split("\0").filter(Boolean).map((line) => {
    const [meta, rel] = line.split("\t");
    const [mode, type, sha] = meta.split(" ");
    return { path: rel, mode, type, sha };
  });
  return Object.fromEntries([...installable(entries)].map(([rel, e]) => [rel, e.sha]));
}

interface State { name: string; repo: string; dir: string; git: string; base: string; head: string; behind: number; edited: boolean; pending: boolean; assumed: boolean; fork: boolean }

function state(name: string, rec: any, fork: boolean): State {
  const dir = paths.mod(name), g = cache(rec.repo);
  const tip = git(["--git-dir", g, "rev-parse", rec.branch ? `refs/heads/${rec.branch}` : "HEAD"]);
  const head = git(["--git-dir", g, "rev-list", "-1", tip, "--", rec.path]);
  if (!head) throw new Error(`${rec.path} isn't in ${rec.repo} any more`);
  if (!git(["--git-dir", g, "cat-file", "-t", rec.commit], undefined, true)) throw new Error(`the installed commit ${rec.commit.slice(0, 7)} is gone from ${rec.repo}`);
  const behind = Number(git(["--git-dir", g, "rev-list", "--count", `${rec.commit}..${head}`, "--", rec.path]));
  // A fork counts as edited and as needing the person: it is never merged unattended.
  const edited = fork || diffTrees(rec.files, hashTree(dir)).length > 0;
  return { name, repo: rec.repo, dir, git: g, base: rec.commit, head, behind, edited, pending: fork || rec.first_update_pending === true, assumed: rec.baseline_assumed === true, fork };
}

// What the person has to run, or null when nothing (or sysup's own `hmod update --all`) covers it.
function action(s: State): string | null {
  if (!s.behind) return null;
  const n = `${s.behind} upstream commit${s.behind > 1 ? "s" : ""}`;
  if (s.fork) return `${s.name}: ${n} since your fork took it (${s.repo}): review and merge with hmod-merge ${s.name}`;
  if (s.assumed && s.edited) return `${s.name}: ${n}, but its install commit is unknown: merge it by hand`;
  if (!s.edited) return s.pending ? `${s.name}: ${n}, first update needs your review: hmod update ${s.name}` : null;
  return s.pending ? `${s.name}: ${n} over your edits, first update needs your review: hmod-merge ${s.name}` : null;
}

async function merge(s: State, rec: any): Promise<string> {
  if (!s.behind) return `${s.name}: up to date`;
  const work = mkdtempSync(join(tmpdir(), `hmod-merge-${s.name}-`));
  git(["clone", "--quiet", "--shared", "--no-checkout", s.git, work]);
  git(["checkout", "--quiet", "-B", "ours", s.base], work);
  const folder = join(work, rec.path);
  for (const rel of Object.keys(files(s.git, s.base, rec.path))) rmSync(join(folder, rel), { force: true });
  for (const rel of Object.keys(hashTree(s.dir))) cpSync(join(s.dir, rel), join(folder, rel), { verbatimSymlinks: true });
  git(["add", "-A", "--", rec.path], work);
  git(["commit", "--quiet", "--allow-empty", "-m", "local edits"], work);
  git(["merge", "--quiet", "--no-edit", s.head], work, true);
  const conflicts = git(["diff", "--name-only", "--diff-filter=U"], work);
  if (conflicts) throw new Error(`merge conflict in ${conflicts.split("\n").join(", ")}; nothing changed. Resolve in ${work}, or keep your version`);

  const merged = hashTree(folder), local = hashTree(s.dir);
  const writing = Object.keys(merged).filter((rel) => local[rel] !== merged[rel]);
  const removed = Object.keys(local).filter((rel) => !(rel in merged));
  const first = await herdrCheck(folder);
  if (!first.ok) throw new Error(`the merged mod fails herdr-app check, nothing changed (${work}): ${first.output.trim()}`);

  const backup = join(hmodHome(), "backups", `${s.name}-${new Date().toISOString().replace(/[:.]/g, "-")}`);
  mkdirSync(join(hmodHome(), "backups"), { recursive: true });
  cpSync(s.dir, backup, { recursive: true, verbatimSymlinks: true });
  apply(folder, s.dir, writing, removed);
  const left = diffTrees(merged, hashTree(s.dir));
  const second = left.length ? { ok: false, output: `these didn't install: ${left.join(", ")}` } : await herdrCheck(s.dir);
  if (!second.ok) {
    const saved = hashTree(backup), now = hashTree(s.dir);
    apply(backup, s.dir, Object.keys(saved).filter((r) => saved[r] !== now[r]), Object.keys(now).filter((r) => !(r in saved)));
    throw new Error(`installed but failed herdr-app check, put back as it was: ${second.output.trim()}`);
  }
  const upstream = files(s.git, s.head, rec.path);
  if (s.fork) recordFork(s.name, s.head);
  else await updateSources((all: any) => {
    const r = all[s.name];
    if (!r) return;
    r.commit = s.head; r.files = upstream;
    delete r.baseline_assumed; delete r.first_update_pending;
  });
  rmSync(work, { recursive: true, force: true });
  const log = git(["--git-dir", s.git, "log", "--oneline", `${s.base}..${s.head}`, "--", rec.path]);
  return `${s.name}: merged ${s.behind} upstream commit(s), your edits kept (backup ${backup})\n${log}`;
}

const args = process.argv.slice(2), json = args.includes("--json");
const sources = loadSources(), forks = readForks();
const linked = [...new Set([...Object.keys(sources), ...Object.keys(forks)])].sort();
let failed = false;
const each = async (names: string[], fn: (s: State, rec: any) => Promise<void> | void) => {
  for (const name of names) {
    const fork = !sources[name], rec = sources[name] ?? forks[name];
    try { await fn(state(name, rec, fork), rec); }
    catch (e: any) { failed = true; console.error(`${name}: ${e?.message ?? e}`); }
  }
};

if (args[0] === "status") {
  const rows: any[] = [];
  await each(linked, (s) => { rows.push({ name: s.name, repo: s.repo, fork: s.fork, behind: s.behind, edited: s.edited, first_update_pending: s.pending, action: action(s) }); });
  if (json) console.log(JSON.stringify(rows));
  else for (const r of rows.filter((r) => r.behind)) console.log(r.action ?? `${r.name}: ${r.behind} upstream commit(s), sysup updates it`);
} else if (args[0] === "--auto") {
  await each(linked, async (s, rec) => {
    if (s.behind && s.edited && !s.pending && !s.assumed) console.log(await merge(s, rec));
    else { const a = action(s); if (a) { failed = true; console.error(a); } }
  });
} else if (args.length && !args[0].startsWith("-")) {
  const unknown = args.filter((n) => !sources[n] && !forks[n]);
  if (unknown.length) { console.error(`not linked in hmod or listed in ${FORKS}: ${unknown.join(", ")}`); process.exit(2); }
  await each(args, async (s, rec) => console.log(await merge(s, rec)));
} else {
  console.error("usage: hmod-merge status [--json] | hmod-merge <mod>... | hmod-merge --auto");
  process.exit(2);
}
process.exit(failed ? 1 : 0);
