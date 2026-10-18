# Discovery: Plan a Port and Retire the Original at Parity

## Classification

Depth: standard | Date: 2026-08-27 | Status: elicitation complete
Elicited from the 2026-08-26 seed of the same number. Original source:
`discovery/inbox/skill-ideas-2026-07-14.md` (2026-07-14 transcript sweep; trashed
2026-08-26 once split into per-idea docs).

## Problem

Ports keep recurring, and each one hand-derives the same artifacts: what the
source does, what the target must match, who consumes it, when the original may
die. Without a parity gate the original never dies - it lingers half-alive while
the replacement grows. pidash proves it: the machine side was decommissioned in
`~/.claude` PRD 00063 on 2026-07-14, and six weeks later `gems 00071-retire-pidash`
still sits in the backlog with the original alive in the repo.

## Requirements

### Must have

1. **Skill `plan-port`** (verb-led). Input: a source and a target. Output: one
   port-plan document.
2. **Behavior-first feature inventory**: derive rows from the source's
   user-facing surface (commands, flags, inputs, outputs, README promises), then
   read the code only to catch behavior the docs never mention. Code-only rows
   are marked as such, because they are the ones nobody has judged yet.
3. **Parity matrix**: every row classified `port` / `drop` / `redesign`, each
   with a reason. No row without a reason.
4. **Drop calls are walked, not batched**: `port` and `redesign` rows are
   presented as one table for a single approval; every proposed `drop` gets an
   individual packet with evidence, per `rules/communication.md`. The plan records
   your ruling per drop row.
5. **Consumer and cutover analysis**: who calls the source today, what breaks at
   cutover, what must be repointed before the original dies.
6. **Phase list, not PRDs**: the plan names phases in dependency order and hands
   off; `create-prd` writes the actual PRDs one phase at a time.
7. **Retirement block**: the plan carries a section holding the matrix and one
   ready-made acceptance criterion per `port` row, in `create-prd`'s criterion
   shape, with a hand-off line telling `create-prd` to lift it verbatim into
   the retirement PRD. The original dies when those criteria pass review, not
   when someone feels done. (Reworded at the 2026-08-28 review: `plan-port`
   never writes the PRD, so the gate must be a plan-side artifact.)

### Nice to have

- A cutover row per consumer, so repointing is trackable rather than remembered.
- A one-line freshness stamp on the plan, so a stale matrix is visible when the
  retirement PRD is finally written months later.

### Out of scope

- Writing the PRDs. `create-prd` owns PRD format and numbering; duplicating those
  rules here is the reference-rot pattern PRD 00081 exists to prevent.
- The HOW of the target's design - `design-solution` owns that, and `plan-port`
  hands off to it.
- Repo-health roadmapping. `assess-evolution` already emits phased, session-sized,
  pipeline-numbered PRD roadmaps with a deletion ledger; `plan-port` stays on
  what-at-parity and reuses that ordering discipline rather than re-implementing it.
- **intake-issues** (gh issues -> elicit -> PRD pipeline), the adjacent idea cut in
  the same 2026-07-14 sweep. Still cut: the repos are solo-developed and there is
  no external issue traffic.

## Constraints

- Autopilot drains PRDs by **lowest sequence number**, so a phase list whose
  numeric order does not equal its dependency order makes the pipeline do the
  wrong work first (`assess-evolution` §7 states the same rule).
- Skills live in `~/git/src/github.com/buvis/agent-skills` and reach
  `~/.claude/skills` through the `~/.agents` braid. Never edit through the link
  farm.
- The plan is a working document: `dev/local/`, gitignored, under the layout the
  `enforce_prd_location.py` hook enforces. No new top-level directories.
- A port often spans two repos, and `dev/local/` is per-repo. The plan has to
  pick a home rather than assume one.

## Codebase Context

- **The roadmap engine already exists**: `assess-evolution/SKILL.md` §7 emits
  phased, session-sized PRDs with explicit dependencies, numbering matched to the
  work-selection mechanism, and a downstream deletion ledger. `plan-port` produces
  the parity matrix that engine lacks, and nothing else it already has.
- **Live example, mid-flight**: the postup port occupies `gems` PRDs 00063-00068
  (scaffold, enrich, web core, web views, serve, TUI), `00070-postup-brief-portfolio-cutover`,
  `00072-surface-meta-budget-in-postup`, with `00069-postup-autopilot-data-layer`
  on hold - a chain hand-derived without a parity matrix.
- **Live counter-example**: `gems 00071-retire-pidash` is still in backlog while
  `~/.claude 00063-decommission-pidash` finished 2026-07-14. Retirement split
  across two repos, and the half in the other repo stalled.
- **Hand-off targets**: `create-prd` (PRD authorship), `design-solution`
  (autopilot plugin, the HOW), `elicit-requirements` (this skill) for a port whose
  target is not yet specified.

## Success Criteria

- Run on the live postup port, `plan-port` produces a matrix in which every
  section of the brief `brief-portfolio` renders and every script flag it
  documents (both enumerable from `brief-portfolio/SKILL.md`) appears as a row,
  and names the condition under which `brief-portfolio` may be deleted.
- Every matrix row carries a classification **and** a reason; a row without a
  reason is a defect, provable by reading the emitted table.
- The retirement PRD written from the plan contains one acceptance criterion per
  `port` row, and `review-work-completion` can therefore fail it on an unmet row.
- Every proposed `drop` appears in the plan with the user's recorded ruling; no
  drop is applied silently.
- The phase list is dependency-ordered, and no phase depends on a later one.

## Risks

- **Overlap with `design-solution` and `assess-evolution`**: three skills that
  emit plans invite drift. Mitigation: `plan-port` outputs a matrix and a phase
  list only, cites the other two by name, and writes no PRD and no design.
- **Behavior-first inventory misses undocumented behavior**: the code cross-check
  is a must-have, and rows found only in code are flagged so they get judged
  rather than assumed.
- **Walkthrough fatigue on a large source**: many drops means a long sitting, and
  late drops get waved through. Mitigation: only drops are walked; if a single
  port produces more than a screen of them, that is itself a signal the port is
  too big for one plan. The skill says so once before the first drop packet and
  continues; splitting is the user's call.
- **The matrix rots between plan and retirement**: months pass. Mitigation:
  `create-prd` lifts the plan's retirement block at write time, so the gate is
  the copy inside the retirement PRD, never the stale plan.

## Open Questions

- Which repo hosts the port plan when source and target live in different repos?
  The postup case spans `agent-skills` and `gems`; pidash's retirement split
  across `~/.claude` and `gems` and half of it stalled.
- Does the retirement PRD belong to the source repo (where the code dies) or the
  target repo (where parity is proven)? The pidash split suggests one of them
  should own it outright.
- Does `create-prd` need an edit to honour the retirement-block lift
  (Must-have 7), or does the plan's hand-off line suffice? If an edit, it ships
  in the same `agent-skills` PRD.

## Evidence (2026-07-14)

Three ports in flight or recently done, each hand-derived: brief-portfolio ->
the gems `postup` gem (7 PRDs, discovery 00062), pidash -> tracon ("port
pipeline/attention/sort visuals first"), and the sonnet-run.sh backend swap off
copilot.

## Freshness check 2026-08-26

- Still unbuilt: no `plan-port` skill anywhere.
- pidash finished the pattern the hard way: the machine-side decommission landed
  as PRD 00063 (hooks purged, `~/.pidash` removed, docs scrubbed) - a retirement
  checklist produced by hand - and the gems half is still queued.
- The postup port is still open, so the next user of this skill exists.
- Ports since then (the autopilot plugin extraction, skills moving to
  `agent-skills`) were repo moves rather than behavior ports, so they neither
  confirm nor weaken the idea.

## Discovery Log

### Q1: Does `plan-port` need to exist as a skill at all?

**Answer**: **Build it as sketched.** Asked because the scan found
`assess-evolution` already emitting phased, dependency-ordered, pipeline-numbered
PRD roadmaps with a deletion ledger, and the seed itself claims the parity matrix
is the only genuinely new artifact - so a template consumed by the existing
pipeline was the recommended, lazier option. Overruled in favour of a named,
discoverable skill. Accepted cost: another entry in the boot listing, and
deliberate discipline to keep it from re-implementing the roadmap engine (handled
by the Out of scope section). Also rejected: a port mode bolted onto
`assess-evolution`, and hand-deriving the next port.

### Q2: Where does the parity gate live, so the original actually dies?

**Answer**: **The matrix goes inside the retirement PRD**, and every `port` row
becomes an acceptance criterion there. One artifact, no sync problem, and it
inherits enforcement that already exists - a PRD cannot finalize with unmet
acceptance criteria. Accepted: the gate only starts biting once the retirement
PRD is written, which on a long chain is months after the drop calls. Rejected: a
standalone matrix file (nothing reads it, and an unread file is how pidash
lingered), a file plus generated criteria (two artifacts that drift), and a
runnable check per row (heavy enough that the matrix shrinks to what is easy to
verify).

### Q3: Who decides that a source feature gets dropped rather than ported?

**Answer**: **The skill proposes; drops are walked one at a time.** `port` and
`redesign` rows are batch-approved as a table; each proposed `drop` gets an
individual packet with evidence. The asymmetry is deliberate - a wrong `port`
costs effort, a wrong `drop` costs a feature. Rejected: whole-matrix approval
(rubber-stamping, and a bad drop hides in a table), consumer-evidence rules (a
feature used twice a year looks dead in a solo portfolio), and never-drop (it
inflates the port, and shedding weight is often the reason to port).

### Q4: What should the feature inventory be derived from?

**Answer**: **Behavior first, code as cross-check.** Rows come from the source's
user-facing surface; the code is read only to catch behavior the docs never
mention. This answers the seed's own risk - a code-derived matrix ports bugs
along with features. Accepted: behavior nobody wrote down can still slip through,
mitigated by flagging code-only rows. Rejected: code-derived (most rows describe
plumbing you cannot judge), behavior-plus-code-sites (doubles the work on an
artifact whose value is being cheap), and tests-as-spec (untested behavior
silently becomes non-parity).

### Q5: Who writes the phased PRD chain the port needs?

**Answer**: **`plan-port` emits the plan; `create-prd` writes the PRDs**, one
phase at a time. PRD format rules stay in a single skill, and numbers are
assigned at write time in the order autopilot drains them. Accepted: a two-step
hand-off, and `create-prd` runs once per phase. Rejected: `plan-port` writing the
chain (a second home for PRD format rules, the exact reference-rot pattern PRD
00081 prevents), calling `create-prd` per phase (a long fragile session with no
resume point), and filing numbered stubs (placeholders are forbidden, and a stub
is a PRD autopilot may try to drain).

### Inferred (not asked - answered by the scan or standing rules)

- Plan home: `dev/local/discovery/`, sharing the PRD sequence (decided),
  because `create-prd` consumes discovery docs and the GC contract already
  treats that directory as curated. The cross-repo case stays an open question.
- Phase ordering: numeric order must equal execution order, because autopilot
  selects the lowest sequence number.
- Skill home: the `agent-skills` repo, reached through the `~/.agents` braid.
