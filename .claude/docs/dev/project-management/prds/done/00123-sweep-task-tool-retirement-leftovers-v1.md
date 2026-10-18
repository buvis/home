---
prd: 00123
title: Sweep the task-tool retirement leftovers and clear the red matcher test
status: backlog
created: 2026-08-17
design: skip
catchup: skip
---

# Sweep the task-tool retirement leftovers and clear the red matcher test

## Problem

PRD 00120 migrated autopilot task tracking to `statectl` and removed
`CLAUDE_CODE_ENABLE_TODO_TOOLS`. Its review deferred four items as out of its
structural scope. All four are still true at HEAD, verified on 2026-08-17, and
three of them are one-file edits. The fourth is a test that has been failing in
the suite for long enough that "1 failed of 2363" now reads as normal.

Source: `dev/local/autopilot/deferred/202608162223-deferred.json`.

1. ~~**A red test in the hooks suite.**~~ **RESOLVED 2026-08-17**, during the agoge
   walkthrough (finding 25). The direction in this PRD's first draft was **backwards**:
   `a2db6e565` (2026-08-03) deliberately dropped `Grep|Glob` from `settings.json`, so
   `dispatch.py:81` was the stale side, not the settings file. Fixed by removing the two
   dead tokens from `ROUTES` with a comment naming upstream bug #52004, plus the same
   removal in `hooks/tests/fixtures/settings-preswap-hooks.json` — the frozen pre-swap
   wiring three `test_dispatch.py` tests compare `ROUTES` against, which went red the
   moment `ROUTES` changed. Whole hooks suite: **941 passed, 0 failed** (was 1 failed
   for 14 days). No `settings.json` edit was needed after all.

2. **Stale nested-metadata paths survive in three files.** PRD 00120's rework task
   9 fixed this pattern in `phase-review.md`, `state-schema.md` and
   `plan-tasks/SKILL.md`, but it is still live in:
   - `run-autopilot/references/model-ladder.md:115-116` (`task.metadata.qwen_eligible`,
     `task.metadata.qwen_excluded_reason`) and `:306` (`metadata.model`)
   - `work/scripts/test_work_routing_ladder_fence.py` (lines 117, 170-171, 184-185, 198)
   - `work/scripts/test_work_routing.py` (lines 742, 748)

   **These three change in lockstep or not at all.** Lines 115-116 are fence
   pseudocode that `test_work_routing_ladder_fence.py` parses **live** with a regex
   extractor, so the doc, the extractor and its tests are one coupled change. That
   coupling is why 00120 deferred it, and it is the whole risk in this item.

3. **Retired tool names sit unlabelled in a test fixture.**
   `hooks/tests/test_dispatch.py` carries 8 literal retired-task-tool strings. They
   are matcher-anchoring negative fixtures for hooks-dispatch regex routing, not
   instructions, so the retirement bar 00120 set is met. They are simply not
   labelled as deliberately-historical, so the next premise sweep re-raises them.
   One comment ends that loop.

## Requirements

- **R1.** ~~The hooks suite has no failing test~~ — **met 2026-08-17**, see item 1.
- **R2.** No file states a task field at a nested path the schema no longer uses.
- **R3.** The fence pseudocode, its regex extractor and its tests agree after the
  change — proven by the fence tests passing on the new wording.
- **R4.** A retired tool name that survives on purpose says so in place.

## Phases

### Phase 1 — the red test (R1) — **DONE 2026-08-17**

1. ~~Apply the decided direction and run the suite.~~ Done in the walkthrough; see item 1.
   The run command for later phases, since the language pack is required and without it
   ~30 unrelated tests fail misleadingly:
   `uv run --with pytest --with tree-sitter-language-pack python -m pytest hooks/tests/ -q`

### Phase 2 — the coupled fence sweep (R2, R3)

2. Change `model-ladder.md:115-116` and `:306` to the flat field names, then the
   regex extractor in `test_work_routing_ladder_fence.py` that parses those lines,
   then that file's own expectations and `test_work_routing.py`'s two prose
   references — in one commit, because the extractor reads the doc at runtime.
3. Run the work-skill script suite. A green run with an extractor that silently
   matches nothing would pass vacuously, so confirm the fence tests still parse a
   non-zero number of clauses from the doc.

### Phase 3 — the label (R4)

4. One comment above the fixture block in `hooks/tests/test_dispatch.py` naming
   the strings as deliberately-retained historical matcher anchors, so the next
   premise sweep stops at the comment.

*Acceptance:* hooks suite green; work-skill script suite green with a
non-vacuous fence parse; `rg 'task\.metadata\.'` over `skills/` returns only
intentional historical references.

## Out of scope

- `check_build_overhead.py`'s dead `completed_tasks` counter and PRD 00120's own
  Phase-1 acceptance wording. Both belong to PRD 00093, which owns that metric,
  and are recorded there.
- The `work/SKILL.md:537` empty-description dispatch question. It is a design
  decision for the operator, recorded on PRD 00119, which owns that file.
