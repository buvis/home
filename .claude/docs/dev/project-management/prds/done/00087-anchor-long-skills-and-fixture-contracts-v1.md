# 00087 - Re-anchor long skills and fixture their contracts

## Problem

Within-session compaction can drop an active skill's text mid-procedure (work is 600+ lines; run-autopilot and review-work-completion are long too) - the agent then drifts off-contract with no re-anchor mechanism. Separately, the machine-parsed artifact contracts (state.json transitions, create-prd frontmatter, review verdict files, work FILES_TOUCHED footers) have no regression net: the create-prd/parser drift class was hand-caught in the 2026-07-19 morning audit and nothing prevents recurrence.

## Goal

A compacted session re-anchors to its skill contract; paired contracts break tests, not batches.

## Requirements

- R1 Contract card: work, run-autopilot, and review-work-completion write a compact contract card (current step, active invariants, next gate) at each gate transition - into state.json via statectl where that world exists, a scratch card file for interactive runs. A SessionStart hook matched to `compact` only (the slot ponytail's activate hook proves out) re-injects the card after compaction. Startup/resume/clear stay un-matched to avoid standing token cost.
- R2 Golden record-replay: a fixtures directory holding one known-good artifact per machine-parsed contract; a test per pair asserts the producing skill's own validator AND the consuming parser both accept it (create-prd frontmatter vs run-autopilot parser vs review-prd-backlog field list; state transitions vs statectl/resume_target; verdict file vs check_review_file; work footer vs its consumer). Deterministic - no model in the loop.

## Acceptance

- The re-injector is unit-tested: given a card file, the hook emits it as additionalContext on a compact event and stays silent on startup/resume.
- Each fixture pair is wired into pytest and fails when either side of the contract changes without the other.

## Out of scope

- Behavioral golden runs with a live model (flaky, expensive). Applicability denominators for compliance metrics (00086 R2 note).

## Notes

Sources: 2026-07-19 second-pass audit, packet 9 (edges 2 and 5); edge scout verdicts A and B.

## Status 2026-07-20 (COMPLETE — committed 7d4c5780)

- **R1** — `reinject_contract_card.py`: a SessionStart hook matched to `compact`
  ONLY (startup/resume/clear unmatched → no standing token cost) re-injects a
  contract card (step / invariants / next gate) as additionalContext after a
  within-session compaction. work / run-autopilot / review-work-completion write
  the card at each gate transition (`state.contract_card` via statectl, or a
  scratch `contract-card.md` interactively). Registered in settings.json;
  `contract_card` documented in state-schema. +5 unit tests (emits on compact,
  silent on startup/resume, state preferred over scratch).
- **R2** — `scripts/golden/` fixtures + `test_golden_contracts.py`, deterministic
  (no model). Fully both-sides-bound: state.json ↔ `statectl.read_and_parse` +
  `resume_target` (3 cases); review file ↔ `check_review_file.check`.
  Producer-pinned with a **documented limitation** (consumer is model-parsed, no
  Python parser to bind): create-prd frontmatter → Phase 0 recognized field set;
  work FILES_TOUCHED footer → its format. +6 tests.

**Acceptance:** ✓ re-injector unit-tested (emits card on compact, silent on
startup/resume); ✓ each fixture pair wired into pytest and fails when a bound
side changes. All 11 tests green; live hook smoke rc=0.

**Note:** R2's create-prd-frontmatter and work-footer pairs have no Python
consumer parser (both are parsed model-side), so those tests bind the producing
shape only — the 2 fully-deterministic pairs (state, verdict) carry the both-sided
regression net.
