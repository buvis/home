---
default_model: opus
---

# Build the warrant approval broker

Source: handoff of 2026-10-16 (SSH-friendly approval path for operations the
agent Seatbelt denies). Deployed 2026-10-16: buvis `09e401cd` (broker, tests,
config) and the following commit (Seatbelt deny-read). The user still has to
re-run `~/bin/warrant init` to replace the passphrase with a PIN.

## Problem

`~/bin/run-agent` wraps the whole agent in `/usr/bin/sandbox-exec` with
`~/.config/seatbelt/ai-agents.sb`. Some legitimate operations fall outside the
profile's write allowlist, for example a commit in the bare dotfiles repo
(`~/.buvis/index.lock`). The only way out today is launching a whole session
with `run-agent --no-sandbox`, which the user rejected. The agent needs a way
to ask for one exact operation, and a human over SSH needs a way to run it
outside the sandbox, without the agent being able to approve or forge it.

### Verified on 2026-10-16 (observations, not assumptions)

- run-agent execs sandbox-exec; the profile is the only boundary. No Codex
  setting lifts it: Codex's macOS sandbox is a second, inner sandbox-exec
  (codex-rs/core README: "Expects `/usr/bin/sandbox-exec` to be present"), and
  an approved `require_escalated` rerun drops only the inner one.
- Codex 0.163.0. Config reference: `approval_policy` is `on-request | never`
  (`untrusted` unsupported, `on-failure` deprecated). workspace-write grants
  project roots plus `/tmp` and `$TMPDIR` unless `exclude_slash_tmp` or
  `exclude_tmpdir_env_var` is set; `~/.codex/config.toml` sets neither. A
  `PermissionRequest` hook may allow or deny but "Don't return `updatedInput`",
  and it runs inside the outer sandbox, so it cannot execute outside it.
- This planning session was itself unsandboxed: started from a plain bash over
  SSH (herdr pane), it could list `~/.gnupg` and `~/.docker`, both deny-read
  subpaths of the profile. Only the autopilot loop was under run-agent.
- `~/bin` is the last PATH entry, behind `~/.local/share/mise/installs/*` and
  `~/.local/share/mise/shims`, which the profile lets agents write. A bare
  `warrant` in the human's shell can be shadowed, so the human side is always
  invoked as `~/bin/warrant`.
- The herdr socket (`~/.config/herdr/herdr.sock`) is reachable from the sandbox
  (`(allow network*)`), and `pseudo-tty` plus `file-ioctl` are allowed. A second
  terminal is therefore not a boundary: assume a sandboxed process can drive the
  human's terminal. The boundary must be something the agent cannot read or
  guess.
- Not agent-writable (absent from the allowlist): `~/bin`, `~/.config/warrant`,
  `/opt/homebrew`. Agent-readable: everything outside the deny-read list, so
  the secret file holds only an scrypt hash and `~/.config/warrant` got its own
  deny-read once the secret became a PIN. The Keychain is unreachable from
  the sandbox (AGENTS.md, exit 36) and needs the login password over SSH, so it
  is not a better secret store here.
- `/private/tmp` is `drwxrwxrwt root`; SSH shells here do carry `TMPDIR`, but
  the spool path must not depend on it (a GUI launch and an SSH approve must
  agree), so the spool is `/private/tmp/warrant-<uid>`, created 0700 and
  ownership-checked on every use.

## Solution

One stdlib Python script, `~/bin/warrant` (interpreter pinned to
`/opt/homebrew/bin/python3`, outside agent-writable paths), with two sides
sharing a spool:

- `warrant request [--cwd DIR] [--env K=V]... [--reason TEXT] [--timeout SEC] [--no-wait] -- CMD ARG...`
  (agent, inside the sandbox): writes a JSON request (random 128-bit id, argv,
  cwd, declared env, reason, created) to `/private/tmp/warrant-<uid>/requests/`,
  pings the human through `~/.claude/hooks/notify.py --send` (ntfy when away,
  desktop otherwise), and polls `results/<id>.json`. It never executes
  anything. Exit codes: the command's once executed, 124 still pending (the
  request stays in the spool; re-attach with `warrant wait ID`), 125 rejected,
  126 refused by policy. `--no-wait` returns right after submitting.
- `warrant wait ID [--timeout SEC]` (agent): re-attach to a pending request.
  Needed because the agent's shell tool call cannot block for long (Claude
  Code: 2 minutes by default, 10 at most) while the human may approve an hour
  later over SSH from a phone. A request lives until decided or
  `request_ttl_sec` (24h).
- `~/bin/warrant approve [ID]` (human, SSH shell, outside the sandbox): reads
  the request once into memory, refuses ids already in the ledger and requests
  older than `request_ttl_sec`, resolves the executable through a fixed
  `exec_path`, refuses executables under any agent-writable root or glob,
  hashes the executable and every argument that names an existing file (for a
  small agent-writable text file it also prints the first 20 lines of the very
  bytes it hashed), prints the whole operation, then prompts for the PIN with
  `getpass`. Before the prompt it refuses while locked (three misses within
  ten minutes) and writes an `attempt` line to the ledger; if that write
  fails, as it does inside the sandbox, no PIN is read. Empty input rejects
  (verdict written, agent unblocked); a mismatch decides nothing but is
  written to the ledger as `mismatch`.
  On a match it re-hashes the files and the executable and refuses if anything
  changed, then runs the resolved executable (not the symlink) with a minimal
  env (fixed PATH, HOME, USER, LOGNAME, LANG, TERM, configured `inherit_env`,
  declared keys; loader keys such as `DYLD_*`, `LD_*`, `PATH`, `PYTHON*` are
  refused), stdin closed, output captured, timeout `exec_timeout_sec`. It
  writes the result, appends `~/.config/warrant/ledger.jsonl`, deletes the
  request. An id is decided once; a replay is refused from the ledger.
- `warrant init` sets a 4 to 8 digit PIN (scrypt n=2^17, about 0.3s per
  check, 0600 file); `warrant list` shows the spool.

Why a PIN and what makes it safe: a 4-digit PIN is 10,000 guesses, so the
secret only holds if nothing can test guesses at speed. Three things close
that: the Seatbelt profile denies agents reading `~/.config/warrant` (the hash
cannot be cracked offline), `approve` logs the attempt before checking (a
sandboxed broker cannot write the ledger, so it never checks), and three
misses lock approvals for ten minutes (ten thousand guesses would take weeks
and show in the ledger). The human types the PIN only into a prompt they
launched. Why a filesystem spool under `/private/tmp`: both
the outer profile and Codex's inner workspace-write sandbox can write there
with no config change. Why no daemon or web server: the human is present over
SSH; a foreground command they run is the smallest executor, and it has power
only when run outside the sandbox (run inside, its child inherits the profile).

Trust placement: `preflight()` resolves the script, the interpreter and the
config dir and refuses to broker if any lies under a configured agent-writable
root. The request file is never re-read after load, so editing it after the
human saw it changes nothing.

Naming: `warrant` (an authorization for one specific act). Rejected: `fiat`
(too broad), `signet` (implies signing), `escrow` (implies holding value).

## Requirements

### Must have
- No approval, no execution: rejection, expiry, replay, wrong PIN, lockout,
  unwritable ledger, no approver, loader env keys, untrusted executable,
  swapped symlink, or a file argument changed after review each leave nothing
  executed. Pinned by `~/bin/tests/test_warrant.py`:
  `test_no_verdict_means_no_execution_and_request_stays_pending`,
  `test_empty_pin_rejects_without_executing`,
  `test_pin_mismatch_is_logged_and_does_not_block_the_id`,
  `test_three_pin_misses_lock_approvals_for_the_window`,
  `test_guess_is_not_checked_when_the_ledger_cannot_be_written`,
  `test_expired_request_is_refused`,
  `test_replayed_id_is_refused`, `test_request_file_edited_after_load_is_ignored`,
  `test_file_argument_changed_after_review_is_refused`,
  `test_executable_in_agent_writable_root_is_refused`,
  `test_executable_matching_agent_writable_glob_is_refused`,
  `test_symlink_in_agent_writable_root_runs_the_reviewed_target`,
  `test_loader_env_keys_are_refused`, `test_command_env_is_minimal_plus_declared`.
- The approval binds to the in-memory operation shown to the human
  (`test_pin_executes_exact_argv_and_records_ledger`,
  `test_requester_receives_verdict_end_to_end`,
  `test_small_agent_writable_file_head_is_shown`).
- A request outlives the agent's tool call and the human gets told
  (`test_wait_reattaches_to_a_pending_request`, `test_wait_on_unknown_request_fails`,
  `test_submit_pings_the_notify_hook`, `test_missing_notify_hook_reports_false`).
- Broker code, config, PIN hash and ledger live outside agent-writable roots
  (`test_preflight_refuses_agent_writable_config_dir`,
  `test_init_accepts_only_four_to_eight_digits`); the spool is private to the
  uid (`test_spool_must_be_private_and_owned`).
- Deployment is a human act (Phase 1). Agents call `~/bin/warrant request` as a
  plain command; no change to Codex or Claude Code. The one Seatbelt change in
  this PRD is the deny-read on `~/.config/warrant` that the PIN requires.

### Nice to have
- Streaming output for long commands. Skipped: results are captured whole.

## Implementation

### Module: warrant
- **Location**: `~/bin/warrant`; tests `~/bin/tests/test_warrant.py`
- **Responsibility**: request, approve, list, init; trust checks; ledger.
- **Exports** (for tests): `Site`, `Op`, `Refused`, `build_request`, `submit`,
  `request`, `approve_one`, `preflight`, `set_passphrase`, `verify_passphrase`,
  `list_requests`, `EXIT_NO_VERDICT`, `EXIT_REJECTED`, `EXIT_REFUSED`

### Config: ~/.config/warrant/config.json
- `agent_writable_roots`, `agent_writable_globs`: mirror of the profile's
  write allowlist (2026-10-16). Edit both together; the project dir of a
  run-agent session is writable too but unknown here.
- `exec_path` (`/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin`),
  `inherit_env` (`SSH_AUTH_SOCK`), `request_ttl_sec` 86400, `exec_timeout_sec` 600.

### Spool: /private/tmp/warrant-<uid>/{requests,results}
- Untrusted. Created 0700; refused if a symlink, not owned by the uid, or
  group/other accessible. Request and result shapes are in the module docstring
  and `build_request`.

### Dependencies
- warrant: No dependencies (stdlib: argparse, fnmatch, getpass, hashlib, hmac,
  json, secrets, shlex, subprocess)

## Tasks

### Phase 0: Stage (done 2026-10-16, uncommitted)
- [x] Write `~/bin/warrant`, `~/.config/warrant/config.json`,
  `~/bin/tests/test_warrant.py`. Acceptance:
  `/opt/homebrew/bin/python3 -m unittest /Users/bob/bin/tests/test_warrant.py`
  exits 0; `/opt/homebrew/bin/python3 ~/bin/warrant list` passes preflight
  against the real config.

### Phase 1: Deploy (human, approval required)
- [x] Review the three files; `chmod +x ~/bin/warrant`; `~/bin/warrant init`
  (done 2026-10-16 22:35 with a passphrase; re-run after the PIN change to
  switch: it asks for the current secret, then the PIN).
- [x] End to end from a sandboxed session (2026-10-16 22:36). Inside
  `run-agent`, `git add` of the three files failed with
  `Unable to create '/Users/bob/.buvis/index.lock': Operation not permitted`;
  the same argv submitted as request `ac4709f3…` from inside the sandbox was
  approved on the host and executed with exit 0, staging the files. Ledger
  holds both lines. The empty-input rejection was not exercised live; the unit
  test covers it.
- [x] Add to `~/.config/seatbelt/ai-agents.sb`, next to the other deny-read
  rules: `(deny file-read* (subpath (string-append (param "_HOME") "/.config/warrant")))`.
  Prerequisite for the PIN; takes effect for new `run-agent` sessions. The
  agent side (`request`, `wait`) never reads that directory. Verified
  2026-10-16 under `run-agent`: `ls ~/.config/warrant` denied, `warrant list`
  exits 126 with a clean message, `warrant wait` still answers, and
  `~/.config/seatbelt` stays readable.
- [x] Re-run `~/bin/warrant init`: current passphrase, then the PIN twice
  (done 2026-10-16 23:04, by the secret file's mtime).
- [x] Parallel session `23b8263e` hardened `launch()` (buvis `023b46be`):
  cwd resolved at review and re-checked at launch, argument paths
  re-resolved, newly appeared file arguments refused; 29 tests.
- [x] Warden rule in `~/.claude/warden.yaml` (buvis `4459b35c`): `warrant`
  asks by default, `request` and `wait` are allowed. Audit log confirms: the
  pre-rule `warrant list` calls were `ask` on `matchedRule: default`, the
  post-rule `warrant wait` probe was `allow`.
- [ ] Commit `:(top)bin/warrant`, `:(top)bin/tests/test_warrant.py`,
  `:(top).config/warrant/config.json` and the profile change to buvis. Never
  stage `passphrase.scrypt` or `ledger.jsonl`.

Exit criteria: one real operation brokered from a sandboxed session (met);
PIN in place with the deny-read; Codex config and Claude settings unchanged.

### Phase 2: Tighten Seatbelt (separate PRD, after Phase 1 works)
- Revisit the deliberate write exceptions that put agent-writable dirs on the
  human's PATH (`~/.local/share/mise`, `~/Applications`, `~/.local/bin/claude*`).
- Decide whether `/dev` writes can narrow to the session's own tty and whether
  the herdr socket needs to be reachable from the sandbox.
- Add a test that parses the `.sb` allowlist and diffs it against
  `config.json`, so the mirror cannot drift silently.

## Success Criteria

- Every test named under Must have passes with
  `/opt/homebrew/bin/python3 -m unittest /Users/bob/bin/tests/test_warrant.py`.
- Phase 1 end to end: a sandboxed `warrant request` for a `~/.buvis` write
  exits 0 only after the PIN (met 2026-10-16), and exit 125 on empty input.
- The only Seatbelt change is the deny-read on `~/.config/warrant`;
  `~/.codex/config.toml` and `~/.claude/settings.json` are untouched.

## Independent review (2026-10-16)

Two reviewers (security lens, doubt lens) read the deployed code against this
PRD. Dispositions:

- Fixed, CRITICAL (both): agent-written text (argv, reason, agent, paths,
  file heads) reached the approver's terminal raw, so ESC and CR sequences
  could repaint the review and hide the real command. Every line `approve`
  and `list` print now passes `visible()`, which escapes control and format
  characters (`test_display_escapes_control_and_format_characters`).
- Fixed, HIGH: declared env was a denylist, which cannot hold
  (`GIT_SSH_COMMAND`, `GIT_CONFIG_*`, exported bash functions). `allowed_env`
  in config.json is now an allowlist
  (`test_env_keys_outside_the_allowlist_are_refused`).
- Fixed, MEDIUM: the agent-writable mirror cannot know a session's project
  dir, so an executable there passed as trusted. Executables must now also
  resolve under `trusted_exe_roots`
  (`test_executable_outside_trusted_roots_is_refused`).
- Fixed, MEDIUM: `wait_for` could answer "no request or result" in the window
  between the result write and the request unlink, inviting a resubmit
  (`test_wait_reports_a_result_whose_request_is_already_gone`).
- Fixed, verify item: two concurrent approves of one id could both execute.
  `approve` holds an exclusive `flock` on the request from load to finish
  (`test_concurrent_approve_of_one_request_runs_once`).
- Fixed, de-slop: unused `pid` request field dropped. Refuted: the bytes
  branch in `cap()` is live; `TimeoutExpired` carries undecoded bytes even in
  text mode (checked on 3.14).
- Test hardened: the unwritable-ledger simulation now pre-creates a read-only
  ledger so a pre-existing file cannot make it pass vacuously.
- Accepted residuals: the window between the pre-launch re-hash and the
  command opening an agent-writable file argument (substituting content would
  break path semantics such as `git add`; the human sees the head and the hash
  is checked at spawn); `--flag=path` forms are shown raw, not hashed;
  results in the spool can be forged by the agent, which only deceives the
  agent; a corrupt ledger line fails closed; a command's own exit 124-126 is
  ambiguous on the agent side, the result JSON carries the status.

## Decisions (user, 2026-10-16)

1. Passphrase mismatches go to the ledger as `mismatch`; they settle nothing
   and do not block the id.
2. `approve` prints the first 20 lines of small (64 KB) UTF-8 agent-writable
   file arguments, taken from the same bytes it hashed.
3. Requests are never withdrawn on the agent's timeout: the agent's tool call
   cannot block, and the human may approve an hour later from a phone over
   SSH. `warrant wait ID` re-attaches; TTL is 24h; submitting pings the human
   through the notify hook.
4. The secret is a 4 to 8 digit PIN, not a 12-character passphrase, made safe
   by the deny-read on `~/.config/warrant`, the attempt-before-check ledger
   write, and the three-miss lockout.
