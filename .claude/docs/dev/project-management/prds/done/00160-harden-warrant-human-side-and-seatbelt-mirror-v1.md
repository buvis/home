---
default_model: opus
---

# Harden the warrant human side and pin the Seatbelt mirror

Source: PRD 00159 Phase 2 (Seatbelt tightening deferred until the broker
worked; it works since 2026-10-16). Two residual exposures sit on the human
side of warrant, and three profile decisions need the user, not an agent.

## Problem

- **PATH shadowing.** `~/.bashrc` runs `mise activate bash`, which puts
  `~/.local/share/mise/installs/*` and `~/.local/share/mise/shims` ahead of
  `~/bin`; the profile lets agents write both mise directories (a deliberate
  exception so sessions can install tools). A bare `warrant` typed by the
  human therefore resolves to whatever an agent planted there. A decoy can
  show a convincing review, capture the PIN, and the agent can then type it
  into a real `approve` because the herdr socket is reachable from the
  sandbox. PRD 00159 answered this with "invoke by absolute path", which
  depends on habit. Closed 2026-10-17: the profile no longer grants writes to
  either mise directory, so nothing an agent can write sits on PATH; the
  function below stays as belt and braces.
- **Mirror drift.** `~/.config/warrant/config.json` copies the profile's
  write allowlist by hand. The broker's "executable under an agent-writable
  path" refusal is only as good as that copy; nothing fails when the profile
  gains a root the mirror lacks.
- **Profile decisions** the user must make, each with a real cost: writes to
  `/dev` (same-uid pty access), the herdr socket being reachable from the
  sandbox, and the three write exceptions that sat on PATH (`~/.local/share/mise`,
  `~/Applications`, `~/.local/bin/claude*`; revoked 2026-10-17, question 3).

## Solution

1. A shell function wins over PATH lookup in bash. Define `warrant` in
   `~/.config/bash/aliases/development.bash` (tracked in buvis, not in the
   profile's write allowlist) as `warrant() { "$HOME/bin/warrant" "$@"; }`.
   Shadowing is then impossible in the user's interactive shell regardless of
   PATH order; the mise exceptions can stay.
2. A test that parses the profile and the mirror and fails on drift:
   `~/bin/tests/test_warrant_mirror.py` reads every `(allow file-write* ...)`
   filter in `~/.config/seatbelt/ai-agents.sb`, substitutes `_HOME`, and
   asserts each `subpath`/`literal` appears in `agent_writable_roots` and each
   `regex` has a counterpart in `agent_writable_globs`. `_PROJECT_DIR` and
   `_TMPDIR` entries are the documented exceptions (unknown at broker time).
3. Profile decisions 1 and 2 are recorded as open questions below with
   their consequence and a test protocol, not changed by this PRD. Decision 3
   was taken on 2026-10-17 and is recorded there.

## Requirements

### Must have
- `type warrant` in a fresh login shell prints a function that execs
  `$HOME/bin/warrant`.
- With a decoy `warrant` script first on PATH, `warrant list` still runs
  `~/bin/warrant` (the decoy's marker file is absent, `spool empty` prints).
- `test_warrant_mirror.py::test_profile_write_roots_are_mirrored` passes on
  the real pair and fails when any root is removed from a temp copy of
  `config.json`.
- `~/bin/tests/test_warrant.py` stays green; the profile and `config.json`
  are not changed by this PRD except through a user decision below.

### Nice to have
- A fish/nushell equivalent of the function, only if the user approves from
  those shells.

## Implementation

### Module: development.bash (function)
- **Location**: `~/.config/bash/aliases/development.bash`
- **Responsibility**: `warrant()` wrapper, one line plus a comment pointing
  at PRD 00160.

### Module: test_warrant_mirror
- **Location**: `~/bin/tests/test_warrant_mirror.py`
- **Responsibility**: parse the `.sb` allow-write filters with a regex over
  `(subpath|literal|regex) (string-append (param "_HOME") "...")` and plain
  `(subpath "/...")` forms; compare with `config.json` after `expanduser`.
- **Exports**: none (test)

### Dependencies
- test_warrant_mirror: No dependencies (stdlib `re`, `json`, `pathlib`)

## Tasks

### Phase 0: Shadow guard
- [x] (buvis `e5395042`, 2026-10-17) Add the `warrant` function to `~/.config/bash/aliases/development.bash`.
  Acceptance: `bash -lc 'type warrant'` prints `warrant is a function`; the
  decoy check under Must have passes; commit to buvis.

### Phase 1: Drift test
- [x] (buvis `f0d0c7fe`, 40/40 green on the host) Write `~/bin/tests/test_warrant_mirror.py`. Acceptance:
  `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'`
  green; the removal check under Must have fails as expected; commit.

Exit criteria: both acceptance checks pass; nothing else changed.

## Success Criteria

- `test_profile_write_roots_are_mirrored` and the existing warrant suite pass.
- The decoy check passes in a fresh shell.
- The open questions below carry a recorded decision each.

## Findings 2026-10-17 (sandboxed session 523838c3)

- This session ran under run-agent, so every write to `~/bin`, `~/.config/bash`
  and `~/.buvis` went through warrant (drafts in the session scratchpad, `cp`
  requests so the source is hashed, then one test-and-commit request).
- Phase 0 acceptance needs `bash -ic`, not `bash -lc`: `~/.bashrc` returns
  early when non-interactive, so bash-it never loads `development.bash`.
- `test_warrant_mirror.py` skips its four tests inside the sandbox (the
  profile denies reading `config.json`); it bites only on the host. Its
  parser counts every sub-form of an allow-write form, so an unknown filter
  (`prefix`, `require-all`) is reported, not skipped.
- The warrant ping is broken from every sandboxed session when the user is
  present: `notify.log` shows `terminal-notifier exited 5` for each submit
  since 2026-10-16 23:38; the 22:31 pings that worked came from an
  unsandboxed session. The ntfy path (user away) was not tested. Not fixed
  here: falling back to ntfy would also fire for every Stop hook.
- Exposure under the live profile, probed from this session (open and close
  only, nothing written or sent): all 36 `/dev/ttys*` open for write,
  `~/.config/herdr/herdr.sock` accepts a connect. Nested `sandbox-exec` is
  refused inside a session (`sandbox_apply: Operation not permitted`), so
  the profile protocols run on the host only.
- Q2 cost settled from code, no live run needed: `herdr-agent-state.sh`
  (SessionStart) and the agent-activity `hook.sh` (7 more hook events in
  `settings.json`) run inside the sandboxed session and connect to
  `herdr.sock`. Both swallow errors, so a deny silently stops pane session
  and activity reports for every sandboxed agent. Seatbelt cannot filter by
  JSON method, so a deny is all or nothing.
- Q2 is worse than "terminal driving" (corrected 2026-10-17, after the user
  first chose keep-open on an understated framing): the socket serves
  `herdr pane split`, `pane run`, `send-text` and `send-keys`, and herdr's
  panes are the user's unsandboxed shells. A sandboxed agent can therefore
  run any command outside Seatbelt with no human step, which makes the
  profile and warrant advisory. herdr's config has no API auth or method
  allowlist. No agent skill, plugin or `~/bin` tool calls the pane API (rg
  over skills, `~/.agents`, `~/bin`, plugin cache); only the two status
  hooks use the socket. Not exercised live.
- Codex path: Codex's workspace-write sandbox is itself Seatbelt, and a
  nested `sandbox_apply` is refused, which is why the `codex` alias passes
  `--sandbox danger-full-access`. Under run-agent only the outer profile
  governs the spool write, and it allows `/private/tmp/` (this session's
  submits prove it). A live Codex submit is still unobserved.
- Q3 was decided mid-session (buvis `14f93f50`, revoke): no allow-write regex
  is left, `agent_writable_globs` is empty. The drift test therefore treats
  any regex grant as an unparsed filter for a hand check instead of keeping
  a per-regex sample table. The first test-and-commit request failed on the
  old glob test and committed nothing; the shell function stays as defense
  in depth.

- Q1 host run 2026-10-17 (live profile before `14f93f50` plus
  `(deny file-write* (regex #"^/dev/ttys[0-9]+$"))`): all 38 ptys denied
  including the caller's own, `/dev/tty` write OK, getpass OK, git
  credential prompt OK. Second host run (rebuilt from the live profile):
  `python3 -c "import pty; pty.openpty()"` hangs instead of failing, so
  every tool that allocates its own pty (Python `pty`, `script`, expect,
  likely Codex interactive exec) would hang in the sandbox; it works under
  the live profile (control run in the sandbox).

## Closure 2026-10-17

- Phase 0 done (`e5395042`). Phase 1 done (`f0d0c7fe`), then superseded by
  PRD 00163: warrant reads the agent-writable roots from the profile, so the
  mirror keys and `test_warrant_mirror.py` are gone and the Must-have mirror
  test no longer applies.
- Notify defect fixed (buvis commit via warrant request `b7b62b21`):
  `-contentImage` fails with exit 5 inside the sandbox ("Failed to move
  attachment file into data store"); `show_desktop_notification` now retries
  text-only. Verified from a sandboxed session: `notify.py --send` exits 0 and
  logs `System notification shown`; `send_ntfy` returns True (away path). A
  sandboxed `warrant request` no longer prints `could not notify the human`.
  Regression test: `test_retries_without_image_when_sandbox_denies_attachment`.
- Q1 decided (no deny), Q2 decided (accept the escape), Q3 decided (revoke).

## Open questions

1. `/dev` writes: the profile allows `file-write*` under `/dev/` so the
   agent's own tty, `/dev/null` and ptys work. Denying `^/dev/ttys[0-9]+$`
   would stop writes to other sessions' terminals but may break tools that
   `open("/dev/tty")` (getpass, git credential prompts) inside the sandbox.
   Protocol before deciding: copy the profile, add the deny, launch
   `run-agent bash` from a repo dir, run `python3 -c 'import getpass; getpass.getpass()'`
   and a git credential prompt; keep the deny only if both still work.
   **Decided 2026-10-17 (user): no deny.** Both prompts survived it, but pty
   allocation hangs under it (Findings). Accepted residual: a sandboxed agent
   can draw on any of the user's terminals, so a fake review can mislead
   about which request is approved; it cannot type input or learn the PIN.
2. herdr socket: `(allow network*)` lets a sandboxed process connect to
   `~/.config/herdr/herdr.sock`. Denying it closes the terminal-driving path
   but the herdr `agent-activity` hook and `herdr-agent-state.sh` run inside
   sessions and may need it. Protocol: deny `network-outbound` to that
   literal path in a profile copy, launch a session, check the herdr pane
   state still updates.
   **Decided 2026-10-17 (user): no deny, accept the escape.** Taken on the
   corrected framing (socket = unsandboxed command execution through herdr
   panes). Accepted residual: a sandboxed agent can run commands outside
   Seatbelt through `herdr.sock`, so the profile and warrant are advisory
   against a hostile agent; the herdr status hooks keep working.
   **Addendum 2026-10-17 (session 523838c3):** the user's actual words were
   "either we find a solution that is still usable or we have to live with
   the risk", so the acceptance stands only until a usable fix exists. One is
   staged: `~/bin/herdr-relay` (launchd `com.buvis.herdr-relay`) forwards
   only `pane.report_agent`, `pane.report_agent_session` and
   `pane.report_metadata` (every method the claude, codex, copilot, pi and
   agent-activity hooks send; the agent-activity publisher runs under herdr,
   unsandboxed, and keeps the real socket); the profile denies unix-socket
   connects under `~/.config/herdr/`; run-agent repoints `HERDR_SOCKET_PATH`.
   6 relay tests green, live round trip through the real herdr OK, warrant
   parses identical write roots from the staged profile. Residual: an agent
   can spoof display metadata or agent state on any pane. Pending: host
   validation (warrant `0ab414fb`), then install on the user's yes.
   Out of scope, same escape class: launchd `com.buvis.cellar-sync` runs
   `~/git/src/github.com/buvis/cellar/sync.sh` hourly outside the sandbox,
   and agents can write `~/git/src`.
3. PATH exceptions: decided 2026-10-17 by the user, revoked. The profile
   no longer grants writes to `~/.local/share/mise`, `~/.config/mise`,
   `~/Applications`, `~/.local/share/claude` or `~/.local/bin/claude*`.
   `config.json` mirrors that and trusts `~/.local/bin` (the mise binary) and
   `~/.local/share/claude` (what `~/.local/bin/claude` resolves to), with
   `~/.local/bin` last on `exec_path`, so installs can be brokered:
   `~/bin/warrant request -- mise install <tool>`,
   `~/bin/warrant request -- claude update`. Consequence: Claude Code's
   in-session auto-update fails until the user brokers `claude update`.
