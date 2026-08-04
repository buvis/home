---
name: run-agoge
description: Use when running the agoge product-QA pack at a repo - recon, armed specialist dispatch, dedup, and one findings report about the product rather than the diff. Triggers on "run agoge", "/run-agoge", "product QA", "QA this project".
---

# Run agoge

Agoge is the product-time lens. Every other review reads a diff; this one runs
the product. Seven named specialists: **olivia** (recon, always), then
**walter** (journeys), **heidi** (integration and db), **judy** (UX),
**wendy** (release truth), **peggy** (performance), **trudy** (runtime
security).

The one rule the whole pack exists to enforce: **a lane that did not run is
never a pass.** Every result carries `verified`, `unverified`, `mocked` or
`skipped`, and only `verified` is a real defect.

## Dependencies

- Agent registry: `olivia`, `walter`, `heidi`, `judy`, `wendy`, `peggy`,
  `trudy` — dispatched by `subagent_type`. Missing = this skill cannot run.
- Path: `references/finding-contract.md` in this skill's directory — the
  finding, report and profile contracts. Read it before step 2.
- Conventions: `review-work-completion/references/agent-registry.md` (registry
  ownership), `rules/communication.md` (the findings walkthrough).
- CLI: `git`, `python3`.

## Arguments

- *(none)* — the current repo.
- `<repo-path>` — an absolute path to the repo to run against.
- `--refresh-profile` — re-run recon even when the profile is fresh.

## Workflow

### 1. Resolve the target

Take the absolute repo path from the argument, else the cwd's repo root. Record
its HEAD:

```bash
git -C /absolute/target/repo rev-parse HEAD
```

Everything downstream uses absolute paths. Never `cd`.

Read `references/finding-contract.md` from this skill's directory now. You will
paste its `## Finding contract` section into every dispatch prompt, so the
specialists get the contract without reading any path of yours.

### 2. Profile

The profile is `dev/local/agoge-profile.md` in the **target** repo. It decides
who runs, so a wrong profile is a wasted run.

- **Missing**, or its freshness sha is not the target's HEAD, or
  `--refresh-profile`: dispatch **olivia** (see the recon prompt below).
- **Fresh**: read it and go to step 3.

After a refresh, before anything else, prove the human-owned section survived:

```bash
git -C /absolute/target/repo diff -- dev/local/agoge-profile.md
```

`dev/local` is usually ignored, so also keep a copy of section 5 from before the
dispatch and compare it byte for byte. **If `## Pins and vetoes` changed, stop
the run and report it.** Recon rewriting a human's veto is a defect in the pack,
not a detail.

### 3. Dispatch the armed specialists

From the profile's per-specialist strategy, dispatch **only** specialists marked
`armed` and not vetoed. Unarmed and vetoed lanes are reported, never run —
that is the cost gate.

Dispatch every armed specialist **in one message**, one Agent call each, so they
run concurrently. One that fails returns its error and the others are unaffected;
record that lane `unverified` with the failure and finish the run.

Each prompt is assembled from four parts, in this order:

1. The absolute target repo path, and the one-line instruction: run the product,
   do not modify it.
2. That specialist's row from the profile — its tactics and the exact commands
   recon established — plus the mocking strategy and any authoring assignment.
3. The `## Finding contract` section, pasted verbatim.
4. For **trudy** only: the `Authorization:` line from the profile's pins section,
   verbatim. If it reads `not asserted`, do not dispatch her — report the lane
   `skipped` with that reason. Only a human writes that assertion.

Keep each prompt under 50 000 bytes (`work/references/subagent-dispatch.md`).
Recon output is small, so this only binds if you paste files in — do not.

### 4. Dedup

Collapse findings that are the same defect seen from two lanes (a dead
integration also breaks a journey). Key on normalized path plus symptom, not on
wording. On merge: keep the **strictest** severity, union the evidence, and keep
every contributing lane's name.

Do not merge two findings that share a file but not a symptom.

### 5. Report

Write both files into the target repo's `dev/local/audit-results/`:

- `agoge-<YYYY-MM-DD>.md` — the human report, in the report contract's shape:
  summary header with per-lane verified / unverified / mocked / skipped counts
  and who was armed, unarmed or vetoed; then one walkthrough packet per finding;
  then the how-to-proceed block.
- `agoge-<YYYY-MM-DD>.json` — the sidecar, in the contract's shape. `fixture` is
  the target directory's basename. Every finding needs a non-empty `paths`; a
  finding you cannot anchor to a file belongs in the markdown only.

The summary header is the honesty ledger. A lane with zero findings still states
which of the four statuses applies to it, and why.

### 6. Close

**Interactive**: walk the findings one at a time per `rules/communication.md` —
one packet per message, at least three real options each, recommendation first.
Record accepted / deferred / rejected in the report as you go, then close with
the minutes.

**Unattended** (an autopilot loop, a headless run, or no human to answer): write
the packets and stop. Never auto-emit PRDs, never guess an approval. Say in the
report that the walkthrough is pending.

## The recon prompt

Dispatch `olivia` with:

1. The absolute target repo path.
2. The profile path: `dev/local/agoge-profile.md`, relative to that repo.
3. The `## Strategy profile contract` section from
   `references/finding-contract.md`, pasted verbatim — it names the six sections
   and their order.
4. When refreshing an existing profile: the current `## Pins and vetoes` section,
   pasted verbatim, with the instruction to copy it through unchanged.
5. When creating a fresh profile: the instruction to write
   `Authorization: not asserted` in that section and to say so in her summary.

She writes the profile and returns a summary. She writes nothing else.

## Notes

- Only `verified` findings are defects. `mocked` is a belief about a dependency,
  not the dependency. `unverified` means the lane could not run — report the
  attempt and how far it got.
- Judy on a repo with no browser surface must **skip loudly**. A skipped lane
  that invents findings to look useful is worse than no lane.
- The pack scores itself against `buvis/agoge-gym`: arm a fixture, run this
  skill at `armed/<fixture>`, then `bin/score` the JSON sidecar against the
  manifest. The gym's manifests are the answer key and are never inside an armed
  repo.
- **Scoring vocabulary never enters the target.** Seed ids belong to the gym.
  Keep the scorecard in the gym's own `dev/local/audit-results/`; the report in
  the target says only that scoring happened elsewhere. `bin/verify-seeds`
  enforces this and will refuse a tree that names a seed.
- **Re-arm between scored runs.** The report you just wrote sits in the target's
  `dev/local/` and describes every defect found. `bin/arm` removes the whole
  armed tree, so a fresh arm clears it — but a second run against the same arm
  lets its specialists read the first run's answers.
