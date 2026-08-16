# Gate-failure flow (step 5.5 default path)

Extracted verbatim from SKILL.md step 5.5 (situational: read it before the first gate failure of a batch; SKILL.md keeps the scope note, the retry snippet, and the `_AUTOPILOT_ESCALATION == "legacy"` branch).

### 5.5. Verify THIS task's tests pass

**Any other value / absent — diagnose→repair/escalate flow (default):**

Per-rung budgets are declared once in `model-ladder.md` § Per-rung budgets — cite, do not restate: Claude rungs (haiku/sonnet/opus) get 2 dispatches (initial + one feedback retry) before diagnosis; the codex rung gets 2 dispatches (initial + one feedback retry), and never a repair; the `fable` rescue rung gets 1 capability dispatch per PRD, ever (no feedback retry, no repair); the qwen rung gets 1 dispatch (no feedback retry — the existing one-shot carve-out, named the ladder's `qwen -> sonnet` capability edge); repair is capped at 1 per task, total, and is Claude-rungs only (qwen never repairs).

**Codex attempt classification — three arms.** Use the arms declared in `model-ladder.md` § Codex rung:

1. **Infra:** an unhealthy batch probe, watchdog timeout, or missing/empty `-o` file falls back to Claude at the task's tier with no `escalation_reason`.
2. **Infra (no-edit arm):** when the `-o` file is non-empty and the helper exited 0 but the run produced no working-tree change, classify the hook-blocked prose-only run as infra: fall back to Claude at tier, with no feedback retry and no `escalation_reason`, and record `cause: "codex_no_edit"`.
3. **Capability:** a step-5.5 test-gate failure after a run that did edit the tree enters diagnosis and escalates with a stamp.

The no-edit detector runs at the dispatch boundary, **not at step 5.5**. Step 5 commits the implementation before the step-5.5 gate, so the porcelain is clean at 5.5 for both a successful codex run and a no-edit run; checking there cannot distinguish them. Capture porcelain for the task's own file slice immediately before the codex dispatch, then capture it again immediately after the helper returns and before step 5's `git add` (both captures are checklist steps in `references/codex-implementor.md` § Codex dispatch); latch the comparison as `codex_no_edit` in the attempt record, and have step 5.5 read only that latched flag — never re-run `git status` here. Scoping both snapshots to the task's own file slice prevents a concurrent user edit elsewhere in the live worktree from masking this arm.

Both snapshots MUST use the same Git context as the `repo_root` invariant. A bare `git status` fails for a bare-repo-backed worktree: measured 2026-07-22, running `git status --porcelain <path>` from `/Users/bob/.claude` exits 128 with `fatal: not a git repository (or any of the parent directories): .git`, because `~/.claude` is tracked by the `~/.buvis` bare repo with work-tree `$HOME` and has no `.git` of its own. Use:

```bash
git --git-dir=<bare-git-dir> --work-tree=<work-tree> status --porcelain -- <file slice>
```

For this repo the context is `--git-dir=/Users/bob/.buvis --work-tree=/Users/bob`. If either snapshot exits non-zero, the probe is **INDETERMINATE**, not "no change": do not latch `codex_no_edit`; record the exit code in `codex_no_edit_probe_exit` and continue through the capability path normally. A broken detector must never silently reclassify real codex capability failures as infra. These classification semantics live as a hand-maintained model in `scripts/work_routing.py`, tested in isolation by `scripts/test_work_routing.py` — kept in sync with this prose by review, not by a test that goes red when the prose changes.

```
gate fail #1 at current rung → feedback retry: dispatch Ivan with the failure output, SAME tier
                                (haiku/sonnet/opus and codex rungs only, never fable - the qwen rung has no
                                feedback retry: its single gate failure goes straight to DIAGNOSE
                                below, per the 1-dispatch budget)
gate fail #2 at current rung → DIAGNOSE:
  1. Write task.description (from state.tasks[i].description, already in hand from step 1's
     pending scan) to dev/local/tmp/diagnose-task-<id>.txt and run:
       python3 ~/.claude/skills/work/scripts/diagnose_task.py <task-file> --repo-root <project-root>
     `<project-root>` = the dir containing dev/local/, resolved by walking up from cwd (same anchor
     as _walk_up.py) — NOT state.repo_root, which differs under a bare-repo-backed project.
     verdict "spec_gap" (exit 0) → REPAIR path below, if repair unused this task AND current rung
     is a haiku, sonnet, or opus rung, never fable (qwen never repairs — see budgets above)
  2. verdict "pass", OR the script errored (exit 2, shape-check inconclusive) → inline rubric
     judgment, this session, at its current tier: spec_gap | solid_spec, with a one-line
     justification, stamped as `diagnosis` on the diagnosed rung's attempt entry (see Attribution
     below). The orchestrator never overrides a deterministic spec_gap verdict from step 1.
REPAIR (spec_gap, repair not yet used this task, current rung is
  haiku, sonnet, or opus, never fable): fill the identified gaps (missing Contract, missing
  Acceptance criteria, dangling file references) from the PRD + design doc, rewrite the task
  description via `task-set-body <task-id> <body-file>` — the canonical store /work reads
  directly from `state.tasks[i].description` — and re-dispatch Ivan at the SAME tier ONCE.
  Stamp `repair_used:true` on that rung's attempt entry. A gate failure after the repair takes
  the solid_spec path below — repair is exhausted for this task.
ESCALATE (solid_spec, OR spec_gap with repair unavailable/already used, OR any qwen-rung spec_gap):
  1. Reset guard — capture `<candidate_head>` = `git rev-parse HEAD` first, then require BOTH:
     - **uncommitted:** `git status --porcelain` is empty (no foreign/uncommitted working-tree files), AND
     - **committed range:** `git rev-list <test_commit_sha>..<candidate_head>` contains ONLY this
       task's own implementation commit(s) (the commits step 5 made after the test commit).
     Passing the guards is necessary but NOT sufficient — a foreign commit can still land between the
     check and the reset (a live worktree; project_autopilot_head_moves_midreview), and `git reset
     --hard <test_commit_sha>` would silently discard it. So move the ref ATOMICALLY, never with a
     bare `git reset --hard` off a stale check:
     - both guards pass → compare-and-swap the branch ref to the test commit, succeeding ONLY if HEAD
       is still `<candidate_head>`: `git update-ref refs/heads/<current-branch> <test_commit_sha>
       <candidate_head>` (the third arg is git's old-value guard — the CAS; `<current-branch>` from
       `git rev-parse --abbrev-ref HEAD`). Then `git reset --hard` (the ref already points at the test
       commit, so this only cleans the worktree). `<test_commit_sha>` is this task's own test commit,
       captured in-session right after step 2.9 — never a prior task's commit.
     - the CAS fails (HEAD moved — a foreign commit raced in), OR either guard failed (foreign
       uncommitted files, or a foreign commit already in `<test_commit_sha>..<candidate_head>`) → do
       NOT reset; escalate fix-forward instead (dispatch the higher rung against the current tree +
       failing tests, no reset) and log the deviation on the attempt. Never discard commits or files
       this task did not create (memory: feedback_subagents_vs_live_worktree,
       project_autopilot_head_moves_midreview). Fix-forward is the safe default whenever the reset is
       not provably this-task-only AND atomic.
  2. Stamp the LOWER rung's entry: `outcome:"escalated"`, `diagnosis:<verdict>` (+
     `qwen_gate_failed:true` if that rung's implementor was qwen, + `repair_used:true` if a repair
     ran at that rung). **If the task's `state.tasks[i]` entry carries a review-flag escalation
     (`escalation_reason:"review_flag"` + `escalated_from`, set by /run-autopilot Phase 6 when this
     rung IS the review-flagged rework rung), copy both onto THIS lower-rung entry now** — Phase 6
     escalated INTO this rung, so the `review_flag` reason belongs here; capturing it before step 3
     clears it is what keeps the review-flag source recorded when a review-flagged task ALSO escalates
     in-loop (otherwise the reason would be lost on this entry and mis-stamped on the higher rung).
  3. `task-set-meta <task-id> <meta-json-file>` with the payload
     `{"model": "<new tier>", "escalation_reason": null, "escalated_from": null}` — one call, one
     payload file, three keys. The `model` key writes `state.tasks[i].model` directly in one locked
     write, so there is no separate mirroring step. Run it BEFORE the dispatch below, so the
     **Per-task model dispatch** rule picks up the escalated tier for Ivan and every downstream
     read this task (step 5.6, step 5.7's tier gate). The two `null` values
     **clear any `escalation_reason`/`escalated_from` from `state.tasks[i]` here** (`task-set-meta`
     deletes a key whose value is JSON `null`) — point 2 already copied a
     review-flag reason onto the lower-rung entry, and the higher in-loop rung records its OWN
     `escalation_reason:"gate_failure"` at point 5. Leaving the sticky `review_flag` in `state.tasks[i]`
     (which `task-set-meta` merges, not replaces) would make step 6's task-entry→attempt-entry copy mis-stamp
     `review_flag` onto this `gate_failure` rung.
  4. Dispatch ONE rung up (per `model-ladder.md` § Capability ladders — qwen -> sonnet skipping
     haiku, haiku -> sonnet -> opus) with a FAILURE SUMMARY: failing test names, the last
     gate-output excerpt, the diagnosis verdict, and the prior implementor + tier. **Codex carve-out:**
     after the second gate failure at the codex rung, DIAGNOSE and dispatch Claude at the task's OWN
     tier — never a repair and never one rung above the task's tier. The capability edge is
     `codex -> claude at the task's own tier`, so Claude-at-tier is the rung above codex.
  5. Stamp the HIGHER rung's NEW attempt entry: `escalation_reason:"gate_failure"`,
     `escalated_from:<prev tier>`.
  6. At the new rung the budget resets (initial + one feedback retry, per `model-ladder.md` §
     Per-rung budgets), then this same gate-failure flow re-applies if it fails again.
  Opus-rung exhaustion (2 failures at opus) flows into the existing abort/stall machinery (PRD
  00017) — do not invent a new halt class.
  A `fable` attempt has **no rung above it**: its gate failure goes straight to that same
  exhaustion path, never to an escalation (`model-ladder.md` § Capability ladders).
```

**Attribution row ownership** (one entry per rung/dispatch-group — never lump every field onto a single entry; see `references/attempt-logging.md` § Attribution row ownership):

| Field | Row it is stamped on |
|-------|----------------------|
| `diagnosis` | the **diagnosed** (lower) rung's entry |
| `qwen_gate_failed` | the qwen (lower) rung's entry |
| `repair_used` | the entry of the same-tier attempt that ran after a repair (that rung's entry) |
| `escalation_reason:"gate_failure"` | the rung escalated **INTO** (higher)'s entry |
| `escalation_reason:"review_flag"` | the review-flagged rework rung's OWN entry (Phase 6 escalated INTO it): copied from `state.tasks[i]` at step 6 if that rung exits there, or at ESCALATE point 2 (then cleared at point 3) if it escalates in-loop |
| `escalated_from` | the rung escalated **INTO** (higher)'s entry (both `gate_failure` and `review_flag` paths) |

For codex attribution, `attempts[].model` records the task's own tier (for example, `"sonnet"`) while `implementor: "codex"` carries the backend identity. This is the same split as qwen, whose attempt records `model: "sonnet"` with `implementor: "qwen"`. On a codex capability failure, stamp the codex entry `outcome: "escalated"` and `diagnosis: <verdict>`; the Claude entry it escalates into receives `escalation_reason: "gate_failure"` and `escalated_from: "codex"`.

**Pipeline stamping on escalation.** An in-loop escalation re-dispatches the implementor at the higher rung and re-runs the tier-appropriate post-implementor gates (step 5.7 reviewer for sonnet+, and this step-5.5 gate) — it does NOT re-run Devon (2.85; the tests are already committed). Stamp the escalated-into entry `pipeline:"lean"` (implementor + reviewer), never `"full"` — `"full"` stays reserved for a from-scratch opus task/rework that actually ran Devon.

**qwen capability breaker counter (this gate).** Guarded by `_AUTOPILOT_ESCALATION != "legacy"`, same as the routing consult in step 3. On an `implementor:"qwen"` attempt only: gate pass → reset `qwen_gate_failures_consecutive = 0`; gate fail → stamp that attempt `qwen_gate_failed:true` and increment `qwen_gate_failures_consecutive`; at 2 consecutive → latch `qwen_breaker = {tripped:true, after_task:<this task id>, failed_tasks:[<the two ids>], batch_id:<effective batch id>}` (batch-scope check as in step 3). Keys off the stored `qwen_gate_failed` field, not `outcome` (an escalated-away qwen entry reads `outcome:"escalated"`), keeping the increment jq-expressible. Rework attempts never touch the breaker — rework never routes qwen. A non-qwen task between two qwen failures leaves the counter unchanged (`run-autopilot/references/state-schema.md` `qwen_gate_failures_consecutive`).

**Deterministic precedence — two separately-scoped orderings** (`model-ladder.md` § Ordering; NOT one linear chain):
- **Routing-time** (step 3, per task): qwen breaker consult → memory-pressure gate → qwen infra preflight → dispatch.
- **Failure-classification** (here, or on a lost result per step 4.2): an infra failure (preflight fail, watchdog/lost result) falls back at the SAME tier and never enters diagnosis or touches the breaker; a capability failure (a real test-gate failure, this section) enters diagnosis, where repair precedes escalate.
