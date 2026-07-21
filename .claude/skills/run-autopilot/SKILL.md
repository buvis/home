---
name: run-autopilot
description: Use when running a PRD end-to-end autonomously - catchup, plan, work, and a review-rework loop running consensus, blind, and doubt lenses every cycle. Triggers on "autopilot", "run autopilot", "autopilot status", "drain backlog".
argument-hint: "[<prd-filename> | status]"
---

# Autopilot

Orchestrate the full PRD lifecycle: catchup → design → plan-tasks → work → review-rework loop (consensus + blind + doubt lenses, every cycle) → done.

Makes autonomous decisions backed by research (dependencies, recurring issues, API/schema changes when PRD-driven) and pauses only for critical security, requirements ambiguity, or blocking decisions.

## Dependencies

- Personal skills (invoked as phases): `design-solution`, `plan-tasks`, `work`,
  `review-work-completion`
- Plugin skills: `git-ferry:catchup` (Phase 1, unless the PRD sets `catchup: skip`)
- Files read from other skill dirs:
  `~/.claude/skills/review-work-completion/scripts/await_reviewer_outputs.py`
  (Watcher keep-alive)
- Hooks outside the skill dir: `~/.claude/hooks/notify.py`
- Shell wrapper outside `~/.claude`: `autoclaude` in
  `~/.config/bash/plugins/development.plugin.bash` - the unattended session loop
- Scripts (own dir, model-invoked as a CLI): `scripts/statectl.py` — the sole
  `state.json` mutator (`get`/`set`/`append`/`del`; atomic, advisory-locked,
  one rotating `.bak`)
- CLIs: `claude` (headless `-p`), `python3`, `git`, `awk`
- Optional: `tracon` (`scripts/tracon/`; the default `autoclaude` front-end since PRD 00062, `_AUTOPILOT_TRACON=0` or no tty/`uv` falls back to `render_stream.py`) - dashboard only, absence changes nothing

## Execution Model

**Run all phases in sequence without stopping.** After each phase completes, immediately update state and proceed to the next phase. Do not pause between phases, do not summarize progress, do not wait for user input - unless the phase explicitly says PAUSE or STOP. Completing a sub-skill invocation (`/catchup`, `/plan-tasks`, `/work`, `/review-work-completion`, etc.) is NOT a stopping point. It is an intermediate step. Continue.

## Entry Points

- `/run-autopilot` — auto-select PRD (wip first, then backlog), run full cycle
- `/run-autopilot <prd-filename>` — full cycle with specific PRD
- `/run-autopilot status` — print current dashboard, no action
- `/run-autopilot review-batch` — interactively review a finished batch's deferred items

If invoked with `status`, read `dev/local/autopilot/state.json`, print phase/cycle/task summary, and stop.

If invoked with `review-batch`, load the newest `dev/local/autopilot/deferred/{batch_id}-deferred.json` and run the "Batch-End Review" presentation (`references/phase-done.md`) against it — chunked by PRD, wait for user decisions, execute "fix now" items. No state changes; the batch is already closed. Stop when all chunks are reviewed (or the user says stop).

## Gate Dispatch

The full per-phase instructions live in three gate reference files; this core deliberately carries only the shared contract plus the invariants below. After the entry-point checks, read `dev/local/autopilot/state.json` and **Read the matching gate file now; do not execute a gate from memory**:

| resume state | Read this gate file |
|--------------|---------------------|
| `phase: "build"` — or `state.json` missing (fresh start) | `references/phase-build.md` |
| `phase: "review"` — or a legacy `"blind"`/`"doubt"` value (pre-00015 state), which maps to `review` | `references/phase-review.md` |
| `phase: "done"` | `references/phase-done.md` |
| `phase: "paused"` — or `stall_reason` set | `references/phase-build.md` (its Phase 0 abort/pause handlers own this resume) |

`status` and `review-batch` invocations do not dispatch a gate (see Entry Points).

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

**`statectl` is the sole writer of `state.json`.** Apply every field mutation with `python3 ~/.claude/skills/run-autopilot/scripts/statectl.py <state.json> set|append|del <json-path> <json-value>` (read one field with `get`); it takes an advisory lock, backs up to `<state.json>.bak`, changes only the named path while preserving all siblings, and replaces the file atomically — so it cannot leave a half-written or unparseable state, and it never trips the "not read yet" / "modified since read" errors the editing tools hit. Resolve `<state.json>` by walking up from the resolved physical cwd to the autopilot dir (the `_walk_up.py` pattern in `/work` step 2). The terse `set X` / `write field Y` / per-PRD-reset instructions throughout these skills and the gate files name the fields to change; each is applied with `statectl`, never by hand-editing the file.

Documented human fallback: outside the loop a person may still Edit or Write `state.json` by hand (for forensics or recovery); `validate_state_json_hook.py` catches a hand-edit that leaves the file unparseable, and `statectl` reads whatever valid JSON it finds on its next mutation.

**When `statectl` itself fails** (nonzero exit — advisory-lock contention, a Python error, an unreadable `state.json`): retry the exact command ONCE. If it fails again, do NOT improvise a partial write and do NOT proceed on the stale state — a lost mutation strands the loop on the wrong `next_phase`. Fall back to the documented hand-edit path above (Edit/Write `state.json` directly; `validate_state_json_hook.py` guards the shape) to record the failure, then treat it as a sub-skill failure: interactive → PAUSE with `state.pause_reason = {"site": "statectl_fail", "detail": "<the statectl command and its raw stderr>"}`; loop mode → stall the PRD (`references/recovery.md` Loop-mode stall procedure, `site: "statectl_fail"`) and continue the batch. The raw stderr rides into the batch report / deferred record so the failure is diagnosable, never silent (`rules/operating-principles.md`). (Lock contention on the single-writer model implies a second loop or a stale lock; the concurrent-loop guard below now refuses a second loop up front, so a persistent lock is a stale one — the retry clears it or the hand-edit fallback records it.)

Create `dev/local/autopilot/` and subdirectories if missing. Initialize state file at PRD selection. Update state at every phase transition. Autopilot also keeps a per-PRD **decision audit log** at `dev/local/reviews/<prd-base>-audit.md`, **rendered once at Phase 9 finalize from the `state.json` decision arrays** (`autonomous_decisions`, `deferred_decisions`, `doubts`). `state.json` is the single in-run source of truth — decisions are NOT mirrored to `audit.md` incrementally per decision. Each rendered entry carries a **source** label (`autonomous`, `deferred`, or `doubt`); cycle/phase context goes in the entry body so the Phase 9 `decisions.md` projection can filter autonomous entries by label. Entry format, the Phase 9 render procedure, and the projection live in `references/audit-log-format.md`.

**Invariant:** every state mutation that advances `phase` SHOULD also set `next_phase` to the same value. The three gates are `build` | `review` | `done` (plus `paused`). `build` is ONE session: selection, catchup, design, planning, and work all run under `phase: "build"` with no mid-build handoff. The review surface runs in its own fresh session; blind and doubt scrutiny are LENSES inside every review cycle (Blake and Bob in `review-work-completion`'s roster), not separate phases — reviewers get isolated contexts by construction (subagent prompts, external CLIs). Legacy `blind`/`doubt` phase values in pre-00015 state files map to `review` on resume. Per-task implementor tiering inside `/work` is unchanged. The authoritative resume signal is `phase` + `phases_completed`; build sub-step skipping is by ARTIFACT (capsule freshness, design-doc-exists, tasks-exist, all-done), not by `phases_completed` membership. This resume decision (phase + phases_completed + artifact checks → next step) is encoded canonically in `scripts/resume_target.py`, which `scripts/test_autopilot_resume.py` imports — editing the resume logic there flips a test red rather than silently drifting from this prose.

### Retention

Durable artifacts are the paper trail of a run; they outlive the batch and must survive every cleanup. Disposable artifacts are transient scaffolding. Cleanup — including the user CLAUDE.md "clean up temp files" mandate — defers to this contract: "temp" means the disposable list below and nothing else. Never delete a directory wholesale when it holds durable artifacts; delete disposables by name.

- **Durable** (never delete): `dev/local/prds/done/` and its PRDs, `dev/local/reviews/` (per-cycle review files, blind/doubt reviews, and the `<prd-base>-audit.md` audit renders), `dev/local/designs/` (per-PRD design docs), `dev/local/autopilot/reports/` (batch reports), `dev/local/autopilot/deferred/` (the `{batch_id}-deferred.json` records), `dev/local/autopilot/loop-metrics.jsonl` (the per-session loop metrics, accumulates across batches), and `dev/local/project-capsule.md`.
- **Disposable** (safe to delete by name): `dev/local/tmp/`, `dev/local/autopilot/last-session.log`, `dev/local/autopilot/wrapper.log`, `dev/local/autopilot/pause-requested`, `dev/local/autopilot/state.json` (at batch end only — in loop mode the wrapper archives it to `reports/{batch_id}-state-final.json`; see `references/phase-done.md`), and `dev/local/autopilot/replan-context.md`.

Batch end and any cleanup step enumerate the disposable list explicitly; they never `rm` a durable path or a directory that contains one. This is what keeps a completed PRD's review trail intact after the batch closes (`references/design-rationale.md` § Verified moves).

### Resuming

When `/run-autopilot` is invoked and `dev/local/autopilot/state.json` exists with `batch.completed_prds`, this is a continuation after a session restart. Preserve `batch.completed_prds` (including `batch.id`) and proceed to the build gate's Phase 0 to pick the next PRD.

Delete `state.pause_reason` from `state.json` if present — unconditional, on every invocation, NOT gated on `batch.completed_prds`. A new session means any pause is being resumed; `pause_reason` belongs only to an unresolved pause and is not overwritten by normal progression, so it must be cleared here or it halts the resumed PRD's next hand-off. Cap-pause detection is unaffected — it keys on `cap_pause_reason`, which this delete does not touch.

### Operator runbook (unattended batches)

All interaction with a running `autoclaude` batch happens at session boundaries — the only safe point. (Operator-shell commands for the human's own terminal, not for the model's Bash tool — `tail -f` would hang a session and pipes are hook-blocked.)

- **Watch**: `tail -f dev/local/autopilot/last-session.log` — the wrapper tees the live event log of the running headless turn there.
- **Pause**: `touch dev/local/autopilot/pause-requested` — the wrapper consumes the marker at the next session boundary, notifies "paused by operator", and stops the loop with state intact.
- **Take over**: with the loop stopped (pause marker, or Ctrl-C on the wrapper), run `/run-autopilot` in a normal interactive session — resume-by-artifact reads the same `state.json`, and full interactive semantics (questions, PAUSEs) apply because `$_AUTOPILOT_LOOP` is unset. Restart `autoclaude` afterwards to go unattended again.
- **Resume after a PAUSE** (`phase: "paused"` in `state.json`, "session paused" banner/ntfy): same take-over recipe, and it is the ONLY way forward — re-running `autoclaude` reads the paused state and exits again immediately. Interactively, the phase that paused re-runs with `AskUserQuestion` available, so the blockers that halted the loop are asked as decisions instead. Answer them, let the session hand off or finish the PRD, then re-run `autoclaude`.
- **Un-park a sidelined PRD**: a PRD the loop parked (a `wrapper_died` death-park, or a loop-mode `design_gate` / `blocking_escalation` stall) sits in `dev/local/prds/hold/` with its stall recorded in the batch deferred JSON; the batch kept draining without it. To resume it, `mv dev/local/prds/hold/<00XXX-…>.md dev/local/prds/backlog/` (keep the `00XXX-` prefix). Autopilot never reads `hold/`, so the next `/run-autopilot` (or `autoclaude` relaunch) re-selects it from `backlog/` and re-enters the build gate, reusing its existing design doc via the Phase 1.5 artifact skip (a `design_gate` park then re-fires the gate interactively). Batch-end review lists every parked PRD (`{m} stalled`), so none is silently forgotten.
- **Forensics**: `claude --resume <session-id>` (the id is in the init event at the top of `last-session.log`) reopens a finished headless conversation for questioning. Harmless by construction: sessions are disposable; `state.json` plus the artifacts are the only orchestration contract, so a resumed chat cannot fork the loop.

- **One loop per repo**: a second `autoclaude` on a repo that already has a live loop refuses to start, naming the incumbent loop's PID (both the tracon front-end and the plain/headless path check the loop registry via `scripts/tracon_wrapper_alive.py` before registering). This prevents two loops double-draining the backlog and racing `state.json` writes. If the refusal is wrong (the named PID is dead), the stale registry entry is pruned automatically on the next launch; force it by deleting `~/.claude/autopilot-loops/<pid>.json`.

A running headless turn is never interrupted except by the wrapper's wall-clock cap (`_AUTOPILOT_SESSION_MAX`, default 7200s); review-phase launches use `_AUTOPILOT_SESSION_MAX_REVIEW` (default 10800s).

### Task Counts

`tasks_total` and `tasks_completed` are maintained by whoever writes the `state.tasks` snapshot: recompute both in the same write — `tasks_total = len(tasks)`, `tasks_completed = count(status == "completed")` (the pidash-era PostToolUse sync hook is retired, PRD 00063). The model does NOT query `TaskList` to mirror counts at each state update; the arithmetic runs on the snapshot already in hand. Keep `state.tasks` accurate at phase transitions and recompute the counts alongside each `tasks` snapshot, applying all three with `statectl set` (§ State Management), keeping the dashboard progress bar live.

### Hydrate TaskList from state.tasks (shared sub-step)

`TaskList` is per-session storage (`~/.claude/tasks/<session-id>/`). Every fresh autopilot session — handoff to a review surface, restart after a context-cap rotation, or any manual re-invocation — starts with an **empty** TaskList even when `state.tasks` carries the full snapshot from the prior session. Phase skipping (planning, work) and per-task model dispatch both rely on TaskList, so without rehydration the new session operates with no task tracker at all.

Run this hydration **before any phase invokes `/work` or queries TaskList for routing** — specifically: Phase 2 (before the skip-rule check), Phase 3 (before `/work`), Phase 6 (before rework `/work`).

**Load if empty.** Query `TaskList`. If it returns **any** tasks, no-op (already populated this session). Otherwise read `state.tasks` from `dev/local/autopilot/state.json`; if absent or empty, no-op (nothing to hydrate). Otherwise, for each entry **in declared order** (do NOT reorder), `TaskCreate(subject: name)`, passing `model` / `estimated_tokens` / `est_context_peak` / `attempts` / `qwen_eligible` / `qwen_excluded_reason` straight through as `metadata` when present — `/work` reads `metadata.model` (PRD 00025) and `metadata.qwen_eligible` (PRD 00031/00019); the rest keep the round-trip lossless. `TaskCreate` assigns ids sequentially from 1, aligning with `state.tasks[].id` by construction. Then `TaskUpdate(status: ...)` each entry to its recorded status (`in_progress` / `completed`; `pending` is the `TaskCreate` default, skip it). The `attempts` array round-trips as-is — the hydration never inspects its rows, so any per-attempt field (`implementor`, `preflight_outcome`, `self_deslop`, future fields) survives the snapshot → hydration → `TaskGet` cycle intact.

**Idempotency:** if a phase re-enters this sub-step on the same session (e.g. Phase 6 after Phase 3), the TaskList-non-empty check short-circuits. Safe to call as a precondition on every `/work` entry point.

### Live Dashboard

`autoclaude` launches `tracon` (`scripts/tracon/`) in the foreground by default (PRD 00062), so the loop terminal shows the live dashboard with no extra step. It reads `dev/local/autopilot/state.json` — no action needed from autopilot beyond keeping the state file updated. `q` detaches (loop keeps running, wrapper prints the reattach command), `p` pauses at the next session boundary, `Ctrl-C` stops the loop with full cleanup. When there is no tty, no `uv`, or `_AUTOPILOT_TRACON=0`, the loop terminal shows the `render_stream.py` fallback with per-lane subagent tags instead. Full operator surface: `references/dashboard-format.md`.

### Phase Banners

Print a banner at each phase transition:

```
── AUTOPILOT ── PRD: {prd-name} ── Phase: {PHASE} ──────────────────
── AUTOPILOT ── PRD: {prd-name} ── Phase: REVIEW ── Cycle {n} ─────
── AUTOPILOT ── PRD: {prd-name} ── Cycle {n} rework complete ───────
── AUTOPILOT ── handing off to fresh session for cycle {n+1} ───────
── AUTOPILOT ── PAUSED ── {n} issue(s) need your decision ──────────
── AUTOPILOT ── PRD: {prd-name} ── DONE ── {n} cycles ─────────────
```

## Session Loop

Unattended mode runs each session headless: the `autoclaude` wrapper (in `~/.config/bash/plugins/development.plugin.bash`) launches `claude -p "/run-autopilot"`, the session runs exactly one turn, and the process exits at turn end. There is no signal file and no Stop-hook choreography — **`state.json` is the entire hand-off contract** (`references/design-rationale.md` § Headless sessions).

**Hand-off = write state, print banner, end the turn.** After the process exits, the wrapper reads `state.json` and branches:

1. `pause_reason` set or `phase == "paused"` → notify the user with the pause detail, stop the loop, state left intact.
2. `stall_reason.stalled == "subagent_prompt_overrun"` (set by `/work`'s Subagent Dispatch Budget when an assembled subagent prompt exceeded 50K after one trim pass; `/work` also appends to `state.task_aborts`) → continue the loop; Phase 0 of the next session replans the PRD in place (PRD stays in `wip/`; see the build gate's abort handlers). This is the one surviving replan path.
3. `next_phase == ""` (empty) → backlog drained: the wrapper archives `state.json` to `reports/{batch_id}-state-final.json`, notifies, and stops the loop.
4. `next_phase` non-empty → relaunch a fresh session, which resumes from state by artifact — capsule fresh → skip catchup, tasks exist → skip planning, `/work` continues at the first non-completed task.
5. `state.json` missing, unreadable, or untouched by the session → usage-limit check against the captured session log (`last-session.log`; a live limit means sleep-until-reset and continue). Otherwise a genuine death: with a PRD selected (`state.prd` non-empty) the wrapper retries the relaunch once (`_AUTOPILOT_DIED_RETRIES_MAX`, default 1), then on exhaustion PARKS it — writes `dev/local/autopilot/park-requested` (`{prd, reason}`) and relaunches, so the next session's Phase 0 park handler sidelines the sick PRD to `hold/` and the batch keeps draining (PRD 00066). Only a **bootstrap** death (no PRD selected — nothing to park) notifies "died" and stops loud; an unconsumed park marker trips the wrapper's park-loop guard (also a loud stop; guarded relaunches back off `_AUTOPILOT_PARK_BACKOFF`, default 30s, and a marker whose write fails outright halts loud rather than handing off an empty marker). These two are rows 8 and 10 of the Error Handling § sanctioned batch-halt list.

A Work-turn context-cap overrun is just branch 4: `autopilot_context_cap_hook.py` records the rotation (appends to `state.cap_rotations`, resets the in-flight task to `pending`, sets `next_phase: "build"`), the turn ends, and the fresh session resumes `build` by artifact — NO replan.

The model's only job at a hand-off is to write `state.next_phase` (and `phase`/`stall_reason`) accurately, print the banner, and end the turn. The model never writes any signal and never inspects the wrapper's decision table — writing accurate state IS the hand-off. Interactive (non-loop) semantics are identical minus the wrapper: the same state writes happen, and the user re-invokes `/run-autopilot` manually.

**End the turn only at a real hand-off.** A phase is complete only when its artifacts are written and `state` is advanced (`phases_completed` updated, `next_phase` set). Dispatched work — `Agent` calls and background Bash — returns its results **within the same headless turn**: the harness re-invokes you with each `<task-notification>` before the turn can end, so dispatch, overlap independent work, wait for the results, and finish the phase. Do not end the turn to "wait for" something you dispatched.

**Background Bash alone cannot hold a headless session open.** Documented `-p` behavior: live subagents keep the process alive across turn ends and re-invoke on completion, but background Bash tasks are killed ~5s after the final result. A turn that ends while ONLY background Bash (codex/gemini/qwen, `cargo test`, …) is still running kills that work and strands the phase (2026-07-12: the review session died this way twice — codex killed mid-review, state untouched, loop halted). Whenever dispatched background Bash may outlive every live subagent, dispatch a **Watcher subagent** in the same message that re-runs `~/.claude/skills/review-work-completion/scripts/await_reviewer_outputs.py` against the expected output files until `DONE` (procedure: `/review-work-completion` step 5). The wrapper exports `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` so the subagent wait has no 10-minute ceiling; the session wall-clock cap stays the backstop.

An idle end-of-turn (phase unfinished, nothing pending) no longer thrashes anything — the wrapper relaunches and the next session resumes the phase by artifact (self-healing) — but it burns a session start, so treat it as waste, not as a mechanism.

For long **Bash** (builds, tests), still prefer the FOREGROUND with an explicit `timeout` (up to 600000 ms) so the result is in hand directly. If genuine work cannot finish in this session, that is a PAUSE (`phase: "paused"` + `state.pause_reason = {"site": "work_incomplete", "detail": "<what could not finish>"}` + end turn), not a silent idle stop.

### Session handoff procedure (canonical — gate files invoke it by site name)

Every session handoff is the same three steps:

1. **Apply the site's state fields** (table below) to `dev/local/autopilot/state.json` with `statectl set` (one `set` per field; statectl merges — it never replaces sibling fields).
2. **Print the site's banner** (shown at the invoking site in the gate file).
3. **End the turn.** In loop mode the wrapper reads `state.json` and relaunches per its decision table above; outside the loop the user re-invokes `/run-autopilot` and the same resume logic applies. Do NOT continue into the next gate's phases in this session, even if context budget appears sufficient.

| site | state writes | `phases_completed` |
|------|--------------|--------------------|
| **build → review** (`phase-build.md`, after Phase 3) | `phase: "review"`, `next_phase: "review"`, updated `tasks` snapshot | unchanged — the build gate leaves no membership marker |
| **review → review** (`phase-review.md` Phase 6, after rework when the loop continues) | `phase: "review"`, `next_phase: "review"` (Phase 6 steps 1-3 already wrote these plus the incremented `cycle`); do NOT rewrite `state.tasks` | unchanged — only convergence (review → done) adds `"review"` |
| **review → done** (`phase-review.md`, on loop convergence) | `phase: "done"`, `next_phase: "done"` | add `"review"` — the convergence marker the review gate's loop-level skip reads |
| **PRD → PRD** (`phase-done.md`, step 10 more-PRDs branch) | `phase: "build"`, `next_phase: "build"`, plus the per-PRD reset list (`phase-done.md` § Continuation); preserve `batch` in full | reset to `[]` |

Batch end is NOT a handoff: it writes `phase: "done"` + `next_phase: ""` (the wrapper's drained branch) and stops — see `references/phase-done.md`.

### Contract card (compaction re-anchor)

Within-session compaction can drop this skill's text mid-procedure, after which the session drifts off-contract with nothing to re-anchor it. To survive that, **at each gate transition write a compact contract card** — the current step, the active invariants, and the next gate:

- **Autopilot (state.json world):** write it via statectl to `state.contract_card` (one `set`), in the same handoff write that advances `phase`/`next_phase`. Keep it a few lines: `step: <phase/step> | invariants: <the 2-3 that bind right now> | next: <the next gate + its precondition>`.
- **Interactive (no state.json):** write the same card to the scratch file `dev/local/autopilot/contract-card.md` (Write tool).

`reinject_contract_card.py` is a SessionStart hook **matched to `compact` only** (startup/resume/clear stay unmatched, so there is no standing token cost); after a compaction it reads the card back and re-injects it as additionalContext. `/work` (task-boundary transitions) and `/review-work-completion` (cycle transitions) write their own cards the same way — `contract_card` in `references/state-schema.md`.

### Loop Detection

The `autoclaude` wrapper exports `_AUTOPILOT_LOOP=$$` before launching each headless session. Skills branch on it for loop-mode behavior only — the `AskUserQuestion` ban (Error Handling), git-push deferral, notify suppression in `~/.claude/hooks/notify.py`. Hand-off sites do NOT check it: the state writes are the same in and out of the loop.

**Review-file gate (in-session quality gate).** `review_coverage_hook.py` stays registered on Stop: at the done hand-off, when the saved review file is missing or fails the `check_review_file.py` shape check (missing reviewer section, verdict, or tests line — PRD 00016), it exit-2-blocks the turn's end and feeds the gap back to the model so the review can be finished before the turn ends. Exit-2 Stop-hook blocking works in `-p` mode (`references/design-rationale.md` § Review-file gate). This is a completeness gate on review artifacts, not loop orchestration.

**State-write gate (in-session integrity gate).** `statectl` is the normal writer and cannot produce an invalid `state.json`, but a stray hand-edit still can, so `validate_state_json_hook.py` stays registered on PostToolUse for the `Edit`/`Write`/`MultiEdit` matchers: any such mutation that leaves the file unparseable exit-2-feeds the parse error back to the model immediately, while the session can still rewrite it. Without it, the corruption surfaces only at session exit, where the wrapper's `jq` check misreads a healthy PAUSE as `died` (state file unreadable) and halts the loop (harness-tag bleed appended `</content>` to a hand-edited write, ddb 2026-07-16).

**Wrapper sketch** (the real `autoclaude` adds the memory circuit-breaker, the session wall-clock cap, orphan cleanup, metrics, notifications, and the operator-view renderer — `scripts/render_stream.py` turns the stream-json terminal output into one-line summaries while `last-session.log` keeps the raw events):

```bash
while true; do
  [ -f dev/local/autopilot/pause-requested ] && break   # operator pause
  WARDEN_UNATTENDED=1 CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 \
    claude -p "/run-autopilot" 2>&1 | tee dev/local/autopilot/last-session.log
  # read state.json and branch per the decision table above (1-5)
done
```

## Phase 0 invariants (selection — full procedure: `references/phase-build.md`)

Test-pinned invariants the build gate's Phase 0 references; they live here so every session carries them.

**Lifecycle directories first.** Before the abort handlers and before PRD selection, as its own Bash call:

```bash
mkdir -p dev/local/prds/backlog dev/local/prds/wip dev/local/prds/done dev/local/prds/hold dev/local/reviews dev/local/tmp dev/local/autopilot/reports dev/local/autopilot/deferred
```

Idempotent, safe on every invocation. `mkdir` before any move is mandatory: a move into a missing destination silently misplaces the PRD (`references/design-rationale.md` § Verified moves).

**Verified moves.** Every lifecycle `mv` (backlog→`wip/` at selection, and equally wip→done / wip→hold at the other gates) is immediately followed by a verification: confirm the moved PRD now exists in the destination directory. If it does not, the `mv` failed — set `state.phase = "paused"` and `state.next_phase = "paused"`, write `state.pause_reason = {"site": "mv_verify", "detail": "<source, destination, and the mv error>"}`, and PAUSE naming the source, the destination, and the `mv` error; do not continue past a failed move.

**Batch-identity rollover.** When `state.batch` already exists at selection, mint a fresh `batch.id` (new `<yyyymmddHHMM>` timestamp, reset `completed_prds: []`) ONLY for a *genuinely closed* surviving batch: `phase == "done"` AND `next_phase == ""` (empty). Both conditions are required — only the batch-end "No more PRDs" branch writes the empty `next_phase`, while Phase 9 step 2 sets a transient `phase: "done"` (with `next_phase: "done"`) BEFORE the verified wip→done move, so a failed move or mid-Phase-9 crash leaves that shape and must NOT roll over (rolling over there would wipe the in-progress batch's `completed_prds` and mint a spurious id). Every normal in-progress resume preserves `batch.id` unchanged. (Forensics: `references/design-rationale.md` § Batch-identity rollover.)

## Phase 3 invariants (work — full procedure: `references/phase-build.md`)

**`work_start_sha` is captured once per PRD.** Run `git rev-parse HEAD` and write it to `state.work_start_sha` before dispatching `/work`, but only if it is unset for the current PRD (`state.work_start_sha` absent or empty). If it is already set, **do NOT re-capture** — a cap-rotation (or any other build re-entry on resume) re-enters the build gate with pending tasks, and the existing value marks the true PRD start; re-capturing the HEAD-at-rotation would shrink the review diff (`work_start_sha..HEAD`) to post-rotation commits only. `review-work-completion` uses `work_start_sha..HEAD` as the full-review diff range, so the doubt lens sees the PRD's whole work range. Phase 9 step 10 clears the field on the PRD-to-PRD reset, so each PRD in a multi-PRD batch captures fresh and ranges never overlap.

**If `git rev-parse HEAD` fails at capture** — an unborn branch or a repo with no commits yet (a *detached* HEAD resolves fine and is not this case; a bare-repo-backed root like `~/.claude` must run rev-parse in the SAME git context `repo_root` uses — the `--git-dir`/`--work-tree` flags — not a bare `git rev-parse` that would fail or resolve a parent repo): there is no base commit to diff against. Do NOT leave `work_start_sha` unset (an absent value makes the review range undefined and crashes the doubt lens). Set it to the git **empty-tree sentinel** `4b825dc642cb6eb9a060e54bf8d69288fbee4904`, log a one-line warning, and note the fallback in the batch report — the review range `4b825dc…..HEAD` then spans the whole tree once `/work` has committed, which is the correct scope for a first-commit repo.

## Phase 9 invariants (completion — full procedure: `references/phase-done.md`)

**Verified finalize move.** The move of the PRD from `wip/` to `done/` keeps the `00XXX-` prefix and is verified: confirm the PRD now exists in `dev/local/prds/done/`; on failure PAUSE per the verified-moves rule above (`site: "mv_verify"`) — never append to `completed_prds` or advance to the next PRD with the PRD in the wrong folder.

**Report identity.** The batch report filename is built from the current `state.batch.id` — `reports/{state.batch.id}-report.md`; before appending, verify the target filename's id matches `state.batch.id`. Never glob `reports/*.md` to choose a file, and never append to a report whose id differs from `state.batch.id` — a mismatch is a batch-identity error; create a fresh `{state.batch.id}-report.md` instead.

## Design-gate invariant: empty-review-log gate (Phase 1.5 — full procedure: `references/phase-build.md`)

Phase 1.5 must verify the design doc's `## Review log` actually holds at least one reviewer dispatch summary line — a silently-skipped review leaves it empty, and nothing else checks that the review ran. Run the gate on this success path (after a successful `/design-solution` run) AND on this artifact-reuse path (when an existing design doc is reused); `design_mode == "skip"` bypasses the empty-review-log gate entirely (no doc exists by design). Inline the design-doc path from `state.design_doc` directly into this exact section-scoped check (one `awk`, no pipe, no shell variable — assignments break permission-prefix matching; exit-code based — it counts only pinned dispatch-summary lines that appear inside the `## Review log` section, so the design doc's own example lines in `## Interfaces & contracts` cannot false-pass it):

```
awk '/^## Review log/{f=1;next} /^## /{f=0} f && /dispatch [0-9]+ \((claude|codex|claude-fallback)\): cardinal-sin [0-9]+, blocker [0-9]+, non-blocker [0-9]+, question [0-9]+/{hit=1} END{exit !hit}' <path-from-state.design_doc>
```

- **exit 0** (≥1 in-section dispatch summary line) → proceed to Phase 2 (planning).
- **exit non-zero** (empty `## Review log` — the review never ran) → treat as a sub-skill failure: set `state.phase = "paused"` and `state.next_phase = "paused"`, write `state.pause_reason = {"site": "sub_skill_fail", "detail": "design doc has empty ## Review log (review never ran)"}`, and do NOT proceed to planning. Surface the remedy: delete the design doc and let Phase 1.5 regenerate it.

The check is deterministic (the pinned `awk` above), NOT a model judgment.

## Shell Command Rules

- **Never chain commands** with `&&`, `|`, or `;` in a single Bash call. Use separate Bash tool calls instead.
- **Never use redirections** like `2>/dev/null`. Handle missing files by checking existence or catching errors in the tool result.
- Use `Read` for file contents; for existence and listing checks Bash `ls` is fine (the native `Glob` tool is absent in this build - rules/tools.md).
- Use `mkdir -p` in its own Bash call when creating directories.

## Error Handling

| Situation | Interactive | Loop mode (`$_AUTOPILOT_LOOP` set, PRD 00017) |
|-----------|-------------|------------------------------------------------|
| Sub-skill invocation fails outright (no usable result; the phase cannot proceed) | PAUSE, report which skill failed and error. A transient reviewer/sub-skill error *during the review-rework cycle* is the review gate's Safety Checks row's domain instead (graceful degradation, not a PAUSE). | Re-invoke the sub-skill ONCE; if it fails again, stall the PRD (`recovery.md` → "Loop-mode stall procedure", `site: "sub_skill_fail"`) and continue the batch |
| No PRDs anywhere | STOP with message about /create-prd | Write `state.phase = "done"` and `state.next_phase = ""` first so the wrapper stops as drained, not died |
| State file corrupted | Delete it, restart from Phase 0 | Same (in-session recovery, no pause) |
| `statectl` state-write fails (lock contention, python error, unreadable state) | Retry once; still failing → hand-edit `state.json` to record the pause, PAUSE (`site: "statectl_fail"`) with the raw stderr in `detail` — never proceed on the stale state | Retry once; still failing → hand-edit to record the stall, stall the PRD (`site: "statectl_fail"`), continue the batch |
| Review produces no parseable output | PAUSE, report — don't retry | Re-run the review ONCE; still unparseable → stall the PRD (`site: "reviewer_fail"`), continue the batch |
| All reviewers fail | PAUSE, report — partial results usable if user confirms | Re-invoke ONCE; still nothing → stall the PRD (`site: "reviewer_fail"`), continue the batch |
| `dev/local/` doesn't exist | Create it | Same |
| Task tools unavailable | STOP, report — can't operate without tasks | Same (a broken harness is not a per-PRD failure) |
| Git push fails (auth, locked signing agent, network) | Report and let the user retry | Log to `deferred_decisions[]`, leave the commits local (the user pushes manually per Phase 9), CONTINUE — a locked signing agent on an unattended host is expected (`references/design-rationale.md` § Git push failures) |
| `mv` verify fails (backlog→wip, wip→done, wip→hold) | PAUSE per the mv-verify sites | Retry the `mv` ONCE after re-running `mkdir -p`; persistent failure is a sanctioned batch halt (row 3 of the sanctioned batch-halt list below) |
| **Security-critical finding** (exposed secret, vulnerability being shipped) | PAUSE | **PAUSE — sanctioned batch halt, row 1** (set `phase: "paused"` + `pause_reason`; the wrapper notifies and halts) |
| **Detected data-loss risk** | PAUSE | **PAUSE — sanctioned batch halt, row 2** (same mechanics) |

**Loop mode never halts the whole batch for a per-PRD decision.** After PRD 00066 the loop-mode turn-ending *decision*-PAUSE list is empty: a blocking escalation and the Phase 1.5 design gate STALL the PRD (`references/recovery.md` Loop-mode stall procedure), a scope alarm DEFERS-and-continues, and a Phase 2 ambiguity is resolved by the simplest safe assumption (or stalls under `pause_on_ambiguity: true`) — none write `phase: "paused"`. Everything else stalls the PRD or defers and continues. The ONLY conditions that stop the whole batch (a loud halt, not a per-PRD park/stall) are the sanctioned batch-halt list below. Future edits must not re-grow the loop-mode decision-PAUSE list, nor add a halt outside that list.

**Sanctioned batch-halt list (the complete set of whole-batch loud stops):**

1. **Security-critical finding** — exposed secret or a vulnerability being shipped (skill PAUSE; `pause_reason` set by the Error Handling row above).
2. **Detected data-loss risk** (skill PAUSE).
3. **`mv`-verify exhaustion** — a lifecycle move that keeps failing after the retry (skill PAUSE, `mv_verify`).
4. **Sustained memory pressure** (wrapper memory circuit-breaker).
5. **Usage-limit beyond `_AUTOPILOT_LIMIT_WAIT_MAX`** (wrapper `died`).
6. **Net-retries exhausted** (wrapper `died`).
7. **Operator pause** — the `pause-requested` marker (wrapper stop).
8. **Died bootstrap session** — a session died before any PRD was selected, so there is nothing to park (wrapper `died`).
9. **Systemic-park breaker** — 2 consecutive `wrapper_died` parks with nothing healthy between (skill PAUSE, `systemic_park`; Phase 0 park handler, `references/phase-build.md`).
10. **Unwritable or unconsumed park marker** — the park hand-off itself is broken: the wrapper cannot write the `park-requested` marker (the write-failure guard in the `park)` else branch, so it never hands off an empty marker) OR a written marker is never consumed (the park-loop guard). Either is a wrapper loud halt.
11. **Plugin version drift** (PRD 00086 R3) — the wrapper's plugin-pin preflight (`_autopilot_plugin_drift`) found an enforcement plugin (aegis/warden) whose installed version differs from the `state.batch.plugin_versions` pin recorded at batch selection: the batch's enforcement code auto-updated mid-run, so the wrapper halts loud with state intact rather than run a session on unpinned enforcement code.

Rows 1–8 are the PRD 00066 Success-Metrics list; rows 9–10 are the two systemic backstops the PRD Risks section mandates (adopted at the design gate, 2026-07-18); row 11 is the plugin-pin preflight (PRD 00086 R3). Nothing outside these eleven stops the batch — Success Metric 2 is read as "no UNSANCTIONED halts".

**Turn-ending PAUSE rows must set `state.phase = "paused"` (and `state.next_phase = "paused"`) before stopping, and must also write `state.pause_reason = {"site": "<slug>", "detail": "<one-line human string>"}`.** `pause_reason` is a durable marker so the loop halts even if the model forgets `phase="paused"`; unlike `phase` it is not overwritten by normal progression, so it must be cleared on resume (see `### Resuming` cleanup). Without it the wrapper — seeing a non-empty `next_phase` — would take its continue branch and relaunch the failed phase instead of stopping for you to intervene; a paused state is the wrapper's stop-and-notify branch (Session Loop branch 1), and the wrapper surfaces `pause_reason.detail` in its notification. This applies to "Sub-skill invocation fails outright" (`pause_reason.site = "sub_skill_fail"`), "Review produces no parseable output" (`"reviewer_fail"`), "All three reviewers fail" (`"reviewer_fail"`), and "statectl state-write fails" (`"statectl_fail"`). Exceptions that need no `phase` change: "State file corrupted" (delete it and restart from Phase 0 in the same session; the freshly-written state is what the wrapper reads at turn end) and "No PRDs anywhere" (see its row — the drained state write covers the loop). PAUSE sites that ask via `AskUserQuestion` mid-turn (Phase 1.5 design gate, Phase 2 clarification, Phase 5 blocking escalation and scope alarm) do NOT end the turn and need no `phase` change — **but only outside the loop. When `$_AUTOPILOT_LOOP` is set there is no human to answer, and (post-00066) none of these pause the batch: each takes its per-PRD path instead. The design gate and a blocking escalation run the Loop-mode stall procedure (`references/recovery.md`; `site: "design_gate"` recording the design doc path, `site: "blocking_escalation"` recording the blocking issue in the deferred JSON `detail`); a scope alarm defers-and-continues (a `scope-overflow` deferred record — the top-10 fixes proceed); a Phase 2 ambiguity is resolved by the simplest safe assumption, or stalls (`site: "clarification"`) under `pause_on_ambiguity: true`. None writes `phase: "paused"` — the batch keeps draining and a human resolves the parked PRD on the next manual `/run-autopilot` (see `references/decision-framework.md` → "Autonomy in loop mode"). A mid-turn question on the unattended path has stranded the loop for hours (`references/design-rationale.md` § No mid-turn questions).**

## Reference Files

- `references/phase-build.md` — build gate (selection/aborts, catchup, design, planning, work)
- `references/phase-review.md` — review gate (lenses, decision gate, cap, rework)
- `references/phase-done.md` — done gate (completion, continuation, batch-end review)
- `references/state-schema.md` — state file JSON schema and skip logic
- `references/decision-framework.md` — auto-fix vs escalate classification rules
- `references/recovery.md` — rare-path handlers (abort/replan, stalls, escalation-exhausted, cap-pause resume)
- `references/design-rationale.md` — incident history behind the rules (non-normative)
- `references/dashboard-format.md` — live dashboard via tracon (render_stream fallback)
- `references/batch-report-format.md` — batch audit report format
- `references/audit-log-format.md` — audit entry format, render procedure, decisions.md projection
- `references/doubt-review-rubric.md` — Bob's doubt-lens rubric (R1-R5)
