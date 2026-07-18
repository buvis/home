# Design Rationale (incident history)

The WHY behind autopilot's load-bearing rules. The rules themselves live where
they are enforced (core `SKILL.md` and the `phase-*.md` gate files); this file
holds the incident stories so the hot path stays lean. Nothing here is
normative — if a statement here ever contradicts a rule file, the rule file wins.

## Verified moves and the lifecycle mkdir (warden 00011)

A bare `mv wip/x.md done` with `done/` absent does not fail — it renames the
PRD to a stray file named `done` and the run continues unaware. The warden-00011
batch lost PRDs this way, and the same batch's over-broad "clean up temp files"
pass deleted `autopilot/` and `reviews/` wholesale, destroying the durable
review trail. Three rules came out of it: Phase 0's `mkdir -p` block runs
before any move; every lifecycle `mv` is followed by a destination-existence
check that PAUSEs loudly on failure; and cleanup deletes disposables by name,
never directories that hold durables (the Retention contract).
`test_autopilot_lifecycle.py` pins all three.

## Batch-identity rollover discriminator (stale-id forensics)

A `batch.id` minted weeks earlier kept being inherited across genuinely
separate batches because Phase 0 preserved any surviving `state.batch`. The fix
keys "genuinely closed" on `phase == "done"` AND `next_phase == ""` — only the
batch-end "No more PRDs" branch writes the empty `next_phase`. Keying on
`phase == "done"` alone would misfire: Phase 9 step 2 sets a transient
`phase: "done"` (with `next_phase: "done"`) BEFORE the verified wip→done move,
so a failed move that PAUSEs mid-PRD leaves that shape, and rolling over there
would wipe the in-progress batch's `completed_prds` and mint a spurious id.

## Persisted cycle increment (warden 00020)

The review loop ran cycles 1-3 but only bumped `state.cycle` in memory, so the
persisted value stayed 1. That blinded BOTH the cap gate (`cycle >= cap` never
fired — no cap-pause after cap cycles) and the wrapper-era thrash guard (the
progress key froze). Hence the rule in `phase-review.md` § After `/work`
returns: the increment is a durable write to `state.json`, not optional.

## Per-cycle review handoff (00067) — extra boots are cheap

Splitting the review loop into one cycle per session adds at most 2 extra
session boots per PRD (cap 3). Each boot re-reads the ~57K-token boot prefix,
but that is a prompt-cache READ within Claude Code's 1h cache TTL (verified
against the Claude Code docs, 2026-07-18), not a re-computation; PRD 00072
shrinks the re-read prefix further. The measured alternative — 2h review
sessions redone after a cap-kill — costs far more in both wall-clock and
dollars.

## No mid-turn questions in loop mode (2026-06-15)

An unattended session asked a mid-turn `AskUserQuestion` with no human present;
the loop sat idle 31 minutes once and 145 minutes again the same day. Loop mode
therefore bans `AskUserQuestion` outright: sites that would ask instead pause
by state (`phase: "paused"` + `pause_reason`) so the wrapper halts loudly, or —
post-PRD-00017 — stall the single PRD and let the batch continue.

## Git push failures defer (2026-06-15, locked signing agent)

A locked commit-signing agent on an unattended host is an expected condition,
not an error worth halting a batch for: it stalled the loop 145 minutes. The
Error Handling row therefore logs to `deferred_decisions[]`, leaves commits
local (the user pushes manually per Phase 9), and continues.

## Headless sessions, no signal file (PRD 00014)

The pre-00014 loop coordinated sessions through a signal file plus Stop-hook
choreography (exit-2 re-prompts, backgrounded-task liveness probes, foreign
Stop-event guards). That machinery was the recurring halt class — six distinct
strand/thrash postmortems patched it before 00014 deleted it. Headless
`claude -p` sessions make the turn boundary the session boundary, so
`state.json` alone is the hand-off contract and the entire class is gone.

## De-slop moved into the review roster

A standalone codex de-slop pass once ran from the `autoclaude` wrapper after
every commit. It was an unconditional external call that fell silently dead
when codex hit its usage limit — de-slopping just stopped, invisibly. Folding
it into Bob's doubt lens (with a Claude fallback) inside every review cycle
means the lens degrades loudly instead of vanishing.

## Commit history left as-is (Phase 9)

Phase 9 once ran a cherry-pick regroup engine that squashed/reordered the PRD's
commits. It never pushed — the user re-reviewed and pushed manually anyway — so
it was pure risk (conflict aborts, backup branches) for no shipped benefit.
Autopilot now leaves history alone; the user squashes manually before pushing.

## Batch catchup cache (Phase 1)

Between PRDs in the same batch on the same branch, a full `/catchup` re-gather
(diff, blast radius, reverse deps, GitHub state) costs ~60-95s and ~50K tokens
per PRD with no information gain — the capsule is already accurate. Hence the
4-hour/same-HEAD delta-refresh cache.

## Escalation diagnosis before tier bump (Phase 6)

The `haiku → sonnet → opus` rework chain assumes a review failure means the
model wasn't capable enough. The observed dominant failure mode is different: a
**spec-transmission gap**, where the task description never carried the PRD's
exact contract and the implementer built a self-consistent wrong thing. A
stronger model fed the same thin description fails the same way, at higher
cost. Root cause fix: `plan-tasks` copies the PRD contract verbatim into each
task (see `plan-tasks/SKILL.md` step 4); the Phase 6 caveat keeps the tier when
findings are predominantly spec-misread.

## Review-file gate stays on Stop (PRD 00016)

`review_coverage_hook.py` exit-2-blocks a done hand-off whose review file is
missing or malformed. Exit-2 Stop-hook blocking is proven to work in `-p` mode
(00014 spike, probe (c) — `dev/local/tmp/00014-headless-spike.md`), so the gate
survives the headless conversion as an in-session artifact-completeness check,
not loop orchestration.

## Superpowers deliberately not used

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

## Note on review layering

Per-task review (`/work` step 5.7) and the review gate's lens battery
(consensus, blind, doubt — every review cycle) are complementary, not
redundant. Per-task catches issues early before they compound. The consensus
lens catches cross-task coherence and integration issues. The blind lens
catches spec drift and gaps that implementation-aware reviewers miss by giving
a fresh agent only the spec. The doubt lens hunts residual findings and slop a
confident reviewer waves past. All are needed.

Per-task review is **tier-gated** (PRD 00044): `/work` step 5.7 dispatches the
per-task code reviewer only for `sonnet`- and `opus`-tier tasks; `haiku`-tier
tasks skip it (as does the opus-only Devon adversarial dispatch at step 2.85).
This does not leave haiku-tier work unreviewed — the mandated PRD-level lens
battery reviews every task's diff regardless of tier, so it covers haiku-tier
tasks that skipped the per-task layer. The gate drops only the per-task layer
on the cheapest tier while keeping the mandated lenses byte-untouched.
