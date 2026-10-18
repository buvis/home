# Cartographer Phase 4 — Architect (Atlas-Aware Plan-First Wrapper)

> Source discovery: `dev/local/discovery/00006-cartographer-architect.md`
> Parent architecture: `dev/local/discovery/00001-cartographer-architecture.md`
> Depends on PRDs: `00009-cartographer-foundation-v1.md`, `00011-cartographer-survey-atlas-v1.md`
>
> **Status: DEFERRED.** Phase 0–3 ship first; reactivation gated by Phase 3 audit data. Tracking PRD: `00019-cartographer-evaluate-phase-4-6-reactivation-v1.md`.
>
> **Revision 2026-06-09**: Phase 3 was redesigned from Recon Gate (deny + ack) to Recon Brief (context injection) - see the redesign note in `00012`. Reactivation criterion 1 originally read engagement off an `audit-recon` ack-quality sampler; that sampler was unbuildable (the ack never passes through a hook, so `audit.jsonl` never sees it). The criterion now requires transcript sampling instead.
>
> **Revision 2026-07-07: SUPERSEDED as a standalone skill.** `superpowers:writing-plans` is no longer installed, so the wrapper has nothing to wrap, and `design-solution` already delivers the spirit: it loads the atlas in its Inputs, grounds "Architecture fit" in it, and persists design docs to `dev/local/designs/`. No separate `/architect` skill or UserPromptSubmit nudge hook will ship. Reactivation criteria are also unevaluable - recon has fired 4 times ever because atlases are stale/absent (see `00049-refresh-atlas-automatically-v1`).
>
> **Re-verified 2026-08-23: unimplementable as written, stay cancelled.** Wrap target `superpowers:writing-plans` absent from `skills/`, `skills-library/`, and the plugin cache; `design-solution` confirmed to load the atlas in its Inputs and ground "Architecture fit" in it. The stale-atlas leg of the 2026-07-07 rationale no longer holds (atlas injection works now via UserPromptSubmit), but the outcome is unchanged. If plan-first nudging is ever wanted again, build it against `design-solution` - do not resurrect this PRD.

## Reactivation Criteria

This PRD un-defers when ALL hold for ≥4 consecutive weeks of recon data:

- audit-sessions transcript sample shows the agent acting on injected Recon Brief content (citing extension points or similar files from the brief) rather than ignoring it. Note: hook-side `audit.jsonl` cannot measure this - the agent's engagement lives only in transcripts, so this criterion is sampled manually (or via `audit-sessions`), not read off `audit-recon`.
- Manual sample shows ≥2 multi-file sessions/week where the agent skipped planning despite multi-file intent (i.e., Recon Brief alone is not enough to force plan-first).
- User confirms `/architect` thin-wrapper is wanted (vs. invoking `superpowers:writing-plans` directly).

If any criterion fails, defer further; reassess monthly via `00019`.

### Decision Log

(populated by `00019` evaluations: `YYYY-MM-DD: <verdict> (<rationale>)`)

- 2026-07-07: superseded (spirit folded into `design-solution` - atlas already in its Inputs; `superpowers:writing-plans` uninstalled; recon data ~0 so criteria unevaluable)
- 2026-08-23: stay cancelled (wrap target still uninstalled; design-solution covers the spirit; stale-atlas rationale obsolete but outcome unchanged)

## Overview

### Problem Statement

Multi-file changes need a plan-first reflex. Existing planners (`superpowers:writing-plans`, `plan-tasks`, `superpowers:brainstorming`) are atlas-blind — they plan without knowing where new code naturally fits, what extension points exist, or what conflicts current architecture. `/architect` is a **thin wrapper**: it loads `atlas.md`, prepends it to the user task, and delegates to `superpowers:writing-plans` via the Skill tool. A UserPromptSubmit hook nudges toward `/architect` on multi-file intent, throttled to one fire per (session × repo × day) and disable-able via env var.

### Target Users

The agent (via the nudge) and the user (when invoking `/architect` directly).

### Success Metrics

- Nudge fires when expected: audit log shows nudge events on multi-file prompts in fresh sessions; suppressed when throttle key already set.
- `/architect` invocation succeeds end-to-end: loads atlas, delegates to writing-plans, returns plan.
- Manual sample of `/architect` adoption rate on multi-file tasks (recorded in audit log; surfaced by audit-cartographer post-MVP).
- Throttle key `nudge-<repo_hash>-<date>` honored — second prompt same day same repo does not re-nudge.
- Opt-out env var (`CARTOGRAPHER_ARCHITECT_NUDGE=0`) suppresses nudges cleanly.

## Functional Decomposition

### Capability: Atlas-Aware Plan Wrapper

`/architect` skill loads atlas.md, prepends it to the task, delegates to writing-plans.

#### Feature: Skill entry (`/architect`)

- **Description**: Markdown skill at `~/.claude/skills/architect/SKILL.md` documenting the wrap behavior + arg parsing.
- **Inputs**: user task (skill argument); optional `--skip-atlas`.
- **Outputs**: delegated plan from `superpowers:writing-plans`.
- **Behavior**: Resolve project hash; read `atlas.md`; if missing AND no `--skip-atlas` → recommend `/survey` first and exit. Otherwise, prepend atlas.md content + a short "atlas context" header to the task and call `Skill(skill: "superpowers:writing-plans", args: <wrapped task>)`. Save final plan output to disk (see below).

#### Feature: Atlas-missing path with `--skip-atlas`

- **Description**: Allow user to bypass atlas requirement.
- **Inputs**: `--skip-atlas` flag.
- **Outputs**: delegated plan without atlas grounding.
- **Behavior**: When flag set + atlas absent → emit warning into the wrapped task ("⚠ planning without atlas grounding") and proceed.

#### Feature: Plan persistence (default on)

- **Description**: Save `/architect` output to `~/.claude/cartographer/projects/<hash>/plans/<task-slug>.md` for Phase 6 (Forecast Extensibility) to reference.
- **Inputs**: plan body, task slug, project hash.
- **Outputs**: markdown file written.
- **Behavior**: Slug = lowercase kebab of task summary, deduplicated with date suffix on collision. Atomic write.

### Capability: UserPromptSubmit Nudge

Detect multi-file intent in user prompts; suggest `/architect`.

#### Feature: Intent regex set

- **Description**: Conservative regex matching `implement`, `add feature`, `create new`, `refactor across`, `build out`, `design`, `add support for`, `extend the`, `restructure`.
- **Inputs**: user prompt text.
- **Outputs**: matched word or none.
- **Behavior**: Word-boundary regex; case-insensitive; first match wins. Case-sensitive `Edit/Write/MultiEdit` strings excluded.

#### Feature: Nudge throttle

- **Description**: Fire at most once per (session × repo × date).
- **Inputs**: session_key, repo_hash, current date (UTC).
- **Outputs**: fire / suppress decision.
- **Behavior**: Throttle key = `f"nudge-{repo_hash}-{date}"`. `is_checked(session_key, "architect-nudge", key)` short-circuits; otherwise fire + `mark_checked`.

#### Feature: Stderr nudge message

- **Description**: Brief stderr line, non-blocking.
- **Inputs**: matched intent word.
- **Outputs**: stderr text.
- **Behavior**: "Multi-file intent detected (`<word>`) — `/architect` available for plan-first execution. Disable: `CARTOGRAPHER_ARCHITECT_NUDGE=0`."

#### Feature: Opt-out env var

- **Description**: `CARTOGRAPHER_ARCHITECT_NUDGE=0` suppresses all nudges in the current session.
- **Inputs**: env var.
- **Outputs**: skipped fire + audit `event:nudge-suppressed, opt_out:true`.
- **Behavior**: Read at hook entry; short-circuit before regex check.

### Capability: Audit Emission

Every nudge fire / suppression / skill invocation emits an audit event.

#### Feature: Audit-log emission

- **Description**: Append events with `phase: "architect"` for telemetry.
- **Inputs**: event type, repo_hash, intent_match, opt_out.
- **Outputs**: side effect — JSONL line.
- **Behavior**: Event types: `nudge-fired`, `nudge-suppressed`, `skill-invoked`, `skill-skipped-no-atlas`. Schema fields: `ts`, `session`, `phase`, `event`, `repo_hash`, `intent_match` (only for nudge events), `opt_out` (only for suppressed events).

### Capability: Hook Wiring

Settings.json UserPromptSubmit block (new in user's config — none exists yet).

#### Feature: UserPromptSubmit matcher

- **Description**: Add `cartographer-architect-nudge.py` to `~/.claude/settings.json` UserPromptSubmit hook block.
- **Inputs**: settings.json edit.
- **Outputs**: hook fires on every user prompt.
- **Behavior**: Stderr-only output (non-blocking); never returns deny envelope.

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── skills/
│   └── architect/
│       ├── SKILL.md                         # Skill entry + arg parsing
│       └── scripts/
│           └── wrap.py                      # Atlas-load + delegation helper (optional)
├── hooks/
│   ├── cartographer-architect-nudge.py      # UserPromptSubmit nudge
│   └── tests/
│       ├── test_architect_skill.py
│       └── test_architect_nudge.py
├── settings.json                            # UserPromptSubmit hook block (new)
├── cache/cartographer/architect-nudge/       # session-state namespace
└── cartographer/projects/<hash>/plans/        # per-task plan markdown (Phase 4 output)
```

### Module: `skills/architect/SKILL.md`

- **Maps to capability**: Atlas-Aware Plan Wrapper.
- **Responsibility**: Document the skill, parse args, delegate to writing-plans, persist plan output.

### Module: `skills/architect/scripts/wrap.py` (optional)

- **Maps to capability**: Plan persistence + atlas loading.
- **Responsibility**: Helper if SKILL.md needs more than markdown can express. Otherwise inline in SKILL.md.

### Module: `hooks/cartographer-architect-nudge.py`

- **Maps to capability**: UserPromptSubmit Nudge + audit emission.
- **Responsibility**: Single-file UserPromptSubmit hook; reads stdin JSON, applies opt-out + intent regex + throttle, emits stderr nudge.
- **Imports**: `_lib_cartographer` (Phase 0); stdlib only.
- **Constraint**: <200 lines.

### Module: `tests/test_architect_*.py`

- **Maps to capability**: All — atlas-load path, --skip-atlas, plan persistence, intent regex, throttle, opt-out, audit emission.

### Module: `settings.json` (data)

- **Maps to capability**: Hook wiring.
- **Responsibility**: New UserPromptSubmit block; `cartographer-architect-nudge.py` entry.

## Dependency Graph

### Upstream (required)

- Phase 0 (`00009`): `_lib_cartographer.py` (project_hash, is_checked/mark_checked, append_audit, atlas_dir).
- Phase 2 (`00011`): atlas.md for context grounding.
- External: `superpowers:writing-plans` skill (wrapped via Skill tool).

### Phase 4 (this PRD)

- **`SKILL.md`** depends on Phase 0 + Phase 2 + writing-plans skill.
- **`cartographer-architect-nudge.py`** depends on Phase 0 only.
- **`settings.json` UserPromptSubmit block** depends on the hook.
- **Tests** depend on the above.

### Downstream (out of scope)

- audit-cartographer dashboard consumes audit events.
- Phase 6 (`/forecast-extensibility`) reads saved plans from `cartographer/projects/<hash>/plans/`.

## Implementation Phases

### Phase 4a: `/architect` skill skeleton

**Goal**: Skill exists and is callable; loads atlas (or warns); delegates to writing-plans.

**Tasks**:

- [ ] Author `~/.claude/skills/architect/SKILL.md` with arg parsing (`--skip-atlas`), atlas resolution, delegation, plan persistence. (depends on: Phase 2 atlas exists in user's repo for E2E test) — Acceptance: skill registered; manual `/architect "refactor X"` returns plan; audit event `skill-invoked` recorded.
- [ ] Atlas-missing path: when `atlas.md` absent and no `--skip-atlas`, recommend `/survey` first; emit `skill-skipped-no-atlas` audit event. (depends on: above) — Acceptance: dry-run on repo without atlas matches recommendation copy.

**Exit Criteria**: Skill callable; both atlas-present and atlas-missing paths work.

### Phase 4b: Plan persistence

**Goal**: Plans saved by default for Phase 6 to reference.

**Tasks**:

- [ ] Implement plan-output persistence to `~/.claude/cartographer/projects/<hash>/plans/<task-slug>.md` with kebab-slug + date-suffix collision handling. (depends on: 4a) — Acceptance: pytest verifies file written; collision adds `-YYYYMMDD` suffix.

**Exit Criteria**: Plans accumulate per repo for downstream phases.

### Phase 4c: UserPromptSubmit nudge

**Goal**: Hook fires on multi-file intent, throttled, opt-out-respecting.

**Tasks**:

- [ ] Create `~/.claude/hooks/cartographer-architect-nudge.py`: read stdin, check `CARTOGRAPHER_ARCHITECT_NUDGE` env, apply intent regex, check throttle, emit stderr + audit. (depends on: Phase 0) — Acceptance: pytest with three intent prompts → first fires nudge, others suppressed; opt-out env suppresses all.
- [ ] Add UserPromptSubmit hook block to `~/.claude/settings.json` (new block — none exists yet). (depends on: above) — Acceptance: real prompt fires hook; verified in audit log.

**Exit Criteria**: Nudge fires once per (session × repo × date); opt-out works.

### Phase 4d: Audit emission + tests

**Goal**: Lock behavior with pytest; finalize audit schema.

**Tasks**:

- [ ] Emit audit events for `nudge-fired`, `nudge-suppressed`, `skill-invoked`, `skill-skipped-no-atlas` with schema `{ts, session, phase, event, repo_hash, intent_match?, opt_out?}`. (depends on: 4a, 4b, 4c) — Acceptance: schema validates on all four event types.
- [ ] Write `tests/test_architect_skill.py` covering: atlas load, --skip-atlas, plan persistence, slug collision. (depends on: 4a, 4b) — Acceptance: pytest green.
- [ ] Write `tests/test_architect_nudge.py` covering: intent regex matches, throttle, opt-out, audit emission. (depends on: 4c) — Acceptance: pytest green; coverage >80%.

**Exit Criteria**: All tests green; audit log interpretable.

## Test Strategy

### Critical Scenarios

- **Happy path — `/architect` with atlas**: skill loads atlas.md, prepends to task, delegates to `superpowers:writing-plans`, saves plan to `cartographer/projects/<hash>/plans/<slug>.md`, audit `skill-invoked`.
- **Happy path — `--skip-atlas`**: atlas absent, flag set; warning emitted in wrapped task; delegation proceeds.
- **Happy path — nudge fires once per day**: prompt 1 with "implement X" → nudge fires; prompt 2 same day same repo with "implement Y" → suppressed; prompt 3 next day → fires again.
- **Edge case — opt-out env var**: `CARTOGRAPHER_ARCHITECT_NUDGE=0` set; multi-file prompt does not produce nudge; audit `event:nudge-suppressed, opt_out:true`.
- **Edge case — intent regex precision**: prompt "edit a single file" → no nudge (no intent word); prompt "implement caching" → nudge.
- **Edge case — slug collision**: two `/architect` calls in same repo same day with identical task → second saves with `-YYYYMMDD` suffix.
- **Error case — atlas missing without flag**: skill recommends `/survey`; does not delegate; audit `skill-skipped-no-atlas`.
- **Error case — writing-plans API drift**: skill should tolerate; document version expectation in SKILL.md body.

## Risks

- **Intent regex too broad → spam nudges**: strict word list; throttle 1/session/repo/date; opt-out env var. *Mitigation*: audit-cartographer surfaces suppressed-fire ratio; user can tune word list.
- **User ignores nudge**: fine — advisory only.
- **`superpowers:writing-plans` API drift**: invocation must be tolerant. *Mitigation*: SKILL.md documents version compat; defensive arg-passing.
- **Atlas missing → `/architect` unusable**: `--skip-atlas` escape hatch + clear `/survey` recommendation.
- **Plan files accumulate**: out of scope here; future cleanup deferred to audit-cartographer post-MVP.

## Open Questions

Carried from discovery doc:

- **Throttle key**: confirmed — session × repo × date.
- **`/architect --quick` mode**: deferred to v2; ship the wrapper first, gather usage data.
- **Save plans to `cartographer/projects/<hash>/plans/`**: confirmed — yes, save by default (small overhead, enables Phase 6 grounding).
