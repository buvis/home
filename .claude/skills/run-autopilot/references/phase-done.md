# Done Gate (`phase: "done"`)

Routed here when `state.phase` is `"done"`. Finalizes the current PRD
(Phase 9), then hands off to the next PRD or ends the batch. The Batch-End
Review presentation at the bottom is also the target of the `/run-autopilot
review-batch` entry point, which replays it interactively against a closed
batch's deferred JSON — no state changes in that mode. Core `SKILL.md` (always
loaded) carries the shared mechanics and the test-pinned invariants.

## Phase 9: Completion

1. **Commit history is left as-is.** Autopilot does NOT rewrite the PRD's commit history; the user squashes/groups commits manually before pushing. (Why the old regroup engine was deleted: `references/design-rationale.md` § Commit history.)

2. Update state: set `phase: "done"` and `next_phase: "done"`

3. Move the PRD from `wip/` to `done/` (use `mv`, keep the `00XXX-` prefix) under the **verified-move invariant** (core `SKILL.md` § "Phase 9 invariants"): confirm arrival in `dev/local/prds/done/`, else pause with `site: "mv_verify"` — never append to `completed_prds` or advance with the PRD in the wrong folder.

4. Append completed PRD to `batch.completed_prds` in state file, and reset
   `batch.parks_consecutive = 0` — a healthy PRD drain clears the systemic-park
   breaker so a later `wrapper_died` park starts counting fresh (see
   `references/recovery.md` § Systemic-park breaker interaction). `batch` is
   preserved in full at step 10, so this reset value carries into the next PRD.

5. Delete all tasks from the completed PRD: query `TaskList`, mark every task as `deleted` via `TaskUpdate`. This prevents stale tasks from triggering Phase 2's skip logic on the next PRD.

6. Append items to `dev/local/autopilot/deferred/{batch_id}-deferred.json` (create if missing). Collect from the current state file:
   - `deferred_decisions` with status `"pending"` or `"deferred"` -> type `"deferred_decision"` (preserve original `type` field if present, e.g. `"doubt-overflow"`)
   - `doubts` with status `"pending"` -> type `"doubt"`
   - `autonomous_decisions` with `research` field -> type `"autonomous_research"` (for user awareness at batch end)
   Each entry gets tagged with `prd` (filename) and `cycle`. Preserve the full `research` field when present - this is the only copy that survives state reset. Skip this step if nothing to write.

6a. **Render this PRD's audit file** `dev/local/reviews/<prd-base>-audit.md` (`<prd-base>` = PRD filename without `.md`) ONCE from the state decision arrays — this is the ONLY writer of `audit.md`. Write in a single pass (Write tool): a header (PRD, started/completed timestamps, counts `autonomous N | deferred N | doubts N`), then one entry per item in `state.autonomous_decisions` (label `autonomous`), `state.deferred_decisions` (`deferred`), and `state.doubts` (`doubt`), using the entry format in `references/audit-log-format.md`. When all three arrays are empty, write the header plus a single `no decisions recorded` line.

7. Append the PRD summary to the batch report under the **report-id invariant** (core `SKILL.md` § "Phase 9 invariants"): the filename is built from the current `state.batch.id` — `dev/local/autopilot/reports/{state.batch.id}-report.md` (create with header if missing), never chosen by glob. See `references/batch-report-format.md` for format. Render these subsections:
   - **Doubt Rubric Verdicts (PRD 00038):** render `state.doubts_rubric_verdicts` one row per rule; when entries carry `source` (a dual-reviewer `doubt_reviewer: fable` run — one entry per rule per reviewer), combine both reviewers into a single row per rule — `| R1 | pass (codex) / pass (fable) |` (a per-reviewer `fail` still shows, e.g. `| R3 | pass (codex) / fail (fable) |`). When no entry carries `source` (single-reviewer / legacy state), render UNCHANGED — one verdict per rule, no source suffix (`| R1 | pass |`).
   - **Loop Metrics (PRD 00013):** render a `### Loop Metrics` subsection from `dev/local/autopilot/loop-metrics.jsonl` — read the lines whose `prd` matches `state.prd` AND whose `batch` matches `state.batch.id`, then report the session count, wall seconds grouped by `phase_launched`, and the PRD total (sum of `wall_secs`). When the metrics file is missing or has no matching lines (a manual run outside the loop), render `no loop metrics (manual run)` instead — never fail the report.
   - **Implementor Mix (PRD 00019):** render an `### Implementor Mix` subsection from `state.tasks[]` — (1) count attempts by `attempts[].implementor` (`claude`/`qwen`/`gemini`; an attempt row without the field counts as `unknown`); (2) list qwen preflight outcomes by counting non-null `attempts[].preflight_outcome` values per value; (3) count ineligible tasks per `qwen_excluded_reason` (tasks whose `qwen_eligible` is `false` or absent; a missing reason counts as `unknown`). Absent fields (legacy tasks) always count as `unknown` and the render never fails the report — when `state.tasks[]` is missing or empty, render `no implementor data` instead.

7b. Project autonomous decisions into `dev/local/decisions.md` when that opt-in file exists (skip when absent; `audit.md` is written either way). Follow the **"decisions.md Projection"** procedure in `references/audit-log-format.md` — it covers the qualify criterion (label `autonomous` + non-trivial), the row format, dedupe, and the single-source rule.

8. Update the Active Work section of `dev/local/project-capsule.md` with batch progress. Use the Edit tool to replace the Active Work section content:
   ```markdown
   ## Active Work

   ### Batch {batch_id}
   - [x] {completed PRD name} ({n} cycles)
   - [x] ...for each completed PRD in batch
   - [ ] {PRD name} - for each PRD still in wip/ or backlog/

   Observations: {any operational gotchas useful for next iteration}
   ```
   If the capsule doesn't exist yet (catchup was skipped), create a minimal one with just the Active Work section.

9. Print per-PRD summary:

```
── AUTOPILOT ── PRD: {prd-name} ── DONE ── {n} cycles ─────────────

Summary:
- Cycles: {n}
- Autonomous decisions: {count}
- Escalated decisions: {count}
- Follow-up tasks fixed: {count}
```

### Continuation

10. Check: any PRDs remaining in `dev/local/prds/wip/*.md` or `dev/local/prds/backlog/*.md`?
   - **Yes** → run the **Session handoff procedure** (core `SKILL.md` § Session Loop) with the **PRD → PRD** site row. Its state write is this reset: set `phases_completed` to `[]`, `cycle` to `1`, `tasks_total: 0`, `tasks_completed: 0`, clear tasks/task_aborts/`cap_rotations`/autonomous_decisions/deferred_decisions/review_cycles/doubts/`doubts_rubric_verdicts`/`rework_task_ids`/`work_start_sha`/`repo_root`/`design_doc`/`design_gate`/`design_mode`/`pause_reason`/`cap_pause_reason` (the next PRD starts a fresh plan, not a rework dispatch; these are all per-PRD scratch — the next PRD's phases re-derive or overwrite them, and clearing here prevents stale values from surviving if the next PRD aborts before reaching those phases), set `replan_count: 0` (it tracked the current PRD's replans; the next PRD starts fresh). Delete `dev/local/autopilot/replan-context.md` if it exists (defensive — plan-tasks deletes it on success, but a malformed prior session may have left it). **Preserve `batch` field in full, including `batch.catchup_completed_at` and `batch.catchup_head_sha`** — Phase 1 of the next PRD reads these to decide between full catchup and delta refresh. Set `phase: "build"` and `next_phase: "build"` (the next PRD starts the build gate at catchup). Print:
     ```
     ── AUTOPILOT ── {prd-name} done ── next PRD in new session ────────
     ```
     Then **STOP** (end the turn — in loop mode the wrapper reads the non-empty `next_phase: "build"` and launches a fresh session for the next PRD; outside the loop the user re-invokes `/run-autopilot` manually).
   - **No** → print the batch summary below, then branch on loop mode:
     - **Loop mode (`$_AUTOPILOT_LOOP` set) — non-interactive batch end.** The deferred JSON (step 6) and the batch report (step 7) are already written. Set `state.phase = "done"` and `state.next_phase = ""` (empty; nothing more to run), notify the user with the batch counts (PRD 00017: `python3 ~/.claude/hooks/notify.py --send "autopilot 📋 {repo}" "Batch done: {n} done, {m} stalled, {k} deferred. Run /run-autopilot review-batch."` — count stalls from the deferred JSON's `type: "stall"` entries; when both m and k are zero, shorten to "Batch done: {n} PRDs."), print the summary, and END THE TURN. The wrapper reads the empty `next_phase`, archives `state.json` to `reports/{batch_id}-state-final.json`, and stops the loop. Do NOT run the chunked Batch-End Review here — no human is present; it runs later via `/run-autopilot review-batch`.
     - **Outside the loop — interactive batch end.** Run the Batch-End Review presentation below, then set `state.phase = "done"` and `state.next_phase = ""` and STOP. `state.json` stays on disk; the next invocation's batch-identity rollover (Phase 0 step 3) mints a fresh batch.
     ```
     ── AUTOPILOT ── COMPLETE ───────────────────────────────────────────

     Completed {n} PRDs:
       1. {prd-name} ({cycles} cycles)
       2. {prd-name} ({cycles} cycles)
       ...
     ```

### Batch-End Review

Collect ALL pending items from across the batch and present them to the user. Interactively, this is mandatory if any items exist — never exit with items unpresented. In loop mode the batch ends non-interactively (see the branch above) and this presentation runs later via `/run-autopilot review-batch`.

**Source:** `dev/local/autopilot/deferred/{batch_id}-deferred.json` (single source of truth - all items were written here at Phase 9 step 6 of each PRD). Contains four item types:
- `deferred_decision` - issues that failed research or were deferred for other reasons
- `doubt` - unresolved findings from doubt review
- `doubt-overflow` - FIX/VERIFY items deferred when doubt review found >5 issues (present under UNRESOLVED DOUBTS)
- `autonomous_research` - research-backed decisions made autonomously (for user awareness)

**Auto-fix trivial items first.** Before presenting items to the user, scan for trivial fixes that are clearly additive-only: docstring/comment improvements, test helper fixes (missing kwargs, style), formatting. Fix these silently, commit, and remove from the deferred list. Only present items that genuinely need a user decision.

**Presentation format - stalls first, then chunked by PRD (PRD 00017):**

Before any PRD chunk, present the `STALLED PRDS` block when the deferred JSON has `type: "stall"` entries (omit the block entirely when none):

```
── BATCH REVIEW ── STALLED PRDS ({count}) ────────────────────────
1. {prd} — {site}: {detail}
   resume: move back to dev/local/prds/wip/ and re-run
```

Also render `type: "assumed-ambiguity"` records under a visible `ASSUMPTIONS MADE ({count})` heading inside their PRD's chunk (each: the question and the assumption taken) — the human reviews everything the loop decided alone. Omit the heading when there are none.

Present items grouped by PRD, one PRD at a time. For each PRD chunk:

```
── BATCH REVIEW ── PRD: {prd-name} ── {n} items ──────────────────

DEFERRED DECISIONS ({count}):

1. {severity emoji} {issue description}
   Cycle: {n} | Consensus: {consensus}
   Context: {why this was deferred - include research evidence if available}
   File: {path}
   Options: fix now / create issue / ignore

2. ...

UNRESOLVED DOUBTS ({count}):

1. {severity emoji} {doubt description}
   Context: {what the doubt review found and why it matters}
   Options: fix now / create issue / ignore

AUTONOMOUS RESEARCH DECISIONS ({count} - for awareness):

1. {severity emoji} {issue description} -> {action taken}
   Research: {evidence_summary from research field}
   (No action needed unless you disagree)
```

Wait for user decisions on each PRD chunk before showing the next. For "fix now" items, execute the fix before continuing. For "create issue", create a GitHub issue with the context shown.

After all PRD chunks are reviewed (or user says stop), **retain** the deferred JSON — `dev/local/autopilot/deferred/` is durable (the batch's deferred-items record per the Retention contract), so do NOT delete it. Then STOP (the interactive batch-end branch above already set `phase: "done"` and `next_phase: ""`).

If the deferred JSON doesn't exist or is empty, there is nothing to present — skip the presentation and STOP.
