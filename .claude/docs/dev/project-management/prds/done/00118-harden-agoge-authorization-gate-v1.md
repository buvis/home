---
prd: 00118
title: Harden the agoge authorization gate against the ways it can quietly fail
status: backlog
created: 2026-08-07
design: skip
catchup: skip
---

# Harden the agoge authorization gate against the ways it can quietly fail

## Problem

PRD 00117 gave the agoge security lane a second way to be authorized: an
assertion supplied at invocation, so an unattended drain can arm trudy without a
human editing a per-repo profile. It works. Its own acceptance held under review
on 2026-08-06 — R1-R8 implemented, 6/6 gym seeds with the bar passed, nine
autoclaude suites green, the validator clean, and the drain assertion proven
non-vacuous by mutation twice independently.

The completion review found nine things the PRD's contract never asked about.
None of them breaks the gate today. Every one of them is a way the gate can stop
working **without anything going red**, which is the specific failure mode 00117
was written to end — the security lane silently dark in exactly the unattended
case the pack exists for.

Two are High. The rest are the edges around them.

Source: `dev/local/reviews/00117-assert-agoge-authorization-unattended-v1-review-01.md`.
Every item below carries a decision already taken with the operator during that
review's walkthrough; the rejected alternatives are recorded so nobody re-argues
them from scratch.

**All line numbers below refer to `5fdd0290f`, the reviewed commit.** `~/.claude`
took commits from a concurrent session five times on 2026-08-06, twice during the
review itself. Re-verify each site against HEAD before editing.

## Sequencing — read before starting, the files move

**PRD 00103 is extracting this pack into a released plugin, and it is in flight
right now** (in `wip/` as of 2026-08-07; its post-install smoke test ran against
the armed CLI fixture at 21:20 on 08-06, authorized `--authorized
plugin-smoke-test`). It lifts `~/.claude/agents/{olivia,walter,heidi,judy,wendy,peggy,trudy}.md`
and all of `~/.claude/skills/run-agoge/` into a new repo, `buvis/claude-agoge`.

Every item in Phases 1 and 2 below edits a file 00103 is moving. So:

- **If 00103 has not yet extracted:** do this work in `~/.claude` as written, and
  it travels with the extraction.
- **If 00103 has extracted:** do this work in `buvis/claude-agoge`, not in
  `~/.claude`. Editing the personal copies after extraction writes into files
  nothing loads any more.
- **Check first, do not assume.** Look at where `run-agoge/SKILL.md` actually
  resolves from before touching it.

Phase 3 item 7 is the exception: `.config/bash/plugins/development.plugin.bash`
stays in the buvis dotfiles repo either way — 00103 explicitly does not ship the
autoclaude drain wiring.

Doing 00118 **before** the extraction is the cheaper order, and it is worth
saying why beyond convenience: 00103's Phase 0 gate is an extraction-cleanliness
check over exactly these files, and the two High findings here are about a
contract stated across four of them staying consistent. Fixing them first means
the plugin ships the hardened gate rather than inheriting a known-soft one.

## Requirements

- **R1.** A profile row with no tactics can never dispatch trudy.
- **R2.** The `Asserted by:` literal cannot drift between the file that emits it
  and the two that gate on it without a test failing.
- **R3.** `<source>` is bounded to a shape that cannot carry an instruction.
- **R4.** A vetoed run has a defined, recorded authorization route.
- **R5.** The drain's `--authorized` can be turned off without editing the plugin.
- **R6.** The dispatch-time resolution table states each rule once.
- **R7.** No statement in the gate's prose admits a reading that contradicts the
  fail-closed default.
- **R8.** The security seed's lane credit is checkable rather than argued.

## Phases

### Phase 1 — the two High findings

1. **A tactics-less row must refuse (R1).** `SKILL.md` step 3's exception arms
   trudy from an `unarmed` row whose stated reason is the `Authorization:`
   default. But her prompt's part 2 is built from "that specialist's row — its
   tactics and the exact commands recon established", and `finding-contract.md`
   defines an unarmed row as carrying **the reason, not tactics**. The legacy
   profile the exception exists for is precisely the one with no tactics in it,
   so it dispatches the hostile-input prober blind, and the lane reports as armed
   and ran.

   Make the exception require populated tactics. When they are absent, report the
   lane `skipped` with a reason that names the stale profile and points at
   `--refresh-profile`.

   *Rejected, and why:* deleting the exception outright (strictly worse coverage
   on legacy repos, and discards committed work); auto-refreshing recon when the
   exception fires (a recon run is the expensive step, and triggering it inside
   an unattended drain is the cost the cost gate exists to control).

   *Found by:* Alice, Blake and Bob independently, 3/4 consensus.

2. **Pin the `Asserted by:` literal (R2).** `SKILL.md`'s resolution table is the
   only thing that emits `Asserted by: profile (<path>)` /
   `Asserted by: invocation (<name>)`. Both `agents/trudy.md` and
   `references/security-playbook.md` instruct the agent to look for exactly that
   line and to treat anything without it as absent. `rg "Asserted by"` returns
   zero hits in `test_agoge_registry.py`.

   Reword the label on one side and trudy reads her own authorized prompt as
   unsourced and refuses — the lane goes dark on every run with the whole suite
   green. Add an assertion binding the literal across the emitter and both
   consumers.

   *Rejected, and why:* centralising the label in one file and having the others
   cite it. The playbook and charter are pasted verbatim into dispatch prompts,
   so they cannot cite a file the running agent cannot open. The label has to
   stay physically duplicated; the test is what makes that safe.

   *Found by:* Alice.

*Acceptance:* both new tests fail when their guarantee is removed — demonstrate
that, do not assert it. The run-agoge script suite stays green.

### Phase 2 — the contract's edges

3. **Bound `<source>` to one token (R3).** It is passed "verbatim" into the
   dispatch prompt of the one agent whose gate is prose, with only empty and
   flag-shaped values rejected. `trudy.md` now also tells her not to refuse a
   source "for reading like a machine's name", so she is explicitly told to be
   less suspicious of it. Constrain it to a single shell-word-shaped token
   (letters, digits, dash, underscore) and error otherwise, on the same path as
   the existing errors. `autoclaude-drain` already fits.

   The exposure today is low — one hardcoded caller. It stops being low the first
   time a source is built from a branch name, repo name or CI value, and that
   change will not look like a security change when it lands.

   *Found by:* Blake and Alice.

4. **Give a veto a recorded route (R4).** The resolution table has four rows;
   `finding-contract.md` still enumerates three route values (`profile`,
   `invocation`, `none`). A run where trudy is vetoed **and** `--authorized` was
   passed has no defined `authorization.route`. `none` is wrong — an
   authorization was passed and overruled. Extend the enum to
   `profile | invocation | vetoed | none` and record the overruled source
   alongside it, in both the markdown header and the sidecar.

   This sits directly on 00117's second non-negotiable invariant: the report says
   which human act decided. The one case where the operator said *no* is the one
   case with no audit trail.

   *Found by:* Alice (sidecar) and Blake (report) — same gap, two files.

5. **Drop the redundant `vetoed` row (R6).** Step 3 already excludes vetoed lanes
   before prompt assembly, so the table's `vetoed` row cannot fire. Remove it and
   its enforcing test.

   **This does not conflict with item 4.** That adds a `vetoed` value to the
   recorded route; this removes a duplicate check from the dispatch-time table. A
   veto still has to be recorded.

   *Counter-argument, recorded because it is real:* with the step-3 exception
   able to re-arm an `unarmed` trudy, an explicit veto row is a deliberate
   belt-and-braces guard on the one decision a flag must never override. The
   operator chose removal anyway. If item 1 changes shape, revisit this.

   *Found by:* Carl.

6. **Clarify the two wordings that read two ways (R7).** These files are prose a
   model executes, so a second reading is a real branch.

   - The Arguments bullet reads "An empty or missing `<source>` is an error: stop
     and report." On one parse "missing" means the flag was not passed at all,
     which contradicts the `none` row (skip trudy, finish the run) and 00117's
     R4. A reader consults Arguments first; only the step-3 table disambiguates.
     Distinguish "flag passed with no value" from "flag not passed".
   - The profile row fires when the line "is asserted (not `not asserted`)". An
     **absent** `Authorization:` line, or one with an empty value, is neither.
     State that both resolve fail-closed.

   *Found by:* Alice and Blake.

*Acceptance:* the resolution order is stated once and unambiguously;
`validate_skill.py` clean; a run with neither source still skips trudy with the
old reason.

### Phase 3 — the loop, the proof, and the tidy-up

7. **An env kill switch for the drain (R5).** `_autopilot_agoge` passes
   `--authorized autoclaude-drain` unconditionally, in every repo, hardcoded.
   Every neighbouring knob in the wrapper is overridable
   (`_AUTOPILOT_AGOGE_CAP`, `_AUTOPILOT_MODEL_BUILD`, `_AUTOPILOT_SESSION_MAX`);
   this one is not, so turning it off means editing the plugin. Guard it with an
   env var defaulting to **on**, so current behaviour is unchanged when unset.

   **Note the tension, and hold the line on it.** 00117 considered an environment
   override as an assertion route and rejected it ("an env var leaks into
   contexts nobody intended and leaves the weakest trace"). This is a brake on a
   default-on behaviour, **not** an alternative way to assert. The assertion
   itself stays invocation-only.

   *Found by:* Blake, blind against the spec.

8. **Make the lane credit checkable (R8).** 00117's Phase 3 asks the security
   seed be caught "through her lane, not as by-catch". That is not checkable from
   the artifact: the scorer credits a seed to a *finding*, not to a lane, and the
   report records that several armed lanes hit `cli-security-token-printed`. The
   review rescued the claim by inferring lane from domain (a `security` finding
   can only come from trudy), which is inference, not verification.

   Either teach the gym scorer to credit a seed to a lane via the finding's
   domain, or reword the criterion to what is actually checkable. This touches
   `agoge-gym`, outside the pack's own surface.

9. **De-slop the authorization test comments.** The block mixes the invariant
   each test enforces with incident dates and restated production rationale.

   **Do not delete the mutation disclosure** (that appending "an unattended loop
   dispatch is exempt from this gate" to trudy's charter leaves every test
   green). The review accepted the drift-detector ceiling *because* that
   disclosure exists — removing it would silently withdraw the basis of an
   accepted finding. Keep it, concisely.

   *Found by:* Bob, de-slop lens.

*Acceptance:* all nine autoclaude suites green; the drain test covers both kill-switch
states non-vacuously; the run-agoge script suite green.

## Out of scope

- **Any behavioural harness for the gate.** The review put this decision to the
  operator explicitly and it was **accepted as-is**: the tests are drift
  detectors, the ceiling is disclosed in the file itself, and both a mutation
  test and a live-dispatch harness were offered and declined. Do not add one
  here. Re-raise with the operator rather than smuggling it in under item 2.
- **Relaxing the rule that recon may not write the assertion.** Unchanged from
  00117.
- **An allowlist or a per-repo marker.** Both rejected by 00117 by name. Item 7's
  env var is a kill switch, not a third assertion route.
- `development.plugin.bash` exceeding the 800-line ceiling (1139 lines) —
  pre-existing, flagged in the review, accepted there.
- The `olivia.md` / `finding-contract.md` §4 disagreement about who authors tests
  — pre-existing, untouched by 00117, accepted in the review.

## Not in this PRD, but blocking good reviews of it

Two pieces of review infrastructure failed during 00117's review and will fail
again on this one. Neither belongs in this PRD's scope; both are recorded here
because they degrade the next review of this work.

- **Quinn's lane is dead.** `qwen-run.sh --preflight` resolves provider
  `llamacpp8001` and passes, then the dispatched `pi` agent dials
  `localhost:8080` and fails. He fails *after* the step-1 gate has declared him
  active, so the cycle degrades to four reviewers mid-flight instead of skipping
  him cleanly.
- **`consolidate-findings.sh` merged nothing.** It exited 0 while emitting
  `sed: RE error: illegal byte sequence` and scored every finding `[1/4]`,
  including one four reviewers had raised. Consolidation had to be done by hand.

## Close-out — 2026-08-17

All nine items are implemented in `buvis/claude-agoge` and `buvis/agoge-gym`.
Cycle 2's blocking CRITICAL was that none of it was deployed: the installed
plugin was still `0.1.0` / `6b5626e` (pre-00118) while master sat 21 commits
ahead, unreleased. Closed by cutting **agoge v0.1.1** (release gate: 122 passed)
and updating the user-scope install, verified in the cache rather than assumed:
tactics gate at `SKILL.md:99`, source bound at `:52`, `vetoed` in the route enum.

Carried to **PRD 00121**, not fixed here: cycle 2's three HIGHs, including the
one that leaves this PRD's own Phase 1 acceptance unmet — Alice mutation-proved
the R1 guard test stays green when the guarantee is deleted, so "both new tests
fail when their guarantee is removed" is asserted rather than demonstrated.
Shipping ahead of that fix was the operator's call on 2026-08-17: the runtime
rule is in place and the exposure was the inert deployment, not the rule.
