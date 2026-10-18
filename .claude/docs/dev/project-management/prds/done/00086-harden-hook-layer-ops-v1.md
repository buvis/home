# 00086 - Harden hook-layer operations

## Problem

The 2026-07-19 second-pass audit found the hook layer has no failure story: a broken python3 (mise upgrade) kills ~13 hooks at once, silently (every one fails open), and the diagnostic tools need the same interpreter; skill adherence (measured 1/30 self-fire, once, by hand) has no standing instrument; and batches run on auto-updating plugin code - aegis/warden can rotate versions between loop relaunches mid-batch with no signal. Decision 12 of the same audit left small hook-polish items unapplied.

## Goal

The hook layer fails loud, is measured, and is version-stable for the duration of a batch.

## Requirements

- R1 Recovery runbook: a short reference (skills/run-autopilot/references/ or rules/) answering "python3 broke, now what": `claude --no-hooks` scope and its caveat (drops warden/aegis too - recovery only), an interpreter preflight (`python3 -c 'print()'`) in autoclaude before batch launch, a settings.json backup-before-edit convention (update-config flows and manual edits), and where hook stderr lands when hooks degrade.
- R2 Compliance counter: a Stop hook appends `{skill, session_id, ts, source}` rows to `metrics/skills.jsonl` by scanning the transcript for Skill tool_use blocks (sibling or extension of track_cost's existing parse); brief-portfolio gains a monthly adherence row. Numerator-only v1 - no applicability denominator.
- R3 Plugin pin per batch: batch selection records resolved plugin versions into `state.batch.plugin_versions`; the wrapper preflight compares at each relaunch and on mismatch warns and parks (never silently proceeds on rotated enforcement code).
- R4 Decision-12 leftovers: notify.py presence probes run concurrently and the raw-payload log call is located and removed (log lines only; notify.log gains a size-rotation rule); enforce_prd_location and the other local policy hooks emit a one-line "policy hook degraded: <exception>" to stderr before exiting on unexpected exceptions (aegis copies via the aegis repo PRD); cartographer-stop.py's `git rev-list` gains `timeout=5`; cartographer-recon-brief.py checks its once-a-day store before spawning git; work/references/subagent-dispatch.md's "standard 200K context ceiling" wording and run-autopilot/references/batch-report-format.md's opus example rows are refreshed to the fable-default world.

## Acceptance

- A fresh session given only the runbook can answer the R1 question without improvising.
- One real session produces correct `metrics/skills.jsonl` rows.
- A staged plugin-version bump mid-batch produces the warn/park, covered by a wrapper test.
- Each R4 item is covered by its file's existing test suite or one new case.

## Out of scope

- Compaction re-anchor and golden fixtures (00087). Cartographer work-tree hashing (00088). Aegis-shipped hook copies (aegis repo PRD 00001).

## Notes

Sources: 2026-07-19 second-pass audit (dev/local/audit-results/2026-07-19-fable5-second-pass-audit.md), packets 9 and 12.

## Status 2026-07-20 (fast-track partial)

Landed and committed: R1 (hook-recovery.md runbook + autoclaude python3
preflight), R2 (track_skills.py Stop hook + tests + registration + brief-
portfolio 30-day adherence row + collect.py support), R4 (cartographer-stop
`git rev-list` timeout=5; enforce_prd_location fail-loud "policy hook
degraded" logging; notify.py raw-payload-log removal + concurrent presence
probes; subagent-dispatch.md + batch-report-format.md fable-default refresh).
Verified already-satisfied: recon-brief once-a-day store guard, notify.log
size-rotation.

**R3 DONE 2026-07-20 (commit d4d8ed7e) — PRD COMPLETE.** Phase 0 pins
aegis+warden resolved versions into `state.batch.plugin_versions` at batch
selection (from `installed_plugins.json`); the `autoclaude` wrapper's
`_autopilot_plugin_drift` preflight compares them before each session launch and
halts loud with state intact on drift (sanctioned-halt row 11), never running a
batch on rotated enforcement code. Unpinned/pre-R3 batches no-op.
`test_autoclaude_plugin_pin.sh` (4 pure-helper unit cases + a
drift-halts-before-launch scenario) all green; the park suite is unregressed.
