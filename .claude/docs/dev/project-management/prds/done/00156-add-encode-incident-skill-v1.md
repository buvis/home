# Encode an Incident as an Invariant

Source: `~/.claude/dev/local/discovery/00154-encode-incidents-as-invariants.md`
(elicitation complete 2026-08-28).

## Overview

### Problem Statement

Every serious incident here already gets converted into an invariant by hand: a
guard, a memory, a rule, sometimes a PRD. The ritual works and has no name, no
checklist and no trigger, so it runs only when the pain is fresh. At least ten
conversions were hand-built in two months - cargo OOM to a three-layer guard,
warden ask-deadlock to an unattended gate, the write-scope fence closing its bash
hole, the `rg`-is-a-function fix that had silently killed cartographer-echo's
gate for months. Quieter incidents get a memory at best, or nothing. Each
hardening makes cheap-tier unattended runs safer, so an unperformed ritual costs
money as well as repeats.

### Target Users

The solo maintainer, right after a meta or loop incident - the autopilot stack,
the hooks, the wrapper, the machine - and later, pointed at an old memory that
never got its guard decision.

### Success Metrics

- An encoding run ends with a memory file and its `MEMORY.md` line committed to
  the cellar repo, plus a `rules-library/rationalizations.md` entry committed to
  `~/.buvis` when the gap was discipline. Nothing else is written without
  approval.
- Every guard proposal names a hook location that actually exists, and answers
  all four bar questions.
- Pointed at a fixture memory with no guard, the skill produces the same package
  it would from a live session.
- The skill never fires unasked: absent from `dispatch.py` `ROUTES` and from
  every plugin `hooks.json`.

## Functional Decomposition

### Capability: Chain reconstruction

#### Feature: Reconstruct the 5-whys from the session

- **Description**: Build the causal chain from facts the session already
  established.
- **Inputs**: The live session, or an existing memory file in retroactive mode.
- **Outputs**: A five-link chain ending at a root cause, with one link marked as
  the least confident.
- **Behavior**: The skill reconstructs rather than interviews - one decision
  instead of five, aimed where the user's knowledge beats the model's (usually
  the link where the answer is history rather than evidence). It asks exactly one
  question, about the marked link, and nothing else.

### Capability: Guard argument

#### Feature: Sweep every hook location before proposing a guard

- **Description**: Check the premise that a guard could live where it is
  proposed.
- **Inputs**: The live hook surface.
- **Outputs**: The enumerated set of live hook locations.
- **Behavior**: Sweeps the `~/.claude/settings.json` hooks block,
  `~/.claude/hooks/dispatch.py` `ROUTES` (including its `PLUGIN_OWNED` and
  `RETIRED` sets), every active plugin's `hooks/hooks.json` discovered from the
  installed cache at run time (five carry one today), `~/.claude/warden.yaml`
  plus any per-repo `.claude/warden.yaml`, `~/.codex/hooks`, and the wrapper
  breakers in `autopilot loop`. A proposal naming a location outside the
  enumerated set is a defect the skill catches, not the reviewer. When the sweep
  cannot enumerate a location, the proposal fails rather than guessing.

#### Feature: Hold every guard to a written bar

- **Description**: Make the expensive artifact argue for itself.
- **Inputs**: The reconstructed chain and the hook-location set.
- **Outputs**: A guard proposal answering four questions, or no proposal.
- **Behavior**: The four questions are: what it catches that a memory cannot,
  what it costs on every call, its own failure mode, and whether it fails open or
  closed. A proposal missing one is not presented. `PostToolUse` exit 2 cannot
  block, so a proposal that relies on `PostToolUse` to gate is invalid on
  arrival; `PreToolUse` and `Stop` both block on exit 2. (Corrected 2026-08-30
  during implementation review: this line read "only `PreToolUse` can block",
  which is false - `review_coverage_hook.py:8-10` is a live blocking `Stop` hook,
  and `dispatch.py:227-241` treats `Stop` the same as `PreToolUse`.) Guards are proposed, never installed. A failing
  repro test ships with a guard where the incident is testable, but it stays
  optional - mandatory ceremony is what stops the ritual being performed at all.

### Capability: Durable write

#### Feature: Always write the memory

- **Description**: Make the cheap artifact the default outcome.
- **Inputs**: The chain, the guard verdict.
- **Outputs**: A memory file in `~/.claude/projects/<hash>/memory/` plus its
  one-line `MEMORY.md` pointer.
- **Behavior**: Every encoding writes a memory, whether or not a guard is
  proposed. Type is `feedback` - the memory is guidance with a why, and the type
  already mandates the `**Why:**` and `**How to apply:**` lines the encoding
  produces. This also keeps the plane split from discovery 00147's distiller,
  which proposes `project` memories through its own queue.

#### Feature: Carry compact reasoning in the memory body

- **Description**: Stop the next incident re-arguing a settled question.
- **Inputs**: The root cause and the guard verdict.
- **Outputs**: A few lines in the memory body: the root cause, and where a guard
  was rejected, the one-line reason.
- **Behavior**: Capped at a few lines - the root cause, not the narrative.
  Readable without opening any other file.

#### Feature: Record a rationalization when the gap was discipline

- **Description**: Feed the excuse back into the live gate.
- **Inputs**: The excuse that let the incident happen, when there was one.
- **Outputs**: One entry in `~/.claude/rules-library/rationalizations.md`, shaped
  `### "excuse"` plus `- **Why it's wrong**:` and `- **Counter-action**:`.
- **Behavior**: Written, not proposed - it is one reversible file entry, and
  `hooks/cartographer-echo.py` parses it live into deny messages. Only written
  when the gap was discipline rather than mechanism.

#### Feature: Encode retroactively from a memory file

- **Description**: Close old incidents through the same path.
- **Inputs**: An existing memory file instead of a session.
- **Outputs**: The same package - chain, guard verdict, updated memory.
- **Behavior**: The input memory is updated in place; the chain and guard verdict
  are appended. No second file, and `MEMORY.md` changes only if the description
  does. One memory at a time - never a bulk pass over the plane, which would
  produce exactly the guard proliferation the bar exists to prevent. Re-running
  on a memory that already carries a rejected-guard line treats the rerun as the
  recurrence marker: the guard is re-proposed and the memory records the second
  occurrence.

## Structural Decomposition

### Repository Structure

Paths are relative to the `~/.claude` repo root, so `skills/` here is
`~/.claude/skills/`.

```
skills/
└── encode-incident/
    ├── SKILL.md                        # Maps to: all three capabilities
    ├── references/
    │   └── hook-locations.md           # Maps to: Guard argument (the premise sweep)
    └── assets/
        └── incident-memory-template.md # Maps to: Durable write
```

This skill is Claude-only and stays out of the `agent-skills` repo. Its whole job
is sweeping Claude's own config surface - `settings.json`, `dispatch.py` `ROUTES`,
plugin `hooks.json`, `warden.yaml` - so it has nothing to say on Codex or Copilot,
and that repo keeps host-locked skills out of `skills/` because `.braidignore`
cannot hide them from those hosts. Same call as `audit-echo` and
`extract-plugin`, which live here for the same reason.

### Module: encode-incident skill body

- **Maps to capability**: Chain reconstruction, Guard argument, Durable write
- **Responsibility**: The single-run workflow - reconstruct, ask one question,
  sweep the hook locations, write the memory, argue or drop the guard. Manual
  only; scope v1 is meta and loop incidents.
- **Exports**:
  - `SKILL.md` frontmatter with a trigger-led description under 250 chars
  - A `## Dependencies` section naming `rules-library/rationalizations.md`
    (consumed live by `hooks/cartographer-echo.py`), the auto-memory frontmatter
    contract in `rules/memory.md`, and the cellar-backed
    `~/.claude/projects/<hash>/memory/` plane

### Module: hook-locations reference

- **Maps to capability**: Guard argument
- **Responsibility**: The enumerated hook surface the premise sweep must cover,
  and how to discover the plugin half live rather than from a pinned list.
- **Exports**: The location list and the discovery procedure.

### Module: incident-memory template

- **Maps to capability**: Durable write
- **Responsibility**: The memory file's shape - frontmatter, the compact chain,
  the guard verdict line, `**Why:**` and `**How to apply:**`.
- **Exports**: The template the skill fills in.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **hook-locations reference**: without it, no guard proposal can be checked
  against a real location.
- **incident-memory template**: fixes the always-written artifact's shape.

### Core Layer (Phase 1)

- **encode-incident skill body**: Depends on [hook-locations reference,
  incident-memory template]

### Integration Layer (Phase 2)

- **retroactive validation**: Depends on [encode-incident skill body]

## Implementation Phases

### Phase 0: Foundation

**Goal**: The two reference artifacts exist and match the live machine.

**Tasks**:

- [ ] Write `skills/encode-incident/references/hook-locations.md` enumerating the
  `settings.json` hooks block, `dispatch.py` `ROUTES`, live plugin
  `hooks/hooks.json` discovery from the installed cache, `warden.yaml` (global
  and per-repo), `~/.codex/hooks`, and the `autopilot loop` wrapper breakers (no
  deps)
  - Premise: five installed plugins carry a `hooks.json` today (`aegis`,
    `warden`, `loupe`, `ponytail`, `autopilot`) and several versions are cached
    per plugin, only the active one firing. Re-check at execution; the reference
    describes live discovery, so a changed count updates the example, not the
    procedure.
  - Acceptance: the reference names every location above and states that the
    plugin half is discovered at run time, not pinned.
- [ ] Write `skills/encode-incident/assets/incident-memory-template.md` (no deps)
  - Acceptance: frontmatter is `name` / `description` / `metadata.type` with
    `type: feedback`; the body carries a compact chain, a guard-verdict line, and
    the `**Why:**` and `**How to apply:**` lines.

**Exit Criteria**: Both reference files exist and match the live hook surface and
the existing 70 memories' frontmatter contract.

### Phase 1: Core

**Goal**: The skill runs end to end on a live incident.

**Tasks**:

- [ ] Write `skills/encode-incident/SKILL.md`: manual-only invocation, meta and
  loop scope, reconstructed chain with exactly one question at the weakest link,
  the premise sweep, the four-question guard bar, the write split by
  reversibility, and the compact-reasoning cap (depends on: Phase 0)
  - Acceptance: the create-skill validator passes; the description is trigger-led
    and under 250 chars; the skill states that guards are proposed and never
    installed.
- [ ] Pin the `PostToolUse`-cannot-block rule in the guard bar (depends on:
  Phase 0)
  - Acceptance: `SKILL.md` states that a proposal relying on `PostToolUse` to
    gate is rejected before it is presented.
- [ ] Pin the no-auto-fire property (depends on: Phase 0)
  - Acceptance: `rg encode-incident` over `~/.claude/hooks/dispatch.py` and every
    plugin `hooks.json` returns no registration.
- [ ] Specify the rationalization write in `SKILL.md`: when the gap was
  discipline, one entry is appended to `~/.claude/rules-library/rationalizations.md`
  without asking (depends on: Phase 0)
  - Acceptance: `SKILL.md` states the entry shape - `### "excuse"` plus
    `- **Why it's wrong**:` and `- **Counter-action**:` - names
    `hooks/cartographer-echo.py` as the live consumer that parses it, and says
    the entry is written only when the gap was discipline rather than mechanism.

**Exit Criteria**: A fixture incident, run against a temporary store under
`dev/local/tmp/`, produces a memory, its `MEMORY.md` line, and either a
bar-clearing guard proposal or a recorded rejection reason.

### Phase 2: Integration

**Goal**: The retroactive path updates a memory in place without a human in the
room.

**Tasks**:

- [ ] Run the skill in retroactive mode against a fixture memory copied into a
  temporary store under `dev/local/tmp/`, with the one question pre-answered in
  the task text (depends on: Phase 1)
  - The skill asks one question at the weakest chain link, which an unattended
    run cannot answer, and the real store sits outside the write fence, which
    allows only the repo, `dev/local`, `$TMPDIR` and `/tmp`. A pre-answered
    fixture exercises the chain, the premise sweep, the guard bar and the
    in-place update without either.
  - Acceptance: the fixture memory is updated in place with a chain and a guard
    verdict, no second memory file is created, and `MEMORY.md` changes only if
    the description changed.

**Exit Criteria**: A fixture memory gains a chain and a guard verdict in place,
produced without a single prompt.

**Attended follow-up** (not part of this PRD, run by hand after it ships): run
retroactive mode on the codex exit-4 memory
(`project_codex_review_run_exit4_false_positive`), which carries no guard today.
If a guard has since been installed, pick another guardless memory and name the
substitution.

## Test Strategy

### Critical Scenarios

- **Happy path**: a live meta incident → memory written, `MEMORY.md` line
  appended, one question asked, guard either proposed with four answers or
  rejected with a recorded reason.
- **Happy path**: retroactive mode on an existing memory → same package, in
  place, no second file.
- **Edge case**: the gap was discipline → one `rationalizations.md` entry in the
  shape `hooks/cartographer-echo.py` parses.
- **Edge case**: a guard proposal that would need `PostToolUse` to block →
  rejected before presentation.
- **Error case**: the premise sweep cannot enumerate a hook location → the guard
  proposal fails loudly rather than naming a location it did not verify.
- **Error case**: a guard proposal missing one of the four bar answers → not
  presented at all.

## Risks

- **Guard proliferation**: the written bar is a soft brake and this skill is
  fluent by construction. Mitigation: memory is the default, and every rejected
  guard's reason is recorded, so a pattern of clearing the bar becomes visible.
- **A guard proposed against the wrong hook location** is worse than none.
  Mitigation: the premise sweep, and failing the proposal when a location cannot
  be enumerated.
- **A confidently wrong reconstructed chain** gets no correction, because the
  skill also chooses which link to question. Mitigation: the chain is written
  into the memory, so a wrong root cause is visible later rather than buried.
- **Two writers of the memory plane**: the `distil-memory` skill (agent-skills
  PRDs 00007-00009) writes there too. Settled split rather than a deferred one:
  this skill writes `feedback` memories only, the distiller writes `project`
  memories only, and neither rewrites the other's type.
- **Memory bloat**: every memory is loaded for recall. Mitigation: the chain is
  capped at a few lines and holds the root cause, not the narrative.
