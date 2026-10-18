# Refresh Cartographer atlas automatically

> Parent architecture: `dev/local/discovery/00001-cartographer-architecture.md`
> Related: `00024-cartographer-conformance-v1-deferred.md` (reactivation gated on this), `00030-loupe-plugin-v1.md` (cascade cut until the atlas lives)

## Overview

### Problem Statement

Everything atlas-dependent in the cartographer suite starved. Evidence (2026-07-07 audit): 3 atlases exist, all stale since 2026-05-18/19, none for actively-edited repos; Recon Brief has fired 4 times ever; atlas-free Echo logged ~54K events in the same window. Root cause: atlases update only when the user remembers to run `/survey`, and nobody remembers. Without a freshness mechanism, every atlas consumer (recon, conformance, loupe cascade, design-solution grounding) stays dead regardless of its own design.

### Target Users

The agent (fresh atlas context in recon briefs and design-solution) and the user (working atlas consumers without manual `/survey` discipline).

### Success Metrics

- ≥80% of repos edited in the last 14 days have an atlas fresher than 14 days (`audit-atlas` measures this).
- Recon Brief inject count rises from ~0 to ≥1/repo/week on active repos.
- No perceptible Stop latency added (the staleness check is an mtime stat, not a survey).

## Functional Decomposition

### Capability: Staleness nudge at Stop

`cartographer-stop.py` already fires at every Stop (~2.5K audit events) - extend it, don't add a hook.

#### Feature: Stale-atlas detection + nudge

- **Inputs**: repo hash, atlas.md mtime, count of files edited this session in this repo.
- **Outputs**: one stderr nudge ("atlas stale (N days) - run /survey"), or silence.
- **Behavior**: Fire only when the session edited files in the repo AND atlas.md is missing or older than 14 days. Throttle 1/(repo × week) via `is_checked`/`mark_checked`. Audit event `phase:"survey", event:"stale-nudge"`.

### Capability: Mechanical refresh (deliberately out of v1)

A Stop hook cannot run a skill, so full auto-rebuild is not v1. If 4 weeks of nudges don't move the freshness metric, Phase B decides between a scheduled `/survey` sweep over active repos and declaring the atlas dead (which cancels `00024`'s atlas dependency and simplifies the suite to Echo only).

## Implementation Phases

### Phase A: Stale-nudge in cartographer-stop

- [ ] Add staleness check + throttled stderr nudge + audit event to `cartographer-stop.py`. — Acceptance: pytest covers fresh atlas (silent), stale atlas + edits (nudge once), second Stop same week (suppressed), session with no edits in repo (silent), missing atlas (nudge).
- [ ] Plant the Phase B trigger: one-time scheduled check ~4 weeks out (/schedule), falling back to a dated follow-up line in the batch report if scheduling is unavailable. — Acceptance: the trigger names the `00029` evaluation runbook and this PRD's Phase B; evidence pasted.

**Exit Criteria**: Nudge fires on real stale-atlas sessions; audit log shows `stale-nudge` events; no added Stop latency beyond an mtime stat; Phase B trigger planted. This PRD completes at Phase A - Phase B runs outside the drain.

### Phase B: Evaluate after 4 weeks (outside the drain - fired by the planted trigger)

- [ ] Read `audit-atlas` + `stale-nudge` events. If freshness metric unmet, decide: scheduled `/survey` sweep vs. atlas sunset. Run the `00029-cartographer-evaluate-phase-4-6-reactivation-v1.md` runbook and record the verdict in its revision trail.

**Exit Criteria**: One recorded decision; suite direction (atlas lives / Echo-only) settled.

## Test Strategy

### Critical Scenarios

- **Happy path**: stale atlas + edits this session → one nudge + one audit line.
- **Edge case**: fresh atlas → silent. Missing atlas + edits → nudge.
- **Edge case**: throttle - second stale Stop in the same repo-week → suppressed.
- **Edge case**: session touching no files in the repo → silent.

## Risks

- **Nudge fatigue**: weekly throttle; Phase B sunsets the whole idea if nudges are ignored - a nudge nobody acts on is worse than none.
- **14-day threshold is a guess**: flagged as such; tune from `audit-atlas` data.

## Open Questions

- Phase B's sweep, if chosen: scheduled session (CronCreate) or a line item in an existing ritual? Decide with 4 weeks of nudge data in hand.
