# Discovery: Encode an Incident as an Invariant

## Classification

Depth: comprehensive | Date: 2026-08-28 | Status: elicitation complete
Elicited from the 2026-08-26 seed of the same number. Original source:
`discovery/inbox/skill-ideas-2026-07-14.md` (2026-07-14 transcript sweep; trashed
2026-08-26 once split into per-idea docs).

## Problem

Every serious incident here already gets converted into an invariant by hand: a
guard, a memory, a rule, sometimes a PRD. The ritual works and has no name, no
checklist, and no trigger - it runs only when the pain is fresh enough to force
it. Incidents that hurt less get a memory at best, or nothing. At least ten
conversions were hand-built in two months, and the pattern kept firing after
that: the write-scope fence closing its bash hole, the `rg`-is-a-function fix
that had silently killed cartographer-echo's gate for months, the instinct
pipeline's post-mortem retirement. Each hardening makes cheap-tier unattended
runs safer, so an unperformed ritual costs money as well as repeats.

## Requirements

### Must have

1. **Skill `encode-incident`** (verb-led), **manual only**. No hook, no phrase
   detection, no auto-fire.
2. **Scope v1: meta and loop incidents** - the autopilot stack, the hooks, the
   wrapper, the machine. Dev-repo bugs are deferred.
3. **Reconstructed 5-whys**: the skill builds the chain from the session's facts,
   marks the link it is least confident in, and asks exactly one question about
   that link.
4. **Memory is the default outcome.** Every encoding writes a memory file plus
   its `MEMORY.md` line.
5. **A guard must clear a written bar** before it is proposed: what it catches
   that a memory cannot, what it costs on every call, its own failure mode, and
   whether it fails open or closed. No case, no guard.
6. **Premise check across every hook location** before proposing a guard - the
   `settings.json` hooks block, `hooks/dispatch.py` `ROUTES`, every active
   plugin's `hooks/hooks.json` discovered from the installed cache at run time
   (five carry one today), `~/.claude/warden.yaml`, `~/.codex/hooks`, and the
   wrapper breakers. A guard proposed against the wrong location is worse than
   none.
7. **Write split by reversibility**: the skill writes the memory, its
   `MEMORY.md` line, and a `rules-library/rationalizations.md` entry when the gap
   was discipline. It **proposes** the guard and any PRD for approval.
8. **Compact reasoning in the memory body**: the root cause and the one-line
   reason a guard was rejected, capped at a few lines, so the next incident in
   the class does not re-argue a settled question.
9. **Retroactive mode**: the skill accepts an existing memory file as input
   instead of a session, so a memory with no guard behind it can be encoded later
   through the same path. In this mode the input memory is updated in place
   (chain and guard verdict appended); no second file, and `MEMORY.md` changes
   only if the description does.

### Nice to have

- A failing repro test where the incident is testable, shipped with the guard.
- A blast-radius line on each memory, so an unguarded incident's cost is visible
  when someone later asks whether the bar should have been cleared.

### Out of scope

- Dev-repo bug encoding (`bug -> regression test -> sweep-fix handoff -> project
  memory`). Deferred: every cited example is a meta incident, and the handoff
  target `sweep-fix` is discovery 00151 with no PRD yet.
- Any automatic trigger.
- A bulk pass over the memory plane. Retroactive encoding is one memory at a
  time, through the same path.
- Installing the guard. Guards are proposed, never self-installed.

## Constraints

- **`~/.claude` work is meta-spend** against the <=30% monthly ceiling, and this
  skill is entirely meta.
- **Memories are the only durable plane**: `projects/<hash>/memory/` for
  project-scoped facts (committed to the cellar repo, which `~/.claude/projects`
  symlinks into - verified 2026-08-28, it is not `~/.buvis`), `~/.claude/` files
  committed to the `~/.buvis` bare repo for global ones such as `rules-library/`. The instincts plane was retired 2026-08-26 for never
  delivering a fact; do not rebuild a statistical one.
- **`dev/local/` is gitignored and GC'd**, so nothing whose value outlives the GC
  horizon may live there alone.
- **Guards are load-bearing on every tool call.** `PostToolUse` exit 2 cannot
  block; only `PreToolUse` can. A guard proposal that assumes otherwise is wrong
  before it is written.
- Skills live in `agent-skills` and reach `~/.claude/skills` through the
  `~/.agents` braid.

## Codebase Context

- **Hook locations, enumerated 2026-08-27** (the premise check must sweep all of
  them):
  - `~/.claude/settings.json` hooks block - six registrations, mostly routing to
    `dispatch.py pre|post|stop`, plus `reinject_contract_card.py` and
    `notify.py`.
  - `~/.claude/hooks/dispatch.py` `ROUTES` - eight routes, `Route(event, matcher,
    name, path, timeout, kind)`; `PLUGIN_OWNED` and `RETIRED` sets document what
    deliberately is not there.
  - Plugin manifests in the installed cache: `aegis`, `warden`, `loupe`,
    `ponytail`, `autopilot`, each `hooks/hooks.json`. Several versions are cached
    per plugin; only the active one fires.
  - `~/.claude/warden.yaml` (plus per-repo `.claude/warden.yaml`) - the same
    config drives Claude Code, Codex and Copilot CLI.
  - `~/.codex/hooks` - gitignored except `notify.py`, a buvis-tracked symlink.
  - Wrapper breakers in the autopilot loop (`autopilot loop`), where the memory
    breaker and net-retry cap already live.
- **Rationalizations**: `~/.claude/rules-library/rationalizations.md`, parsed into
  `{excuse: (why, counter)}` by `hooks/cartographer-echo.py:750` and cited inline
  in its deny messages. Entry shape is `### "excuse"` plus `- **Why it's
  wrong**:` and `- **Counter-action**:` bullets. **The seed's path
  `rules/rationalizations.md` is wrong.**
- **Memory plane**: 70 memory files plus `MEMORY.md` in
  `projects/-Users-bob--claude/memory/`; frontmatter is `name` / `description` /
  `metadata.type` with types `user | feedback | project | reference`.
- **Similar implementations**: `debug-stuck-agent` (diagnosis, no artifacts),
  `review-with-doubt` (skeptical pass), `spike` (throwaway build). None of them
  emits invariants.

## Approach

- **Chosen**: a manual, single-run skill that reconstructs the chain, always
  writes the memory, and proposes the guard only against a written bar, with the
  premise check sweeping every hook location first.
- **Why**: the ritual already works by hand; what it lacks is a name, a
  checklist, and a bar for the expensive half. Making the cheap artifact the
  default and the expensive one argued keeps the guardrail stack growing on
  evidence rather than on adrenaline.
- **Rejected alternatives**:
  - *Auto-triggering* on batch-report stalls, memory writes, or phrase detection:
    an incident is a judgement call, and loop stalls are common and mostly
    boring, so any detector becomes wallpaper. Phrase matching on natural
    language is the same false-positive machine as the codex exit-4 bug.
  - *Proposing everything and writing nothing*: that is the hand-built ritual
    with extra steps, and the hand-built ritual is what fails to run.
  - *Writing the guard too*: it manufactures hooks, the seed's own top risk.
  - *Deferring memory writes to discovery 00147's queue*: 00147 is a three-slice
    epic with zero PRDs; depending on it blocks this skill indefinitely.
  - *Guards only on the second occurrence*: the cargo OOM locked the machine out
    once, and a rule that waits for a repeat is unacceptable where guards matter
    most.
  - *A bulk retro sweep over the 70 memories*: a batch of guard proposals is the
    proliferation the bar exists to prevent.

## Success Criteria

- An encoding run ends with the memory file and its `MEMORY.md` line committed
  to the cellar repo and, when the gap was discipline, one
  `rules-library/rationalizations.md` entry committed to `~/.buvis`; nothing
  else is written without approval.
- Every guard proposal names the hook location it would occupy, and that location
  is one of the enumerated set; a proposal naming a location that does not exist
  is a defect the skill must catch, not the reviewer.
- Every guard proposal answers all four bar questions. A proposal missing one is
  not presented.
- The memory body carries the root cause and, where a guard was rejected, the
  one-line reason - readable without opening any other file.
- Pointed at an existing memory instead of a session, the skill produces the same
  package. Verified on the codex exit-4 memory, which today has no guard.
- The skill never fires unasked: absent from `dispatch.py` `ROUTES` and from
  every plugin `hooks.json`.

## Risks

- **Guard proliferation**: the written bar is a soft brake and this skill is
  fluent by construction, so it can argue its way past prose. Mitigation: memory
  is the default and the rejected-guard reason is recorded, which makes a pattern
  of clearing the bar visible over time.
- **A guard proposed against the wrong hook location** is worse than none
  (`feedback_hook_discovery_scope`). Mitigation: the premise check sweeps the
  enumerated set and fails the proposal when it cannot enumerate it.
- **A confidently wrong reconstructed chain** gets no correction, because the
  skill also chooses which link to question. Mitigation: the chain is written
  into the memory, so a wrong root cause is visible later rather than buried in a
  session.
- **Two writers of the memory plane**: discovery 00147 plans to write memories
  too. Mitigation: whichever ships second reconciles; recorded as an open
  question rather than designed around now.
- **Memory bloat**: incident memories carry a chain, and every memory is loaded
  for recall. Mitigation: the cap is a few lines, and the chain is the root cause
  only, not the narrative.

## Open Questions

- How do this skill and discovery 00147's distiller share the memory plane -
  separate types, one writer, or a merge at review time?
- Does a rejected guard get re-proposed if the same incident class recurs, and
  what marks the recurrence?
- Should the repro test be mandatory when the incident is testable, or does that
  reintroduce the ceremony that stops the ritual being performed?
- Which memory type does an incident memory take - `feedback` (guidance with a
  why) or `project`? Both fit, and the choice changes how recall surfaces it.

## Evidence (2026-07-14, extended)

At least ten hand-built incident -> invariant conversions in the preceding two
months: cargo OOM -> three-layer guard; warden ask-deadlock -> unattended gate;
usage-limit idling -> detector plus auto-wait; network death -> capped retries;
headless bg-bash kill -> watcher plus env knob; mid-review HEAD moves -> diff
scoping; codex exit-4 -> salvage path; write-scope fence -> bash hole closed
(PRD 00145); `rg`-as-function -> `_resolve_rg()` in cartographer-echo;
instinct pipeline -> retired with a do-not-rebuild memory.

## The payoff that is not obvious

Every encoded incident hardens the guardrail stack, and the guardrail stack is
what makes cheap-tier unattended runs safe. More encoded incidents means more
confidence at lower tiers, which bends the cost curve. It converts pain into
cheaper batches.

## Freshness check 2026-08-26

- Still unbuilt: no `encode-incident` skill anywhere.
- The pattern kept firing after 2026-07-14: the write-scope fence closing its
  bash hole (PRD 00145), the `rg`-is-a-function fix that had silently killed
  echo's gate, the instinct pipeline's post-mortem retirement. All hand-built.
- `rationalizations.md` is live at runtime via `hooks/cartographer-echo.py`, so
  the rationalizations output still has a real consumer.
- The named first candidate - the codex exit-4 salvage path, a memory with no
  guard - is still a memory with no guard.

## Discovery Log

### Q1: What triggers an incident encoding?

**Answer**: **Manual only.** An incident is a judgement call - the cargo OOM and
a flaky test look identical to any detector - and a wrong auto-fire spends a full
5-whys and guard proposal on nothing. Accepted: it fires only when the pain is
fresh, so the quieter incidents keep getting a memory at best. Rejected: a
batch-report nag (loop stalls are common and become wallpaper), a memory-write
nag (most memory-only decisions are correct), and phrase detection (the same
false-positive machine as the codex exit-4 bug).

### Q2: Does the skill write the artifacts, or propose them?

**Answer**: **Writes the memory, its `MEMORY.md` line and the rationalizations
delta; proposes the guard and any PRD.** The split falls on reversibility - a
memory is one file you can delete, a guard runs on every tool call forever.
Accepted: it becomes a second writer of the memory plane alongside discovery
00147, needing reconciliation later. Rejected: proposing everything (the
hand-built ritual with extra steps), writing the guard too (manufactures hooks),
and deferring memories to 00147's queue (blocks this skill behind an epic with no
PRDs).

### Q3: How should the 5-whys be produced?

**Answer**: **Reconstructed, then one question at the weakest link.** One
decision instead of five, aimed where your knowledge beats the model's - usually
the step where the answer is history rather than evidence. Accepted: choosing the
weakest link is itself a judgement, so a confidently wrong chain with a
confidently wrong marker gets no correction. Rejected: full reconstruction with
no question (drifts toward what the model already believes), a live five-question
interview (ceremony at the worst moment), and skipping the chain (guards the
symptom, not the class).

### Q4: How is the guard budget enforced?

**Answer**: **Memory is the default; a guard must clear a written bar** - what it
catches that a memory cannot, its per-call cost, its own failure mode, and
whether it fails open or closed. Accepted: prose bars are soft and this skill is
fluent. Rejected: a hard cap where a new guard retires an old one (arbitrary
number, and a needed guard at a full quota turns the brake into paperwork), a
ponytail pass per proposal (extra dispatch, and it judges the guard without
seeing the stack), and guards-on-second-occurrence (unacceptable for
machine-lockout-class incidents).

### Q5: Does the skill cover dev-repo bugs too?

**Answer**: **Meta and loop incidents only for v1.** All ten pieces of evidence
are meta incidents, so v1 is built against real cases, and it ships without
waiting on `sweep-fix` (discovery 00151, no PRD yet). Accepted: the bug-fix
discipline rule stays unenforced in the product repos. Rejected: both paths in
one skill (doubles the surface and depends on unbuilt work), dev-only (no
evidence behind it), and a pointer-only dev path (restating the standing rule is
what already fails).

### Q6: Where does the incident's reasoning live?

**Answer**: **A compact chain in the memory body** - root cause plus the one-line
reason a guard was rejected, capped at a few lines. The guard bar's value is
being reviewable months later, and memories are the only plane here that is both
committed to buvis and loaded into future sessions. Accepted: every incident
memory is slightly fatter, paid in recall. Rejected: no record (the next incident
re-argues a settled question), a post-mortem in `dev/local/audit-results/`
(gitignored and GC'd, so it expires), and a zettel in `~/bim/` (durable but never
loaded when a guard decision is being made).

### Q7: What about the backlog of past incidents never fully encoded?

**Answer**: **No batch - the skill accepts a memory file as input.** Retroactive
encoding is the same path pointed at a memory instead of a session, so the known
gap (codex exit-4, a memory with no guard) can be closed without a migration.
Accepted: it still depends on choosing which memory to point at. Rejected:
out-of-v1 entirely (ships without fixing the case it was written for), a sweep
over the memory plane (a batch of guard proposals is the proliferation the bar
prevents), and a ranked report (another list needing action, which is the
original disease).

### Contradiction check

Answers were re-read as a set. Q4's default-to-memory and Q6's chain-in-memory
reinforce each other: the bar's argument and its rejection both land in the
artifact that is always written. Q1's manual trigger and Q5's meta-only scope
narrow consistently. The only unresolved tension is Q2 against discovery 00147's
planned memory writer, recorded as an open question rather than silently designed
around.

### Inferred (not asked - answered by the scan or standing rules)

- Hook-location set for the premise check: enumerated above from
  `settings.json`, `dispatch.py`, every active plugin manifest (discovered live,
  five today), `warden.yaml`, `~/.codex/hooks` and the wrapper.
- Rationalizations path and entry shape corrected: `rules-library/`, not
  `rules/`.
- Guard mechanics: only `PreToolUse` can block, so a proposal relying on
  `PostToolUse` to gate is invalid on arrival.
