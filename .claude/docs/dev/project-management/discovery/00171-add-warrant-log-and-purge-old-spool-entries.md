# Discovery: Add warrant log and settle old spool entries

## Classification

Depth: standard | Date: 2026-10-18 | Status: not reviewed
Seeded from session 523838c3 follow-ups; user instruction 2026-10-18: 'all of
them must be recorded as discovery documents that I will go through'. The
item was listed as optional polish in PRD 00160 ("`warrant log` plus purge of
old spool results"). Written from a sandboxed session: `~/.config/warrant`
(config, ledger) was not read; everything about the ledger comes from
`~/bin/warrant`, and everything about the spool from `ls` and `stat`.

## Premise check

**Partly confirmed.** Two of the seed's three claims hold; the third is
wrong in a useful way.

- **No command shows history.** `list` prints only files still in
  `requests/` (`warrant:587-603`). Nothing reads results or prints the
  ledger. The human's only way to see past decisions is to open
  `ledger.jsonl` raw, which prints agent-controlled `argv` and `cwd`
  unescaped on a terminal, the exact attack `visible()` exists to stop
  (`warrant:160-168`).
- **Expired requests are never settled on their own.** The TTL is checked in
  one place, `decide()` (`warrant:487-488`), so only an `approve` of that id
  settles it. `list` labels it `expired` and leaves it (`warrant:601`).
  `wait_for()` has no TTL check (`warrant:555-568`) and the agent cannot
  learn the TTL anyway, since `config.json` sits in the denied
  `~/.config/warrant`. Observed twice in session 523838c3: the wait on
  `0ab414fb` blocked for over 24 hours and ended only when the user tried to
  approve it ("request expired; submit a fresh one", exit 126); request
  `bf2aa6d0` (2026-10-17 10:39, the stranded sudo request of discovery 00164)
  is still in `requests/` today, its wait long killed.
- **"Nothing deletes results" is wrong.** macOS runs
  `/System/Library/LaunchDaemons/com.apple.tmp_cleaner.plist` daily at 00:00.
  `/usr/libexec/tmp_cleaner` deletes files under `/tmp` whose atime, mtime and
  ctime are all older than 3 days, and empty directories older than 3 days
  (`tmp_cleaner:8-9,17-30`). The oldest result (`ac4709f3`, mtime 2026-10-16
  22:36) is under 3 days old, which is why all 36 are still there. Results
  therefore live 3 days or more (a read of a result refreshes atime), then
  vanish without a ledger trace. The same sweep can delete an expired request
  that nobody approved, after which `wait` answers "no request or result"
  (`warrant:562-564`, exit 2).

## Problem

The human cannot review what warrant has done without reading a file that
can repaint their terminal. A request that nobody approves in 24 hours keeps
its agent's `wait` blocked until a human happens to `approve` that id or
macOS sweeps it, and the agent then gets either a refusal or "no request",
never "expired". Results, which carry up to 1 MB each of a brokered
command's stdout and stderr (`warrant:418-422`), sit for at least 3 days in
a spool every sandboxed session can read and write.

## What the code records (from `~/bin/warrant`, not the ledger file)

Every line is `{"id", "decision", "at", ...}` with sorted keys
(`warrant:275-280`):

| decision | extra fields | written at |
|----------|--------------|------------|
| `attempt` | none | `warrant:497`, before the PIN is read |
| `mismatch` | `argv` | `warrant:509` |
| `rejected` | `argv`, `cwd` | `warrant:504` |
| `refused` | `reason`, `argv` (null when refused before review) | `warrant:290` |
| `executed`, `timeout` | `exit`, `argv`, `cwd` | `warrant:453` |

Not recorded: `reason` given by the agent, `agent`, declared `env`, the
executable's hash, stdout and stderr. The output reaches the human only on
screen at approve time (`warrant:455`) and the agent only through
`results/<id>.json` (`warrant:283-285`). The ledger is read whole by
`decided()` and `lockout_until()` on every call (`warrant:253-272`), so it
must never be truncated by a purge: settled ids guard against replay
(`warrant:483-485`) and mismatches drive the lockout.

## Spool exposure

`/private/tmp/warrant-501` is mode 0700 and owner-checked
(`warrant:171-176`), but agents run as the same uid and the profile grants
writes to all of `/private/tmp/` (`ai-agents.sb`, `(subpath "/private/tmp/")`).
So any sandboxed session, in any project, can read every result, delete any
request or result, and forge a result for another session's pending request
(which that session's `wait` reports as real, `warrant:559-560`). PRD 00159
treats the spool as untrusted data by design, and the ledger stays the
record of truth. The new fact is the leak: a brokered command's output is
something the requesting agent asked for, but it is readable by every other
agent session for at least 3 days. Outputs that could matter: `git push`
remote messages, `mise install` logs, diagnostic scripts, and any approved
command that prints a file the profile denies agents (the broker runs
unsandboxed, so a `cat` the human approves bypasses the read deny for every
session, not just the requester).

## Who purges

- **Agent side** may delete only results it has already reported, and only
  its own: any agent can already delete anything in the spool, so this is a
  hygiene rule for honest agents, not a boundary. Deleting on first read
  breaks re-attach after a context reset (session 523838c3 re-read wait
  outputs several times), so the agent side keeps results.
- **Human side** settles and prunes. It can read the config (TTL) and write
  the ledger, so it is the only side that can turn "expired" into a verdict
  the waiting agent understands. It must never delete a request that has
  not been settled in the ledger first: the ledger line is the evidence, the
  spool file is only the delivery.

## Requirements (proposed)

### Must have

1. **`warrant log` (human side).** Prints ledger entries oldest first, one
   line each: local time, short id, decision, exit or reason, `shlex.join`
   of argv, cwd. Every field passes through `guard()`. Filters: `--id
   PREFIX`, `--since YYYY-MM-DD`, `--decision NAME` (repeatable), `--last N`
   (default 50). Unknown keys print as `key=value` so lines added by PRD
   00165 (`decision auto`, rule id) show without a code change. A malformed
   line prints as `INVALID line N` and does not stop the listing. Runs
   through the existing preflight and needs no tty or PIN.
2. **Expired requests settle as refused.** One helper, `settle_expired(site,
   now)`, runs at the start of `list` and `approve`: for each request past
   `request_ttl_sec`, take the same per-request `flock` approve takes
   (`warrant:470`), skip it if held, else call the existing `refuse()` with
   "request expired; submit a fresh one". That writes the ledger line, the
   result and unlinks the request, so a waiting agent exits 126 at its next
   poll. A request whose JSON or id is invalid settles the same way.
3. **Old results are pruned by age, human side.** The same pass deletes
   `results/*.json` older than `result_ttl_sec` (new config key, default
   86400) by mtime, and only when the ledger holds a settled entry for that
   id; anything else stays for a human to look at. Prints one summary line
   (`pruned N results`) when N > 0.
4. **Tests** in `~/bin/tests/test_warrant.py`, `WarrantCase` style
   (`created=time.time() - 901` against the fixture's 900 s TTL, as in
   `test_expired_request_is_refused`, `test_warrant.py:181-185`):
   - an expired request is settled by `list`: ledger `refused`, result
     present, request gone, `wait_for` returns `EXIT_REFUSED`;
   - an expired request under another holder's `flock` is left alone;
   - a fresh request survives `list`;
   - a settled result older than `result_ttl_sec` is pruned; an equally old
     result with no ledger entry is kept; a fresh settled one is kept;
   - `log` escapes an argv carrying `\x1b[2J` and filters by id prefix,
     decision and `--last`;
   - `log` shows an unknown ledger key and survives a malformed line.

### Nice to have

- Record the agent's `reason` and `agent` in the `executed`, `rejected` and
  `refused` lines so `log` can show why a command ran. Agent-controlled, so
  escaped on display like everything else.
- `warrant log --show ID` prints that id's result file too while it exists.

### Out of scope

- Truncating, rotating or compacting the ledger. It is the replay guard and
  the lockout counter.
- Moving the spool out of the agent-writable `/private/tmp`, or signing
  results so a forged one is detected. Both change the PRD 00159 trust model;
  see Open questions.
- Agent-side expiry detection in `wait` (it cannot read the TTL).
- A launchd job that runs the settle pass on a timer. PRD 00165's
  foreground `serve` is the natural home for a periodic pass.

## Constraints

- One stdlib file under `/opt/homebrew/bin/python3`; deploy through warrant
  as in PRD 00159 (draft in the scratchpad, `cp` request so the source is
  hashed).
- Commands brokered by warrant run without `TMPDIR`, so tests that use
  `tempfile` land under `/private/tmp`; fixtures must not assume otherwise
  (buvis `feb24522`).
- `tmp_cleaner` keeps running; the design must stay correct when it deletes
  any spool file or empty spool directory at midnight (`ensure_spool()`
  recreates directories on submit, `warrant:171-173`; `list` and `pick`
  already tolerate a missing `requests/`, `warrant:589,614`).

## Codebase Context

- **Relevant code**: `record` 275-280, `finish` 283-285, `refuse` 288-292,
  `approve_one` 460-474 (the flock), `decide` 477-512 (the only TTL check),
  `wait_for` 555-568, `list_requests` 587-603, `main` 623-666 (subcommands).
- **Conventions**: subcommands are argparse subparsers in `main`; human-side
  output goes through `guard(out)`; tests inject `now` and `out=quiet`, read
  results with `self.result(id)` and the ledger with `self.last_entry()`.
- **Integration points**: `settle_expired()` called from `list_requests` and
  `pick`/`approve`; a new `log` subparser; `result_ttl_sec` read with a
  default so existing configs keep working (`REQUIRED_CONFIG` unchanged,
  `warrant:85`).
- **Overlap with PRD 00165** (backlog): its foreground `serve` claims
  requests under the same lock, adds `decision auto` and rule-id fields to
  the ledger, and extends `list` with automatic outcomes and pending
  diagnostics. This change is smaller and lands first: `serve` then calls
  `settle_expired()` on its poll, and `log` already prints the new fields
  generically. If 00165 lands first, requirement 2 must also respect its
  durable automatic-execution claim (never settle a claimed request).

## Success Criteria

- `~/bin/warrant log --last 5` on the host prints five escaped lines and no
  raw control characters, with no PIN asked.
- After `~/bin/warrant list`, `bf2aa6d0` is gone from `requests/`, the
  ledger holds a `refused ... expired` line for it, and a `warrant wait
  bf2aa6d0b6903a15de1888ff8bde4c9e` exits 126.
- A request left unapproved past the TTL unblocks its `warrant wait` with
  exit 126 the next time the human runs `list` or `approve`.
- Results older than a day with a settled ledger entry disappear on the next
  `list`; `test_warrant.py` stays green on the host.

## Risks

- **Settling a request the human is reviewing right now.** The flock in
  requirement 2 skips any request another approve holds.
- **Deleting the only copy of output a waiting agent still needs.** Results
  are pruned only after `result_ttl_sec`, which defaults to the request TTL;
  an agent that has not collected a result in a day re-runs the command.
- **`log` as a new terminal-injection surface.** Every field goes through
  `visible()`; a test feeds an escape sequence.
- **Pruning hides a forged result.** A forged result has no ledger entry, so
  requirement 3 keeps it for the human to see in `log --show`.

## Open Questions

1. `result_ttl_sec` default: one day (matches the request TTL) or shorter,
   such as one hour, to cut the window in which other agent sessions can
   read brokered output?
2. Should the leak of results to every agent session be closed for real
   (results written outside `/private/tmp`, for example a host-only
   directory the profile denies, with `wait` unable to read them and the
   agent getting only status and exit)? That costs the agent its captured
   output and is a trust-model change, so it would be its own PRD.
3. Settle `bf2aa6d0` by hand now (approve it and press Enter to reject),
   or leave it for the first `list` after this ships?

## Discovery Log (2026-10-18)

### Q1: Does anything delete spool files today?
**Answer** (from the system, not asked): yes, `com.apple.tmp_cleaner` at
00:00, files idle 3 days. Not a warrant feature and not ledgered, so it is a
backstop, not the design.

### Q2: Should the agent side purge its own results?
**Answer** (inferred, open to reversal): no. Any agent can delete anything in
the spool already, so a rule adds no safety, and delete-on-read breaks
re-attach after a context reset. The human side owns settling and pruning.

### Q3: Where does expiry get enforced?
**Answer** (inferred): on the human side, through the existing `refuse()`
path, because only that side knows the TTL and can write the ledger. The
agent side gets the verdict through the result file it already polls.
