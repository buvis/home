import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { cleanupPlan, removeCheckout } from './cleanup.js';

function fixture(t) {
  const dir = mkdtempSync(join(tmpdir(), 'ship-cleanup-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const main = join(dir, 'repo'), root = join(dir, 'topic'), remote = join(dir, 'remote.git');
  const git = (args, cwd = main) => execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  execFileSync('git', ['init', '-b', 'main', main], { stdio: 'ignore' });
  git(['config', 'user.name', 'Test']);
  git(['config', 'user.email', 'test@example.invalid']);
  git(['config', 'core.hooksPath', '/dev/null']);
  git(['commit', '--allow-empty', '-m', 'base']);
  git(['worktree', 'add', '-b', 'topic', root]);
  git(['commit', '--allow-empty', '-m', 'topic'], root);
  const sha = git(['rev-parse', 'HEAD'], root);
  execFileSync('git', ['init', '--bare', remote], { stdio: 'ignore' });
  git(['remote', 'add', 'origin', remote]);
  git(['push', '-u', 'origin', 'topic'], root);
  const pr = { number: 42, state: 'MERGED', headRefName: 'topic', headRefOid: sha, baseRefName: 'main' };
  const exec = async (program, args, opts) => {
    if (program === 'gh') return { code: 0, stdout: JSON.stringify(pr), stderr: '' };
    const r = spawnSync(program, args, { cwd: opts.cwd, encoding: 'utf8' });
    return { code: r.status, stdout: r.stdout || '', stderr: r.stderr || '' };
  };
  return { git, exec, root, main, remote, sha, pr, target: { root, number: 42, on: null } };
}

test('removes a merged worktree and local branch while retaining its exact tip', async (t) => {
  const f = fixture(t);
  // Main intentionally does not contain the topic commit, as after squash/rebase.
  const result = await removeCheckout(f.exec, await cleanupPlan(f.exec, 'gh', f.target));
  assert.equal(result.warning, null);
  assert.equal(existsSync(f.root), false);
  assert.equal(f.git(['rev-parse', result.recovery]), f.sha);
  assert.throws(() => f.git(['rev-parse', '--verify', 'refs/heads/topic']));
  assert.equal(existsSync(f.main), true);
  assert.equal(f.git(['ls-remote', '--heads', 'origin', 'topic']), '');
  assert.throws(() => f.git(['rev-parse', '--verify', 'refs/remotes/origin/topic']));
});

test('accepts a remote branch already deleted by the hosting service', async (t) => {
  const f = fixture(t);
  f.git(['update-ref', '-d', 'refs/heads/topic'], f.remote);
  const result = await removeCheckout(f.exec, await cleanupPlan(f.exec, 'gh', f.target));
  assert.equal(result.warning, null);
  assert.equal(existsSync(f.root), false);
  assert.throws(() => f.git(['rev-parse', '--verify', 'refs/remotes/origin/topic']));
});

test('refuses a remote tip that moved and preserves the worktree', async (t) => {
  const f = fixture(t), base = f.git(['rev-parse', 'main']);
  f.git(['update-ref', 'refs/heads/topic', base], f.remote);
  await assert.rejects(removeCheckout(f.exec, await cleanupPlan(f.exec, 'gh', f.target)), /remote branch has moved/);
  assert.equal(existsSync(f.root), true);
  assert.equal(f.git(['rev-parse', 'topic'], f.remote), base);
});

test('remote lease rejects a push racing the deletion', async (t) => {
  const f = fixture(t), plan = await cleanupPlan(f.exec, 'gh', f.target);
  const base = f.git(['rev-parse', 'main']);
  const exec = async (program, args, opts) => {
    if (args[0] === 'push') f.git(['update-ref', 'refs/heads/topic', base], f.remote);
    return f.exec(program, args, opts);
  };
  await assert.rejects(removeCheckout(exec, plan));
  assert.equal(existsSync(f.root), true);
  assert.equal(f.git(['rev-parse', 'topic'], f.remote), base);
});

test('remote rejection preserves the local branch and worktree', async (t) => {
  const f = fixture(t);
  f.git(['config', 'receive.denyDeletes', 'true'], f.remote);
  await assert.rejects(removeCheckout(f.exec, await cleanupPlan(f.exec, 'gh', f.target)));
  assert.equal(existsSync(f.root), true);
  assert.equal(f.git(['rev-parse', 'topic']), f.sha);
  assert.equal(f.git(['rev-parse', 'topic'], f.remote), f.sha);
});

test('refuses missing upstreams and different push destinations', async (t) => {
  const f = fixture(t);
  f.git(['config', 'remote.origin.pushurl', join(f.main, 'other.git')]);
  await assert.rejects(cleanupPlan(f.exec, 'gh', f.target), /destinations differ/);
  f.git(['config', '--unset', 'branch.topic.remote']);
  await assert.rejects(cleanupPlan(f.exec, 'gh', f.target));
  assert.equal(existsSync(f.root), true);
});

for (const state of ['OPEN', 'CLOSED']) test(`refuses ${state} PRs`, async (t) => {
  const f = fixture(t); f.pr.state = state;
  await assert.rejects(cleanupPlan(f.exec, 'gh', f.target), /not confirmed merged/);
  assert.equal(existsSync(f.root), true);
});

test('refuses commits added after the merged PR', async (t) => {
  const f = fixture(t);
  f.git(['commit', '--allow-empty', '-m', 'later'], f.root);
  await assert.rejects(cleanupPlan(f.exec, 'gh', f.target), /no longer matches/);
});

test('refuses untracked files and locked worktrees', async (t) => {
  const f = fixture(t);
  writeFileSync(join(f.root, 'notes'), 'keep me');
  await assert.rejects(cleanupPlan(f.exec, 'gh', f.target), /uncommitted or untracked/);
  f.git(['worktree', 'lock', f.root]);
  await assert.rejects(cleanupPlan(f.exec, 'gh', f.target), /unlocked linked worktree/);
});

test('refuses the main checkout even when it matches a merged PR', async (t) => {
  const f = fixture(t);
  f.pr.headRefName = 'main'; f.pr.headRefOid = f.git(['rev-parse', 'HEAD']); f.pr.baseRefName = 'release';
  await assert.rejects(cleanupPlan(f.exec, 'gh', { ...f.target, root: f.main }), /never the main checkout/);
});

test('git refuses new files appearing after preflight without forcing removal', async (t) => {
  const f = fixture(t), plan = await cleanupPlan(f.exec, 'gh', f.target);
  writeFileSync(join(f.root, 'late-notes'), 'keep me');
  await assert.rejects(removeCheckout(f.exec, plan));
  assert.equal(existsSync(f.root), true);
  assert.equal(f.git(['rev-parse', 'topic']), f.sha);
});

test('retains a branch moved concurrently after worktree removal', async (t) => {
  const f = fixture(t), plan = await cleanupPlan(f.exec, 'gh', f.target);
  const base = f.git(['rev-parse', 'main']);
  const exec = async (program, args, opts) => {
    const result = await f.exec(program, args, opts);
    if (args[0] === 'worktree' && args[1] === 'remove' && result.code === 0)
      f.git(['update-ref', 'refs/heads/topic', base, f.sha]);
    return result;
  };
  const result = await removeCheckout(exec, plan);
  assert.match(result.warning, /branch retained/);
  assert.equal(f.git(['rev-parse', 'topic']), base);
  assert.equal(f.git(['rev-parse', result.recovery]), f.sha);
});
