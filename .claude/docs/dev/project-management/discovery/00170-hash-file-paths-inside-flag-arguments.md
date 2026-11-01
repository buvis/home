# Discovery: Hash File Paths Inside Flag Arguments

## Classification

Depth: standard | Date: 2026-10-18 | Status: specified as PRD 00176
(backlog, 2026-10-19); live deployment remains separate
Seeded from session 523838c3 follow-ups; user instruction 2026-10-18: "all of
them must be recorded as discovery documents that I will go through".
Written from a sandboxed session from `~/bin/warrant` at buvis HEAD `609a769c`
(PRD 00163's profile-derived roots included), `~/bin/tests/test_warrant.py`
and the spool. `~/.config/warrant` was not read.

## Premise check

**Confirmed, and narrower than "flags".** `file_args()` (`warrant:357-367`)
walks `argv[1:]` and inspects an entry only when `cwd / arg` is an existing
regular file (`warrant:361-362`). The source says so itself:
`# ponytail: only whole arguments that name a file are inspected; --flag=path
forms show up raw` (`warrant:358`), and PRD 00159 lists it as an accepted
residual (`prds/done/00159-build-warrant-approval-broker-v1.md:273`).

What happens per shape today:

| Argument shape | Inspected? | Why |
|---|---|---|
| `PATH` (absolute) | yes | `cwd / "/abs"` is `/abs` in pathlib |
| `PATH` (relative) | yes | joined to the resolved cwd (`warrant:380`) |
| `--flag PATH` (two entries) | yes | `PATH` is its own entry |
| `--flag=PATH` | no | the whole string is not a file |
| `-fPATH`, `-CPATH` | no | same |
| `KEY=PATH` (`dd if=`, `make VAR=`) | no | same |
| `:(top)PATH` (git pathspec magic) | no | the literal string is not a file |
| a directory, in any form | no | `is_file()` only; dirs are never pinned |
| a path inside `sh -c "..."` | no | one string, see below |

For an inspected file, review resolves it, marks it agent-writable via
`agent_writable()` (`warrant:235-237`), hashes it, and keeps the first 20
lines (`HEAD_LINES`, `warrant:75`) only when it is agent-writable, UTF-8 and at
most 64 KiB (`HEAD_MAX_BYTES`, `warrant:76`; `inspect_file()`,
`warrant:342-354`). `show()` prints one `file :` line per entry plus the head
(`warrant:405-410`). `launch()` re-resolves and re-hashes every reviewed entry
and refuses any whole argument that became a file after review
(`warrant:441-445`, the "appeared" check). An uninspected flag value gets none
of this: no hash, no head, no re-check, no appeared check.

Evidence from this period (spool results carry no argv, so the shapes come
from the requests session 523838c3 itself made):

- `/bin/cp SRC DST`: SRC pinned with head; DST pinned when it already existed
  (not agent-writable, so hash only). Fully covered.
- `/bin/bash install_relay.sh relay.patch testfix.patch`: all three pinned.
  The heads showed 20 lines each, so most of `relay.patch` (about 300 lines)
  was hashed but never displayed. Files the script read indirectly were
  unpinned.
- `/bin/bash validate_relay.sh`: script pinned; `relay_probe.py` and the
  staged tree it read were not.
- `/bin/sh -c "cd /Users/bob && git ... commit -- ':(top).claude/docs/.../00160-....md' && git push"`
  (`631aeeba`): nothing pinned. The committed file lives under agent-writable
  `~/.claude`, so the agent could have changed it between review and launch.
- `git --git-dir=/Users/bob/.buvis --work-tree=/Users/bob apply PATCH` (used
  for `14f93f50`): PATCH pinned; the two flag values are directories and would
  stay unpinned even if split.

No result in `/private/tmp/warrant-501/results/` was ever refused for
"changed after review"; the four refusals on record are executable and env
checks, plus one expiry.

## Problem

An agent can hand the human a command whose real input sits behind
`--file=`, `-f`, `if=` or a git pathspec. The review shows the string but not
the content, and nothing stops the agent from editing that file after the
PIN. The whole-argument path closes this window (re-hash at spawn); the glued
forms leave it open. The gap is small (it needs the agent to choose a glued
form) but it is a silent one: the review gives no hint that a path went
unchecked.

## Requirements (proposed)

### Must have

1. **One candidate set, used by review and launch.** For each `argv[i]`,
   `i >= 1`, the candidates are: the whole entry; for `--name=value`, the text
   after the first `=`; for dashless `KEY=value`, the text after the first
   `=`; for a single-dash entry longer than two characters,
   the text after the first two characters (`-fPATH`). A candidate is a file
   argument when `cwd / candidate` is an existing regular file, exactly the
   current predicate. No per-tool flag grammar.
2. **Same treatment as whole arguments.** Resolve, mark agent-writable, hash,
   keep the head under the existing limits. `Op.files` records which form
   matched, so `launch()` re-derives the same path.
3. **Launch re-checks every candidate.** A reviewed candidate that changed is
   refused; a candidate that did not exist at review and exists at launch is
   refused as appeared, mirroring `warrant:444-445`.
4. **show() names the form.** `file : [3 --file=] /abs/path sha256 ...` and
   `file : [2 -f] /abs/path ...`, so the human sees which flag carried it.
5. **Tests** in `~/bin/tests/test_warrant.py`, using the existing
   `self.agentw` fixture and `submit()`/`approve_one()` helpers
   (`test_warrant.py:283-373` for the whole-argument versions):
   - `--file={note}` and `-f{note}` changed by the PIN callback refuse with
     "changed after review";
   - `--rcfile={late}` created by the PIN callback refuses as appeared;
   - a small agent-writable `--patch={diff}` shows its head;
   - `--message=hello` and `-n5` produce no `file :` line.

6. A note line when an argument names an agent-writable **directory**
  (`-C dir`, `--git-dir=dir`, `--work-tree=dir`), the same warning `show()`
  already gives for an agent-writable cwd (`warrant:411-412`): git reads
  config and hooks from such a directory.

### Out of scope

- **`sh -c "..."` strings and scripts that read other files.** Parsing shell
  or following a script's reads is undecidable in general. The line: warrant
  pins what the argv names directly; the human reads the `argv :` line and
  the script head and decides whether the indirect inputs are trustworthy.
  Agents should prefer argv forms over `sh -c` when a file matters; that is
  guidance, not a gate.
- Git pathspec magic (`:(top)PATH`). Resolving it needs git's own selection
  semantics, which PRD 00165 builds for its Git seeds. Reuse that resolver
  later rather than writing a second one here.
- Showing whole patches. The 20-line head is a separate tradeoff.

## Constraints

- Stdlib Python, one file, deployed through warrant like every `~/bin`
  change (draft in the scratchpad, the patch pinned as a whole argument).
- `Op` is built once and never re-read (`warrant:120`); the matched form must
  be stored on it, not recomputed from a changed argv.
- Commands run under warrant have no `TMPDIR`; fixtures must not rely on it
  (see the `feb24522` test fix).

## Codebase Context

- **Relevant code**: `file_args()` `warrant:357-367`, `inspect_file()`
  `342-354`, `Op.files` `128`, the call in `review()` `392`, `show()`
  `405-410`, `launch()` re-check `441-445`.
- **Conventions**: tests name the rule they enforce and drive approval with a
  PIN callback that tampers between review and launch.
- **Integration points**: `file_args()` gains the candidate split; `launch()`
  uses the same helper so review and launch cannot drift.
- **Overlap**: PRD 00166 (backlog) replaces `sha256_file` in `inspect_file()`
  and the `launch()` re-check with `fingerprint()`, and removes `argv[1]` of a
  sudo request from `file_args()`. Same functions, so land one first and
  rebase the other; the logic does not conflict. PRD 00165 (backlog) adds a
  separate automatic path and leaves `review()` for human approvals unchanged;
  its pathspec resolver is the natural home for the `:(top)` case.

## Success Criteria

- A fixture executable that actually reads `--file=NOTE` succeeds with the
  reviewed contents when NOTE is unchanged; mutating NOTE in the PIN callback
  instead refuses with "changed after review". The fixture controls cwd so
  `--message=hello` and `-n5` have no accidental matching files.
- The review of `foo -fPROFILE` prints a `file : [1 -f]` line with the hash.
- No change for argv without glued paths: existing tests stay green on the
  host.

## Risks

- **False positives.** A glued value that happens to name a file (`-n5` with
  a file `5` in cwd) is pinned and shown. Cost: one extra line and a refusal if
  that file changes. Acceptable; it fails toward more review.
- **Display noise.** Commands with many flag files get long reviews. No
  mitigation planned; it is the content the human should see.
- **False sense of coverage.** Pinning glued forms can make `sh -c` and
  script reads look covered. Mitigation: the out-of-scope line above, stated
  in the PRD.

## Elicitation decisions (2026-10-18)

The existing proposed defaults are adopted as routine planning decisions under
standing authorization: include dashless `KEY=value`, include directory
notes, and land after PRD 00166. No additional user answers were needed.
Directory notes report writable paths; they do not claim to hash a tree.
No scope question remains; deployment and verification occur downstream.

## Discovery Log (2026-10-18)

### Refresh: are the three remaining defaults material unresolved choices?
**Answer** (agent decision under standing authorization): no. Include the
existing candidate and warning proposals; follow the prerequisite that changes
the same fingerprint call sites. The current code confirms the integration
points. This records inferred decisions, not user replies.

### Q1: Does warrant already see `--flag PATH` as two entries?
**Answer** (from code, not asked): yes. Only glued forms are missed; the
separate-value form is already pinned because the path is its own argv entry.

### Q2: Why not a per-tool flag grammar (git, cp, dd)?
**Answer** (inferred): the predicate "names an existing file" already decides
whole arguments; reusing it for glued values covers every tool with about ten
lines and no table to maintain. A grammar would be precise and endless.

### Q3: Where is the line for indirect inputs?
**Answer** (inferred, open to reversal): at argv. Warrant pins what the
command line names; anything a shell string or script opens on its own is
the human's call from the displayed text.

## Discovery review (2026-10-18)

All five standard-depth lenses ran. F12 (Integrity, Non-blocking), option 1:
replace the unsupported `cat --file` example with a consuming fixture and
both unchanged/mutated checks. The generic candidate heuristic is a deliberate
tradeoff, not a tool-grammar guarantee; its false positives remain documented.
No broker code or request was changed. Open Questions 1–3 remain visible for
PRD creation; the defaults are proposals, not host changes.

## PRD coverage check (2026-10-18)

PRD created: yes, [00176](/Users/bob/.claude/docs/dev/project-management/prds/backlog/00176-inspect-warrant-glued-file-arguments-v1.md) (backlog), saved 2026-10-19.
The earlier no-match audit was superseded by the requested PRD creation.

### Elicitation refresh

Routine planning defaults adopted under standing authorization: include dashless KEY=value candidates, include directory warnings, and sequence after PRD 00166. Live file_args still inspects whole arguments only; review and launch must share candidate extraction. Existing inferred answers cover the remaining elicitation questions. Requirements are ready for the next discovery review; no PRD or broker change was created.

These are code-derived findings and planning defaults, not new user answers
or a new discovery-review pass. Existing Discovery Log answers remain valid.

## PRD creation (2026-10-19)

Specified as [00176](/Users/bob/.claude/docs/dev/project-management/prds/backlog/00176-inspect-warrant-glued-file-arguments-v1.md). The user requested creation of the missing PRDs.
The earlier elicitation and review entries remain historical evidence.
The PRD records final authoring defaults, dependency ordering and scope.
Implementation uses an isolated checkout and headless acceptance checks;
live deployment and host-only operational steps remain separate.
Template, guess-density and grounding gates passed before saving.
