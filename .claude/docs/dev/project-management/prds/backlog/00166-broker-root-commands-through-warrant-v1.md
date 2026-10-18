---
default_model: opus
model_tier_rationale: broker trust code gating root behind a 4-8 digit PIN; invented predicates (fingerprint fallback, the exact sudo-argv ban) and a destructive blast radius (root execution), with no exact final text given for them, and deploy is a human warrant act
design: skip
eligibility: /usr/bin/false
---

# Broker root commands through warrant

Source: discovery 00164
(`docs/dev/project-management/discovery/00164-broker-root-commands-through-warrant.md`),
premise confirmed 2026-10-17. Lane: hand-built in a sandboxed or attended
session like PRDs 00159, 00160 and 00163; the `eligibility: /usr/bin/false`
field keeps the unattended drain from picking it, because every deploy target
sits outside the sandbox write allowlist and needs a human to approve the `cp`
through warrant. The agent cannot verify sudo end to end: warden denies `sudo`
in-session and `approve` works only unsandboxed, so the host protocol is
Phase 1.

## Overview

### Problem Statement

A warrant request whose executable or file argument the broker cannot read
during review kills `approve` with a raw errno instead of producing a verdict.
`review()` hashes the resolved executable with `sha256_file(op.exe)`, which
opens the file; `/usr/bin/sudo` is mode 4511 (exec-only, root-readable only),
so the open raises `PermissionError`. `decide()` catches only `Refused` and
`ValueError`, so the error escapes to `main()`, which prints the errno and
exits 126 with no ledger line, no result file, and the agent's `warrant wait`
blocked until the request's 24h TTL expires. This is a crash independent of
sudo: any exec-only binary or root-only file argument (e.g. `/etc/sudoers` at
mode 0440) strands the request.

Beyond the crash, warrant has no stance on sudo. The review shows
`sudo mdutil -E /` but vets and hashes only `sudo`; which `mdutil` root runs is
sudo's PATH lookup, never shown or pinned. Warrant is the agent's only path to
root (warden denies `sudo` to every agent session), so brokering it well
matters, but root removes every Seatbelt cap the PIN relies on.

### Target Users

The solo developer approving agent requests on the host, and any agent whose
task needs one exact root command. Today the fallback is "paste this command,
I will wait", which loses the ledger line and the captured output for the one
class of operation where both matter most.

### Success Metrics

- Every reviewed request settles with a verdict (`refused`, `executed`,
  `rejected` or `timeout`): no request can strand on an unreadable path.
  Pinned by `test_unreadable_executable_runs_stat_pinned` and
  `test_unreadable_agent_writable_file_arg_refuses` green inside the sandbox.
- Brokered sudo runs exactly one canonical shape (`sudo CMD ARG...`) and always
  costs the password. Pinned by `test_sudo_plain_form_resolves_inner_command`,
  `test_sudo_options_and_assignments_refuse` and
  `test_sudo_launch_runs_dash_k_before_the_command` green inside the sandbox.
- On the host, `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'`
  is green with no skipped test, and the host sudo protocol below runs or
  refuses, never strands.

## Functional Decomposition

### Capability: Review failures become verdicts

Any error raised while reviewing or re-checking a request ends as a `refused`
verdict instead of crashing the broker.

#### Feature: Settle review-time OSErrors as refusals

- **Description**: An `OSError` raised while building the `Op` in `review()`,
  or in `launch()`'s re-check after the PIN, is caught and settled as
  `refused` with the error text.
- **Inputs**: A request whose executable or a file argument cannot be read
  (exec-only binary, root-only file at mode 0440), reaching `decide()` and
  `launch()`.
- **Outputs**: A `refused` ledger line via `record()`, a result file via
  `finish()`, the request removed, the agent's `warrant wait` unblocked with
  exit 126 (`EXIT_REFUSED`) within one poll.
- **Behavior**: Widen `decide()`'s `except (Refused, ValueError)` to
  `except (Refused, ValueError, OSError)`; wrap `launch()`'s re-check (the
  `sha256_file`/`fingerprint` calls) so an `OSError` there routes through
  `refuse()`. Same settled shape as a `Refused`.

### Capability: Fingerprint unreadable trusted paths by identity

An executable or file argument that cannot be read is pinned by its inode
identity instead of its content hash, so review no longer requires read access.

#### Feature: fingerprint() helper replaces content-only hashing

- **Description**: One `fingerprint(path)` helper returns a content sha256 when
  the path is readable and a `stat:<dev>:<ino>:<size>:<mtime_ns>` tuple when it
  is not; both `review()` and `launch()` call it for the executable and for
  file arguments.
- **Inputs**: A resolved, trusted (non-agent-writable) path that may or may not
  be readable.
- **Outputs**: A fingerprint string — `sha256 hex` when readable, else the
  `stat:` tuple.
- **Behavior**: Try to open and hash; on `PermissionError`/`OSError` fall back
  to `os.stat` and format the dev/ino/size/mtime_ns tuple. `os.stat` needs only
  search permission on the parent directory, so this works for `/usr/bin/sudo`.
  `launch()` recomputes the same fingerprint and refuses on any change. An
  unreadable path that is agent-writable is refused, never stat-pinned: its
  owner can rewrite it in place and restore dev, ino, size and mtime; only
  non-agent-writable paths are stat-pinned. The trusted-root and
  not-agent-writable checks in `resolve_exe()` still apply. The `stat:` tuple
  is formatted exactly `stat:<dev>:<ino>:<size>:<mtime_ns>` (colon-separated,
  from `os.stat`). `New symbols:` below.

#### Feature: show() prints the pinning mode

- **Description**: `show()` prints `stat-pinned (unreadable, mode <mode> root)`
  where the hash would go for a stat-pinned path, and a file head only when the
  file was readable.
- **Inputs**: An `Op` whose executable or a file argument is stat-pinned.
- **Outputs**: A review line marking the path as stat-pinned with its octal
  mode.
- **Behavior**: Branch the existing `exe` and `file` lines on whether the
  fingerprint is a `stat:` tuple; print `stat-pinned (unreadable, mode <octal> root)`
  (e.g. `mode 4511 root` for `/usr/bin/sudo`) where the sha would go, and
  suppress the head for an unreadable file.

### Capability: Broker sudo in one canonical shape

A request whose resolved executable is named `sudo` is accepted only as
`sudo CMD ARG...`, with the inner command resolved and shown, and the password
always charged.

#### Feature: Restrict sudo argv to the plain form

- **Description**: When the resolved executable's basename is `sudo`, `argv[1]`
  must exist and must not start with `-` or contain `=`; anything else is
  refused.
- **Inputs**: A request whose `argv[0]` resolves (via `resolve_exe()`) to a
  file named `sudo`.
- **Outputs**: Either a reviewed `Op` carrying the inner command as a second
  resolved executable, or a `Refused` with the message
  `put the exact command; sudo options are not brokered`.
- **Behavior**: In `review()`, after `resolve_exe()`, detect `sudo` by the
  resolved path's name. `argv[1]` is the inner program; refuse when `argv[1]`
  is absent, starts with `-`, or contains `=` (bans `-u`, `-i`, `-s`, `-E`,
  `--preserve-env`, and `VAR=value` assignments).
  Resolve `argv[1]` through `resolve_exe()` (trusted root, not agent-writable,
  fingerprinted), carry it so `show()` prints a second `exe` line, exclude it
  from `file_args()`, and launch it by absolute path so sudo's PATH never picks
  the program. A sudo request whose cwd is agent-writable is refused (root
  would run code the agent controls: Makefile, git hooks, package scripts);
  agent-writable file arguments stay allowed, their head shown and re-hashed.
  The ban keeps one canonical shape, not a security boundary (`sudo sh -c`,
  `sudo env`, `sudo sudo` reach the same power); requirement 4's password is
  the gate. `New symbols:` below.

#### Feature: Force the password with sudo -k before launch

- **Description**: Right before launching a sudo request, `execute()` runs the
  resolved sudo with `-k` to invalidate any cached tty ticket, so root always
  costs the password even if the approver typed `sudo` in the same pane
  minutes earlier.
- **Inputs**: An `Op` whose executable is sudo, about to be executed.
- **Outputs**: A side effect — the sudo ticket for this tty is invalidated;
  `-k` needs no password and exits 0.
- **Behavior**: In `execute()`, when the `Op` is a sudo op, run
  `subprocess.run([str(op.exe), "-k"], ...)` with output discarded and
  `check=False`, immediately before the main `subprocess.run`. Resolved
  decision for discovery open question 1: force the prompt (the safe default);
  reversible by deleting one line.

### Capability: Fail accidental tty use closed

Only sudo is expected to prompt for a password; every other brokered child is
detached from the controlling terminal, and the review states the rule.

#### Feature: Detach non-sudo children from the tty

- **Description**: Non-sudo commands run with `start_new_session=True`, so
  `open("/dev/tty")` in the child fails with ENXIO and accidental tty use fails
  closed.
- **Inputs**: An `Op` that is not a sudo op.
- **Outputs**: A child process in a new session with no controlling terminal.
- **Behavior**: In `execute()`, pass `start_new_session=True` to the main
  `subprocess.run` for non-sudo ops (and `False` for sudo ops, which keep the
  controlling tty so the inner command, already root, can prompt). This raises
  the bar, not a boundary: a same-uid child can still open `/dev/ttysNNN` by
  name or raise a GUI dialog.

#### Feature: show() states the password rule on every request

- **Description**: `show()` prints `password: sudo asks once, after the PIN`
  for a sudo request and `password: none expected` for any other, so any other
  password prompt reads as fake.
- **Inputs**: An `Op`.
- **Outputs**: One `password:` review line.
- **Behavior**: Add a `password:` line to `show()` branched on whether the `Op`
  is a sudo op, printing `password: sudo asks once, after the PIN` for a sudo
  op and `password: none expected` otherwise.

## Structural Decomposition

### Repository Structure

```
bin/
├── warrant                     # Maps to: all four capabilities (single-file broker)
└── tests/
    └── test_warrant.py         # Maps to: tests shipped with each behaviour
```

Both files live outside the agent write allowlist and are deployed by a human
warrant act (Phase 1); the agent edits staged copies under
`docs/dev/tmp/00166-stage/`.

### Module: warrant

- **Location**: `bin/warrant`
- **Maps to capability**: Review failures become verdicts; Fingerprint
  unreadable trusted paths by identity; Broker sudo in one canonical shape;
  Fail accidental tty use closed.
- **Responsibility**: Human-approved execution of one exact command outside the
  agent sandbox; this PRD hardens the review, fingerprinting, sudo handling and
  child-session parts of it.
- **Exports** (module-level functions edited; warrant is a script, not an
  importable package):
  - `review()` - detect sudo, resolve the inner command, call `fingerprint()`,
    refuse agent-writable sudo cwd.
  - `launch()` - re-check with `fingerprint()`; its re-check `OSError` routes
    through `refuse()`.
  - `decide()` - catch `OSError` alongside `Refused` and `ValueError`.
  - `execute()` - run `sudo -k` before a sudo command; pass
    `start_new_session=True` for non-sudo children.
  - `show()` - print the stat-pinned marker and the `password:` line.
- New symbols: `fingerprint`

### Module: test_warrant

- **Location**: `bin/tests/test_warrant.py`
- **Maps to capability**: all four (one test per shipped behaviour).
- **Responsibility**: Pin each behaviour inside the sandbox. Loads the script
  with `SourceFileLoader`; `WarrantCase.setUp` builds a `Site` with
  `trusted_exe_roots` `/usr/bin` and `/bin` and fakes executables with
  `chmod 0o755`; tests name the rule they enforce.
- **Exports** (new test methods on `WarrantCase`):
  - `test_unreadable_agent_writable_file_arg_refuses` - chmod 000 file argument
    under `agent_writable_roots` refuses, settles, unblocks.
  - `test_unreadable_non_agent_writable_file_arg_stat_pinned` - an unreadable
    non-agent-writable file argument is stat-pinned and runs.
  - `test_pin_callback_chmods_file_arg_zero_then_launch_refuses` - the PIN
    callback chmods the agent-writable file argument to 000 after review;
    launch refuses, settles, unblocks.
  - `test_unreadable_executable_runs_stat_pinned` - a copy of `/bin/echo` at
    mode 0111 in a trusted root runs and the review prints `stat-pinned`.
  - `test_stat_pinned_executable_swapped_inode_refuses` - the same binary
    swapped for a new inode after review is refused as changed.
  - `test_sudo_plain_form_resolves_inner_command` - a fake `sudo` in a trusted
    root: plain form resolves and shows the inner command.
  - `test_sudo_options_and_assignments_refuse` - `-u`, `-E` and `FOO=1` forms
    refuse with the options message.
  - `test_sudo_launch_runs_dash_k_before_the_command` - the launch log shows
    `-k` before the command.
  - `test_sudo_from_agent_writable_cwd_refuses` - the same sudo request from an
    agent-writable cwd refuses.
  - `test_show_prints_password_rule` - `show()` prints
    `password: sudo asks once, after the PIN` for a sudo request and
    `password: none expected` for any other.
  - `test_detached_child_cannot_open_dev_tty` - a brokered
    `sh -c 'exec </dev/tty'` fails under the fixture (skipped when the test
    process itself has no tty).
  - New symbols: `test_unreadable_agent_writable_file_arg_refuses`, `test_unreadable_non_agent_writable_file_arg_stat_pinned`, `test_pin_callback_chmods_file_arg_zero_then_launch_refuses`, `test_unreadable_executable_runs_stat_pinned`, `test_stat_pinned_executable_swapped_inode_refuses`, `test_sudo_plain_form_resolves_inner_command`, `test_sudo_options_and_assignments_refuse`, `test_sudo_launch_runs_dash_k_before_the_command`, `test_sudo_from_agent_writable_cwd_refuses`, `test_show_prints_password_rule`, `test_detached_child_cannot_open_dev_tty`

## Dependency Graph

### Foundation Layer (Phase 0)

- **warrant: review failures become verdicts + fingerprint()**: No dependencies
  — the crash fix and `fingerprint()` are built first; every later feature
  calls `fingerprint()` and relies on review errors settling rather than
  crashing.

### Core Layer (Phase 0, after foundation)

- **warrant: sudo canonical form, `-k`, detached children, show() lines**:
  Depends on [fingerprint()] — the inner sudo command is fingerprinted, and
  `show()`'s stat-pinned branch is shared with the sudo second-`exe` line.

### Integration Layer (Phase 1)

- **host deploy + verification**: Depends on [all Phase 0 features] — the staged
  `warrant` and `test_warrant.py` are copied to `~/bin` by a human warrant act
  and verified against the real sudo on the host.

## Implementation Phases

All Phase 0 work edits staged copies under `docs/dev/tmp/00166-stage/bin/`
inside the sandbox. First copy `~/bin/warrant` and `~/bin/tests/test_warrant.py`
into that staging layout and confirm the staged suite is green before any edit:
`/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00166-stage/bin/tests -t docs/dev/tmp/00166-stage/bin/tests -p 'test_warrant.py'`.

### Phase 0: Harden the broker (agent, inside the sandbox)

**Goal**: The staged `warrant` settles unreadable-path reviews as refusals,
pins unreadable trusted paths by inode, brokers sudo in the plain form with the
password forced, and detaches non-sudo children — all pinned by staged tests.

**Tasks**:
- [ ] Stage the two files and confirm the baseline suite is green (no deps) -
  Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00166-stage/bin/tests -t docs/dev/tmp/00166-stage/bin/tests -p 'test_warrant.py'`
  exits 0 before any edit.
- [ ] In `docs/dev/tmp/00166-stage/bin/warrant`, widen `decide()` to catch
  `OSError` beside `Refused` and `ValueError`, and route `launch()`'s re-check
  `OSError` through `refuse()` (no deps) - Acceptance:
  `test_unreadable_agent_writable_file_arg_refuses` and
  `test_pin_callback_chmods_file_arg_zero_then_launch_refuses` pass and the
  request settles with a `refused` result and exit 126.
- [ ] In `docs/dev/tmp/00166-stage/bin/warrant`, add `fingerprint(path)` and
  replace the three `sha256_file` call sites (`review()` executable,
  `file_args()`/`inspect_file()`, `launch()` re-check) with it; refuse an
  unreadable agent-writable path (depends on: Phase 0 crash fix) - Acceptance:
  `test_unreadable_executable_runs_stat_pinned` and
  `test_stat_pinned_executable_swapped_inode_refuses` pass.
- [ ] In `docs/dev/tmp/00166-stage/bin/warrant`, add the sudo branch to
  `review()`: plain-form check on `argv[1]`, resolve the inner command via
  `resolve_exe()`, carry it on the `Op`, exclude it from `file_args()`, refuse
  an agent-writable sudo cwd (depends on: fingerprint()) - Acceptance:
  `test_sudo_plain_form_resolves_inner_command`,
  `test_sudo_options_and_assignments_refuse` and
  `test_sudo_from_agent_writable_cwd_refuses` pass.
- [ ] In `docs/dev/tmp/00166-stage/bin/warrant`, run `sudo -k` before a sudo
  command and pass `start_new_session=True` for non-sudo children in
  `execute()` (depends on: sudo branch) - Acceptance:
  `test_sudo_launch_runs_dash_k_before_the_command` and
  `test_detached_child_cannot_open_dev_tty` pass.
- [ ] In `docs/dev/tmp/00166-stage/bin/warrant`, add the `stat-pinned` marker
  and the `password:` line to `show()` (depends on: fingerprint(), sudo branch)
  - Acceptance: `test_show_prints_password_rule` passes and
  `test_unreadable_executable_runs_stat_pinned` finds `stat-pinned` in the
  review text.
- [ ] Add the eleven new test methods listed in the test_warrant module block
  to `docs/dev/tmp/00166-stage/bin/tests/test_warrant.py` (depends on: all
  above) - Acceptance: `/opt/homebrew/bin/python3 -m unittest discover -s docs/dev/tmp/00166-stage/bin/tests -t docs/dev/tmp/00166-stage/bin/tests -p 'test_warrant.py'`
  exits 0 with the eleven new tests collected and no skips except the
  `test_detached_child_cannot_open_dev_tty` tty skip.

**Exit Criteria**: The staged suite passes inside the sandbox with the eleven
new tests present; `rg -n "fingerprint" docs/dev/tmp/00166-stage/bin/warrant`
shows the helper and its call sites.

### Phase 1: Deploy and verify (human on the host, or warrant requests the human approves)

**Goal**: The hardened `warrant` and tests reach `~/bin`, the host suite is
green against the real sudo, and the sudo protocol runs or refuses as specified.

Premise for every task here: the staged files are tested and the live host
sudo differs from the sandbox (unreadable in the sandbox). Re-check at
execution; a failed premise means skip and report, never force. Deploy is a
human warrant act as in PRD 00159 Phase 1: draft in the scratchpad, `cp` request
so the source is hashed.

**Tasks**:
- [ ] `cp docs/dev/tmp/00166-stage/bin/warrant ~/bin/warrant` and
  `cp docs/dev/tmp/00166-stage/bin/tests/test_warrant.py ~/bin/tests/test_warrant.py`
  via warrant requests the human approves (depends on: Phase 0) - Acceptance:
  `~/bin/warrant list` passes preflight against the real profile and prints the
  spool or `warrant: nothing pending`; a `diff` of the deployed files against
  the staged copies is empty.
- [ ] Run the host suite including the mirror
  (depends on: deploy) - Acceptance:
  `/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'`
  is green on the host with no skipped test except the tty skip.
- [ ] Run the host sudo protocol (depends on: deploy) - Acceptance:
  `~/bin/warrant request -- sudo /usr/bin/true` is approved with the PIN, then
  prompts `Password:` even though the approver ran `sudo -v` in the same pane a
  minute earlier, then records `executed ... exit 0`, and the review showed two
  `exe` lines with the `stat-pinned` marker on `/usr/bin/sudo`;
  `~/bin/warrant request -- sudo -u bob id` and `-- sudo FOO=1 id` are refused
  with the options message and nothing runs;
  `~/bin/warrant request -- sh -c 'echo x > /dev/tty'` executes with a non-zero
  exit and nothing appears on the approver's terminal; a re-submitted
  `sudo mdutil -E /` runs or is refused, never stranded (the stranded request
  `bf2aa6d0` is left to expire at its 24h TTL — resolved decision for discovery
  open question 3).
- [ ] One commit for the two paths, then push (depends on: host suite green) -
  Acceptance:
  `git --git-dir=~/.buvis --work-tree=~ commit -m "feat(warrant): broker root commands through sudo hardening" -- ':(top)bin/warrant' ':(top)bin/tests/test_warrant.py'`
  then `git --git-dir=~/.buvis --work-tree=~ show --stat HEAD` lists exactly
  those two paths; never stage `passphrase.scrypt` or `ledger.jsonl`.

**Exit Criteria**: Host suite green, sudo protocol passed, commit pushed.

## Test Strategy

### Critical Scenarios

- **Happy path**: `sudo /usr/bin/true` approved → Expected: `/usr/bin/sudo`
  stat-pinned and shown, inner `/usr/bin/true` resolved and shown, `sudo -k`
  run before the command, password prompted, `executed exit 0` recorded.
- **Edge case**: unreadable non-agent-writable file argument (a copy of
  `/bin/echo` at mode 0111 in a trusted root) → Expected: stat-pinned and runs;
  the same binary swapped for a new inode after review → refused as changed.
- **Error case**: unreadable agent-writable file argument (chmod 000 under an
  agent-writable root) → Expected: `refused`, ledger line, result file,
  `warrant wait` exits 126 within one poll — never a stranded request.

## Risks

- **Root behind a 4-digit PIN**: Mitigated by forcing `sudo -k` before every
  sudo launch so a fresh ticket cannot skip the password; the review shows the
  real inner program resolved under trusted roots and launched by absolute path.
- **Root running agent-controlled code**: Mitigated by refusing a sudo request
  whose cwd is agent-writable (`sudo make install` would hand root to the
  agent's Makefile, hooks or package scripts).
- **Fake prompts**: Mitigated by `start_new_session=True` for non-sudo children
  (removes `/dev/tty`) and the `password:` line `show()` prints on every
  request. Residual: a same-uid child can open `/dev/ttysNNN` by name or raise
  an `osascript` dialog; the defence there is the printed rule.
- **Commands that need a tty now fail closed**: Acceptable — warrant brokers
  non-interactive commands by design; `git` credential prompts or an
  interactive installer fail closed and show in the result; `SSH_AUTH_SOCK`
  still carries ssh.
- **Agent cannot verify sudo end to end**: Mitigated by the Phase 1 host
  protocol run by the human; the sandbox verifies everything a fake `sudo`
  fixture can cover.
