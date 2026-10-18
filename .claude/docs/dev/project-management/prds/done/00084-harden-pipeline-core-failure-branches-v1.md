# 00084 - Harden pipeline-core failure branches

## Problem

The 2026-07-19 authoring audit mapped the autopilot core's uncovered failure branches. Each is a real stop-the-batch or silent-wrong-result path with no documented behavior; agents improvise when they hit one.

## Goal

Every named branch has a documented, fail-loud behavior a to-the-letter agent can execute.

## Requirements

- R1 run-autopilot: statectl.py itself failing (lock contention, python error) gets a handler (retry once, then stall with the raw error in the report); two concurrent autoclaude loops on one repo are detected via a lockfile (second loop refuses to start, names the first's PID); `git rev-parse HEAD` failing at work_start_sha capture (empty repo, detached head) gets a branch.
- R2 work: a commit rejected by validate_commit_msg or warden gets a repair branch (read the deny reason, fix the message/command, retry once, then ESCALATE); step 7 defines behavior when the repo has no documented verification commands (state the improvised command set in the phase report); remove or honest-skip the third dead superpowers gate at :384 (verification-before-completion) plus the matching `superpowers:*` Dependencies mention at :26; refresh references/attempt-logging.md schema with the stamps added 2026-07-19 (verification, red_check, review) plus self_deslop.
- R3 plan-tasks: a PRD missing Functional Decomposition / Dependency Graph sections gets a stated fallback (derive from requirements, note the derivation) instead of undefined behavior; TaskCreate failing mid-plan rolls back cleanly (delete created tasks, stall with cause); re-derive the 55K/150K token constants on Fable 5 transcripts per the skill's own model-change mandate (blocked until a few Fable batches exist).
- R4 review-work-completion: consolidate-findings.sh nonzero or warden-denied gets a branch (fall back to model-side consolidation, note it); two PRDs in wip/ on a standalone run is detected and refused (name both, ask which - or in unattended mode stall).
- R5 design-solution: reviewers get a minimum-engagement check (a review under N substantive findings or lacking file-level references is re-dispatched once with a sharper prompt, then marked WEAK in the report) mirroring review-with-doubt's "fewer than 3 doubts = look harder".
- R6 create-prd: document the v1→v2 update path (when to bump the version suffix vs allocate a new number) and a concurrent-creation collision rule (re-scan after write, renumber on collision).

## Acceptance

- Each branch above has a numbered step in its skill with an observable outcome (stamp, stall_reason, report line) - no "should" language.
- A dry-read of each edited skill by a fresh session (no memory) can answer "what do I do when X fails" for every X above.

## Out of scope

- Dispatch-layer CLI branches (PRD 00085).
- Plugin skills.

## Notes

Sources: audit report F1/F2 omitted-edges. R3's constant re-derivation depends on Fable 5 batch transcripts existing; sequence it last.

## Status 2026-07-20 (complete; committed 89b44339)

R1-R6 landed. R1: statectl-fail handler + work_start_sha empty-tree fallback +
plain-path concurrent-loop guard (names incumbent pid; guard script prints it,
+test). R2: commit-rejection repair branch, step-7 improvise-and-report, dead
`superpowers:verification-before-completion` gate/dep removed (+ its stale
phase-build row), attempt-logging.md refreshed (verification/red_check/review/
self_deslop). R3: FD/DG derivation fallback + TaskCreate rollback (`taskcreate_failed`).
R4: consolidate-findings.sh model-side fallback + two-PRDs-in-wip refusal. R5:
reviewer minimum-engagement check (WEAK). R6: v1->v2 path + collision rule.

**R3 third bullet (re-derive 55K/150K on Fable 5) DEFERRED — BLOCKED:** the
build phase still runs on `opus-4.8` (`autoclaude` hardcodes
`_AUTOPILOT_MODEL_BUILD=claude-opus-4-8`), which is exactly what the current
55K was measured against, so the constants are correct as-is. The re-derivation
mandate is documented in plan-tasks `### Estimator caveats` ("Pending
re-derivation (PRD 00084 R3, BLOCKED)"); do it on real Fable build transcripts
IF/when the build phase moves to Fable. Durable home = that skill note; no open
defect ships.
