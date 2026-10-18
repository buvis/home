# Discovery: Prove Warrant From a Codex Session

## Classification

Depth: standard | Date: 2026-10-18 | Status: not reviewed
Seeded from session 523838c3 follow-ups; user instruction 2026-10-18: 'all of
them must be recorded as discovery documents that I will go through'.
Written from a sandboxed Claude session. No Codex process was started and no
warrant request was submitted; everything below comes from `~/.codex`
(config, hooks, rules, rollout transcripts), the warrant spool results, the
aliases and `~/bin/run-agent`. `~/.config/warrant` was not read.

## Premise check

**Mostly false.** The PRD 00160 handoff said a Codex submit was "still
unobserved". The Codex rollouts show four Codex sessions under run-agent that
submitted six warrant requests on 2026-10-16 and 2026-10-17. Each rollout
records `"sandbox_policy":{"type":"danger-full-access"}`,
`"approval_policy":"on-request"` (the `codex` alias) and 4 to 9 `Operation not
permitted` denials, so the outer Seatbelt profile was active. Verdicts, read
from `/private/tmp/warrant-501/results/`:

| Request | Codex session | Command | Verdict |
|---|---|---|---|
| `d86ed27b` | `01a146a4` | `mise exec -- uv run pytest ...` | refused: env key `UV_CACHE_DIR` outside `allowed_env` |
| `f20d90da` | `01a146a4` | `mise exec -- uv --cache-dir ... run pytest ...` | refused: `~/.local/bin/mise` not under `trusted_exe_roots` |
| `91aacc71` | `01a14951` | `git ... add -f -- ':(top)...discovery/00161-...'` | executed, exit 0 |
| `0493f1c0` | `01a14984` | `git ... add -f -- ':(top)...prds/backlog/00165-...'` | executed, exit 0 |
| `1385e7cd` | `01a14996` | `~/git/src/github.com/buvis/ovcaq/tools/check` | refused: executable in an agent-writable path |
| `03b6c41c` | `01a14996` | `.../mise/installs/uv/0.13.0/.../uv run --locked pytest` | refused: not under `trusted_exe_roots` |

So submit, spool write, human approval with execution, and policy refusal all
work from Codex. Codex learned each ID from the request's stdout
(`warrant: request ID waits for a human`) and polled with
`~/bin/warrant wait ID --timeout 1` through its unified exec tool, getting exit
124 while pending. Every request then printed `could not notify the human;
tell them yourself`; another session fixed the notify hook since (warrant
request `b7b62b21`).

What stays unobserved:

1. **A human reject seen by Codex** (`status: rejected`, exit 125, `warrant:
   rejected by the approver`). No Codex request was ever rejected.
2. **Codex after the 2026-10-17/18 changes**: PATH write grants revoked
   (`14f93f50`), warrant parsing the profile for agent-writable roots (PRD
   00163, `b1cea72e`), and the herdr relay (`082c8778`). All six requests
   predate the relay; three predate `b1cea72e`.
3. **The Codex herdr hook through the relay.** Since `082c8778`, run-agent
   repoints `HERDR_SOCKET_PATH` to `~/.config/herdr-relay/relay.sock` and the
   profile denies unix-socket connects under `~/.config/herdr/`. The relay was
   checked with the Claude hook only.

## Problem

The open question is narrower than the handoff assumed: the reject path and
the Codex sidebar after the relay install were never exercised. Neither is
likely to break (the reject path is shared code that Claude sessions use, and
the Codex hook sends an allowlisted method), but the relay changed what every
sandboxed Codex hook connects to, and nobody has looked at a Codex row since.

## Requirements (proposed)

### Must have

1. One interactive Codex session in a herdr pane, started with the `codex`
   alias after the relay install, proves three things: the sidebar row
   updates (the relay path for the Codex hook), a `warrant request` from it
   lands in the spool, and a human reject reaches Codex as exit 125.
2. The outcome is recorded in PRD 00160 Findings (or here if 00160 stays
   closed), with the request ID and the observed exit codes.

### Nice to have

- Run the same three checks the next time copilot or pi starts under
  run-agent for real work, instead of a dedicated probe. No extra cost.
- A Codex execpolicy rule that forbids `warrant approve` and `warrant init`
  (see Open Questions 2).

### Out of scope

- The Moshi daemon (see Related finding). Separate discovery.
- Kiro and Gemini (see Other agents).
- Any change to warrant, the profile or the relay. This is a verification
  item.

## Constraints

- A probe cannot start from inside a sandboxed session: nested `sandbox-exec`
  fails (`sandbox_apply: Operation not permitted`, exit 71), so run-agent and
  Codex must be launched by the user on the host.
- `approve` needs a tty and the PIN. The user runs it in a plain herdr pane,
  never through an agent and never through the `!` prompt.
- run-agent refuses `$HOME` as the project dir, so Codex starts from a repo.

## Codebase Context

- **Aliases**: `~/.config/bash/aliases/development.bash:3-4`: `codex` is
  `run-agent codex --sandbox danger-full-access --ask-for-approval
  on-request`; `codex-unbound` adds `--no-sandbox`. Codex's own
  workspace-write sandbox is a nested Seatbelt and fails under run-agent,
  hence `danger-full-access`; the outer `ai-agents.sb` is the only boundary.
  The spool `/private/tmp/warrant-501` sits under the `/private/tmp/` grant.
- **Codex config**: `~/.codex/config.toml` sets `sandbox_mode =
  "workspace-write"` and `approval_policy = "never"`, both overridden by the
  alias flags. No `shell_environment_policy` block, so Codex's default applies
  (inherit the environment, minus names matching its default excludes such as
  `*KEY*`, `*SECRET*`, `*TOKEN*`; from Codex docs, not verified here). That
  passes `HERDR_SOCKET_PATH`, `GH_CONFIG_DIR` and `PATH` through and drops
  `COPILOT_GITHUB_TOKEN`; step 4 of the protocol shows whether
  `HERDR_SOCKET_PATH` arrives.
- **Instructions**: `~/.codex/AGENTS.md` is a symlink to
  `~/.claude/AGENTS.md`, which teaches `warrant request`/`wait` and forbids
  approving. The rollouts show Codex following it.
- **Codex hooks** (`~/.codex/hooks.json`): SessionStart runs
  `~/.codex/herdr-agent-state.sh session` (herdr integration v8), which sends
  only `pane.report_agent_session` to `$HERDR_SOCKET_PATH`, in the relay's
  allowlist. The agent-activity `hook.sh codex` sends `pane.report_metadata`,
  also allowlisted. `~/.local/bin/moshi-hook codex-hook` resolves herdr ids
  daemon-side ("no herdr CLI runs in-process", per its embedded source) and
  talks to the Moshi daemon, not to herdr. Bash PreToolUse hooks are the
  aegis-style ports (`validate_commit_msg.py`, `gateguard-fact-force.py`,
  ...); there is **no warden** in Codex.
- **Codex execpolicy**: `~/.codex/rules/default.rules` holds eight allow
  `prefix_rule`s (git add/commit/status/diff, mise exec uv, sonnet-run) and no
  forbidden rule.
- **warrant**: `~/bin/warrant:501-505`: an empty PIN at `Type the warrant PIN
  to EXECUTE (empty rejects)` rejects, ledgers and settles; `:548-549`: `wait`
  prints `warrant: rejected by the approver` and exits 125 (`:84`).

### Other agents under run-agent

- **copilot, pi, kiro**: their instruction files symlink to
  `~/.claude/AGENTS.md` (`~/.copilot/copilot-instructions.md`,
  `~/.pi/agent/AGENTS.md`, `~/.kiro/steering/AGENTS.md`), so they are taught
  warrant. None has ever submitted a request: `waits for a human` appears in
  no file under `~/.copilot`, `~/.pi`, `~/.kiro` or
  `~/Library/Application Support/kiro-cli` (the one kiro hit is skill text).
  The copilot and pi herdr integrations send `pane.report_agent_session` and
  `pane.report_agent`, both allowlisted by the relay (PRD 00160 addendum).
- **gemini**: no alias in `development.bash` and no AGENTS.md link in
  `~/.gemini`; it runs through the `use-gemini` skill from inside a Claude
  session and inherits that session's sandbox. Never seen using warrant.

## Host protocol

Cost: one short interactive Codex session, one turn plus a few polling tool
calls. Most of the cost is the instruction load every Codex session pays
(AGENTS.md and rules). The Stop hook `~/.codex/hooks/track_cost.py` appends
the real cost to `~/.claude/metrics/costs.jsonl`; read the last line after
step 10.

1. Open a new herdr pane.
2. Type `cd ~/git/src/github.com/buvis/gems` and press Enter.
3. Type `codex` and press Enter. Expected: Codex starts.
4. Look at this pane's row in the herdr sidebar. Expected: the row shows a
   Codex session.
5. Give Codex this prompt: "Run `~/bin/warrant request --no-wait --reason
   'codex probe' -- true`. Print the request ID. Then run `~/bin/warrant wait
   ID --timeout 1` every 20 seconds until its exit code is not 124. Report
   the last exit code and output." Expected: Codex prints a 32-character ID.
6. Open a second herdr pane. Do not start an agent in it.
7. Type `~/bin/warrant approve ID` with the ID from step 5. Expected: the
   review shows `true`, the gems directory and the reason `codex probe`.
8. At the PIN prompt, press Enter with no PIN. Expected: `rejected ID`.
9. Go back to the Codex pane. Expected: Codex reports exit code 125 and
   `warrant: rejected by the approver`.
10. Exit Codex.
11. Tell the agent the results of steps 4, 5 and 9.

## Success Criteria

- Step 4 shows the Codex row, with `HERDR_SOCKET_PATH` pointing at the relay.
- Step 9 shows exit 125 and the rejected message inside Codex.
- The result file for the probe ID reads `"status": "rejected"`.
- The outcome is written into PRD 00160 Findings.

## Risks

- **No warden in Codex.** Nothing in Codex blocks a `warrant approve` call.
  Under the `codex` alias it fails before the PIN, because Seatbelt denies
  reading `~/.config/warrant` (seen 2026-10-18 in session 523838c3:
  `Operation not permitted: '/Users/bob/.config/warrant/config.json'`). Under
  `codex-unbound` it reaches the PIN prompt if Codex's exec tool gives it a
  pty. The PIN, the attempt ledger line and the 10-minute lock after three
  misses still gate it. Open Question 2.
- **Probe turns into real work.** A probe prompt that names `true` and a
  reject keeps the command harmless even if approved by mistake.
- **Stale sidebar.** If step 4 fails, the cause is either the relay job or a
  dropped `HERDR_SOCKET_PATH`. The relay answers a direct probe (see the PRD
  00160 addendum); then the env passthrough is the suspect.

## Related finding (out of scope)

The Moshi daemon (`~/.local/bin/moshi-hook serve`, pid 36528 on 2026-10-18)
runs outside the sandbox and listens on `127.0.0.1:24543` and
`~/Library/Application Support/Moshi/moshi-hook.sock`. Its embedded strings
include herdr and tmux pane control (`send-keys`, `split-window`, `launch
agent in herdr pane`, prompt submission). Seatbelt allows sandboxed agents
both connects (`(allow network*)`; only `~/.config/herdr/` is denied). If its
local API accepts unauthenticated pane control, it is the same escape class
as the herdr socket. Not probed. It needs its own discovery.

## Open Questions

1. Run the probe now, or fold it into the next real Codex session (same
   steps 4 and 5 to 9 with a real request)? The history already proves the
   submit and execute paths, so the probe only adds the reject path and the
   post-relay sidebar.
2. Add `decision="forbidden"` execpolicy rules for `~/bin/warrant approve`
   and `~/bin/warrant init` to `~/.codex/rules/default.rules`? It mirrors
   warden's stance for Claude. Whether Codex applies prefix rules inside
   `bash -lc` scripts is unverified, so it is a speed bump, not a boundary.
3. Should the Moshi finding become its own discovery now?

## Discovery Log

### Q1: Has a Codex session ever used warrant?
**Answer** (from transcripts, not asked): yes, six requests from four sessions
on 2026-10-16/17, two executed and four refused by policy. The marker
`waits for a human` appears only in real request output; plain mentions of
`bin/warrant request` occur in nearly every rollout because AGENTS.md is part
of the session instructions.

### Q2: Does the herdr relay break Codex's status hook?
**Answer** (from code): not by method. Every herdr call in the Codex hooks is
allowlisted. Unproven end to end; protocol step 4 settles it.

### Q3: Do Codex sessions get warrant approve gated?
**Answer** (from config): only by Seatbelt (config unreadable), the tty and
the PIN. There is no warden and no forbidden execpolicy rule.
