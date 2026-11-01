# Discovery: Broker Root Commands Through Warrant

## Classification

Depth: standard | Date: 2026-10-17 | Status: reviewed 2026-10-17 (6
findings applied); specified in backlog PRD 00166; authentication qualification
must be reconciled there before build (review 2026-10-18)
Seeded from the user's observation of 2026-10-17: "warrant can't run sudo
commands". Written from a sandboxed session, so `~/.config/warrant` (config,
ledger) was not read and the host's `sudo -V` is unknown; everything below
comes from `~/bin/warrant`, the spool, the transcript of session `3e6c5ffc`
and the binaries' modes.

## Premise check

**Confirmed, with a narrower cause than "sudo".** The approve side hashes the
resolved executable during review (`warrant:337`, `sha256_file(exe)`).
`/usr/bin/sudo` is `-r-s--x--x root wheel` (mode 4511): anyone may execute it,
only root may read it. The open fails with EACCES. `decide()` catches only
`Refused` and `ValueError` (`warrant:434`), so the `PermissionError` escapes to
`main()` (`warrant:617`), which prints the raw errno and exits 126:

```
❯ warrant approve bf2aa6d0b6903a15de1888ff8bde4c9e
warrant: [Errno 13] Permission denied: '/usr/bin/sudo'
```

Observed 2026-10-17 10:40 local on request `bf2aa6d0` (`sudo mdutil -E /`,
cwd `/Users/bob`, the retry of `1f1cb2e1` which ran as the user and answered
"Try as root"). Consequences, all verified in the spool at 10:43:

- No ledger line: the `attempt` write comes after `show()`, and review died
  before `show()`.
- No result file, so the agent's `warrant wait` blocked until the user killed
  the task; the request is still in `requests/` and `warrant list` shows it
  `pending` until the 24h TTL (2026-10-18 10:39).
- Every retry of `approve` fails the same way. The only exit is deleting the
  request file by hand.

So there are two layers. **Layer 1 is a bug independent of sudo:** any path
the broker cannot read during review (an exec-only binary, a root-only file
argument such as `/etc/sudoers` at mode 0440) crashes approve and strands the
request instead of producing a verdict. **Layer 2 is a decision:** whether
warrant should broker root at all, and on what terms.

Three bounds frame layer 2:

1. **Warrant is the agent's only path to root.** Warden denies `sudo` to every
   agent session (`~/.claude/warden.yaml:247-248`, `default: deny`), so an
   agent cannot run sudo even unsandboxed. Today the fallback is "paste this
   command, I'll wait", which loses the ledger line and the captured output.
2. **The password is a second gate the PIN lacks.** PRD 00159 accepts a 4 to 8
   digit PIN because Seatbelt caps what a brokered command can do only on the
   host side of the trust story; root removes every cap. sudo's own prompt is
   the natural second factor, and it is typed into `/usr/bin/sudo`, a
   SIP-protected root binary warrant resolves by absolute path.
3. **The child inherits the human's terminal.** `execute()` closes stdin and
   captures output but does not detach (`warrant:377`, no
   `start_new_session`). The child keeps the controlling tty, so sudo can
   open `/dev/tty` and prompt (the reason brokered sudo can work at all), and
   so can any other brokered command (the reason it needs hardening once a
   password prompt after the PIN becomes normal).

## Problem

A request whose executable or file argument the broker cannot read kills
`approve` with an errno instead of a verdict: nothing in the ledger, nothing
in `results/`, the agent blocked, the request pending for a day. The first
such request was the first root operation ever brokered. Beyond the crash,
warrant has no stance on sudo: the review shows `sudo mdutil` but vets and
hashes only `sudo`; which `mdutil` root runs is sudo's PATH lookup, never
shown or pinned.

## Requirements (proposed)

### Must have

1. **Review failures are verdicts.** Any `OSError` raised while building the
   `Op` (hashing, stat, reading a head) or in `launch()`'s re-check after the
   PIN ends as `refused` with the error text:
   ledger line, result file, request removed, agent unblocked with exit 126.
   Same shape as a `Refused`.
2. **Unreadable executables are pinned by identity, not content.** When the
   resolved executable cannot be read, `review()` records
   `stat:<dev>:<ino>:<size>:<mtime_ns>` in place of the sha256 and `launch()`
   re-checks the same tuple; `show()` prints `stat-pinned (unreadable, mode
   4511 root)` where the hash would go. One `fingerprint(path)` helper serves
   the executable and file arguments; a file head is shown only when readable.
   `os.stat` needs only search permission on `/usr/bin`, so this works for
   sudo, and the trusted-root plus not-agent-writable checks still apply.
   An unreadable path that is agent-writable is refused, not pinned: its
   owner can rewrite it in place and restore dev, ino, size and mtime. Only
   non-agent-writable paths are stat-pinned.
3. **Brokered sudo is exactly `sudo CMD ARG...`.** When the resolved
   executable's name is `sudo`, argv[1] must exist and must not start with `-`
   or contain `=` (no sudo options, no `VAR=value` assignments, no `-u`, `-i`,
   `-s`, `-E`, `--preserve-env`); anything else is refused with "put the exact
   command; sudo options are not brokered". argv[1] is resolved through
   `resolve_exe()` like argv[0] (trusted root, not agent-writable,
   fingerprinted), shown as a second `exe` line, excluded from `file_args`, and
   launched by its absolute path so sudo's PATH never picks the program.
   The ban keeps one canonical shape so the review shows exactly what root
   runs; it is not a boundary (`sudo sh -c`, `sudo env`, `sudo sudo` reach
   the same power), and requirement 4's password is the gate. A sudo request
   whose cwd is agent-writable is refused: root would run code the agent
   controls (Makefile, git hooks, package scripts). Agent-writable file
   arguments stay allowed; their head is shown and re-hashed.
4. **Root requires fresh host authentication.** Enable root brokerage only
   after host qualification establishes that the supported command policy
   requires fresh authentication; password-free or unproven policies must
   not silently reduce this to the warrant PIN. Do not edit sudoers here.
   Invalidating a cached ticket alone does not prove this requirement.
   Right before launching a sudo request,
   approve runs the resolved sudo (the `Op`'s executable, already
   trust-checked) with `-k` (invalidates the tty ticket, needs no
   password, exits 0); a failed invalidation refuses the launch. Without it,
   cached authentication in the approve pane can make the PIN the only
   fresh gate for root.
   `NOPASSWD` and other authentication exemptions are separate policy cases,
   not defeated by `-k`; their refusal and the host qualification mechanism
   must be specified in PRD 00166 before build.
5. **Only sudo is expected to ask for a password.** Non-sudo commands run
   with `start_new_session=True`, so `open("/dev/tty")` fails with ENXIO and
   accidental tty use fails closed. This raises the bar, it is not a
   boundary: a same-uid child can still open the pty by name
   (`/dev/ttysNNN` is owned by the user, mode 0620) or raise a GUI dialog
   (`osascript display dialog`). So `show()` states the rule on every
   request: `password: none expected` for non-sudo, `password: sudo asks
   once, after the PIN` for sudo. Any other password prompt is fake.
6. **Tests ship with each behaviour**, in `~/bin/tests/test_warrant.py`:
   - unreadable agent-writable file argument (chmod 000 under
     `agent_writable_roots`) refuses, settles, unblocks; an unreadable
     non-agent-writable file argument is stat-pinned and runs;
   - the PIN callback chmods the agent-writable file argument to 000 after
     review: launch refuses, settles, unblocks;
   - a copy of `/bin/echo` at mode 0111 in a trusted root runs and prints
     `stat-pinned`; the same binary swapped for a new inode after review is
     refused as changed;
   - a fake `sudo` in a trusted root: plain form resolves and shows the inner
     command, `-u`, `-E` and `FOO=1` forms refuse, the launch log shows `-k`
     before the command, the same request from an agent-writable cwd
     refuses;
   - `show()` prints `password: sudo asks once, after the PIN` for a sudo
     request and `password: none expected` for any other;
   - a brokered `sh -c 'exec </dev/tty'` fails under the fixture (skipped when
     the test process itself has no tty).

### Nice to have

- `-u USER` once a non-root target user is needed; not now.

### Out of scope

- The warrant notify defect (`could not notify the human`, again on this
  request; PRD 00160 findings). Unchanged.
- sudoers edits of any kind (NOPASSWD rules, secure_path); see Discovery Log.
- Deriving agent-writable roots from the profile (discovery 00162 / PRD 00163)
  and the model approver (00161). This change touches `review()`, `show()`,
  `execute()` and `launch()` only and lands before or after either without
  conflict beyond line moves.
- Seatbelt profile changes.

## Constraints

- Stdlib Python under `/opt/homebrew/bin/python3`, one file, deployed by a
  human act as in 00159 Phase 1 (`~/bin` is written only through warrant;
  draft in the scratchpad, `cp` request so the source is hashed).
- The agent cannot verify sudo end to end: warden denies `sudo` in-session and
  `approve` works only unsandboxed. Host protocol below.
- sudo on macOS 26.5.2: version unknown from the sandbox (`/usr/bin/sudo`
  unreadable, no plugin dir at `/usr/libexec/sudo`). If `sudo -V` reports
  1.9.14 or later, `use_pty` is on by default and the inner command's stderr
  arrives merged into stdout; cosmetic. `passwd_timeout` (5 min) is shorter
  than `exec_timeout_sec` (600), so an unanswered prompt ends as exit 1, not
  a warrant timeout. `/etc/pam.d/sudo_local` is absent, so no Touch ID path.

## Codebase Context

- **Relevant code**: `~/bin/warrant` `review()` 315-338 (hash at 337),
  `show()` 341-358, `execute()` 370-382 (DEVNULL, capture, `TERM=dumb`, no
  setsid), `launch()` 385-402 (re-hash and refuse on change), `decide()`
  422-457 (the narrow `except` at 434), `main()` 614-619 (where the errno
  surfaced).
- **Conventions**: `test_warrant.py` loads the script with `SourceFileLoader`,
  `WarrantCase.setUp` builds a `Site` with `trusted_exe_roots` `/usr/bin`,
  `/bin` and fakes executables with `chmod 0o755` (lines 378-424); tests name
  the rule they enforce.
- **Integration points**: `fingerprint()` replaces `sha256_file` at 337, 310
  and 387/393; the sudo branch sits in `review()` after `resolve_exe`;
  `-k` and `start_new_session` sit in `execute()`; the note in `show()`.
- **Similar implementations**: sysup's `SudoPrime`
  (`gems/src/tools/sysup/capabilities/sudo.py`) primes a ticket with `sudo -v`
  and refreshes it with `sudo -n -v` to avoid prompts mid-run. Warrant wants
  the opposite (a prompt per root request), which is why requirement 4 uses
  `-k`. Same mechanism, inverted intent.

## Success Criteria

- Approving a request whose agent-writable file argument is chmod 000 prints
  `refused ...`,
  writes a `refused` ledger line and result, and `warrant wait` on it exits
  126 within one poll.
- On the host, from a sandboxed session: `~/bin/warrant request -- sudo
  /usr/bin/true` is approved with the PIN, then prompts `Password:` even
  though the approver ran `sudo -v` in the same pane a minute earlier, then
  records `executed ... exit 0`; the review showed two `exe` lines and the
  `stat-pinned` marker on `/usr/bin/sudo`.
- `~/bin/warrant request -- sudo -u bob id` and `-- sudo FOO=1 id` are refused
  with the options message; nothing runs.
- `~/bin/warrant request -- sh -c 'echo x > /dev/tty'` executes with a
  non-zero exit and nothing appears on the approver's terminal (this closes
  `/dev/tty` only; see Risks).
- The historical stranded request is separately inspected and settled if
  still present; TTL alone does not remove it in the current broker. Verify
  the fixed path with harmless `sudo /usr/bin/true`, not the old indexing job.
- The current `test_warrant*.py` suite stays green on the host; PRD 00163
  already removed `test_warrant_mirror.py`.
- Authentication-policy fixtures cover cached credentials, password-free
  policy and failed invalidation; unsupported or unproven cases never launch
  the root command. The host protocol qualifies the actual supported policy.

## Risks

- **Root behind a 4-digit PIN.** Gated by requirement 4: the password
  prompt cannot be skipped by a fresh ticket. Requirement 3 makes the review
  show the real program (resolved under trusted roots, launched by absolute
  path); it does not limit what root can do.
- **Root running agent-controlled code.** `sudo make install` from an
  agent-writable cwd hands root to the agent's Makefile, hooks or package
  scripts. Requirement 3 refuses sudo from an agent-writable cwd.
- **Fake prompts.** Enabling one legitimate password prompt trains the human
  to type a password after the PIN. Requirement 5 removes `/dev/tty` from
  every non-sudo child; sudo's inner command keeps it but already runs as
  root. Residual: a same-uid child can open `/dev/ttysNNN` by name (owner
  rw) or raise an `osascript` dialog. The defence there is the `password:`
  line `show()` prints on every request.
- **Commands that need a tty now fail.** `git` credential prompts or an
  interactive installer under `start_new_session` fail closed and show in the
  result. Acceptable: warrant brokers non-interactive commands by design, and
  `SSH_AUTH_SOCK` still carries ssh.
- **Signal delivery.** A detached child does not get the approver's Ctrl-C
  from the terminal; `subprocess.run` kills it on `KeyboardInterrupt`, so the
  behaviour matches today.
- **PATH for the inner command's own children** still comes from `exec_path`
  (`/opt/homebrew/bin` and `~/.local/bin` are user-writable, not
  agent-writable). Unchanged exposure, now documented.

## Discovery Log (2026-10-17)

### Q1: Is this a sudo problem or a review problem?
**Answer** (from code and spool, not asked): a review problem first. The
hash of an exec-only binary raises, the exception class is not caught where
verdicts are made, and the request is never settled. sudo is merely the first
exec-only binary anyone asked for.

### Q2: Should warrant broker root at all?
**Answer** (inferred, open to reversal): yes, in the plain form. Alternatives
on the ladder:

- (a) **Refuse cleanly, keep root human-typed.** Smallest change (layer 1
  only). Rejected as the end state: it throws away the ledger line and the
  captured output for the one class of operation where both matter most, and
  the human is already present at a terminal typing a PIN.
- (b) **Generic fix only: stat-pin unreadable executables.** sudo then works
  implicitly, prompting on `/dev/tty`. Accepted as the base, insufficient
  alone: the inner program is chosen by sudo's PATH and a fresh ticket skips
  the prompt.
- (c) **(b) plus sudo hygiene**: plain form, inner command resolved, `-k`,
  detached non-sudo children. Accepted. About forty lines plus tests.
- (d) **sudoers NOPASSWD rules for brokered commands.** Rejected: permanent
  system policy that makes the PIN the only gate for root; each rule is an
  edit to a root-owned file the agent then wants brokered too.
- (e) **Run approve itself under sudo.** Rejected: the ledger and config get
  written as root, every brokered command runs as root whether asked or not.
- (f) **An interactive pass-through mode (child inherits stdin and stdout).**
  Rejected: it is the fake-prompt surface of risk 2 made official, and
  warrant's results contract is captured output.

### Q3: Force the password or accept sudo's ticket window?
**Answer** (safe default chosen, user may reverse): force it with `sudo -k`.
One line. The ticket window exists to spare a human retyping during their own
session; here the typing is the gate.

### Q4: Where does `start_new_session` belong?
**Answer**: in this change, not a separate one. It becomes necessary the
moment a password prompt after the PIN is normal; shipping sudo without it
opens the phishing path and closing it later means a second deploy of
`~/bin/warrant`.

## Open questions

1. Requirement 4: keep forcing the password prompt, or let a fresh ticket
   pass? Default above is force; say so if that is one prompt too many.
2. `exec_path` for sudo requests: leave as is, or drop `/opt/homebrew/bin` and
   `~/.local/bin` when argv[0] is sudo so root's children resolve only system
   paths? Not needed for the inner command after requirement 3.
3. Historical request `bf2aa6d0`: inspect its current state before deciding
   whether manual rejection is still needed. TTL is checked at approval, not
   automatic settlement; discovery 00171 covers cleanup. Do not execute the
   old indexing command merely to verify this fix.
4. **Before building PRD 00166:** define how root brokerage qualifies fresh
   authentication and refuses password-free/unproven policies without sudoers
   edits. `-k` alone is insufficient; update the existing PRD's requirements,
   fixtures and host protocol rather than generating another PRD.

## Next step

Amend existing backlog PRD 00166 before build; do not create a duplicate.
Reconcile its `sudo -k` guarantee with requirement 4's authentication-policy
qualification and failure behavior. Deploy remains a human act as in 00159.

## Discovery review (2026-10-18)

All five standard-depth lenses ran. F1 (Integrity, Blocking) resolved in
requirements: ticket invalidation is not proof of mandatory authentication;
PRD 00166 needs the same correction before build. F14 (Coherence,
Non-blocking) resolved by pointing to that existing PRD and removing the
retired mirror-suite expectation. No root command or security change ran.
The host qualification mechanism remains a specification prerequisite.
Evidence: local `~/bin/warrant`, `~/bin/run-agent`, backlog PRD 00166 and
the official [sudo manual](https://raw.githubusercontent.com/sudo-project/sudo/main/docs/sudo.man.in).

## PRD coverage check (2026-10-18)

PRD created: yes. Verified files: [buvis 00166](/Users/bob/.claude/docs/dev/project-management/prds/backlog/00166-broker-root-commands-through-warrant-v1.md) (backlog).

Existing PRD 00166 owns this work; its authentication qualification remains a build prerequisite.
