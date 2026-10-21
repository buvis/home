---
design: run
default_model: opus
model_tier_rationale: launcher trust predicates, bootstrap ordering and cross-cutting scheduling changes
eligibility: /usr/bin/false
---
# Confine scheduled repository jobs

Source: [Discovery 00167](../../discovery/00167-close-launchd-escapes-through-agent-writable-scripts.md). Created 2026-10-19 after the user requested the missing PRDs.

Authoring decisions: The user confirmed preserving both jobs inside the agent sandbox, including the agent commit identity. Use the cellar repository as the fixed project directory for both launch paths. Keep human-triggered tools and cron outside this implementation; retain cron as an unverified inventory item.

Lane (backlog review 2026-10-19): hand-built in an attended session like PRDs 00163 and 00166. `eligibility: /usr/bin/false` keeps the unattended drain from picking it, because every deploy target sits outside the sandbox write allowlist. Implementation edits staged copies under `docs/dev/tmp/00174-stage/`; every path below is relative to `~/.claude` unless it starts with `~/`. Tests load the staged launcher and plists, never the installed live copies. Build acceptance is headless; the Phase 3 deploy tasks are human warrant acts, as in PRD 00166 Phase 1. Schedule activation, the live `gita-pull` task line and log-directory creation stay outside this PRD: they follow the repeatable procedure it writes. Preserve all required review lenses and the fresh-session build-to-review handoff.

## Overview

### Problem Statement
Hourly cellar-sync executes an agent-writable script outside Seatbelt, and daily gita-pull consumes writable repository configuration in the host shell. A protected launcher alone does not establish confinement: current run-agent performs Git discovery before entering the sandbox.

### Target Users
The solo developer and sandboxed agents using the local warrant and Seatbelt workflow.

### Success Metrics
- The three named contract checks below pass using isolated fixtures.
- The final regression command passes against the staged files; no live operation is counted as tested from a fixture result.
- Provide a host qualification command that runs only disposable local repository fixtures through the candidate launcher, records confinement with a denied non-secret fixture path, and checks both schedule launch paths. Runtime qualification also checks repository access and credential resolution before activation. Never plant helpers in live repositories or push as part of implementation acceptance.

## Functional Decomposition

### Capability: Confined scheduled execution
Both scheduled jobs enter the sandbox before any repository-controlled code or configuration runs.

#### Feature: Safe explicit workspace entry
- **Description**: Enter confinement before examining repository-controlled executable configuration.
- **Inputs**: An explicit project directory, protected profile and scheduled command.
- **Outputs**: A confined child or a diagnostic without running repository helpers.
- **Behavior**: Add an explicit `--project-dir PATH` mode to run-agent. In this mode resolve the supplied directory with shell builtins, reject HOME and filesystem root, and bypass pre-sandbox Git discovery. Keep the existing HOME-refusal message (`Refusing to sandbox entire HOME directory`) and the `SANDBOX_PROFILE=` line unchanged: PRD 00165's envelope pins that refusal text, and `test_live_profile_path_matches_run_agent` reads that line. Scheduled callers use a protected absolute shell with privileged startup and a clean explicit environment so PATH, BASH_ENV, ENV, exported functions and Git environment cannot inject bootstrap execution. Resolve command discovery and repository helpers only inside confinement. Preserve the existing interactive mode. Premise: the live launcher runs Git discovery before sandbox entry (`~/bin/run-agent` lines 30-51); recheck at execution and adapt only the remaining gap, never restore an obsolete launcher.

#### Feature: Preserve schedules and protect logs
- **Description**: Prepare tracked configuration for the two jobs and independent log protection.
- **Inputs**: The existing cellar and herdr plists, shell task configuration and profile roots.
- **Outputs**: Staged deployment candidates with hourly sync and daily pull preserved.
- **Behavior**: Route cellar-sync and gita-pull through the safe explicit-workspace entry, retaining dedicated agent credentials and identity. Plist sources become tracked under `~/.config/launchagents/` (staged as `docs/dev/tmp/00174-stage/.config/launchagents/`); keep the live `~/Library/LaunchAgents` untouched during implementation. Choose logs under `~/.config/scheduled-logs` with a protected parent, and check resolved paths and symlink ancestors before activation. Update the herdr relay plist log without changing its service command. Never treat a sandboxed child as protecting logs opened by launchd. Unknown execution chains fail qualification. Profile roots are conservative evidence; account explicitly for the selected runtime project grant and parser limitations.

### Capability: Qualification and delivery
Preserve a reviewable implementation and honest operational status.

#### Feature: Reproducible validation and operational procedure
- **Description**: Deliver tests, a repeatable qualification procedure and the deployed sources.
- **Inputs**: Staged code, fixture outcomes and the source discovery's residual risks.
- **Outputs**: Passing contract checks, the procedure named below and the deployed sources.
- **Behavior**: Write the repeatable procedure `docs/dev/procedures/qualify-scheduled-jobs.md`. It covers recurring work only: the host qualification command from Success Metrics, schedule activation, the live `gita-pull` task line quoted verbatim from the tested staged `tasks.yaml`, and the log checks. Re-run it after any change to the launcher, the plists or the job credentials. One-time deploy steps stay in Phase 3 of this PRD. Document what was measured and what remains unverified. Recheck observed-state premises before editing; when obsolete, skip the obsolete mutation and report evidence rather than forcing it. Never weaken existing checks to satisfy new ones.

## Structural Decomposition

### Repository Structure

```text
docs/dev/tmp/00174-stage/
├── bin/
│   ├── run-agent                              # staged copy of ~/bin/run-agent
│   └── tests/test_scheduled_jobs.py           # new contract tests
└── .config/
    ├── shell-hooks/tasks.yaml                 # staged copy of ~/.config/shell-hooks/tasks.yaml; tested candidate, goes live only through the procedure
    └── launchagents/
        ├── com.buvis.cellar-sync.plist        # staged copy of ~/Library/LaunchAgents/com.buvis.cellar-sync.plist
        └── com.buvis.herdr-relay.plist        # staged copy of ~/Library/LaunchAgents/com.buvis.herdr-relay.plist
docs/dev/procedures/qualify-scheduled-jobs.md
```

### Module: Implementation
- **Maps to capability**: Confined scheduled execution
- **Location**: `docs/dev/tmp/00174-stage/bin/run-agent`, `docs/dev/tmp/00174-stage/.config/shell-hooks/tasks.yaml`, `docs/dev/tmp/00174-stage/.config/launchagents/com.buvis.cellar-sync.plist`, `docs/dev/tmp/00174-stage/.config/launchagents/com.buvis.herdr-relay.plist`
- **Responsibility**: Implement the behavior above in the staged copies.
- **Exports**: `run-agent --project-dir PATH`

### Module: Contract tests
- **Maps to capability**: Confined scheduled execution
- **Location**: `docs/dev/tmp/00174-stage/bin/tests/test_scheduled_jobs.py`
- **Responsibility**: Exercise fixture behavior, failure paths and integration with the staged implementation.
- **Exports**: The named unittest methods on `ScheduledJobsCase`. Direct selection fails if a case is absent.
- New symbols: `ScheduledJobsCase`, `test_explicit_project_enters_sandbox_before_git`, `test_scheduled_bootstrap_rejects_injection`, `test_job_candidates_and_log_paths`

### Module: Operational procedure
- **Maps to capability**: Qualification and delivery
- **Location**: `docs/dev/procedures/qualify-scheduled-jobs.md`
- **Responsibility**: Describe the repeatable qualification and activation workflow, its prerequisites, scope limits and observable outcomes.
- **Exports**: One ordered host procedure with commands, preconditions before dependent steps, and one instruction per sentence.

## Dependency Graph

### Foundation Layer (Phase 0)
No internal dependencies - staged copies of the live files are made first.
- **Implementation**: the four staged copies, byte-identical to the live files before any edit.
- **External prerequisites**: None.

### Core Layer (Phase 1)
- **Contract tests**: Depends on [Implementation]; the named cases load the staged launcher, and the implementation edits land in the same task. Re-read the actual live files; do not copy stale tuple shapes or line numbers.

### Integration Layer (Phase 2)
- **Operational procedure**: Depends on [Implementation, Contract tests].
- **Host deploy** (Phase 3): Depends on [Implementation, Contract tests, Operational procedure]; human warrant acts after the review closes.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Stage the live files without changing them.

**Tasks**:
- [ ] Copy `~/bin/run-agent`, `~/.config/shell-hooks/tasks.yaml`, `~/Library/LaunchAgents/com.buvis.cellar-sync.plist` and `~/Library/LaunchAgents/com.buvis.herdr-relay.plist` into the staged layout above (no deps) - Acceptance: `cmp` of each staged copy against its live source exits 0 before any edit.

**Exit Criteria**: Four staged copies exist and match the live files.

### Phase 1: Core
**Goal**: Implement the two functional features with their contract tests.

**Tasks**:
- [ ] Implement the stated behavior in the four staged files and add `docs/dev/tmp/00174-stage/bin/tests/test_scheduled_jobs.py` (depends on: Phase 0) - Premise: the live launcher runs Git discovery before sandbox entry; a failed premise means skip the obsolete edit and report with evidence. Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00174-stage/bin/tests -t docs/dev/tmp/00174-stage/bin/tests -p 'test_scheduled_jobs.py' -k test_explicit_project_enters_sandbox_before_git` and the same command with `-k test_scheduled_bootstrap_rejects_injection` pass; record the first case's failure against the unedited staged launcher as evidence. An injected Git/config/PATH/startup helper never runs before the captured sandbox invocation; HOME and root workspaces refuse. Use isolated fake executables and malicious repository configuration; preserve normal interactive invocation and reject unknown job dependency chains.

**Exit Criteria**: Both feature contracts pass their focused checks without modifying live host state.

### Phase 2: Integration
**Goal**: Verify edge cases and write the repeatable procedure.

**Tasks**:
- [ ] Add `test_job_candidates_and_log_paths` to `docs/dev/tmp/00174-stage/bin/tests/test_scheduled_jobs.py` and write `docs/dev/procedures/qualify-scheduled-jobs.md` (depends on: Phase 1) - Acceptance: the Phase 1 command with `-k test_job_candidates_and_log_paths` passes. Parse both staged plists and the task YAML; assert intervals, fixed cwd, agent identity wiring and protected log destinations, including symlink rejection. The procedure exists, names prerequisites before commands, quotes the tested `gita-pull` line verbatim, and distinguishes fixture results from live qualification. Check first that the procedures folder is tracked: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" check-ignore -q "$HOME/.claude/docs/dev/procedures/qualify-scheduled-jobs.md"` exits 1; if it exits 0, write the procedure anyway and report that `~/.gitignore` still hides the folder.

**Exit Criteria**: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00174-stage/bin/tests -t docs/dev/tmp/00174-stage/bin/tests -p 'test_*.py'` passes once against the staged files. The fresh-session review closes before Phase 3.

### Phase 3: Deploy
**Goal**: Install the reviewed sources (human on the host, or warrant requests the human approves).

**Tasks**:
- [ ] Copy the staged `bin/run-agent`, `bin/tests/test_scheduled_jobs.py` and both plists to `~/bin/run-agent`, `~/bin/tests/test_scheduled_jobs.py` and `~/.config/launchagents/` with warrant `cp` requests, so the source is hashed (depends on: Phase 2 and its review). The staged `tasks.yaml` is not copied; its tested line goes live only through the procedure. Acceptance: `diff` of each deployed file against its staged copy is empty, and the host suite `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_*.py'` is green, including the warrant launcher-pin tests.
- [ ] One commit, then push (depends on: deploy) - Acceptance: `git --git-dir="$HOME/.buvis" --work-tree="$HOME" show --stat HEAD` lists exactly `bin/run-agent`, `bin/tests/test_scheduled_jobs.py`, `.config/launchagents/com.buvis.cellar-sync.plist`, `.config/launchagents/com.buvis.herdr-relay.plist` and `.claude/docs/dev/procedures/qualify-scheduled-jobs.md`.

**Exit Criteria**: Host suite green, sources tracked, commit pushed. No schedule changes until the procedure runs.

## Test Strategy

### Critical Scenarios
- **Happy path**: An injected Git/config/PATH/startup helper never runs before the captured sandbox invocation; HOME and root workspaces refuse.
- **Edge case**: A safe launcher with a writable log still fails; an unsupported executable/configuration chain remains unverified.
- **Error case**: Missing profile, unsafe workspace, bootstrap injection or protected-log failure prevents candidate activation.

## Risks

- **Operational limits**: Credential access may differ from the human identity; preserve both jobs only after separate host qualification. Mocked sandbox invocation verifies ordering, not actual Seatbelt enforcement.
- **Launcher pins**: PRD 00165 pins run-agent's HOME-refusal text and `test_warrant.py` reads its `SANDBOX_PROFILE=` line. Changing either deactivates the Git seeds or fails the warrant suite; keep both unchanged.
- **Launcher deploy**: Copying `run-agent` changes the launcher every new session uses. The interactive mode is unchanged by contract, and the host suite runs before the commit.
- **Concurrent repository changes**: Re-read live files and current configuration before staging; preserve unrelated work.
- **Scope drift**: No schedule activation or additional discovery scope enters this PRD; the procedure owns activation.
