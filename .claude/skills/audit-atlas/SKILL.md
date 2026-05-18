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
- Parse `surveyed_at` (ISO-8601 UTC).
- Compute age in days: `now - surveyed_at`.
- Check for a sibling `staleness.flag` file — the `cartographer-stop` Stop hook touches it when the atlas drifts past the staleness threshold (50 commits OR 14 days, whichever first; per-repo overrides read from `atlas.json.staleness`).
- Classify (the staleness threshold, per PRD, is 50 commits OR 14 days):
  - **Fresh**: no `staleness.flag` AND `surveyed_at` age < 14 days
  - **Stale**: `staleness.flag` present, OR `surveyed_at` age ≥ 14 days

`staleness.flag` is the authoritative signal — the Stop hook computes the full 50-commit / 14-day check (including per-repo overrides) and the flag encodes its verdict. The 14-day age check here is a backstop for atlases whose repos have not triggered the Stop hook recently.

Compute:
- `fresh_pct` = 100 × (fresh count) / (total with atlas)
- `active_fresh_pct` = 100 × (actively-edited repos with a fresh atlas) / (actively-edited repos)

Report:

| Hash (short) | Surveyed age | Status | Staleness flag |
|---|---|---|---|
| `abc123` | 2d | Fresh | No |
| `def456` | 20d | Stale | Yes |

**HIGH** if `active_fresh_pct < 80%` (target per PRD: >80% of actively-edited repos have a fresh atlas).

## Step 3: Atlas size distribution

For each `atlas.json` and sibling `atlas.md`:
- Record `atlas.json` byte size.
- Record `atlas.md` byte size; flag if > 5120 bytes (exceeds 5KB budget).

Report:

| Hash (short) | atlas.json (bytes) | atlas.md (bytes) | Over budget |
|---|---|---|---|

**HIGH** if any `atlas.md` exceeds 5120 bytes (the 5KB budget was not enforced at write time).

## Step 4: Layer population and degradation

For each atlas, check `atlas.json.layers`:
- Count total layers.
- Count layers with a non-empty `files` list.
- `layers_populated_pct` = 100 × (layers with files) / (total layers).

Also check the enrichment fields `naming`, `error_style`, `forbidden_imports`, `dependency_edges`: if these are empty when the repo has source files, note as under-enriched.

Check the `degraded` flag: an atlas with `degraded: true` was generated with the tree-sitter regex fallback (tree-sitter unavailable). Count these.

**MEDIUM** if `layers_populated_pct < 80%` for any atlas.
**LOW** if `naming`, `error_style`, `forbidden_imports`, and `dependency_edges` are all empty (atlas was generated but never enriched).
**LOW** for each `degraded: true` atlas (re-run `/survey` once tree-sitter is installed).

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
- {atlas for <hash> is Stale (Xd old / staleness.flag set)}
- {layers_populated_pct X% < 80% for <hash>}

### LOW
- {atlas for <hash> has empty naming/error_style/forbidden_imports/dependency_edges — re-run /survey to enrich}
- {atlas for <hash> is degraded (tree-sitter fallback) — install tree-sitter and re-survey}

## Summary

- Total atlases: N
- Fresh / Stale: N / N
- Active repos with fresh atlas: X%
- Degraded (tree-sitter fallback): N
- Median atlas.json size: N bytes
- Median atlas.md size: N bytes
```

## Notes

- Atlas dir: `~/.claude/cartographer/projects/<hash>/`.
- Atlas schema (`atlas.json`): required keys `head_sha`, `surveyed_at` (ISO-8601 UTC), `layers`, `forbidden_imports`, `naming`, `error_style`, `dependency_edges`; optional `staleness`, `[manual]`, `truncated`, `degraded`. (`head_sha` is omitted for non-git directories.)
- Staleness flag: `staleness.flag` sibling file — presence means "atlas is stale, re-run /survey". Maintained by the `cartographer-stop` Stop hook.
- To refresh a specific atlas: `cd <repo_path> && /survey --refresh`.
- This skill is read-only; it never modifies atlas files.
