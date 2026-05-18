---
name: audit-atlas
description: Use when auditing the health of Cartographer atlases across all tracked repos. Reports fresh-atlas coverage, staleness distribution, atlas size, and layer population. Triggers on "audit atlas", "atlas health", "cartographer coverage".
---

# Audit Atlas

Enumerate all atlas files under `~/.claude/cartographer/projects/` and report on coverage, freshness, and content quality.

## Step 1: Discover projects

List all directories under `~/.claude/cartographer/projects/`. For each, check if `atlas.json` exists.

Also read `~/.claude/instincts/projects.json` if present (list of `{"hash": str, "path": str, "last_active": str}` entries). Cross-reference: any project with a `last_active` within the last 30 days is "actively-edited".

If neither the projects dir nor any atlas files exist: report `LOW: no atlases found` and stop.

## Step 2: Freshness analysis

For each `atlas.json` found:
- Parse `generated_at` (ISO-8601 UTC).
- Compute age in hours: `now - generated_at`.
- Check for sibling `staleness.flag` — if present, atlas is explicitly marked stale regardless of age.
- Classify:
  - Fresh: age < 24h AND no staleness.flag
  - Stale: staleness.flag present OR age ≥ 24h but < 168h (7 days)
  - Expired: age ≥ 168h

Compute:
- `fresh_pct` = 100 × (fresh count) / (total with atlas)
- `active_fresh_pct` = 100 × (actively-edited repos with fresh atlas) / (actively-edited repos)

Report:

| Hash (short) | Age | Status | Staleness flag |
|---|---|---|---|
| `abc123` | 2h | Fresh | No |
| `def456` | 48h | Stale | Yes |

**HIGH** if `active_fresh_pct < 80%` (target per PRD: >80% of actively-edited repos have fresh atlas).
**MEDIUM** if any atlas is Expired.

## Step 3: Atlas size distribution

For each `atlas.json` and sibling `atlas.md`:
- Record `atlas.json` byte size.
- Record `atlas.md` byte size; flag if > 5120 bytes (exceeds 5KB budget).

Report:

| Hash (short) | atlas.json (bytes) | atlas.md (bytes) | Over budget |
|---|---|---|---|

**HIGH** if any `atlas.md` exceeds 5120 bytes (the 5KB budget was not enforced at write time).

## Step 4: Layer population

For each atlas, check `atlas.json.layers`:
- Count total layers.
- Count layers with `files` list non-empty.
- `layers_populated_pct` = 100 × (layers with files) / (total layers).

Also check `symbols`, `naming_conventions`, `error_handling`, `forbidden_imports`, `dependency_edges`: if any are empty lists or empty dicts when the repo has `.py` files, note as degraded.

**MEDIUM** if `layers_populated_pct < 80%` for any atlas.
**LOW** if all five analysis fields are empty (atlas was generated but never enriched).

## Step 5: Findings report

Synthesize:

```
## Findings

### CRITICAL
(atlas contract violations — e.g. atlas.json missing required keys)

### HIGH
- {active_fresh_pct X% < 80% — N actively-edited repos lack a fresh atlas}
- {atlas.md for <hash> is NNN bytes — exceeds 5KB budget}

### MEDIUM
- {atlas for <hash> is Expired (Xd old)}
- {layers_populated_pct X% < 80% for <hash>}

### LOW
- {atlas for <hash> has no symbols/naming/error_handling — re-run /survey to enrich}

## Summary

- Total atlases: N
- Fresh / Stale / Expired: N / N / N
- Active repos with fresh atlas: X%
- Median atlas.json size: N bytes
- Median atlas.md size: N bytes
```

## Notes

- Atlas dir: `~/.claude/cartographer/projects/<hash>/`.
- Atlas schema: `generated_at` (ISO-8601 UTC), `project_hash`, `layers`, `symbols`, `naming_conventions`, `error_handling`, `forbidden_imports`, `dependency_edges`.
- Staleness flag: `staleness.flag` sibling — presence means "atlas is stale, re-run /survey".
- To refresh a specific atlas: `cd <repo_path> && /survey --refresh`.
- This skill is read-only; it never modifies atlas files.
