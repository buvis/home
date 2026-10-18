# The autopilot's writers and CLIs report success while destroying or misstating things

Source: agoge product-QA run, `dev/local/audit-results/agoge-2026-08-17.md`, findings 17, 22, 24
and 26 (MEDIUM) and 36, 39 and 40 (LOW), each accepted in the 2026-08-17 walkthrough. Found by
heidi, judy and wendy.

## Overview

### Problem Statement

Seven defects across the autopilot's write and command surfaces. None is dramatic alone; together
they are the reason the state file and its tooling cannot be taken at face value.

1. **`statectl` destroys a newer schema stamp.** Two writers exist. The `autopilot` CLI correctly
   refuses a future-schema state file (`v999 > v1, refusing`, rc 6, file untouched). `statectl.py`
   exits 0 and clobbers 999 back to 1, because `state.transaction` line 139 stamps
   `SCHEMA_VERSION` unconditionally and `statectl.main` runs no version preflight — and
   `statectl` is the writer the docs and ~100 call sites use.
2. **A deliberate `rework_cap` change is reverted silently.** Phase 0's frontmatter re-parse
   merges `{**current, **fields}` where `frontmatter.defaults()` fills every key the PRD omits, so
   a mid-batch cap of 5 becomes 2 with rc 0 and nothing on stderr. Memory
   `reference_prd_frontmatter_overrides_state.md` records that frontmatter wins; what is new is
   that the reversion is invisible.
3. **`autopilot defer` is undocumented.** The verb appends to the batch deferred log with
   locking, `op_id` dedup, path validation and corruption detection. Every mention of it in the
   tree is in deleted history, while `phase-done.md:26` tells the model to hand-write that file
   with the Write tool — and `phase-done.md:87` calls it the "single source of truth" for
   batch-end review.
4. **`statectl.py --help` and `fablectl.py --help` exit 1 with zero bytes on stdout**, sending
   usage to stderr and never mentioning `-h/--help`, while the sibling `cli/__main__.py --help`
   exits 0 correctly.
5. **`render report` appends the same PRD section twice** on a re-run; the sibling `render audit`
   rewrites in place.
6. **`statectl.py`'s docstring claims the CLI is "unchanged" and lists nine of ten forms** —
   `append-attempt` is missing, so a reader who cannot find the verb hand-edits state.json, which
   is what `statectl` exists to prevent.
7. **`autopilot init` on a missing directory** fails with a random temp filename that never
   existed, under exit code 2, whose documented meaning is the *success* precondition for `init`.

### Target Users

Every autopilot session, and the operator reading a batch report or reaching for a verb.

### Success Metrics

- A future-schema state file is refused by **every** writer, `statectl` included, with the same
  exit code.
- A frontmatter re-parse that overwrites a state value says so on stderr, naming the key and both
  values.
- `rg "autopilot defer"` finds it in live documentation, and every registered subcommand appears
  in at least one live doc.
- `statectl.py --help | less` prints usage and exits 0.
- Running `render report` twice leaves one section per PRD.
- The `statectl.py` docstring lists exactly the verbs the CLI supports.
- `autopilot init` on a missing parent names the directory and the fix.

## Functional Decomposition

Accepted options, per finding:

- **17:** move the future-schema check into `state.transaction`, so every writer inherits it.
  Putting the rule where the write happens is the only version that cannot drift again.
- **22:** print one stderr line per overwritten key
  (`autopilot: PRD frontmatter reset rework_cap 5 -> 2`), keeping the deliberate
  frontmatter-wins rule and removing only the silence.
- **26:** replace the hand-append instruction with the verb in all five places, **and** add a
  doc-contract test asserting every registered subcommand appears in at least one live doc.
- **24:** intercept `-h/--help` before the arg check in both shims; usage to stdout, exit 0.
- **36:** drop an existing `## <prd>` section before appending, mirroring `render audit`.
- **39:** add the missing `append-attempt` line plus a test asserting every line of
  `cli.statectl.USAGE` appears in the shim's `__doc__`.
- **40:** detect a missing parent before the atomic write and emit
  `init failed: {dir} does not exist (Phase 0 creates the lifecycle dirs)` under its own exit
  code.

## Structural Decomposition

- `skills/run-autopilot/cli/state.py` — `transaction`, the version preflight (finding 17)
- `skills/run-autopilot/cli/__main__.py` — `_run_frontmatter` (22), `render report` (36), `init`
  (40)
- `skills/run-autopilot/cli/frontmatter.py` — `defaults()` (22)
- `skills/run-autopilot/cli/render_report.py` — section replacement (36)
- `skills/run-autopilot/scripts/statectl.py` — `--help` (24), docstring (39)
- `skills/run-autopilot/scripts/fablectl.py` — `--help` (24)
- `skills/run-autopilot/references/phase-done.md:26`, `phase-review.md:148` and `:194`,
  `phase-build.md:184`, `decision-framework.md:10` — the `defer` instruction (26)

## Implementation Phases

### Phase 1: the writers (findings 17, 22)

1. Version preflight inside `state.transaction`; `statectl` inherits it.
2. Per-key stderr line on frontmatter overwrite.

### Phase 2: the documentation contract (finding 26)

3. Five doc edits pointing at `autopilot defer`.
4. The doc-contract test over registered subcommands.

### Phase 3: the papercuts (findings 24, 36, 39, 40)

5. `--help` in both shims; idempotent `render report`; docstring line plus parity test; `init`
   missing-parent message and its exit code.

*Acceptance:* each reproduction below inverts, and the `render report` fixture — the archived
`202608162223` state — renders one section per PRD on a second run.

## Test Strategy

Verbatim evidence:

```
autopilot: future-schema state.json: v999 > v1, refusing      <- correct writer
frontmatter rc=6   { "schema_version": 999, "phase": "build", "cycle": 3 }   <- untouched
statectl rc=0      { "schema_version": 1,   "phase": "build", "cycle": 4 }   <- 999 clobbered
```

```
$ statectl.py .../state.json get rework_cap          -> 5
$ autopilot frontmatter --state ... --prd ...        -> {"rework_cap": 2}  rc=0  (stderr empty)
$ statectl.py .../state.json get rework_cap          -> 2
```

```
$ rg "autopilot defer" ~/.claude ~/.config/bash  -> 13 hits, ALL under file-history/ or tasks/
   (control: "autopilot select" -> 32 hits including live SKILL.md and references)
```

```
$ python3 skills/run-autopilot/scripts/statectl.py --help   -> RC=1  stdout_bytes=0
$ python3 skills/run-autopilot/cli/__main__.py --help       -> RC=0  options: -h, --help
```

```
$ ... render report --state ... --now 2026-08-17T01:00:00Z
$ ... render report --state ... --now 2026-08-17T01:05:00Z   -> rc 0
$ rg -c "## 00901-walk-the-journey.md" .../reports/20260817-walter-report.md   -> 2
```

```
$ ... init --state /tmp/wendy/sel/dev/local/autopilot/state.json --prd 00005-earlier.md
autopilot: init failed: [Errno 2] No such file or directory: '.../tmpvqzzhvrw.tmp'
rc=2      (after mkdir -p the same command succeeds; rc 7 on re-run, as documented)
```

## Risks

- **Moving the version check into `state.transaction` changes behaviour for every caller at
  once**, in the module the whole autopilot depends on — a mistake there is a broad outage.
- **The stderr line lands in a log in the unattended loop**, so the person most affected by a cap
  reversion is still the least likely to read it. Accepted knowingly; the alternative reversed a
  deliberate design rule.
- **A doc-contract test binds prose to code**, and that is exactly the kind of test that gets
  disabled the first time a verb ships before its docs.
- **Markdown section parsing for `render report` is fiddly** and can introduce its own bugs, for a
  defect whose worst outcome is a duplicated heading.
- **A new `init` exit code ripples through the documented table and any caller switching on rc 2.**
- **The docstring parity test is a string comparison**, brittle to an innocent reflow of `USAGE`.
