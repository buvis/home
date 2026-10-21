---
default_model: opus
model_tier_rationale: Git selection semantics, shared-index locking and fixed-destination push qualification inside a security boundary
design: run
eligibility: /usr/bin/false
---

# Warrant bookkeeping, part 2: bounded Git seeds

Source: [Discovery 00161](../../discovery/00161-auto-approve-bounded-warrant-requests.md), Must-have 2 and the per-rule tests of Must-have 10. Split from PRD 00165 on 2026-10-19 (backlog review, user decision). Lands after PRD 00165, deployed; PRD 00181 builds on it.

PRD review (2026-10-17, before build) added the agent identity: automatic launches of the buvis seeds run under the agent Git identity, because the human's `~/.gitconfig` signs every commit through 1Password's `op-ssh-sign` and `~/.ssh/config` routes every host through the 1Password agent, and both need a fingerprint. The seeds pin cwd to the worktree root through PRD 00165's fixed-cwd rule.

Lane (backlog review 2026-10-19): hand-built in an attended session like PRDs 00163 and 00166. `eligibility: /usr/bin/false` keeps the unattended drain from picking it, because every deploy target sits outside the sandbox write allowlist. Implementation edits staged copies under `docs/dev/tmp/00180-stage/`; every path below is relative to `~/.claude` unless it starts with `~/`. Agents cannot read the live `~/.config/warrant/rules.json`, so the stage takes the policy from the buvis commit PRD 00165 made. Tests drive rule evaluation and the existing `launch` directly; the resident service arrives in PRD 00181. Deploy is a human warrant act (Phase 2).

## Overview

### Problem Statement
Bookkeeping in the bare buvis repository (add, commit, push) costs a PIN per command. PRD 00165 supplies protected authority and dependency qualification but no rule. This part adds the three bounded Git grammars that may run without the PIN, under the agent identity.

### Target Users
The solo developer and sandboxed agents using the existing warrant request/wait interface against the bare buvis repository.

### Success Metrics
- In fixture repositories, a qualifying add, path-limited commit and fixed-destination fast-forward push run through the allow path without a terminal, PIN, 1Password prompt or ssh-agent; the commit is authored and signed with the agent identity run-agent uses inside the sandbox.
- Tests selected by `-k auto_git_selection`, `-k auto_git_identity` and `-k auto_git_push` pass; unrelated staged entries survive and never enter the selected commit.
- No mise seed activates, and no existing broker refusal becomes eligible for PIN fallback.

## Functional Decomposition

### Capability: Bounded bookkeeping
Separate command grammars prevent path rules from being misapplied to push.

#### Feature: Selected add and commit
- **Description**: Allow only explicit, bounded selections in the fixed buvis repository and worktree.
- **Inputs**: Protected repository identity, the fixed worktree cwd, one or more pathspecs and a commit message for commit.
- **Outputs**: Selected add or commit with unrelated index entries preserved; unsupported syntax remains pending.
- **Behavior**: Accept fixed --git-dir and --work-tree values with cwd resolving to that worktree root (so plain literal pathspecs resolve against the worktree), add followed by -- and explicit pathspecs, or commit -m MESSAGE followed by -- and explicit pathspecs. Support plain literal paths and the established :(top) literal-path form; reject other magic, wildcards, exclusions, option injection, empty/unmatched or ambiguous selections. Reject add -A/-u/--all, bare commit, commit -a, --no-verify, amend and all extra flags. Resolve selected tracked/untracked/deleted paths and directory descendants using literal Git selection semantics rather than prefix text; every selected path must pass PRD 00165's envelope. Commit only the selected paths using Git's selected-path index behavior; glean inspects the exact prospective commit index through PRD 00165's protected copy. Serialize shared-index mutations with Git-compatible locks; abort safely on index races/conflicts, preserving unrelated staged blobs and flags. Do not overwrite the shared index from a stale snapshot. Test deletion, rename, partially staged and unrelated staged-content cases explicitly.

#### Feature: Fixed push
- **Description**: Publish only local master to origin master at the protected destination.
- **Inputs**: Fixed repository/worktree, argv push origin master, protected expected destination and effective Git configuration.
- **Outputs**: A normal fast-forward push or pending/PIN; no file-path filter on history.
- **Behavior**: Reject every additional option/refspec, forced update, deletion, tag, mirror, alternate remote, pushurl multiplicity or additional destination. Verify effective URL rewrites, push configuration and transport dependencies cannot add refs, tags or destinations. Prove the proposed update is fast-forward and retain Git's server-side non-force check for races. Preserve protected required pre-push checks. This deliberately publishes committed history, including human-created commits outside the add/commit selection roots. Read and verify the current remote during qualification; never infer it from the discovery or fetched refs alone. Network/authentication uncertainty fails closed or returns the existing execution failure without broadening authority.

#### Feature: Agent Git identity for automatic launches
- **Description**: Run every automatic buvis launch as the agent, never through the human's 1Password signer or SSH agent.
- **Inputs**: A protected per-rule `env` block; the agent key `~/.ssh/agent_github` and `.pub`; `ssh` and `ssh-keygen` on exec_path; the human's `~/.gitconfig` (`commit.gpgsign=true`, `gpg.ssh.program=op-ssh-sign`) and `~/.ssh/config` (`Host *` routed to the 1Password agent), both left unchanged.
- **Outputs**: Commits authored and committed as `Agent ran by Tomáš Bouška` and signed with the agent key by `ssh-keygen`; pushes authenticated with the agent key and `IdentityAgent=none`; no prompt anywhere.
- **Behavior**: Mirror `~/bin/run-agent` lines 64-81 exactly: `GIT_AUTHOR_NAME`, `GIT_COMMITTER_NAME`, `GIT_CONFIG_COUNT=3` carrying `gpg.format=ssh`, `user.signingkey=~/.ssh/agent_github.pub` and `gpg.ssh.program=ssh-keygen`, plus `GIT_SSH_COMMAND="ssh -i ~/.ssh/agent_github -o IdentitiesOnly=yes -o IdentityAgent=none -o BatchMode=yes"`, with the home directory spelled absolute in the file. Verified 2026-10-17 with `SSH_AUTH_SOCK` unset: the key signs through both the private and the `.pub` path, has no passphrase, and authenticates to GitHub as `tbouska`. The block is literal text in the protected rules file, applied by `execute` after the request's declared env so a request cannot override it, and never accepted from a request (`allowed_env` keeps refusing `GIT_*`). Every executable the block names resolves through `resolve_exe`; the key files enter PRD 00165's dependency manifest (protected by the `~/.ssh` write deny; agents may already read them, so signing with them grants nothing new). One block serves all three seeds. A missing key, an unresolvable executable or an absent block deactivates the seeds; there is no fallback to the human's signer. Human PIN approvals are unchanged and keep the human's identity.

## Structural Decomposition

### Repository Structure

```text
docs/dev/tmp/00180-stage/
├── bin/
│   ├── warrant                         # staged copy of ~/bin/warrant after PRD 00165; Git grammars, selection proofs, push qualification
│   └── tests/test_warrant.py           # staged copy of ~/bin/tests/test_warrant.py; auto_git_* tests
└── .config/warrant/rules.json          # staged from the PRD 00165 buvis commit; three seeds and the agent identity env block
```

Deploy targets mirror the staged paths under `~/`.

### Module: Git seeds
- **Maps to capability**: Bounded bookkeeping
- **Location**: `docs/dev/tmp/00180-stage/bin/warrant`, `docs/dev/tmp/00180-stage/.config/warrant/rules.json`
- **Responsibility**: Separate Git grammars, actual-selection proofs, effective-index checking, fixed push qualification and the fixed-cwd seeds in the staged broker; the agent identity env block in the policy, applied by `execute` (`~/bin/warrant` lines 425-437).
- **Exports**: Three individually qualified allow seeds: add, commit and push. Each carries one why-bounded description. Mise install/reshim candidates are documented as disabled, with no matching allow rule; git apply and claude update have no seed.

### Module: Verification
- **Maps to capability**: Bounded bookkeeping
- **Location**: `docs/dev/tmp/00180-stage/bin/tests/test_warrant.py`
- **Responsibility**: Fake protected sites, local bare remotes, hostile Git configuration, index races and a throwaway fixture key. Tests do not change live policy, contact the real origin or execute hostile helpers.
- **Exports**: Headless unittest cases selected by the filters below.

## Dependency Graph

### Foundation Layer (Phase 0)
No internal dependencies - staged copies are made first.
- **Verification**: staged suite baseline. External prerequisite: PRD 00165, deployed and committed.

### Core Layer (Phase 1)
- **Git seeds**: Depends on [Verification]; commit activation requires PRD 00165's protected glean qualification.

### Integration Layer (Phase 2)
- **Host deploy**: Depends on [Git seeds, Verification]; a human warrant act after the staged suite passes and the review closes.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Stage the deployed broker and policy from PRD 00165.

**Tasks**:
- [ ] Copy `~/bin/warrant` and `~/bin/tests/test_warrant.py` into the staged layout above, and write the policy with `git --git-dir="$HOME/.buvis" --work-tree="$HOME" show HEAD:.config/warrant/rules.json` (no deps) - Premise: PRD 00165 is deployed and buvis tracks its policy; `git --git-dir="$HOME/.buvis" --work-tree="$HOME" ls-files -- ':(top).config/warrant/rules.json'` prints the path. A failed premise means stop and report. Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00180-stage/bin/tests -t docs/dev/tmp/00180-stage/bin/tests -p 'test_warrant.py'` exits 0 before any edit.

**Exit Criteria**: The prerequisite is confirmed and the staged suite is green before any edit.

### Phase 1: Core
**Goal**: Qualify bookkeeping while retaining required checks.

**Tasks**:
- [ ] Implement the selected add/commit seeds and the agent identity env block in `docs/dev/tmp/00180-stage/bin/warrant` and `docs/dev/tmp/00180-stage/.config/warrant/rules.json` (depends on: Phase 0). Acceptance: `-k auto_git_selection` in the staged test file proves literal/top paths, directories, deletions, renames, partial staging and preserved unrelated staged entries; boundary selection, extra flags, bare commits, hostile config and index races never auto-execute. `-k auto_git_identity` proves, with a throwaway fixture key and a fixture gitconfig that names a marker signer, that an automatic commit is authored by the agent name and carries an ssh signature made by ssh-keygen, that the marker signer and a fake agent socket are never touched, that a request declaring GIT_CONFIG_* or GIT_SSH_COMMAND is still refused, that a human PIN on the same request keeps the fixture's human identity, and that a missing key deactivates the seed.
- [ ] Implement the fixed push seed in `docs/dev/tmp/00180-stage/bin/warrant` and `docs/dev/tmp/00180-stage/.config/warrant/rules.json` (depends on: Phase 0). Acceptance: `-k auto_git_push` uses a local bare remote to verify exactly master-to-master fast-forward; it rejects alternate destinations, force, divergent history, extra refs/tags, URL rewrites and writable transport/pre-push dependencies before helper execution. Automatic push launches carry the policy GIT_SSH_COMMAND, and the qualification-time remote check runs with it.

**Exit Criteria**: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00180-stage/bin/tests -t docs/dev/tmp/00180-stage/bin/tests -p 'test_warrant*.py'` passes, including existing PIN/refusal tests. Qualifying fixture repositories perform all three operations; a live seed stays inactive whenever its complete bound cannot be demonstrated. Mise remains PIN-only. Run the fresh-session review on the staged files before Phase 2.

### Phase 2: Integration
**Goal**: Deploy the reviewed staged files (human on the host, or warrant requests the human approves).

**Tasks**:
- [ ] Copy `~/bin/warrant`, `~/bin/tests/test_warrant.py` and `~/.config/warrant/rules.json` from their staged copies with warrant `cp` requests, so the source is hashed (depends on: Phase 1 and its review). Acceptance: `diff` of the two `~/bin` files against their staged copies is empty; the human confirms the same for `rules.json`, which agents cannot read; `~/bin/warrant list` passes preflight.
- [ ] Run the host suite (depends on: deploy). Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'` is green on the host.
- [ ] One commit, then push (depends on: host suite green). Acceptance: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" show --stat HEAD` lists exactly `bin/warrant`, `bin/tests/test_warrant.py` and `.config/warrant/rules.json`; never stage `passphrase.scrypt` or `ledger.jsonl`.

**Exit Criteria**: Host suite green, seeds deployed, commit pushed. Nothing evaluates the spool automatically until PRD 00181.

## Test Strategy

### Critical Scenarios
- **Happy path**: Protected dependencies, a selected PRD commit and a fixed local push → executed results and unchanged unrelated staging; glean checks the exact commit tree; the commit is authored as the agent and signed by ssh-keygen with the agent key.
- **Edge case**: A request from the agent's project cwd stays pending; the same request approved by PIN runs with the human's identity, as today.
- **Error case**: Hostile config, an index race, a divergent push or a missing key → no automatic launch; existing broker hard refusals remain terminal.

## Risks

- **Shared index loss**: Use Git-compatible transactions and race fixtures; never restore an old whole-index snapshot over concurrent work.
- **Agent identity on the host**: Automatic commits and pushes use `~/.ssh/agent_github`, which authenticates as `tbouska` and is already agent-readable, so it adds no authority. It does change provenance: unattended commits read `Agent ran by Tomáš Bouška`, never the human's 1Password-signed identity. A missing or rotated key deactivates the seeds instead of falling back to 1Password.
- **Policy source**: The stage reads the policy from the buvis commit, not the live file. A live edit the human never committed is invisible to this build; Phase 0's premise check and the Phase 2 `diff` confirmation catch drift.
