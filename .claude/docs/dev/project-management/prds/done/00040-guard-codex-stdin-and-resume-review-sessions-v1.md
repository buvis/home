# Guard Codex Stdin and Resume Review Sessions Across Rework Cycles

## Overview

### Problem Statement

Two defects in how autopilot invokes the codex CLI, both surfaced by the grill-me-codex analysis (2026-07-04):

1. **Silent stdin hang.** `codex exec` reads stdin in addition to its prompt argument; under a non-TTY driver with no EOF it blocks forever at ~0% CPU (verified upstream by the grill-me-codex author, 2026-06-04). Neither of our codex entry points guards stdin: `codex_review_run.py:495` launches `Popen` without `stdin=subprocess.DEVNULL` (child inherits session stdin), and `codex-run.sh:147` runs `codex exec` with no `< /dev/null`. This is the likely root cause of the historical Phase 8 0-CPU doubt-review hang (PRDs 00042-00047 era) that "no longer reproduces": stdin inheritance is environment-dependent, so the hang is intermittent and will return.
2. **Each Phase 4 rework cycle pays a fresh codex context and invites re-litigation.** Bob (codex) starts a new session every cycle. The incremental-review prompt hands him the prior cycle's consolidated findings, but he has no memory of his own critique: settled points get re-argued and new objections appear late (the flip-flop shape behind several review-cycle thrash incidents). `codex exec resume <thread_id>` preserves the session so cycle N+1 verifies fixes instead of re-reviewing from zero.

### Target Users

The autopilot operator. Benefit: one whole class of silent loop hangs eliminated; cheaper, more convergent Phase 4 rework cycles.

### Success Metrics

- Both codex entry points redirect stdin: no codex process launched by autopilot can block waiting for stdin EOF.
- On Phase 4 rework cycles (cycle >= 2), Bob resumes his cycle-1 codex session whenever a thread id is available; a missing/expired thread degrades to a fresh run with a loud note, never a blocked cycle.
- Resumed calls are provably read-only: `codex exec resume` is always passed `-c sandbox_mode="read-only"` (resume rejects `-s`; without `-c` it inherits `config.toml`, which may be `danger-full-access`).
- Reviewer output file contents remain byte-compatible for existing consumers (consolidation script, coverage gate): plain review text at the `-o` path, no JSONL leakage.

## Functional Decomposition

### Capability: Stdin Guard

Close the stdin-inheritance hang in both codex entry points.

#### Feature: DEVNULL stdin in codex_review_run.py

- **Description**: The doubt-review runner's `Popen` gets `stdin=subprocess.DEVNULL`.
- **Inputs**: None (invariant on the existing launch site).
- **Outputs**: codex child process with closed stdin.
- **Behavior**: One-line change to the `subprocess.Popen` call; heartbeat, JSONL logging, and exit codes unchanged.

#### Feature: /dev/null stdin in codex-run.sh

- **Description**: The shell wrapper's `codex exec` invocation gets `< /dev/null`.
- **Inputs**: None.
- **Outputs**: codex child process with immediate stdin EOF.
- **Behavior**: Applied to the codex backend invocation (the documented failure mode); copilot backend untouched.

### Capability: Codex Session Resume

Thread-id capture on cycle 1, resume on cycles >= 2, in the Phase 4 review loop only. Phase 8 (doubt) runs once per PRD and is out of scope.

#### Feature: Thread-id capture (`--emit-thread-id FILE`)

- **Description**: New `codex-run.sh` flag that records the codex session's thread id for later resume.
- **Inputs**: A writable file path; requires `-o OUTPUT_FILE` in the same call.
- **Outputs**: The thread id (from the `{"type":"thread.started","thread_id":"..."}` JSONL event) written to FILE; final review text at the `-o` path exactly as today.
- **Behavior**: codex backend runs `codex exec --json --output-last-message <OUTPUT_FILE> ...` and parses the JSONL stream for `thread.started`. copilot backend: warn on stderr and run one-shot as today (no thread concept). Absent flag: behavior byte-identical to today.

#### Feature: Session resume (`--resume-thread ID`)

- **Description**: New `codex-run.sh` flag that continues a prior codex session instead of starting fresh.
- **Inputs**: A thread id (or a file containing one).
- **Outputs**: Review text at the `-o` path; same exit-code semantics as a fresh run.
- **Behavior**: codex backend runs `codex exec resume "$ID" -c sandbox_mode="read-only" --json --output-last-message <OUTPUT_FILE> ... < /dev/null`. HARD CONTRACT: resume rejects `-s`, so read-only MUST travel via `-c sandbox_mode="read-only"` on every resume call. Empty/missing id, resume exit failure, or copilot backend: log one loud stderr line and fall back to a fresh run (never fail the review because resume broke). `--resume-thread` composes with `--emit-thread-id` (re-writes the same id, keeping the sidecar fresh).

#### Feature: Phase 4 wiring in review-work-completion

- **Description**: Bob's dispatches carry the thread id across cycles via the review file frontmatter.
- **Inputs**: Prior cycle's review file (`{prd-name}-review-{N}.md`) frontmatter.
- **Outputs**: `codex_thread_id: <id>` stamped in each cycle's review file frontmatter, next to the existing `head_sha`.
- **Behavior**: Step 5 cycle 1: Bob's launch adds `--emit-thread-id dev/local/tmp/bob-thread-{id}.txt`. Step 8: stamp the captured id as `codex_thread_id` frontmatter (omit the field when capture failed or Bob was skipped). Step 3 incremental path: read `codex_thread_id` from the same prior review file that supplies `head_sha`; step 5 then adds `--resume-thread <id>` to Bob's launch. Storing the id in the PRD-named review file (not state.json, not a bare sidecar) makes staleness impossible across PRDs and keeps the skill fully standalone outside autopilot. The incremental prompt (prior findings + scoped diff) is unchanged, so the fresh-run fallback loses nothing.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/
├── use-codex/scripts/
│   ├── codex-run.sh                      # Maps to: /dev/null stdin, --emit-thread-id, --resume-thread
│   └── test_codex_run.sh                 # Maps to: Codex Session Resume (stubbed-codex tests, new file)
├── run-autopilot/scripts/
│   ├── codex_review_run.py               # Maps to: DEVNULL stdin
│   └── test_codex_review_run.py          # Maps to: DEVNULL stdin (new assertion in existing suite)
└── review-work-completion/
    ├── SKILL.md                          # Maps to: Phase 4 wiring (steps 3, 5, 8)
    └── scripts/                          # (contract test lands beside existing scripts)
        └── test_codex_resume_contract.py # Maps to: Phase 4 wiring (contract test, new file)
```

### Module: codex-run.sh

- **Maps to capability**: Stdin Guard, Codex Session Resume
- **Responsibility**: Single codex CLI entry point: stdin redirect, thread-id capture, resume with forced read-only sandbox, copilot degradation.
- **Exports**: `--emit-thread-id FILE`, `--resume-thread ID` flags; unchanged `-o` output contract.

### Module: codex_review_run.py

- **Maps to capability**: Stdin Guard
- **Responsibility**: Doubt-review runner launches codex with closed stdin.
- **Exports**: Unchanged CLI and exit codes.

### Module: review-work-completion skill

- **Maps to capability**: Codex Session Resume
- **Responsibility**: Carry `codex_thread_id` through the cycle chain (capture cycle 1, stamp step 8, read step 3, resume step 5).
- **Exports**: The `codex_thread_id` review-file frontmatter field.

### Module: tests

- **Maps to capability**: All
- **Responsibility**: `test_codex_run.sh` uses a stub `codex` binary on PATH (emits a fixed `thread.started` JSONL line, records its argv and stdin state) to pin: stdin redirected, thread file written, resume argv contains `resume <id> -c sandbox_mode="read-only"`, fallback on empty id. `test_codex_review_run.py` gains an assertion that `Popen` is called with `stdin=subprocess.DEVNULL`. `test_codex_resume_contract.py` pins the SKILL.md contract lines (frontmatter field name, step 3 read, step 5 flags).
- **Exports**: Test entry points runnable standalone.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **codex_review_run.py stdin guard**: Independent one-liner plus test.
- **codex-run.sh stdin guard**: Independent redirect on the codex invocation.

### Core Layer (Phase 1)

- **codex-run.sh thread flags**: Depends on [codex-run.sh stdin guard] (same invocation site; resume calls must also carry the redirect).

### Integration Layer (Phase 2)

- **review-work-completion wiring**: Depends on [codex-run.sh thread flags] (consumes both new flags).
- **contract test**: Depends on [review-work-completion wiring].

## Implementation Phases

### Phase 0: Foundation

**Goal**: No autopilot-launched codex process can block on stdin.

**Tasks**:

- [ ] Add `stdin=subprocess.DEVNULL` to the `Popen` call in `codex_review_run.py`; extend `test_codex_review_run.py` with the assertion (no deps) - Acceptance: test fails without the change, passes with it; full existing suite green.
- [ ] Add `< /dev/null` to the codex backend invocation in `codex-run.sh` (no deps) - Acceptance: stub-codex test observes closed/empty stdin.

**Exit Criteria**: Both entry points verified stdin-safe by tests.

### Phase 1: Core

**Goal**: codex-run.sh can capture and resume sessions.

**Tasks**:

- [ ] Implement `--emit-thread-id FILE`: codex backend switches to `--json` + `--output-last-message`, parses `thread.started`, writes FILE; `-o` content stays plain review text; copilot warns and degrades (depends on: Phase 0) - Acceptance: stub test sees thread file with the stub's id and clean `-o` output.
- [ ] Implement `--resume-thread ID`: `codex exec resume "$ID" -c sandbox_mode="read-only"` with stdin redirect; fallback to fresh run on empty id or resume failure, loud stderr note (depends on: Phase 0) - Acceptance: stub test pins the exact resume argv including `-c sandbox_mode="read-only"`; fallback path produces a fresh-run argv plus the warning line.

**Exit Criteria**: `test_codex_run.sh` green; `codex-run.sh` without the new flags remains byte-identical in behavior.

### Phase 2: Integration

**Goal**: Phase 4 rework cycles resume Bob's session end to end.

**Tasks**:

- [ ] Wire review-work-completion: step 5 cycle-1 emit flag, step 8 `codex_thread_id` frontmatter stamp (omit on capture failure/skip), step 3 incremental read, step 5 incremental `--resume-thread` (depends on: Phase 1) - Acceptance: SKILL.md names field, file, and flags exactly; docs-only diff conventions applied for the coverage gate.
- [ ] Write `test_codex_resume_contract.py` pinning the SKILL.md contract lines (depends on: wiring task) - Acceptance: deleting the frontmatter stamp instruction or the resume flag instruction fails the test.

**Exit Criteria**: Contract test green; a live smoke run of `codex-run.sh --emit-thread-id` followed by `--resume-thread` against real codex completes and the resumed reply references the first call's context.

## Test Strategy

### Critical Scenarios

- **Happy path**: Cycle 1 captures thread id into review-file frontmatter; cycle 2 resumes it; codex verifies prior findings without re-litigating. → Expected: resume argv used, output file format unchanged, cycle completes.
- **Edge case**: Prior review file has no `codex_thread_id` (pre-change file, or Bob skipped in cycle 1). → Expected: fresh run, no warning spam beyond one line, cycle completes.
- **Edge case**: copilot backend active (codex CLI absent). → Expected: both flags degrade with a stderr warning; one-shot behavior as today.
- **Error case**: `codex exec resume` exits non-zero (expired/unknown thread). → Expected: loud fallback to fresh exec in the same invocation; reviewer still produces output; the review cycle never pauses.
- **Error case (regression)**: codex launched with inherited TTY-less stdin and no EOF. → Expected: impossible by construction; stub test asserts the redirect on every codex argv path (exec and resume).

## Risks

- **`--json` changes what lands in `-o`**: Mitigated by using codex's `--output-last-message` for the review text (verified working together with `--json` upstream, grill-me-codex 2026-06-04); the stub test pins the `-o` content contract.
- **Resume inherits a writable sandbox**: The single most dangerous failure. Pinned by contract and by test: every resume argv MUST contain `-c sandbox_mode="read-only"`; the stub test fails on its absence.
- **Thread expiry between cycles** (long gaps, codex updates): Fallback-to-fresh keeps the cycle alive; the unchanged incremental prompt (consolidated findings + scoped diff) means a fresh run loses convergence speed, not correctness.
- **Stale thread id crossing PRDs**: Prevented structurally: the id lives in the PRD-named review file frontmatter, which cycle chaining already scopes per PRD.
- **codex CLI resume surface changes across versions** (`resume` accepted `-s` again, flag renames): The stub test pins today's contract; a real-CLI failure trips the loud fallback rather than a hang, and the smoke test in Phase 2 exit criteria catches it at ship time.
