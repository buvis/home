---
name: audit-recon
description: Use when auditing cartographer recon-brief injections in the audit log. Reports (repo x day) inject uniqueness, missing-atlas repos, stale-at-inject rate, and excerpt-size distribution. Triggers on "audit recon", "recon audit", "recon injections".
---

# Audit Recon

Read `~/.claude/cartographer/audit.jsonl`, filter to the recon-brief hook's events, and report on injection uniqueness, atlas coverage, staleness, and excerpt size.

The `cartographer-recon-brief.py` UserPromptSubmit hook emits one audit event per inject (once per repo per UTC day) and one per atlas-missing recommendation. Suppressed prompts are not logged. Each recon event has:

- `ts` — ISO-8601 UTC timestamp (stamped by `append_audit`).
- `session` — session id (may be `""`).
- `phase` — always `"recon"`.
- `decision` — `"inject"` (atlas present) or `"atlas-missing"` (no atlas yet).
- `repo_hash` — the per-repo hash.
- `atlas_excerpt_bytes` — excerpt byte length on inject; `0` on atlas-missing.
- `stale` — `true` when `staleness.flag` was present at inject; always `false` on atlas-missing.

## Step 1: Load recon events

Read `~/.claude/cartographer/audit.jsonl` (one JSON object per line). Keep only events where `phase == "recon"`. For each kept event, derive `day` = the date portion (`YYYY-MM-DD`) of `ts`.

If the audit log is absent, empty, or has no `phase == "recon"` events: report `LOW: no recon events recorded yet` and stop (the hook has not injected in any repo this install).

## Step 2: Inject uniqueness per (repo x day)

This is the hook's core success metric: at most one inject per (`repo_hash` x UTC `day`).

- Group `decision == "inject"` events by (`repo_hash`, `day`).
- Any group with a count `> 1` is a **double-inject** — the day-keyed throttle failed (or two concurrent sessions raced the store; one redundant inject per day is a documented, accepted race).

Report:

| repo_hash (short) | day | inject count |
|---|---|---|
| `abc123` | 2026-07-04 | 1 |
| `def456` | 2026-07-04 | 2 |

**HIGH** for each (`repo_hash`, `day`) with an inject count `> 1` that exceeds the accepted single-race tolerance (a count of exactly 2 is the documented worst-case race; a count `>= 3` in one day means the throttle is broken).

## Step 3: Missing-atlas repos (need /survey)

- Collect the distinct `repo_hash` values that appear with `decision == "atlas-missing"`.
- Count `atlas-missing` events total and per repo.

Report:

| repo_hash (short) | atlas-missing events | last day |
|---|---|---|

**MEDIUM** for each repo with `atlas-missing` events — those repos have no atlas and should run `/survey`.

## Step 4: Stale-at-inject rate (need /survey --refresh)

Among `decision == "inject"` events:

- `stale_pct` = 100 x (inject events with `stale == true`) / (total inject events).
- List the distinct `repo_hash` values with any `stale == true` inject.

Report:

| repo_hash (short) | stale injects | last stale day |
|---|---|---|

**MEDIUM** if `stale_pct > 0` — the listed repos injected a stale atlas and should run `/survey --refresh`.

## Step 5: Excerpt size distribution

Filter to `decision == "inject"` only (atlas-missing events carry `atlas_excerpt_bytes: 0`, which would skew the distribution).

Compute over `atlas_excerpt_bytes`:

- min, median, max.
- count at the 1024-byte cap (excerpts truncated to the byte budget).

Report:

| metric | bytes |
|---|---|
| min | N |
| median | N |
| max | N |
| at 1024-byte cap | N injects |

**LOW** if a large share of injects sit at the 1024-byte cap — atlases are routinely larger than the excerpt budget (informational; the cap is working as designed).

## Step 6: Findings report

Synthesize:

```
## Findings

### CRITICAL
(recon audit contract violations — e.g. a recon event missing required keys)

### HIGH
- {(repo_hash, day) has N injects (>= 3) — day-keyed throttle broken}

### MEDIUM
- {repo <hash> has N atlas-missing events — run /survey}
- {stale_pct X% — repos <hashes> injected a stale atlas, run /survey --refresh}

### LOW
- {no recon events recorded yet}
- {N% of injects at the 1024-byte excerpt cap — atlases exceed the budget (informational)}

## Summary

- Recon events total: N (inject N / atlas-missing N)
- Distinct repos injected: N
- (repo x day) double-inject groups: N
- Repos needing /survey (atlas-missing): N
- Stale-at-inject rate: X%
- Excerpt bytes (min / median / max): N / N / N
```

## Notes

- Audit log: `~/.claude/cartographer/audit.jsonl` (JSONL, appended by `_lib_cartographer.append_audit`).
- Source hook: `~/.claude/hooks/cartographer-recon-brief.py` (UserPromptSubmit; injects once per repo per UTC day).
- Suppressed prompts are intentionally not logged, so absence of an event for a (repo, day) after the first inject is expected, not a gap.
- The documented concurrent-session race can produce exactly one redundant inject per repo per day; treat a count of 2 as within tolerance and `>= 3` as a broken throttle.
- This skill is read-only; it never modifies the audit log or any atlas files.
