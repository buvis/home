# The loop registry reports a dead loop as alive and deletes a live one's entry

Source: agoge product-QA run, `dev/local/audit-results/agoge-2026-08-17.md`, findings 4 and 5
(both HIGH), accepted in the 2026-08-17 walkthrough. Found by heidi against live loop
processes.

## Overview

### Problem Statement

Two independent defects in the same registry, pointing opposite ways.

**A dead loop reads as alive.** `prune_registry` applies a recycled-pid guard (`_pid_tagged`);
`live_wrapper_pid` does not, and `tracon.discovery` never prunes at all. So an unrelated
process that lands on a recycled pid makes a dead loop look healthy — and that suppresses the
one signal that says a batch died. Fed into the product's own status folder, the truth renders
`⚠ orphaned 5h00m => run autoclaude` while the recycled-pid lie renders `idle 5h`. Memory
records a batch that died unannounced on 2026-07-12; this is how that stays invisible.

**A live loop's entry is deleted.** `routing._load_json` collapses `OSError` and `ValueError`
into the same `None`, so an unreadable entry — a permission or ownership problem — is treated
as corrupt and pruned. With the entry gone, the duplicate-loop guard stops firing, which is the
precondition for two loops draining one backlog at once. Memory records the 2026-06-25 machine
lockout, where an uncapped parallel fan-out exhausted RAM and locked the box out.

Both are live today: two loops (gems, ddb) were running while this run was walked, so this
status view is load-bearing.

### Target Users

The operator reading autopilot status, and the duplicate-loop guard that protects the machine.

### Success Metrics

- A registered pid that is alive but **untagged** resolves as **not** the loop:
  `wrapper_alive()` is `False`, and the status view shows the orphan warning.
- An unreadable registry entry belonging to a live, correctly-tagged loop **survives** a prune,
  and `live_wrapper_pid` still returns its pid.
- A dead-pid, untagged or malformed entry still prunes, unchanged.

## Functional Decomposition

### Capability: liveness means "the loop", not "some process" (finding 4)

Accepted option: call `_pid_tagged` in **both** `live_wrapper_pid` implementations. The guard
already exists and is tested, so this is reuse. A shared resolver was considered and rejected as
a refactor of the loop's hot path while two loops are running.

### Capability: unreadable is not corrupt (finding 5)

Accepted option: catch `OSError` separately in `routing._load_json` and keep the entry.
Unreadable then means "leave alone", the safe default.

## Structural Decomposition

- `skills/run-autopilot/cli/loop.py` — `live_wrapper_pid`, the registration/teardown flow
- `skills/run-autopilot/cli/routing.py` — `_load_json`
- `skills/run-autopilot/scripts/tracon/discovery.py` — the second `live_wrapper_pid`

## Implementation Phases

### Phase 1: both fixes plus their regression tests

1. `_pid_tagged` in both liveness paths.
2. `OSError` handled separately in `_load_json`, entry preserved.
3. Regression tests per Test Strategy, each demonstrated failing first.

*Acceptance:* the two new tests fail against current code; the existing prune tests (dead-pid,
untagged, malformed) stay green.

## Test Strategy

Evidence carried verbatim — both are reproductions someone already ran:

```
untagged live child pid 92352 tagged? False
cli.loop.live_wrapper_pid (NO prune first) -> 92352
tracon.discovery.wrapper_alive             -> True

wrapper=False (truth: loop is dead) -> ⚠ orphaned 5h00m => run autoclaude
wrapper=True  (recycled pid lie)    -> o idle 5h
```

```
child pid 55509 tagged? True alive? True
CONTROL readable: survived= True  live_wrapper_pid= 55509
UNREADABLE     : survived= False live_wrapper_pid= None
child still alive? True
```

Tests: register a live-but-untagged pid and assert `wrapper_alive()` is `False`; make a live,
tagged entry unreadable and assert it survives the prune with its pid still resolvable.

## Risks

- **A legitimately live loop whose tagging is missing now reads as dead.** Safer direction, but
  it is a behaviour change — an old loop started before tagging existed would be reported
  orphaned.
- **The `OSError` fix trades fail-open for possible fail-stuck**: a permanently unreadable entry
  never gets cleaned up and blocks new loops until someone clears it by hand. The warn-loudly
  variant was the better end state and was not taken; if the stuck case ever bites, that is the
  upgrade path.
- **Two copies of the tagging rule remain**, in `cli/loop.py` and `tracon/discovery.py`, which
  is how they diverged in the first place. The regression tests are what keeps them honest.
