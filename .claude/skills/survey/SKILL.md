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

- *(no argument)* — No-op if `atlas.json` exists and `staleness.flag` is absent
  (prints a skip reason). Runs the survey otherwise (atlas missing or stale).
- `--if-missing` — Survey only when `atlas.json` is absent. No-op when an atlas
  already exists, even if `staleness.flag` is present (a stale atlas is left
  for the bare invocation or `--refresh` to rebuild). Used by `/catchup`, which
  only needs an atlas to exist.
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
