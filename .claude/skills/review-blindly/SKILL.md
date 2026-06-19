---
name: review-blindly
description: Use when a major implementation is complete and all per-task reviews have passed, before finishing-a-development-branch. Mandatory after multi-file features and plan execution. Not for single-file fixes or refactors.
---

# Blind Review

Dispatch a review agent that receives ONLY the original spec. A reviewer who knows nothing about the implementation catches spec drift, security gaps, and race conditions that implementation-aware reviewers miss.

**Announce at start:** "I'm using the blind-review skill to validate this implementation against the spec."

## The Process

### Step 1: Gather the Spec and Rubric

Extract the original requirements. This is the ONLY narrative context the reviewer gets.

**Do NOT include:** implementation summaries, file lists, notes about how it was built, implementer's self-review.

Also load the numbered blind-review rubric from `references/rubric.md`. Its contents will be embedded inline into the reviewer's prompt (see Step 2). The rubric is spec-only by design — it does NOT introduce implementation context. Inline embedding (not a file reference) is REQUIRED because the blind reviewer is dispatched with a self-contained prompt and cannot resolve relative paths. Also note that the dispatched prompt embeds the `---review-coverage---` block format inline (per `references/review-coverage-format.md`); the format does NOT need to be loaded separately.

**Template substitution.** Step 2's prompt block uses the placeholder `{contents of references/rubric.md}`. When assembling the dispatch, read `references/rubric.md` and substitute its full file contents at that placeholder. The rubric file is the single source of truth — never copy the rules into this SKILL.md.

### Step 2: Dispatch the Blind Reviewer (Sonnet, inline)

**Block on the reviewer — never dispatch-and-yield, and never via a `model`-override subagent.** Route the review to Sonnet by shelling out to the Sonnet CLI from a plain `general-purpose` subagent (the Diana pattern in `review-work-completion`). Do **NOT** set `model: "sonnet"` on the Task tool: a `model` override makes the harness run the subagent as a *background* task that returns an async-launch acknowledgment (an `agentId` / "you will be notified automatically") instead of the report. Under autopilot that strands the review — the Stop hook ends the session before the background result lands, `"blind"` never reaches `phases_completed`, and the loop re-enters blind review until the phase-thrash circuit-breaker halts the run (observed 2026-06-17 PRD 00157: 18 dead restarts; recurred 2026-06-19 on playground PRD 00001, where the Sonnet reviewer actually completed but its notification arrived in a session the Stop hook had already killed). Omitting `model` keeps the subagent inline and blocking, so it returns the reviewer's full report this same turn; continue straight to Step 2.5. The blind phase is done only when the reviewer's findings + `---review-coverage---` block are in hand AND `dev/local/reviews/<prd>-blind-review.md` is written.

Pin the reviewer to **Sonnet** for model diversity — a different family from the typical Opus implementer breaks shared priors and gives actual independence, not narrative-only blindness. Sonnet runs agentically via the CLI (`-a` auto-approves tools), so it finds and reads the implementation itself.

**Step 2a — write the reviewer prompt to a temp file.** Use the **Write tool** to create `dev/local/reviews/.blind-reviewer-prompt.md` with exactly this content — paste the full spec at the marked line and inline the rubric:

```text
    You are a hostile auditor reviewing code you've never seen before.
    You know ONLY what was supposed to be built. You must find the code,
    read it, and determine if it does what the spec says.

    ## The Specification

    [PASTE FULL SPEC/REQUIREMENTS — NOTHING ELSE]

    ## The Rubric (binary pass/fail rules, spec-only)

    {contents of references/rubric.md}

    ## Your Job

    Read the actual codebase and verify against the spec above.
    You have NO implementation context. Find the code yourself.

    **Check for:**

    1. **Spec compliance** — Every requirement implemented? Anything
       extra? Requirements misinterpreted?

    2. **Security and deployment readiness** — Secrets with empty
       defaults? Missing auth checks? Fail-open paths? Race conditions
       (check-then-act)?

    3. **Data safety** — Backward compatibility? Migration paths?
       Malformed/missing data handling?

    4. **Missing error paths** — Token expiry, network failure, partial
       writes? Retry and recovery?

    **IMPORTANT: If you cannot find implementation files, you MUST still
    produce a full report.** Enumerate every spec requirement, flag every
    security concern derivable from the spec. "Code not found" is a
    Critical finding, not a reason to stop.

    **Report format:**
    - Critical: Must fix before merge (security, data loss, spec violations)
    - Important: Should fix (missing error handling, race conditions)
    - Minor: Nice to fix (style, naming)
    - Spec compliance: ✅ Met / ❌ Not met — line-by-line breakdown
    - Spec-derived risks: Concerns to verify in code

    **PER-RULE VERDICTS ARE MANDATORY.** For every rule in The Rubric above, emit one line in this exact shape:
    ```
    R{n}: pass
    ```
    or
    ```
    R{n}: fail
    ```
    One rule per line, no other text on the line, no rationale. Answer every rule — a rule you cannot evaluate (insufficient context, no implementation found, etc.) counts as `fail`; never omit the line. Rule IDs are stable; do not renumber.

    ## Coverage Block (mandatory at end of output)

    Emit a `---review-coverage---` block as the LAST thing in your output. Fill three dimensions: `files`, `features`, `rubric`. Leave `tests` empty (the consolidation step fills it). The `files` dimension covers files the blind reviewer inspects (since the blind reviewer must find the code itself).

    Format (delimiters are EXACT strings on their own lines):

    ---review-coverage---
    files:
      <path>: reviewed
      <path>: n/a:<reason>
    tests:
      pending: filled by consolidation
    features:
      <feature name>: verified
      <feature name>: reviewed
      <feature name>: failed
    rubric:
      R{n}: pass
      R{n}: fail
    ---end-review-coverage---

    Rules:
    - `files`: one entry per diff path. Value is `reviewed` or `n/a:<reason>` (free text after the colon).
    - `tests`: leave it as the single line `pending: filled by consolidation`. Do NOT report test counts; consolidation runs the suite and fills the aggregate.
    - `features`: one entry per PRD `#### Feature:` heading. Value is `verified` / `reviewed` / `failed`.
    - `rubric`: one entry per rule ID from the surface's rubric. Value is `pass` / `fail`. Lowercase only.
    - A feature or rule you cannot evaluate counts as `failed` / `fail` — never omit the line.

    Source of truth for the block format: `~/.claude/skills/review-work-completion/references/review-coverage-format.md`.
```

**Step 2b — dispatch the reviewer inline.** Dispatch a `general-purpose` subagent with **NO `model` parameter** (omitting it is exactly what keeps the run inline and blocking) whose only job is to run Sonnet on that prompt file and hand the output back verbatim:

```text
Task tool:
  subagent_type: general-purpose
  description: "Blind spec review for [feature name]"
  prompt: |
    You are the blind-review dispatcher. Run this single command and return
    its output verbatim — do not summarize, do not add commentary, do not act
    on the findings yourself:

    timeout 600 ~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -a -f <ABSOLUTE path to dev/local/reviews/.blind-reviewer-prompt.md>

    `-a` auto-approves tools so Sonnet can read the codebase and find the
    implementation itself. `timeout 600` bounds a hung CLI. If the command
    exits non-zero (including a timeout), report the failure immediately and
    verbatim — do not retry silently.
```

The subagent runs the CLI in the foreground and blocks until Sonnet's full report (ending in the `---review-coverage---` block) is in hand, then returns it as the tool result this same turn. There is no async acknowledgment to wait across turns for, so there is nothing to strand on. Proceed to Step 2.5.

### Step 2.5: Gate Coverage and Write the Review File

After the blind reviewer subagent returns its report verbatim, do the following in order. **If the subagent returned an error, a timeout, or an empty / async-launch acknowledgment instead of a full report ending in a `---review-coverage---` block, the review did NOT complete — re-dispatch (Step 2b) and wait for the real report. Do not proceed past this point, and do not end your turn, until the findings + coverage block are in hand.**

1. Write the reviewer's FULL output (ending with its `---review-coverage---` block) to a temp block file:
   ```
   dev/local/reviews/.blind-reviewer-block.md
   ```

2. Resolve `<prd-base>` = the PRD filename without its `.md` extension. Read `work_start_sha` from `dev/local/autopilot/state.json` to form the diff range `<work_start_sha>..HEAD`. If no `state.json` exists (standalone, non-autopilot run), fall back to `master...HEAD`. Do not crash on a missing state file.

3. Invoke the coverage gate (do NOT pass `--rubric`; the gate resolves the `blindly` rubric via `SURFACE_RUBRIC_DEFAULTS`):
   ```bash
   python3 ~/.claude/skills/review-work-completion/scripts/review_coverage.py \
     --surface blindly \
     --prd <prd-path> \
     --diff-range <work_start_sha>..HEAD \
     --reviewer-block dev/local/reviews/.blind-reviewer-block.md \
     --run-tests \
     --write-aggregate dev/local/reviews/.blind-aggregate.md
   ```

   `--run-tests` makes the gate run the changed test files (`test_*.py` / `*_test.py`
   in the diff) once and fill the aggregate's `tests` dimension with real
   pass/fail/skip counts. The reviewer leaves `tests` as the `pending` sentinel;
   the gate replaces it. Without real counts, a code diff fails `EMPTY_TESTS`.

4. **Fail loud:** if the gate exits non-zero, the blind review FAILS. Surface the gap kind printed on stderr (`MISSING_REVIEW_BLOCK`, `MALFORMED_BLOCK`, `MISSING_FILES`, `EMPTY_TESTS`, `UNMAPPED_FEATURE`, `MISSING_RUBRIC_RULE`, or `MISSING_PRD`) and its detail. Do NOT produce a clean verdict.

5. On exit 0: write `dev/local/reviews/<prd>-blind-review.md` containing the reviewer's findings prose followed by the aggregate coverage block from `dev/local/reviews/.blind-aggregate.md`. Note in the file that this name is intentionally distinct from the `-review-NN.md` pattern (it does not collide with the Phase 4 cycle-skip glob), and that the autopilot Phase 2 Stop hook re-checks this file's aggregate block.

### Step 3: Act on Findings

- **Critical:** Fix immediately, re-run blind review on affected areas
- **Important:** Fix before merge
- **Minor:** Fix or note for follow-up
- Zero issues found? Be suspicious — verify the reviewer actually read code (check for file:line references)

## Integration

```text
subagent-driven-development: Per-task reviews → All tasks done → BLIND REVIEW → finishing-a-development-branch
executing-plans:             All batches done → BLIND REVIEW → finishing-a-development-branch
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Including implementation context | Spec only — let reviewer find code independently |
| Skipping because per-task reviews passed | Per-task reviews catch different bugs than whole-spec review |
| Trusting "zero issues" result | Verify reviewer read the code (check for file references) |
| Short-circuiting on "code not found" | Still enumerate every spec requirement and flag spec-derived risks |
| Cutting corners under time pressure | "Merge today" is not a reason for a "quick review" |

## Red Flags

**Never:** give the reviewer implementation context, skip because standard reviews passed, merge with unresolved Critical findings, do a "quick" blind review under time pressure, stop because files weren't found.

**Always:** provide only the spec, let the reviewer find code independently, enumerate spec-derived risks before reading code, fix Critical/Important before merge, re-review after significant fixes.
