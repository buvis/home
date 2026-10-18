# Autopilot efficiency learnings from the hand-driven PRD 00136 run (2026-08-24/25)

> Processed 2026-08-26. § 1, § 9a-b -> claude-autopilot PRD 00140 (done); § 3, § 5, § 9c -> claude-autopilot PRD 00141 (backlog) and ~/.claude PRD 00146 (done); § 4 option c, § 6, § 8 engram -> claude-autopilot PRD 00148 (backlog); § 2 -> cost note on claude-autopilot PRD 00110 (hold) and `dev/local/reviews/00110-flip-evidence.md`. § 7 -> claude-autopilot PRD 00149 (`autopilot review-once` + the stale `/run-autopilot` launch prompt) and ~/.claude PRD 00150 (the buvis shell front-end still pointed at the removed `~/.claude/skills/run-autopilot`; found and fixed by hand 2026-08-26, done/). Not tracked: § 8 consolidation alias and gateguard subagent retries (low priority).

Source: PRD 00136 review cycle 1 (4 lenses + shadow) and the hand-driven rework (/work tasks 4-5), all in one interactive session. Every item below is backed by a number or an artifact from that run; none is a guess. Ordered by expected payoff.

## 1. Pre-review mechanical gate in /work step 7 (highest payoff, cheapest)

- Evidence: 3 of the 14 cycle-1 findings were countable coding-style violations (R12: a 57-line test function; R13: `test_handler_run_parity.py` 796 -> 817 lines; plus a duplicated `_boom` helper). They cost a full review cycle plus a rework task (~35 min wall-clock, ~150K subagent tokens) to fix a -25-line prose trim.
- The measuring script already exists: `review-work-completion/scripts/compute_mech_facts.py` (used by the review to pin line counts).
- Change: in `/work` step 7 (final verification), run `compute_mech_facts.py` over the phase's changed Python files plus `wc -l`; any NEW function over 50 lines or file crossing 800 lines is a phase-red condition that gets one Ivan fix dispatch before hand-off. Also worth a `git diff --numstat` check of the before/after file length so a crossing is attributed to the diff.
- Payoff: one review cycle per occurrence; R12/R13 fails have appeared in several recent cycles (00133, 00134 minutes).

## 2. Shadow consensus engine: evidence for PRD 00110 (hold)

- Evidence: the `review-fanout` shadow on 00136 cycle 1 ran 6 agents, 771K subagent tokens, 5.5 min, and returned `converged` with 0 blocking and 20 advisory items; its rubric was identical to legacy Alice (118K tokens). Of the 20 advisory items, 4 duplicated gating reviewers, 3 were genuinely new (auto-memory root false-deny, `expanduser` on extra roots, no durable home for the export) and 2 of those were adopted in the walkthrough; the rest were noise or restatements.
- Reading: the shadow is a ~6.5x token multiplier for one adopted LOW/MEDIUM finding per cycle. It does surface things the four lenses miss, but only as advisories.
- Options for 00110: keep `legacy` as default (this evidence); or arm the workflow only on cycle 1 of PRDs whose diff exceeds a size threshold (e.g. 500 lines), where five dimension lanes have room to disagree; never on incremental cycles.

## 3. Blind lens and the symlinked dev/local

- Evidence: Blake reported `dev/local/tmp/00136-smoke-autopilot/last-session.log` "does not exist on disk"; it did (31 KB). His own report says he searched `dev/local/tmp/` and `.trash/` - the same dot-directory / symlink blindness (`rg --files` does not descend into `~/.claude` or follow `dev/local`) that caused the 00136 incident itself. One refuted 🟡 cost a verification round.
- Change: `review-work-completion` step 4, Blake's run inputs, one line for projects with a symlinked or dot-directory layout: "dev/local is a symlink to <realpath>; `rg --files` will not see it - use `ls` on the realpath."
- His other 🟡 (kill switch / extra roots "not in the PRD") is settled by the design doc by construction; cycle 2's ledger dismiss absorbs it. No change needed.

## 4. Formatter reflow during subagent edits (loupe autofix)

- Evidence: during Tess's task-5 dispatch, `test_enforce_write_scope.py` acquired a whole-file reflow (trailing commas, line splits: 35/23 lines) that was not hers. Ivan's edits to the same file 20 minutes earlier were clean, so the trigger is unclear (loupe is enabled here and carries autofixers). The test commit had to be hunk-scoped by hand (`git apply --cached` with a hand-written patch) to keep the review diff clean; the reflow remains as work-tree noise, like the pre-existing `test_cartographer_echo.py` one.
- Change options: (a) `/work` step 5 diff-checks the implementor's `FILES_TOUCHED` against the edit regions the subagent reported and hunk-scopes automatically when the file diff is far larger than the report; (b) loupe's autofix is disabled when `CLAUDE_UNATTENDED=1` or inside subagent tool calls; (c) at minimum, `/work` step 5 records the reflow in the phase report (done by hand this time).
- Payoff: avoids review-diff noise (incremental cycle 2 would otherwise re-review 58 formatting hunks) and the risk of sweeping foreign formatting into task commits.

## 5. Tess briefs for hook tasks need the harness contract

- Evidence: the first draft of Tess's brief asked for a marker-first test driven through `_common.capture_main`; that helper installs its own `sys.stdin`, so the test would have passed against the OLD code too (non-discriminating). Caught only because the orchestrator read `_common.py` before dispatch and rewrote the brief to drive `main()` directly.
- Change: a reusable `PUBLIC_INTERFACES` stub for hooks tasks (`hooks/tests/_common_contract.md` or generated from `_common.py` docstrings) that `/work` step 2.7 always passes for any task under `hooks/`: `read_input` returns `{}` on malformed input, `capture_main` replaces stdin/stdout/stderr, `allow`/`block` raise SystemExit. Tess must not read the implementation, but the harness contract is not the implementation.

## 6. Micro-task lane for rework tasks

- Evidence: task 4 (prose trim, -25 net lines, test files only) took ~15 min wall-clock and ~100K subagent tokens (Ivan 80K, Pat ~20K) for a change the orchestrator could have made in two Edits; task 5's two code lines plus four doc lines took ~20 min. The per-task ceremony (three scratch files, render, watchdog, review render, sonnet runner) dominates below ~30 net lines.
- Change: in rework mode (`review_cycle` set), a task that is docs/prose-only OR whose expected diff is under the step-5.6 skip threshold (30 net lines / 2 files) may be implemented by the orchestrator directly, with Pat's review kept and Tess/Devon skipped; the attempt record stamps `implementor: "orchestrator"` so it is visible. Same fail-loud shape as the existing test-only/docs-only Tess skip.

## 7. Headless fresh-session review from a build session

- Evidence: the fresh-session review rule forced a human session hop between build and review; the hop itself is one `runner.spawn(...)` call (`routing.route("review", ...)` supplies model/effort/cap), which task 3's smoke driver already demonstrated. Hand-driven mode has no first-class way to do it.
- Change: `autopilot review-once` (or `spawn --phase review`) subcommand: one review-phase session, no loop, `_AUTOPILOT_LOOP` set for the child's lifetime, then exit; the operator keeps the walkthrough in their interactive session. Cheap: it is the body of `Loop.run`'s single iteration minus `_decide`.

## 8. Smaller items

- Auto-mode classifier friction: Ivan reported one Edit denied three times before byte-identical retries passed (aegis fact-forcing gate plus the classifier). Turns, not correctness; worth a look at gateguard's behavior on subagent Edits.
- `engram pack` in a bare-repo home fails every cycle ("must run inside a git worktree"); the skill already prescribes one attempt and no retry. Skip the attempt when `git rev-parse --show-toplevel` fails at the project root - saves seconds, removes a red line from every review file.
- Consolidation missed real 3/4 overlaps because the same defect was filed against different files (design doc vs the hook). Treating the PRD's own design-doc path as an alias of the code file the finding names would have merged them; low priority, the orchestrator records overlaps by hand today.
- The review's own full-suite run (54 s) duplicates the build's; harmless, keep (fail-loud Tests line).

## 9. Added from the PRD 00122 wave-2 run (2026-08-25, hybrid fast track)

Folded into 00140 (items a, b) and 00141 (item c) on the user's decision the same day; item d was already covered by the review skill.

- a. **Consolidation misses countable findings on wording, not paths.** Three reviewers filed the same 822-line `test_render.py` fact; `files_match` agreed on all three spellings, but description Jaccard was 0.139-0.200 against the 0.25 threshold (measured with the script's own `tokens`/`jaccard`), while every pair shared the numbers `800` and `822`. The review file's merge note blamed path spelling; that diagnosis was wrong. Fix: a same-file + two-shared-numbers secondary match (00140).
- b. **Pat MEDIUMs take the expensive lane.** Step 5.7's "MEDIUM/LOW → proceed" sent a 7-line duplicate Pat had already located (task 1) through a 4-reviewer cycle and a rework task (task 4); task 4's own Pat MEDIUM is now queued for cycle 2. Fix: one in-task Ivan retry for MEDIUMs inside the task's files (00140).
- c. **Test-only rework has no lane.** `agents/ivan.md` line 8 forbids test-file edits outright, so both test-only rework tasks (4 and 5) needed a hand-built implementor, recorded as a deviation each time (`dev/local/meta/assumptions.md` ## 4, ## 5). Fix: the allowlist decides, not a blanket ban (00141).
- d. **Bare-repo degradations are already handled**: `review-work-completion/SKILL.md:149` (gather-context carve-out) and `:173` (expect `engram pack` to fail, note and move on). The only new fact is that the run-autopilot `scripts/` suite needs `--with rich --with textual` (tracon tests import `rich`); recorded in project memory, not a PRD.
- Confirmation for § 1: 3 of the 8 cycle-1 findings were `wc -l` facts the build could have measured.

## Not a learning (already right)

- The per-task hunk-scoped `git add` discipline and the foreign-WIP rule worked: four foreign dirty files survived two tasks untouched.
- Pat's closure verdicts (`CLOSURE | resolved`) on rework tasks gave a cheap, specific check that each finding was actually closed - keep.
