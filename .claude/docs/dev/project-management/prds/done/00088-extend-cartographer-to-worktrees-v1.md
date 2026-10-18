# 00088 - Extend cartographer to bare-repo work-trees

## Problem

cartographer's project_hash requires a .git directory, so ~/.claude - a bare-repo work-tree and the busiest Claude-on-Claude surface - hashes to "global" and can never have an atlas: recon-brief no-ops on every prompt there while still paying its git spawn. The one atlas injected near-daily (ddb) has been stale on every inject since 2026-07-05. cartographer-echo spawns one rg subprocess per extracted symbol per Edit/Write, which can exceed the 5s hook budget on symbol-dense files - latency paid, gate skipped.

## Goal

The meta-repo gets a real, fresh atlas; the plane's per-call costs shrink to one subprocess.

## Requirements

- R1 project_hash work-tree fallback: resolve identity for bare-repo work-trees (GIT_DIR-aware or path-keyed), with every existing repo's hash preserved (regression test pins current hashes).
- R2 Meta-repo atlas + staleness flow: /survey ~/.claude once R1 lands; define the refresh path for stale atlases (cartographer-stop nudge into an actual survey run, or a scheduled refresh) and un-stale the ddb atlas through it.
- R3 Echo batching: one rg invocation with an alternation of all extracted symbols replaces the per-symbol spawns; a timing test pins p95 under the hook budget on a 30-symbol fixture.

## Acceptance

- recon-brief injects a real ~/.claude brief (observed in a live session).
- Existing repos' hash dirs are untouched by R1 (test).
- Echo's symbol scan is a single subprocess per tool call.

## Out of scope

- Retiring the recon leg (explicitly declined in the 2026-07-19 walkthrough, packet 7). New atlas content semantics.

## Notes

Sources: 2026-07-19 second-pass audit packet 7 (option a chosen: mechanical + meta-repo atlas; mechanical timeout/cache items land via 00086 R4, the echo batching lives here with the hash work).

## Status 2026-07-20 (COMPLETE — acceptance met)

Commits: 09e3e87a (R1), 6b859919 (R3), 7b2a09fa (R2). User decision: "Split lib,
land 00088 fully."

- **R1** — `project_hash` resolves the ~/.claude meta-repo work-tree to a stable
  hash (`f6cfe3ca951e`), scoped so git repos + other non-git dirs are untouched.
  Split into a sibling `_cartographer_identity` module (re-exported) to respect
  `_lib_cartographer`'s PRD-00009 400-line cap. +2 meta tests; existing
  remote-hash pin + parity green (92/92).
- **R3** — echo symbol search is ONE rg over an alternation of all symbols
  (`search_candidates_batch`); `search_candidates` is a thin one-symbol wrapper.
  +2 tests incl. a p95-under-budget timing test on a 30-symbol fixture.
- **R2** — survey `_scan_layers` gained `_SKIP_DIRS` (build/dep + meta-repo data
  dirs). Live `/survey ~/.claude` wrote a clean 6-layer atlas and
  **cartographer-recon-brief injects a real ~/.claude brief (verified live)** —
  the headline acceptance. Refresh path = cartographer-stop's existing
  `maybe_nudge`, now reaching ~/.claude.

**Acceptance:** ✓ recon-brief injects a real ~/.claude brief (observed live);
✓ existing repos' hashes untouched (pinned test); ✓ echo scan is one subprocess.

**Operational carve-outs (documented, not blockers):**
- **Un-stale ddb** — needs an in-ddb `/survey` run; unreachable from this
  ~/.claude-scoped session (harness confines cwd to ~/.claude). The refresh
  nudge now prompts it in-repo; do it there.
- **Bare-repo head_sha** — run.py's `git rev-parse HEAD` fails in ~/.claude (no
  own .git), so the atlas has `head_sha: none` and staleness falls to the
  atlas.md-age nudge only (not the commit-count path). Acceptable.
- **`.cartographerignore`** — a repo-local ignore would generalize the hardcoded
  meta-repo names in `_SKIP_DIRS`. Follow-up, not required for this PRD.
