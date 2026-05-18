---
name: survey
description: Use when building or refreshing the Cartographer per-repo atlas — a small codebase map of layers, naming conventions, error style, and extension points. Triggers on "/survey", "survey repo", "refresh atlas", "rebuild codebase map".
---

# Survey

Build or refresh the Cartographer **atlas** for the current repository — a
proactive map of "where things live" that downstream phases (Recon Gate,
Architect, Conformance) consult before deciding where to make a change.

The atlas lives at `~/.claude/cartographer/projects/<hash>/`:

- `atlas.json` — machine-readable summary (layers, naming, error style,
  dependency edges, forbidden imports, staleness config).
- `atlas.md` — human-readable 2-5KB summary.
- `staleness.flag` — empty marker; present means the atlas has drifted.

## Arguments

- *(no argument)* — Survey if no atlas exists. No-op if a fresh atlas exists.
  Rebuild if `staleness.flag` is set.
- `--if-missing` — Run a survey only when `atlas.json` is absent or
  `staleness.flag` is present; otherwise a logged no-op. Used by `/catchup`.
- `--refresh` — Force a full re-survey, bypassing the staleness check. Clears
  `staleness.flag` on success. Preserves any `[manual]` override block in
  `atlas.json` byte-for-byte; rewrites every other field.

## Workflow

Delegate to the survey script, forwarding any flag verbatim:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/run.py"
```

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/run.py" --if-missing
```

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/run.py" --refresh
```

The script resolves the project hash via `_lib_cartographer`, walks the repo
tree, extracts symbols (tree-sitter, with a regex fallback marked `degraded`),
classifies layers, naming, and error style, then writes `atlas.json` and
`atlas.md` atomically.

## After running

Report the status line the script emits — whether it surveyed, refreshed, or
skipped, plus the atlas location and size. If the script reports a degraded
run (tree-sitter unavailable) or a truncated atlas, surface that to the user.

## Notes

- Atlas path: `~/.claude/cartographer/projects/<hash>/`.
- Layer detection is heuristic; a `[manual]` block in `atlas.json` lets the
  user override it and survives re-survey.
- Survey caps files-sampled at 50 per layer; large repos produce a partial
  atlas with `truncated: true`.
- On a non-git directory the atlas omits `head_sha` and staleness checks skip.
