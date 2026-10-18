---
catchup: force
design_gate: user
---

# Autopilot State-Machine Core

> Source discovery: `dev/local/discovery/00050-autopilot-cli.md` (PRD 1 of 3).
> Precondition: overhaul PRDs 00014-00019 have landed. This PRD encodes the
> semantics **as shipped on disk**, not as specced in those PRDs (premise
> discipline, same as 00048).
>
> Boundary note (2026-07-18 backlog review, RESOLVED 2026-07-29): statectl
> (PRD 00068) is the shared low-level atomic writer for state.json field
> mutations (e.g. work's attempts[] appends). The note asked the design phase
> to decide whether this PRD calls or absorbs it. **Decision: neither, here.**
> The design chose absorption, but the scope split moved that work — and the
> sole-writer metric it serves — to PRD 00089. For THIS PRD statectl is left
> untouched and keeps writing through its own lock; the new boundary is used
> only by the code this PRD adds. Do not rip out statectl's writer path here;
> 00089 ports its callers.

**Unparked 2026-07-28** on the loop evaluation
(`dev/local/audit-results/2026-07-28-autopilot-loop-eval.md`). 00052, 00053 and
00060 stay in `hold/` until this PRD proves the extraction. Two constraints
from that report:

- **Absorb the F4 repair.** The park handler must become a callable subcommand,
  not prose in `references/phase-build.md` + `references/recovery.md`. Batch
  202607202320 halted for four days because a session was still reading that
  procedure when the 10800s wall-clock cap killed it - twice. Park is the
  named acceptance case; the same argument applies to every Phase 0 handler.
- **Run this PRD interactively, not via autoclaude** (operator decision,
  2026-07-28). It rewrites the state machine the loop runs on, and F2/F5 say
  large meta-repo PRDs are exactly what the loop cannot finish.

## Scope split (operator decision, 2026-07-29)

The design phase produced
`dev/local/designs/00051-autopilot-state-machine-core-v1-design.md` and its three
reviewer dispatches grew the surface to ~17 tasks — over the 15-task ceiling this
PRD's own F5 amendment introduces, on exactly the PRD class the loop evaluation says
does not finish. So the work is split; the design doc is shared and marks which
sections belong to which PRD.

**THIS PRD (00051) is now the F4 loop repair only** — the durable-state boundary and
the recovery procedures that must stop being prose:

- `cli/state.py` — `transaction()` (the locked read-modify-write primitive),
  `load`, `init`, `restore`
- `cli/schema.py` — `validate` + `SCHEMA_VERSION` stamp + `version_status`
- `cli/records.py` — `record_defer`, `reset_prd_fields`, `do_stall`, `do_park`
- `cli/__main__.py` — dispatch for `init | stall | park | reset-prd | defer | restore`
- port `autopilot_context_cap_hook.py` off its private unlocked writer
- the last-resort `state-write-failed` marker + its wrapper decision-table row
- rewire the Phase 0 park handler, the Loop-mode stall procedure, and the four
  hand-written per-PRD reset lists to call the subcommands

**Deferred to PRD 00089** (`extract-autopilot-lifecycle-core`): the `statectl.py`
absorption and its ~100 call sites, the pure lifecycle ports (`selection.py`,
`frontmatter.py`, `transitions.py`, `resume.py`, `policy.py`), the
`phase-done`/`select`/`frontmatter`/`resume-target`/`check-plan` subcommands, and the
**F5 task ceiling**. 00089 is what makes Success Metric 1 literally true; until it
lands, `statectl.py` remains a second (locked, atomic, but unvalidated) writer.

**Why this cut and not another:** `do_stall`/`do_park` need `transaction()` and
`reset_prd_fields` and nothing else. The statectl absorption is the highest-risk,
lowest-urgency half (100 call sites, a proven file, no bearing on the four-day halt),
so it is the part that waits.

## Review scope note (2026-07-31)

Two commits inside this PRD's review diff range (`work_start_sha 3f559176..HEAD`)
are FOREIGN to the PRD — reviewers must not count them as 00051 work or flag
their absence from the design/tasks:

- `bc00bf23` `fix(autoclaude): widen park-marker staleness bound to the
  review-phase cap` — the operator's own in-flight fix, committed separately
  before task 7 edited the same file (00072 precedent).
- `aad5e404` `fix(work): probe for progress before watchdog kills and
  right-size dispatch briefs` — an operator-requested work-skill protocol fix,
  made after the build→review handoff.

## Overview

### Problem Statement
The deterministic core of the autopilot loop - PRD selection, frontmatter
parse, phase transitions, resume mapping, stall/defer records, and every
`state.json` write - currently lives as SKILL.md prose executed by an LLM. That
burns context each session, drifts under paraphrase, and produced several of
the root-caused loop-halt classes. This PRD extracts that logic into a tested
stdlib Python package that is the **sole writer** of `state.json`, callable via
subcommands. It does not yet own the loop (that is 00052); the existing bash
loop and interactive sessions call into it.

### Target Users
The autopilot loop wrapper, interactive `/run-autopilot` sessions, and
future-you maintaining the state machine.

### Success Metrics

Scoped to the F4 repair (see § Scope split). The full sole-writer metric moves to
PRD 00089.

- **Park and stall are each ONE command.** No session sequences the sub-steps, and
  no reference file describes them as a procedure. `references/phase-build.md`'s
  7-step park handler and `references/recovery.md`'s 5-step stall procedure are
  replaced by a subcommand call plus its exit-code branch table.
- **A kill at any point in park/stall is recoverable, and a test proves it.** Named
  failpoints at every durable boundary; each re-runs the command and asserts the
  end state is correct and the deferred record is written exactly once.
- **One per-PRD reset list exists.** `reset_prd_fields` replaces four hand-written
  lists; the four fields that leak today (`repo_root` in three of them, plus
  `pause_on_ambiguity`, `review_lenses`, `contract_card`, `needs_attention` in all
  four) are cleared, with each change recorded in the migration map.
- **No unlocked writer of `state.json` remains.** `autopilot_context_cap_hook.py`
  writes through `transaction()`; a two-process race test shows neither its write
  nor a concurrent stall is lost. (`statectl.py` still writes, through its own
  lock — unvalidated, and 00089's problem.)
- **A broken writer stops the loop instead of stranding it.** With `cli/` made
  unimportable, the session still writes `state-write-failed` and the wrapper still
  halts with the reason.
- `state.json` stays human-readable (pretty-printed, stable key order).

## Functional Decomposition

### Capability: State ownership
The single boundary through which `state.json` and its sibling records are read
and written.

#### Feature: State read/write boundary
- **Description**: Sole reader/writer of `state.json`; all mutation goes through subcommands.
- **Inputs**: Current on-disk `state.json`, a requested mutation (phase-done, defer, stall).
- **Outputs**: A new pretty-printed `state.json` with stable key order.
- **Behavior**: Load, validate, apply mutation, re-validate, atomic write; never partial-write.

#### Feature: Schema validation
- **Description**: Stdlib-only validation of state shape at write time.
- **Inputs**: A candidate state dict.
- **Outputs**: Pass, or a clear rejection naming the offending field.
- **Behavior**: Reject malformed writes before they touch disk; no third-party validator.

#### Feature: Schema version stamp
- **Description**: Every `state.json` carries a schema version.
- **Inputs**: State dict, current schema version constant.
- **Outputs**: Versioned state; a detection flag when a loaded state is an older version.
- **Behavior**: A resumed old-batch state is detected and surfaced, never silently corrupted.

> **Moved to PRD 00089** by the 2026-07-29 scope split: the *PRD lifecycle logic*
> capability in full (PRD selection, frontmatter parse, phase transitions, resume
> mapping) and the F5 task ceiling. They are pure functions with no bearing on the
> four-day halt this PRD repairs.

### Capability: Recovery procedures (the F4 repair)
The multi-step sequences that must complete or cleanly resume, never half-apply.

#### Feature: Park a sick PRD
- **Description**: Consume the wrapper's `park-requested` marker and sideline the named PRD end-to-end, as one callable command.
- **Inputs**: The marker, the `wip/` listing, `batch.parks_consecutive`, current state.
- **Outputs**: The PRD in `hold/`, a `wrapper_died` deferred record, a reset state with the counter incremented, the marker deleted — or a distinct exit code the caller branches on.
- **Behavior**: Classification stays `park_decision()`; execution becomes transactional. A durable intent record precedes every effect, retries are idempotent, and a crash mid-procedure is reconciled on the next run rather than dropped.

#### Feature: Stall a PRD
- **Description**: The Loop-mode stall procedure as one callable command, for every in-skill stall site.
- **Inputs**: PRD filename, stall site slug, one-line detail, current state.
- **Outputs**: The PRD in `hold/`, a `{"type":"stall"}` deferred record, a reset state, `parks_consecutive` handled per the systemic-breaker rule.
- **Behavior**: Same intent/retry/reconcile protocol as park; the verified move happens before anything else is written, and a failed move leaves the PRD in `wip/` with a recoverable intent.

#### Feature: Per-PRD reset
- **Description**: ONE definition of the per-PRD field reset, replacing four hand-written prose lists.
- **Inputs**: Current state.
- **Outputs**: State with per-PRD scratch cleared and `batch` preserved in full.
- **Behavior**: Clears the four fields that leak today; the excluded fields carry a recorded reason (batch-scoped, or re-derived from the next PRD's frontmatter).

#### Feature: Defer record
- **Description**: Append one record to the batch deferred JSON.
- **Inputs**: PRD filename, batch id, the record.
- **Outputs**: An appended record; the file created when absent.
- **Behavior**: Idempotent by operation id so a retried stall never doubles its record.

### Capability: Loop survivability
The loop must stop loudly when the boundary itself is broken, never relaunch on stale state.

#### Feature: Last-resort failure marker
- **Description**: A halt signal that does not depend on the state boundary.
- **Inputs**: The failure site and its raw error.
- **Outputs**: `dev/local/autopilot/state-write-failed`, and a wrapper that stops on it.
- **Behavior**: Written with a bare file write — no package import, no lock, no schema — so a wedged or unimportable boundary still halts the loop with a reason.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/run-autopilot/cli/
├── __init__.py
├── __main__.py            # Maps to: subcommand dispatch (argparse)
├── state.py               # Maps to: transaction / init / restore / mutate
├── schema.py              # Maps to: validation + version stamp
├── records.py             # Maps to: do_park, do_stall, reset_prd_fields, record_defer
├── migration_map.md       # retired prose behavior -> CLI test crosswalk
├── migration_manifest.txt # independent behavior-ID list (set-equality guard)
└── test_*.py              # pytest beside sources (shared umbrella)
```

(`selection.py`, `frontmatter.py`, `transitions.py`, `resume.py`, `policy.py` are
PRD 00089's.) Plus a thin `autopilot` alias in
`~/.config/bash/plugins/development.plugin.bash` running the **absolute**
`cli/__main__.py` path — never `python3 -m cli`, which lets any cwd containing its
own `cli/` package shadow it.

### Module: state
- **Maps to capability**: Recovery procedures (the durable substrate)
- **Responsibility**: The locked, validated, versioned boundary for `state.json`.
- **Exports**:
  - `transaction(path, fn, *, validator)` - locked read-modify-write; the primitive
  - `load(path)` - read-only inspection, never the read half of a write
  - `init(path, initial)` - exclusive creation
  - `restore(path)` - validated rollback from `<state>.bak`

> **Not built here (YAGNI):** the design doc also specifies
> `state.mutate(path, verb, tokens, value)` and `schema.validate_path`. Both exist
> ONLY to serve the `statectl.py` shim, which is PRD 00089's scope — nothing in
> this PRD calls either (`records.py` and the ported cap hook build whole coherent
> states and use `transaction` + whole-state `validate`). Build them in 00089,
> with the callers that need them.

### Module: schema
- **Maps to capability**: Recovery procedures (write validation)
- **Responsibility**: Stdlib shape/enum validation and the version stamp.
- **Exports**:
  - `validate(state)` - whole-state check, raising on the offending field
  - `version_status(state)` - `unstamped | current | old | future | invalid`

### Module: records
- **Maps to capability**: Recovery procedures
- **Responsibility**: Park, stall, per-PRD reset, and deferred-record writes.
- **Exports**:
  - `do_park(state_path, *, prds_dir, autopilot_dir)` - the whole Phase 0 handler
  - `do_stall(state_path, *, prd, site, detail, prds_dir, autopilot_dir)`
  - `reset_prd_fields(state)` - the one per-PRD reset definition
  - `record_defer(path, prd, batch_id, record)` - idempotent by `op_id`

### Module: cli
- **Maps to capability**: Recovery procedures (entry surface)
- **Responsibility**: argparse dispatch, exit codes, and the human log lines.
- **Exports**:
  - `main(argv)` - dispatch `init | stall | park | reset-prd | defer | restore`

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **schema / state**: the locked, validated, versioned boundary + the crosswalk.

### Core Layer (Phase 1)
- **records**: Depends on [state, schema]

### Integration Layer (Phase 2)
- **cli**: Depends on [records, state]
- **cutover**: Depends on [cli]

## Implementation Phases

### Phase 0: Foundation
**Goal**: Establish the locked, validated boundary and the contract crosswalk.

**Tasks**:
- [ ] Build `migration_map.md` + `migration_manifest.txt` from the on-disk park/stall/reset prose (no deps) - Acceptance: every retired prose behavior has a manifest ID and a map row naming its planned test; a test asserts set equality.
- [ ] Implement `schema.py` (no deps) - Acceptance: a malformed field is rejected naming it; `version_status` returns each of its five classes; the live `state.json` and the `golden/state-*.json` fixtures all validate clean.
- [ ] Implement `state.py` `transaction` + `load` + `init` + `restore` (depends on: schema) - Acceptance: the lock is held across read-modify-write; `fn` raising leaves both `state.json` and `<state>.bak` byte-unchanged; a kill during either write leaves a whole file; `init` is exclusive; `restore` refuses a corrupt backup. Do NOT build `mutate` (00089 owns it with the statectl shim).

**Exit Criteria**: Every write in the package goes through one locked transaction, and a failed mutation can never destroy the rollback point.

### Phase 1: Core
**Goal**: Make park, stall and reset transactional and recoverable.

**Tasks**:
- [ ] Implement `reset_prd_fields` + `record_defer` (depends on: Phase 0) - Acceptance: the reset clears every listed field including the four that leak today, preserves `batch` in full, and the defer append is idempotent by `op_id`.
- [ ] Implement `do_stall` with the intent/retry/reconcile protocol (depends on: reset) - Acceptance: the five named failpoints each recover on re-run with exactly one deferred record; a failed move leaves the PRD in `wip/` and state equal modulo `stall_op`.
- [ ] Implement `do_park` over `do_stall` (depends on: do_stall) - Acceptance: all eight rows of the marker/`stall_op` match table behave as specified; reset + counter + systemic pause land in exactly one commit (asserted by a commit-counter spy); the marker is deleted last.

**Exit Criteria**: A kill at any point in park or stall is recoverable, proven by failpoint tests rather than by argument.

### Phase 2: Integration and cutover
**Goal**: Expose the subcommands, port the second writer, and cut over safely.

**Tasks**:
- [ ] Implement `__main__.py` + the `autopilot` alias (depends on: Phase 1) - Acceptance: every subcommand runs as a subprocess from four cwds including one containing a decoy `cli/` package; every exit code pinned by a case.
- [ ] Port `autopilot_context_cap_hook.py` to `transaction()` (depends on: dispatch) - Acceptance: its private `_atomic_write_state` is gone; a barrier-coordinated two-process test shows neither its write nor a concurrent stall is lost; the hook still never raises into the harness.
- [ ] Add the `state-write-failed` marker + its wrapper decision-table row (depends on: dispatch) - Acceptance: with `cli/` made unimportable the session still writes the marker and the wrapper halts with its detail.
- [ ] Rewire the park handler, the stall procedure and the four reset lists to the subcommands (depends on: all) - Acceptance: no reference file describes park or stall as a multi-step procedure; the doc-contract tests that covered retired prose are retired with a named replacement CLI test in the migration map.

**Exit Criteria**: Park and stall are each one command; no unlocked `state.json` writer remains; the loop halts loudly when the boundary itself is broken.

## Test Strategy

### Critical Scenarios
- **Happy path**: `autopilot park` on a valid marker → Expected: PRD in `hold/`, one deferred record, reset + counter in one commit, marker gone, exit 0.
- **Edge case**: killed after the move, before the deferred append → Expected: re-run completes the operation with exactly one record and a correct reset.
- **Error case**: `transaction`'s mutator raises → Expected: `state.json` AND `<state>.bak` both byte-unchanged, nonzero exit naming the field.

## Risks

- **Self-hosted cutover**: `statectl.py` and the cap hook are used by the session implementing this PRD. Land `cli/` inert first; cut over in one commit with no batch running; canary before continuing (design doc § Risks).
- **The CLI now moves PRD files**: the move is verified at the destination before any record or reset write; a failed verify exits 4 with the PRD still in `wip/`.
- **Semantics drift between spec and shipped prose**: derive the park/stall/reset contract from the on-disk files at execution time, not from this PRD's text.
- **Doc-contract tests**: `test_autopilot_lifecycle.py` asserts prose phrases exist. Prose the CLI absorbs gets its test retired WITH a named replacement, recorded in the migration map — never silently deleted.
