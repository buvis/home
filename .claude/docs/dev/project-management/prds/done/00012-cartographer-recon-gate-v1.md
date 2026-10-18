# Cartographer Phase 3 - Recon Brief (Per-Day Atlas Context Injection)

> Source discovery: `dev/local/discovery/00005-cartographer-recon-gate.md`
> Parent architecture: `dev/local/discovery/00001-cartographer-architecture.md`
> Depends on PRDs: `00009-cartographer-foundation-v1.md` (lib + cache + audit), `00011-cartographer-survey-atlas-v1.md` (atlas.md + staleness.flag)
>
> **Redesign 2026-06-09**: this PRD originally specced a Recon Gate - a PreToolUse deny on first edit with a structured 3-question ack. Two flaws killed that design: (1) the ack was unverifiable - the agent's answers live only in the transcript and never pass through any hook, so the planned ack-quality sampler could not be built from `audit.jsonl`; (2) gate state lived in a per-session file while the intent was once-per-repo-per-day across sessions, so the 24-hour TTL never applied. The redesign injects the atlas as context instead: same information delivery, zero denies, zero retry round-trips. If transcript sampling later shows the injected atlas being ignored, escalate to a gate with that evidence.

## Overview

### Problem Statement

Atlas exists (Phase 2) but the agent doesn't read it before editing - it dives in based on the immediate prompt context. Recon Brief injects a ≤1KB atlas excerpt as additional context on the first user prompt per (repo × day) via a UserPromptSubmit hook. No deny, no ack ceremony: the atlas is simply present in context before the first edit happens.

### Target Users

The agent (receives the brief as context). End-user observable effect: nothing - injection is silent; at most 1KB of context cost per repo per day.

### Success Metrics

- audit-recon reports at most one inject per (repo × day), verified by repo_hash + date in the audit log. This is fully measurable from `audit.jsonl`, unlike the old ack-quality metric.
- Hook latency: <150ms p95 on the suppressed path; <200ms on inject. The floor is Python interpreter startup plus the git subprocess inside `_lib_cartographer.project_hash` (~60-120ms combined), the same cost class cartographer-echo already pays per edit; the hook adds at most one small JSON read on top.
- Missing-atlas path injects a one-line `/survey` recommendation instead, same throttle.
- Stale atlas (`staleness.flag` present) appends a stale warning to the brief.
- v2 candidate: audit-sessions transcript sample measures whether injected atlas content is referenced in subsequent turns. Out of scope for v1.

## Functional Decomposition

### Capability: Per-Repo-Per-Day Throttle

Inject once per (repo × day); pass through silently otherwise.

#### Feature: Throttle decision

- **Description**: Decide inject / suppress from a day-keyed store.
- **Inputs**: repo_hash; current UTC date.
- **Outputs**: inject or silent pass-through.
- **Behavior**: Single shared store `~/.claude/cache/cartographer/recon/injected.json` mapping `repo_hash → last-inject ISO date (UTC)`. Inject when the entry is missing or older than today; otherwise suppress. Day-keyed and session-independent by construction, which fixes the per-session-state contradiction in the gate design.

#### Feature: Store resilience

- **Description**: Tolerate a missing or malformed store.
- **Inputs**: `injected.json`.
- **Outputs**: rebuilt store.
- **Behavior**: Malformed JSON → rebuild from empty and proceed with inject. Writes are atomic (temp file + rename).

### Capability: Brief Content

What gets injected.

#### Feature: Atlas excerpt injection

- **Description**: Read `atlas.md`, cap at 1KB, emit as JSON `hookSpecificOutput.additionalContext` (added to the agent's context discretely; plain stdout would also be added as context but renders as hook output in the transcript - verified against the hooks reference docs 2026-06-09).
- **Inputs**: atlas.md path.
- **Outputs**: excerpt string ≤1KB.
- **Behavior**: v1 - full atlas.md truncated to 1KB if larger (Phase 2's 5KB cap keeps this rare). Excerpt selection by directory relevance deferred to v2 if signal data argues for it.

#### Feature: Grounding header

- **Description**: Short preamble framing the excerpt, with the three grounding reminders from the gate design kept as guidance, not as a gated ack.
- **Inputs**: none.
- **Outputs**: text block prepended to the excerpt.
- **Behavior**: "Atlas for this repo (consult before editing). Before adding new code: know the role of the file you touch, find two existing files with similar shape, and use a declared extension point or justify a new one."

### Capability: Atlas-State Awareness

Handle missing-atlas and stale-atlas cases without crashing.

#### Feature: Missing atlas → /survey one-liner

- **Description**: When `atlas.md` is absent for the current repo, inject a single line recommending `/survey` instead of the brief.
- **Inputs**: atlas_dir path.
- **Outputs**: one-line `additionalContext`.
- **Behavior**: Same once-per-repo-per-day throttle; the suggestion does not repeat within a day. Skip entirely (no injection, no store write) when `project_hash` resolves to `"global"` (cwd is not a git repo) - non-repo contexts have no atlas to survey and a daily nag there is pure noise.

#### Feature: Stale atlas warning

- **Description**: When `staleness.flag` is present, append a warning to the injected brief.
- **Inputs**: staleness.flag path.
- **Outputs**: "⚠ atlas is stale - recommend /survey --refresh" appended to the brief.
- **Behavior**: Informational only; the excerpt is still injected.

### Capability: Audit Emission

Injections logged for `audit-recon` to consume.

#### Feature: Audit-log emission

- **Description**: Append one event per inject via `_lib_cartographer.append_audit`. Suppressed prompts are NOT logged - UserPromptSubmit fires on every prompt and per-prompt suppress events would flood `audit.jsonl`.
- **Inputs**: decision, repo_hash, atlas state.
- **Outputs**: side effect - one JSONL line per inject.
- **Behavior**: Fields: `ts`, `session`, `phase: "recon"`, `decision` ∈ {inject, atlas-missing}, `repo_hash`, `atlas_excerpt_bytes`, `stale` (bool).

### Capability: Hook Wiring

Settings.json UserPromptSubmit block (new - verified 2026-06-09: no UserPromptSubmit block in `settings.json`; `settings.local.json` does not exist).

#### Feature: UserPromptSubmit matcher

- **Description**: Add `cartographer-recon-brief.py` to `~/.claude/settings.json` UserPromptSubmit hook block.
- **Inputs**: settings.json edit.
- **Outputs**: hook fires on every user prompt; suppressed path must stay cheap.
- **Behavior**: Context injection via JSON `additionalContext` only; never emits `decision: "block"`; exits 0 on any internal error (never break prompt handling - a stuck UserPromptSubmit hook stalls the session, hence the latency budget).

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── hooks/
│   ├── cartographer-recon-brief.py      # UserPromptSubmit hook entry
│   └── tests/
│       └── test_cartographer_recon_brief.py
├── settings.json                        # UserPromptSubmit hook block (new)
├── cache/cartographer/recon/
│   └── injected.json                    # repo_hash → last-inject date
└── cartographer/projects/<hash>/
    ├── atlas.md                         # read by hook (Phase 2 produced)
    └── staleness.flag                   # presence checked (Phase 2 produced)
```

### Module: `cartographer-recon-brief.py`

- **Maps to capability**: All.
- **Responsibility**: Single-file UserPromptSubmit hook; reads stdin JSON (cwd), resolves repo_hash, applies throttle + atlas-state logic, prints brief to stdout.
- **Imports**: `_lib_cartographer` (Phase 0); stdlib only.
- **Constraint**: <150 lines (no deny-envelope or ack machinery to carry).

### Module: `tests/test_cartographer_recon_brief.py`

- **Maps to capability**: All - throttle, day rollover, per-repo isolation, missing atlas, stale flag, store resilience, excerpt cap, audit emission.

### Module: `settings.json` (data)

- **Maps to capability**: Hook wiring.
- **Responsibility**: New UserPromptSubmit block.

## Dependency Graph

### Upstream (required)

- Phase 0 (`00009`): `_lib_cartographer.py` (project_hash, atlas_dir, append_audit).
- Phase 2 (`00011`): `atlas.md`, `staleness.flag` for the current repo. Brief degrades to the /survey one-liner when missing.

### Phase 3 (this PRD)

- **`cartographer-recon-brief.py`** depends on Phase 0 + Phase 2 artifacts.
- **`settings.json` matcher** depends on the hook.
- **Tests** depend on the hook + fixture state.

### Downstream (out of scope)

- (none - `audit-recon` skill is in scope, see Phase 3d.)
- Phase 4 (`00013`, deferred): reactivation criterion 1 samples transcripts for evidence the brief is read; see that PRD.

## Implementation Phases

### Phase 3a: Hook scaffolding + throttle store

**Goal**: Hook fires on UserPromptSubmit; injects once per (repo × day).

**Tasks**:

- [ ] Create `~/.claude/hooks/cartographer-recon-brief.py`: read stdin JSON, resolve repo_hash via `_lib_cartographer.project_hash`, apply day-keyed throttle against `injected.json`, atomic store writes, exit 0 on any error. (depends on: Phase 0) — Acceptance: pytest covers first-prompt inject, same-day suppress, day-rollover re-inject, per-repo isolation, malformed-store rebuild.
- [ ] Add settings.json UserPromptSubmit hook block (new). (depends on: hook) — Acceptance: real prompt triggers hook; suppressed path verified silent.

**Exit Criteria**: Inject fires exactly once per (repo × day) across sessions; never crashes; never blocks a prompt.

### Phase 3b: Brief content + atlas-state branches

**Goal**: Injected brief is useful on all three atlas states.

**Tasks**:

- [ ] Read `atlas.md` from `_lib_cartographer.atlas_dir(repo_hash)`; cap excerpt at 1KB; prepend grounding header. (depends on: 3a) — Acceptance: pytest with fixture atlas verifies header + excerpt length and content.
- [ ] Missing-atlas branch: inject one-line `/survey` recommendation, same throttle. (depends on: above) — Acceptance: pytest with no atlas verifies the one-liner and that it doesn't repeat same-day.
- [ ] Stale-flag branch: append stale warning to the brief. (depends on: above) — Acceptance: pytest with flag present verifies the appended warning.

**Exit Criteria**: All three atlas states produce correct output.

### Phase 3c: Audit emission + latency + tests

**Goal**: Lock behavior with pytest; verify latency budget.

**Tasks**:

- [ ] Emit audit events on inject / atlas-missing only (no suppress events) with fields `ts`, `session`, `phase: "recon"`, `decision`, `repo_hash`, `atlas_excerpt_bytes`, `stale`. (depends on: 3b) — Acceptance: mixed runs produce one line per inject, zero lines for suppressed prompts.
- [ ] Time hook on 100 invocations, suppressed and inject paths separately. (depends on: above) — Acceptance: suppressed p95 <150ms; inject p95 <200ms (includes interpreter spawn + project_hash git subprocess).
- [ ] Write `tests/test_cartographer_recon_brief.py` covering all capabilities. (depends on: above) — Acceptance: pytest green; coverage >80%.

**Exit Criteria**: pytest green; latency budget met; audit log interpretable.

### Phase 3d: audit-recon skill + audit-claude-config wiring

**Goal**: `audit-recon` skill exists and is launchable via `audit-claude-config`.

**Tasks**:

- [ ] Create `~/.claude/skills/audit-recon/SKILL.md` filtering `~/.claude/cartographer/audit.jsonl` to `phase:"recon"`. Report sections: inject uniqueness per (repo × day), missing-atlas inject count (repos needing `/survey`), stale-at-inject rate (repos needing `/survey --refresh`), excerpt size distribution. Follow audit-skill canonical shape. (depends on: 3c) — Acceptance: skill runs on real audit.jsonl; report renders; passes `audit-skills`.
- [ ] Append `audit-recon` to the `code-quality` row in `~/.claude/skills/audit-claude-config/SKILL.md` Arguments table (created in PRD 00010 Phase 1h). (depends on: above, PRD 00010 Phase 1h complete) — Acceptance: `/audit-claude-config code-quality` now includes `audit-recon`.
- [ ] Append `audit-recon` to the numbered Audit Registry in `audit-claude-config/SKILL.md` (category `code-quality`, speed `fast`). (depends on: above) — Acceptance: default dashboard includes `audit-recon`.

**Exit Criteria**: `/audit-claude-config code-quality` runs `audit-recon` and surfaces findings.

## Test Strategy

### Critical Scenarios

- **Happy path - first prompt of the day injects**: prompt 1 in repo A → brief injected (header + excerpt); prompt 2 same repo same day → silent; audit shows exactly one inject line.
- **Edge case - second repo same day**: inject in repo A, switch cwd to repo B → repo B injects independently; per-repo isolation via repo_hash key.
- **Edge case - day rollover**: `injected.json` entry dated yesterday → next prompt re-injects.
- **Edge case - missing atlas**: no atlas.md → one-line `/survey` recommendation injected; throttled the same; audit `decision:atlas-missing`.
- **Edge case - non-repo cwd**: `project_hash` resolves to `"global"` → hook exits silently; no injection, no store write, no audit line.
- **Edge case - stale flag**: `staleness.flag` present → brief carries the stale warning; audit `stale:true`.
- **Edge case - atlas.md >1KB**: excerpt truncated; audit `atlas_excerpt_bytes:1024`.
- **Error case - malformed injected.json**: store rebuilt; inject proceeds; no crash.
- **Error case - malformed stdin**: hook exits 0 silently; prompt handling unaffected.

## Risks

- **Agent ignores the injected brief**: the failure mode the old gate tried to prevent by force. v2 answer: audit-sessions transcript sampling to measure reference rate; escalate to a gate only with that evidence. Forcing an ack the hook can't verify was ceremony, not enforcement.
- **UserPromptSubmit fires on every prompt**: suppressed path is one stat + one small JSON read; no atlas parsing. Latency budget enforced by Phase 3c. The unavoidable floor is interpreter spawn + the project_hash git subprocess.
- **Concurrent sessions race the store**: two sessions in the same repo can both read `injected.json` before either writes, producing a double inject. Worst case is one redundant 1KB injection that day; atomic rename prevents corruption. Accepted - no locking in v1.
- **Context cost**: ≤1KB once per repo per day - negligible.
- **Store grows unbounded**: one entry per repo ever touched; tens of entries; ignore.

## Open Questions

- **Gate vs inject**: resolved by this redesign - inject first, escalate with evidence.
- **Atlas excerpt selection**: full atlas.md (≤1KB) in v1; directory-relevant excerpt in v2 if signal data argues for it. (Carried from discovery doc.)

## Review Log

2026-06-09 doubt review of the redesign, before any implementation:

**Verified**:

- UserPromptSubmit exit-0 stdout and JSON `additionalContext` are both added to the agent's context (hooks reference docs). Plain stdout renders as visible hook output in the transcript; `additionalContext` is added discretely - hence the spec mandates `additionalContext` so the "silent to user" claim holds.
- No UserPromptSubmit hook block exists in `settings.json`; `settings.local.json` absent.
- `_lib_cartographer.project_hash` shells out to git (1-2 subprocesses) and returns `("global", "global", "")` outside a git repo - drove the latency floor (150/200ms budgets) and the non-repo silent-skip rule.

**Accepted limitations**:

- Concurrent sessions can race `injected.json` into a double inject (worst case one redundant 1KB injection per day; atomic rename prevents corruption; no locking in v1).
- Hook-side audit cannot measure whether the agent uses the injected brief - engagement lives only in transcripts. Measuring it is the v2 transcript-sampling item; it also gates 00013's reactivation criterion 1 and any escalation back to a gate.
