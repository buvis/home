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

### Step 2: Run the Blind Reviewer (Sonnet, direct foreground CLI)

**Run the Sonnet CLI as a DIRECT Bash command in THIS session — do NOT wrap it in a subagent.** This harness backgrounds EVERY `Agent`/`Task` dispatch, even a plain `general-purpose` subagent with no `model` override (the old "omitting model keeps it inline" assumption is dead — verified 2026-06-19). A backgrounded reviewer returns an async-launch acknowledgment (an `agentId` / "you will be notified automatically") instead of the report, and under autopilot the Stop hook ends the session before that result lands — so `"blind"` never reaches `phases_completed` and the loop re-enters blind review until the phase-thrash circuit-breaker halts the run (observed 2026-06-17 PRD 00157: 18 dead restarts; recurred 2026-06-19 on playground and claude-warden, where the Sonnet reviewer completed but its notification arrived in a session the Stop hook had already killed). A **foreground Bash call blocks the turn** until the CLI exits, so there is nothing to strand on. The blind phase is done only when the reviewer's findings + `---review-coverage---` block are in hand AND `dev/local/reviews/<prd>-blind-review.md` is written.

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

**Step 2b — run the reviewer with a direct foreground Bash call.** Run this single command in THIS session via the **Bash tool** (NOT wrapped in a subagent). Give the Bash tool a generous timeout (up to 600000 ms) so it blocks for the whole run. Do NOT redirect into `dev/local/` — the aegis hook blocks shell `>` there; the Bash result comes back into this turn and the Write tool (Step 2.5) owns the file:

```bash
timeout 600 ~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -a -f <ABSOLUTE path to dev/local/reviews/.blind-reviewer-prompt.md>
```

`-a` auto-approves tools so Sonnet reads the codebase and finds the implementation itself. `timeout 600` bounds a hung CLI. The Bash tool runs this in the FOREGROUND and blocks the turn until the CLI exits, then returns Sonnet's full report (ending in the `---review-coverage---` block) as the tool result this same turn — there is no async acknowledgment to strand on. If the command exits non-zero (including a timeout), or the result does not end with a `---review-coverage---` block, the review did NOT complete — re-run this command; do not proceed. Proceed to Step 2.5.

### Step 2.5: Gate Coverage and Write the Review File

After Step 2b's Bash call returns, do the following in order. **If the command errored, timed out, or the Bash result does not end with a full `---review-coverage---` block, the review did NOT complete — re-run Step 2b. Do not proceed past this point until the findings + coverage block are in hand.**

1. Write the reviewer's FULL output (the Bash result from Step 2b, ending with its `---review-coverage---` block) to `dev/local/reviews/.blind-reviewer-block.md` using the **Write tool** (not a shell redirect — the aegis hook blocks `>` into `dev/local/`).

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
