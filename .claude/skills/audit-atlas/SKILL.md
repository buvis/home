---
name: audit-atlas
description: Use when auditing the health of Cartographer atlases across all tracked repos. Reports fresh-atlas coverage, staleness distribution, atlas size, and layer population. Triggers on "audit atlas", "atlas health", "cartographer coverage".
---

# Audit Atlas

Report on atlas coverage, freshness, and content quality across
`~/.claude/cartographer/projects/`. The aggregation is deterministic, so a
script computes it (PRD 00046) — never scan the atlas files in-model.

## Dependencies

- Skill: `survey` - produces the atlases audited here, and is the remediation
  every finding points at.
- Paths: `~/.claude/cartographer/projects/<hash>/atlas.json` (written by
  `survey` plus the cartographer hooks), `~/.claude/instincts/projects.json`
  (recent-activity cross-reference).
- CLI: `python3`.
- No atlas store yet = zero counts, which is the `LOW: no atlases found`
  finding, not an error.

## Step 1: Run the report script

```bash
python3 ~/.claude/skills/audit-atlas/scripts/report.py
```

It scans every `projects/<hash>/atlas.json` (cross-referencing
`~/.claude/instincts/projects.json` for repos active in the last 30 days) and
prints four sections: `Fresh-atlas coverage`, `Staleness distribution`,
`Atlas size`, `Layer population`, plus a `malformed:` count. Fresh = no
`staleness.flag` AND surveyed under 14 days ago (the flag is authoritative —
the `cartographer-stop` hook computes the full 50-commit/14-day check with
per-repo overrides). An empty projects dir prints zero counts — that is the
`LOW: no atlases found` finding.

## Step 2: Interpret the summary into findings

- **HIGH** — `active_fresh_pct` below 80% (the PRD target: >80% of
  actively-edited repos have a fresh atlas), and any `atlas.md` listed over
  the 5KB budget.
- **MEDIUM** — each Stale atlas row, and any atlas under 80% layers populated.
- **LOW** — `under-enriched` atlases (empty naming/error_style/
  forbidden_imports/dependency_edges — re-run `/survey` to enrich) and each
  `degraded` atlas (tree-sitter fallback; re-survey once tree-sitter is
  installed), plus the no-atlases case.

## Step 3: Findings report

Synthesize a `## Findings` section (CRITICAL/HIGH/MEDIUM/LOW) followed by a
`## Summary` block quoting the script's counts verbatim: total atlases,
fresh/stale, active_fresh_pct, degraded count, and the median sizes.

## Notes

- Atlas dir: `~/.claude/cartographer/projects/<hash>/`; schema keys:
  `head_sha` (absent for non-git dirs), `surveyed_at` (ISO-8601 UTC),
  `layers`, `forbidden_imports`, `naming`, `error_style`,
  `dependency_edges`; optional `staleness`, `truncated`, `degraded`.
- To refresh a specific atlas: `cd <repo_path>` then `/survey --refresh`.
- Read-only: neither the script nor this skill modifies atlas files.
