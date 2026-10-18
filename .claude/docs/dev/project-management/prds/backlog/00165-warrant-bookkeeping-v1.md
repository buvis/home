---
default_model: opus
model_tier_rationale: security boundary, Git selection semantics, protected dependency closure and concurrent execution contracts
design: run
lane: full
---

# Deterministic warrant bookkeeping with protected dependencies

Source: [Discovery 00161](../../discovery/00161-auto-approve-bounded-warrant-requests.md), current Requirements and final review entry, 2026-10-17. This is PRD A; PRD B remains unready.

Traceability: discovery Must-haves 1/2/6/8/9/10 map to Authority and Git seeds; 5 maps to accounting; 7 maps to service audit. Must-haves 3/4 and judge-specific parts of 5/7/8/10 belong to B. Final review corrections 1–7 are retained; correction 8 is B's prerequisite. Foreground launch resolves question 2; the 10-second local fast-path target and inactive future-judge defaults resolve A's part of question 3.

PRD review (2026-10-17, before build) added three requirements the discovery did not carry. Automatic launches of the buvis seeds run under the agent Git identity, because the human's `~/.gitconfig` signs every commit through 1Password's `op-ssh-sign` and `~/.ssh/config` routes every host through the 1Password agent, and both need a fingerprint. The Git seeds pin cwd to the worktree root, because the per-session `_PROJECT_DIR` makes a general cwd predicate unprovable. The agent-side request form is documented and test-bound, because the default request cwd and the documented bare `commit -m` would leave the shipped seeds dormant.

## Overview

### Problem Statement
Routine dotfiles bookkeeping repeatedly requires a PIN. Automatic host execution is safe only when code bounds the command, selected paths and every executable dependency. The current protected pre-commit hook loads agent-writable glean code and cannot qualify.

### Target Users
The solo developer and sandboxed agents using the existing warrant request/wait interface against the bare buvis repository.

### Success Metrics
- A qualifying add, path-limited commit and fixed-destination fast-forward push execute without a terminal, PIN, 1Password prompt or ssh-agent; the commit is authored and signed with the agent identity run-agent uses inside the sandbox. The harmless local-repository fast-path integration test completes each within 10 seconds, including polling, using the documented request form. Network push completion retains the existing broker timeout.
- Named envelope, Git, dependency, concurrency and audit tests below pass; unrelated staged entries survive and never enter the selected commit.
- No judge process runs, no mise seed activates, and no existing broker refusal becomes eligible for PIN fallback.
- The three command lines documented in `.claude/AGENTS.md` and `.claude/rules/memory.md` are exactly the lines the seeds accept; a test binds them, so the shipped seeds are not dormant.

## Functional Decomposition

### Capability: Protected automatic authority
Only protected policy and code can authorize execution; inspected agent material remains data.

#### Feature: Strict policy and small matcher
- **Description**: Load a separate protected rules policy with warden-compatible matching syntax and warrant-specific bounds.
- **Inputs**: Broker configuration, profile, protected rules file, schema-validated request and existing reviewed operation.
- **Outputs**: One allow match or a pending request with an escaped diagnostic; invalid policy authorizes nothing.
- **Behavior**: Require schema version, unique rule IDs, boundedness descriptions, command, argPatterns/match/decision and explicit envelope predicates; reject unknown keys/types, unsupported matcher forms, ambiguous multiple matches and untrusted command resolutions. Support only the warden matcher subset actually used by the shipped seeds, with positive and negative compatibility fixtures. No shared warden policy or executable dependency. In A, only allow decisions execute; judge decisions remain pending without a call. Missing/unreadable/invalid policy and engine exceptions preserve human approval. Policy schema details are design work (guess), constrained by these fields and fail-closed behavior.

#### Feature: Profile envelope and boundary backstop
- **Description**: Bound cwd, actual selected paths and protected execution inputs before every automatic launch.
- **Inputs**: Profile-derived grant candidates, explicit write denies, warrant protected paths, rule grammar, canonical paths, each seed's fixed cwd and the launcher's HOME refusal.
- **Outputs**: Proven permission or pending/PIN; the profile is unchanged.
- **Behavior**: Require trusted resolved executables. `_PROJECT_DIR` and `_TMPDIR` are per-session values the broker cannot see, so a general "cwd outside every agent-writable root" predicate is unprovable and does not ship in A. Each seed instead names its one permitted cwd, compared after resolution; the three Git seeds name the resolved worktree root, `$HOME`. Proof that `$HOME` is never agent-writable: no static grant covers it, `_TMPDIR` resolves under the static `/private/var/folders` grant, and run-agent refuses to sandbox HOME as the project dir (`bin/run-agent:42-45`). Pin that refusal the way `test_live_profile_path_matches_run_agent` pins the profile path: the broker rereads the launcher at qualification and deactivates the Git seeds when the refusal text is absent. In the permissive direction (selected paths must lie under an agent-writable root) an unknown runtime root grants nothing. Apply explicit denies before grants, including literal, subtree, regex and project-relative forms. Unknown forms never grant authority; fail the affected evaluation closed. Include warrant code, interpreter, policy, ledger, locks and configuration in the backstop. Check lexical and resolved aliases, deleted paths, symlinks, parent traversal and directory expansion. Do not treat the union of project-root grants as universal permission. Read request files only as untrusted data; never import or execute their contents. Revalidate selection, configuration and dependency identity immediately before launch; changed proof leaves pending without executing.

#### Feature: Protected execution dependency closure
- **Description**: Preserve glean and required Git checks using a protected execution bundle.
- **Inputs**: Current hook, resolved glean source, Python/import paths, Git configuration and helpers, SSH/credential/signing/filter hooks and environment.
- **Outputs**: Protected dependency manifest and qualifying execution profile, or a disabled seed with a diagnostic.
- **Behavior**: Premise: the current hook calls glean through an agent-writable skill link. Recheck before changes; if false, skip the obsolete migration and report, then independently qualify the actual chain. Copy the required glean check into protected warrant storage; never edit the skill link farm or disable checks. Use an absolute protected interpreter in isolated mode and protected helper paths; preserve the check's credential, plaintext, encrypted-blob, local-path and never-ledger exclusions. Treat ledgers/mappings as data; pin authoritative gate configuration and prevent agent edits from weakening mandatory exclusions or redirecting repository/helper execution. Preserve effective-index handling for selected commits. Enumerate and protect all executable/configuration dependencies, including global/system/includes, repository config, hooks, filters, transports, credentials, signing and dynamic interpreter imports. Unknown dependencies, config-discovery paths or writable components disable the affected seed before any helper runs. Protected copies require explicit refresh and renewed qualification after source updates. Do not claim a general-purpose dependency scanner proves arbitrary programs safe.

### Capability: Bounded bookkeeping
Separate command grammars prevent path rules from being misapplied to push.

#### Feature: Selected add and commit
- **Description**: Allow only explicit, bounded selections in the fixed buvis repository and worktree.
- **Inputs**: Protected repository identity, the fixed worktree cwd, one or more pathspecs and a commit message for commit.
- **Outputs**: Selected add or commit with unrelated index entries preserved; unsupported syntax remains pending.
- **Behavior**: Accept fixed --git-dir and --work-tree values with cwd resolving to that worktree root (so plain literal pathspecs resolve against the worktree), add followed by -- and explicit pathspecs, or commit -m MESSAGE followed by -- and explicit pathspecs. Support plain literal paths and the established :(top) literal-path form; reject other magic, wildcards, exclusions, option injection, empty/unmatched or ambiguous selections. Reject add -A/-u/--all, bare commit, commit -a, --no-verify, amend and all extra flags. Resolve selected tracked/untracked/deleted paths and directory descendants using literal Git selection semantics rather than prefix text; every selected path must pass the envelope. Commit only the selected paths using Git's selected-path index behavior; glean inspects the exact prospective commit index. Serialize shared-index mutations with Git-compatible locks; abort safely on index races/conflicts, preserving unrelated staged blobs and flags. Do not overwrite the shared index from a stale snapshot. Test deletion, rename, partially staged and unrelated staged-content cases explicitly.

#### Feature: Fixed push
- **Description**: Publish only local master to origin master at the protected destination.
- **Inputs**: Fixed repository/worktree, argv push origin master, protected expected destination and effective Git configuration.
- **Outputs**: A normal fast-forward push or pending/PIN; no file-path filter on history.
- **Behavior**: Reject every additional option/refspec, forced update, deletion, tag, mirror, alternate remote, pushurl multiplicity or additional destination. Verify effective URL rewrites, push configuration and transport dependencies cannot add refs, tags or destinations. Prove the proposed update is fast-forward and retain Git's server-side non-force check for races. Preserve protected required pre-push checks. This deliberately publishes committed history, including human-created commits outside the add/commit selection roots. Read and verify the current remote during qualification; never infer it from the discovery or fetched refs alone. Network/authentication uncertainty fails closed or returns the existing execution failure without broadening authority.

#### Feature: Agent Git identity for automatic launches
- **Description**: Run every automatic buvis launch as the agent, never through the human's 1Password signer or SSH agent.
- **Inputs**: A protected per-rule `env` block; the agent key `~/.ssh/agent_github` and `.pub`; `ssh` and `ssh-keygen` on exec_path; the human's `~/.gitconfig` (`commit.gpgsign=true`, `gpg.ssh.program=op-ssh-sign`) and `~/.ssh/config` (`Host *` routed to the 1Password agent), both left unchanged.
- **Outputs**: Commits authored and committed as `Agent ran by Tomáš Bouška` and signed with the agent key by `ssh-keygen`; pushes authenticated with the agent key and `IdentityAgent=none`; no prompt anywhere.
- **Behavior**: Mirror `bin/run-agent:64-81` exactly: `GIT_AUTHOR_NAME`, `GIT_COMMITTER_NAME`, `GIT_CONFIG_COUNT=3` carrying `gpg.format=ssh`, `user.signingkey=~/.ssh/agent_github.pub` and `gpg.ssh.program=ssh-keygen`, plus `GIT_SSH_COMMAND="ssh -i ~/.ssh/agent_github -o IdentitiesOnly=yes -o IdentityAgent=none -o BatchMode=yes"`, with the home directory spelled absolute in the file. Verified 2026-10-17 with `SSH_AUTH_SOCK` unset: the key signs through both the private and the `.pub` path, has no passphrase, and authenticates to GitHub as `tbouska`. The block is literal text in the protected rules file, applied by `execute()` after the request's declared env so a request cannot override it, and never accepted from a request (`allowed_env` keeps refusing `GIT_*`). Every executable the block names resolves through `resolve_exe`; the key files enter the dependency manifest (protected by the `~/.ssh` write deny; agents may already read them, so signing with them grants nothing new). One block serves all three seeds. A missing key, an unresolvable executable or an absent block deactivates the seeds; there is no fallback to the human's signer. Human PIN approvals are unchanged and keep the human's identity. The auto ledger line records the applied env keys.

#### Feature: Documented request form
- **Description**: Teach agents the one request shape that qualifies, and bind the docs to the matcher so the shipped seeds are not dormant.
- **Inputs**: `.claude/AGENTS.md` (Dotfiles repo section), `.claude/rules/memory.md` (buvis add/commit/push lines), the shipped grammars.
- **Outputs**: Three documented command lines, the PIN-only forms named beside them, and a test that feeds the lines to the matcher.
- **Behavior**: Today `warrant request` defaults cwd to the agent's project dir and both files teach a bare `commit -m`; under the seeds both wait for the PIN, so without this feature nothing auto-approves. Document, with `--cwd "$HOME"` and absolute `--git-dir="$HOME/.buvis" --work-tree="$HOME"`: `~/bin/warrant request --cwd "$HOME" --reason "..." -- git --git-dir="$HOME/.buvis" --work-tree="$HOME" add -- ':(top)PATH'`, the same prefix with `commit -m "MSG" -- ':(top)PATH'`, and with `push origin master`. State that the default cwd, a bare `commit -m`, `add -A/-u` and any path outside agent-writable roots wait for the PIN as before. Replace the bare `commit -m` lines in `rules/memory.md`. `request`/`wait` code stays unchanged. A test extracts the fenced lines from both files, substitutes the fixture repository and worktree for the fixed values, and asserts each matches its seed and nothing else. The edit lives under agent-writable `~/.claude`; its own commit is the natural first automatic commit.

### Capability: Resident execution and durable accounting
Reuse broker one-shot execution and human fallback without adding background installation.

#### Feature: Foreground serve and audit
- **Description**: Add host-side warrant serve, polling once per second, without launchd in v1.
- **Inputs**: Validated spool, protected policy and ledger; the existing human approve command remains available.
- **Outputs**: Existing results for executed requests, pending requests for automatic ineligibility, and visible audit reasons.
- **Behavior**: Start outside the sandbox; sandbox launch fails existing preflight. Never prompt or ping per auto-approval. Share the existing per-request lock with human approval; claim, review, decide and launch under it. Record a durable automatic-execution claim before launch; a crash after claiming never causes replay, and list reports an indeterminate execution for inspection. Preserve existing result/status semantics and terminal decisions; do not reinterpret an auto audit line as a finished command before execution. Record decision auto, rule ID, argv and cwd alongside existing execution outcome records; escape displayed agent text through visible(). List exposes automatic outcomes and why pending work did not qualify. Bound diagnostics so polling does not append duplicate events indefinitely. Policy/profile/dependency changes invalidate cached qualification. No edits to request/wait, agent settings or notification behavior.

#### Feature: Durable future-judge rate limiter
- **Description**: Supply tested accounting primitives for B without invoking a model.
- **Inputs**: Protected ledger/lock, clock, exact argv plus canonical cwd and explicit call/approval events.
- **Outputs**: Atomic call reservations and approval admission, reusable by B.
- **Behavior**: Defaults (guess): rolling 3600-second window; at most 10 judge approvals and 20 judge invocations per hour; at most one approval for identical argv and cwd in that window. Count all invocation outcomes and reserve before calling; persist one automatic attempt per request before a future call. Serialize reservations and admissions across processes/restarts, count uncertain crash reservations conservatively and fail closed on corrupt/unwritable state or clock rollback. Deterministic allows consume no judge budget. A ships no model backend, credentials, verdict contract or enabled judge rule; tests drive accounting with synthetic events only. B supplies judge audit fields and real call integration.

## Structural Decomposition

### Repository Structure
Paths are relative to the buvis worktree, /Users/bob, not the session cwd. Protected destinations are implementation targets; this PRD-creation task changes none of them.

```text
bin/
├── warrant                                      # Existing broker; all new runtime logic
└── tests/test_warrant.py                         # Existing and new isolated fixtures/tests
.config/
├── buvis/hooks/pre-commit                        # Existing required glean gate
└── warrant/
    ├── rules.json                               # New protected rules, limits and the agent identity env block
    └── runtime/
        ├── glean.py                             # Protected check copy
        ├── glean-policy.json                    # Protected gate configuration/data bounds
        └── dependencies.json                    # Qualified dependency identities
.claude/
├── AGENTS.md                                     # Existing; documented request form (Dotfiles repo section)
└── rules/memory.md                               # Existing; buvis add/commit/push lines
.ssh/
├── agent_github                                  # Existing agent key; push identity for automatic launches
└── agent_github.pub                              # Signing key for automatic commits
```

### Module: Authority
- **Maps to capability**: Protected automatic authority
- **Responsibility**: Strict loader, matcher, deny-aware envelope and dependency qualification in bin/warrant; protected policy and runtime artifacts above. Reuse `review` (`bin/warrant:370-418`), `resolve_exe` (`bin/warrant:325-340`), and the existing profile/trust helpers (`bin/warrant:187-247`).
- **Exports**: Internal broker policy evaluation; no new public Python API required.
- New symbols: `.config/warrant/rules.json`, `.config/warrant/runtime/glean.py`, `.config/warrant/runtime/glean-policy.json`, `.config/warrant/runtime/dependencies.json`

### Module: Git seeds
- **Maps to capability**: Bounded bookkeeping
- **Responsibility**: Separate Git grammars, actual-selection proofs, effective-index checking, fixed push qualification and the fixed-cwd rule with its launcher pin in bin/warrant; the agent identity env block in .config/warrant/rules.json, applied by `execute` (`bin/warrant:425-437`); protected glean integration in .config/buvis/hooks/pre-commit; the documented request form in .claude/AGENTS.md and .claude/rules/memory.md.
- **Exports**: Three individually qualified allow seeds: add, commit and push. Each carries one why-bounded description. Mise install/reshim candidates are documented as disabled, with no matching allow rule; git apply and claude update have no seed.

### Module: Service and accounting
- **Maps to capability**: Resident execution and durable accounting
- **Responsibility**: Host foreground polling, one-shot claims, audit/list integration and rate-limit primitives in bin/warrant, using existing protected ledger storage.
- **Exports**: New serve CLI; extended list output; internal rate limiter. Reuse `approve_one` and `launch` (`bin/warrant:440-475`), `record` (`bin/warrant:275-281`) and existing ledger/list helpers without weakening manual behavior.

### Module: Verification
- **Maps to capability**: All three capabilities
- **Responsibility**: Extend bin/tests/test_warrant.py and ProfileCase with fake protected sites, local bare remotes, hostile inputs, controlled clocks and concurrency/crash tests. Tests do not change live policy, contact the real origin or execute hostile helpers.
- **Exports**: Headless unittest cases selected by the filters below; no separate mirror test file.

## Dependency Graph

### Foundation Layer (Phase 0)
- **Authority**: No new module dependencies; builds on the existing warrant broker/profile parser.
- **Verification**: No new dependencies; extends the existing unittest fake site.

### Core Layer (Phase 1)
- **Git seeds**: Depends on [Authority, Verification]; commit activation requires protected glean qualification.

### Integration Layer (Phase 2)
- **Service and accounting**: Depends on [Authority, Git seeds, Verification]; judge invocation remains deferred to B.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Establish automatic authority without enabling unproven execution.

**Tasks**:
- [ ] Implement strict rules loading/matching in bin/warrant and the disabled-by-default policy at .config/warrant/rules.json (no deps). Acceptance: bin/tests/test_warrant.py tests selected by unittest -k auto_policy pass for valid rules, unknown keys, unsupported syntax, ambiguous matches and untrusted executable resolution; no model process is launched.
- [ ] Add deny-aware envelope and protected dependency qualification in bin/warrant (depends on: preceding task). Acceptance: tests selected by -k auto_envelope in bin/tests/test_warrant.py cover every supported deny form, the per-seed fixed cwd (the worktree root passes; the agent's project dir and every static root pend), the launcher HOME-refusal pin (present qualifies, absent deactivates the Git seeds), symlink swaps, warrant backstop and exception fallback; an always-yes stub cannot bypass bounds.

**Exit Criteria**: Invalid/unproven policy or dependencies produce pending work, with existing hard refusals preserved.

### Phase 1: Core
**Goal**: Qualify bookkeeping while retaining required checks.

**Tasks**:
- [ ] Prepare protected glean runtime and manifest at .config/warrant/runtime/glean.py, .config/warrant/runtime/glean-policy.json and .config/warrant/runtime/dependencies.json; update .config/buvis/hooks/pre-commit and bin/warrant qualification (depends on: Phase 0). Acceptance: bin/tests/test_warrant.py -k auto_dependencies rechecks the migration premise, proves required glean exclusions and prospective-index behavior, and leaves planted import/hook/helper markers absent. Unknown or writable dependencies keep seeds inactive; no skill source or profile is edited.
- [ ] Implement selected add/commit seeds in bin/warrant and .config/warrant/rules.json (depends on: protected glean task). Acceptance: bin/tests/test_warrant.py -k auto_git_selection proves literal/top paths, directories, deletions, renames, partial staging and preserved unrelated staged entries; boundary selection, extra flags, bare commits, hostile config and index races never auto-execute. -k auto_git_identity proves, with a throwaway fixture key and a fixture gitconfig that names a marker signer, that an automatic commit is authored by the agent name and carries an ssh signature made by ssh-keygen, that the marker signer and a fake agent socket are never touched, that a request declaring GIT_CONFIG_* or GIT_SSH_COMMAND is still refused, that a human PIN on the same request keeps the fixture's human identity, and that a missing key deactivates the seed.
- [ ] Implement fixed push seed in bin/warrant and .config/warrant/rules.json (depends on: Phase 0 dependency qualification). Acceptance: bin/tests/test_warrant.py -k auto_git_push uses a local bare remote to verify exactly master-to-master fast-forward; rejects alternate destinations, force, divergent history, extra refs/tags, URL rewrites and writable transport/pre-push dependencies before helper execution. Automatic push launches carry the policy GIT_SSH_COMMAND, and the qualification-time remote check runs with it.

**Exit Criteria**: Qualifying fixture repositories perform all three operations; the live seed stays inactive whenever its complete bound cannot be demonstrated. Mise remains PIN-only.

### Phase 2: Integration
**Goal**: Deliver resident automatic processing and durable accounting.

**Tasks**:
- [ ] Add durable future-judge caps in bin/warrant and .config/warrant/rules.json (depends on: Phase 0). Acceptance: bin/tests/test_warrant.py -k auto_rate verifies the 11th approval, 21st invocation and duplicate argv/cwd block; failed calls consume budget, concurrent reservations cannot exceed it, restarts do not reroll, and corrupt state/clock rollback fail closed without judge execution.
- [ ] Integrate serve, shared claims, audit/list and pending diagnostics in bin/warrant (depends on: Phase 1 and rate task). Acceptance: bin/tests/test_warrant.py -k auto_service covers human/service races, two services, claim/launch crashes, policy reload, expired/malformed requests, escaped ledger fields and no duplicate execution; -k auto_fast_path proves the 10-second local-operation target without a terminal. Keep agent interfaces unchanged.
- [ ] Document the request form in .claude/AGENTS.md and .claude/rules/memory.md and bind it (depends on: Phase 1). Acceptance: bin/tests/test_warrant.py -k auto_documented_form extracts the fenced lines from both files and proves each matches its seed with fixture values substituted; -k auto_fast_path uses those lines verbatim; the bare commit -m lines are gone from rules/memory.md.

**Exit Criteria**: Host command `/opt/homebrew/bin/python3 -m unittest discover -s /Users/bob/bin/tests -t /Users/bob/bin/tests -p 'test_warrant*.py'` passes, including existing PIN/refusal tests. Foreground service shuts down cleanly; no launchd installation or model calls occur. No automatic launch invokes op-ssh-sign or opens an ssh-agent socket. Protected deployment uses warrant when denied; no acceptance criterion requires manual testing or approval as evidence of correctness. Preserve the fresh-session full review boundary before implementation completion.

## Test Strategy

### Critical Scenarios
- **Happy path**: Protected dependencies, selected PRD commit and fixed local push → automatic ledger/result records and unchanged unrelated staging; glean checks the exact commit tree; the commit is authored as the agent and signed by ssh-keygen with the agent key.
- **Edge case**: A boundary filename appears only in reason/file contents → deterministic verdict stays governed by actual paths; text does not authorize or veto a rule. Replays touching the Seatbelt profile or warrant config → PIN, not automatic execution. A request from the agent's project cwd stays pending; the same request approved by PIN runs with the human's identity, as today.
- **Error case**: Invalid policy, unsupported profile/config dependency, expired request, concurrent claimant or mutated proof → no unsafe automatic launch; existing broker hard refusals remain terminal. A crash with uncertain execution never replays.

## Risks

- **Git indirect execution**: Configuration and helpers create hidden authority. Qualify a narrow protected execution profile and test planted dependencies; leave unsupported live configurations on PIN rather than bypassing glean or required checks.
- **Protected copy drift**: Glean source remains maintained in agent-skills. Pin the copied version and dependency manifest; refresh deliberately through warrant and requalify before activation.
- **Shared index loss**: Use Git-compatible transactions and race fixtures; never restore an old whole-index snapshot over concurrent work.
- **Deployment boundary**: Protected destinations and bare-repository writes may require human warrant approval. Prepare recoverable artifacts and automated fixture evidence first; never approve requests or work around denials.
- **Deferred prerequisites**: PRD B requires a useful in-envelope judged operation, explicit yes/no rubric and benign/hostile examples (discovery question 8), then backend isolation/model/login and numerical fixture decisions. Mise requires demonstrated installer/reshim dependency and effect bounds (question 7). None is an unresolved implementation decision for A; no hard credit-spend claim is made.
- **Agent identity on the host**: Automatic commits and pushes use `~/.ssh/agent_github`, which authenticates as `tbouska` and is already agent-readable, so it adds no authority. It does change provenance: unattended commits read `Agent ran by Tomáš Bouška`, never the human's 1Password-signed identity. A missing or rotated key deactivates the seeds instead of falling back to 1Password.
- **Launcher pin**: The fixed-cwd proof rests on text in `bin/run-agent`. A refactor that keeps the HOME refusal but rewords it deactivates the Git seeds until the pin is updated; that is the intended failure direction.
