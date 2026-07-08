---
name: review-work-completion
description: Use after all tasks are completed to validate implementation against PRD requirements via multi-agent consensus review. Triggers on "review work", "check completed work", "validate implementation", "are we done".
---

# Review Work Completion

## What This Does

Validates completed implementation work against PRD requirements using independent AI reviewers (tools may change in the future). Each reviewer analyzes the code changes and PRD criteria separately, then findings are consolidated by consensus - issues flagged by multiple reviewers get higher priority. Creates follow-up tasks for any gaps found.

**Why multiple reviewers:** Different models catch different issues. Consensus scoring surfaces real problems while filtering noise from single-model false positives.

> **Note for anyone reviewing/auditing this skill:** See `references/design-rationale.md` for settled design decisions
> before suggesting changes. This doesn't apply to skill users, as it doesn't add any useful information
> to perform the skill.

## Reviewers

Every review cycle runs all lenses (PRD 00015) — consensus, blind, and doubt
are prompt disciplines carried by the roster, not separate phases:

- **Alice** → Claude subagent (direct, not nested CLI); implementation-aware consensus lens
- **Blake** → Claude subagent, **blind lens**: PRD-only prompt — no diff, no file list, no review history, no design doc (see `references/blind-lens-prompt.md`)
- **Bob** → Codex, **doubt lens**: carries the doubt rubric (R1-R5) and the de-slop lens every cycle; when codex is unavailable, a Claude subagent runs the same prompt so the lens never silently drops
- **Carl** → Gemini (frontend & design specialist; skipped when the Gemini CLI is unavailable)
- **Diana** → Sonnet via `sonnet-run.sh` (background Bash: headless `claude -p` pinned to `model: sonnet`; skipped when the script is unavailable)
- **Eve** → Claude Fable 5 Task subagent, opt-in fifth lens: joins the batch only when the PRD frontmatter sets `doubt_reviewer: fable`, running the same doubt prompt as Bob (see `references/agent-invocation.md` "Eve (Fable 5)"); absent otherwise

## Workflow

### 1. Validate prerequisites

Check these exist:

1. `~/.claude/skills/use-codex/scripts/codex-run.sh` - executable
2. `dev/local/prds/wip/` contains at least one `.txt` or `.md` file

(Alice is a native Claude subagent - no CLI prerequisite.)

**Optional - Carl (Gemini):** check `~/.claude/skills/use-gemini/scripts/gemini-run.sh` is executable AND a backend CLI resolves - `copilot` (preferred; serves `gemini-3.1-pro-preview`) OR native `gemini` (`mise which`/`command -v` succeeds for either). If both pass, Carl is active. If neither CLI resolves, skip Carl and proceed with the three remaining reviewers - this is graceful degradation, not a failure. Note in the final review file which reviewers ran. (Carl on the copilot backend spends Copilot AI credits; a "monthly quota exceeded" error from the helper is a runtime skip, not a prerequisite failure.)

**Optional - Diana (Sonnet):** check `~/.claude/skills/use-sonnet/scripts/sonnet-run.sh` is executable. If it passes, Diana is active. If missing or non-executable, skip Diana and proceed with the remaining reviewers - graceful degradation, not a failure. Note in the final review file which reviewers ran. (`sonnet-run.sh` is a headless `claude -p` wrapper, so it needs only the harness's own `claude` binary; its absence is an install anomaly, not a reason to hard-abort the review.)

Create if missing: `dev/local/tmp/`, `dev/local/reviews/`

**Path convention:** All `dev/local/` paths in this skill are relative to the project root. When passing file paths to subagents or external scripts, always use absolute paths (e.g. `$PWD/dev/local/tmp/...`) so they resolve correctly regardless of the subagent's working directory.

**If CLI/script check fails, STOP and report:**

```text
Cannot proceed: {missing prerequisite}
```

### 2. Check task status

Use `TaskList`.

**If no tasks exist:** If `catchup` skill is available, invoke it to populate tasks from branch history, then return here. If `catchup` is unavailable, proceed without task context.

**If ANY task is `in_progress`:** STOP and report:

```text
Cannot review: {N} task(s) still in progress
- Task {id}: {subject}
```

**If ALL tasks are `pending`:** STOP and report:

```text
Cannot review: no completed tasks found. Complete tasks first.
```

### 3. Gather context

Read all PRDs from `dev/local/prds/wip/`. Extract success criteria, acceptance criteria, required features.

Load architecture docs: AGENTS.md, agent_docs/, and any `dev/local/` architecture notes. Reviewers benefit from seeing invariants and boundaries.

Build markdown of completed tasks with descriptions. **One row per task — never merge rows.** If a task was implemented in the same commit as another task (folded), it still gets its own row; note the shared commit SHA and the companion task IDs in the row's description so the cycle-N task→commit table stays unambiguous.

Write tasks markdown to `dev/local/tmp/review-tasks-{id}.md` and PRD summary to `dev/local/tmp/review-prd-{id}.md` using the **Write tool** (not bash).

**Design doc context (when present).** Check `state.design_doc` in `dev/local/autopilot/state.json`; if it is unset, fall back to the glob `dev/local/designs/<prd-stem>-design.md` (`<prd-stem>` = the wip PRD filename minus `.md`). When a design doc exists, append its full content to the PRD summary file (`dev/local/tmp/review-prd-{id}.md`) under a `## Design Doc` heading. This lets reviewers distinguish "implemented as designed" from drift. The PRD remains the requirements authority — the design doc is the implementation design (the HOW), not the spec. Blind review and doubt review stay PRD-only by design (a blind reviewer must test requirements without design bias) — do **not** add the design doc to those surfaces.

**Determine review scope (full vs incremental).** With `Glob`, list existing review files for this PRD: `dev/local/reviews/<prd-name>-review-*.md` (PRD filename without the `.md` extension).

- **No prior review file** → cycle 1, a **full review**. Run `gather-context.sh` without `--since`.
- **A prior review file exists** → this is a rework cycle, an **incremental review**. Read the highest-numbered prior file's `head_sha` frontmatter field.
  - `head_sha` present → pass `--since <head_sha>` to `gather-context.sh`. The diff then covers only the rework commits since that cycle, not the whole PRD branch — the prior cycle already reviewed the full diff. Also read that file's consolidated findings; step 4 hands them to the reviewers to verify.
  - `head_sha` absent (file predates this field) → fall back to a full review (omit `--since`).
  - Also read that same prior file's `codex_thread_id` frontmatter field (stamped in step 8 of the prior cycle). Present → step 5 adds `--resume-thread <codex_thread_id>` to Bob's launch so codex resumes his prior session instead of re-reviewing from zero. Absent (pre-change file, or Bob was skipped / thread-id capture failed last cycle) → Bob runs a fresh review, no resume flag.

Capture the current HEAD now — `git rev-parse HEAD` — and hold it; step 8 stamps it into this cycle's review file as `head_sha`.

Also capture the diff range for the coverage gate (used in step 6). For an **incremental review** the diff range is `<prior-cycle-head-sha>` (the same SHA passed to `gather-context.sh --since`). For a **full review**: when running under autopilot and `state.work_start_sha` is set in `dev/local/autopilot/state.json`, use `<work_start_sha>..HEAD` (the PRD's whole work range — this is the scope the doubt lens reviews); otherwise compute it via `git merge-base HEAD origin/HEAD` (fallback: `git merge-base HEAD master`, then `git merge-base HEAD develop`). Store this as `COVERAGE_DIFF_RANGE`.

Run `gather-context.sh` (from project root). Full review:

```bash
~/.claude/skills/review-work-completion/scripts/gather-context.sh dev/local/tmp/review-tasks-{id}.md dev/local/tmp/review-prd-{id}.md
```

Incremental review (rework cycle) — prepend `--since <prior-cycle-head-sha>`:

```bash
~/.claude/skills/review-work-completion/scripts/gather-context.sh --since <prior-cycle-head-sha> dev/local/tmp/review-tasks-{id}.md dev/local/tmp/review-prd-{id}.md
```

Both positional args are optional — omit if no tasks/PRD available. Outputs context file and diff file paths to `dev/local/tmp/`.

### 4. Prepare agent prompts

Create prompt files in `dev/local/tmp/`:

For each active agent, use the **Write tool** (not bash heredocs) to create `dev/local/tmp/{agent}-prompt-{unique-id}.md` (use timestamp or UUID). **Use absolute paths** (e.g. `/full/path/to/project/dev/local/tmp/...`) when writing and when referencing these files in agent prompts - relative `dev/local/` paths get misresolved as `~/dev/local/` by subagents. See `references/agent-prompts.md` for prompt template structure.

**Create each prompt independently.** Do NOT create one prompt and copy/sed it into another - this triggers bash permission warnings (quote characters in comments desync quote tracking). Diana and Alice share the same template; Bob gets the sandbox constraints appendix PLUS the doubt-lens appendix (rubric R1-R5 + de-slop, per `references/agent-prompts.md` "Bob"); Blake's prompt is assembled from `references/blind-lens-prompt.md` + the PRD content ONLY (no context file, no diff file, no incremental-review addendum — blind every cycle); Eve (when active) reuses Bob's doubt-lens content per `references/agent-invocation.md`. Build each from its template directly.

> **Why Write tool:** Prompt templates contain patterns like `{path or "N/A"}` that trigger bash permission checks ("brace with quote character - expansion obfuscation"). The Write tool bypasses this entirely since it doesn't go through the shell.

With 1M context, agent prompts can include more background — full PRD, architecture summary, relevant module interfaces — rather than compressed summaries. Richer context produces better reviews.

**For an incremental review** (step 3 found a prior cycle): add to each agent prompt the prior cycle's consolidated findings, plus this instruction:

> This is an **incremental review** of the rework done since the previous review cycle — the diff is scoped to changes since then. Two jobs: (1) for each prior finding listed below, verify it is now resolved in the code; (2) review the scoped diff for any regression the rework introduced. You need not re-review unchanged code; the previous cycle already reviewed the full implementation.

### 5. Run agent review

**Launch ALL active reviewers in a SINGLE message so they run concurrently.** Alice, Blake, and Eve (when active) are Task subagent calls (native Claude tools). Bob, Carl, and Diana are parallel **background Bash** commands (`run_in_background: true`) - never wrap a CLI reviewer (codex/gemini/sonnet) in a subagent, it hangs and strands the whole cycle (see `references/agent-invocation.md`). Put the Task calls and the background Bash calls in the one message.

**Do not Write or Edit ANY reviewer output (Alice's and Blake's included) until ALL reviewers have reported.** The CLIs self-write via `-o`; subagent-returned text is saved only in step 6, after every reviewer has completed - even if a subagent returns first.

**Bob fallback (the doubt lens never drops).** If `codex-run.sh` exits non-zero with exit 3 (codex unavailable) or 4 (codex ran but failed, e.g. quota), dispatch a Claude Task subagent with Bob's exact assembled prompt (doubt lens + rubric included) and use its output as Bob's. Only if the fallback also fails does Bob count as a failed reviewer per `references/retry-policy.md`.

Active reviewers: Alice, Blake, Bob, Carl, Diana, plus Eve when `doubt_reviewer: fable`. Include Carl only if the optional Gemini check in step 1 passed, and Diana only if the optional Sonnet check passed; otherwise run the remaining reviewers. Use one `{id}` for the cycle so the `-o` output paths here match the consolidation paths in step 6.

Read these before proceeding:

- `references/agent-invocation.md` - invocation commands for each agent
- `references/retry-policy.md` - retry and format compliance rules

### 6. Consolidate findings

Save each subagent reviewer's returned text to `dev/local/tmp/` — **Alice** to `alice-output-{id}.txt`, **Blake** to `blake-output-{id}.txt`, **Eve** (when she ran) to `eve-output-{id}.txt`, and Bob's Claude fallback (when it ran) to `bob-output-{id}.txt`. Bob's, Carl's, and Diana's CLI outputs are already on disk - their `-o` flag wrote them straight to `bob-output-{id}.txt` / `carl-output-{id}.txt` / `diana-output-{id}.txt` in step 5. Then run:

```bash
~/.claude/skills/review-work-completion/scripts/consolidate-findings.sh \
  --surface work-completion \
  --prd $PWD/dev/local/prds/wip/<prd-filename> \
  --diff-range <COVERAGE_DIFF_RANGE captured in step 3> \
  --rubric ~/.claude/skills/review-work-completion/references/rubric.md \
  --repo $PWD \
  --run-tests \
  --write-aggregate $PWD/dev/local/tmp/coverage-{id}.md \
  ALICE:$PWD/dev/local/tmp/alice-output-{id}.txt \
  BLAKE:$PWD/dev/local/tmp/blake-output-{id}.txt \
  BOB:$PWD/dev/local/tmp/bob-output-{id}.txt \
  CARL:$PWD/dev/local/tmp/carl-output-{id}.txt \
  DIANA:$PWD/dev/local/tmp/diana-output-{id}.txt
```

Pass only agents that produced output (omit the `CARL:` pair when Carl was skipped, the `DIANA:` pair when Diana was skipped; append an `EVE:` pair when Eve ran). The script computes consensus dynamically from the number of agent pairs provided.

**Record the doubt-rubric verdicts (autopilot runs).** When `dev/local/autopilot/state.json` exists, parse the five `R{n}: pass|fail` lines from Bob's output (or his Claude fallback's) and REPLACE `state.doubts_rubric_verdicts` with the five entries `{"rule_id": "R{n}", "verdict": "pass"|"fail"}`; when Eve also ran, read her raw `R{n}:` lines too and write one entry per rule per reviewer with `source` tags (`"codex"` / `"fable"`). Verdicts are re-recorded every cycle; the final cycle's are the durable ones (the batch report renders them). Skip this entirely on standalone (non-autopilot) runs.

**If the coverage gate fails** (non-zero exit), stop and report the gap named in stderr. Do not proceed to step 7.

If coverage passes, `dev/local/tmp/coverage-{id}.md` now contains the aggregate coverage block. Step 8 appends it to the review file.

Outputs consolidated issues sorted by consensus then severity. See `references/output-formats.md` for output format details.

### 7. Create follow-up tasks

**If no issues found:** Skip task creation. Report clean review to user.

**If issues found:** Use `TaskCreate`, prioritizing multi-agent consensus:

- Process 🔴 → 🟠 → 🟡 order
- Max 25 tasks (batch overflow into "Misc fixes")
- Group by theme
- Tag complexity: `(S)` small, `(M)` medium, `(L)` large

See `references/output-formats.md` for task description format.

### 8. Save review file

Create at `dev/local/reviews/`.

See `references/output-formats.md` for filename convention, frontmatter, and content format.

Stamp the `head_sha` frontmatter field with the HEAD sha captured in step 3 — the next rework cycle reads it to scope its diff via `--since`.

Stamp the `codex_thread_id` frontmatter field with the thread id from `dev/local/tmp/bob-thread-{id}.txt` when that file exists and is non-empty AND Bob produced output this cycle — the next rework cycle reads it (step 3) to resume Bob's codex session via `--resume-thread`; omit the field otherwise (Bob was skipped, or thread-id capture failed).

Include all findings even if zero issues.

**Append the aggregate coverage block** from `dev/local/tmp/coverage-{id}.md` (written by step 6's coverage gate) at the end of the review file, after all findings. Use the **Write tool** to build the complete file content including the block.
