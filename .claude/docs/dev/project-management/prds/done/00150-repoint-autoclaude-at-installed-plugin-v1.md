---
catchup: skip
design: skip
---

# Repoint the autoclaude shell front-end at the installed autopilot plugin

Source: `dev/local/discovery/00148-autopilot-fast-track-learnings.md` § 7 (the shell half; the CLI verb itself is claude-autopilot PRD 00149). Found 2026-08-26 while reading the front-end for that PRD; every path below was checked on disk that day. Nothing is a guess unless marked `(guess)`.

## Problem

`~/.config/bash/plugins/development.plugin.bash` hardcodes `$HOME/.claude/skills/run-autopilot` in eight places (lines 50 `tracon`, 54 `autopilot`, 60-61 and 81 `_autoclaude_tracon`, 271, 284 and 290 `_autopilot_fable_decide`). That path stopped existing on 2026-08-25: PRD 00144 moved the skill into the `autopilot` plugin and excluded the bash front-end on purpose ("lives in buvis dotfiles"), and `braid.ignore` keeps plugin-owned names out of `~/.claude/skills/`. The only copy of `cli/__main__.py`, `scripts/tracon.py`, `_walk_up.py`, `tracon_wrapper_alive.py` and `fablectl.py` is now `~/.claude/plugins/cache/buvis-plugins/autopilot/<version>/skills/run-autopilot/` (0.1.2 today). So `autopilot <verb>`, `autoclaude`, `tracon`, `autoclaude approve-fable` and `reject-fable` all die with `python3: can't open file …/.claude/skills/run-autopilot/…: No such file or directory`. The suite that covers this file (`test_autoclaude_fable_subcommands.sh`, now in the plugin repo) stubs `python3`, so it reported 29 PASS today with the real path absent. The last commit to the file is 2026-08-17 (`b1184872`), eight days before the extraction.

## Solution

One resolver, `_autopilot_skill_root`, and every site goes through it. It echoes `$_AUTOPILOT_SKILL_ROOT` when that is set (a dev-checkout override), else the highest-version cache directory that holds `skills/run-autopilot/cli/__main__.py` (never a pinned version: the 00140 review driver pinned 0.1.1 and was stranded when the cache rolled to 0.1.2 mid-PRD), else prints one line to stderr and returns 1. `autopilot`, `tracon` and the two internal helpers return that failure instead of a python traceback. The installed plugin is the right target because it is the code the spawned sessions load; a checkout would let the shell and the session drift.

## Requirements

### Must have

- `development.plugin.bash` gains `_autopilot_skill_root` right above `tracon()` (line 46): `[ -n "$_AUTOPILOT_SKILL_ROOT" ]` wins; else iterate `"$HOME"/.claude/plugins/cache/buvis-plugins/autopilot/*/skills/run-autopilot/cli/__main__.py`, keep the version directory names, pick the last of a numeric `sort -t. -k1,1n -k2,2n -k3,3n`, and echo `<cache>/<version>/skills/run-autopilot`; else, when no plugin is installed, fall back to the pre-extraction layout `$HOME/.claude/skills/run-autopilot` if its `cli/__main__.py` exists (a checkout linked at the old path; the moved bash suites sandbox `HOME` that way, so the cache never shadows nothing and a stale link never shadows the cache); else `printf 'autopilot: no autopilot plugin installed under %s (install it, or set _AUTOPILOT_SKILL_ROOT).\n' … >&2; return 1`. Pure stdout/stderr, no globals set.
- All eight sites use it. `autopilot()` becomes: resolve into a local; on failure return 1 (the resolver already printed); else `python3 "$_skill/cli/__main__.py" "$@"`. `tracon()` the same shape with `uv run --quiet --no-project "$_skill/scripts/tracon.py"`. `_autoclaude_tracon` and `_autopilot_fable_decide` resolve tolerantly (`2>/dev/null`, empty on failure) and substitute the local in the five `python3 ~/.claude/skills/run-autopilot/scripts/*.py` calls: the duplicate-loop guard reads a missing probe as "not alive" (tracon suite scenario 38 depends on that under a sandboxed `HOME`), the preflight falls back to the plain renderer whose `autopilot loop` hand-off refuses out loud, and `_autopilot_fable_decide`'s existing "could not be resolved" refusal (scenario 20/21) fires because `_walk_up.py` fails the same way.
- No other behavior changes: `_AUTOPILOT_LOOP` export, the pgrp guard, the tracon branch and the Fable subcommands are untouched except for the path substitution (surgical-changes rule).
- Test, fail-first per `rules/testing.md`: `hooks/tests/test_development_plugin_skill_root.py` (the existing hooks suite already hosts non-hook config tests such as `test_settings_wiring.py`, and `~/.config/bash/plugins/` is sourced by bash-it's `*.plugin.bash` glob, so a test file cannot live there). It runs `bash -c` with stubs for `cite` and `about-plugin` (as `test_autoclaude_tracon_launch.sh` lines 26-33 do), sources the plugin with `HOME` pointed at a temp dir, and pins: (1) cache holding `0.1.2` and `0.1.10` resolves to `0.1.10` (numeric, not lexical, sort); (2) a version directory without `cli/__main__.py` is skipped; (3) an empty cache exits 1 with the message on stderr and nothing on stdout; (4) `_AUTOPILOT_SKILL_ROOT=/x` echoes `/x` without touching the cache; (5) `autopilot status` with an empty cache exits 1 with that message and no `python3:` traceback text; (6) the legacy `~/.claude/skills/run-autopilot` path is used when no plugin is installed; (7) an installed plugin shadows that legacy path. Runs under the existing runner (`uv run --with pytest --with tree-sitter-language-pack pytest hooks/tests`).
- The moved bash suites still pass: `bash <plugin>/skills/run-autopilot/scripts/test_autoclaude_fable_subcommands.sh` and `test_autoclaude_tracon_launch.sh` report all checks passed after the change.
- Commit to the buvis bare repo (`git --git-dir=~/.buvis --work-tree=~`, pathspecs anchored with `:(top)`, `git diff --cached --stat` checked before the commit); no CHANGELOG (the dotfiles repo has none by rule).

### Nice to have

- Update `~/.claude/projects/-Users-bob--claude/memory/reference_autoclaude_function.md` to name the resolver and the `_AUTOPILOT_SKILL_ROOT` override once shipped.

## Implementation

### Module: skill-root-resolver
- **Location**: `~/.config/bash/plugins/development.plugin.bash`
- **Responsibility**: locate the installed plugin's `skills/run-autopilot` once; every shell entry point (`autopilot`, `tracon`, `autoclaude`, Fable subcommands) uses it.
- **Exports**: `_autopilot_skill_root`, `_AUTOPILOT_SKILL_ROOT` (env override)

### Module: resolver-test
- **Location**: `~/.claude/hooks/tests/test_development_plugin_skill_root.py`
- **Responsibility**: pin the resolver's pick order, the failure line, and that `autopilot` fails cleanly without a plugin.
- **Exports**: none (test module)

### Dependencies
- skill-root-resolver: No dependencies (foundation)
- resolver-test: Depends on [skill-root-resolver]

## Tasks

### Phase 0: Foundation
- [ ] Write `test_development_plugin_skill_root.py` and watch its five cases fail against the current file (no `_autopilot_skill_root` function; `autopilot status` prints a python `can't open file` line) - `pytest hooks/tests/test_development_plugin_skill_root.py` reports 5 failed on the old file.
- [ ] Add `_autopilot_skill_root` and route all eight sites through it - `rg -n 'skills/run-autopilot' ~/.config/bash/plugins/development.plugin.bash` prints only the resolver's own glob and echo lines (no `$HOME/.claude/skills/run-autopilot` or `~/.claude/skills/run-autopilot` literal remains); the five tests pass; both moved bash suites print `All checks passed`.

### Phase 1: Core
- [ ] Commit to buvis by explicit pathspec (depends on: Phase 0) - `git --git-dir=~/.buvis --work-tree=~ show --stat HEAD` lists exactly `.config/bash/plugins/development.plugin.bash` and `.claude/hooks/tests/test_development_plugin_skill_root.py`.

## Success Criteria

- In a fresh login shell, `autopilot status` run from `~/.claude` prints the state view (or a state-CLI error code, never `No such file or directory`), and `autoclaude approve-fable` with no argument prints its usage line.
- With the cache directory renamed away, `autopilot status` exits 1 with the single `no autopilot plugin installed` line.
- After claude-autopilot PRD 00149 ships and installs, `autopilot review-once` resolves through the same path with no further shell change.
