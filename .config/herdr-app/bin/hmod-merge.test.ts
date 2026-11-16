// bun test bin/hmod-merge.test.ts — offline: a local repo stands in for GitHub and
// `true` for herdr-app check. Never touches the real Herdr or hmod homes.
import { afterEach, beforeEach, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const SCRIPT = join(import.meta.dir, "hmod-merge.ts");
let base: string, env: Record<string, string>, upstream: string, mod: string, sources: string;
const sh = (args: string[], cwd: string) => {
  const p = Bun.spawnSync(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", ...args], { cwd });
  if (p.exitCode) throw new Error(p.stderr.toString());
  return p.stdout.toString().trim();
};
const commit = (files: Record<string, string>) => {
  for (const [rel, text] of Object.entries(files)) writeFileSync(join(upstream, "mods/x", rel), text);
  sh(["add", "-A"], upstream); sh(["commit", "-qm", "c"], upstream);
  return sh(["rev-parse", "HEAD"], upstream);
};
const blobs = (rev: string) => Object.fromEntries(sh(["ls-tree", "-r", `${rev}:mods/x`], upstream).split("\n").map((l) => [l.split("\t")[1], l.split(" ")[2].split("\t")[0]]));
const run = (...args: string[]) => {
  const p = Bun.spawnSync(["bun", SCRIPT, ...args], { env: { ...process.env, ...env } });
  return { code: p.exitCode, out: p.stdout.toString(), err: p.stderr.toString() };
};
const record = () => JSON.parse(readFileSync(sources, "utf8")).x;

let baseSha: string, headSha: string;
beforeEach(() => {
  base = mkdtempSync(join(tmpdir(), "hmod-merge-test-"));
  upstream = join(base, "upstream"); mkdirSync(join(upstream, "mods/x"), { recursive: true });
  sh(["init", "-q", "-b", "master"], upstream);
  baseSha = commit({ "main.js": "a\nb\nc\n", "mod.json": "{}" });
  headSha = commit({ "main.js": "a\nb\nC\n", "extra.js": "new upstream file\n" });
  mod = join(base, "herdr/mods/x"); mkdirSync(mod, { recursive: true });
  writeFileSync(join(mod, "mod.json"), "{}");
  writeFileSync(join(mod, "gpui-kit.d.ts"), "// injected by Herdr");
  mkdirSync(join(base, "hmod"));
  sources = join(base, "hmod/sources.json");
  writeFileSync(sources, JSON.stringify({ x: { repo: "o/r", path: "mods/x", branch: null, commit: baseSha, files: blobs(baseSha), first_update_pending: true } }));
  env = { HERDR_APP_HOME: join(base, "herdr"), HMOD_HOME: join(base, "hmod"), XDG_CACHE_HOME: join(base, "cache"), HMOD_MERGE_REMOTE: upstream, HMOD_HERDR_APP: "true" };
});
afterEach(() => rmSync(base, { recursive: true, force: true }));

test("merge_keeps_local_edits_and_takes_upstream_changes", () => {
  writeFileSync(join(mod, "main.js"), "A\nb\nc\n");
  const r = run("x");
  expect(r.code).toBe(0);
  expect(readFileSync(join(mod, "main.js"), "utf8")).toBe("A\nb\nC\n");
  expect(readFileSync(join(mod, "extra.js"), "utf8")).toBe("new upstream file\n");
  expect(readFileSync(join(mod, "gpui-kit.d.ts"), "utf8")).toBe("// injected by Herdr");
  // Recorded as hmod records an update: the new baseline is upstream's head.
  expect(record().commit).toBe(headSha);
  expect(record().files).toEqual(blobs(headSha));
  expect(record().first_update_pending).toBeUndefined();
});

test("conflict_changes_nothing", () => {
  writeFileSync(join(mod, "main.js"), "a\nb\nZ\n");
  const r = run("x");
  expect(r.code).toBe(1);
  expect(r.err).toContain("merge conflict in mods/x/main.js");
  expect(readFileSync(join(mod, "main.js"), "utf8")).toBe("a\nb\nZ\n");
  expect(record().commit).toBe(baseSha);
});

test("auto_leaves_a_first_update_to_the_person_and_says_what_to_run", () => {
  writeFileSync(join(mod, "main.js"), "A\nb\nc\n");
  const r = run("--auto");
  expect(r.code).toBe(1);
  expect(r.err).toContain("x: 1 upstream commit over your edits, first update needs your review: hmod-merge x");
  expect(readFileSync(join(mod, "main.js"), "utf8")).toBe("A\nb\nc\n");
});

test("auto_merges_once_the_person_has_taken_an_update", () => {
  writeFileSync(join(mod, "main.js"), "A\nb\nc\n");
  const rec = record(); delete rec.first_update_pending;
  writeFileSync(sources, JSON.stringify({ x: rec }));
  const r = run("--auto");
  expect(r.code).toBe(0);
  expect(readFileSync(join(mod, "main.js"), "utf8")).toBe("A\nb\nC\n");
});

const asFork = () => {
  writeFileSync(sources, "{}");
  writeFileSync(join(base, "herdr/forks.json"), JSON.stringify({ x: { repo: "o/r", path: "mods/x", branch: null, commit: baseSha } }));
};

test("auto_never_merges_a_fork_and_says_upstream_moved", () => {
  asFork();
  writeFileSync(join(mod, "main.js"), "A\nb\nc\n");
  const r = run("--auto");
  expect(r.code).toBe(1);
  expect(r.err).toContain("x: 1 upstream commit since your fork took it (o/r): review and merge with hmod-merge x");
  expect(readFileSync(join(mod, "main.js"), "utf8")).toBe("A\nb\nc\n");
});

test("merging_a_fork_records_the_new_upstream_commit_in_forks_json", () => {
  asFork();
  writeFileSync(join(mod, "main.js"), "A\nb\nc\n");
  writeFileSync(join(mod, "ours.js"), "fork-only file\n");
  const r = run("x");
  expect(r.code).toBe(0);
  expect(readFileSync(join(mod, "main.js"), "utf8")).toBe("A\nb\nC\n");
  expect(readFileSync(join(mod, "ours.js"), "utf8")).toBe("fork-only file\n");
  expect(JSON.parse(readFileSync(join(base, "herdr/forks.json"), "utf8")).x.commit).toBe(headSha);
  expect(readFileSync(sources, "utf8")).toBe("{}");
});

test("auto_is_quiet_when_nothing_is_behind", () => {
  writeFileSync(join(mod, "main.js"), "A\nb\nC\n");
  const rec = record(); rec.commit = headSha; rec.files = blobs(headSha); delete rec.first_update_pending;
  writeFileSync(sources, JSON.stringify({ x: rec }));
  const r = run("--auto");
  expect(r.code).toBe(0);
  expect(r.err).toBe("");
});
