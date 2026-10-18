# Evaluate Cartographer Phases 4–6 reactivation

> Parent architecture: `dev/local/discovery/00001-cartographer-architecture.md`
> Tracks: `00114-cartographer-conformance-v1-deferred.md` (architect and forecast-extensibility are cancelled - files at `cancelled/00013-...` and `cancelled/00015-...` under the OLD cartographer numbering, which collides with active autopilot PRD numbers; always folder-qualify those two)
>
> **Phase B trigger planted 2026-07-09 (PRD 00049 Phase A)**: `00049` shipped its stale-atlas `stale-nudge` (cartographer-stop, namespace `survey-nudge`). Evaluate this runbook's atlas-freshness path on or after **2026-08-06** (~4 weeks): read `audit-atlas` freshness + `stale-nudge` audit events; if ≥80% of repos edited in the last 14 days lack a <14-day atlas, decide scheduled `/survey` sweep vs. atlas sunset per `00049` Phase B, and record the verdict in this trail. Scheduling automation is unavailable (CronCreate is session-only), so this dated line IS the trigger — the fallback the PRD names.
>
> **Revision 2026-07-07 (numbers updated 2026-07-08 after the backlog renumber)**: First evaluation ran (Decision Logs in the tracked PRDs). Architect and forecast-extensibility are superseded - spirit folded into `design-solution`'s Inputs and template; files moved to `cancelled/`. Only conformance (`00114` (ex-`00024`)) remains deferred, blocked on `00030` (loupe, its delivery vehicle) and `00049` (atlas auto-refresh). Cadence is now **event-driven** - re-run when either of those ships (`00049` Phase B invokes this runbook explicitly) - not monthly; two months of silence proved the monthly-memory mechanism doesn't work. This file is a recurring decision runbook, not a build PRD: **if the autopilot drain selects it before `00030` and `00049` have shipped, the criteria cannot be met - record one `extended` evaluation and complete, do not build anything.** Phase B automation stays cancelled by YAGNI (the manual checklist has run once).

## Unblock Path (added 2026-08-23)

Inputs that can change the verdict, in dependency order:

1. PRD 00135 (backlog) fixes `audit-atlas`'s silently zeroed metrics - until it ships,
   coverage must be hand-counted (as the 2026-08-18 run did).
2. `/survey` the 7 active repos with no atlas (cli, agoge-gym, klyreon, claude-plugins,
   clusters, home, zettelkasten) - criterion 1 cannot cross 80% otherwise.
3. Author `forbidden_imports` rules in the surveyed atlases - every atlas carries `[]`
   today, so conformance would ship a warning surface that can never warn.

Re-running this runbook before (1) and (2) change re-buys the same EXTEND verdict
(measured $53.63 on 2026-08-18). Cheapest decision first: 00114's criterion 3 is a free
operator yes/no that can cancel the whole conformance branch and retire this runbook.

## Decision Trail

- 2026-08-23: **RETIRED (runbook closed).** Operator answered `00114` criterion 3
  NO at the hold triage (edit-time layer-drift warnings not wanted), cancelling
  the last PRD this runbook tracks; with architect and forecast-extensibility
  already cancelled 2026-07-07, nothing remains to evaluate. Both files move to
  `cancelled/`. `00135` (audit-atlas fix, in backlog) proceeds independently.
  The Unblock Path above is moot; kept for the record.
- 2026-08-18: **Evaluation RUN (autopilot batch 202608180438).** Verdict on
  `00114`: **EXTEND** — criterion 1 still measurably unmet, same reading as
  2026-08-10 (30%, far below the 80% bar either way).
  - **Criterion 1 (`audit-atlas` >80% of actively-edited repos have `layers`
    populated and non-degraded): UNMET, 3/10 = 30%** — same as the 2026-08-10
    reading, not worse. Active set from `instincts/projects.json` `last_seen`
    within 14d of 2026-08-18 (cutoff 2026-08-04): 10 non-global entries, all
    qualify (earliest is engram at 2026-08-05). Exactly 3 of the 10 have
    `layers` populated and `degraded: false`: ddb (`3f951e987a4f`, 11
    layers), gems (`6a85e702bdfb`, 6 layers), engram (`4e5634efc659`, 1
    layer). The 7 remaining active repos (cli, agoge-gym, klyreon,
    claude-plugins, clusters, home, zettelkasten) have never had an atlas at
    all. 30% sits far below the 80% bar, so the verdict stays EXTEND. **This
    number was computed by hand, not read from `audit-atlas`'s own printed
    aggregate** — see the tooling finding below.
  - **Staleness (additional concern, not part of criterion 1 as written):**
    the criterion says nothing about freshness. The three populated atlases
    (ddb, gems, engram) are all 16 days stale with the staleness flag set
    (surveyed 2026-08-01).
  - **Mandatory `forbidden_imports` carryover check:** every atlas on disk
    (all 7) still has `forbidden_imports: []`, unchanged since the
    2026-07-07 note — 0% coverage or 100%, the hook has zero rules to
    enforce either way.
  - **Criterion 2 (manual sample finds ≥3 layer-drift incidents lint
    missed): UNCLEAR, evidence base improved but still irrelevant.** 11
    non-hidden `.md` review files survive under `dev/local/reviews/` (up from
    2 on 2026-08-10; 17 `.md` files counting 6 hidden reviewer-scaffolding
    templates, 15 non-hidden files of any extension counting 4 JSON verdict
    ledgers, 21 files total) plus the GC-exempt `ledger/review-verdicts.jsonl`
    (47 lines, schema unchanged: `ts, file, prd, verdicts, reviewers` — still
    no finding text). Grepped all 11 surviving `.md` reviews for
    layer-drift/architecture-boundary language: zero hits. They cover PRDs
    00051, 00093, 00117-00120 — all autopilot-tooling changes to
    `~/.claude/skills/`, none of which have cartographer-tracked layers of
    their own to drift, so this evidence base can't speak to the criterion
    even though more of it now survives.
  - **Criterion 3 (user confirms PostToolUse stderr warnings are wanted):
    UNCLEAR — moot this run,** same reasoning as 2026-08-10 (criterion 1
    already fails and the PRD is ALL-criteria).
  - **New finding this run, raised not fixed (out of scope for this PRD —
    no `~/.claude/skills/` edits belong here per this PRD's own design):**
    `~/.claude/skills/audit-atlas/scripts/report.py` has two schema-mismatch
    bugs that silently zero its two headline numbers rather than erroring.
    (1) `load_active_hashes` guards on `isinstance(entries, list)`, but the
    real `instincts/projects.json` is a dict keyed by hash with a `last_seen`
    field (not a list of `{hash, last_active}` objects) — the function always
    returns an empty set, so the script prints `active_fresh_pct: n/a` no
    matter what. (2) the layer-population loop guards on
    `isinstance(v, dict) and v.get("files")`, but every real `atlas.json`
    layer value is a flat list of file paths, not a `{"files": [...]}` dict —
    every atlas prints `0/N layers populated (0%)` regardless of actual
    content (verified directly: `3f951e987a4f`/ddb has 11 real, non-empty
    layers). Both bugs were confirmed by reading the live schema directly and
    hand-computing the correct numbers (above) rather than trusting the
    script. **Any prior evaluation of this runbook that quoted the script's
    own printed aggregate instead of hand-computing — none did; both 2026-08-10
    and this run hand-computed — would have been misled.** Filed as
    `00135-fix-audit-atlas-schema-mismatches-v1.md` in `dev/local/prds/backlog/`
    (design doc for `00029` explicitly excludes `~/.claude/skills/` code
    changes from this runbook's scope, so the fix is filed there, not built
    here).
  - **Phase A literal step skipped this cycle, by substitution, not by
    omission.** `/audit-claude-config code-quality` was not run. Evidence
    above came from reading sources directly: `audit-recon` stays dormant in
    `~/.claude/skills-library/` and can't run without reactivating it, an
    unscoped change; `audit-echo` covers only `phase:"echo"` duplicate-symbol
    events, not architectural layer drift, so it isn't evidence for this
    runbook; and `audit-atlas`'s own printed aggregate is broken (both
    headline numbers silently zero per the tooling finding above), so running
    it now would produce a misleading dashboard, not evidence. This resolves
    the design doc's open literal-vs-substitution question in favor of
    substitution — future runs don't need to re-derive it.
- 2026-08-10: **Post-sweep evaluation RUN** (the "next evaluation" the 2026-08-01
  entry below calls for; the dated 2026-08-06 trigger has also now passed, so both
  triggers are satisfied). Verdict on `00114`: **EXTEND** — it is an ALL-criteria
  PRD and criterion 1 is measurably unmet.
  - **Criterion 1 (`audit-atlas` >80% of actively-edited repos have populated,
    non-degraded layers): UNMET, `active_fresh_pct` = 3/10 = 30%.** Active set from
    `instincts/projects.json` `last_seen` within 14d (all 10 non-global entries
    qualify, 2026-08-03..2026-08-09). Fresh, non-degraded, layers-populated atlases
    exist for exactly ddb (11 layers), gems (6), engram (1). **No atlas at all** for
    cli, agoge-gym, web, klyreon, claude-plugins, clusters, home. The two hash
    namespaces (`cartographer/projects/` and `instincts/projects.json`) were proven
    to be the SAME before cross-referencing — ddb/engram/gems resolve identically in
    both — and the date comparison was proven non-vacuous with a deliberately stale
    control cutoff.
  - **Criterion 2 (manual sample finds ≥3 layer-drift incidents lint missed):
    UNCLEAR — no evidence base survives to sample.** `dev/local/reviews/` holds 2
    files (the rest GC'd) and the GC-exempt `ledger/review-verdicts.jsonl` carries
    only `file, prd, reviewers, ts, verdicts` — rubric pass/fail, **no finding
    text** — spanning 2026-07-17..2026-08-02. Per this runbook, UNCLEAR defaults to
    extend. To make this criterion evaluable, the verdict harvest would have to
    retain finding text, which is a change to `purge-devlocal`, not to `00114`.
  - **Criterion 3 (user confirms PostToolUse stderr warnings are wanted): NOT
    EVALUATED — moot this run.** Criterion 1 already fails and the PRD is
    ALL-criteria, so asking would spend the operator's attention on a decision that
    cannot change the outcome. It remains the open question for the first
    evaluation where criteria 1 and 2 both pass.
  - **Why coverage FELL from the 2026-08-01 sweep rather than holding**: the sweep
    refreshed the 6 atlases that existed, and coverage was read against the active
    set of that day. Nine days later the active set has GROWN — cli, agoge-gym
    (item 5's new repo), klyreon, web, clusters, claude-plugins and home are all
    newly active with no atlas ever created. Coverage is a ratio, and the sweep only
    moves the numerator for repos that already have an atlas.
  - **This invalidates the queued nag's trigger, and that is the actionable finding
    of this run.** The 2026-08-01 schedule decision was "nag when the newest atlas
    among active repos is >14d old". The three existing atlases are 9 days old, so
    that nag would stay SILENT while real coverage sits at 30%. The condition that
    matters is *missing* atlases for active repos, not *stale* ones. The queued
    `brief-portfolio` edit must not ship as specified; it is now unblocked
    (`00051` is in `done/`) but its trigger needs redesign first. Raised to the
    operator rather than silently redesigned.
- 2026-08-01 (later the same day): tracked PRD renumbered 00024 → 00114 in the
  backlog tail resequence (mapping: memory `project_backlog_renumber_2026_08`);
  every reference in this runbook updated. Historical decision-log lines inside
  the tracked PRD keep whatever number they were written with.

- 2026-08-01: **Phase-B atlas-freshness evaluation RUN (1 week early, ~3.2 of 4
  weeks of data — operator-initiated during the hold/ triage).** Criterion MET:
  actively-edited repos last 14d (echo audit log) = buvis-home, doogat/ddb,
  tbouska/figure-skating-guide, buvis/gems, buvis/engram, buvis/claude-aegis
  (+2 trace); atlases on disk = 4, only ONE <14d old → ≥83% of active repos
  lack a fresh atlas. stale-nudge fired 16× total since planting (2026-07-09)
  with zero resulting refreshes — nudging alone does not sustain freshness.
  **Verdict (operator): SURVEY SWEEP + SCHEDULE** — refresh atlases for the
  active repos now and add a scheduled recurring sweep so freshness persists
  without a human-memory trigger. 00114 (ex-00024) conformance stays viable (its
  criterion 1 becomes genuinely satisfiable); its remaining criteria (≥3
  layer-drift incidents, user confirmation of PostToolUse warnings) are still
  unmet — next evaluation reads them against post-sweep data.
- 2026-08-01 (execution): sweep RAN — 6 atlases refreshed (ddb,
  figure-skating-guide, gems, engram, claude-aegis, buvis-home), all
  `degraded: false` under the tree-sitter pack, staleness flags cleared.
  Schedule mechanism (operator): **piggyback on brief-portfolio**, mirroring
  its brush-nag pattern — nag when the newest atlas among active repos is
  >14d old, offer the inline sweep. Sweep script parked durably at
  `~/.local/bin/atlas_sweep.py` (untracked). The brief-portfolio SKILL.md
  edit is QUEUED until PRD 00051's review closes (no buvis commits during a
  live review); adopt the script into buvis in the same change.

## Overview

### Problem Statement

Phases 4 (Architect), 5 (Conformance), and 6 (Forecast Extensibility) are deferred until Phase 0–3 audit data justifies them. This PRD is the periodic decision gate: read the audit data, check each deferred phase's `## Reactivation Criteria` section, then un-defer / extend / cancel. Without this PRD, the deferred phases silently rot in `backlog/`.

### Target Users

User (event-driven: when `00030` loupe or `00049` atlas auto-refresh ships; `00049` Phase B invokes this runbook).

### Success Metrics

- One decision recorded per deferred phase per evaluation run.
- No deferred phase sits >12 months without an explicit "extend" decision (sunset signal).
- When a phase un-defers, the `-deferred` suffix is removed and any `Depends on PRDs:` lines pointing at the old name are fixed in the same change.

## Functional Decomposition

### Capability: Audit-data ingestion

Read fresh audit reports (or invoke them inline) so each criterion has a current evidence point.

#### Feature: Per-phase criteria evaluation

- **Description**: For each still-deferred tracked PRD (currently only `00114` (ex-`00024`), conformance), walk the `## Reactivation Criteria` bullets and classify each as MET / UNMET / UNCLEAR with one-line evidence.
- **Inputs**: deferred PRD path; reports from `audit-echo`, `audit-atlas`, `audit-recon`; user confirmation prompts where the criterion is subjective.
- **Outputs**: per-PRD verdict ∈ {un-defer, extend, cancel} with rationale.
- **Behavior**: Conformance (`00114` (ex-`00024`)) is ALL-criteria: every bullet MET to un-defer. UNCLEAR defaults to extend; user override allowed. (The cancelled architect/forecast PRDs are no longer evaluated.)

### Capability: PRD lifecycle action

Apply the verdict to disk.

#### Feature: Un-defer rename

- **Description**: Rename `*-v1-deferred.md` → `*-v1.md`; update inbound `Depends on PRDs:` references; append a Decision Log entry.
- **Inputs**: PRD path; verdict.
- **Outputs**: renamed file; updated dependents; appended log line.
- **Behavior**: Plain `mv` (PRDs are local-only — `dev/local/` is gitignored). Then rg for the old filename across `dev/local/prds/` and update each match. Append `- YYYY-MM-DD: un-deferred (<rationale>)` to the PRD's Reactivation Criteria > Decision Log.

#### Feature: Extend deferral

- **Description**: PRD stays deferred; one log line added.
- **Inputs**: PRD path; reason text.
- **Outputs**: appended Decision Log entry.
- **Behavior**: Append `- YYYY-MM-DD: extended (<reason>)` under the PRD's Decision Log subsection.

#### Feature: Cancel

- **Description**: When a phase is determined unwanted, move PRD to `dev/local/prds/cancelled/` (creating the directory if missing). User confirmation required.
- **Inputs**: PRD path; explicit user confirmation.
- **Outputs**: moved PRD; logged decision; dependents flagged.
- **Behavior**: Plain `mv` to `dev/local/prds/cancelled/`. Append `- YYYY-MM-DD: cancelled (<reason>)` to the PRD before moving. If any other PRD lists this one in `Depends on PRDs:`, surface that to the user — they must reconsider those dependents.

## Implementation Phases

### Phase A: Manual checklist (first run)

**Goal**: First evaluation runs as a manual walkthrough — no automation yet.

**Tasks**:

- [ ] Run `/audit-claude-config code-quality` to produce fresh audit-* reports for `audit-echo`, `audit-atlas`, `audit-recon` (and `audit-conformance` if Phase 5 has un-deferred and shipped). — Acceptance: dashboard table populated.
- [ ] Read `00114-cartographer-conformance-v1-deferred.md` Reactivation Criteria; evaluate each bullet against the report; record verdict + rationale. (Architect and forecast: cancelled 2026-07-07, skip.)
- [ ] Apply verdict (rename / extend / cancel). For un-defer: also update `Depends on PRDs:` references in dependent PRDs.

**Exit Criteria**: One Decision Log entry per deferred PRD; any un-deferred PRDs renamed and dependents fixed.

### Phase B: Automate evaluation (deferred until Phase A has run twice)

**Goal**: If the manual checklist proves valuable across two runs, codify as a skill.

**Tasks**:

- [ ] Create `evaluate-deferred-prds` skill that: (1) finds `*-deferred.md` files in any `prds/` folder, (2) parses Reactivation Criteria bullets, (3) invokes the right `audit-*` skills, (4) prompts the user for subjective criteria, (5) applies the verdict.

**Exit Criteria**: Out of scope for first run.

## Test Strategy

### Critical Scenarios

- **Happy path — un-defer**: all `00114` (ex-`00024`) Reactivation Criteria MET → `-deferred` suffix dropped; any `Depends on PRDs:` lines pointing at the old filename updated; Decision Log entry appended.
- **Happy path — extend**: any criterion UNMET on `00114` (ex-`00024`) → file untouched except for one log line.
- **Edge case — partial-MET on Conformance**: one bullet UNCLEAR → defaults to extend; user can override to un-defer with explicit confirmation.
- **Error case — deferred PRD missing Reactivation Criteria section**: flag as malformed; user fixes the PRD before re-running.
- **Error case — cancelling a PRD others depend on**: surfaces dependents; require user to reconsider before move.

## Risks

- **PRDs sit in deferred state forever**: 12-month sunset signal; if a phase hasn't earned reactivation in a year, it probably never will. Reassess whether the design is still right.
- **Audit data thin in early months**: first 2–3 evaluations will mostly extend. That's expected.
- **User runs this once and forgets**: mitigated by the explicit trigger in `00049` Phase B (which schedules its 4-week follow-up when Phase A ships and names this runbook).

## Open Questions

- **Cadence**: resolved 2026-07-07 - event-driven (see revision note); no standing schedule.
- **Cancellation requires user confirmation**: yes — never auto-cancel a deferred phase.
- **Phase B (skill automation) — track here or as a separate PRD?**: defer until Phase A has run twice and a clear automation pattern emerges.
