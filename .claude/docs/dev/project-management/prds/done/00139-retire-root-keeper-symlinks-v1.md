# Retire the dev/local root keeper symlinks

Source: 2026-08-23 meta/ migration - keepers moved to `dev/local/meta/` across
all 15 stores with compat symlinks left at root for the released plugins that
still read root paths. This PRD ends the symlink era.

**Blocked by:** git-ferry PRD 00012, agoge PRD 00001, aegis PRD 00014 - all
three must be RELEASED AND INSTALLED first (verify the shipped plugin cache,
not the version string).

> **Hold reviewed 2026-08-26, kept. Blocker status verified against the shipped
> caches, not the repos:**
> - **agoge 00001** (`read-profile-from-devlocal-meta`) is in `claude-agoge/dev/local/prds/done/`
>   but has NOT shipped: the installed cache `plugins/cache/buvis-plugins/agoge/0.1.2`
>   still reads the ROOT path in four places (`skills/run-agoge/SKILL.md:80,157,307`,
>   `references/finding-contract.md:177`) and its own gate test pins it
>   (`scripts/test_agoge_authorization_gate.py:207` asserts `dev/local/agoge-profile.md`).
>   Done-in-repo is not installed. **This one needs a release, not a PRD.**
>   **CLEARED later on 2026-08-26:** agoge 0.1.3 and 0.1.4 are now installed. Cache
>   0.1.4 resolves `dev/local/meta/agoge-profile.md` first with a root fallback
>   (`skills/run-agoge/SKILL.md:84-85,166,317`, `references/finding-contract.md:177-178`),
>   and the gate test asserts meta-before-root
>   (`scripts/test_agoge_authorization_gate.py:655-657`). One of three blockers down.
> - **git-ferry 00012** (`read-keepers-from-devlocal-meta-v1.md`) is still in
>   `claude-git-ferry/dev/local/prds/backlog/` - undone.
> - **aegis 00014** (`canonicalize-meta-keepers-in-contract-v1.md`) is still in
>   `claude-aegis/dev/local/prds/backlog/` - undone.
>
> Control for the cache check: `dev/local` matches 3/8/8 files across the three
> caches while `dev/local/meta` matches 0, so the empty result is a real absence
> rather than a broken search. **Unblock path: one agoge release plus two PRDs
> drained in their own repos.** Re-check the three caches before unparking.
>
> **Unblock path as of 2026-08-26 (evening): two PRDs, no release.** agoge is done
> (above). git-ferry 0.3.0 and aegis 0.3.1 caches still match `dev/local/meta` zero
> times, and both PRDs sit undone in their repo backlogs. Re-check those two caches
> before unparking.

> **UNPARKED 2026-08-27. All three blockers cleared and verified in the shipped
> caches, not the version strings:**
> - **agoge 0.1.4**: `skills/run-agoge/SKILL.md:84-85,166,317` read
>   `dev/local/meta/agoge-profile.md` first with a root fallback; the gate test
>   asserts meta-before-root (`test_agoge_authorization_gate.py:655-657`).
> - **git-ferry 0.4.0** (PRD 00012, released 2026-08-26): `skills/catchup/SKILL.md:32,89`
>   read the keepers meta-first and write the capsule to `dev/local/meta/project-capsule.md`;
>   `skills/catchup-upstream/SKILL.md:47,100` look for and delete the legacy cursor at
>   both homes. 33/33 bats green at release.
> - **aegis 0.3.2** (PRD 00014, released 2026-08-26): `rules/working-documents.md:21,25-26`
>   name `meta/` canonical, list `agoge-profile.md` as a keeper, state the write-time
>   enforcement, and drop the "kept-but-unclassified forever" claim. 227 release-checks
>   green. Note this file says `meta/`, not `dev/local/meta`, so a `dev/local/meta` grep
>   over the aegis cache hits only its CHANGELOG - check the rule file's own text.
>
> A stale marketplace index made the first `/plugin update` a silent no-op (it compared
> against `git-ferry 0.3.0` / `aegis 0.3.1`); `/plugin marketplace update buvis-plugins`
> before the updates is what landed them. Phase 1 step 1 is therefore already done.

## Overview

### Problem Statement

Root symlinks (`project-capsule.md`, `assumptions.md`, `agoge-profile.md`,
`ecc-cursor`, ...) exist only so unrepointed plugin releases keep resolving
root paths. Once the three repoints ship, the symlinks are dead weight and the
root can become dirs-only, which was the point of the migration.

### Success Metrics

- `ls` of every store root shows directories only (no files, no symlinks).
- The layout hook blocks root keeper names outright (no symlink-era allowance).
- `/catchup`, `/run-agoge`, `/catchup-ecc`, engram `pack`/`index`, and an
  autopilot phase-done capsule update all work against meta/ paths.

## Implementation Phases

### Phase 1: Verify and retire

1. Verify the three plugin releases are installed (plugin cache carries the
   meta-first paths).
2. Remove the root keeper symlinks in every store (loop over
   `purge_devlocal.find_stores`, `os.unlink` symlinks whose name is in
   KEEP_NAMES; regular files stay untouched and get reported).
3. Flip `~/.claude/hooks/enforce_prd_location.py`: the root-keeper allowance
   branch (marked with the symlink-era comment) becomes a block; update its
   tests.
4. `purge_devlocal.py`: keep accepting root-keeper REGULAR files (other
   machines may migrate later) - only the hook flips.
5. Optionally drop engram's root fallbacks (corpora decisions, cli capsule)
   once every machine's stores are migrated; otherwise leave them.

*Acceptance:* success metrics above; hook + GC + engram test suites green.

## Test Strategy

- Hook test: root keeper name write blocks after the flip.
- Manual: one catchup run and one agoge recon against a migrated store.

## Risks

- **A stale plugin cache on another machine** resolves root paths after the
  symlinks are gone: reads fail loudly and the fallback is `git pull` +
  plugin update, not data loss - the meta/ files are the canonical bytes.
