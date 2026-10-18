---
prd: 00117
title: Assert agoge authorization from the invocation, not only the profile
status: backlog
created: 2026-08-05
design: skip
catchup: skip
---

# Assert agoge authorization from the invocation, not only the profile

## Problem

Trudy, the agoge runtime-security lane, refuses to run unless the strategy
profile asserts:

```
Authorization: this project is the operator's own or explicitly authorized.
```

Recon writes `Authorization: not asserted` on every fresh profile and may not
change it, by design: whether a repo belongs to the operator is not a fact an
agent can establish. **That rule is correct and this PRD does not relax it.**

The consequence is that the security lane is permanently dark in an autoclaude
drain, which is exactly the unattended situation the pack exists for. Proven on
2026-08-05 (PRD 00102's Phase-0 run): a full headless `claude -p` agoge run
against the armed CLI gym fixture scored 6/6 seeds with trudy skipped, because
the fresh profile carried the default. Store permissions, path handling and TLS
posture went unprobed; the one security seed was caught only as by-catch.

The operator's ruling: human gating is not acceptable in autoclaude loops.

## What settles the shape

PRD 00101 recorded that the harness permission classifier refused three trudy
dispatches in an **interactive** session carrying the asserted line, and that an
unattended batch would not get an operator's unblock. If that also held under
`claude -p`, no profile-level bypass would be sufficient on its own.

**It does not hold.** Probed 2026-08-05 before designing anything: trudy was
dispatched under the exact drain invocation
(`claude -p --permission-mode auto`, `WARDEN_UNATTENDED=1 CLAUDE_UNATTENDED=1`)
with an asserted authorization line in her prompt. The dispatch was **permitted**.
She ran, returned 9 findings (7 verified, 2 mocked), left the armed tree
byte-identical and `bin/verify-seeds cli` at 6/6 with 0 leaks. So the refusals
are an interactive-session behaviour, and an invocation-level assertion is
sufficient.

## Decision

Put to the operator with four options on 2026-08-05. **Chosen: pointing
autoclaude at a repo IS the authorization.**

The drain hook passes an explicit authorized flag through to `/run-agoge`. The
operator already granted that loop autonomous edit-and-commit rights over the
repo; probing it is strictly less invasive than what the loop already does.

Rejected, with the reason each was rejected:

- **An operator-owned allowlist** (`~/.claude/agoge-authorized`): covers
  hand-runs too, but is new config to maintain, does not extract into a released
  plugin (a machine-local path), and a stale glob silently authorizes a repo the
  operator forgot.
- **An environment override**: cheapest, but an env var leaks into contexts
  nobody intended and leaves the weakest trace — the report can name it but
  cannot show when or why it was set.
- **A durable per-repo marker**: most explicit, but still needs a human per repo,
  so it does not fix a first unattended drain at a new target, which is the case
  raised.

**Two invariants, non-negotiable, and they bound every phase below:**

1. The assertion still traces to a **human act**. The machine never asserts for
   itself. Recon still writes `not asserted` and still may not edit the line.
2. The report says **which** act, so a reader can tell an invocation assertion
   from a hand-edited profile.

## Requirements

- **R1.** `/run-agoge` accepts `--authorized <source>`: an assertion supplied at
  invocation, where `<source>` names the human act it came from.
- **R2.** A missing or empty `<source>` is an error. The run stops and reports;
  it never falls back to asserting anonymously.
- **R3.** The profile's human-edited line still asserts, and still wins when both
  are present — the file in the repo is the more specific act.
- **R4.** With neither, trudy is still skipped with the existing reason. The
  default stays fail-closed.
- **R5.** Trudy's dispatch prompt carries the assertion **and its source**. Her
  charter and the security playbook must accept an assertion whose source is the
  invocation, not only the profile.
- **R6.** The report names the authorization source for trudy's lane, in both the
  markdown summary and the JSON sidecar.
- **R7.** The autoclaude drain hook passes the flag, so a drained batch arms the
  security lane without a human editing a per-repo profile.
- **R8.** `trudy.md`, `security-playbook.md` and `finding-contract.md` §5 agree
  after the change, and the playbooks stay extraction-clean (PRD 00103 lifts them
  verbatim into a released plugin).

## Phases

### Phase 1 — the contract

Rewrite the authorization gate in the three places that state it, so all three
describe the same two-source rule.

1. `references/finding-contract.md` § profile section 5: the profile line is one
   of two human acts that may assert. Name the other. Keep "the machine never
   edits this section" exactly as it is.
2. `agents/trudy.md`: the gate currently reads "the profile in your dispatch
   prompt must assert that". Generalize to an assertion carrying a named source,
   with an unsourced assertion treated as absent.
3. `references/security-playbook.md`: the same restatement, extraction-clean.

*Acceptance:* the three files agree; `test_agoge_registry.py`'s extraction-clean
and playbook-budget assertions still pass.

### Phase 2 — the skill

1. `run-agoge/SKILL.md` § Arguments: document `--authorized <source>`.
2. § Dispatch, part 5: resolve the authorization — profile first, then the flag,
   then skip — and record which source won. Fail loud on an empty source.
3. § Report: the summary header and the sidecar carry the source for trudy's
   lane.

*Acceptance:* `validate_skill.py` clean; the resolution order is stated once and
unambiguously; a run with neither source still skips trudy with the old reason.

### Phase 3 — the loop and the proof

1. `_autopilot_agoge` in the autoclaude wrapper passes the flag.
2. `test_autoclaude_agoge_drain.sh` asserts it, non-vacuously (the assertion must
   fail if the flag is dropped). All nine sibling suites stay green.
3. Hygiene tests for the contract itself in `test_agoge_registry.py`.
4. **Prove it by running it, not by argument.** An unattended `claude -p` agoge
   run against a freshly armed fixture must arm trudy through the invocation
   assertion and catch the security seed **through her lane**, not as by-catch.

*Acceptance:* `bin/score` on a freshly armed `armed/cli`, with the security seed
credited to trudy; `bin/verify-seeds cli` 6/6 with 0 leaks afterwards;
`validate_skill.py` clean; 91+ run-agoge script tests and all nine autoclaude
suites green.

## Out of scope

- Any relaxation of the rule that recon may not write the assertion.
- An allowlist, an env override, or a per-repo marker — all three were considered
  and rejected above. Re-raise with the operator rather than adding one quietly.
- Arming trudy on a hand-run at a fresh profile. That case still gates, which is
  the stated cost of the chosen option.
