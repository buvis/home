# Discovery: Snapshot Agent-Writable File Arguments

## Classification

Depth: standard | Date: 2026-10-18 | Status: not reviewed
Seeded from session 523838c3 follow-ups; user instruction 2026-10-18: 'all
of them must be recorded as discovery documents that I will go through'.
The handoff item was "opt-in `request --snapshot ARG`". Written from a
sandboxed session: `~/.config/warrant` was not read; everything below comes
from `~/bin/warrant`, the profile and PRD 00159.

## Premise check

**The residual is real, and the proposed fix does not close it as worded.**
PRD 00159 accepted "the window between the pre-launch re-hash and the
command opening an agent-writable file argument" (`prds/done/00159-...md:270`).
The code shows exactly where it is:

1. `review()` hashes each file argument once (`warrant:357-367`, via
   `inspect_file` at `342-354`, which keeps the head of the very bytes it
   hashed for files up to 64 KiB, `warrant:75-76`).
2. `show()` prints that hash and head (`warrant:405-410`); the human types
   the PIN.
3. `launch()` re-hashes every file argument and refuses on any change
   (`warrant:441-442`), then calls `execute()` (`warrant:452`).
4. `execute()` spawns the child (`warrant:432`). The child opens the path
   whenever it gets to it.

Between the re-hash in step 3 and the child's open in step 4 the agent can
swap the content. Two things widen that gap beyond a few milliseconds:

- **Interpreters read scripts lazily.** `bash script.sh` reads the file as it
  runs, so an agent can rewrite lines that bash has not reached yet, minutes
  after the re-hash. This is the common shape: in session 523838c3 every
  install went through `/bin/bash <scratchpad>/install_relay.sh`, and the
  scratchpad lives under `/private/tmp/`, which the profile grants for
  writes (`ai-agents.sb:124`).
- **Files the command reads indirectly are never hashed at all.**
  `validate_relay.sh` (requests `0ab414fb`, `22f071d9`) read
  `relay_probe.py`, `stage/bin/herdr-relay` and the staged profile by path
  from inside the script. Only the script itself was a file argument. Those
  inputs could change at any point, before or after the PIN. This is a
  larger hole than the re-hash window, and no per-argument snapshot fixes it.

**A request-time snapshot into the spool protects nothing.** The spool is
`/private/tmp/warrant-<uid>` (`warrant:63`), mode 0700 and owned by the user
(`warrant:171-176`), but the agent runs as the same uid and the profile grants
writes under `/private/tmp/` (`ai-agents.sb:124`). The docstring already says
so: "The spool sits inside the agent-writable paths, so a request is untrusted
data" (`warrant:30`). A copy the agent makes at request time is one more
agent-writable file, pinned by the same hash the original already has. The
same holds for `/private/var/folders/` and `_TMPDIR` (`ai-agents.sb:122-123`).

So the copy must be made **by the human side, at approve time, into a
directory no agent can write**, and the child must be pointed at the copy.

## Problem

What the human reviews is the bytes of each file argument at review time.
What runs is whatever those paths hold when the child reads them, which for a
shell script can be long after the last check. An agent that wants to run
something the human would reject submits a harmless script, waits for the
PIN, and rewrites the tail. The re-hash cannot see it. Separately, a script
argument that reads other agent-writable files gives the human no view of
those files at all.

## Requirements (proposed)

### Must have

1. **Approve-time copy, host-only location.** In `review()`, for each file
   argument chosen for snapshot (requirement 3), read the bytes once, hash
   those bytes, keep the head from those bytes (as `inspect_file` already does
   at `warrant:346-354`), and hold them in the `Op`. In `launch()`, after the
   existing checks and before `execute()`, write the held bytes to
   `SNAP_ROOT/<id>/<argv index>-<basename>`, mode 0600, directory 0700, with
   `O_EXCL`, and point the child's argv at the copy. The original file is
   never opened again. `SNAP_ROOT` is under `~/.config/warrant/` (not
   agent-writable and already denied for agent reads,
   `ai-agents.sb:90`); `preflight()` (`warrant:240-251`) refuses to broker if
   it ever becomes agent-writable.
2. **Copies are removed after the run**, in a `finally` around
   `execute()`, including on timeout. A crash leaves a directory named by the
   request id; the next approve removes stale ones.
3. **Which arguments are copied.** Default rule, host-side and automatic: the
   first argument after an interpreter (`argv[0]` resolves to `bash`, `sh`,
   `zsh`, `dash` or `python3*`) when it is an agent-writable file. That is the
   script, the case where lazy reads make the window minutes long. Every other
   agent-writable file argument keeps today's re-hash, because substituting it
   would break path semantics (requirement 4). The agent may additionally
   mark data inputs with `warrant request --snapshot N` (argv index, repeatable),
   for files read only for content, such as a patch passed to `git apply`.
   The flag can only narrow what the agent controls, so trusting it is safe;
   omitting it leaves today's behaviour.
4. **`show()` says what will run.** Each copied argument prints
   `snapshot -> <copy path>` beside its hash. Each non-copied agent-writable
   argument keeps the current note (`warrant:409-410`), reworded to say the
   window is still open for that argument.
5. **Indirect reads are named, not solved.** When a copied script is
   agent-writable and its text names other paths under agent-writable roots
   (a plain scan of the held bytes for absolute paths), `show()` lists them as
   `reads  : <path>   AGENT-WRITABLE, not pinned`. This is a hint for the
   human, not a boundary: a script can build paths at run time.
6. **Tests ship with each behaviour** in `~/bin/tests/test_warrant.py`:
   - an `execute` stub that rewrites the original script after `launch()`'s
     re-hash: the child prints the reviewed text, not the rewritten one;
   - a bash script that appends a line to its own original path while running:
     the appended line does not run;
   - `--snapshot 2` on a `git apply`-style fake: the child gets the copy path;
     an index that is not an agent-writable file argument is refused at review;
   - `cp SRC DST` with both agent-writable and no flag: neither is copied, the
     re-hash note shows;
   - the copy directory is gone after executed, timeout and refused outcomes;
   - preflight refuses when `SNAP_ROOT` lies under a write grant.

### Nice to have

- `--snapshot-dir DIR`: copy a whole agent-writable directory (size and file
  count capped) and run with cwd or the argument pointed at the copy. This is
  the only real fix for scripts with sibling inputs, such as
  `validate_relay.sh`. It needs a tree hash in `show()` and a cap on what the
  human can meaningfully review.

### Out of scope

- Paths embedded in `--flag=path` arguments (discovery 00170, written in
  parallel). A snapshot of those needs the same argument model; see Risks.
- Making non-script arguments automatic. See Discovery Log Q3.
- Seatbelt profile changes.

## Constraints

- Stdlib Python, one file, deployed through warrant as in PRD 00159 (the
  scratchpad draft plus a `cp` request, so the source is hashed).
- The copy is read by an unsandboxed child, so a location under
  `~/.config/warrant/` works for the child although agents cannot read it.
- Memory: requirement 1 holds the bytes in the `Op`. Cap snapshot size (16 MiB
  is a guess) and refuse a larger snapshot candidate instead of silently
  falling back to the re-hash.

## Codebase Context

- **Relevant code**: `~/bin/warrant` `inspect_file` 342-354 (already reads
  small files once and hashes the same bytes), `file_args` 357-367 (only
  whole arguments that are files; the `ponytail:` note at 358 names the
  `--flag=path` gap), `review` 370-393, `show` 396-412, `execute` 425-437
  (argv built at 430 from `op.argv`), `launch` 440-457 (re-hash at 441-449),
  `preflight` 240-251, `Op.files` tuple at 128.
- **Conventions**: tests load the script with `SourceFileLoader` and build a
  fake `Site` (`test_warrant.py` `WarrantCase`, `ProfileCase` at 527).
  Under warrant, `TMPDIR` is unset and `tempfile` lands in `/private/tmp`, which
  the profile grants; fixtures must keep a fake host-only root outside every
  fake grant (fixed for one test in buvis `feb24522`).
- **Integration points**: `Op` gains held bytes per copied index; `execute()`
  takes the rewritten argv; `request()` and `build_request()` (518-528)
  carry the optional `snapshot` index list.

## Success Criteria

- A brokered `bash /private/tmp/x.sh` whose original file is rewritten after
  the PIN runs the reviewed bytes; the ledger records the copy path.
- `show()` on a request like `install_relay.sh relay.patch` prints
  `snapshot -> ...` for the script and, with `--snapshot 2`, for the patch.
- `cp`, `git add` and `git apply` requests without the flag behave exactly as
  today.
- No copy remains under `SNAP_ROOT` after any outcome; the test suite stays
  green on the host with `TMPDIR` unset.

## Risks

- **Scripts that find siblings via `$0` or `__file__`.** A copied script's
  `$0` is the copy path, so `$(dirname "$0")/x` resolves into `SNAP_ROOT`
  and fails. Today's scratchpad scripts used absolute paths and would still
  work. Mitigation: the failure is loud (file not found), and `show()` prints
  the copy path; the agent can pass absolute paths or opt into
  `--snapshot-dir`.
- **Path-semantic arguments copied by mistake.** Copying `DST` in `cp SRC DST`
  writes into the copy; copying a `git add` path stages nothing. Only the
  interpreter's script is automatic; everything else needs the explicit index,
  so this needs the agent to ask for it.
- **Overlap with 00170, 00165, 00166.** 00170 changes what counts as a file
  argument; 00165 (auto-approve bookkeeping) relies on `git add`/`commit`
  path semantics, which must never be copied (true under requirement 3);
  00166 (root commands) stat-pins unreadable files, which cannot and need not
  be copied. All four edit `review()`, `show()` and `launch()`. Land them in
  sequence; whichever lands second rebases its tuple shape.
- **False comfort from requirement 5.** A path scan misses computed paths.
  The `show()` line says "not pinned" so it never reads as a guarantee.

## Open Questions

1. Automatic for interpreter scripts (recommended), or opt-in only as the
   handoff worded it? Automatic closes the common case without the agent
   having to remember a flag.
2. `SNAP_ROOT` under `~/.config/warrant/` (recommended: already protected and
   read-denied), or a separate host-only directory?
3. Build the `--snapshot-dir` nice-to-have now? It is the only fix for the
   `validate_relay.sh` shape (indirect inputs), which today is the bigger hole.
4. Size cap for a snapshot: 16 MiB is a guess.

## Discovery Log (2026-10-18)

### Q1: Does a request-time copy into the spool help?
**Answer** (from code and profile, not asked): no. The spool is agent-writable
(`warrant:30`, `warrant:63`, `ai-agents.sb:124`), so the copy is exactly as
trustworthy as the original, and the original is already hash-pinned until the
re-hash. Rejected.

### Q2: Where does the window actually sit?
**Answer** (from code): between `sha256_file` in `launch()` (`warrant:442`)
and the child's own open after `subprocess.run` (`warrant:432`). For a script
run by bash it extends to the whole run, because bash reads lazily. The head
the human sees is safe: `inspect_file` derives it from the hashed bytes.

### Q3: Copy every agent-writable file argument automatically?
**Answer** (inferred, open to reversal): no. PRD 00159 already rejected
substitution because it "would break path semantics such as `git add`"
(`00159-...md:270-272`). Alternatives:

- (a) **Copy every agent-writable file argument.** Rejected: breaks `cp` DST,
  `git add`, `mv`, anything that uses the path, not the bytes.
- (b) **Opt-in flag only.** Safe but leaves the common script case open
  unless the agent remembers.
- (c) **Automatic for an interpreter's script, opt-in for the rest.**
  Recommended: covers the case with the long window, and the flag covers
  content-only inputs such as patches.
- (d) **Pass content on stdin instead of a path** (`bash -s < copy`).
  Rejected for now: changes `$0` and argv for every script, and stdin is
  `DEVNULL` by design (`warrant:432`).
- (e) **Leave it as an accepted residual.** Possible; the human still sees
  the head. But the bash lazy-read case makes the residual much larger than
  PRD 00159 described.

### Q4: Is the flag a trust problem, since the agent writes it?
**Answer**: no. The flag can only ask the host to freeze more; it never
widens what runs. A missing flag gives today's behaviour, and the host
refuses an index that is not an agent-writable file argument.
