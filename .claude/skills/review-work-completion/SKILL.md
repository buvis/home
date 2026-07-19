---
name: review-work-completion
description: Use after all tasks are completed to validate implementation against PRD requirements via multi-agent consensus review; for a spec-only blind lens use review-blindly. Triggers on "review work", "check completed work", "are we done".
---

# Review Work Completion

## What This Does

Validates completed implementation work against PRD requirements using independent AI reviewers (tools may change in the future). Each reviewer analyzes the code changes and PRD criteria separately, then findings are consolidated by consensus - issues flagged by multiple reviewers get higher priority. Creates follow-up tasks for any gaps found.

**Why multiple reviewers:** Different models catch different issues. Consensus scoring surfaces real problems while filtering noise from single-model false positives.

> **Note for anyone reviewing/auditing this skill:** See `references/design-rationale.md` for settled design decisions
> before suggesting changes. This doesn't apply to skill users, as it doesn't add any useful information
> to perform the skill.

## Dependencies

Step 1 (Validate prerequisites) owns the reviewer-CLI checks and their
degradation rules - see it, this list does not repeat them. What step 1 does
not name:

- Personal skills: `use-codex` (hard - `scripts/codex-run.sh`, STOP if missing)
- Files read from other skill dirs:
  - `~/.claude/skills/run-autopilot/prompts/doubt-review.md` - the doubt-lens
    prompt carried by Bob (and Eve)
  - `~/.claude/skills/review-blindly/references/rubric.md` - inlined into
    Blake's blind prompt
- CLIs: `python3`, `git`
- Optional (graceful degradation, detailed in step 1): `use-gemini`, `use-qwen`,
  `git-ferry:catchup`

## Reviewers

Every review cycle runs all lenses (PRD 00015) — consensus, blind, and doubt
are prompt disciplines carried by the roster, not separate phases:

- **Alice** → Claude subagent (direct, not nested CLI); implementation-aware consensus lens. Her leg runs on the engine the PRD's `consensus_engine` flag selects (step 1): the legacy single subagent by default, or the `review-fanout` workflow — dimension fan-out, dedup, adversarial verification — when the flag opts in
- **Blake** → Claude subagent, **blind lens**: PRD-only prompt — no diff, no file list, no review history, no design doc (see `references/blind-lens-prompt.md`)
- **Bob** → Codex, **doubt lens**: carries the doubt rubric (R1-R5) and the de-slop lens every cycle; when codex is unavailable, a Claude subagent runs the same prompt so the lens never silently drops
- **Carl** → Gemini (frontend & design specialist; skipped when the Gemini CLI is unavailable)
- **Quinn** → local qwen via `qwen-run.sh -R --approved-only` (background Bash: the `pi` agent against a llama.cpp-served model, read-only, pinned to the eval-approved registry; **advisory weight** — findings unique to Quinn create no tasks; active only when the qwen preflight probe passes, skipped otherwise with a note)
- **Eve** → Claude Fable 5 Task subagent, opt-in fifth lens: joins the batch only when the PRD frontmatter sets `doubt_reviewer: fable`, running the same doubt prompt as Bob (see `references/agent-invocation.md` "Eve (Fable 5)"); absent otherwise

## Workflow

### 1. Validate prerequisites

Check these exist:

1. `~/.claude/skills/use-codex/scripts/codex-run.sh` - executable
2. `dev/local/prds/wip/` contains at least one `.txt` or `.md` file

(Alice is a native Claude subagent - no CLI prerequisite.)

**Optional - Carl (Gemini):** check `~/.claude/skills/use-gemini/scripts/gemini-run.sh` is executable AND a backend CLI resolves - `copilot` (preferred; serves `gemini-3.1-pro-preview`) OR native `gemini` (`mise which`/`command -v` succeeds for either). If both pass, Carl is active. If neither CLI resolves, skip Carl and proceed with the three remaining reviewers - this is graceful degradation, not a failure. Note in the final review file which reviewers ran. (Carl on the copilot backend spends Copilot AI credits; a "monthly quota exceeded" error from the helper is a runtime skip, not a prerequisite failure.)

**Optional - Quinn (local qwen):** run `~/.claude/skills/use-qwen/scripts/qwen-run.sh --preflight --approved-only` (foreground). It passes ONLY when a real 1-token completion succeeds against the served model — a `/v1/models` listing alone never passes (the false-healthy class). Exit 0 → Quinn is active. Any failure (`pi_missing`, `endpoint_unreachable`, `model_id_missing` — no approved model is live — `completion_failed`, or the script missing/non-executable) → skip Quinn and proceed with the remaining reviewers - graceful degradation, not a failure; llama-server down degrades to today's roster. Note in the final review file which reviewers ran and Quinn's skip reason when he was skipped. (The probe can take up to ~2 min on a cold backend — it doubles as the model warm-up for step 5.)

Create if missing: `dev/local/tmp/`, `dev/local/reviews/`

**Path convention:** All `dev/local/` paths in this skill are relative to the project root. When passing file paths to subagents or external scripts, always use absolute paths (e.g. `$PWD/dev/local/tmp/...`) so they resolve correctly regardless of the subagent's working directory.

**Resolve the consensus engine.** Alice's leg runs on one of three engines. Read `state.consensus_engine` from `dev/local/autopilot/state.json` (autopilot parses the PRD frontmatter once, at Phase 0); on a standalone run with no state file, read `consensus_engine` straight from the wip PRD's frontmatter.

| value | Alice's leg |
|-------|-------------|
| `legacy` (default — also every absent or invalid value) | Today's single Task subagent. No Workflow call, nothing else changes. |
| `workflow` | The `review-fanout` workflow **is** Alice's leg (step 5). |
| `shadow` | Both. Legacy Alice gates the cycle; the workflow runs beside her, non-gating, and its result is recorded as an observation (step 8). |

An invalid value falls back to `legacy` with one logged warning line (same rule as `rework_cap` / `doubt_reviewer`). Hold the resolved value as `CONSENSUS_ENGINE` for steps 5 and 8.

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

**Determine review scope (full vs incremental).** List existing review files for this PRD with Bash `ls` (the native `Glob` tool is absent in this build): `dev/local/reviews/<prd-name>-review-*.md` (PRD filename without the `.md` extension).

- **No prior review file** → cycle 1, a **full review**. Run `gather-context.sh` without `--since`.
- **A prior review file exists** → this is a rework cycle, an **incremental review**. Read the highest-numbered prior file's `head_sha` frontmatter field.
  - `head_sha` present → pass `--since <head_sha>` to `gather-context.sh`. The diff then covers only the rework commits since that cycle, not the whole PRD branch — the prior cycle already reviewed the full diff. Also read that file's consolidated findings; step 4 hands them to the reviewers to verify.
  - `head_sha` absent (file predates this field) → fall back to a full review (omit `--since`).
  - Also read that same prior file's `codex_thread_id` frontmatter field (stamped in step 8 of the prior cycle). Present → step 5 adds `--resume-thread <codex_thread_id>` to Bob's launch so codex resumes his prior session instead of re-reviewing from zero. Absent (pre-change file, or Bob was skipped / thread-id capture failed last cycle) → Bob runs a fresh review, no resume flag.

Capture the current HEAD now — `git rev-parse HEAD` — and hold it; step 8 stamps it into this cycle's review file as `head_sha`.

Also capture the diff range for the review scope (recorded in the review file; the doubt lens reviews this range). For an **incremental review** the diff range is `<prior-cycle-head-sha>` (the same SHA passed to `gather-context.sh --since`). For a **full review**: when running under autopilot and `state.work_start_sha` is set in `dev/local/autopilot/state.json`, use `<work_start_sha>..HEAD` (the PRD's whole work range — this is the scope the doubt lens reviews); otherwise compute it via `git merge-base HEAD origin/HEAD` (fallback: `git merge-base HEAD master`, then `git merge-base HEAD develop`). Store this as `COVERAGE_DIFF_RANGE`.

Run `gather-context.sh` (from project root). Full review:

```bash
~/.claude/skills/review-work-completion/scripts/gather-context.sh dev/local/tmp/review-tasks-{id}.md dev/local/tmp/review-prd-{id}.md
```

Incremental review (rework cycle) — prepend `--since <prior-cycle-head-sha>`:

```bash
~/.claude/skills/review-work-completion/scripts/gather-context.sh --since <prior-cycle-head-sha> dev/local/tmp/review-tasks-{id}.md dev/local/tmp/review-prd-{id}.md
```

Both positional args are optional — omit if no tasks/PRD available. Outputs context file and diff file paths to `dev/local/tmp/`.

**Bare-repo homes (e.g. `~/.buvis`: `git --git-dir=~/.buvis --work-tree=~`):** `gather-context.sh` assumes a normal checkout and fails here — do not fight it. Build the review inputs yourself: generate the diff with `git --git-dir=<bare-dir> --work-tree=<tree> diff <COVERAGE_DIFF_RANGE>` (the range captured above), write it plus the tasks/PRD/context files to `/tmp/` with the Write tool, and pass those absolute `/tmp` paths to the reviewer prompts. The script path stays primary for normal repos.

### 4. Prepare agent prompts

Create prompt files in `dev/local/tmp/`:

For each active agent, use the **Write tool** (not bash heredocs) to create `dev/local/tmp/{agent}-prompt-{unique-id}.md` (use timestamp or UUID). **Use absolute paths** (e.g. `/full/path/to/project/dev/local/tmp/...`) when writing and when referencing these files in agent prompts - relative `dev/local/` paths get misresolved as `~/dev/local/` by subagents. See `references/agent-prompts.md` for prompt template structure.

**Create each prompt independently.** Do NOT create one prompt and copy/sed it into another - this triggers bash permission warnings (quote characters in comments desync quote tracking). Quinn and Alice share the same template (Quinn runs the standard implementation-aware review prompt — never the blind or doubt lens); Bob gets the sandbox constraints appendix PLUS the doubt-lens appendix (rubric R1-R5 + de-slop, per `references/agent-prompts.md` "Bob"); Blake's prompt is assembled from `references/blind-lens-prompt.md` + the PRD content ONLY (no context file, no diff file, no incremental-review addendum — blind every cycle); Eve (when active) reuses Bob's doubt-lens content per `references/agent-invocation.md`. Build each from its template directly.

> **Why Write tool:** Prompt templates contain patterns like `{path or "N/A"}` that trigger bash permission checks ("brace with quote character - expansion obfuscation"). The Write tool bypasses this entirely since it doesn't go through the shell.

With 1M context, agent prompts can include more background — full PRD, architecture summary, relevant module interfaces — rather than compressed summaries. Richer context produces better reviews.

**For an incremental review** (step 3 found a prior cycle): add to each agent prompt the prior cycle's consolidated findings, plus this instruction:

> This is an **incremental review** of the rework done since the previous review cycle — the diff is scoped to changes since then. Two jobs: (1) for each prior finding listed below, verify it is now resolved in the code; (2) review the scoped diff for any regression the rework introduced. You need not re-review unchanged code; the previous cycle already reviewed the full implementation.

### 5. Run agent review

**Stamp the lens roster (autopilot runs).** When `dev/local/autopilot/state.json` exists, REPLACE `state.review_lenses` (merge into state.json, do NOT replace sibling fields) with one key per active lens set to `"running"`: `consensus` (Alice), `blind` (Blake), `doubt` (Bob), plus `ui` (Carl), `qwen` (Quinn), and `fable` (Eve) only when active. tracon renders these as the review phase's sub-steps; step 6 flips them to `"done"`/`"failed"`. Skip entirely on standalone (non-autopilot) runs.

**Launch ALL active reviewers in a SINGLE message so they run concurrently.** Alice, Blake, and Eve (when active) are Task subagent calls (native Claude tools). Bob, Carl, and Quinn are parallel **background Bash** commands (`run_in_background: true`) - never wrap a CLI reviewer (codex/gemini/qwen) in a subagent, it hangs and strands the whole cycle (see `references/agent-invocation.md`). Put the Task calls, the Watcher (below, if `$_AUTOPILOT_LOOP` is set), and the background Bash calls in the one message - if any CLI reviewer is in the dispatch, the Watcher goes in the same message or nothing holds the session open to see it finish.

**Watcher (headless keep-alive — dispatch only when `$_AUTOPILOT_LOOP` is set).** Headless `claude -p` kills background Bash tasks ~5s after the final result; only a live subagent holds the session open (2026-07-12 loop death: every Claude subagent reviewer finished first, the CLI exited at turn end and killed codex mid-review, the loop halted). So in the SAME dispatch message, launch one extra Task subagent named Watcher (general-purpose) whose entire prompt is:

> Run `python3 ~/.claude/skills/review-work-completion/scripts/await_reviewer_outputs.py --budget 100 <absolute -o output path of each CLI reviewer dispatched>` as a foreground Bash call. If the last stdout line is `WAITING`, run the same command again — up to 30 times total. Return the script's final output verbatim (`DONE`, or `WAITING` plus the pending files after 30 runs). Do nothing else: no reading the output files, no review commentary.

The Watcher is scaffolding, not a reviewer: its return is never saved, consolidated, or counted by the retry policy. Once every reviewer's output is in hand (including a Bob fallback's), `TaskStop` the Watcher if it is still running, then proceed to step 6. A `WAITING` return after 30 runs (~50 min) means a CLI reviewer stalled — treat that reviewer as failed per `references/retry-policy.md`.

**Do not Write or Edit ANY reviewer output (Alice's and Blake's included) until ALL reviewers have reported.** The CLIs self-write via `-o`; subagent-returned text is saved only in step 6, after every reviewer has completed - even if a subagent returns first.

**Bob fallback (the doubt lens never drops).** If `codex-run.sh` exits non-zero with exit 3 (codex unavailable), dispatch a Claude Task subagent with Bob's exact assembled prompt (doubt lens + rubric included) and use its output as Bob's. On exit 4 (codex ran but failed, e.g. quota), FIRST check the wrapper's `codex-review-last.jsonl` sidecar: exit 4 has a documented false-positive mode (quota markers matched in codex's own command args or gateguard noise) where codex actually finished — if the sidecar holds a complete review (findings plus all `R{n}:` verdict lines), salvage it as Bob's output and skip the fallback entirely. Only when no complete review is salvageable dispatch the Claude fallback; only if that also fails does Bob count as a failed reviewer per `references/retry-policy.md`.

**Alice on the workflow engine** (`CONSENSUS_ENGINE` is `workflow` or `shadow`; skip this whole block on `legacy`). The workflow call goes in the SAME single dispatch message as the other reviewers — it is a foreground tool call whose inner agents are live subagents, so it holds a headless session open exactly as a Task subagent does. The Watcher rule above is unchanged: it exists for the background-Bash CLI reviewers.

```
Workflow({
  scriptPath: "/Users/bob/.claude/workflows/review-fanout.workflow.js",
  args: { ... }
})
```

Invoke by absolute `scriptPath`, never by `name` — the named-workflow registry resolves `.claude/workflows/` relative to the project root, and when the project root *is* `~/.claude` that path is ambiguous.

Build `args` from the context already gathered in step 3:

| arg | value |
|-----|-------|
| `diff` | The diff file's text, **truncated by you to at most 400000 bytes** (`MAX_DIFF_BYTES`). The payload crosses the tool boundary as JSON, so the cap is the caller's job. |
| `diff_bytes` | The diff file's **real** byte size before truncation (`wc -c`). |
| `diff_path` | Absolute path to the full diff file. Mandatory whenever `diff_bytes` exceeds 400000; the dimension agents are told to read it. |
| `rubric_text` | `~/.claude/skills/review-work-completion/references/rubric.md`, verbatim — THIS skill's 12-rule file, not review-blindly's same-named R1–R19 rubric (the workflow's verdict-line schema expects exactly these rules). Alice's `R{n}: pass\|fail` verdict lines are generated from it, and `references/retry-policy.md` fails a reviewer that omits them. |
| `prd_text`, `prd_path`, `changed_files`, `context_path` | From step 3's gathered context. |
| `head_sha`, `date`, `cycle`, `agent_name` | `head_sha` from step 3; `date` as `YYYY-MM-DD` (the sandbox cannot call `Date()`); `cycle` = this review cycle; `agent_name` = `ALICE`. |
| `tests_line` | Omit on the live path — test counts do not exist until step 6. Shadow runs substitute it at step 8. |

On return, write the result's `agent_output` verbatim to `dev/local/tmp/alice-output-{id}.txt`. Step 6 consolidates it unchanged: it already speaks the `[ALICE] {emoji} … | File: … | Task: …` line format, carries the twelve `R{n}` verdict lines, and ends with the engine's `stats_line`.

Three failure classes, three different answers — **only the last one may fall back to legacy**:

1. **`INVALID_ARGS` throw** (empty diff, missing `rubric_text`, an over-cap diff with no `diff_path`). A caller bug or a review with nothing valid to review — it must NOT degrade to legacy Alice, which would paper over it. Repairable (e.g. `rubric_text` was not passed) → repair and re-invoke once. An **empty diff STOPS the review**: a review of nothing must never reach `Verdict: converged`.
2. **`incomplete: true` in the return value** (a dimension agent or a verifier died). Re-invoke once with `resumeFromRunId: <runId>` — completed dimensions replay from cache, only the dead ones re-run. Still `incomplete` → its 🔴 `review incomplete` lines stand (a partial review cannot converge) and Alice counts as a degraded reviewer per `references/retry-policy.md`.
3. **Engine unavailable** (the `Workflow` tool is absent or the harness refuses the call). This — and only this — falls back to legacy Alice for the cycle, loudly, with the fallback noted in the review file.

On `shadow`, legacy Alice still runs and still gates; the workflow's output is never written to `alice-output-{id}.txt` and never consolidated. Step 8 records it.

Active reviewers: Alice, Blake, Bob, Carl, Quinn, plus Eve when `doubt_reviewer: fable`. Include Carl only if the optional Gemini check in step 1 passed, and Quinn only if the optional qwen preflight in step 1 passed; otherwise run the remaining reviewers. Use one `{id}` for the cycle so the `-o` output paths here match the consolidation paths in step 6.

Read these before proceeding:

- `references/agent-invocation.md` - invocation commands for each agent
- `references/retry-policy.md` - retry and format compliance rules

### 6. Consolidate findings

**Close out the lens roster (autopilot runs).** When `state.review_lenses` was stamped in step 5, set each lens to `"done"`, or `"failed"` for a reviewer that failed per `references/retry-policy.md` (a lens rescued by a fallback — e.g. Bob's Claude fallback — is `"done"`). Skip on standalone runs.

Save each subagent reviewer's returned text to `dev/local/tmp/` — **Alice** to `alice-output-{id}.txt`, **Blake** to `blake-output-{id}.txt`, **Eve** (when she ran) to `eve-output-{id}.txt`, and Bob's Claude fallback (when it ran) to `bob-output-{id}.txt`. Bob's, Carl's, and Quinn's CLI outputs are already on disk - their `-o` flag wrote them straight to `bob-output-{id}.txt` / `carl-output-{id}.txt` / `quinn-output-{id}.txt` in step 5. Then run:

```bash
~/.claude/skills/review-work-completion/scripts/consolidate-findings.sh \
  ALICE:$PWD/dev/local/tmp/alice-output-{id}.txt \
  BLAKE:$PWD/dev/local/tmp/blake-output-{id}.txt \
  BOB:$PWD/dev/local/tmp/bob-output-{id}.txt \
  CARL:$PWD/dev/local/tmp/carl-output-{id}.txt \
  QUINN:$PWD/dev/local/tmp/quinn-output-{id}.txt
```

Pass only agents that produced output (omit the `CARL:` pair when Carl was skipped, the `QUINN:` pair when Quinn was skipped; append an `EVE:` pair when Eve ran). The script computes consensus dynamically from the number of agent pairs provided.

**Advisory weighting for Quinn (local model).** After consolidation, split the findings: any finding whose only finder is Quinn is ADVISORY — list it in the review file under an `### Advisory (local model, unconfirmed)` heading (same line format, no consensus score) and create NO follow-up tasks from it in step 7. Findings where Quinn concurs with at least one other reviewer stay in the consolidated table and count toward consensus normally — his concurrence raises the score like any other reviewer's. Local-model noise must never create rework tasks alone. See `references/output-formats.md` "Advisory bucket (Quinn)".

**Compose the `Verdict:` line.** Zero consolidated findings → `Verdict: converged`; otherwise `Verdict: N findings` (the consolidated count). Step 8 writes it into the review file.

**Compose the `Tests:` line.** Record the cycle's test counts — run the project's test suite once in the FOREGROUND (or reuse the counts from a suite run already performed this cycle; do not run it twice) and write `Tests: N passed, M failed, K skipped`. When the reviewed diff touches no code, write `Tests: none (docs-only)` — a first-class value, not a sentinel.

**Record the doubt-rubric verdicts (autopilot runs).** When `dev/local/autopilot/state.json` exists, parse the five `R{n}: pass|fail` lines from Bob's output (or his Claude fallback's) and REPLACE `state.doubts_rubric_verdicts` with the five entries `{"rule_id": "R{n}", "verdict": "pass"|"fail"}`; when Eve also ran, read her raw `R{n}:` lines too and write one entry per rule per reviewer with `source` tags (`"codex"` / `"fable"`). Verdicts are re-recorded every cycle; the final cycle's are the durable ones (the batch report renders them). Skip this entirely on standalone (non-autopilot) runs.

Outputs consolidated issues sorted by consensus then severity. See `references/output-formats.md` for output format details.

### 7. Create follow-up tasks

**If no issues found:** Skip task creation. Report clean review to user.

**If issues found:** Use `TaskCreate`, prioritizing multi-agent consensus:

- Process 🔴 → 🟠 → 🟡 order
- Max 25 tasks (batch overflow into "Misc fixes")
- Group by theme
- Tag complexity: `(S)` small, `(M)` medium, `(L)` large
- **Skip advisory-bucket findings** (Quinn-only, per step 6) — they are recorded in the review file but never become tasks

See `references/output-formats.md` for task description format.

### 8. Save review file

Create at `dev/local/reviews/`.

See `references/output-formats.md` for filename convention, frontmatter, and content format.

Stamp the `head_sha` frontmatter field with the HEAD sha captured in step 3 — the next rework cycle reads it to scope its diff via `--since`.

Stamp the `codex_thread_id` frontmatter field with the thread id from `dev/local/tmp/bob-thread-{id}.txt` when that file exists and is non-empty AND Bob produced output this cycle — the next rework cycle reads it (step 3) to resume Bob's codex session via `--resume-thread`; omit the field otherwise (Bob was skipped, or thread-id capture failed).

Stamp the `reviewers:` frontmatter field with the comma-separated lowercase names of every reviewer that actually ran (e.g. `reviewers: alice,blake,bob,quinn`) — `check_review_file.py` reads it to verify each section.

**Stamp `consensus_run_id`** with the `runId` the Workflow tool returned, whenever the engine ran (`workflow` or `shadow`) — same pattern as `codex_thread_id`, and the forensic handle for that cycle's run. It is deliberately not written to `state.json`: `resumeFromRunId` is same-session only, so a stored id would outlive its own usefulness.

**Shadow runs (`CONSENSUS_ENGINE == "shadow"`).** The workflow's `review_markdown` carries the literal token `{{TESTS_LINE}}` (step 5 passed no `tests_line`). Substitute the `Tests:` line composed in step 6 for that token — a file still carrying the token cannot pass `check_review_file.py` — then write the result to `dev/local/tmp/<prd-base>-consensus-shadow-{cycle}.md`. **Never** to `dev/local/reviews/`: step 3's `-review-*.md` glob finds the prior cycle there, and a shadow file in that directory would be mistaken for one. Gate the shadow file with `check_review_file.py --reviewers alice`, then record in the real review file, under Alice's section, the engine's `stats_line` and any verdict divergence from legacy Alice — as an observation, never as a finding. The shadow never gates.

Include all findings even if zero issues. Give each reviewer that ran a `## <Name>` section (their findings, or a one-line all-clear; Bob's keeps his `R{n}:` verdict lines), and end the file with the `Verdict:` and `Tests:` lines composed in step 6.

**Gate the saved file (PRD 00016).** Run the shape check and fix the file if it fails — do not report a completed review over a failing gate:

```bash
python3 ~/.claude/skills/review-work-completion/scripts/check_review_file.py --review-file $PWD/dev/local/reviews/<review-file>
```
