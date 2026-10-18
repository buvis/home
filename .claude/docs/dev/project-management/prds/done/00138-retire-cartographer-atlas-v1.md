---
design: skip
catchup: skip
---

# Retire The Cartographer Atlas, Make Survey Ephemeral

> Source: hold-triage session 2026-08-23, operator decision "ephemeral map" (memory
> `project_hold_triage_2026_08_23`); cancels followed the same day (00029, 00114,
> 00135 all in `cancelled/`). Every file:line below was recon-verified 2026-08-23 in
> a live work-tree - **re-verify each site at HEAD before editing.**

> **Path drift found 2026-08-26 (backlog sanity check). Substance intact, three
> locations moved. Phase 0 must correct these before touching anything:**
>
> 1. **`~/.claude/cartographer/` NO LONGER EXISTS.** The tree moved to
>    `~/.local/share/agents/cartographer/` (commit `429bd128`, "move cross-agent state
>    to ~/.local/share/agents"). Verified there: `audit.jsonl` live at 47MB (mtime
>    2026-08-26 08:45) and `projects/` holding exactly **7** atlas dirs - matching R5's
>    count, so R5's reasoning holds and only its paths are stale. Consumers are ALREADY
>    repointed: `skills/audit-echo/scripts/report.py:19` reads
>    `~/.local/share/agents/cartographer/audit.jsonl`. R5's rename target becomes
>    `~/.local/share/agents/cartographer/projects.retired-<YYYY-MM-DD>/`.
> 2. **R7's `skills/design-solution/SKILL.md` is no longer host-side.** It shipped into
>    the autopilot plugin repo (`claude-autopilot/skills/design-solution`, released in
>    v0.1.2). Editing it is now a change to a different repo's released plugin, not a
>    local prose update - rescope or drop that half of R7. The brush surfaces in R7 are
>    unaffected and still host-side.
> 3. **R6's `~/.claude/skills-library/` does not exist.** The documented dormant-skill
>    convention is `~/.claude/.archive/skills/` (present, 4 entries: audit-recon,
>    design-agent-loop, explain-interactively, sort-agent-setup) per AGENTS.md
>    § Conventions. Retarget `audit-atlas` there.
>
> Everything else verified present at HEAD: `hooks/cartographer-{recon-brief,stop,echo}.py`,
> `hooks/dispatch.py`, `hooks/tests/test_{dispatch,handler_run_parity}.py`,
> `skills/{survey,audit-atlas,audit-echo,brush}`, `~/.local/bin/atlas_sweep.py`.
>
> **Related inconsistency, not this PRD's to fix but worth knowing:** while this PRD sits
> in `backlog/`, the atlas is neither retired nor maintained - `skills/audit-atlas` is
> still installed and still carries the two schema-guard bugs from `cancelled/00135`,
> which was cancelled *because* this retirement was expected to land. Either this ships
> or 00135 returns; leaving both is the incoherent option.

## Overview

### Problem Statement

Cartographer's stored atlas failed adoption: 7 atlases exist under
`~/.claude/cartographer/projects/`, none refreshed since 2026-08-01, and all three
payoff phases are cancelled (architect and forecast 2026-07-07, conformance
2026-08-23). The only runtime reader of atlas data is cartographer's own
recon-brief injector - loupe reads nothing (verified: one docstring mention,
`plugins/cache/buvis-plugins/loupe/0.2.1/hooks/loupe/project.py:3`). The map is
useful at generation time; storage adds only staleness and its upkeep machinery
(nudge, flags, audit skill, sweep script). Survey becomes generate-and-hand-over;
everything storage-dependent retires. Echo (duplicate detection) is alive and
atlas-independent; it must survive untouched.

### Success Metrics / Requirements

- **R1**: `/survey` generates its brief with zero writes under
  `~/.claude/cartographer/` (deliver to the session and/or the surveyed repo's
  `dev/local/tmp/`); `skills/survey/SKILL.md` rewritten accordingly and passing
  the create-skill validator.
- **R2**: the recon-brief hook is gone: `hooks/cartographer-recon-brief.py`
  removed together with `hooks/tests/test_cartographer_recon_brief.py` (which
  loads it by absolute path), and its UserPromptSubmit registration dropped
  from `settings.json` - the whole `UserPromptSubmit` block at `:148-158`,
  since recon-brief is its only entry (no test binds that event).
  Without this, every repo's first daily prompt would nag "run /survey" forever
  once atlases are gone (`NO_ATLAS_LINE`, recon-brief `:20`/`:51`).
- **R3**: `hooks/cartographer-stop.py` retires whole - both halves are
  storage-dependent (PRD 00049 nudge `:25-53` + call `:64`; staleness-flag writer
  `:56-123`): file removed, `dispatch.py` ROUTES Stop entry (`:154-161` at HEAD
  `477560c9`) removed, `hooks/tests/test_cartographer_stop.py` removed, and
  every census that pins the route updated in lockstep:
  `hooks/tests/test_dispatch.py` (`len(actual) == 16` -> 15 at `:1178`, the
  `cartographer-stop` key in `_EXPECTED_ROUTE_KIND` `:1159`,
  `test_routing_stop_runs_all_six_in_order` `:1033-1045` -> five), the frozen
  fixture `hooks/tests/fixtures/settings-preswap-hooks.json:100`, and
  `hooks/tests/test_handler_run_parity.py` (`_HANDLERS` entry `:323-325` and
  its "13 handlers" prose). `hooks/tests/test_settings_wiring.py:135` needs NO
  edit: it is `assertGreaterEqual`, and the Stop sum falls 55 -> 50 under the
  declared 60s timeout.
- **R4**: echo unharmed: `hooks/cartographer-echo.py` duplicate detection and its
  PreToolUse routes stay; only the dead `survey-edits` stamping block
  (`:829-837`, existed solely for the stop nudge) is removed. Shared libs
  (`hooks/_lib_cartographer.py`, `hooks/_cartographer_identity.py`) STAY -
  after R2/R3 their live importers are echo (`cartographer-echo.py:33`) and
  `skills/survey/scripts/run.py:14`; audit-echo hardcodes the audit path
  (`skills/audit-echo/scripts/report.py:19`) and imports neither. Phase 0
  confirms the import graph.
- **R5**: `~/.claude/cartographer/projects/` retired by ONE rename to the
  dated sibling `~/.claude/cartographer/projects.retired-<YYYY-MM-DD>/`
  (decided 2026-08-25: no `.trash` convention exists outside `dev/local`, and
  `.trash/` writes are hook-blocked there); the sibling is deleted by hand at
  the next GC pass. Atlases are regenerable by `/survey`. **`~/.claude/cartographer/audit.jsonl` is PRESERVED** -
  it is audit-echo's only event source (`skills/audit-echo/scripts/report.py:19`);
  deletion is scoped to `projects/` only, never the tree.
- **R6**: `skills/audit-atlas/` moves to `~/.claude/skills-library/` (dormant
  convention, reactivation is a `mv` back); `~/.local/bin/atlas_sweep.py` retired
  with it.
- **R7**: prose consumers updated: `skills/design-solution/SKILL.md`
  (`:31,40-41,81`, atlas is an optional input there), `skills/brush/SKILL.md`
  phase 6 (`:28,76`) plus its `README.md:12,24` and
  `references/report-template.md:13,43` - survey-refresh becomes
  survey-on-demand or is dropped.
- Hooks suite shows no failures beyond the Phase 0 recorded baseline, before
  and after (`uv run --with pytest --with tree-sitter-language-pack`, per memory
  `project_hooks_tests_need_tree_sitter`). At HEAD `477560c9` the baseline is 8
  failures, all `hooks/tests/test_cartographer_echo.py::test_search_candidates_*`;
  they build their own `tmp_path` fixtures and never read the atlas, so R5
  cannot change them - Phase 0 owns them (fix, or quarantine with a named
  reason) so the baseline is zero before Phase 1 starts. `audit-echo` still
  renders from `audit.jsonl` afterward.

### Non-Goals

- No change to echo's detection, thresholds, stopwords, or namespace.
- No rotation or pruning of the 42.7MB `audit.jsonl` (surface separately if it
  bothers anyone).
- No replacement freshness machinery of any kind.

## Implementation Phases

### Phase 0: Re-verify the surface
**Tasks**:
- [ ] Re-verify every file:line above at HEAD; confirm via imports that
  `_lib_cartographer.py` / `_cartographer_identity.py` are needed by echo or
  audit-echo (if provably unused after R2/R3, they may retire too - record the
  call either way). Run the hooks suite and fix or quarantine the 8 pre-existing
  `test_search_candidates_*` failures (echo tests; echo survives this PRD) so
  the baseline is green. Acceptance: site table in the task report; baseline
  counts recorded; the 8 either pass or are skipped with a `reason=` naming
  the environmental cause and a follow-up owner.

### Phase 1: Hook retirement (R2, R3, R4)
**Tasks**:
- [ ] Remove recon-brief (file + settings.json registration), retire
  cartographer-stop (file + ROUTES + tests + wiring cross-check), delete echo's
  dead stamping block. Acceptance: hooks suite at the Phase 0 baseline; no test references the
  removed modules; the census, fixture and parity edits listed in R3 landed;
  echo tests untouched and passing. Note: `settings.json` edits
  pass through aegis `protect_config`; satisfy its gate, do not bypass it.

### Phase 2: Storage and skill retirement (R5, R6)
**Tasks**:
- [ ] Trash-first removal of `cartographer/projects/` (7 atlas dirs), preserving
  `audit.jsonl`; `mv skills/audit-atlas ~/.claude/skills-library/`; retire
  `atlas_sweep.py`. Acceptance: `audit-echo` report renders afterward;
  `cartographer/` contains `audit.jsonl`, `scripts/` and the dated
  `projects.retired-*` sibling, and no `projects/`.

### Phase 3: Survey rewrite and docs (R1, R7)
**Tasks**:
- [ ] Rewrite `skills/survey/SKILL.md` + `scripts/run.py` for ephemeral output,
  retargeting `hooks/tests/test_survey.py:98-99` and
  `skills/survey/scripts/test_survey.py` (both pin the atlas write); update
  design-solution (`:31,40-41,81`) and brush surfaces (`SKILL.md:28,76-77`,
  `README.md:12,24,79`, `references/report-template.md:13,43`). Acceptance: create-skill validator
  clean on every edited SKILL.md; a survey run against a fixture repo leaves
  `~/.claude/cartographer/` unmodified (mtime check); no live reference to
  `cartographer/projects/` survives outside `cancelled/` PRDs and history.

**Exit Criteria**: all R1-R7; suites green; echo end-to-end intact.

## Test Strategy

Hooks suite green at every phase boundary; a regression test pinning that the
Stop dispatch table carries no cartographer route; echo's existing tests as the
R4 guard; the Phase 3 no-write mtime check binds R1.

## Risks

- **Deleting echo's telemetry by over-scoping R5**: mitigated by naming
  `audit.jsonl` preserved in the requirement and asserting audit-echo renders in
  Phase 2 acceptance.
- **Live HOME work-tree**: the user edits concurrently; diff staged changes
  before every commit and stage by explicit path (buvis rules; hooks and skills
  here are buvis-tracked).
- **Site drift between recon and drain**: every line number re-verified in
  Phase 0 before any edit.
