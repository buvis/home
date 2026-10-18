# Close the Bash hole in the unattended write fence

## Status (2026-08-26, fast-track build) — DONE / LIVE

IMPLEMENTED, reviewed (5 independent reviewers: cora/opus, mallory/opus,
blake/sonnet-blind, codex, gemini), RELEASED, and INSTALLED. All phases done; 12
review-found bypasses fixed and re-verified. Minutes:
`dev/local/reviews/00145-review-1.md`. Design note:
`dev/local/designs/00145-close-bash-hole-in-write-fence-v1-design.md`.

- warden **v0.14.0** released (commit 7610ab6 + tag), central marketplace bumped
  (claude-plugins c4d06dc), plugin updated to 0.14.0 in the user cache.
- Tests: warden vitest 1488 pass; hooks pytest 970 pass; parity 8 pass + 42
  subtests against the INSTALLED 0.14.0 hook (no override, no skip).
- Live installed hook denies e.g. `timeout 5 cp README.md ../other-repo/README.md`
  (exit 2). Fully live for the next session/batch (current session keeps the old
  hook in memory until restart).

buvis commit 3dc6849b carries the Python-hook hardening + parity gate + rules doc.

## Overview

### Problem Statement

The unattended write fence gates four tools and no more. `hooks/dispatch.py` registers it as
`Route("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit", "enforce_write_scope", ...)`, so every
write that travels through Bash walks straight past it: shell redirects, `tee`, `cp`, `mv`,
`sed -i`, `install`, `dd`, and any `python3 script.py` that opens a file for writing.

This is not theoretical. On 2026-08-25 the PRD 00140 batch ran with session repo `~/.claude`
(PID 5898, cwd `/Users/bob/.claude`) and its edits landed in
`~/git/src/github.com/buvis/autopilot`, a different repo. That is precisely the cross-repo write
the fence exists to stop. It is the second time this class has fired: batch 202608180438
(2026-08-18) had an unattended subagent edit a file in a synced directory outside the repo, which
a sync daemon then auto-committed and pushed. The fence was built for that incident and still
does not cover the path the next one will take.

A second, smaller defect sits in the same file. `main()` wraps its whole body in
`except Exception: ... allow()`, so any error permits the write and prints `policy hook degraded:`
to stderr, which nobody reads during an unattended run. A probe of the live hook with 7 malformed
payloads disarmed it 7 times out of 7. It is not reachable through the harness today, because
off-schema `tool_input` is rejected before dispatch (an `Edit` carrying an extra `edits` key
returns `InputValidationError` and no write happens), so this is a latent defect rather than a
live bypass. It is one refactor away from being live, and shipping a Bash gate on top of a hook
that fails open would be building on sand.

### Target Users

The operator running unattended autopilot batches (`CLAUDE_UNATTENDED=1`), who cannot watch a
headless session and needs the blast radius bounded by construction rather than by attention.

### Success Metrics

- Every out-of-scope Bash write in the test corpus is denied while the fence is armed. Target 100%,
  measured by the new parity suite, not by inspection.
- Zero of the 7 probed malformed payloads disarm the hook (today: 7 of 7 disarm it).
- No regression in allowed traffic: the existing warden suite plus a new in-scope corpus of at
  least 20 real batch commands stays green, so the gate costs no false denials.

## Functional Decomposition

### Capability: Bash write gating

Deny, during an armed unattended run, any Bash command whose write target resolves outside the
session's allowed roots.

#### Feature: Out-of-scope write denial

- **Description**: A warden path-target policy denies Bash writes landing outside the session scope.
- **Inputs**: The parsed command from warden's shell AST; the session cwd; the allowed root set.
- **Outputs**: An allow or deny decision, with the offending resolved path in the deny reason.
- **Behavior**: Warden already parses shell into an AST including redirects (`parser.ts:305`,
  `parser.ts:321`) and already resolves path targets with `{{cwd}}` expansion and glob matching
  (`targets.ts`). The policy expresses the same root set the Python hook computes: the session
  repo, its `dev/local`, `TMPDIR`, and the static temp roots. A write target outside every root is
  denied. Reads are untouched. Whether `PathPolicy` can express allow-list ("deny unless inside")
  polarity, or whether it needs a code change in the warden repo, is settled in the design step
  (guess).

#### Feature: Unattended arming

- **Description**: The policy is inert in interactive sessions and active only when the batch marker is set.
- **Inputs**: `CLAUDE_UNATTENDED`, and the `_AUTOPILOT_WRITE_SCOPE` kill switch.
- **Outputs**: Policy active or bypassed, matching the Python hook's arming exactly.
- **Behavior**: Same three-state contract the hook uses: no marker means allow everything; marker
  plus `_AUTOPILOT_WRITE_SCOPE=off` means allow everything and say so; marker alone means enforce.
  `evaluator.ts` already reads `process.env` and the suite already carries `unattended.test.ts`, so
  an env-aware evaluation path exists; whether it is reachable from config alone is settled in the
  design step (guess).

#### Feature: Write-command coverage

- **Description**: The policy covers the commands that actually write, not just the ones warden lists today.
- **Inputs**: The command name and its parsed arguments and redirects.
- **Outputs**: The set of paths the command would write.
- **Behavior**: `targets.ts` defines `PATH_COMMANDS = ['rm', 'chmod', 'chown', 'cp', 'mv', 'tee',
  'mkdir', 'rmdir', 'touch', 'ln']`. That list misses the common write vectors: `>` and `>>`
  redirects, `sed -i`, `install`, `dd of=`, and interpreter one-liners. Redirects matter most,
  since they are how a shell writes a file by default. Coverage is a named list, and anything
  outside it is recorded as a known gap rather than assumed safe.

### Capability: Fence robustness

Stop the Python hook from waving writes through when it meets input it did not expect.

#### Feature: Non-string target filtering

- **Description**: `_targets` and `_resolve` skip entries that are not strings, so a malformed payload yields no targets instead of an exception.
- **Inputs**: The `tool_input` dict from the PreToolUse payload.
- **Outputs**: A list of string paths, possibly empty.
- **Behavior**: `tool_input.get("edits")` entries that are not dicts are skipped; `file_path` and
  `notebook_path` values that are not strings are skipped. The outer `except Exception: allow()`
  stays as a last resort for genuine hook bugs. This removes all 7 probed fail-open paths without
  changing what happens when the hook is truly broken.

### Capability: Scope parity

Keep the two enforcement points agreeing on one root set, so a future scope change cannot leave
half the fence behind.

#### Feature: Shared root definition

- **Description**: One documented root set, asserted identical across the hook and the warden policy.
- **Inputs**: A session cwd fixture.
- **Outputs**: A pass or fail on set equality.
- **Behavior**: A test computes the hook's `_allowed_roots` for a fixture cwd, derives the roots
  the warden policy resolves for the same cwd, and fails if they differ. This is the guard against
  the split-brain risk the two-system design introduces.

## Structural Decomposition

### Repository Structure

```
~/.claude/                                    # Maps to: session repo under test
├── warden.yaml                               # Maps to: Bash write gating
├── hooks/
│   ├── enforce_write_scope.py                # Maps to: Fence robustness
│   ├── dispatch.py                           # Maps to: Scope parity (route table)
│   └── tests/
│       ├── test_enforce_write_scope.py       # Maps to: Non-string target filtering
│       └── test_write_scope_parity.py        # Maps to: Shared root definition (new)
└── rules/
    └── claude-tooling.md                     # Maps to: the two-point fence, documented

~/git/src/github.com/buvis/claude-warden/     # only if config cannot express the policy
└── src/
    ├── targets.ts                            # Maps to: Write-command coverage
    └── config-schema.ts                      # Maps to: Unattended arming
```

### Module: warden-scope-policy

- **Maps to capability**: Bash write gating
- **Responsibility**: Deny out-of-scope Bash writes while a batch is armed.
- **Exports**:
  - `warden.yaml` targets block - the path policy and its root set
  - deny reason string - names the resolved path and the roots that were allowed

### Module: write-scope-hook

- **Maps to capability**: Fence robustness
- **Responsibility**: Gate the four structured edit tools without failing open on odd input.
- **Exports**:
  - `_targets()` - write paths from a payload, non-strings skipped
  - `_allowed_roots()` - the canonical root set both enforcement points must agree on

### Module: scope-parity-tests

- **Maps to capability**: Scope parity
- **Responsibility**: Fail loudly when the two enforcement points drift apart.
- **Exports**:
  - `test_write_scope_parity.py` - root-set equality and a shared out-of-scope corpus

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **write-scope-hook**: Provides the canonical root set and stops failing open.

### Core Layer (Phase 1)

- **warden-scope-policy**: Depends on [write-scope-hook] for the root set it must mirror.

### Integration Layer (Phase 2)

- **scope-parity-tests**: Depends on [warden-scope-policy, write-scope-hook]

## Implementation Phases

### Phase 0: Foundation

**Goal**: The Python hook stops failing open, and its root set is documented as the shared contract.

**Tasks**:

- [ ] Filter non-string entries in `_targets` and `_resolve` (no deps) - Acceptance: the 7-payload
      probe (non-string `file_path`, `edits` list of non-dicts, `edits` as dict, `edits` as string,
      `edits` entry non-dict with a valid sibling, `tool_input` as list, `file_path` as list) all
      return exit 2 against an out-of-scope target, and none print `policy hook degraded`.
- [ ] Pin the root set as the shared contract in a docstring and one test (no deps) - Acceptance:
      `test_enforce_write_scope.py` asserts `_allowed_roots` for a fixture cwd equals the documented
      list, and the whole hook suite passes.

**Exit Criteria**: `python3 -m pytest ~/.claude/hooks/tests/test_enforce_write_scope.py` passes and
the probe finds zero fail-open payloads.

### Phase 1: Core

**Goal**: Bash writes outside the session scope are denied while a batch is armed.

**Tasks**:

- [ ] Confirm whether `PathPolicy` expresses deny-unless-inside polarity and env-gated arming, and
      pick config-only or a warden code change (depends on: Phase 0) - Premise: `~/.claude/warden.yaml`
      today has `alwaysDeny`, `alwaysAllow` and `rules` but no `targets` block. Re-check at execution
      time; if a `targets` block already exists, extend it instead of adding one. Acceptance: the
      design doc names the chosen path and cites the warden source that supports it.
- [ ] Add the path policy with the Phase 0 root set (depends on: Phase 0) - Acceptance: with
      `CLAUDE_UNATTENDED=1`, `warden` denies `echo x > /tmp/../etc/out-of-scope.txt` and every
      command in the out-of-scope corpus, and allows the same writes inside the session repo.
- [ ] Cover redirects, `sed -i`, `install`, and `dd of=` as write targets (depends on: Phase 0) -
      Premise: `targets.ts` `PATH_COMMANDS` lists ten commands and none of these four. Re-check at
      execution time. Acceptance: each of the four is denied against an out-of-scope path and allowed
      in-scope; any vector left uncovered is named in the PRD's known-gaps list, not left silent.
- [ ] Match the hook's three-state arming (depends on: Phase 0) - Acceptance: unset marker allows;
      marker plus `_AUTOPILOT_WRITE_SCOPE=off` allows and emits the disarm line; marker alone enforces.

**Exit Criteria**: The out-of-scope corpus is denied and the in-scope corpus of at least 20 real
batch commands is allowed, both under one command.

### Phase 2: Integration

**Goal**: The two enforcement points cannot drift apart unnoticed.

**Tasks**:

- [ ] Add `test_write_scope_parity.py` (depends on: Phase 1) - Acceptance: the test fails when the
      warden root set and `_allowed_roots` disagree for a fixture cwd, proven by a deliberate skew
      in the test itself.
- [ ] Document the two-point fence in `rules/claude-tooling.md` (depends on: Phase 1) - Acceptance:
      the file states that Bash is gated by warden and edit tools by the hook, and names both root
      sources; a doc test asserts both paths appear.

**Exit Criteria**: Parity suite green, and the rules file names both enforcement points.

## Test Strategy

### Critical Scenarios

- **Happy path**: armed batch writes `dev/local/tmp/x.txt` inside its session repo via
  `echo x > dev/local/tmp/x.txt` → Expected: allowed, no prompt, no deny line.
- **Happy path**: armed batch runs `rg foo /etc/hosts` (a read outside scope) → Expected: allowed,
  because the fence gates writes, not reads.
- **Edge case**: armed batch runs `sed -i '' s/a/b/ ../../other-repo/file.py` → Expected: denied,
  with the resolved absolute path in the reason, proving relative escapes resolve before matching.
- **Edge case**: unarmed interactive session runs the same command → Expected: allowed, since the
  fence must stay invisible outside batches.
- **Error case**: hook meets a payload it cannot parse → Expected: no targets, no exception, and the
  write is judged on the targets it did find rather than waved through.
- **Error case**: warden binary missing or erroring during a batch → Expected: the failure is loud
  in the batch record, not a silent allow.

## Known gaps (recorded at build, 2026-08-26)

Gated by neither enforcement point; each is a named gap, not a covered case. Mirrored in warden
`docs/guide/write-scope.md`:

- Interpreter programs: `python3 script.py`, `python3 -c ...`, `node -e ...` (warden's script
  scanner judges danger, not location).
- `git -C /other ...`, `gh`, and other tools that write through their own path arguments.
- Archive and sync tools: `tar -C`, `unzip -d`, `rsync`, `zip`, `patch`.
- In-place editors other than `sed`: `perl -i`, `ruby -i`, `awk -i inplace`.
- `curl -o` / `wget -O` output files.
- Anything reached through an MCP tool.
- A session that `cd`s into another repo moves the hook's root 1 with it (root 1 is derived from
  the payload cwd; `cd` persists across Bash calls). Pre-existing, unchanged by this PRD.

Deviation from the Phase 0 acceptance line: 6 of the 7 malformed payloads exit 2 on the
surviving out-of-scope target; `tool_input` as a list carries no target and exits 0 silently.
None print `policy hook degraded`.

## Risks

- **Over-blocking breaks unattended runs**: a false deny stalls a batch with nobody watching.
  Mitigation: build the in-scope corpus from real batch transcripts first, require it green before
  the policy arms, and keep `_AUTOPILOT_WRITE_SCOPE=off` as the one-batch escape hatch.
- **Split-brain between two enforcement points**: the hook and warden could disagree after a future
  scope change. Mitigation: the Phase 2 parity test is the whole point of that phase.
- **Work spans two repos**: if the policy needs a warden code change, that lands in
  `~/git/src/github.com/buvis/claude-warden`, outside the session repo, and the fence itself will
  block it. Mitigation: export `_AUTOPILOT_WRITE_SCOPE_EXTRA="$HOME/git/src/github.com/buvis/claude-warden"`
  for that batch, and prefer the config-only path so the question never arises.
- **Latency on every Bash call**: warden already runs on each command, so the marginal cost is the
  target resolution only. Mitigation: measure before and after on the in-scope corpus, and record
  the delta rather than assuming it is free.
- **Bash is not the last hole**: an MCP tool or a future write path is gated by neither point.
  Mitigation: the rules file states the fence covers Bash and the four edit tools, and nothing else,
  so the next gap is a known gap.
