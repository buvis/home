# autocodex

Codex drives the existing autopilot PRD workflow. Each phase runs in a fresh
`codex exec` process; reviewers use the opposite implementation-model provider.

Run from the intended repository root:

```bash
autocodex                  # build, fresh review/rework cycles, finalize, next PRD
autocodex --dry-run        # show exact routing and host instructions, no session
autocodex --once           # finish one session, stop at its boundary
autocodex status
autocodex pause            # stop after the active session finishes
autocodex --scope scope.md # carry additional user constraints into every session
autocodex --once --scope docs/dev/project-management/plans/fast-track-handoffs/.../rework-NN.md
                            # run one standalone handoff session, then stop
```

Ctrl-C terminates the active session's process group and exits. `--cd /repo`
selects a different root explicitly. Existing paused batches remain paused;
`autocodex` prints the recorded findings and exact recovery steps without
changing their state. For a current PRD pause, open `codex` in the repository and
ask it to read `~/.config/autocodex/host.md` and follow its interactive recovery
instructions. That procedure loads the resolved host contract and the installed
autopilot Resume procedure without requiring a registered slash command. For a
review-cap pause, choose Resume and optionally raise the cap. Exit Codex after
resolving the pause, then run `autocodex` again. If the paused state names a PRD
already under
`docs/dev/project-management/prds/done/`, preserve and detach that stale task tree with the `mv`
command `autocodex` prints before starting the current WIP PRD. Never edit
`state.json` directly.
Fast-track handoff scopes intentionally have no task state. `autocodex`
recognizes their path and implies `--once`, preventing a successful repair or
review from being retried with its now-stale expected HEAD.
This launcher uses that root's `docs/dev/project-management/autopilot` tree, including existing
autoclaude batches. It does not import OVCAQ state or choose a handoff PRD for you.

The coordinator uses `gpt-6.1-sol` / low. Native worker mappings remain
Haiku → `gpt-6-luna` / low, Sonnet → `gpt-6.1-sol` / medium, and
Opus → `gpt-6.1-sol` / high; bounded failed Opus work may escalate to
`gpt-6-astra` / high under the source policy.

Before implementation dispatch, a source route without independent review
support falls back to the mapped native worker at the task's existing tier.
This includes UI tasks routed to an installed Gemini CLI. The coordinator
records the fallback and preserves every task gate and review lens; no operator
decision is needed. Unknown or conflicting evidence from work already performed
still pauses for resolution.

Reviewers are chosen from the actual implementation model company, verified
against task/attempt logs, never from launcher identity. GPT implementation gets
three separate Claude Opus/xhigh reviewers; Claude implementation gets three
separate GPT/high reviewers. Kiro and Copilot follow their logged resolved model.
Mixed work gets both complete rosters. Unknown or conflicting evidence pauses.
Alice, Blake and Bob retain consensus, blind and doubt/de-slop respectively.

Before review, the coordinator records a per-task log audit under
`autopilot/reports/<prd-stem>-implementation-models.json`; `review-route` verifies
its freshness, coverage and cited line hashes. See `host.md` for the format and
log-correlation obligations. Audit all model switches, repairs and contributing
attempts; read-only reviewers and coordinator models do not count.

After convergence, the source's tail sweep may append completed cleanup tasks
without reopening review. The host preserves the reviewed audit and receipts,
requires unchanged original task provenance and the current review's batch
stamps, and validates a separate `<prd-stem>-tail-sweep-models.json` audit of the
completed task set. Ordinary rework, incomplete sweeps, and missing or stale
model evidence still block finalization. The normal work pipeline supplies
sweep tests and task review. See `host.md` for the companion audit and recovery
procedure; installing this fix does not automatically clear an existing pause.

The reviewer helper accepts `--lens alice|blake|bob` and `-m <model>` (`opus` for
Claude, a concrete GPT model for OpenAI). Each external process is fresh and
preserves launcher guards. It validates the source lens rubric and saves raw
output plus a receipt. The completion gate checks all required provider/lens
receipts. This provider guard replaces the source's launcher-based additive Eve
guard; it does not remove a review lens. Live launcher availability remains a
dispatch precondition. Anthropic reviews try Kiro, Copilot, then native Claude
by default. Quota/authentication failures and missing executables try the next
route before any quota wait; permission denials, stalls, incomplete output,
wrong model/effort evidence and other failures still stop review.
Kiro and Copilot use explicit Claude models with xhigh effort and read tools
only. Their raw model/effort events must match the receipt. These transports
cannot execute test commands; provide existing gate evidence in the applicable
review prompt. Preserve Blake's PRD-only context. Prompt contents are passed
directly, so gitignored rubric files need not be readable through Kiro's tools.

On macOS, Codex coordinator and GPT reviewer processes use the inherited Seatbelt
sandbox when `sandbox_check(getpid(), NULL, 0)` confirms it. They pass
`--sandbox danger-full-access -c approval_policy="on-request" -c approvals_reviewer="auto_review"`
to avoid creating a second Seatbelt sandbox while retaining automatic approval
review. `run-agent` continues to enforce its outer profile. The probe checks
sandbox presence, not profile identity. Unprotected processes, other platforms,
and probe errors retain `--approve-for-me` and Codex's native workspace sandbox.
Claude uses automatic permissions with unanswered requests denied. Neither
invocation bypasses approvals. Permission failures and rejected review gates
remain visible; a failed session cannot certify completion.

Raw JSONL, stderr and prompts are retained in
`docs/dev/project-management/autopilot/autocodex-sessions/`; metrics in `autocodex-metrics.jsonl`.
Each reviewer helper writes unique raw files and a receipt beside its output.
Finished batch state is archived under `reports/`, allowing a later invocation
to start a fresh batch. No post-drain purge or extra agoge batch is launched.

Configuration:

| Environment variable | Default |
|---|---|
| `AUTOCODEX_SKILL_ROOT` | Latest installed autopilot `skills/run-autopilot` |
| `AUTOCODEX_SONNET_MODEL` / `AUTOCODEX_SONNET_EFFORT` | `gpt-6.1-sol` / `medium` |
| `AUTOCODEX_OPUS_MODEL` / `AUTOCODEX_OPUS_EFFORT` | `gpt-6.1-sol` / `high` |
| `AUTOCODEX_HAIKU_MODEL` / `AUTOCODEX_HAIKU_EFFORT` | `gpt-6-luna` / `low` |
| `AUTOCODEX_REVIEWER_MODEL` | `opus` (Claude) |
| `AUTOCODEX_ANTHROPIC_BACKENDS` | `kiro,copilot,claude`; explicit order, no duplicate routes |
| `AUTOCODEX_ANTHROPIC_OPUS_MODEL` / `AUTOCODEX_ANTHROPIC_SONNET_MODEL` / `AUTOCODEX_ANTHROPIC_HAIKU_MODEL` | `claude-<tier>-5.5` for Kiro/Copilot; must retain the requested tier |
| `AUTOCODEX_KIRO_BIN` / `AUTOCODEX_COPILOT_BIN` | `kiro-cli` / `copilot` |
| `AUTOCODEX_COORDINATOR_MODEL` / `AUTOCODEX_COORDINATOR_EFFORT` | `gpt-6.1-sol` / `low` |
| `AUTOCODEX_REVIEW_MODEL` / `AUTOCODEX_REVIEW_EFFORT` | `gpt-6.1-sol` / `high` (OpenAI reviewer lanes) |
| `AUTOCODEX_ESCALATION_MODEL` / `AUTOCODEX_ESCALATION_EFFORT` | `gpt-6-astra` / `high` |
| `AUTOCODEX_RETRY_DELAY` | 15 seconds |
| `AUTOCODEX_LIMIT_POLL` | 300 seconds |
| `AUTOCODEX_STALL_TIMEOUT` | 1800 seconds without substantive activity |
| `AUTOCODEX_REVIEWER_STALL_TIMEOUT` | `AUTOCODEX_STALL_TIMEOUT` |
| `_AUTOPILOT_LIMIT_WAIT_MAX` | 21600 seconds |
| `_AUTOPILOT_DIED_RETRIES_MAX` | 1 |

`AUTOCODEX_EFFORT` is rejected with migration guidance; unset it and select
role-specific settings. Inherited logical phase tiers no longer change the
coordinator. Explicit `_AUTOPILOT_MODEL_<PHASE>=gpt-...` overrides still apply,
unless `AUTOCODEX_COORDINATOR_MODEL` is set. Worker settings do not affect
external Claude dispatches, which retain their source role and guards.

Main and reviewer sessions have no fixed wall-clock limit. The launcher stops a
session only after the stall timeout passes without a substantive provider event
or workspace change. Repeated agent `wait` calls do not count as progress. The
watchdog retains raw evidence, terminates the process group, and reports the
inactivity duration explicitly.

Usage-limit polling is bounded; reset times are not guessed from prose.
Only after configured alternatives have been attempted, a final native Claude
reviewer attempt with a structured API 429 quota rejection waits for the
reported reset plus five seconds, then retry with a fresh raw log. Waiting is
bounded by `_AUTOPILOT_LIMIT_WAIT_MAX`; stale or missing resets fail normally.
An operator pause interrupts the wait within
60 seconds. Only a successful full D1–D5 review receives an output and receipt.
Existing paused batches still require interactive recovery.

Other unsuccessful sessions get the configured retry budget and then stop with their
evidence. Existing loop memory, plugin-version and repeated-progress guards
remain active. Some inherited diagnostics still name autoclaude.

Already-running reviewers keep their loaded code. Restart a waiting helper at a
safe session boundary to load a routing update; do not launch duplicate reviews
or change workflow state by hand. Existing pauses still use interactive recovery.
Set `AUTOCODEX_ANTHROPIC_BACKENDS=kiro,copilot` to exclude native Claude during
a known outage, or `claude` to request the legacy native-only behavior.

Requires mise Python 3.12+, authenticated Codex and an available Anthropic route, and the installed
autopilot plugin. The adapter is personal tooling in `~/.config/autocodex`; the
tracked development shell plugin exposes it as `autocodex`, wrapped in
`~/bin/run-agent` so git commits use the agent identity and `ssh-keygen` signing
instead of the user's 1Password signer. Its tests use the
resolved installed plugin and disposable repositories/processes:

```bash
mise exec -- uv run --with pytest --no-project pytest ~/.config/autocodex
```

### Cap-regression stalls

Before canonical `cap_regression` stall/reset, record cap-overflow decisions and
run `python3 ~/.config/autocodex/driver.py --cd <repo> review-stall-snapshot`.
Then follow the source stall, mint-stubs and handoff procedure. The immutable
`reports/<prd-stem>-cycle-<cycle>-cap-regression-boundary.json` preserves the
latest verified review, including one produced after session launch. The boundary
rechecks receipts, audits and rubrics, the unchanged PRD's move into hold, fresh
deferred stall and migrated decisions, and canonical reset. It permits only
canonical minted-stub bookkeeping and a contract card after reset. Missing or
tampered evidence still pauses. No cap or review requirement changes.
