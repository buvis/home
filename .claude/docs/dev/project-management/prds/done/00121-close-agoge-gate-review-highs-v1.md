---
prd: 00121
title: Close the three HIGHs left open by PRD 00118's cycle-2 review
status: backlog
created: 2026-08-17
design: skip
catchup: skip
consensus_engine: shadow
---

# Close the three HIGHs left open by PRD 00118's cycle-2 review

## Problem

PRD 00118 hardened the agoge authorization gate and shipped as **agoge v0.1.1**
on 2026-08-17. Its cycle-2 review raised three HIGH findings that the release
deliberately went ahead of, on the operator's call: the exposure at the time was
that the hardened gate was deployed nowhere, not that the rules were wrong.

One of the three is not a new defect but 00118's own **unmet acceptance**. Its
Phase 1 bullet reads "both new tests fail when their guarantee is removed —
demonstrate that, do not assert it." Alice mutation-proved the opposite for R1.

Source: `dev/local/reviews/00118-harden-agoge-authorization-gate-v1-review-2.md`.
**Line numbers there refer to `d0e74a8`.** HEAD is now `76ed61e` (the v0.1.1
release commit). Re-verify each site before editing.

Two repos: `buvis/claude-agoge` (items 2, 3, 4) and `buvis/agoge-gym`
(items 1, 5, 6). PRD 00118's lesson is that neither counts as done until it is
released and installed, hence R4.

## Requirements

- **R1.** A malformed gym manifest exits 2, never 1, whatever its shape.
- **R2.** Deleting the R1 tactics guarantee from `SKILL.md` fails a test.
- **R3.** A veto carrying both a profile and an invocation assertion has exactly
  one legal recorded source.
- **R4.** The fix is released and the installed plugin version is verified, not
  assumed.

## Phases

### Phase 1 — the three HIGHs

1. **`bin/score` exit codes (R1).** Its contract says every broken manifest
   exits 2; three shapes land on exit 1 instead, which under this scorer's own
   contract means "the pack failed the bar" — the exact confusion the exit-2 work
   exists to prevent. Reproduced by 00118's gate at `d0e74a8`: a bare `42`
   manifest exits 1 with `TypeError: argument of type 'int' is not a container or
   iterable` at `read_seeds` line 118; a seed carrying `domain` and `id` but no
   `evidence` exits 1 with `KeyError: 'evidence'` at `match()` line 142; a
   missing or unreadable file raises `FileNotFoundError`. `read_findings` already
   has the `isinstance` guards `read_seeds` lacks — mirror them.
   *Found by:* Blake, Alice, Bob (3/4). File: `buvis/agoge-gym/bin/score`.

2. **Re-guard the R1 tactics rule (R2).** 00118's task 12 moved "populated
   tactics" / "stale profile" / "--refresh-profile" out of the exception
   paragraph into step 3's normal path, so the guard test now passes on the new
   sentence alone: deleting the entire "A third way the exception fails closed…"
   paragraph leaves 109/109 green (mutation-proved by Alice). The exception path
   re-arms a row marked `unarmed`, which the normal-path wording does not cover.
   Add a test that binds the exception path's own tactics rule, and demonstrate
   it failing with the paragraph removed.
   *Found by:* Alice. File: `claude-agoge/skills/run-agoge/SKILL.md`.

3. **Profile precedence on a combined veto (R3).** A veto with **both** profile
   and invocation assertions has two legal source outcomes today: step 7 says
   either route may be overruled, while the profile-wins rule sits inside part 5,
   which vetoed lanes explicitly bypass. State profile precedence for the
   combined case and test it.
   *Found by:* Bob. File: `claude-agoge/skills/run-agoge/SKILL.md:229`.

*Acceptance:* each of the three new/changed tests fails when its guarantee is
removed — demonstrate it, do not assert it. Both repos' suites green.

### Phase 2 — the mediums behind them

4. **Split `test_agoge_registry.py` (816 lines, ceiling 800).** 00118's task 15
   was titled "split the oversized gate tests" and split nothing: it removed a
   62-line function and added enough to cross the ceiling. Alice names the split
   point — the authorization-gate block below the `PRD 00117` banner.
   *Found by:* Alice, Bob, Blake (3/4).

5. **One `_load_json(path)` in `bin/score`.** The `json.loads` +
   `JSONDecodeError` → `ReportError` block is byte-identical in `read_findings`
   and `read_seeds`. One helper states the parse contract once and gives item 1's
   `isinstance(data, dict)` guard a single home. Do item 1 first, then fold.
   *Found by:* Alice, Bob, Carl (3/4).

6. **`lane` disagrees with its own docs by one word.** The module docstring, the
   field comment and the CHANGELOG all say `lane` is "looked up from the seed's
   own domain", but `bin/score:171` reads `LANE_BY_DOMAIN[hit["domain"]]` — the
   finding's domain. Identical today only because `match()` requires the two
   domains to be equal. Fix the code or the three prose sites, not both ways.
   *Found by:* Alice, Bob (2/4).

### Phase 3 — ship it (R4)

7. Release `claude-agoge` via `dev/bin/release`, update the user-scope install,
   and verify the shipped cache carries the change rather than trusting the
   version string. `agoge-gym` is not a plugin and needs no release.

*Acceptance:* `claude plugin list` shows the new agoge version, and an `rg` over
`plugins/cache/buvis-plugins/agoge/<new>/` finds the Phase 1 edits.

## Out of scope

- Any further behavioural harness for the gate. 00118 put this to the operator
  and it was accepted as-is; the tests are drift detectors with a disclosed
  ceiling. Do not smuggle one in under item 2.
- The remaining cycle-2 LOWs. They stay in the review file; this PRD is the three
  HIGHs and the three 2/4-or-better mediums that sit on the same two files.
