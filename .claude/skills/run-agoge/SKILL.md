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
- Path: `references/{browser,data,perf,security}-playbook.md` in this skill's
  directory — per-lane execution doctrine, pasted into the dispatch that needs
  it. `references/authoring-playbook.md` is the master's own, never dispatched.
- Path: `references/prd-emission.md` and
  `scripts/allocate_prd_number.py` — how an accepted finding becomes a backlog
  PRD, and the claim that keeps two writers off one number. Step 9 only.
- Wrapper: `_autopilot_agoge` in the autoclaude drain branch fires one
  unattended run per drained batch. Not needed to run this skill by hand.
- Conventions: `review-work-completion/references/agent-registry.md` (registry
  ownership), `rules/communication.md` (the findings walkthrough).
- CLI: `git`, `python3`.

## Arguments

- *(none)* — the current repo.
- `<repo-path>` — an absolute path to the repo to run against.
- `--refresh-profile` — re-run recon even when the profile is fresh.
- `--authorized <source>` — assert, at invocation, that the target is the
  operator's own or explicitly authorized, where `<source>` names the human act
  it came from (an unattended loop passes its own name). Arms **trudy** only.
  An empty or missing `<source>` is an error: stop and report. Never assert
  anonymously, and never supply a source of your own.
- `--resume <report>` — walk an existing report's packets and record decisions.
  Dispatches nobody. Jump straight to step 9.
- `--decisions <file>` — with `--resume`, take the decisions from a JSON file
  instead of asking. For headless verification, never for a real walkthrough.

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

After a refresh, before anything else, prove the human-owned section survived.
**Do not reach for `git diff`** — `dev/local/` is ignored almost everywhere, so
that diff comes back empty whatever recon did, and a check that cannot fail is
worse than none. Copy `## Pins and vetoes` to a scratch file *before* the
dispatch, extract it again afterwards, and compare the bytes (`cksum` on both).

**If the section changed, stop the run and report it.** Recon rewriting a
human's veto is a defect in the pack, not a detail.

### 3. Dispatch the armed specialists

From the profile's per-specialist strategy, dispatch **only** specialists marked
`armed` and not vetoed. Unarmed and vetoed lanes are reported, never run —
that is the cost gate.

Dispatch every armed specialist **in one message**, one Agent call each, so they
run concurrently. One that fails returns its error and the others are unaffected;
record that lane `unverified` with the failure and finish the run.

Each prompt is assembled from five parts, in this order:

1. The absolute target repo path, and the one-line instruction: run the product,
   do not modify it.
2. That specialist's row from the profile — its tactics and the exact commands
   recon established — plus the mocking strategy.
3. **The lane's playbook**, pasted verbatim from this skill's `references/`:

   | Lane | Playbook |
   |---|---|
   | judy | `browser-playbook.md` |
   | heidi | `data-playbook.md` |
   | peggy | `perf-playbook.md` |
   | trudy | `security-playbook.md` |
   | walter | `browser-playbook.md`, **only** when the profile puts a journey through a page |
   | wendy, olivia | none |

   A lane never authors. If the profile assigns authoring, that is the master's
   job in step 6 — say so in the prompt so the specialist puts its test in the
   finding's `fix` field instead of on disk.
4. The `## Finding contract` section, pasted verbatim.
5. For **trudy** only: the authorization, and the human act it came from. Resolve
   it in this order and stop at the first hit:

   | Source | When | What her prompt carries |
   |---|---|---|
   | `profile` | the profile's `Authorization:` line is asserted (not `not asserted`) | that line verbatim, plus `Asserted by: profile (dev/local/agoge-profile.md)` |
   | `invocation` | `--authorized <source>` was passed | the contract's assertion line, plus `Asserted by: invocation (<source>)` |
   | none | neither | nothing — **do not dispatch her**; report the lane `skipped`, reason "authorization not asserted" |

   The profile wins when both are present: the file in the repo is the more
   specific act. Both routes are a human's — a machine never asserts for itself,
   and recon still may not write that line. Pass the source through verbatim; do
   not invent, shorten or supply one.

   An `--authorized` with an empty source is an error. Stop the run and report
   it, the same rule the decisions file follows in step 9: a path whose whole
   point is that a human authorized it must not guess who.

Keep each prompt under 50 000 bytes — measure it, do not estimate. Recon output
and one playbook are small; this only binds if you paste files in, so do not.

### 4. Audit the statuses

Before anything is merged or written, check every finding that arrived
`verified` against its own evidence, per the finding contract's downgrade rule.
Evidence that quotes a command and its output backs the claim; evidence that
reads the code or names a mock does not, and the finding is downgraded with a
note.

A lane cannot audit its own claim. This step exists because the master is the
only reader who did not make it.

### 5. Dedup

Collapse findings that are the same defect seen from two lanes (a dead
integration also breaks a journey). Key on normalized path plus symptom, not on
wording. On merge: keep the **strictest** severity, union the evidence, and keep
every contributing lane's name.

Do not merge two findings that share a file but not a symptom.

### 6. Author, if the profile assigns it

Only the master authors — every specialist is pinned read-and-run so the armed
tree stays byte-identical while the lanes work. Read
`references/authoring-playbook.md` and follow it: branch, write, run, commit
tests only, return to the branch you started on.

Skip the step, and say so in the report, when the profile assigns no authoring,
no finding survived step 4 as `verified`, or the target's tree is dirty.

### 7. Report

Write both files into the target repo's `dev/local/audit-results/`:

- `agoge-<YYYY-MM-DD>.md` — the human report, in the report contract's shape:
  summary header with per-lane verified / unverified / mocked / skipped counts
  and who was armed, unarmed or vetoed; then one walkthrough packet per finding;
  then the how-to-proceed block.
- `agoge-<YYYY-MM-DD>.json` — the sidecar, in the contract's shape. `fixture` is
  the target directory's basename. Every finding needs a non-empty `paths`; a
  finding you cannot anchor to a file belongs in the markdown only.

**Never overwrite a report.** If that date is taken, suffix yours (`-2`, `-3`).
Two drained batches land on one day often enough, and the report you would
clobber may still be carrying somebody's unwalked packets.

The summary header is the honesty ledger. A lane with zero findings still states
which of the four statuses applies to it, and why. Counts are post-downgrade.
Name the authored branch and its runner command, or say nothing was authored.

It also records **how the security lane was authorized** — the profile line, or
the invocation and the source it named, or neither — in the header and in the
sidecar's `authorization` object. Whether a probe was authorized by a file
somebody wrote in that repo or by the flag on the command that started the run is
exactly the kind of thing a reader cannot reconstruct later, so it is written
down at the time.

### 8. Close

**Interactive**: go to step 9 and walk the findings now.

**Unattended** (an autopilot loop, a headless run, or no human to answer): write
the packets and stop. Never auto-emit PRDs, never guess an approval. End the
report with this line, exactly:

```
> **AGOGE-WALKTHROUGH-PENDING** — run `/run-agoge --resume <path to this file>` to walk these packets and record decisions.
```

That token is how a returning human and the resume path both find an unwalked
report. A run that reaches step 9 removes the line.

An unattended run writes **only** into `dev/local/audit-results/`. It never
touches `dev/local/prds/`: a machine that files its own findings as work has
approved them on the human's behalf.

### 9. Walk the findings

Reachable two ways: an interactive run arriving from step 8, or `--resume
<report>` on a report someone left pending. On the resume path, dispatch nobody
and re-run nothing — the findings are already established, and re-running them
would produce a second set of numbers to reconcile.

Walk them one at a time per `rules/communication.md`: one packet per message, at
least three real options each, recommendation first. Record accepted / deferred /
rejected in the report as you go, then close with the minutes and delete the
pending line.

**With `--decisions <file>`**, read the decisions instead of asking. The file
maps a finding's number in the report to `accept`, `defer` or `reject`, and an
optional option label:

```json
{
  "1": {"decision": "accept", "option": "Invalidate on write"},
  "2": {"decision": "reject"}
}
```

A finding the file does not mention is `deferred` — silence is never consent.
An `option` that matches no option in that packet is an **error**: stop and
report it. Do not map it to the nearest one. The point of this path is that its
output is determined by its input, and a guess breaks exactly that.

Record the minutes exactly as an interactive walk would, and note in the report
that the decisions were scripted, so nobody later reads them as a human's.
This path exists so a headless build can prove the walk works; it is not a way
to run a real walkthrough without a human.

**Accepted findings become PRDs**, one per finding or per cluster the human
approved, in the target repo's `dev/local/prds/backlog/`. Read
`references/prd-emission.md` and follow it. Emission happens on explicit
acceptance and on nothing else: deferred and rejected findings stay in the
report.

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
- The interactive browser fallback is the **master's**, not a lane's. Every
  specialist is pinned to `Read, Bash` and holds no browser tool, so a lane
  cannot reach it however the prompt is worded. Use it only in an interactive
  session, label those findings interactive-run, and never in an unattended run.
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
