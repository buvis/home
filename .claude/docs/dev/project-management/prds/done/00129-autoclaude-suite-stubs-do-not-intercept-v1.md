# The autoclaude suites' bash stubs no longer intercept anything

Source: agoge product-QA run, `dev/local/audit-results/agoge-2026-08-17.md`, findings 8 and 12
(both HIGH), accepted as one cluster in the 2026-08-17 walkthrough. Found by walter — the second
one the hard way.

## Overview

### Problem Statement

Both `autoclaude` shell suites stub external binaries as **bash functions**, with a comment
saying "Never let a scenario touch the real machine". Since PRD 00106 moved the loop into
Python, those functions cannot intercept anything: `loop.py:349` runs
`subprocess.run(["sysctl", ...])` and `notify_out.py:31-35` shells out with `sys.executable`.
A bash function is invisible to both.

Two consequences, both observed on 2026-08-17:

1. **The suite aborts under memory pressure.** Two consecutive runs stopped after 13 of 58
   checks with `FAIL: scenario 7 … safety timeout`, while the real `sysctl` reported pressure
   level 2 and `_memory_gate` slept toward its 3600 s default. The remaining 45 checks never
   ran, hidden behind a message about the tracon launch path. The suite therefore passes or
   fails on how much RAM the machine happens to have — and fails precisely when the machine is
   busy, which is when it is most needed.
2. **The suite sends real push notifications.** The `python3()` stub's
   `*notify.py*) : ;;` arm at line 183 is bypassed, so three real ntfy pushes reached the
   operator's phone at 01:03, 01:05 and 01:06, `http=200`, each titled with a meaningless
   `mktemp` sandbox name. Any loop branch the suite reaches that notifies — memory wait, limit
   wait, pause, park, drained — does the same. It trains the operator to ignore autopilot
   notifications, which is the loop's only alerting channel.

This is one root cause with two symptoms, which is why the accepted option is an audit rather
than two patches: the move to Python broke a **class** of stub, not two instances.

### Target Users

Anyone running either `autoclaude` suite — and the operator's phone, which is not a test fixture.

### Success Metrics

- Both suites run to completion with the machine under memory pressure level 2, all 58 checks
  reported.
- A full run of both suites produces **zero** new lines in `hooks/notify.log`.
- Every stub in both suites intercepts the call the product actually makes, verified by
  asserting the stub was hit rather than by the absence of a side effect.

## Functional Decomposition

### Capability: a stub intercepts what the product actually invokes

Accepted option: **audit every bash-function stub in both suites** for the
subprocess-versus-function gap, and convert each one that a Python subprocess walks past into a
real executable stub in the sandbox `bin/` (already first on `PATH`), which is how the suites
already stub other binaries.

The two known instances are `sysctl` (finding 8) and `notify.py` (finding 12). The audit exists
because there may be more: every binary the loop shelled out to after the Python move is a
candidate.

Where an executable stub is impractical, an env kill-switch is acceptable **only** with an
assertion that the switch was honoured — a stub that silently does nothing is what caused this.

## Structural Decomposition

- `skills/run-autopilot/scripts/test_autoclaude_fable_subcommands.sh` — the `sysctl` stub at
  line 143, the `python3` stub at line 183
- the sibling `autoclaude` suite — same audit, same class
- `skills/run-autopilot/cli/loop.py` — `_memory_gate` at line 349, the notify call sites (read
  only; this PRD changes the suites, not the loop)
- `skills/run-autopilot/cli/notify_out.py` — lines 31-35, the `sys.executable` shell-out (read
  only)

## Implementation Phases

### Phase 1: inventory

1. List every stub in both suites, and for each one name the call the product makes (bash
   builtin, `subprocess.run` with a bare name, `sys.executable`, absolute path). Record the
   table in the commit message — it is the evidence the audit was an audit.

### Phase 2: convert and assert

2. Convert each ineffective stub to a real executable in the sandbox `bin/`.
3. Add one assertion per converted stub that it was actually invoked, so a future move breaks a
   test instead of reaching the machine.
4. Re-run both suites under real memory pressure if reachable; otherwise with a stub reporting
   level 2.

*Acceptance:* both suites green with 58/58 checks under pressure level 2, and `notify.log`
unchanged across a full run of both.

## Test Strategy

Verbatim evidence:

```
$ bash /tmp/agoge_run_clean.sh .../test_autoclaude_fable_subcommands.sh
...13 PASS lines...
FAIL: scenario 7 (bare autoclaude still runs the loop) — safety timeout — the call never returned

stderr: autoclaude: memory pressure (level 2); waiting for it to clear before launching next session.
final rc=137 timeout=yes
$ sysctl -n kern.memorystatus_vm_pressure_level  -> 2
```

```
--- hooks/notify.log after two suite runs and one repro ---
[2026-08-17 01:03:55] CLI --send: autopilot ⏳ tmp.qy4HlFCENT / Waiting: memory pressure (level 2).
[2026-08-17 01:03:55] Notification sent successfully (http=200)
[2026-08-17 01:05:06] CLI --send: autopilot ⏳ tmp.kBl3E9arHb / ...
[2026-08-17 01:06:34] CLI --send: autopilot ⏳ tmp.9wJWvgwuY9 / ...
```

The notify assertion is the strongest available: run both suites, diff `notify.log`, require
zero new lines.

## Risks

- **This is the largest change to the suite that is currently the main confidence signal for
  `autoclaude`**, so a mistake there is expensive and quiet.
- **Converting a stub can change what a scenario tests.** Any scenario that relied on a function
  stub which still works must keep working — the inventory in Phase 1 is what makes that
  checkable.
- **The kill-switch shortcut is tempting and was deliberately not taken**: exporting
  `_AUTOPILOT_MEM_WAIT_MAX=0` and a notify-quiet variable would stop both symptoms today while
  testing neither gate, and the next thing the loop shells out to would bite identically.
