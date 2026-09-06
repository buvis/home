# autocodex

Codex drives the existing autopilot PRD workflow. Each phase runs in a fresh
`codex exec` process; Claude Opus takes the former external Codex review role.

Run from the intended repository root:

```bash
autocodex                  # build, fresh review/rework cycles, finalize, next PRD
autocodex --dry-run        # show exact routing and host instructions, no session
autocodex --once           # finish one session, stop at its boundary
autocodex status
autocodex pause            # stop after the active session finishes
autocodex --scope scope.md # carry additional user constraints into every session
```

Ctrl-C terminates the active session's process group and exits. `--cd /repo`
selects a different root explicitly. Existing paused batches remain paused;
resolve their recorded reason through the workflow state CLI before resuming.
This launcher uses that root's `dev/local/autopilot` tree, including existing
autoclaude batches. It does not import OVCAQ state or choose a handoff PRD for you.

Logical model roles: Sonnet → `gpt-5.6-sol` (high); Opus → `gpt-6-astra`
(xhigh); Haiku → `gpt-5.6-luna`. Finalization uses medium effort. These are role
mappings, not performance-equivalence claims. Sol and Astra both passed local
live CLI probes, as did the external Claude Opus invocation, on 2026-09-06.

The installed autopilot plugin provides lifecycle policy, state transactions,
PRD selection, task procedures, persona sources and rubrics. The adapter provides
Codex arguments/event parsing, raw session capture, process-group cleanup, fresh
phase boundaries, and a required Claude review receipt. Alice and Blake use
isolated native Codex agents; Bob uses Claude, including D1–D5 and de-slop.
Read `host.md` for the explicit host adaptations. It does not install or pretend
to register a native Codex autopilot plugin, nor load Claude hooks into Codex.

Codex uses `--approve-for-me`, retaining automatic approval review and the
workspace sandbox. Claude uses automatic permissions with unanswered requests
denied. Neither invocation bypasses approvals. Permission failures and rejected
review gates remain visible; a failed session cannot certify completion.

Raw JSONL, stderr and prompts are retained in
`dev/local/autopilot/autocodex-sessions/`; metrics in `autocodex-metrics.jsonl`.
Bob's helper writes unique raw files and a receipt beside his review output.
Finished batch state is archived under `reports/`, allowing a later invocation
to start a fresh batch. No post-drain purge or extra agoge batch is launched.

Configuration:

| Environment variable | Default |
|---|---|
| `AUTOCODEX_SKILL_ROOT` | Latest installed autopilot `skills/run-autopilot` |
| `AUTOCODEX_SONNET_MODEL` | `gpt-5.6-sol` |
| `AUTOCODEX_OPUS_MODEL` | `gpt-6-astra` |
| `AUTOCODEX_HAIKU_MODEL` | `gpt-5.6-luna` |
| `AUTOCODEX_REVIEWER_MODEL` | `opus` (Claude) |
| `AUTOCODEX_EFFORT` | Selected by phase/model |
| `AUTOCODEX_RETRY_DELAY` | 15 seconds |
| `AUTOCODEX_LIMIT_POLL` | 300 seconds |
| `_AUTOPILOT_LIMIT_WAIT_MAX` | 21600 seconds |
| `_AUTOPILOT_DIED_RETRIES_MAX` | 1 |
| `_AUTOPILOT_SESSION_MAX` | 7200 seconds |
| `_AUTOPILOT_SESSION_MAX_REVIEW` | 10800 seconds |

Usage-limit polling is bounded; reset times are not guessed from prose. Other
unsuccessful sessions get the configured retry budget and then stop with their
evidence. Existing loop memory, plugin-version and repeated-progress guards
remain active. Some inherited diagnostics still name autoclaude.

Requires mise Python 3.12+, authenticated Codex and Claude CLIs, and the installed
autopilot plugin. The adapter is personal tooling in `~/.config/autocodex`; the
tracked development shell plugin exposes it as `autocodex`. Its tests use the
resolved installed plugin and disposable repositories/processes:

```bash
mise exec -- uv run --with pytest --no-project pytest ~/.config/autocodex
```
