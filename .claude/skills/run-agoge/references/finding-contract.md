# Agoge Contracts

Three contracts every agoge run obeys: what a specialist returns, what the run
writes, and what the strategy profile holds.

The seven agent bodies carry none of this. They receive the finding contract in
their dispatch prompt, so the personas stay portable and the skill owns every
path (registry convention, `review-work-completion/references/agent-registry.md`).

## Finding contract

Every specialist returns findings in this shape. One finding per defect.

| Field | Required | Notes |
|-------|----------|-------|
| `title` | yes | One line, what a user experiences. Not the code smell. |
| `domain` | yes | `journey`, `integration`, `ux`, `release`, `performance`, `security`. One per finding; the lane that found it. |
| `severity` | yes | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`. |
| `paths` | yes | Repo-relative paths, no leading `./`. A finding with no path cannot be acted on or scored. |
| `evidence` | yes | What was actually observed: the command, the request, the output. Quoted, not summarized. |
| `status` | yes | `verified`, `unverified`, `mocked`, `skipped`. See below. |
| `fix` | no | The concrete change, when it is obvious. |

### Status is the honesty field

- `verified` — the specialist ran the product and observed the symptom. Only
  this status may be reported as a real defect.
- `mocked` — observed against a mock or stub because the real dependency was
  unreachable. Never report a mocked probe as verified; the mock is the author's
  belief about the dependency, not the dependency.
- `unverified` — the specialist could not execute the surface. Report what was
  attempted and why it failed. **Unverified is never reported as passed.**
- `skipped` — the surface does not exist here (no browser, no db). A loud skip,
  not silence, and never a finding invented to fill the lane.

A lane that produces no findings must still say which of the four applies to it.
"No findings" from a lane that never ran is the failure this contract exists to
prevent.

## Report contract

One run writes two files into the target repo's `dev/local/audit-results/`:

- `agoge-<YYYY-MM-DD>.md` — for the human.
- `agoge-<YYYY-MM-DD>.json` — for a scorer.

### The markdown report

1. **Summary header** — per-lane counts of verified / unverified / mocked /
   skipped, and which specialists were armed, unarmed or vetoed.
2. **Findings**, each as a walkthrough packet per `rules/communication.md`:
   position, severity, title; what it is and where; the evidence plus whether it
   is confirmed or suspected; what breaks if unchanged; at least three real
   options with benefit, drawback and effort; a marked recommendation naming the
   strongest reason against it.
3. **How-to-proceed block**, verbatim, at the end.

Interactive runs walk the packets one at a time and record accepted / deferred /
rejected in the report. Unattended runs write the packets and stop; they never
auto-emit PRDs.

### The JSON sidecar

Written for machine consumption, and shaped for `agoge-gym`'s `bin/score`:

```json
{
  "fixture": "cli",
  "findings": [
    {
      "domain": "journey",
      "severity": "CRITICAL",
      "paths": ["pocket/store.py"],
      "status": "verified",
      "title": "`pocket done <id>` completes the wrong note after a delete"
    }
  ]
}
```

`fixture` names the target the run was pointed at. The scorer requires it: two
targets can share a relative path (both gym fixtures ship a root `CHANGELOG.md`)
and without it one target's finding would credit another's seed.

`score` reads `fixture`, `domain`, `severity` and `paths`; the extra keys are
carried for the human and ignored by matching. A finding with an empty `paths`
list makes the whole report unscoreable, by design — it fails loud rather than
scoring as a zero the pack did not earn.

## Strategy profile contract

One content contract, two landing spots. `run-agoge` reads whichever exists,
atlas preferred:

- The `qa` layer of the target's cartographer atlas, when one exists.
- Otherwise `dev/local/agoge-profile.md` in the target repo. A named keeper: it
  survives dev/local GC.

Sections, in order:

1. **Surfaces** — what is actually runnable here: test suites and how to run
   them, CLI entry points, dev server, browser (Playwright present?), database,
   external services.
2. **Per-specialist strategy** — one row per specialist: `armed` with concrete
   tactics, or `unarmed` with the reason. Only armed specialists dispatch; this
   is the cost gate.
3. **Mocking strategy** — for each unreachable external, what to mock and how.
   Anything probed this way reports `mocked`, never `verified`.
4. **Authoring assignments** — which specialist, if any, should leave durable
   tests behind.
5. **Pins and vetoes** — human-owned. A veto means that specialist never runs.
   **The machine never edits this section**; a refresh copies it through
   byte-identically.
6. **Freshness stamp** — ISO date of the last recon, and the target's HEAD sha.

A profile whose stamp is older than the target's current HEAD is stale: refresh
it, preserving section 5 exactly.
