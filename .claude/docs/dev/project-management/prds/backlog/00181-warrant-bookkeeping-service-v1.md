---
default_model: opus
model_tier_rationale: concurrent claims, crash and replay safety, durable rate accounting and a resident host service
design: run
eligibility: /usr/bin/false
---

# Warrant bookkeeping, part 3: resident service, audit and accounting

Source: [Discovery 00161](../../discovery/00161-auto-approve-bounded-warrant-requests.md), Must-haves 5, 7 and the resident approver of 8. Split from PRD 00165 on 2026-10-19 (backlog review, user decision). Lands after PRDs 00165, 00177 and 00180, deployed. Foreground launch resolves discovery question 2; the 10-second local fast-path target and inactive future-judge defaults resolve A's part of question 3.

PRD review (2026-10-17, before build) added the documented request form: `warrant request` defaults cwd to the agent's project dir and both instruction files teach a bare `commit -m`, so without a documented, test-bound form the shipped seeds stay dormant. Backlog review (2026-10-19, user decision): PRD 00177 lands first, so this service reuses its settle pass and owns the rule that a claimed request is never settled.

Lane (backlog review 2026-10-19): hand-built in an attended session like PRDs 00163 and 00166. `eligibility: /usr/bin/false` keeps the unattended drain from picking it, because every deploy target sits outside the sandbox write allowlist. Implementation edits staged copies under `docs/dev/tmp/00181-stage/`; every path below is relative to `~/.claude` unless it starts with `~/`. `AGENTS.md` and `rules/memory.md` sit inside the project and are edited in place. Deploy is a human warrant act (Phase 2).

## Overview

### Problem Statement
With PRDs 00165 and 00180, protected policy can allow qualifying bookkeeping requests, but nothing evaluates the spool without a human at `approve`, records automatic outcomes, or teaches agents the request shape the seeds accept.

### Target Users
The solo developer and sandboxed agents using the existing warrant request/wait interface against the bare buvis repository.

### Success Metrics
- A qualifying add, path-limited commit and fixed-destination fast-forward push execute without a terminal, PIN, 1Password prompt or ssh-agent. The harmless local-repository fast-path integration test completes each within 10 seconds, including polling, using the documented request form. Network push completion retains the existing broker timeout.
- Tests selected by `-k auto_rate`, `-k auto_service`, `-k auto_fast_path` and `-k auto_documented_form` pass; no judge process runs, and no existing broker refusal becomes eligible for PIN fallback.
- The three command lines documented in `AGENTS.md` and `rules/memory.md` are exactly the lines the seeds accept; a test binds them, so the shipped seeds are not dormant.

## Functional Decomposition

### Capability: Resident execution and durable accounting
Reuse broker one-shot execution and human fallback without adding background installation.

#### Feature: Foreground serve and audit
- **Description**: Add host-side warrant serve, polling once per second, without launchd in v1.
- **Inputs**: Validated spool, protected policy and ledger; the existing human approve command remains available.
- **Outputs**: Existing results for executed requests, pending requests for automatic ineligibility, and visible audit reasons.
- **Behavior**: Start outside the sandbox; sandbox launch fails existing preflight. Never prompt or ping per auto-approval. Share the existing per-request lock with human approval; claim, review, decide and launch under it. Record a durable automatic-execution claim before launch; a crash after claiming never causes replay, and list reports an indeterminate execution for inspection. Each poll first runs PRD 00177's `settle_expired` pass; extend it so a request holding a durable claim is never settled, checked under the same per-request lock. Preserve existing result/status semantics and terminal decisions; do not reinterpret an auto audit line as a finished command before execution. Record decision auto, rule ID, argv, cwd and the identity env keys PRD 00180 applies, alongside existing execution outcome records; escape displayed agent text through `visible`. List exposes automatic outcomes and why pending work did not qualify. Bound diagnostics so polling does not append duplicate events indefinitely. Policy/profile/dependency changes invalidate cached qualification. No edits to request/wait, agent settings or notification behavior.

#### Feature: Durable future-judge rate limiter
- **Description**: Supply tested accounting primitives for B without invoking a model.
- **Inputs**: Protected ledger/lock, clock, exact argv plus canonical cwd and explicit call/approval events.
- **Outputs**: Atomic call reservations and approval admission, reusable by B.
- **Behavior**: Defaults (guess): rolling 3600-second window; at most 10 judge approvals and 20 judge invocations per hour; at most one approval for identical argv and cwd in that window. Count all invocation outcomes and reserve before calling; persist one automatic attempt per request before a future call. Serialize reservations and admissions across processes/restarts, count uncertain crash reservations conservatively and fail closed on corrupt/unwritable state or clock rollback. Deterministic allows consume no judge budget. A ships no model backend, credentials, verdict contract or enabled judge rule; tests drive accounting with synthetic events only. B supplies judge audit fields and real call integration.

### Capability: Documented request form
Agents learn the one request shape the seeds accept.

#### Feature: Documented request form
- **Description**: Teach agents the one request shape that qualifies, and bind the docs to the matcher so the shipped seeds are not dormant.
- **Inputs**: `AGENTS.md` (Dotfiles repo section), `rules/memory.md` (buvis add/commit/push lines), the shipped grammars of PRD 00180.
- **Outputs**: Three documented command lines, the PIN-only forms named beside them, and a test that feeds the lines to the matcher.
- **Behavior**: Today `warrant request` defaults cwd to the agent's project dir and both files teach a bare `commit -m`; under the seeds both wait for the PIN, so without this feature nothing auto-approves. Document, with `--cwd "$HOME"` and absolute `--git-dir="$HOME/.buvis" --work-tree="$HOME"`: `~/bin/warrant request --cwd "$HOME" --reason "..." -- git --git-dir="$HOME/.buvis" --work-tree="$HOME" add -- ':(top)PATH'`, the same prefix with `commit -m "MSG" -- ':(top)PATH'`, and with `push origin master`. State that the default cwd, a bare `commit -m`, `add -A/-u` and any path outside agent-writable roots wait for the PIN as before. Replace the bare `commit -m` lines in `rules/memory.md`. `request`/`wait` code stays unchanged. A test extracts the fenced lines from both files, substitutes the fixture repository and worktree for the fixed values, and asserts each matches its seed and nothing else. The edit lives under agent-writable `~/.claude`; its own commit is the natural first automatic commit.

## Structural Decomposition

### Repository Structure

```text
docs/dev/tmp/00181-stage/
├── bin/
│   ├── warrant                         # staged copy of ~/bin/warrant after PRD 00180; serve, claims, audit/list, rate limiter
│   └── tests/test_warrant.py           # staged copy of ~/bin/tests/test_warrant.py; auto_rate, auto_service, auto_fast_path, auto_documented_form
└── .config/warrant/rules.json          # staged from the PRD 00180 buvis commit; rate defaults
AGENTS.md                               # edited in place; Dotfiles repo section
rules/memory.md                         # edited in place; buvis add/commit/push lines
```

Deploy targets for the staged files mirror their paths under `~/`.

### Module: Service and accounting
- **Maps to capability**: Resident execution and durable accounting
- **Location**: `docs/dev/tmp/00181-stage/bin/warrant`, `docs/dev/tmp/00181-stage/.config/warrant/rules.json`
- **Responsibility**: Host foreground polling, one-shot claims, the claim-aware settle pass, audit/list integration and rate-limit primitives in the staged broker, using existing protected ledger storage.
- **Exports**: New serve CLI; extended list output; internal rate limiter. Reuse `approve_one` and `launch` (`~/bin/warrant` lines 440-474), `record` (lines 275-280), `settle_expired` (PRD 00177) and existing ledger/list helpers without weakening manual behavior.

### Module: Request form docs
- **Maps to capability**: Documented request form
- **Location**: `AGENTS.md`, `rules/memory.md`
- **Responsibility**: The three documented request lines and the PIN-only forms beside them.
- **Exports**: Fenced command lines the binding test extracts.

### Module: Verification
- **Maps to capability**: Resident execution and durable accounting; Documented request form
- **Location**: `docs/dev/tmp/00181-stage/bin/tests/test_warrant.py`
- **Responsibility**: Fake protected sites, local bare remotes, controlled clocks and concurrency/crash tests. Tests do not change live policy, contact the real origin or execute hostile helpers.
- **Exports**: Headless unittest cases selected by the filters below.

## Dependency Graph

### Foundation Layer (Phase 0)
No internal dependencies - staged copies are made first.
- **Verification**: staged suite baseline. External prerequisites: PRDs 00165, 00177 and 00180, deployed and committed.

### Core Layer (Phase 1)
- **Service and accounting**: Depends on [Verification]; judge invocation remains deferred to B.
- **Request form docs**: Depends on [Service and accounting, Verification]; the fast-path test uses the documented lines.

### Integration Layer (Phase 2)
- **Host deploy**: Depends on [Service and accounting, Request form docs, Verification]; human warrant acts after the review closes.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Stage the deployed broker and policy from PRDs 00165, 00177 and 00180.

**Tasks**:
- [ ] Copy `~/bin/warrant` and `~/bin/tests/test_warrant.py` into the staged layout above, and write the policy with `git --git-dir="$HOME/.buvis" --work-tree="$HOME" show HEAD:.config/warrant/rules.json` (no deps) - Premise: `test -f docs/dev/project-management/prds/done/00180-warrant-bookkeeping-git-seeds-v1.md` exits 0 and `rg -n "def settle_expired" docs/dev/tmp/00181-stage/bin/warrant` prints one line, so the seeds and the settle pass are deployed (link-ok: future done path). A failed premise means stop and report. Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00181-stage/bin/tests -t docs/dev/tmp/00181-stage/bin/tests -p 'test_warrant.py'` exits 0 before any edit.

**Exit Criteria**: The prerequisites are confirmed and the staged suite is green before any edit.

### Phase 1: Core
**Goal**: Deliver resident automatic processing, durable accounting and the bound request form.

**Tasks**:
- [ ] Add durable future-judge caps in `docs/dev/tmp/00181-stage/bin/warrant` and `docs/dev/tmp/00181-stage/.config/warrant/rules.json` (depends on: Phase 0). Acceptance: `-k auto_rate` in the staged test file verifies the 11th approval, 21st invocation and duplicate argv/cwd block; failed calls consume budget, concurrent reservations cannot exceed it, restarts do not reroll, and corrupt state/clock rollback fail closed without judge execution.
- [ ] Integrate serve, shared claims, the claim-aware settle pass, audit/list and pending diagnostics in `docs/dev/tmp/00181-stage/bin/warrant` (depends on: rate task). Acceptance: `-k auto_service` covers human/service races, two services, claim/launch crashes, policy reload, expired/malformed requests, escaped ledger fields and no duplicate execution; an expired request holding a durable claim survives the settle pass while an expired unclaimed one settles as refused. Keep agent interfaces unchanged.
- [ ] Document the request form in `AGENTS.md` and `rules/memory.md` and bind it (depends on: serve task). Acceptance: `-k auto_documented_form` extracts the fenced lines from both files and proves each matches its seed with fixture values substituted; `-k auto_fast_path` uses those lines verbatim and proves the 10-second local-operation target without a terminal; the bare commit -m lines are gone from `rules/memory.md`.

**Exit Criteria**: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00181-stage/bin/tests -t docs/dev/tmp/00181-stage/bin/tests -p 'test_warrant*.py'` passes once against the staged files, without modifying live host state. The fresh-session review closes before Phase 2.

### Phase 2: Integration
**Goal**: Deploy the reviewed staged files (human on the host, or warrant requests the human approves).

**Tasks**:
- [ ] Copy `~/bin/warrant`, `~/bin/tests/test_warrant.py` and `~/.config/warrant/rules.json` from their staged copies with warrant `cp` requests, so the source is hashed (depends on: Phase 1 and its review). Acceptance: `diff` of the two `~/bin` files against their staged copies is empty; the human confirms the same for `rules.json`; the host suite `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'` is green.
- [ ] One commit, then push (depends on: host suite green). Acceptance: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" show --stat HEAD` lists exactly `bin/warrant`, `bin/tests/test_warrant.py` and `.config/warrant/rules.json`; never stage `passphrase.scrypt` or `ledger.jsonl`. `AGENTS.md` and `rules/memory.md` stay out of this commit: once `~/bin/warrant serve` runs, their commit through the documented line is the first automatic commit.

**Exit Criteria**: Host suite green, including existing PIN/refusal tests. Foreground service shuts down cleanly; no launchd installation or model calls occur. No automatic launch invokes op-ssh-sign or opens an ssh-agent socket. No acceptance criterion requires manual testing or approval as evidence of correctness.

## Test Strategy

### Critical Scenarios
- **Happy path**: A selected PRD commit and fixed local push through the documented lines → automatic ledger/result records and unchanged unrelated staging, each within 10 seconds.
- **Edge case**: A boundary filename appears only in reason/file contents → deterministic verdict stays governed by actual paths. A request from the agent's project cwd stays pending.
- **Error case**: Expired request, concurrent claimant or mutated proof → no unsafe automatic launch; a crash with uncertain execution never replays; a claimed request is never settled as expired.

## Risks

- **Resident process**: A foreground service in a pane can stop silently. Requests then wait for the PIN, which fails closed; `list` reports why pending work did not qualify.
- **Agent instruction files**: `AGENTS.md` is the shared instruction file for every agent; the binding test keeps the documented lines and the seeds in step.
- **Deferred prerequisites**: B supplies the judge backend, verdict contract and judge audit fields; the rate limiter ships inactive.
