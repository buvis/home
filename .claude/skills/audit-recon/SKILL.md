---
name: audit-recon
description: Use when auditing cartographer recon-brief injections in the audit log. Reports (repo x day) inject uniqueness, missing-atlas repos, stale-at-inject rate, and excerpt-size distribution. Triggers on "audit recon", "recon audit", "recon injections".
---

# Audit Recon

Report on the recon-brief hook's injection uniqueness, atlas coverage,
staleness, and excerpt size. The aggregation is deterministic, so a script
computes it (PRD 00046) — never parse `audit.jsonl` in-model.

## Dependencies

- Path: `~/.claude/cartographer/audit.jsonl` - the only event source
  (`phase == "recon"`).
- Hook: `~/.claude/hooks/cartographer-recon-brief.py` writes those events. An
  absent hook means an empty audit, not a healthy silence.
- CLI: `python3`.

## Step 1: Run the report script

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/report.py
```

It reads `~/.claude/cartographer/audit.jsonl` (`phase == "recon"` events) and
prints four sections: `Inject uniqueness (repo x day)`, `Missing-atlas
repos`, `Stale-at-inject rate`, `Excerpt-size distribution`, plus header
totals and a `malformed:` line count. An empty or missing log prints zero
counts — that itself is the `LOW: no recon events recorded yet` finding.

## Step 2: Interpret the summary into findings

- **HIGH** — any (repo x day) group the script marks `THROTTLE BROKEN (>=3)`.
  A count of exactly 2 is the documented concurrent-session race; tolerate it.
- **MEDIUM** — each repo under `Missing-atlas repos` (no atlas; run `/survey`
  there), and a non-zero `stale_pct` (listed repos injected a stale atlas;
  run `/survey --refresh`).
- **LOW** — no recon events yet, or a large share of injects sitting at the
  1024-byte excerpt cap (informational; the cap is working as designed).

## Step 3: Findings report

Synthesize a `## Findings` section (CRITICAL/HIGH/MEDIUM/LOW) followed by a
`## Summary` block quoting the script's counts verbatim: recon totals
(inject / atlas-missing), double-inject groups, repos needing `/survey`,
stale-at-inject rate, and excerpt min/median/max.

## Notes

- Source hook: `~/.claude/hooks/cartographer-recon-brief.py` (UserPromptSubmit;
  injects once per repo per UTC day). Suppressed prompts are intentionally not
  logged, so absence of an event after a day's first inject is expected.
- Event schema: `ts` (ISO-8601 UTC), `session`, `phase: "recon"`, `decision`
  (`inject` | `atlas-missing`), `repo_hash`, `atlas_excerpt_bytes` (0 on
  atlas-missing), `stale` (bool).
- Read-only: neither the script nor this skill modifies the audit log.
