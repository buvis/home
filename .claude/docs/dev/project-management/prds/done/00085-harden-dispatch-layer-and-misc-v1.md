# 00085 - Harden the dispatch layer and close audit leftovers

## Problem

The use-* dispatch skills and several small skills carry known uncovered failure branches and audit leftovers (2026-07-19 authoring audit). The shared dispatch contract got an unattended fork today; its error taxonomy is still thin.

## Goal

Dispatched CLI failures are recognized, named, and recovered (or failed loud) per a shared taxonomy; audit leftovers are closed.

## Requirements

- R1 dispatch-contract (use-codex/references/dispatch-contract.md, shared by all four use-* skills): add an error taxonomy with per-class behavior - auth expired (re-auth hint, FAILED), quota/rate exhausted (distinguish from auth; note reset time when the CLI reports it), CLI died mid-run (partial output salvage rule), output file empty despite rc 0 (treat as FAILED, quote stderr). Move the codex exit-4 salvage rule (now in review-work-completion) into the contract so all callers inherit it.
- R2 use-sonnet: usage-limit-banner branch (claude -p returns the limit banner; detect, report reset time, FAILED - mirror detect_usage_limit.py's markers). use-qwen: server-died-after-preflight branch (probe passed, dispatch hangs/refuses: kill, mark FAILED, name the llama.cpp restart command).
- R3 review-fanout.workflow.js: type-check `changed_files` (string input currently iterates characters and silently under-arms the security dimension); reject non-array with a clear error.
- R4 Small closures: spike deletion gets an owner (purge-devlocal prompts on spikes/ entries whose PRD is in done/); research model:sonnet pin gets its cost rationale stated inline or is dropped; catchup-ecc pagination gets a date-carrying cursor (store SHA + date; use ?since=); brief-portfolio maintenance commands (:108-120) switch to ${CLAUDE_SKILL_DIR} and `open` is marked attended-only; design-solution's subagent-dispatch reference migrates off deprecated TaskOutput to task-notification + Read.
- R5 instincts distiller: analyze-instincts.py trigger extraction classifies errors (tool + error class) instead of embedding truncated raw payload dicts; delete-and-regenerate path for existing junk documented. (The three junk instinct files were deleted 2026-07-19.) Re-enable the observe_tool.py registration in settings.json (deregistered 2026-07-19, walkthrough decision 8) TOGETHER with the fixed distiller, and give the observer per-process project-identity caching (no git spawn per tool call), registry pruning tied to INSTINCTS_RETENTION_DAYS, and the CLAUDE_NESTED skip (already in is_automated_session).
- R6 pre-existing test debt in hooks/tests: test_survey placeholder contract drifted from survey/scripts/run.py (red today); register the custom unit/integration pytest marks that warn on every run.

## Acceptance

- Each use-* skill answers "what do I do when the CLI fails this way" for all four R1 classes without consulting memory.
- review-fanout tests cover the string-input rejection (extend the .mjs suite).
- rg finds no TaskOutput reference in design-solution's references.
- A synthetic error observation run through the repaired distiller produces a trigger a human can read and match.

## Out of scope

- Plugin repos (their own PRDs). Autopilot core (00084).

## Notes

Sources: audit report F3 findings + omitted-edges, F1 review-fanout note, instincts decision (walkthrough packet 9).

## Status 2026-07-20 (COMPLETE — R1-R6)

Commits: 4968c203 (R1-R4), d0e4a892 (R5 distiller), bf4acfe2 (R5 observe_tool
re-enable + cwd cache + registry pruning), 3116868d (R6). R5's user decision
(2026-07-20): "Finish R5 + continue" — the observe_tool hook was re-registered
in settings.json (matcher `Bash|Edit|Write|MultiEdit`) with a cross-process
cwd-cache killing the per-call git spawn; live smoke test rc=0. R6: test_survey
naming drift fixed + hooks/tests/pytest.ini registers unit/integration marks
(+ --strict-markers). All new/changed tests green (survey 9/9, observe_tool
28/28, analyze-instincts 7/7, review-fanout args 15/15).

## Status 2026-07-20 (superseded — R1-R4 done, R5 partial, R6 open)

**Committed 4968c203 (R1-R4):** R1 dispatch-contract error taxonomy + codex
exit-4 salvage moved in. R2 use-sonnet usage-limit branch + use-qwen
server-died-after-preflight branch. R3 review-fanout `changed_files` non-array
rejection (+args.test.mjs, 15/15). R4 all five closures (purge-devlocal
consumed-spike prompt; research sonnet cost rationale; catchup-ecc SHA+date
cursor via `?since=`; brief-portfolio `${CLAUDE_SKILL_DIR}` + `open`
attended-only; design-solution off deprecated TaskOutput → task-notification +
Read).

**Committed d0e4a892 (R5 distiller):** analyze-instincts.py `_classify_error`
replaces the raw-output-embedding `_normalize_error`; error-fix triggers now
name a stable class; delete-and-regenerate path documented. +2 tests (7/7).

**OPEN — R5 remainder (carved out for a decision):**
- observe_tool.py: project-identity caching to drop the per-tool-call `git`
  spawn, registry pruning tied to `INSTINCTS_RETENTION_DAYS`. (CLAUDE_NESTED
  skip already present in `is_automated_session`, line 38 — no change needed.)
- **settings.json: re-register observe_tool.py as a PostToolUse hook** —
  re-enables a per-tool-call GLOBAL hook deliberately disabled 2026-07-19
  (walkthrough decision 8). Standing behavior change in the user's live
  sessions; sensitive file. **Ambiguity:** the "per-process caching" spec saves
  nothing as literally written (each hook run is a fresh process) — the only
  interpretation that achieves "no git spawn per tool call" is a CROSS-process
  cwd-keyed cache (e.g. a small cache file, or reading `cwd` from the hook
  payload). Awaiting the user's steer on re-registration + caching approach.

**OPEN — R6 (test debt):** hooks/tests test_survey placeholder drifted from
survey/scripts/run.py (red today); register the custom unit/integration pytest
marks that warn on every run.

**Broader finding (out of 00085 scope, flag for a follow-up PRD):** TaskOutput
is now harness-DEPRECATED, but the shared `use-codex/references/dispatch-contract.md`
and `work/references/subagent-dispatch.md` still prescribe it as the canonical
wait primitive. R4.5 migrated only design-solution; the shared contract + all
use-* skills that inherit it need the same migration.
