# Build Gate (`phase: "build"`)

Routed here when `state.phase` is `"build"`, `state.json` is missing, or the
state is `"paused"`/aborted (the Phase 0 handlers below own that resume).
`build` is ONE session — selection, catchup, design, planning, work — with no
mid-build handoff; sub-steps skip by ARTIFACT, never by `phases_completed`
membership. Core `SKILL.md` (always loaded) carries the shared mechanics and
the test-pinned invariants this file references.

## Phase 0: PRD Selection

### Ensure lifecycle directories exist

Before anything else — before the abort handlers and before PRD selection — run
the lifecycle `mkdir -p` block from core `SKILL.md` § "Phase 0 invariants" as
its own Bash call (idempotent; mandatory before any move can run).

### Handle Work-phase abort (from a prior session)

Before anything else, read `dev/local/autopilot/state.json` and check `stall_reason`:

- `stall_reason.stalled` is `"subagent_prompt_overrun"` — the previous session's work aborted from a hook. The PRD is not broken; one task was scoped too big. **Follow `references/recovery.md` → "Work-phase abort: replan procedure"**, then STOP (the next session re-enters `build` at planning). This is the one surviving replan path.
- `stall_reason.stalled` is `"escalation_exhausted"` — Phase 6 owns this inline; seeing it at Phase 0 means a crash landed mid-stall-move. **Follow `references/recovery.md` → "Crash recovery: escalation_exhausted seen at Phase 0"**, then fall through to Normal PRD selection.
- `state.phase == "paused"` AND `state.cap_pause_reason` is set (the previous session's review-gate cap-pause behavior fired). The capped PRD is still in `dev/local/prds/wip/`; do NOT treat it as fresh PRD selection. **Follow `references/recovery.md` → "Cap-Pause Resume Handler"** — it presents the recorded unresolved findings and cycle count via the `AskUserQuestion` tool and branches on resume/abandon.
- `state.cap_rotations` has a new entry but none of the above holds — the previous session hit the Work-turn context cap and the cap hook rotated to a fresh session. The cap hook recorded the rotation (appended `cap_rotations`, reset the in-flight task to `pending`, set `next_phase: "build"`); that session then ended its turn and the loop wrapper relaunched on the non-empty `next_phase`. NOT a replan. A `cap_rotations` entry is **informational only** and needs no special handling here: fall through to Normal PRD selection, which resumes `build` by artifact (capsule fresh → skip catchup; tasks exist → skip planning; `/work` continues at the first non-completed task — the rotated task, now reset to `pending`).
- None of the above (neither a recognised `stall_reason` value nor the cap-pause condition `phase == "paused"` + `cap_pause_reason`) — continue with Normal PRD selection below.

### Normal PRD selection

1. If argument provided, find that PRD in `dev/local/prds/wip/` or `dev/local/prds/backlog/`. If found in backlog, move it to `wip/` under the **verified-move invariant** (core `SKILL.md` § "Phase 0 invariants"): confirm arrival, else pause with `site: "mv_verify"`; do not continue.
2. Otherwise, auto-select (never ask the user):
   a. Check `dev/local/prds/wip/`:
      - 1+ found → auto-pick lowest sequence number (by `00XXX-` prefix), announce
   b. If wip is empty, check `dev/local/prds/backlog/`:
      - PRDs available → auto-pick lowest sequence number, move to `wip/` under the same verified-move invariant
      - Empty → STOP: "No PRDs found. Create one with /create-prd." (Loop mode: first write the drained state per the Error Handling row "No PRDs anywhere".)
3. Initialize `batch` in state file if not already present: `id: "<yyyymmddHHMM>"` (current timestamp), `mode: "autopilot"`, `completed_prds: []`. If `state.batch` IS already present, apply the **batch-identity rollover invariant** (core `SKILL.md` § "Phase 0 invariants") — mint a fresh `batch.id` only for a genuinely closed surviving batch; every normal in-progress resume preserves `batch.id` unchanged.
4. Parse the PRD frontmatter per the table below and write the results to state.
5. Read the Active Work section of `dev/local/project-capsule.md` if it exists. This contains PRD progress and operational context from previous sessions. Use it to inform work in this session.
6. Initialize/update state with selected PRD, preserve `batch` field
7. Print progress:
   ```
   ── AUTOPILOT ── PRD {n}: {prd-name} ─────────────────────────────
   ```
   Where `{n}` = `len(batch.completed_prds) + 1`

### Frontmatter parse table (step 4)

Read the first 20 lines of the selected PRD. If it begins with a `---` line,
parse the YAML block between the opening `---` and the next `---`, then apply:

| field | accepted values | default | state target | on invalid / absent |
|-------|-----------------|---------|--------------|---------------------|
| `catchup` | `run`, `skip`, `force` | `run` | `state.catchup_mode` | default + warn |
| `rework_cap` | positive integer (or string that parses cleanly as one) | `3` | `state.rework_cap` | default + warn |
| `design` | `run`, `skip` | `run` | `state.design_mode` | default + warn |
| `design_gate` | exact `user` | field left absent | `state.design_gate` | leave absent, no warn |
| `doubt_reviewer` | `codex`, `fable` | `codex` | `state.doubt_reviewer` | default + warn |
| `consensus_engine` | `legacy`, `shadow`, `workflow` | `legacy` | `state.consensus_engine` | default + warn |
| `pause_on_ambiguity` | exact `true` (PRD 00017) | treat as `false`, field left absent | `state.pause_on_ambiguity` | treat as `false`, no warn |

Shared fallback: on malformed YAML or missing frontmatter, log ONE warning line
("autopilot: PRD frontmatter malformed; defaulting catchup_mode=run,
rework_cap=3, design_mode=run, doubt_reviewer=codex, consensus_engine=legacy"),
take every default, and continue — never crash Phase 0 on a frontmatter
problem. Frontmatter is the source of truth; once Phase 0 has parsed it, do
not re-parse it after Phase 0.
(Exception by design: `default_model` belongs to `/plan-tasks` and is re-read
from the PRD at Phase 6 rework dispatch — Phase 0 never touches it.)

Semantics the table cannot carry:

- `catchup`: `run` honors the Phase 1 batch cache; `skip` bypasses catchup entirely; `force` ignores the cache and re-runs full catchup regardless of recency.
- `rework_cap` is consumed by the review gate's cap check (`references/phase-review.md` § Cap check).
- `doubt_reviewer`: `fable` adds Eve to the review batch as a fifth lens; `codex` runs the standard roster.
- `consensus_engine`: selects the engine behind Alice's consensus leg (`review-work-completion` step 1). `legacy` is today's single subagent; `workflow` makes the `review-fanout` workflow her leg; `shadow` runs both, with legacy gating and the workflow recorded as a non-gating observation.
- `pause_on_ambiguity: true` — in loop mode a requirements ambiguity STALLS the PRD instead of being resolved by assumption; it never pauses the batch (see Phase 2).

## Phase 1: Catchup

**Skip if:** the batch cache is fresh (the batch-cache freshness check below holds — the capsule is already current), OR `state.catchup_mode == "skip"`. The skip is by ARTIFACT (capsule freshness), not `phases_completed` membership.

When skipped via `catchup_mode == "skip"`: do not invoke `/catchup`. Set `state.catchup_mode = "skipped"` (so subsequent re-entries also skip), keep `phase: "build"` and `next_phase: "build"`, and proceed to Phase 1.5 (Design).

Otherwise, decide between **full catchup** and **delta refresh** using the batch cache.

### Batch cache check

The capsule (`dev/local/project-capsule.md`) is the persisted output of catchup: invariants, architecture decisions, GitHub state, project memories. Subsequent phases and their subagents read the capsule when they need that context — not TaskList, not state.json. Between PRDs in the same batch on the same branch, re-running the heavy gather phase costs ~60-95s and ~50K tokens with no information gain (`references/design-rationale.md` § Batch catchup cache).

`state.batch.catchup_completed_at` (ISO 8601) and `state.batch.catchup_head_sha` (current branch HEAD when last full catchup completed) record the cache. **Skip the full catchup and run a delta refresh** when ALL of the following hold:

1. `state.catchup_mode != "force"` — PRD frontmatter `catchup: force` overrides the cache.
2. `state.batch.catchup_completed_at` is present AND less than 4 hours old.
3. `state.batch.catchup_head_sha` matches the current `git rev-parse HEAD` on the active branch.

If any condition fails → **full catchup**: invoke `/catchup`. After completion, write `state.batch.catchup_completed_at = <now>` and `state.batch.catchup_head_sha = <current HEAD>`. These fields persist across PRDs in the batch (Phase 9 step 10 preserves them).

If all conditions hold → **delta refresh** (no `/catchup` invocation):

- Re-read all PRDs in `dev/local/prds/wip/` (the active set has changed since last catchup; new PRDs may have entered, old ones moved to `done/`).
- Update the Active Work section of `dev/local/project-capsule.md` with the current PRD list (use the same format Phase 9 step 8 uses). Leave Key Invariants, Architecture Decisions, Component Boundaries, GitHub State, Project Health, and Project Memories untouched — those reflect batch-stable knowledge.
- Print a one-line note: `── AUTOPILOT ── catchup: delta refresh (cache <Xm> old, HEAD <sha7>) ──`

After either path completes, proceed to Phase 1.5 (Design). Stay on `phase: "build"` and `next_phase: "build"`; do NOT add anything to `phases_completed`.

## Phase 1.5: Design (build-gate sub-step)

Between catchup (Phase 1) and planning (Phase 2), in the SAME build session. Design turns the PRD's requirements (the WHAT) into a reviewed implementation design doc (the HOW) before tasks are planned. This is a BUILD-GATE SUB-STEP: `state.phase` stays `"build"`, there is **no** new phase enum value, **no** `phases_completed` entry, and **no** session handoff. The skip is by ARTIFACT (the design doc), exactly like catchup's capsule-freshness skip.

Let `<prd-stem>` = `state.prd` with its trailing `.md` removed. The design doc artifact path is `dev/local/designs/<prd-stem>-design.md`.

**Skip if `state.design_mode == "skip"`:** do not invoke `/design-solution`. Set `state.design_mode = "skipped"`, leave `state.design_doc` unset, and proceed to Phase 2. (This skip also bypasses the empty-review-log gate — no doc exists by design.)

**Skip if the artifact already exists:** when `dev/local/designs/<prd-stem>-design.md` is already on disk (a manual `/design-solution` run earlier, or a work-abort replan re-entering the build gate). Log a one-line reuse note (`── AUTOPILOT ── design: reusing existing <prd-stem>-design.md ──`), set `state.design_doc` to that path, then **run the empty-review-log gate** (core `SKILL.md` § "Design-gate invariant") **on the artifact-reuse path** — an existing doc from a manual or aborted run is exactly where a skipped review hides — and proceed to Phase 2 only if the gate passes; do NOT re-invoke the skill. This artifact-based skip is what lets work-abort replans reuse the design with no extra logic.

**Otherwise, run design:**

1. Invoke `/design-solution` with the wip PRD path (`dev/local/prds/wip/<state.prd>`).
2. **On success (exit 0):** set `state.design_doc` to the artifact path it printed (`dev/local/designs/<prd-stem>-design.md`). Log the design decision (chosen approach + any unresolved non-blockers from the doc's `## Review log`) to `state.autonomous_decisions` under the existing audit label `autonomous` — do NOT add a `design` audit label (the audit-log label set is closed). Then **run the empty-review-log gate** (core `SKILL.md` § "Design-gate invariant") **on the success path** before proceeding to Phase 2.
3. **On failure (non-zero exit — unresolved cardinal sins/blockers after 3 reviewer dispatches):** treat as a sub-skill failure. PAUSE per the Error Handling table's "Sub-skill invocation fails outright" row — set `state.phase = "paused"` and `state.next_phase = "paused"`, write `state.pause_reason = {"site": "sub_skill_fail", "detail": "design-solution failed with open findings"}`, report the open findings, and do NOT proceed to planning.

**Design gate (`state.design_gate == "user"`):** after a successful design (or an artifact reuse), and only when `state.design_gate == "user"`, PAUSE before planning — present the design doc summary plus any unresolved non-blockers from `## Review log` via `AskUserQuestion`, and proceed to Phase 2 only after the user answers. This is a mid-turn `AskUserQuestion` PAUSE; it does not end the turn, so no `phase` change is needed. (Loop mode: the Error Handling table's `AskUserQuestion` ban applies — pause by state instead.)

After design completes (run, skipped, or reused), stay on `phase: "build"` and `next_phase: "build"`; do NOT add anything to `phases_completed`. Then proceed to Phase 2.

## Phase 2: Planning

**First, run the "Hydrate TaskList from state.tasks" sub-step** (core `SKILL.md` § State Management). This is mandatory — the skip rule below depends on it. Initial planning has nothing to hydrate (no-ops on empty `state.tasks`) and replan clears `state.tasks` deliberately (also no-ops); the case the hydration covers is a resumed PRD whose prior session populated `state.tasks` and handed off (e.g., a context-cap rotation into a fresh session). Without the hydration, the skip rule below sees an empty TaskList and mistakenly re-runs `/plan-tasks`.

**Skip if:** `TaskList` returns any pending or completed tasks (tasks already exist). Evaluate this **after** the hydration step above completes. This skip is by ARTIFACT (tasks exist), not `phases_completed` membership.

### Replan mode

Before invoking `/plan-tasks`, check for `dev/local/autopilot/replan-context.md`. If present, this is a replan triggered by a Phase 0 abort handler. Pass the file to `/plan-tasks` (see `plan-tasks/SKILL.md` "Replan mode") so it scopes to remaining work and uses the tighter ≤75K per-task budget. `/plan-tasks` deletes the file after successful planning.

If `replan-context.md` is absent, run `/plan-tasks` normally — first-pass planning for a fresh PRD.

Invoke `/plan-tasks` with the selected PRD.

**PAUSE site - requirements clarification.** When `/plan-tasks` pauses autopilot with a requirements-ambiguity or clarification question:

- **Interactive:** present it to the user and wait for the answer. Once answered, record the clarification and its resolution in `state.autonomous_decisions` (label `autonomous`) so the Phase 9 audit render captures it. Do not write `audit.md` here.
- **Loop mode (`$_AUTOPILOT_LOOP` set, PRD 00017):** never end the batch on an ambiguity. Resolve it by the **simplest safe assumption** (the user's own global rule), record it in `state.autonomous_decisions` as `{"type": "assumed-ambiguity", "question": ..., "assumption": ...}`, AND mirror the same record into the batch deferred JSON so batch-end review shows it under "assumptions made". Exception: when the PRD frontmatter set `pause_on_ambiguity: true` (parsed at Phase 0 step 4), do not guess — stall the PRD instead (`references/recovery.md` → "Loop-mode stall procedure", `site: "clarification"`) and continue the batch. A premise failure is never resolved by assumption either — it always stalls (see `/work`'s premise gate when present).

### Handle plan-tasks stall (oversized task)

`/plan-tasks` exits non-zero with `state.stall_reason.stalled == "oversized_task"` when a task cannot be split below the per-task budget. When this happens, do NOT proceed to Phase 3 — **follow `references/recovery.md` → "plan-tasks stall: oversized task"** (deletes orphan tasks, moves the PRD to `dev/local/prds/hold/`, advances to the next PRD).

**Other outcomes from `/plan-tasks`:**

- **Exits zero**: no stall. Continue normally to the post-completion state update below.
- **Exits non-zero without `stall_reason`** (or with a `stall_reason.stalled` value other than `"oversized_task"`): treat as a sub-skill failure. PAUSE and report the error per the "Sub-skill invocation fails" entry in the Error Handling table — also write `state.pause_reason = {"site": "plan_tasks_fail", "detail": "<one-line error>"}` alongside `phase="paused"`. Do NOT proceed to Phase 3 or move the PRD.

After completion, query `TaskList` and update state: stay on `phase: "build"` and `next_phase: "build"`, write the `tasks` snapshot (see Phase 3 for format; the sync hook maintains `tasks_total`/`tasks_completed`). Do NOT add anything to `phases_completed`. Flow continues DIRECTLY into Phase 3 (work) in this same session — there is no planning→work handoff.

## Phase 3: Work

**Skip if:** All tasks completed, none pending. Evaluate **after** running the hydration sub-step (below) — otherwise a fresh session sees TaskList empty and mistakenly treats "no pending" as "all done". This skip is by ARTIFACT (all tasks done), not `phases_completed` membership. When all tasks are done, the build is complete → hand off to the review session (see below).

**First, run the "Hydrate TaskList from state.tasks" sub-step** (core `SKILL.md` § State Management). This is the critical entry point for the post-context-cap-rotation session path.

Before invoking `/work`, query `TaskList` and write the full `tasks` snapshot to `dev/local/autopilot/state.json`:
- `tasks`: array of `{"id": "<task-id>", "name": "<title>", "status": "pending|in_progress|completed", ...metadata}` for EVERY task. The snapshot **must preserve every field plan-tasks or the review gate's rework may have written** — at minimum: `model` (when set by plan-tasks tier classifier or Phase 6 escalation), `attempts` (the per-attempt log; see "Attempt logging" in `/work`), `estimated_tokens` and `est_context_peak` (when plan-tasks recorded a budget estimate), `qwen_eligible` and `qwen_excluded_reason` (when plan-tasks classified qwen eligibility — the Phase 9 Implementor Mix render reads them, PRD 00019). Stripping these on snapshot would break the hydration round-trip (subsequent sessions read them back into TaskList metadata) and lose Phase 6's tier-escalation history across the handoff. Treat the snapshot as merge-preserving over `state.tasks[i]`, not a three-field replacement.

`tasks_total`/`tasks_completed` are NOT written here — the `update-pidash-tasks.py` sync hook recomputes both from this `tasks` snapshot on every `TaskUpdate` (core `SKILL.md` § Task Counts).

**Include the task `id` field** — the `update-pidash-tasks.py` PostToolUse hook on TaskUpdate matches on it (via `taskId`) to sync status changes and recompute counts. This is mandatory.

**Capture `work_start_sha`** per the invariant in core `SKILL.md` § "Phase 3 invariants": once per PRD, before `/work` runs, only when unset — never re-captured on a cap-rotation or resume re-entry.

**Capture `repo_root` in the same step.** Run `git rev-parse --show-toplevel` in the work repo and write the absolute path to `state.repo_root`. Usually this equals the project root, but when the work repo is nested under a non-git project root (e.g. `~/.claude/skills/run-autopilot` under `~/.claude`), the review session needs it to run `git` (diff gathering, `head_sha` capture) in the right repo. **Bare-repo-backed project root** (the project root has no `.git` of its own because it is tracked by a bare repo with a separate work-tree, e.g. `~/.claude` under the `~/.buvis` bare repo with work-tree `$HOME`): a plain `git rev-parse --show-toplevel` from the project root FAILS, so do NOT default `repo_root` to the project dir (that silently mis-records it every PRD). Record the bare repo's work-tree root instead — `git --git-dir=<bare-git-dir> --work-tree=<work-tree> rev-parse --show-toplevel` (for `~/.buvis`-backed `$HOME` this resolves to `/Users/<you>`).

Invoke `/work` skill. It runs until all tasks complete.

While `/work` runs (Phases 3 and 6), it uses these superpowers when available (all conditional — autopilot works without them, quality improves with them):

| Superpower | Step | Purpose |
|-----------|------|---------|
| `test-driven-development` | 2.7 | Write failing tests before implementation |
| `systematic-debugging` | 4.5 | Root-cause analysis on errors |
| `verification-before-completion` | 5.5 | Run test suite before marking done |
| `requesting-code-review` | 5.7 | Per-task code review after commit |
| `receiving-code-review` | 5.7 | Evaluate review feedback before acting on it |

(Deliberately unused superpowers and the review-layering rationale: `references/design-rationale.md`.)

After completion, query `TaskList` again and update state: set `phase: "review"` and `next_phase: "review"`, write the updated `tasks` snapshot (the sync hook maintains `tasks_total`/`tasks_completed`). Do NOT add anything to `phases_completed` here — the `build` gate leaves no membership marker; review-loop convergence is the only `phases_completed` entry.

### Hand off to a fresh session for reviews

After the build completes (all tasks done), do NOT continue into the review phases in the same session — the review surface spawns multiple cloud reviewers and needs a clean context window. Run the **Session handoff procedure** (core `SKILL.md` § Session Loop) with the **build → review** site row, and print:

```
── AUTOPILOT ── PRD: {prd-name} ── Build complete ──────────────────
── AUTOPILOT ── handing off to fresh session for reviews ───────────
```

**STOP.** Do NOT invoke `/review-work-completion` (or any review lens) in this session (the handoff procedure's step 3 discipline applies).
