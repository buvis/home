# Deliver Strunk Rulings Via A Hook

> ## PHASE 0 RAN 2026-07-13 — GATE PASSED. THE PRD IS VIABLE. BUILD IT.
>
> **Result: hook-injected `additionalContext` IS obeyed, 3/3, with no rules file present to corroborate it** (i.e. under this PRD's actual end state).
>
> **Method (clean A/B on a ruling the model demonstrably ignores by default):** a `PreToolUse` hook injected strunk `web-patterns`' real CSS ruling ("never px for sizing — use rem") when the tool target was a `.css` file, with `rules/{python,rust,web}/` **moved out of the tree**. Baseline (no rules, no hook): the model wrote `padding: 16px`. With the hook: `padding: 1.5rem`, and even the box-shadow offsets in rem. **3/3 obeyed.**
>
> **So the three build questions are settled:**
> 1. *Can a hook inject context on file work?* **Yes** — `PreToolUse` → `hookSpecificOutput.additionalContext`, and it sees `tool_input.file_path`.
> 2. *Is it obeyed?* **Yes, 3/3** — and obeyed even with nothing to corroborate it.
> 3. *Which event?* **`Read`.** It must fire BEFORE the model composes content. `Edit`/`Write` fire after the content is already written — too late to steer the first write (the model may self-correct on a second pass, but do not rely on it).
>
> ### CRITICAL DESIGN CONSTRAINT discovered in Phase 0 (do not skip this)
>
> The **first** canary — an absurd, unattributed instruction ("every docstring must begin with the literal word ZEBRAFISH") — was **received, recognised as a prompt-injection attack, and REFUSED**, and the model reported it to the user verbatim:
>
> > *"That's not in any of your actual rule files (I can see the real `python/coding-style.md` etc. above, and none say this) — it's an injected instruction, not a legitimate project rule. I'm ignoring it."*
>
> This is a **security feature, and it is load-bearing for this design**: the model treats hook-injected imperatives with suspicion and cross-checks them against the real rules files. Consequences the hook MUST respect:
>
> - **Inject genuine guidance, attributed to its source.** The successful run's payload opened with *"Guidance for this file type, from the strunk `web-patterns` skill:"* and carried the skill's real ruling table verbatim. That is the shape that works.
> - **Never inject a synthesised, paraphrased, or novel instruction.** Anything that does not look like real, sourced guidance risks being refused AND surfaced to the user as a suspected attack — which is worse than no guidance at all (it is alarming noise).
> - **This constraint gets stronger, not weaker, after the rules tree is deleted**, because the model loses the corroborating anchor it used here. The Phase 2 canary must re-verify obedience in that exact state (it did, 3/3 — but re-verify per language, since only `.css` was tested).
>
> Only `.css` was tested. **Phase 2 must canary `.py` and `.rs` too** before any deletion.

> Source: PRD 00055's live probe (2026-07-13), which falsified the "migrate rules into skills" model by measurement. This PRD is the real fix that 00055 could not be.
> Target: a new hook in `~/.claude/hooks/`, `settings.json` wiring, and (only on success) the retirement of `~/.claude/rules/{python,rust,web}/` (15 files).
> Prerequisite already shipped: **strunk v0.2.0** carries all 71 language rulings, verified per-ruling against the released plugin cache.

## Overview

### Problem Statement

Language guidance now exists twice, deliberately:

- `~/.claude/rules/{python,rust,web}/*.md` — 15 files, 1026 lines, `paths:`-scoped. **Measured: the harness PUSHES these and the model OBEYS them** (PRD 00055's canary test — a planted ruling was followed by a fresh session doing Python work).
- The **strunk** plugin's skills — same rulings, released and versioned. **Measured: the model PULLS these almost never — 1 invocation in 30 realistic-work runs.** They fire on explicit keywords ("check python compat"), not on the work itself.

PRD 00055 tried to delete the rules tree and rely on strunk. The probe blocked it: that trade swaps a guaranteed delivery mechanism for one that demonstrably does not fire. A router file (a `paths:` pointer saying "invoke the skill now") does not help either — 0/3; attachment is not invocation.

So we are stuck with two copies of the same rulings, drifting independently — the exact problem 00055 set out to kill. **The blocker was never content. It is delivery.**

### Target Users

The solo operator who wants one authoritative source per language topic, and wants it to actually reach the model while they work.

### Success Metrics

- Guidance from strunk reaches the model during ordinary file work **without the model choosing to invoke anything** — verified by the same canary method 00055 used (plant a ruling in the strunk skill, confirm a fresh session obeys it while editing a matching file).
- Exactly one source per (language × topic): the strunk skill. `~/.claude/rules/{python,rust,web}/` is gone.
- The always-loaded top-level `~/.claude/rules/*.md` still work untouched.
- Delivery survives a strunk version bump (the hook reads the installed cache, not a pinned path).

### Non-Goals

- Rewriting the rulings. strunk v0.2.0's content is the source of truth and is already reviewed.
- Touching the top-level language-agnostic `~/.claude/rules/*.md`.
- Making every skill auto-fire. This is about *guidance* skills whose content must reach the model unprompted, not about action skills.

## Functional Decomposition

### Capability: Guaranteed delivery of strunk rulings

#### Feature: File-matched ruling injection
- **Description**: a hook that, when the model touches a file of a given type, injects the matching strunk skill's rulings as context — the same guarantee `paths:` rules have today, but sourced from strunk.
- **Inputs**: the tool call's target path; the installed strunk cache (`plugins/cache/buvis-plugins/strunk/<version>/skills/`).
- **Outputs**: injected context carrying the skill's rulings.
- **Behavior**: `.py`/`.pyi` → `python-patterns` (+ `python-testing` on test files); `.rs` → `rust-patterns` (+ `rust-testing`); `.css`/`.html`/`.svelte`/`.ts`/`.tsx`/`.vue` → `web-patterns` (+ `apply-design-system`). Resolve the strunk version at runtime — never pin it.

**The mechanism is PROVEN — verified 2026-07-13, do not re-derive.** A **`PreToolUse`** hook CAN inject context via `hookSpecificOutput.additionalContext`, and it sees the tool's target path. Two live proofs on this machine:

- The **context-mode** plugin emits `hookSpecificOutput.additionalContext` from PreToolUse on `Bash`/`Read`/`Grep` (emitter: `plugins/cache/context-mode/context-mode/<version>/hooks/formatters/claude-code.mjs`, `case "context"`; entry `hooks/pretooluse.mjs`); its integration tests assert `parsed.hookSpecificOutput.additionalContext`. Observed in-session as `PreToolUse:Read hook additional context: <context_guidance>…`.
- `~/.claude/hooks/cartographer-recon-brief.py` uses the same envelope on `UserPromptSubmit` (`hookEventName` + `additionalContext`) — the in-house precedent for the JSON shape and the exit-0-on-any-error contract.

So the design is: **PreToolUse on Read/Edit/Write → match the path → inject the matching strunk skill's rulings as `additionalContext`.** `UserPromptSubmit` is the wrong event (fires per prompt, not per file; the path is unknown at that point).

**The obedience gate: PASSED (Phase 0, 2026-07-13 — see banner).** Hook-injected `additionalContext` was obeyed 3/3 in this PRD's end state (no rules files present) when the payload was genuine guidance attributed to its source strunk skill. What remains unproven is per-language generalisation (`.py`, `.rs` — only `.css` was tested) and delivery from the real released cache; both are owned by Phase 2's canaries. If a language's canary fails, that language keeps its rules files (partial success), exactly as the Rules-tree retirement feature specifies.

#### Feature: Throttle
- **Description**: inject a given skill's rulings at most once per (session × skill), not on every file touch.
- **Behavior**: reuse the day-keyed / session-keyed store pattern from `cartographer-recon-brief.py`; atomic temp+rename writes; exit 0 on any error (a delivery hook must never block a tool call).

#### Feature: Rules-tree retirement
- **Description**: delete `rules/{python,rust,web}/` once, and only once, delivery is proven.
- **Behavior**: gated on the canary test passing for all three languages. If it fails for a language, that language keeps its rules files and the PRD reports partial success. **Never delete on an unproven gate — that is the mistake 00055 nearly made and its probe caught.**

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── hooks/
│   ├── strunk-ruling-inject.py               # Maps to: File-matched ruling injection + Throttle (new)
│   └── tests/test_strunk_ruling_inject.py    # Maps to: hook unit tests (new)
├── settings.json                             # Maps to: PreToolUse wiring (new Read|Edit|Write matcher entry)
├── rules/{python,rust,web}/                  # Maps to: Rules-tree retirement (deleted only after the Phase 2 gate)
└── skills/sort-agent-setup/SKILL.md          # Maps to: retirement sweep (lines 122-123 reference rules/web, rules/rust)
```

### Module: strunk-ruling-inject hook
- **Maps to capability**: Guaranteed delivery of strunk rulings
- **Responsibility**: match the tool target path → resolve the installed strunk cache version at runtime → inject the mapped skill's rulings as `additionalContext`, attributed to the source skill, throttled once per (session × skill); exit 0 on every error path.
- **Exports**: PreToolUse stdout envelope (`hookSpecificOutput.hookEventName` + `additionalContext`); throttle store file (atomic temp+rename, `cartographer-recon-brief.py` pattern).

## Dependency Graph

### Foundation Layer (Phase 0)
Gate already satisfied by evidence (banner) — no build dependencies.

### Core Layer (Phase 1)
- **strunk-ruling-inject hook**: depends on [strunk 0.2.0 installed cache] (shipped).
- **settings.json wiring**: depends on [strunk-ruling-inject hook].

### Integration Layer (Phase 2)
- **per-language canaries, rules-tree retirement, sort-agent-setup sweep**: depend on [settings.json wiring].

## Implementation Phases

### Phase 0: Prove injected context is OBEYED (the gate) — SATISFIED 2026-07-13
**Tasks**:
- [x] Obedience gate — PASSED BY EVIDENCE (banner above): 3/3 obeyed on `.css` with genuine attributed strunk guidance and no rules files present. Do NOT re-run the unattributed absurd-canary form (ZEBRAFISH): the banner documents it is received, recognised as prompt injection, and REFUSED — a re-run would false-falsify a viable PRD. Residual risk (only `.css` tested; released-cache delivery) is owned by Phase 2's per-language canaries.

### Phase 1: Build the hook
**Tasks**:
- [ ] Implement the injection hook + throttle, Python, stdlib-only, exit 0 on any error (depends on: Phase 0). Acceptance: unit tests cover path→skill mapping, version resolution, throttle, and the malformed-store rebuild path.
- [ ] Wire it into `settings.json` (depends on: previous). Acceptance: hook fires; suppressed-path latency p95 < 150ms.

### Phase 2: Prove delivery, then retire the tree
**Tasks**:
- [ ] Canary test per language (depends on: Phase 1). Acceptance: a ruling planted in the strunk skill is obeyed by a fresh session editing a matching file, for `.py`, `.rs`, and `.css`/`.svelte`. This is the gate.
- [ ] Delete `rules/{python,rust,web}/` and fix `sort-agent-setup` (depends on: the gate passing). Acceptance: `rg 'rules/(python|rust|web)'` over `~/.claude` returns nothing that does not exist; buvis commit stages only the named paths by absolute path.

**Exit Criteria**: one home per topic (strunk); delivery proven by canary, not assumed; the top-level rules untouched.

## Test Strategy

- **The canary is the gate**, and it is the only test that matters: plant a ruling no model would invent into a strunk skill, edit a matching file in a fresh session, confirm the ruling is obeyed. Remove the canary afterwards (PRD 00055 left one in a rules file for ~90 seconds — revert immediately and verify with `rg`).
- Unit tests for the hook: path→skill mapping, cache-version resolution, throttle, malformed store, and the exit-0-on-error contract.
- **Measurement gotchas, learned the hard way in 00055 — do not repeat:** grepping a session stream for a skill *name* is a FALSE POSITIVE (the skill list is injected into every session; detect a `"name":"Skill"` tool_use instead), and the headless `stream-json` output does **not** echo injected rules at all, so "the text isn't in the stream" proves nothing about attachment. Test delivery **behaviourally**.

## Risks

- **Injected context might not be OBEYED**, even though it is injectable. This is the one that kills the PRD, and it is not hypothetical: 00055 died because a mechanism that *existed* (skills) was not *used*. Mitigation: Phase 0 canary-tests obedience before a line of the real hook is written.
- **The end state is not "no local config."** The 15 rules files go away, but a hook takes their place in `~/.claude/hooks/`. The win is one content source (strunk, versioned, portable) and one delivery mechanism — not zero local machinery. Say this plainly; do not oversell the consolidation.
- **This trades a zero-moving-parts mechanism for a hook.** `paths:` rules work today with no code. A hook adds latency, a failure mode, and a throttle store. If the drift risk it removes is not worth that, the honest alternative is to keep the duplication and add a cheap **drift detector** instead (a test that greps the 70 pinned rulings in both places and fails when they diverge). Weigh this explicitly in `/design-solution` as the smallest-diff alternative — do not skip past it.
- **Context cost.** Injecting a whole skill on every matching file touch could cost more than today's `paths:` rules. Mitigation: the once-per-(session × skill) throttle; measure the delta before retiring the tree.
- **Version coupling.** A strunk release changes the cache path. Mitigation: resolve the installed version at runtime; never pin.
- **A hook that blocks a tool call is far worse than missing guidance.** Mitigation: exit 0 on every error path, always — the `cartographer-recon-brief.py` contract.
- **Concurrent-commit hazard.** `~/.buvis` is a live shared work-tree; stage only named paths by absolute path, never `git add -A`.
