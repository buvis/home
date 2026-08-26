---
name: survey
description: Use to generate an on-demand codebase brief via /survey - where things live, naming conventions, error style, and extension points for the current repo. Triggers on "/survey", "survey repo", "codebase map", "where do things live".
---

# Survey

Generate a codebase brief for the current repository — a map of "where things
live" you can read before deciding where to make a change.

The brief is ephemeral. It is printed to the session and never stored, so it
always describes the repo as it is right now. Run it again whenever you need
a fresh one.

## Dependencies

- Path: `~/.claude/hooks/_lib_cartographer.py` - hard import in `scripts/run.py`
  (tree-sitter access). Missing = the skill cannot run.
- CLI: `python3`.
- Optional: tree-sitter (absent = regex fallback, and the brief says so).

## Workflow

Delegate to the survey script:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/run.py"
```

The script walks the repo tree, extracts symbols (tree-sitter, with a regex
fallback), classifies layers, naming, and error style, then prints the brief
as markdown on stdout.

## After running

Read the brief and use it. Report anything notable to the user: a degraded run
(the brief ends with a `_degraded:_` note when tree-sitter was unavailable) or
a truncated one (it ends with `*brief truncated*` when the repo exceeds the
5KB budget).

## Notes

- Layer detection is heuristic.
- The brief caps files-sampled at 50 per layer and its own size at 5KB; a large
  repo produces a partial brief with the truncation footer.
- Nothing is written to disk. There is no atlas, no staleness check, and no
  cached copy to refresh (PRD 00138).
