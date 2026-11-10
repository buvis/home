// Keep the merged tip recoverable even after a squash merge removes its branch.
export async function cleanupPlan(exec, gh, target) {
  const { root, on, number } = target;
  const call = async (program, args, cwd = root) => {
    const r = await exec(program, args, { cwd, on });
    if (r.code !== 0) throw new Error((r.stderr || r.stdout || `${program} failed`).trim());
    return r.stdout.trim();
  };
  const pr = JSON.parse(await call(gh, ["pr", "view", String(number), "--json", "number,state,headRefName,headRefOid,baseRefName"]));
  if (pr.number !== number || pr.state !== "MERGED") throw new Error("The pull request is not confirmed merged.");
  const branch = await call("git", ["branch", "--show-current"]);
  const sha = await call("git", ["rev-parse", "HEAD"]);
  if (!branch || branch !== pr.headRefName || sha !== pr.headRefOid || branch === pr.baseRefName)
    throw new Error("This checkout no longer matches the merged PR tip. Nothing removed.");
  const top = await call("git", ["rev-parse", "--show-toplevel"]);
  const list = await call("git", ["worktree", "list", "--porcelain", "-z"]);
  const entries = list.split("\0\0").filter(Boolean).map((s) => s.split("\0"));
  const main = entries[0]?.find((s) => s.startsWith("worktree "))?.slice(9);
  const current = entries.find((e) => e.includes(`worktree ${top}`));
  if (!main || !current || main === top || current.some((s) => /^(locked|prunable)( |$)/.test(s)))
    throw new Error("Cleanup requires an unlocked linked worktree, never the main checkout.");
  const status = await call("git", ["status", "--porcelain=v1", "--untracked-files=all"]);
  if (status) throw new Error("The worktree has uncommitted or untracked files. Nothing removed.");
  // Use the configured upstream, not an assumed origin or a pushRemote override.
  const remote = await call("git", ["config", "--get", `branch.${branch}.remote`]);
  const remoteRef = await call("git", ["config", "--get", `branch.${branch}.merge`]);
  if (!remote || remote === "." || remoteRef !== `refs/heads/${pr.headRefName}`)
    throw new Error("Cleanup needs a remote upstream matching the PR branch.");
  const remoteUrl = await call("git", ["remote", "get-url", remote]);
  const pushUrls = await call("git", ["remote", "get-url", "--push", "--all", remote]);
  if (pushUrls !== remoteUrl) throw new Error("Upstream fetch and push destinations differ; remote cleanup stopped.");
  const trackingRef = await call("git", ["for-each-ref", "--format=%(upstream)", `refs/heads/${branch}`]);
  let trackingSha = null;
  if (trackingRef.startsWith("refs/remotes/")) {
    const r = await exec("git", ["rev-parse", "--verify", trackingRef], { cwd: root, on });
    if (r.code === 0) trackingSha = r.stdout.trim();
  }
  return { root: top, on, number, branch, sha, main, remoteUrl, remoteRef, trackingRef, trackingSha };
}

// The closing space's terminals ({cwd, own: true}) must all be in the worktree;
// no other terminal on that machine may be. A folder that is gone is in no
// worktree: Herdr's exec rejects there, and that must not block cleanup.
export async function checkTerminals(exec, root, on, terminals) {
  for (const { cwd, own } of terminals) {
    if (!cwd) throw new Error("A terminal's folder is unknown; close it before cleanup.");
    const r = await exec("git", ["rev-parse", "--show-toplevel"], { cwd, on }).catch(() => null);
    const inside = r?.code === 0 && r.stdout.trim() === root;
    if (own && !inside) throw new Error(`This space also contains a terminal outside the worktree (${cwd}); move it before cleanup.`);
    if (!own && inside) throw new Error(`Another space is using this worktree (${cwd}); close it before cleanup.`);
  }
}

export async function removeCheckout(exec, plan) {
  const { main, root, on, branch, sha, remoteUrl, remoteRef } = plan;
  const git = async (args, cwd = main) => {
    const r = await exec("git", args, { cwd, on });
    if (r.code !== 0) throw new Error((r.stderr || r.stdout || "git failed").trim());
    return r.stdout.trim();
  };
  // Retain a named recovery ref before removing anything; do not overwrite one.
  const recovery = `refs/archive/ship-it/${branch}/${sha}`;
  const existing = await exec("git", ["rev-parse", "--verify", recovery], { cwd: main, on });
  if (existing.code !== 0) await git(["update-ref", recovery, sha, ""]);
  else if (existing.stdout.trim() !== sha) throw new Error("The recovery ref has changed. Nothing removed.");
  const remoteHead = await git(["ls-remote", "--refs", "--", remoteUrl, remoteRef]);
  if (remoteHead) {
    if (remoteHead !== `${sha}\t${remoteRef}`) throw new Error("The remote branch has moved since the PR merged. Nothing removed.");
    // The server checks the expected tip atomically, including a push racing this check.
    await git(["push", "--porcelain", "--no-follow-tags", `--force-with-lease=${remoteRef}:${sha}`, "--", remoteUrl, `:${remoteRef}`]);
  }
  try {
    // Hosting services can delete the remote branch without updating our cached ref.
    if (plan.trackingSha) {
      const r = await exec("git", ["rev-parse", "--verify", plan.trackingRef], { cwd: main, on });
      if (r.code === 0) await git(["update-ref", "-d", plan.trackingRef, plan.trackingSha]);
    }
    await git(["worktree", "remove", "--", root]); // Never force dirty/locked worktrees or submodules.
  } catch (e) {
    throw new Error(`Remote branch removed or already absent; local cleanup stopped: ${e.message}`);
  }
  try {
    const list = await git(["worktree", "list", "--porcelain", "-z"]);
    if (list.split("\0").includes(`branch refs/heads/${branch}`))
      throw new Error("The branch is checked out elsewhere.");
    await git(["update-ref", "-d", `refs/heads/${branch}`, sha]);
    return { recovery, warning: null };
  } catch (e) {
    return { recovery, warning: `Worktree removed; local branch retained: ${e.message}` };
  }
}
