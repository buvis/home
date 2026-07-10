---
name: run-autopilot
description: Use when running a PRD end-to-end autonomously - catchup, plan, work, and a review-rework loop running consensus, blind, and doubt lenses every cycle. Triggers on "autopilot", "run autopilot", "autopilot status", "drain backlog".
argument-hint: "[<prd-filename> | status]"
---

# Autopilot

Orchestrate the full PRD lifecycle: catchup → design → plan-tasks → work → review-rework loop (consensus + blind + doubt lenses, every cycle) → done.

Makes autonomous decisions backed by research (dependencies, recurring issues, API/schema changes when PRD-driven) and pauses only for critical security, requirements ambiguity, or blocking decisions.

## Execution Model

**Run all phases in sequence without stopping.** After each phase completes, immediately update state and proceed to the next phase. Do not pause between phases, do not summarize progress, do not wait for user input - unless the phase explicitly says PAUSE or STOP. Completing a sub-skill invocation (`/catchup`, `/plan-tasks`, `/work`, `/review-work-completion`, etc.) is NOT a stopping point. It is an intermediate step. Continue.

## Entry Points

- `/run-autopilot` — auto-select PRD (wip first, then backlog), run full cycle
- `/run-autopilot <prd-filename>` — full cycle with specific PRD
- `/run-autopilot status` — print current dashboard, no action
- `/run-autopilot review-batch` — interactively review a finished batch's deferred items

If invoked with `status`, read `dev/local/autopilot/state.json`, print phase/cycle/task summary, and stop.

If invoked with `review-batch`, load the newest `dev/local/autopilot/deferred/{batch_id}-deferred.json` and run the "Batch-End Review" presentation (Phase 9) against it — chunked by PRD, wait for user decisions, execute "fix now" items. No state changes; the batch is already closed. Stop when all chunks are reviewed (or the user says stop).

## State Management

All autopilot artifacts live under `dev/local/autopilot/`, organized by type:

```
dev/local/autopilot/
  state.json                              # current cycle state
  last-session.log                        # wrapper-teed output of the last headless session
  reports/{batch_id}-report.md            # batch audit report
  deferred/{batch_id}-deferred.json       # unresolved items across PRDs
```

State file: `dev/local/autopilot/state.json` — see `references/state-schema.md` for schema.

Create `dev/local/autopilot/` and subdirectories if missing. Initialize state file at PRD selection. Update state at every phase transition. Autopilot also keeps a per-PRD **decision audit log** at `dev/local/reviews/<prd-base>-audit.md`, **rendered once at Phase 9 finalize from the `state.json` decision arrays** (`autonomous_decisions`, `deferred_decisions`, `doubts`). `state.json` is the single in-run source of truth — decisions are NOT mirrored to `audit.md` incrementally per decision. Each rendered entry carries a **source** label (`autonomous`, `deferred`, or `doubt`); cycle/phase context goes in the entry body so the Phase 9 `decisions.md` projection can filter autonomous entries by label. Entry format, the Phase 9 render procedure, and the projection live in `references/audit-log-format.md`.

**Invariant:** every state mutation that advances `phase` SHOULD also set `next_phase` to the same value. The three gates are `build` | `review` | `done` (plus `paused`). `build` is ONE session: selection, catchup, design, planning, and work all run under `phase: "build"` with no mid-build handoff. The review surface runs in its own fresh session; blind and doubt scrutiny are LENSES inside every review cycle (Blake and Bob in `review-work-completion`'s roster), not separate phases — reviewers get isolated contexts by construction (subagent prompts, external CLIs). Legacy `blind`/`doubt` phase values in pre-00015 state files map to `review` on resume. Per-task implementor tiering inside `/work` is unchanged. The authoritative resume signal is `phase` + `phases_completed`; build sub-step skipping is by ARTIFACT (capsule freshness, design-doc-exists, tasks-exist, all-done), not by `phases_completed` membership. This resume decision (phase + phases_completed + artifact checks → next step) is encoded canonically in `scripts/resume_target.py`, which `scripts/test_autopilot_resume.py` imports — editing the resume logic there flips a test red rather than silently drifting from this prose.

### Retention

Durable artifacts are the paper trail of a run; they outlive the batch and must survive every cleanup. Disposable artifacts are transient scaffolding. Cleanup — including the user CLAUDE.md "clean up temp files" mandate — defers to this contract: "temp" means the disposable list below and nothing else. Never delete a directory wholesale when it holds durable artifacts; delete disposables by name.

- **Durable** (never delete): `dev/local/prds/done/` and its PRDs, `dev/local/reviews/` (per-cycle review files, blind/doubt reviews, and the `<prd-base>-audit.md` audit renders), `dev/local/designs/` (per-PRD design docs), `dev/local/autopilot/reports/` (batch reports), `dev/local/autopilot/deferred/` (the `{batch_id}-deferred.json` records), `dev/local/autopilot/loop-metrics.jsonl` (the per-session loop metrics, accumulates across batches), and `dev/local/project-capsule.md`.
- **Disposable** (safe to delete by name): `dev/local/tmp/`, `dev/local/autopilot/last-session.log`, `dev/local/autopilot/pause-requested`, `dev/local/autopilot/state.json` (at batch end only — in loop mode the wrapper archives it to `reports/{batch_id}-state-final.json`; see Phase 9), and `dev/local/autopilot/replan-context.md`.

Batch end and any cleanup step enumerate the disposable list explicitly; they never `rm` a durable path or a directory that contains one. This is what keeps a completed PRD's review trail intact after the batch closes (the warden-00011 plugin repos lost `autopilot/` and `reviews/` to an over-broad cleanup).

### Resuming

When `/run-autopilot` is invoked and `dev/local/autopilot/state.json` exists with `batch.completed_prds`, this is a continuation after a session restart. Preserve `batch.completed_prds` (including `batch.id`) and proceed to Phase 0 to pick the next PRD.

Delete `state.pause_reason` from `state.json` if present — unconditional, on every invocation, NOT gated on `batch.completed_prds`. A new session means any pause is being resumed; `pause_reason` belongs only to an unresolved pause and is not overwritten by normal progression, so it must be cleared here or it halts the resumed PRD's next hand-off. Cap-pause detection is unaffected — it keys on `cap_pause_reason`, which this delete does not touch.

### Operator runbook (unattended batches)

All interaction with a running `autoclaude` batch happens at session boundaries — the only safe point:

- **Watch**: `tail -f dev/local/autopilot/last-session.log` — the wrapper tees the live event log of the running headless turn there.
- **Pause**: `touch dev/local/autopilot/pause-requested` — the wrapper consumes the marker at the next session boundary, notifies "paused by operator", and stops the loop with state intact.
- **Take over**: with the loop stopped (pause marker, or Ctrl-C on the wrapper), run `/run-autopilot` in a normal interactive session — resume-by-artifact reads the same `state.json`, and full interactive semantics (questions, PAUSEs) apply because `$_AUTOPILOT_LOOP` is unset. Restart `autoclaude` afterwards to go unattended again.
- **Forensics**: `claude --resume <session-id>` (the id is in the init event at the top of `last-session.log`) reopens a finished headless conversation for questioning. Harmless by construction: sessions are disposable; `state.json` plus the artifacts are the only orchestration contract, so a resumed chat cannot fork the loop.

A running headless turn is never interrupted except by the wrapper's wall-clock cap (`_AUTOPILOT_SESSION_MAX`, default 7200s).

### Task Counts

`tasks_total` and `tasks_completed` are maintained **solely** by the `update-pidash-tasks.py` PostToolUse sync hook (registered on `TaskUpdate` in `settings.json`), which recomputes both from the `state.tasks` snapshot on every `TaskUpdate` — `tasks_total = len(tasks)`, `tasks_completed = count(status == "completed")`. The model does NOT query `TaskList` to mirror counts at each state update; that ceremony is gone. Keep `state.tasks` accurate at phase transitions (the snapshot the hook reads) and the counts follow automatically, keeping the dashboard progress bar live.

### Hydrate TaskList from state.tasks (shared sub-step)

`TaskList` is per-session storage (`~/.claude/tasks/<session-id>/`). Every fresh autopilot session — handoff to a review surface, restart after a context-cap rotation, or any manual re-invocation — starts with an **empty** TaskList even when `state.tasks` carries the full snapshot from the prior session. Phase skipping (planning, work) and per-task model dispatch both rely on TaskList, so without rehydration the new session operates with no task tracker at all.

Run this hydration **before any phase invokes `/work` or queries TaskList for routing** — specifically: Phase 2 (before the skip-rule check), Phase 3 (before `/work`), Phase 6 (before rework `/work`).

**Load if empty.** Query `TaskList`. If it returns **any** tasks, no-op (already populated this session). Otherwise read `state.tasks` from `dev/local/autopilot/state.json`; if absent or empty, no-op (nothing to hydrate). Otherwise, for each entry **in declared order** (do NOT reorder), `TaskCreate(subject: name)`, passing `model` / `estimated_tokens` / `est_context_peak` / `attempts` straight through as `metadata` when present — `/work` reads `metadata.model` (PRD 00025); the rest keep the round-trip lossless. `TaskCreate` assigns ids sequentially from 1, aligning with `state.tasks[].id` by construction. Then `TaskUpdate(status: ...)` each entry to its recorded status (`in_progress` / `completed`; `pending` is the `TaskCreate` default, skip it). The `attempts` array round-trips as-is — the hydration never inspects its rows, so any per-attempt field (`implementor`, `preflight_outcome`, `self_deslop`, future fields) survives the snapshot → hydration → `TaskGet` cycle intact.

**Idempotency:** if a phase re-enters this sub-step on the same session (e.g. Phase 6 after Phase 3), the TaskList-non-empty check short-circuits. Safe to call as a precondition on every `/work` entry point.

### Live Dashboard

The user can run `pidash` (from buvis-gems) in a separate terminal pane to watch progress in real time. It watches `dev/local/autopilot/state.json` automatically — no action needed from autopilot beyond keeping the state file updated.

### Phase Banners

Print a banner at each phase transition:

```
── AUTOPILOT ── PRD: {prd-name} ── Phase: {PHASE} ──────────────────
── AUTOPILOT ── PRD: {prd-name} ── Phase: REVIEW ── Cycle {n} ─────
── AUTOPILOT ── PAUSED ── {n} issue(s) need your decision ──────────
── AUTOPILOT ── PRD: {prd-name} ── DONE ── {n} cycles ─────────────
```

## Phase 0: PRD Selection

### Ensure lifecycle directories exist

Before anything else — before the abort handlers and before PRD selection — create every directory the run will move files into. Idempotent, so it is safe on every invocation (fresh repo, resume, or mid-batch). Run it as its own Bash call:

```bash
mkdir -p dev/local/prds/backlog dev/local/prds/wip dev/local/prds/done dev/local/prds/stalled dev/local/reviews dev/local/tmp dev/local/autopilot/reports dev/local/autopilot/deferred
```

This guarantees the very first `mv` (backlog -> wip below, and later wip -> done at Phase 9, wip -> stalled in recovery) always has a destination directory, so a move can never silently mis-place a PRD for want of a target folder. `mv` does not create destinations; without this step a move into a missing dir renames the PRD to a stray file and the run continues unaware (the warden-00011 failure mode).

### Handle Work-phase abort (from a prior session)

Before anything else, read `dev/local/autopilot/state.json` and check `stall_reason`:

- `stall_reason.stalled` is `"subagent_prompt_overrun"` — the previous session's work aborted from a hook. The PRD is not broken; one task was scoped too big. **Follow `references/recovery.md` → "Work-phase abort: replan procedure"**, then STOP (the next session re-enters `build` at planning). This is the one surviving replan path.
- `stall_reason.stalled` is `"escalation_exhausted"` — Phase 6 owns this inline; seeing it at Phase 0 means a crash landed mid-stall-move. **Follow `references/recovery.md` → "Crash recovery: escalation_exhausted seen at Phase 0"**, then fall through to Normal PRD selection.
- `state.phase == "paused"` AND `state.cap_pause_reason` is set (the previous session's Phase 5 cap-pause behavior fired). The capped PRD is still in `dev/local/prds/wip/`; do NOT treat it as fresh PRD selection. **Follow `references/recovery.md` → "Cap-Pause Resume Handler"** — it presents the recorded unresolved findings and cycle count via the `AskUserQuestion` tool and branches on resume/abandon.
- `state.cap_rotations` has a new entry but none of the above holds — the previous session hit the Work-turn context cap and the cap hook rotated to a fresh session. The cap hook recorded the rotation (appended `cap_rotations`, reset the in-flight task to `pending`, set `next_phase: "build"`); that session then ended its turn and the loop wrapper relaunched on the non-empty `next_phase`. NOT a replan. A `cap_rotations` entry is **informational only** and needs no special handling here: fall through to Normal PRD selection, which resumes `build` by artifact (capsule fresh → skip catchup; tasks exist → skip planning; `/work` continues at the first non-completed task — the rotated task, now reset to `pending`).
- None of the above (neither a recognised `stall_reason` value nor the cap-pause condition `phase == "paused"` + `cap_pause_reason`) — continue with Normal PRD selection below.

### Normal PRD selection

1. If argument provided, find that PRD in `dev/local/prds/wip/` or `dev/local/prds/backlog/`. If found in backlog, `mv` to `wip/`; then **verify the move**: confirm the PRD file now exists in `dev/local/prds/wip/`. If it does not, the `mv` failed — set `state.phase = "paused"` and `state.next_phase = "paused"`, write `state.pause_reason = {"site": "mv_verify", "detail": "<source, destination, and the mv error>"}`, PAUSE naming the source, the destination, and the `mv` error; do not continue.
2. Otherwise, auto-select (never ask the user):
   a. Check `dev/local/prds/wip/`:
      - 1+ found → auto-pick lowest sequence number (by `00XXX-` prefix), announce
   b. If wip is empty, check `dev/local/prds/backlog/`:
      - PRDs available → auto-pick lowest sequence number, `mv` to `wip/`; then **verify the move**: confirm the PRD now exists in `dev/local/prds/wip/`, else set `state.phase = "paused"` and `state.next_phase = "paused"`, write `state.pause_reason = {"site": "mv_verify", "detail": "<source, destination, and the mv error>"}`, and PAUSE naming the source, the destination, and the `mv` error (do not continue)
      - Empty → STOP: "No PRDs found. Create one with /create-prd."
3. Initialize `batch` in state file if not already present: `id: "<yyyymmddHHMM>"` (current timestamp), `mode: "autopilot"`, `completed_prds: []`. **Batch-identity rollover:** if `state.batch` IS already present but the surviving state represents a *genuinely closed* batch — `state.phase == "done"` AND `state.next_phase == ""` (empty) (batch end ran but `state.json` was not deleted, e.g. an abnormal exit before the Stop hook fired) — do NOT inherit the dead batch's id: mint a FRESH `batch.id` (a new `<yyyymmddHHMM>` timestamp) and reset `completed_prds: []`. This is the fix for the stale-id reuse the forensics found, where a `batch.id` minted weeks earlier kept being inherited across genuinely separate batches. **Both conditions are required:** only the batch-end "No more PRDs" branch (Phase 9 step 10) sets `next_phase: ""`, so the empty `next_phase` is what distinguishes a genuinely closed batch from a transient mid-PRD `phase: "done"` — Phase 9 step 2 sets `phase: "done"` with `next_phase: "done"` BEFORE the verified `wip -> done` move, so a move that fails and PAUSEs (or a crash in steps 3-9) leaves `phase == "done"` with `next_phase == "done"` (non-empty), which must NOT roll over (doing so would wipe the in-progress batch's `completed_prds` and mint a spurious id). A normal in-progress resume (`phase` is `build`/`review` — or a legacy `blind`/`doubt`, which maps to `review` — a `paused` handled by an abort handler above, or any `phase == "done"` whose `next_phase` is still non-empty) preserves `batch.id` unchanged.
4. Read the first 20 lines of the selected PRD. If it begins with a `---` line, parse the YAML block between the opening `---` and the next `---`. Look for `catchup:`. Accepted values: `run`, `skip`, `force`. Anything else (other value, malformed YAML, missing frontmatter, absent `catchup:` field) → default to `run`. Write the resulting value to `state.catchup_mode`. Also look for `rework_cap:` in the same YAML block. Accepted values: positive integer (or a string that parses cleanly as a positive integer). Anything else (non-integer string, negative/zero, absent field, malformed YAML, missing frontmatter) → default to **3**. Write the resulting integer to `state.rework_cap`. Also look for `design:` in the same YAML block. Accepted values: `run`, `skip`. Anything else (other value, malformed YAML, missing frontmatter, absent `design:` field) → default to `run`. Write the resulting value to `state.design_mode`. Also look for `design_gate:` in the same block: on an exact `user` match write `"user"` to `state.design_gate`; otherwise (absent field, any other value) leave `state.design_gate` absent. Also look for `doubt_reviewer:` in the same YAML block. Accepted values: `codex`, `fable`. Anything else (other value, malformed YAML, missing frontmatter, absent `doubt_reviewer:` field) → default to `codex`. Write the resulting value to `state.doubt_reviewer` (read by the review phase: `fable` adds Eve to the review batch as a fifth lens; `codex` runs the standard roster). Also look for `pause_on_ambiguity:` in the same YAML block (PRD 00017): an exact `true` → write `state.pause_on_ambiguity = true`; anything else (absent, other value, malformed) → treat as `false` (leave the field absent). In loop mode a `true` makes a requirements ambiguity STALL the PRD instead of being resolved by assumption — it never pauses the batch (see Phase 2). On a malformed-frontmatter fallback, log a one-line warning ("autopilot: PRD frontmatter malformed; defaulting catchup_mode=run, rework_cap=3, design_mode=run, doubt_reviewer=codex") and continue — never crash Phase 0 on a frontmatter problem. PRD frontmatter is the source of truth for catchup behavior; once Phase 0 has set `catchup_mode`, do not re-parse the PRD. Mode semantics: `run` honors the batch-cache check in Phase 1; `skip` bypasses catchup entirely; `force` ignores the batch cache and re-runs full catchup regardless of recency. The `rework_cap` value is consumed by the Phase 5 decision gate's cap check (out of scope here; that's a separate task).
5. Read the Active Work section of `dev/local/project-capsule.md` if it exists. This contains PRD progress and operational context from previous sessions. Use it to inform work in this session.
6. Initialize/update state with selected PRD, preserve `batch` field
7. Print progress:
   ```
   ── AUTOPILOT ── PRD {n}: {prd-name} ─────────────────────────────
   ```
   Where `{n}` = `len(batch.completed_prds) + 1`

## Phase 1: Catchup

**Skip if:** the batch cache is fresh (the batch-cache freshness check below holds — the capsule is already current), OR `state.catchup_mode == "skip"`. The skip is by ARTIFACT (capsule freshness), not `phases_completed` membership.

When skipped via `catchup_mode == "skip"`: do not invoke `/catchup`. Set `state.catchup_mode = "skipped"` (so subsequent re-entries also skip), keep `phase: "build"` and `next_phase: "build"`, and proceed to Phase 1.5 (Design).

Otherwise, decide between **full catchup** and **delta refresh** using the batch cache.

### Batch cache check

The capsule (`dev/local/project-capsule.md`) is the persisted output of catchup: invariants, architecture decisions, GitHub state, project memories. Subsequent phases and their subagents read the capsule when they need that context — not TaskList, not state.json. So between PRDs in the same batch on the same branch, the heavy gather phase of `/catchup` (full diff, blast radius, reverse deps, GitHub state) produces output that's already accurate; re-running it costs ~60-95s and ~50K tokens per PRD with no information gain.

`state.batch.catchup_completed_at` (ISO 8601) and `state.batch.catchup_head_sha` (current branch HEAD when last full catchup completed) record the cache. **Skip the full catchup and run a delta refresh** when ALL of the following hold:

1. `state.catchup_mode != "force"` — PRD frontmatter `catchup: force` overrides the cache.
2. `state.batch.catchup_completed_at` is present AND less than 4 hours old.
3. `state.batch.catchup_head_sha` matches the current `git rev-parse HEAD` on the active branch.

If any condition fails → **full catchup**: invoke `/catchup`. After completion, write `state.batch.catchup_completed_at = <now>` and `state.batch.catchup_head_sha = <current HEAD>`. These fields persist across PRDs in the batch (Phase 9 step 10 preserves them).

If all conditions hold → **delta refresh** (no `/catchup` invocation):

- Re-read all PRDs in `dev/local/prds/wip/` (the active set has changed since last catchup; new PRDs may have entered, old ones moved to `done/`).
- Update the Active Work section of `dev/local/project-capsule.md` with the current PRD list (use the same format Phase 9 step 8 uses). Leave Key Invariants, Architecture Decisions, Component Boundaries, GitHub State, Project Health, and Project Memories untouched — those reflect batch-stable knowledge.
- Print a one-line note: `── AUTOPILOT ── catchup: delta refresh (cache <Xm> old, HEAD <sha7>) ──`

After either path completes, proceed to Phase 1.5 (Design). Stay on `phase: "build"` and `next_phase: "build"`; do NOT add anything to `phases_completed` (build sub-steps skip by artifact, not by membership).

### Frontmatter examples

- `---\ncatchup: skip\n---` → `state.catchup_mode = "skip"`. Phase 1 records mode `skipped` and advances to planning (still `phase: "build"`).
- `---\ncatchup: force\n---` → `state.catchup_mode = "force"`. Phase 1 ignores the batch cache and runs full `/catchup`.
- PRD with no frontmatter → `state.catchup_mode = "run"`. Phase 1 honors the batch cache (delta refresh when fresh, full catchup otherwise).
- `---\ncatchup: invalid\n---` → `state.catchup_mode = "run"`, warning logged.
- `---\ncatchup\n---` (malformed YAML) → `state.catchup_mode = "run"`, warning logged.
- `---\nrework_cap: 5\n---` → `state.rework_cap = 5`. Phase 5 cap check allows 5 review cycles before pausing.
- `---\nrework_cap: abc\n---` → `state.rework_cap = 3`, warning logged. Invalid value falls back to the default.
- PRD with no `rework_cap` field → `state.rework_cap = 3` (default). Phase 5 cap check allows 3 review cycles before pausing.
- `---\ndoubt_reviewer: fable\n---` → `state.doubt_reviewer = "fable"`.
- `---\ndoubt_reviewer: opus\n---` → `state.doubt_reviewer = "codex"`, warning logged. Unrecognized value falls back to the default.
- PRD with no `doubt_reviewer` field → `state.doubt_reviewer = "codex"` (default), no warning (absence is not malformed).

## Phase 1.5: Design (build-gate sub-step)

Between catchup (Phase 1) and planning (Phase 2), in the SAME build session. Design turns the PRD's requirements (the WHAT) into a reviewed implementation design doc (the HOW) before tasks are planned. This is a BUILD-GATE SUB-STEP: `state.phase` stays `"build"`, there is **no** new phase enum value, **no** `phases_completed` entry, and **no** session handoff. The skip is by ARTIFACT (the design doc), exactly like catchup's capsule-freshness skip.

Let `<prd-stem>` = `state.prd` with its trailing `.md` removed. The design doc artifact path is `dev/local/designs/<prd-stem>-design.md`.

**Skip if `state.design_mode == "skip"`:** do not invoke `/design-solution`. Set `state.design_mode = "skipped"`, leave `state.design_doc` unset, and proceed to Phase 2.

**Skip if the artifact already exists:** when `dev/local/designs/<prd-stem>-design.md` is already on disk (a manual `/design-solution` run earlier, or a work-abort replan re-entering the build gate). Log a one-line reuse note (`── AUTOPILOT ── design: reusing existing <prd-stem>-design.md ──`), set `state.design_doc` to that path, then **run the empty-review-log gate (defined below) on this artifact-reuse path** — an existing doc from a manual or aborted run is exactly where a skipped review hides — and proceed to Phase 2 only if the gate passes; do NOT re-invoke the skill. This artifact-based skip is what lets work-abort replans reuse the design with no extra logic.

**Otherwise, run design:**

1. Invoke `/design-solution` with the wip PRD path (`dev/local/prds/wip/<state.prd>`).
2. **On success (exit 0):** set `state.design_doc` to the artifact path it printed (`dev/local/designs/<prd-stem>-design.md`). Log the design decision (chosen approach + any unresolved non-blockers from the doc's `## Review log`) to `state.autonomous_decisions` under the existing audit label `autonomous` — do NOT add a `design` audit label (the audit-log label set is closed). Then **run the empty-review-log gate (defined below) on this success path** before proceeding to Phase 2.
3. **On failure (non-zero exit — unresolved cardinal sins/blockers after 3 reviewer dispatches):** treat as a sub-skill failure. PAUSE per the Error Handling table's "Sub-skill invocation fails outright" row — set `state.phase = "paused"` and `state.next_phase = "paused"`, write `state.pause_reason = {"site": "sub_skill_fail", "detail": "design-solution failed with open findings"}`, report the open findings, and do NOT proceed to planning.

**Empty-review-log gate (both continue paths — the success path above AND the artifact-reuse path).** Before advancing to Phase 2 from either continue path, verify the design doc's `## Review log` actually holds at least one reviewer dispatch summary line: a silently-skipped review leaves it empty, and nothing else checks that the review ran. `design_mode == "skip"` bypasses the empty-review-log gate entirely (no doc exists by design). Otherwise bind `DESIGN_DOC` to `state.design_doc` and run this exact section-scoped check (one `awk`, no pipe, exit-code based — it counts only pinned dispatch-summary lines that appear inside the `## Review log` section, so the design doc's own example lines in `## Interfaces & contracts` cannot false-pass it):

```
awk '/^## Review log/{f=1;next} /^## /{f=0} f && /dispatch [0-9]+ \((claude|codex|claude-fallback)\): cardinal-sin [0-9]+, blocker [0-9]+, non-blocker [0-9]+, question [0-9]+/{hit=1} END{exit !hit}' "$DESIGN_DOC"
```

- **exit 0** (≥1 in-section dispatch summary line) → proceed to Phase 2.
- **exit non-zero** (empty `## Review log` — the review never ran) → treat as a sub-skill failure: set `state.phase = "paused"` and `state.next_phase = "paused"`, write `state.pause_reason = {"site": "sub_skill_fail", "detail": "design doc has empty ## Review log (review never ran)"}`, and do NOT proceed to planning. Surface the remedy: delete the design doc and let Phase 1.5 regenerate it.

The check is deterministic (the pinned `awk` above), NOT a model judgment.

**Design gate (`state.design_gate == "user"`):** after a successful design (or an artifact reuse), and only when `state.design_gate == "user"`, PAUSE before planning — present the design doc summary plus any unresolved non-blockers from `## Review log` via `AskUserQuestion`, and proceed to Phase 2 only after the user answers. This is a mid-turn `AskUserQuestion` PAUSE; it does not end the turn, so no `phase` change is needed.

After design completes (run, skipped, or reused), stay on `phase: "build"` and `next_phase: "build"`; do NOT add anything to `phases_completed` (build sub-steps skip by artifact, not by membership). Then proceed to Phase 2.

### Design frontmatter examples

- `---\ndesign: skip\n---` → `state.design_mode = "skip"`. Phase 1.5 records mode `skipped` and advances to planning (still `phase: "build"`).
- PRD with no `design:` field → `state.design_mode = "run"`. Phase 1.5 invokes `/design-solution` unless the design doc already exists (then it reuses it).
- `---\ndesign: invalid\n---` → `state.design_mode = "run"`, warning logged.
- `---\ndesign_gate: user\n---` → `state.design_gate = "user"`. Phase 1.5 PAUSEs for user review after a successful design, before planning.
- PRD with no `design_gate` field → `state.design_gate` absent; no gate pause.

## Phase 2: Planning

**First, run the "Hydrate TaskList from state.tasks" sub-step** (defined in State Management above). This is mandatory — the skip rule below depends on it. Initial planning has nothing to hydrate (no-ops on empty `state.tasks`) and replan clears `state.tasks` deliberately (also no-ops); the case the hydration covers is a resumed PRD whose prior session populated `state.tasks` and handed off (e.g., a context-cap rotation into a fresh session). Without the hydration, the skip rule below sees an empty TaskList and mistakenly re-runs `/plan-tasks`.

**Skip if:** `TaskList` returns any pending or completed tasks (tasks already exist). Evaluate this **after** the hydration step above completes. This skip is by ARTIFACT (tasks exist), not `phases_completed` membership.

### Replan mode

Before invoking `/plan-tasks`, check for `dev/local/autopilot/replan-context.md`. If present, this is a replan triggered by a Phase 0 abort handler. Pass the file to `/plan-tasks` (see `plan-tasks/SKILL.md` "Replan mode") so it scopes to remaining work and uses the tighter ≤75K per-task budget. `/plan-tasks` deletes the file after successful planning.

If `replan-context.md` is absent, run /plan-tasks normally — first-pass planning for a fresh PRD.

Invoke `/plan-tasks` with the selected PRD.

**PAUSE site - requirements clarification.** When `/plan-tasks` pauses autopilot with a requirements-ambiguity or clarification question:

- **Interactive:** present it to the user and wait for the answer. Once answered, record the clarification and its resolution in `state.autonomous_decisions` (label `autonomous`) so the Phase 9 audit render captures it. Do not write `audit.md` here.
- **Loop mode (`$_AUTOPILOT_LOOP` set, PRD 00017):** never end the batch on an ambiguity. Resolve it by the **simplest safe assumption** (the user's own global rule), record it in `state.autonomous_decisions` as `{"type": "assumed-ambiguity", "question": ..., "assumption": ...}`, AND mirror the same record into the batch deferred JSON so batch-end review shows it under "assumptions made". Exception: when the PRD frontmatter set `pause_on_ambiguity: true` (parsed at Phase 0 step 4), do not guess — stall the PRD instead (`references/recovery.md` → "Loop-mode stall procedure", `site: "clarification"`) and continue the batch. A premise failure is never resolved by assumption either — it always stalls (see `/work`'s premise gate when present).

### Handle plan-tasks stall (oversized task)

`/plan-tasks` exits non-zero with `state.stall_reason.stalled == "oversized_task"` when a task cannot be split below the per-task budget. When this happens, do NOT proceed to Phase 3 — **follow `references/recovery.md` → "plan-tasks stall: oversized task"** (deletes orphan tasks, moves the PRD to `dev/local/prds/stalled/`, advances to the next PRD).

**Other outcomes from `/plan-tasks`:**

- **Exits zero**: no stall. Continue normally to the post-completion state update below.
- **Exits non-zero without `stall_reason`** (or with a `stall_reason.stalled` value other than `"oversized_task"`): treat as a sub-skill failure. PAUSE and report the error per the "Sub-skill invocation fails" entry in the Error Handling table — also write `state.pause_reason = {"site": "plan_tasks_fail", "detail": "<one-line error>"}` alongside `phase="paused"`. Do NOT proceed to Phase 3 or move the PRD.

After completion, query `TaskList` and update state: stay on `phase: "build"` and `next_phase: "build"`, write the `tasks` snapshot (see Phase 3 for format; the sync hook maintains `tasks_total`/`tasks_completed`). Do NOT add anything to `phases_completed`. Flow continues DIRECTLY into Phase 3 (work) in this same session — there is no planning→work handoff.

## Phase 3: Work

**Skip if:** All tasks completed, none pending. Evaluate **after** running the hydration sub-step (below) — otherwise a fresh session sees TaskList empty and mistakenly treats "no pending" as "all done". This skip is by ARTIFACT (all tasks done), not `phases_completed` membership. When all tasks are done, the build is complete → hand off to the review session (see below).

**First, run the "Hydrate TaskList from state.tasks" sub-step** (defined in State Management above). This is the critical entry point for the post-context-cap-rotation session path.

Before invoking `/work`, query `TaskList` and write the full `tasks` snapshot to `dev/local/autopilot/state.json`:
- `tasks`: array of `{"id": "<task-id>", "name": "<title>", "status": "pending|in_progress|completed", ...metadata}` for EVERY task. The snapshot **must preserve every field plan-tasks or Phase 6 may have written** — at minimum: `model` (when set by plan-tasks tier classifier or Phase 6 escalation), `attempts` (the per-attempt log; see "Attempt logging" in `/work`), `estimated_tokens` and `est_context_peak` (when plan-tasks recorded a budget estimate). Stripping these on snapshot would break the hydration round-trip (subsequent sessions read them back into TaskList metadata) and lose Phase 6's tier-escalation history across the handoff. Treat the snapshot as merge-preserving over `state.tasks[i]`, not a three-field replacement.

`tasks_total`/`tasks_completed` are NOT written here — the `update-pidash-tasks.py` sync hook recomputes both from this `tasks` snapshot on every `TaskUpdate` (see "Task Counts" above).

**Include the task `id` field** — the `update-pidash-tasks.py` PostToolUse hook on TaskUpdate matches on it (via `taskId`) to sync status changes and recompute counts. This is mandatory.

**Capture `work_start_sha` before dispatching `/work`, but only if it is unset for the current PRD** (`state.work_start_sha` absent or empty). Run `git rev-parse HEAD` and write the resulting SHA to `state.work_start_sha`. **If it is already set, do NOT re-capture** — a cap-rotation (or any other build re-entry on resume) re-enters the build gate with pending tasks, and the existing value marks the true PRD start; re-capturing the HEAD-at-rotation would shrink the review diff (`work_start_sha..HEAD`) to post-rotation commits only. This bounds the commit range `work_start_sha..HEAD` that this PRD's `/work` dispatches produce — `review-work-completion` uses it as the full-review diff range, so the doubt lens sees the PRD's whole work range. Capture happens **once per PRD** (the unset guard enforces this across cap-rotations and resumes), before `/work` runs. Phase 9 step 10 clears `work_start_sha` on the PRD-to-PRD reset, so the guard is per-PRD correct: each PRD in a multi-PRD batch captures fresh, so ranges never overlap.

**Capture `repo_root` in the same step.** Run `git rev-parse --show-toplevel` in the work repo and write the absolute path to `state.repo_root`. Usually this equals the project root, but when the work repo is nested under a non-git project root (e.g. `~/.claude/skills/run-autopilot` under `~/.claude`), the review session needs it to run `git` (diff gathering, `head_sha` capture) in the right repo. **Bare-repo-backed project root** (the project root has no `.git` of its own because it is tracked by a bare repo with a separate work-tree, e.g. `~/.claude` under the `~/.buvis` bare repo with work-tree `$HOME`): a plain `git rev-parse --show-toplevel` from the project root FAILS, so do NOT default `repo_root` to the project dir (that silently mis-records it every PRD). Record the bare repo's work-tree root instead — `git --git-dir=<bare-git-dir> --work-tree=<work-tree> rev-parse --show-toplevel` (for `~/.buvis`-backed `$HOME` this resolves to `/Users/<you>`).

Invoke `/work` skill. It runs until all tasks complete.

After completion, query `TaskList` again and update state: set `phase: "review"` and `next_phase: "review"`, write the updated `tasks` snapshot (the sync hook maintains `tasks_total`/`tasks_completed`). Do NOT add anything to `phases_completed` here — the `build` gate leaves no membership marker; review-loop convergence is the only `phases_completed` entry.

### Hand off to a fresh session for reviews

After the build completes (all tasks done), do NOT continue into Phase 4 in the same session. The review phases (4, 7, 8) each spawn multiple cloud reviewers and need a clean context window. Hand off by ending the turn (the Session Loop contract):

1. Update `state.next_phase` to `"review"` (the phase the next session will run). The next session resumes at this phase.
2. Print:

```
── AUTOPILOT ── PRD: {prd-name} ── Build complete ──────────────────
── AUTOPILOT ── handing off to fresh session for reviews ───────────
```

3. **STOP.** Do NOT invoke `/review-work-completion`, `/review-blindly`, or `/review-with-doubt` in this session, even if context budget appears sufficient.

**End the turn.** In loop mode the session is headless (`claude -p`): the process exits at turn end, the wrapper reads `state.json` (non-empty `next_phase: "review"`) and launches a fresh session, which resumes at Phase 4 and re-enters `build` only if an artifact is missing (capsule stale, no tasks, or tasks pending). Outside the loop, ending the turn leaves the session interactive and the same resume logic applies on the next manual invocation.

## Phase 4: Review

**Skip the entire review-rework loop if:** `"review"` is in `phases_completed` — the loop already converged in a prior session and handed off (see "Hand off to the finalize session" in Phase 5). Skip Phases 4, 5, and 6, and resume directly at Phase 9.

**Skip this cycle's review if:** A review file exists in `dev/local/reviews/` for the current cycle (filename pattern `{prd-name}-review-{cycle}.md`).

Invoke `/review-work-completion` skill. Every cycle runs ALL lenses (its roster, PRD 00015): Alice (consensus), Blake (blind, PRD-only), Bob (doubt rubric R1-R5 + de-slop; Claude fallback when codex is down), Carl (UI, optional), Diana (optional), plus Eve as a fifth lens when `state.doubt_reviewer == "fable"`. The skill's consolidation records `state.doubts_rubric_verdicts` from Bob's rubric lines (replaced each cycle; the final cycle's verdicts are what Phase 9 renders).

After completion, stay on `phase: "review"` and `next_phase: "review"` (the decision gate is part of the review surface).

## Phase 5: Decision Gate

### Cap check — evaluate after reading review, before rework dispatch

The cap is a gate on REWORK, not on Phase 5 itself. **First, read the review output** (see "Read the review output" further below). If it converged (no unresolved findings remain), the cap is irrelevant — proceed directly to Outcomes "No issues found" → finalize hand-off. The PRD success metric "passes review within three cycles is completely unaffected" requires this: a clean cycle-3 convergence at cap=3 must reach the finalize session, not cap-pause.

Otherwise (unresolved findings remain), before evaluating the Safety Checks table below, check whether the review-rework cycle cap has been reached.

Read `state.cycle` (starts at 1; the number of the review cycle just completed) and `state.rework_cap` (the effective cap, set by Phase 0 from PRD frontmatter — default 3; see Phase 0 step 4).

**Rework is allowed while `cycle < cap`; when `cycle >= cap` AND rework would otherwise be dispatched, the gate pauses instead of reworking.**

Worked example, cap 3:

- cycle 1 review fails → `1 < 3` → rework → cycle 2.
- cycle 2 fails → `2 < 3` → rework → cycle 3.
- cycle 3 fails → `3 >= 3` → **pause, no 4th rework**.
- cycle 3 converges (0 findings) → cap irrelevant → finalize hand-off (no pause).

Cap 5 yields five review cycles before the pause (cycles 1-4 → rework, cycle 5 → pause).

When the cap is hit AND the review did not converge (`state.cycle >= state.rework_cap` AND unresolved findings remain), branch on loop mode (PRD 00017):

- **Loop mode (`$_AUTOPILOT_LOOP` set) — cap-out defers, never pauses.** Any unresolved CRITICAL finding → stall the PRD (follow `references/recovery.md` → "Loop-mode stall procedure", `site: "cap_critical"`) and continue the batch. Otherwise (all unresolved findings ≤ high): append each to `deferred_decisions` as `{"type": "cap-overflow", "issue": ..., "severity": ..., "consensus": ...}`, proceed to the finalize hand-off as converged-with-deferrals, and make the banner name the deferral count (`── cap reached: {k} findings deferred to batch end ──`). Stop polishing, not the batch.
- **Interactive — perform the Cap-pause behavior** (see below) and STOP — do NOT continue into the rest of Phase 5 (no Classification, no Outcomes).

When the cap is NOT hit (or the review converged with no findings), continue with the normal Outcomes flow below.

### Cap-pause behavior

Executed only when the Cap check above fired on the INTERACTIVE branch (`state.cycle >= state.rework_cap` AND the review did not converge AND `$_AUTOPILOT_LOOP` is unset — loop mode defers/stalls instead, per the Cap check). This sub-section is the ONLY writer of the `cap_pause_reason` state field; it is a separate top-level field from `stall_reason` (which has different shapes — `oversized_task`, `subagent_prompt_overrun`, `escalation_exhausted` — and a different lifecycle).

1. **Collect unresolved findings.** Read the current review-cycle output (the same review file Phase 4 produced) and gather every finding that has not yet been resolved by an earlier cycle. Format each finding minimally — at least `{"issue": <description>, "severity": <"critical"|"high"|"medium"|"low">, "consensus": <"N/M">}` — additional fields are allowed.

2. **Write `cap_pause_reason` to `state.json`.** Merge (do NOT replace siblings) the field:
   ```json
   "cap_pause_reason": {
     "cycle": <state.cycle>,
     "cap": <state.rework_cap>,
     "unresolved_findings": [ ... ]
   }
   ```

3. **Set `state.phase` and `state.next_phase`.** Both become `"paused"`. The Phase 0 Cap-Pause Resume Handler (a separate task) is what clears these on resume.

4. **Best-effort dashboard hint (optional).** MAY set `state.needs_attention = true`. This is a hint only — `needs_attention` is dashboard-only state cleared by the `clear-pidash-attention.py` PostToolUse hook on the next tool call, so it does NOT survive and MUST NOT be relied on as the pause indicator. The authoritative cap-pause signal is `phase == "paused"` PLUS `cap_pause_reason` being set (NOT `needs_attention`).

5. **The pause halts the loop by state alone.** Step 3 set `state.phase = "paused"`; the loop wrapper's decision table maps a paused state to "notify the user and stop the loop", leaving `state.json` intact. The user re-invokes `/run-autopilot` to handle the pause.

6. **Print the cap-pause banner:**
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── CAP PAUSE (cycle {n}/{cap}) ─────
   ── {k} unresolved findings — see state.json cap_pause_reason ───────
   ── re-invoke /run-autopilot to resume or abandon ───────────────────
   ```
   Substitute `{prd-name}` from `state.prd` (strip the `.md` extension), `{n}` from `state.cycle`, `{cap}` from `state.rework_cap`, and `{k}` from `len(unresolved_findings)`.

7. **STOP.** Do NOT proceed to Phase 6. Do NOT continue into Classification, Outcomes, or the finalize hand-off sub-section. The paused `state.json` is the durable signal that this PRD is awaiting user action; the Phase 0 Cap-Pause Resume Handler picks it up on the next `/run-autopilot` invocation.

Read the review output. Categorize each finding using `references/decision-framework.md`.

### Safety Checks — evaluate BEFORE classifying individual issues:

| Condition | Action |
|-----------|--------|
| >10 follow-up tasks from review | Interactive: PAUSE (scope alarm — ask user before proceeding). Loop mode (PRD 00017): keep the top 10 by severity, defer the rest to the batch deferred JSON as `{"type": "scope-overflow", ...}`, log one line, and continue — mirroring the doubt >5 overflow rule |
| Issue count not decreasing vs previous cycle | LOG and continue — a steady cycle is not a failure; the Phase 5 rework cap is the backstop |
| Same issue reappearing after previous fix | Route to research-then-decide Protocol B |
| A reviewer or sub-skill errored transiently during this review cycle | LOG and continue using the reviewers/sub-skills that succeeded (graceful degradation - e.g. a quota-exhausted reviewer is skipped, per the review skill). PAUSE only if the cycle cannot complete at all (no reviewer produced parseable output). A single transient error must not break an unattended run. |

### Classification (per finding):

**Auto-fix** (proceed without asking):
- Low severity, any consensus
- Medium severity, clear mechanical fix
- Medium severity, 1/3 consensus
- Any severity where fix is additive only (adds code/tests, doesn't modify signatures/types/schemas)

**Research-then-decide** (run protocol, then auto-fix or defer):
- New dependency needed -> Protocol A from `references/decision-framework.md`
- Recurring issue (appeared in previous cycle) -> Protocol B
- High + data model change -> Protocol C
- High + touches public API -> Protocol D

Execute the research protocol. If verdict is "proceed", treat as auto-fix. If verdict is "escalate", defer to batch end. Log with full `research` field in either case.

**Defer to batch end** (log, don't PAUSE):
- Critical severity, always
- Requirements ambiguity (PRD says X, code does Y)
- Research-failed items (verdict "escalate" from research protocols)

**PAUSE** (present to user, block progress):
- >10 follow-up tasks from review (scope alarm)
- Decision blocks subsequent tasks (e.g. API shape needed before frontend can proceed)
- Data model choice that all remaining work depends on

Log every decision in the state file (`autonomous_decisions` or `deferred_decisions`); note the review cycle (`state.cycle`) in the entry's Decision text. The Phase 9 audit render reads these arrays — do not write `audit.md` here.

### Outcomes:

- **All auto-fixable, no deferrals, no blockers** → proceed to Phase 6
- **Has deferrals but no blockers** → log deferred items to `dev/local/autopilot/deferred/{batch_id}-deferred.json`, proceed to Phase 6 with auto-fixable items only
- **Has blocking escalation** → PAUSE. Present only the blocking issue(s) to user. Wait for decision. After user responds, proceed to Phase 6.
- **No issues found** → the review-rework loop has converged (all lenses, including blind and doubt, passed this cycle). Hand off to the finalize session (see below).

### Hand off to the finalize session

When the review-rework loop has converged (the "No issues found" outcome above), do NOT continue into Phase 9 in this session:

1. Add `"review"` to `phases_completed` — the marker Phase 4 reads to skip the whole review-rework loop on resume.
2. Set `phase` and `next_phase` to `"done"`. The next session runs Phase 9.
3. Print:

```
── AUTOPILOT ── PRD: {prd-name} ── review-rework loop complete ─────
── AUTOPILOT ── handing off to finalize session ────────────────────
```

4. **End the turn.** In loop mode the wrapper reads the non-empty `next_phase: "done"` and launches a fresh session, which skips Phases 4-6 via the loop-level skip in Phase 4 and runs Phase 9. Outside the loop the same resume logic applies on the next manual invocation.

## Phase 6: Rework

**Session model:** Phase 6 runs in the same session as Phase 4 (the `review` surface). The per-task tier escalation in `/work` step 3 (dispatching each task as a separate Agent call at `metadata.model`) means the actual rework implementation runs at the escalated tier (haiku/sonnet/opus) regardless of the outer session. No separate rework handoff is needed: the review session handles review quality; per-task dispatch handles implementation correctness.

Two task kinds enter this phase:

- **Review-flagged original-plan tasks** (`[C{cycle}]` prefix): a task `/work` already attempted that the review phase wants re-done. These are retries — escalate the model tier per the rule below.
- **Decision gate follow-ups** (`[D{cycle}]` prefix): brand-new tasks created from decision gate resolutions. These are first-pass work, not retries — they default to `sonnet` (no escalation applies). Apply the `/plan-tasks` Tier classifier here too if you have the inputs (PRD slice, files-touched estimate); otherwise default `sonnet`.

Both prefixes use the current cycle number. Both kinds dispatch through the same rework-mode `/work` invocation — see "Dispatch rework" below for how each gets its tier set and queued.

### Hydrate before any TaskUpdate (PRD 00025)

**Run the "Hydrate TaskList from state.tasks" sub-step** (defined in State Management above) BEFORE the "Escalate review-flagged tasks by tier" section's `TaskUpdate` calls. The rework session almost always inherits an empty TaskList from the post-Phase-3 handoff — running escalation TaskUpdate calls against an empty tracker either errors on unknown IDs or silently no-ops, losing the status→pending transition and dashboard visibility. Hydration is the first action of Phase 6, no exceptions.

### Escalate review-flagged tasks by tier (PRD 00025)

**Escalation caveat — diagnose the failure before escalating.** The tier chain
`haiku → sonnet → opus` assumes a review failure means the model wasn't capable
enough. That is often wrong. A review failure caused by a **spec-transmission
gap** — the implementer built a self-consistent *wrong* thing because the task
description never carried the PRD's exact contract (field names, enum values,
hook kind, thresholds) — is not a capability failure. Escalating the tier costs
more and does not address the cause: a stronger model fed the same thin task
description can fail the same way. Before escalating, look at the cycle's review
findings. If they are predominantly spec-misread (wrong schema, wrong API,
missing feature, wrong artifact kind) rather than implementation-quality bugs
(edge cases, perf, logic errors), the real fix is a **corrected task
description** — and the review's follow-up tasks should already carry the exact
contract verbatim. In that case keep the **same tier**; do not escalate. Record
the decision and rationale in `autonomous_decisions` (the Phase 9 audit render reads it). Escalate the tier only
when the prior attempt genuinely struggled on a correctly-specified task. (Root
cause of the original gap: `plan-tasks` must copy the PRD's contract and
acceptance criteria verbatim into each task — see `plan-tasks/SKILL.md` step 4.)

For each review-flagged original-plan task in the current cycle's review output:

1. Look up `state.tasks[i].attempts[-1]` — the last `/work` pass's entry, written by `/work` Attempt logging.
2. If `state.tasks[i].attempts` is empty or absent (legacy-plan task with no attempt log — covered by step 3's "no prior attempt" case and the closing paragraph after step 5), skip this step entirely and proceed to step 3's next-tier computation. Otherwise, rewrite that entry's `outcome` to `"review_flagged"` (it was `"completed"` when `/work` exited; review just flagged it).
3. Compute the next tier in the chain `haiku → sonnet → opus`:
   - **no prior attempt** (`state.tasks[i].attempts` empty or absent — covers both pre-PRD-00025 legacy plans and PRD-00025 tasks that crashed before the first attempt log wrote) → treat as `"sonnet"`; next is `"opus"`. **Metric caveat**: when this branch fires for a PRD-00025 task whose actual pass ran `haiku`, it inflates the apparent sonnet→opus escalation rate vs the PRD's ≤2% target. The branch is rare (crash before first attempt-log write) and the conservative jump-to-opus is the right correctness choice; just don't read sonnet→opus telemetry without accounting for it.
   - last attempt at `"haiku"` → next is `"sonnet"`
   - last attempt at `"sonnet"` → next is `"opus"`
   - last attempt at `"opus"` → **escalation exhausted**: the `haiku → sonnet → opus` chain has no higher tier, so the task cannot be reworked automatically. Do NOT continue to step 4 — **follow `references/recovery.md` → "Rework escalation exhausted"** (rewrites the last attempt's `outcome` to `"rework_failed"`, moves the PRD to `dev/local/prds/stalled/`, advances to the next PRD).
4. Otherwise (chain not exhausted), persist the escalated tier in BOTH places so `/work` and the state snapshot stay in sync, then queue the task for rework:
   - `TaskUpdate(taskId="<id>", metadata={"model": "<next_tier>"})` — canonical source `/work` reads via `TaskGet` (see `work/SKILL.md` "Per-task model dispatch").
   - Write the same value to `state.tasks[i].model` — the snapshot the dashboard and the next review cycle read.
   - Append the task ID to `state.rework_task_ids` (create the array if absent).
5. Reset `state.tasks[i].status` back to `"pending"` via `TaskUpdate(taskId, status="pending")` so `/work` will iterate it again. **Reverse status transitions (`completed` → `pending`) are supported** — the hydration sub-step (State Management above) relies on the same mechanism to restore `completed` status on a fresh session, and the PostToolUse status-sync hook treats whatever `TaskUpdate` writes as the new ground truth.

The "no prior attempt" case in step 3 covers both pre-PRD-00025 legacy plans (which lack `metadata.model` and `attempts[]` entirely) and PRD-00025 tasks that crash before the first attempt log writes (rare but possible). Both are treated as `"sonnet"` for the next-tier computation, so first escalation goes to `"opus"`.

### Dispatch rework

Build the rework batch from two sources:

1. **Review-flagged `[C{cycle}]` tasks** — `state.rework_task_ids` already contains their IDs (appended in step 4 above), and their `metadata.model` + `state.tasks[i].model` already carry the escalated tier.
2. **Decision gate `[D{cycle}]` follow-ups** — for each new task created from a decision gate resolution:
   - Compute the tier: start with the `/plan-tasks` Tier classifier output if the inputs are available (PRD slice, files-touched estimate); otherwise default to `sonnet`. Then apply the **PRD `default_model` floor** the same way `/plan-tasks` step 4.7 does: `final_tier = max(tier, default_model)` — a PRD with `default_model: opus` must produce `opus` for every `[D]` follow-up, never a lower tier. **Reading `default_model` at Phase 6 runtime:** re-parse the PRD frontmatter from `dev/local/prds/wip/<state.prd>` using the same YAML-tolerant parse Phase 0 step 4 applies for `catchup:`. Look for `default_model:`. Accepted values: `haiku`, `sonnet`, `opus`. Behavior matches `/plan-tasks` step 4.7 exactly: absent frontmatter or unset `default_model:` → no override (silent; classifier output passes through); malformed YAML or invalid value → no override AND log a one-line warning, then classifier output passes through; valid value → apply `final_tier = max(tier, default_model)`. `default_model` is intentionally NOT persisted to state — the PRD frontmatter is the single source of truth.
   - `TaskCreate(metadata={"model": final_tier, ...})`.
   - Append the new task's ID to `state.rework_task_ids` AND insert a merge-preserving snapshot into `state.tasks[]` carrying `{id, name, status, model}` plus any classifier-produced fields (`estimated_tokens`, `est_context_peak`) — same merge-preserving rule Phase 3 establishes for the original-plan snapshot. The dashboard sees the new task and `/work` rework mode iterates it.

Hydration already ran at the top of Phase 6 (see "Hydrate before any TaskUpdate" above) — the rework session inherits a populated TaskList by this point, so the `TaskUpdate` and `TaskCreate` calls operate on real tasks.

After both sources are merged into `rework_task_ids`, update state (the sync hook maintains the task counts). Invoke `/work` — it reads `state.rework_task_ids` and enters **rework mode** (see `work/SKILL.md` "Rework-mode task filter"), processing only the listed IDs at the tier each task carries in `metadata.model`; non-listed completed tasks are skipped.

The work skill may parallelize independent rework tasks when `superpowers:dispatching-parallel-agents` is available (see work skill's "Parallel dispatch for independent rework fixes").

### After /work returns

1. Clear `state.rework_task_ids` (set to `[]`).
2. **Increment `state.cycle` and persist it to `state.json` in this step** (a durable write, not an in-memory bump). The Phase 5 cap-pause gate (`state.cycle >= state.rework_cap`) reads `state.cycle`; skipping the persisted increment blinds it. On warden 00020 the review loop ran cycles 1-3 but never persisted the bump, so `state.cycle` stayed 1 and cap-pause never fired. This write is not optional.
3. Update state: set `phase: "review"` and `next_phase: "review"`. Do NOT rewrite `state.tasks` here — `/work` already wrote `attempts[]` entries directly to `state.tasks` during rework, and a bare TaskList snapshot would strip them; the sync hook keeps `tasks_total`/`tasks_completed` current.
4. Loop back to Phase 4.

Cross-references: `references/state-schema.md` (`rework_task_ids`, `tasks[].model`, `tasks[].attempts`, `stall_reason` shapes); `work/SKILL.md` Per-task model dispatch, Attempt logging, Rework-mode task filter.




## Phase 9: Completion

1. **Commit history is left as-is.** Autopilot does NOT rewrite the PRD's commit history. The former cherry-pick regroup engine never pushed — it only churned local history the user re-reviewed before pushing anyway — so it was pure risk (conflict aborts, backup branches) for no shipped benefit. The user squashes/groups commits manually before pushing.

2. Update state: set `phase: "done"` and `next_phase: "done"`
3. Move PRD from `wip/` to `done/` (use `mv`, keep `00XXX-` prefix); then **verify the move**: confirm the PRD now exists in `dev/local/prds/done/`. If it does not, the `mv` failed — set `state.phase = "paused"` and `state.next_phase = "paused"`, write `state.pause_reason = {"site": "mv_verify", "detail": "<source, destination, and the mv error>"}`, PAUSE naming the source, the destination, and the `mv` error, and do not continue (do not append to `completed_prds` or advance to the next PRD with the PRD in the wrong folder)
4. Append completed PRD to `batch.completed_prds` in state file
5. Delete all tasks from the completed PRD: query `TaskList`, mark every task as `deleted` via `TaskUpdate`. This prevents stale tasks from triggering Phase 2's skip logic on the next PRD.
6. Append items to `dev/local/autopilot/deferred/{batch_id}-deferred.json` (create if missing). Collect from the current state file:
   - `deferred_decisions` with status `"pending"` or `"deferred"` -> type `"deferred_decision"` (preserve original `type` field if present, e.g. `"doubt-overflow"`)
   - `doubts` with status `"pending"` -> type `"doubt"`
   - `autonomous_decisions` with `research` field -> type `"autonomous_research"` (for user awareness at batch end)
   Each entry gets tagged with `prd` (filename) and `cycle`. Preserve the full `research` field when present - this is the only copy that survives state reset. Skip this step if nothing to write.
6a. **Render this PRD's audit file** `dev/local/reviews/<prd-base>-audit.md` (`<prd-base>` = PRD filename without `.md`) ONCE from the state decision arrays — this is the ONLY writer of `audit.md`. Write in a single pass (Write tool): a header (PRD, started/completed timestamps, counts `autonomous N | deferred N | doubts N`), then one entry per item in `state.autonomous_decisions` (label `autonomous`), `state.deferred_decisions` (`deferred`), and `state.doubts` (`doubt`), using the entry format in `references/audit-log-format.md`. When all three arrays are empty, write the header plus a single `no decisions recorded` line.

7. Append PRD summary to the batch report, whose filename is built from the current `state.batch.id`: `dev/local/autopilot/reports/{state.batch.id}-report.md` (create with header if missing). **Invariant — before appending, verify the target filename's id matches the batch.id** held in `state.batch.id`; they are identical by construction. Never glob `reports/*.md` to choose a file, and never append to a report whose id differs from `state.batch.id` — a mismatch is a batch-identity error; create a fresh `{state.batch.id}-report.md` instead. See `references/batch-report-format.md` for format. **Doubt Rubric Verdicts (PRD 00038):** render `state.doubts_rubric_verdicts` one row per rule; when entries carry `source` (a dual-reviewer `doubt_reviewer: fable` run — one entry per rule per reviewer), combine both reviewers into a single row per rule — `| R1 | pass (codex) / pass (fable) |` (a per-reviewer `fail` still shows, e.g. `| R3 | pass (codex) / fail (fable) |`). When no entry carries `source` (single-reviewer / legacy state), render UNCHANGED — one verdict per rule, no source suffix (`| R1 | pass |`). **Loop Metrics (PRD 00013):** render a `### Loop Metrics` subsection from `dev/local/autopilot/loop-metrics.jsonl` — read the lines whose `prd` matches `state.prd` AND whose `batch` matches `state.batch.id`, then report the session count, wall seconds grouped by `phase_launched`, and the PRD total (sum of `wall_secs`). When the metrics file is missing or has no matching lines (a manual run outside the loop), render `no loop metrics (manual run)` instead — never fail the report. See `references/batch-report-format.md`.
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
   - **Yes** → reset state for next PRD: set `phases_completed` to `[]`, `cycle` to `1`, `tasks_total: 0`, `tasks_completed: 0`, clear tasks/task_aborts/`cap_rotations`/autonomous_decisions/deferred_decisions/review_cycles/doubts/`doubts_rubric_verdicts`/`rework_task_ids`/`work_start_sha`/`repo_root`/`design_doc`/`design_gate`/`design_mode`/`pause_reason`/`cap_pause_reason` (the next PRD starts a fresh plan, not a rework dispatch; `cap_rotations`, `work_start_sha`, `repo_root`, and `doubts_rubric_verdicts` are per-PRD scratch — Phase 3 of the next PRD overwrites `work_start_sha` and `repo_root`, the review phase's consolidation overwrites `doubts_rubric_verdicts`, but clearing here prevents stale values from surviving if the next PRD aborts before reaching those phases; the design fields are likewise per-PRD scratch — Phase 0 re-derives `design_mode`/`design_gate` from the next PRD's frontmatter and Phase 1.5 re-sets `design_doc`, cleared here so a skipped or aborted next PRD can't inherit them), set `replan_count: 0` (it tracked the current PRD's replans; the next PRD starts fresh). Delete `dev/local/autopilot/replan-context.md` if it exists (defensive — plan-tasks deletes it on success, but a malformed prior session may have left it). **Preserve `batch` field in full, including `batch.catchup_completed_at` and `batch.catchup_head_sha`** — Phase 1 of the next PRD reads these to decide between full catchup and delta refresh (see Phase 1 "Batch cache check"). Set `phase: "build"` and `next_phase: "build"` (the next PRD starts the build gate at catchup). Then end the turn — in loop mode the wrapper reads the non-empty `next_phase: "build"` and launches a fresh session for the next PRD; outside the loop the user re-invokes `/run-autopilot` manually. Print:
     ```
     ── AUTOPILOT ── {prd-name} done ── next PRD in new session ────────
     ```
     Then **STOP**.
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

     Before any PRD chunk, present the `STALLED PRDS` block when the deferred
     JSON has `type: "stall"` entries (omit the block entirely when none):

     ```
     ── BATCH REVIEW ── STALLED PRDS ({count}) ────────────────────────
     1. {prd} — {site}: {detail}
        resume: move back to dev/local/prds/wip/ and re-run
     ```

     Also render `type: "assumed-ambiguity"` records under a visible
     `ASSUMPTIONS MADE ({count})` heading inside their PRD's chunk (each:
     the question and the assumption taken) — the human reviews everything
     the loop decided alone. Omit the heading when there are none.

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

## Session Loop

Unattended mode runs each session headless: the `autoclaude` wrapper (in `~/.config/bash/plugins/development.plugin.bash`) launches `claude -p "/run-autopilot"`, the session runs exactly one turn, and the process exits at turn end. There is no signal file and no Stop-hook choreography — **`state.json` is the entire hand-off contract**.

**Hand-off = write state, print banner, end the turn.** After the process exits, the wrapper reads `state.json` and branches:

1. `pause_reason` set or `phase == "paused"` → notify the user with the pause detail, stop the loop, state left intact.
2. `stall_reason.stalled == "subagent_prompt_overrun"` (set by `/work`'s Subagent Dispatch Budget when an assembled subagent prompt exceeded 50K after one trim pass; `/work` also appends to `state.task_aborts`) → continue the loop; Phase 0 of the next session replans the PRD in place (PRD stays in `wip/`; see Phase 0 step 1's replan procedure). This is the one surviving replan path.
3. `next_phase == ""` (empty) → backlog drained: the wrapper archives `state.json` to `reports/{batch_id}-state-final.json`, notifies, and stops the loop.
4. `next_phase` non-empty → relaunch a fresh session, which resumes from state by artifact — capsule fresh → skip catchup, tasks exist → skip planning, `/work` continues at the first non-completed task.
5. `state.json` missing, unreadable, or untouched by the session → usage-limit check against the captured session log (`last-session.log`; a live limit means sleep-until-reset and continue), else notify "died" and stop loud.

A Work-turn context-cap overrun is just branch 4: `autopilot_context_cap_hook.py` records the rotation (appends to `state.cap_rotations`, resets the in-flight task to `pending`, sets `next_phase: "build"`), the turn ends, and the fresh session resumes `build` by artifact — NO replan.

The model's only job at a hand-off is to write `state.next_phase` (and `phase`/`stall_reason`) accurately, print the banner, and end the turn. The model never writes any signal and never inspects the wrapper's decision table — writing accurate state IS the hand-off. Interactive (non-loop) semantics are identical minus the wrapper: the same state writes happen, and the user re-invokes `/run-autopilot` manually.

**End the turn only at a real hand-off.** A phase is complete only when its artifacts are written and `state` is advanced (`phases_completed` updated, `next_phase` set). Dispatched work — `Agent` calls and background Bash — returns its results **within the same headless turn**: the harness re-invokes you with each `<task-notification>` before the turn can end, so dispatch, overlap independent work, wait for the results, and finish the phase. Do not end the turn to "wait for" something you dispatched.

An idle end-of-turn (phase unfinished, nothing pending) no longer thrashes anything — the wrapper relaunches and the next session resumes the phase by artifact (self-healing) — but it burns a session start, so treat it as waste, not as a mechanism.

For long **Bash** (builds, tests), still prefer the FOREGROUND with an explicit `timeout` (up to 600000 ms) so the result is in hand directly. If genuine work cannot finish in this session, that is a PAUSE (`phase: "paused"` + `state.pause_reason = {"site": "work_incomplete", "detail": "<what could not finish>"}` + end turn), not a silent idle stop.

### Loop Detection

The `autoclaude` wrapper exports `_AUTOPILOT_LOOP=$$` before launching each headless session. Skills branch on it for loop-mode behavior only — the `AskUserQuestion` ban (Error Handling), git-push deferral, notify suppression in `~/.claude/hooks/notify.py`. Hand-off sites do NOT check it: the state writes are the same in and out of the loop.

**Review-file gate (in-session quality gate).** `review_coverage_hook.py` stays registered on Stop: at the done hand-off, when the saved review file is missing or fails the `check_review_file.py` shape check (missing reviewer section, verdict, or tests line — PRD 00016), it exit-2-blocks the turn's end and feeds the gap back to the model so the review can be finished before the turn ends. Exit-2 Stop-hook blocking works in `-p` mode (proven by the 00014 spike, probe (c) — `dev/local/tmp/00014-headless-spike.md`). This is a completeness gate on review artifacts, not loop orchestration.

**Wrapper sketch** (the real `autoclaude` adds the memory circuit-breaker, the session wall-clock cap, orphan cleanup, metrics, and notifications):

```bash
while true; do
  [ -f dev/local/autopilot/pause-requested ] && break   # operator pause
  WARDEN_UNATTENDED=1 claude -p "/run-autopilot" 2>&1 | tee dev/local/autopilot/last-session.log
  # read state.json and branch: paused → stop; stall → continue (replan);
  # next_phase "" → archive state, stop (drained); next_phase set → continue;
  # state missing/untouched → usage-limit check, else stop loud (died)
done
```

### De-slop is part of the doubt lens

There is no separate between-session de-slop pass. The standalone codex pass that
once ran from the `autoclaude` wrapper after every commit was removed: it was an
unconditional external call that fell silently dead when codex hit its usage
limit. De-slopping now happens **inside every review cycle** — Bob (codex)
carries the doubt + de-slop lens in the `review-work-completion` roster, with a
Claude fallback when codex is unavailable, so the lens never silently drops. If
you are checking how de-slop is wired, look at the review roster, not the
`autoclaude` function.

## Shell Command Rules

- **Never chain commands** with `&&`, `|`, or `;` in a single Bash call. Use separate Bash tool calls instead.
- **Never use redirections** like `2>/dev/null`. Handle missing files by checking existence or catching errors in the tool result.
- Use `Glob` or `Read` instead of `ls` where possible (e.g. to check if files exist or list directory contents).
- Use `mkdir -p` in its own Bash call when creating directories.

## Error Handling

| Situation | Interactive | Loop mode (`$_AUTOPILOT_LOOP` set, PRD 00017) |
|-----------|-------------|------------------------------------------------|
| Sub-skill invocation fails outright (no usable result; the phase cannot proceed) | PAUSE, report which skill failed and error. A transient reviewer/sub-skill error *during the review-rework cycle* is the Phase 5 Safety Checks row's domain instead (graceful degradation, not a PAUSE). | Re-invoke the sub-skill ONCE; if it fails again, stall the PRD (`recovery.md` → "Loop-mode stall procedure", `site: "sub_skill_fail"`) and continue the batch |
| No PRDs anywhere | STOP with message about /create-prd | Write `state.phase = "done"` and `state.next_phase = ""` first so the wrapper stops as drained, not died |
| State file corrupted | Delete it, restart from Phase 0 | Same (in-session recovery, no pause) |
| Review produces no parseable output | PAUSE, report — don't retry | Re-run the review ONCE; still unparseable → stall the PRD (`site: "reviewer_fail"`), continue the batch |
| All reviewers fail | PAUSE, report — partial results usable if user confirms | Re-invoke ONCE; still nothing → stall the PRD (`site: "reviewer_fail"`), continue the batch |
| `dev/local/` doesn't exist | Create it | Same |
| Task tools unavailable | STOP, report — can't operate without tasks | Same (a broken harness is not a per-PRD failure) |
| Git push fails (auth, locked signing agent, network) | Report and let the user retry | Log to `deferred_decisions[]`, leave the commits local (the user pushes manually per Phase 9), CONTINUE — a locked signing agent on an unattended host is expected (it stalled the loop 145 min on 2026-06-15) |
| `mv` verify fails (backlog→wip, wip→done, wip→stalled) | PAUSE per the mv-verify sites | Retry the `mv` ONCE after re-running `mkdir -p`; persistent failure is one of the two sanctioned loop stops below |
| **Security-critical finding** (exposed secret, vulnerability being shipped) | PAUSE | **PAUSE — sanctioned loop stop #1** (set `phase: "paused"` + `pause_reason`; the wrapper notifies and halts) |
| **Detected data-loss risk** | PAUSE | **PAUSE — sanctioned loop stop #2** (same mechanics) |

**Loop mode has exactly two turn-ending PAUSEs — the two sanctioned rows above (plus the mv-retry exhaustion, which resolves into the same loud stop). Everything else stalls the PRD or defers and continues.** Future edits to this table must not re-grow the loop-mode PAUSE list.

**Turn-ending PAUSE rows must set `state.phase = "paused"` (and `state.next_phase = "paused"`) before stopping, and must also write `state.pause_reason = {"site": "<slug>", "detail": "<one-line human string>"}`.** `pause_reason` is a durable marker so the loop halts even if the model forgets `phase="paused"`; unlike `phase` it is not overwritten by normal progression, so it must be cleared on resume (see `### Resuming` cleanup). Without it the wrapper — seeing a non-empty `next_phase` — would take its continue branch and relaunch the failed phase instead of stopping for you to intervene; a paused state is the wrapper's stop-and-notify branch (Session Loop branch 1), and the wrapper surfaces `pause_reason.detail` in its notification. This applies to "Sub-skill invocation fails outright" (`pause_reason.site = "sub_skill_fail"`), "Review produces no parseable output" (`"reviewer_fail"`), and "All three reviewers fail" (`"reviewer_fail"`). Exceptions that need no `phase` change: "State file corrupted" (delete it and restart from Phase 0 in the same session; the freshly-written state is what the wrapper reads at turn end) and "No PRDs anywhere" (see its row — the drained state write covers the loop). PAUSE sites that ask via `AskUserQuestion` mid-turn (Phase 2 clarification, Phase 5 blocking escalation and scope alarm) do NOT end the turn and need no `phase` change — **but only outside the loop. When `$_AUTOPILOT_LOOP` is set there is no human to answer: these sites MUST NOT call `AskUserQuestion`. Instead set `state.phase = "paused"` (and `state.next_phase = "paused"`) and write `state.pause_reason` (Phase 2 clarification → `{"site": "clarification", "detail": "..."}`; Phase 5 blocking escalation → `{"site": "blocking_escalation", "detail": "..."}`; Phase 5 scope alarm → `{"site": "scope_alarm", "detail": "..."}`), print the PAUSE banner, and end the turn, so the loop halts cleanly and the user resolves it on the next manual `/run-autopilot` (see `references/decision-framework.md` → "Autonomy in loop mode"). A mid-turn question on the unattended path stranded the loop 31 min and 145 min on 2026-06-15.**

## Superpowers Integration

Autopilot depends on superpowers for quality gates. All integrations are conditional - autopilot works without them, but quality improves with them.

### Used by the Work skill (Phases 3 and 6)

| Superpower | Step | Purpose |
|-----------|------|---------|
| `test-driven-development` | 2.7 | Write failing tests before implementation |
| `systematic-debugging` | 4.5 | Root-cause analysis on errors |
| `verification-before-completion` | 5.5 | Run test suite before marking done |
| `requesting-code-review` | 5.7 | Per-task code review after commit |
| `receiving-code-review` | 5.7 | Evaluate review feedback before acting on it |

### Used in Phase 6 (Rework)

| Superpower | Condition | Purpose |
|-----------|-----------|---------|
| `dispatching-parallel-agents` | 2+ independent rework tasks | Parallelize isolated review fixes |

### Not used (rationale)

| Superpower | Reason |
|-----------|--------|
| `brainstorming` | Interactive; happens before PRD exists |
| `writing-plans` | PRD is the plan; plan-tasks decomposes into tasks |
| `executing-plans` | Work skill manages per-task dispatch already |
| `subagent-driven-development` | Work skill's loop serves same purpose |
| `finishing-a-development-branch` | Autopilot works on current branch, not worktrees |
| `using-git-worktrees` | Separate architectural concern |
| `using-superpowers` | Session-start meta-skill; autopilot is autonomous, not conversational |
| `writing-skills` | Meta-skill for creating skills, not a workflow gate |

### Note on review layering

Per-task review (step 5.7) and the Phase 4 lens battery (consensus, blind, doubt — every review cycle) are complementary, not redundant. Per-task catches issues early before they compound. The consensus lens catches cross-task coherence and integration issues. The blind lens catches spec drift and gaps that implementation-aware reviewers miss by giving a fresh agent only the spec. The doubt lens hunts residual findings and slop a confident reviewer waves past. All are needed.

Per-task review is **tier-gated** (PRD 00044): `/work` step 5.7 dispatches the per-task code reviewer only for `sonnet`- and `opus`-tier tasks; `haiku`-tier tasks skip it (as does the opus-only Devon adversarial dispatch at step 2.85). This does not leave haiku-tier work unreviewed — the mandated PRD-level lens battery (consensus, blind, doubt) reviews every task's diff regardless of tier, so it covers haiku-tier tasks that skipped the per-task layer. The gate drops only the per-task layer on the cheapest tier while keeping the mandated lenses byte-untouched.

## Reference Files

- `references/state-schema.md` — state file JSON schema and skip logic
- `references/decision-framework.md` — auto-fix vs escalate classification rules
- `references/recovery.md` — rare-path handlers: Work-phase abort/replan, plan-tasks stall, escalation-exhausted
- `references/dashboard-format.md` — live dashboard via pidash
- `references/batch-report-format.md` — batch audit report format
