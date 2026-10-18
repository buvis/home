---
catchup: skip
design: skip
---

# Gate coding-style limits in /work before the review phase

Source: `dev/local/discovery/inbox/autopilot-fast-track-learnings-2026-08-25.md` § 1 (PRD 00136 review cycle 1, 2026-08-24).

## Problem

Three of the fourteen findings in PRD 00136's first review cycle were countable coding-style violations that the build itself could have measured: a 57-line test function (`rules/coding-style.md` caps functions at 50), a test file that grew from 796 to 817 lines (cap 800), and a duplicated helper. Each was rule-mandated, so the review had no decision to make - it queued a rework task, and closing it cost a full review cycle plus a rework task (about 35 minutes of wall-clock and about 150K subagent tokens for a -25-line prose trim). R12/R13 failures recur across recent cycles (00133, 00134, 00136 minutes). The measuring script already exists: `review-work-completion/scripts/compute_mech_facts.py` reports per-function line counts from `ast`, and the review gate already discards findings that contradict it. `/work` never runs it.

PRD 00122's wave-2 cycle 1 (2026-08-25, `dev/local/reviews/00122-make-batch-reports-tell-the-truth-v1-review-1.md`) repeated the pattern and exposed two neighbours. Three of its eight findings were the same `wc -l` fact (`test_render.py` 763 -> 822 lines) filed by Alice, Bob and Carl, yet `consolidate_findings.py` printed three [1/4] rows instead of one [3/4]: the paths match (`files_match` is a suffix compare, so `/Users/bob/.claude/skills/run-autopilot/cli/test_render.py`, `cli/test_render.py:821` and `cli/test_render.py` all agree) but the descriptions score token Jaccard 0.139-0.200 against `MERGE_THRESHOLD` 0.25, while every pair shares the numeric tokens `800` and `822`. The orchestrator merged them by hand. And the `_raw_cell`/`_parse_counter` duplicate that became a [3/4] finding had been caught by Pat, the per-task reviewer, as a MEDIUM on task 1; `/work` step 5.7 says MEDIUM/LOW "proceed", so a 7-line fix Pat had already located went through a four-reviewer cycle and a full rework task (task 4). The same thing happened again inside that rework: Pat's MEDIUM on task 4 (a test module importing `_state`/`_batch_state` from a sibling test file) is now queued for cycle 2.

## Solution

Add a small script to `/work` that reads the phase's diff and the changed Python files, and reports only the violations the diff introduced: a function the diff touched that is over 50 lines, or a file the diff pushed over 800 lines. `/work` step 7 runs it before the full suite; a violation is a phase-red condition that gets one Ivan fix dispatch (the existing step-7 regression-fix shape) and a re-run, and the outcome is stamped in the phase report so a skipped or failed gate never reads as clean.

Two small neighbours ride along, both from the 00122 evidence: `consolidate_findings.match` gains a numeric-signature path (same file plus two shared numbers is the same countable defect), and `/work` step 5.7 gives a Pat MEDIUM that sits inside the task's own files one Ivan retry instead of shipping it to the PRD-level review.

## Requirements

### Must have
- `skills/work/scripts/check_style_limits.py --diff <unified-diff-file> <py-file>...` exits 1 and prints one line per violation the diff introduced, exits 0 with no output otherwise. Function violations are reported as `FUNCTION | <path>:<line> | <qualified name> | <N> lines` for functions over 50 lines whose line span intersects a new-side hunk range of the diff; file violations as `FILE | <path> | <N> lines` for files over 800 lines whose pre-image (new length minus insertions plus deletions from the diff's per-file counts) was 800 or fewer. Untouched over-limit functions and files already over 800 before the diff are NOT reported (they are pre-existing debt for the review, not this phase's regression).
- The function walk reuses `review-work-completion/scripts/compute_mech_facts.py` (imported by path, declared in `/work`'s `## Dependencies` section), never a second `ast` walker.
- `skills/work/SKILL.md` step 7 gains the gate: build the phase diff (`git diff <base>..HEAD --output=dev/local/tmp/phase-diff.txt`, where `<base>` is `state.work_start_sha` — see the recorded deviation below — spelled with the repo's own git flags where the repo is a bare-repo home), run the script over the changed `.py` files, and on exit 1 dispatch Ivan once with the violation lines as `FAILING_TESTS` and `RETRY_INSTRUCTION` "Fix only the listed style-limit violations; do not touch other code", re-commit, re-run the gate. Second failure: proceed and record it. The phase report carries one line `style_gate: clean | fixed:<sha> | failed:<violations>`.

  **Recorded deviation (2026-08-26, review cycle 1).** This bullet originally
  specified the base as "parent of the phase's first test commit". It was
  changed to `state.work_start_sha` on evidence, and the original wording is
  quoted here so the change is visible rather than retconned.

  The literal base cannot be computed when step 7 needs it. It is held
  in-session only and never persisted, so it is lost across a task-boundary
  handoff; and it does not exist at all when the first task of a phase writes no
  tests. `state.work_start_sha` is persisted in `state.json` and captured once
  per PRD before the first `/work` pass: on a first pass it IS exactly that
  parent, and on a rework pass it widens the diff to the whole PRD, which is the
  review's scope anyway.

  Two independent findings drove this. Pat raised it as a HIGH on task 4 during
  the build, where it was confirmed and the base was changed. Blake then reached
  the same conclusion in review cycle 1 from the PRD alone, without seeing the
  diff — so the spec and the implementation genuinely disagreed in the text, not
  merely in one reader's interpretation. His finding was that the deviation was
  "deliberate and documented, but unpinned by any test". The resolution taken was
  to ratify the deviation and pin it: `test_dispatch_prose.py` now asserts step 7
  names `work_start_sha`, so reverting the skill to this bullet's original
  wording turns that test red instead of silently reintroducing the handoff bug.
- Tests in `skills/work/scripts/test_check_style_limits.py`: a touched function over 50 lines is reported; an untouched function over 50 lines in the same file is not; a file that crosses 800 with the diff is reported; a file already over 800 before the diff is not; a clean diff exits 0 with empty output; a diff whose hunks are all deletions never reports a FUNCTION line.
- Non-Python changed files are skipped silently (same rule as `compute_mech_facts.py`).
- `skills/review-work-completion/scripts/consolidate_findings.py`: `match(a, b)` returns True when `files_match(a.file, b.file)` AND EITHER the token Jaccard is at least `MERGE_THRESHOLD` (unchanged) OR the two descriptions share at least two distinct all-digit tokens (`numeric_tokens(desc) -> frozenset[str]`, the `_WORD_RE` tokens matching `^\d+$`). `MERGE_THRESHOLD` and `STOPWORDS` are untouched. Tests in `scripts/test_consolidate_findings.py`: the three real 00122 cycle-1 lines (Alice, Bob, Carl, quoted verbatim from the review file's `## Consolidated Findings` table) consolidate into ONE row reading `[3/4]` with finders `ALICE, BOB, CARL`; two same-file findings sharing one number and scoring under the threshold stay separate; two different-file findings sharing two numbers stay separate; every existing fixture test still passes.
- `skills/work/SKILL.md` step 5.7, the "MEDIUM/LOW only, or `NO FINDINGS`" row splits in two. A MEDIUM whose `file:line` is inside this task's `FILES_TOUCHED` (as reported by Ivan's footer) gets ONE retry: verify it against the code, re-render `ivan.md` with the confirmed finding lines as `FAILING_TESTS` and the existing `RETRY_INSTRUCTION` "Apply ONLY the specific fixes listed below...", re-commit, re-verify (step 5.5), re-run Pat once; whatever that second Pat run returns, proceed to step 6 (no third dispatch). A MEDIUM outside the task's files, and every LOW, keep the current "note and proceed" behaviour. The attempt record's `review` string records the retry as `medium-retry:<fixed|unfixed>`. `skills/work/scripts/test_dispatch_prose.py` gains one assertion that step 5.7 names `FILES_TOUCHED` and the `medium-retry:` stamp.

### Nice to have
- `--limits function=50,file=800` override, defaulting to the coding-style values, so a repo with different limits can reuse the gate.

## Implementation

### Module: check_style_limits
- **Location**: `skills/work/scripts/check_style_limits.py`
- **Responsibility**: parse the unified diff's `@@ -a,b +c,d @@` headers per file, compute touched new-side ranges and per-file insertion/deletion counts, intersect with `compute_mech_facts`' function spans, and emit the violation lines.
- **Exports**: `touched_ranges(diff_text) -> dict[path, list[tuple[int, int]]]`, `violations(diff_text, paths, function_limit=50, file_limit=800) -> list[str]`, `main(argv) -> int`

### Module: work-skill-step-7
- **Location**: `skills/work/SKILL.md` (step 7 "Final verification") and `skills/work/SKILL.md` § Dependencies
- **Responsibility**: run the gate before the full suite, drive the one-shot Ivan fix, stamp `style_gate` in the phase report.
- **Exports**: none (prose)

### Module: consolidate-numeric-match
- **Location**: `skills/review-work-completion/scripts/consolidate_findings.py`, `skills/review-work-completion/scripts/test_consolidate_findings.py`
- **Responsibility**: the numeric-signature secondary match in `match()` and its fixture tests.
- **Exports**: `numeric_tokens(desc) -> frozenset[str]`; `match` signature unchanged

### Module: work-skill-step-5-7
- **Location**: `skills/work/SKILL.md` (step 5.7), `skills/work/scripts/test_dispatch_prose.py`
- **Responsibility**: the in-task MEDIUM retry rule and its prose pin.
- **Exports**: none (prose) + one test assertion

### Dependencies
- check_style_limits: depends on `review-work-completion/scripts/compute_mech_facts.py` (existing; function spans)
- work-skill-step-7: depends on [check_style_limits]
- consolidate-numeric-match: No dependencies (foundation)
- work-skill-step-5-7: No dependencies (foundation)

## Tasks

### Phase 0: Foundation
- [ ] Write `check_style_limits.py` with `touched_ranges`, `violations`, `main` and its six test cases - `uv run --with pytest pytest skills/work/scripts/test_check_style_limits.py -q` green; `python3 skills/work/scripts/check_style_limits.py --diff <fixture diff> <fixture .py>` prints the documented line shapes.

- [ ] Add the numeric-signature match to `consolidate_findings.match` with `numeric_tokens` and the four test cases - `uv run --with pytest pytest skills/review-work-completion/scripts/test_consolidate_findings.py -q` green; the 00122 three-line fixture renders one `[3/4]` row.
- [ ] Split step 5.7's MEDIUM/LOW row into the in-task MEDIUM retry and the note-and-proceed remainder, with the `medium-retry:` stamp and the prose pin - `rg -n "medium-retry:" skills/work/SKILL.md` hits step 5.7; `uv run --with pytest pytest skills/work/scripts/test_dispatch_prose.py -q` green.

### Phase 1: Core
- [ ] Wire the gate into `/work` step 7 and declare the cross-skill dependency (depends on: Phase 0) - `rg -n "check_style_limits" skills/work/SKILL.md` hits step 7 and the `## Dependencies` section; `rg -n "style_gate:" skills/work/SKILL.md` hits the phase-report line; `skills/work/scripts/test_dispatch_prose.py` (the existing prose-contract suite) gains one assertion that step 7 names the script and the three `style_gate` values.

## Success Criteria

- Replaying PRD 00136's cycle-1 diff (`c4b8e3c1..aa4ac650`) through the script reports exactly the two violations the reviewers found (the 57-line dispatcher test; `test_handler_run_parity.py` crossing 800) and nothing else - pinned as a fixture-based test using the committed diff text, not the live repo.
- A `/work` phase whose diff introduces no over-limit function or file records `style_gate: clean`, and the next review cycle has zero R12/R13 failures attributable to that phase.
- Feeding the four 00122 cycle-1 reviewer output files (`/tmp` staging, reproduced in the fixture) through `consolidate_findings.py` yields an 800-line row of `[3/4]`, matching the orchestrator's hand merge note in that review file.
- In the next three PRDs, no finding that Pat raised as a MEDIUM inside the task's own files reappears as a PRD-level review finding.
