# Cartographer Phase 5 — Conformance (Layer-Drift Warning)

> Renumbered 00024 → 00114 on 2026-08-01 (backlog tail resequence; mapping in memory `project_backlog_renumber_2026_08`). Atlases were swept fresh the same day (00029 Decision Trail), so criterion 1 is now genuinely evaluable.
> Source discovery: `dev/local/discovery/00007-cartographer-conformance.md`
> Parent architecture: `dev/local/discovery/00001-cartographer-architecture.md`
> Depends on PRDs: `00009-cartographer-foundation-v1.md`, `00011-cartographer-survey-atlas-v1.md`
>
> **Status: CANCELLED 2026-08-23** (operator answered criterion 3 NO at the hold triage; see the final Decision Log entry). Historical status text follows. Depends on Phase 2 atlas `layers` accuracy plus a real layer-drift signal. Tracking runbook: `00029-cartographer-evaluate-phase-4-6-reactivation-v1.md`. **If the autopilot drain selects this file while still deferred: do NOT implement.** Re-check the Reactivation Criteria below; unmet -> append an `extended` Decision Log line, move this file out of the drain's way, and continue with the next PRD (Phase 0 auto-pick has no deferred-skip rule - this note is the guard).
>
> **Revision 2026-07-07**: The heuristic baseline (flag any cross-layer import absent from `dependency_edges`) is cut - edges are a survey snapshot, so every legitimately new edge would warn; that is where the false positives live. v1 detection is atlas-declared `forbidden_imports` only. Reactivation additionally requires `00049-refresh-atlas-automatically-v1` to be live: with 3 atlases, all stale since May, criterion 1 (>80% coverage) cannot be met.
>
> **Delivery note (2026-06-09; loupe renumbered 00029->00030 on 2026-07-08)**: if `00030-loupe-plugin-v1` has shipped by reactivation time, implement Conformance as an atlas-aware rule source inside loupe's `analyze.py` pipeline instead of the standalone PostToolUse hook specced below. loupe already runs per-edit analysis on the same hook event, owns language detection and tool dispatch, and reads the Cartographer atlas for its cascade - a second parallel hook stack would double per-edit process spawns and latency for no gain. The Functional Decomposition below still defines the logic; the Structural Decomposition (hook file, settings.json wiring) moves into `claude-loupe` as a rule module.

**Unblock path (added 2026-08-23):** fastest first - criterion 3 is a free operator
yes/no (are PostToolUse layer-drift warnings wanted at all?); a no cancels this PRD and
retires the 00029 runbook. A yes requires, in order: 00135 (audit-atlas metrics fix, in
backlog), `/survey` on the 7 atlas-less active repos, `forbidden_imports` rules authored
(all atlases carry `[]` today), and criterion 2 evidence from surviving reviews. Do not
re-run the evaluation before those inputs change.

## Reactivation Criteria

This PRD un-defers when ALL hold:

- `audit-atlas` reports >80% of actively-edited repos have `layers` populated and non-degraded (atlas is trustworthy enough to gate on).
- Manual code-review sample (last month) finds ≥3 layer-drift incidents that lint missed.
- User confirms layer-drift warnings are wanted as PostToolUse stderr (vs. catching at code-review time).

If any criterion fails, defer further; reassess event-driven via the `00029` runbook (re-run when `00030` loupe or `00049` atlas auto-refresh ships).

### Decision Log

(populated by `00019` evaluations: `YYYY-MM-DD: <verdict> (<rationale>)`)

- 2026-07-07: extended (atlas coverage ~0% of active repos, all 3 atlases stale since May; blocked on `00049` atlas auto-refresh + `00029` loupe as delivery vehicle; heuristic baseline cut, forbidden_imports only)
- 2026-08-10: extended (criterion 1 UNMET — `active_fresh_pct` 3/10 = 30% against
  a >80% bar: ddb/gems/engram have fresh non-degraded atlases, while cli,
  agoge-gym, web, klyreon, claude-plugins, clusters and home have none. Criterion 2
  UNCLEAR — no sampleable evidence survives: reviews are GC'd and the durable
  verdict ledger keeps no finding text. Criterion 3 not evaluated, moot under
  ALL-criteria. Full measurement and method in `00029`'s Decision Trail.
  **Also recorded for the next evaluation:** every atlas on disk has
  `forbidden_imports: []`, and the 2026-07-07 line above cut this PRD's delivery
  down to "forbidden_imports only" — so even at 100% atlas coverage the hook would
  currently have zero rules to enforce. Whoever un-defers this must check that
  first, or ship a warning surface that can never warn.)
- 2026-08-18: extended (criterion 1 UNMET — `layers` populated and
  non-degraded on 3/10 = 30% of the active set, the same reading as
  2026-08-10, not worse: computed by hand, not from `audit-atlas`'s own
  output, which is silently broken (one-line pointer below). Only
  ddb/gems/engram have `layers` populated and `degraded: false`; cli,
  agoge-gym, klyreon, claude-plugins, clusters, home, zettelkasten have no
  atlas at all. 30% sits far below the 80% bar either way. Additional
  concern, not part of the criterion as written: all three populated atlases
  are also 16 days stale (flagged). Criterion 2 UNCLEAR — 11 non-hidden
  `.md` review files survive (up from 2 on 2026-08-10) but none touch a
  layer-boundary/architecture-violation finding; they're all
  autopilot-tooling PRDs (00051/00093/00117-00120) with no cartographer
  layers of their own to drift, and the durable verdict ledger (47 lines)
  still keeps no finding text. Criterion 3 UNCLEAR, moot under ALL-criteria
  (same reasoning as 2026-08-10). `forbidden_imports` carryover check: still
  `[]` on all 7 atlases, unchanged since 2026-07-07 — the hook would still
  have zero rules to enforce even at full coverage. Full measurement and
  method in `00029`'s Decision Trail. `report.py` has two schema-mismatch
  bugs that silently zero its headline metrics — raised, not fixed, out of
  this PRD's scope; filed as `00135-fix-audit-atlas-schema-mismatches-v1.md`.)
- 2026-08-23: cancelled (operator decision at hold triage: criterion 3 answered
  NO - edit-time layer-drift warnings are not wanted; under ALL-criteria that
  ends the PRD regardless of coverage. Context: three evaluations found zero
  layer-drift incidents review missed, `forbidden_imports` is `[]` on every
  atlas, and 7/10 active repos were never surveyed. Review lenses remain the
  drift-catching surface. File moved to `cancelled/`; the `00029` runbook
  retires the same day. `00135` (audit-atlas metrics fix) proceeds
  independently - the skill serves survey and health reporting beyond
  conformance.)

## Overview

### Problem Statement

Even after Echo (no duplicate symbols) + Recon Brief (atlas injected) + `/architect` (plan-first), code still drifts at the layer boundary: a DB call appears in a UI file, an API handler reaches into a repository's internals, business logic leaks into a controller. Lint can't catch this — it's an architectural concern. Conformance is a non-blocking PostToolUse warning that surfaces layer crossings against atlas-recorded `layers` and `forbidden_imports` rules.

### Target Users

The agent (sees stderr warnings after Edit/Write/MultiEdit). End-user observable effect: warnings inline with tool output; audit log entries for `audit-conformance` to consume.

### Success Metrics

- audit-conformance reports steady-state low layer-drift rate in surveyed repos (<5% of edits trigger warnings after week 4).
- False-positive rate <20% in week-1 manual sampling.
- Hook performance: <500ms p95 on 1000-line files.
- Atlas-missing path is a graceful no-op + one-liner suggestion ("atlas missing for layer check; run /survey").
- pytest coverage for layer detection, forbidden-import detection, missing-atlas, file-size cap, audit emission.

## Functional Decomposition

### Capability: Layer Detection on the Edited File

Map the just-edited file to one of the atlas's declared layers.

#### Feature: Path-based layer assignment

- **Description**: Given the file path, find which `atlas.json.layers[layer]` directory list contains it.
- **Inputs**: edited file path; `atlas.json.layers`.
- **Outputs**: `layer_detected: str | None`.
- **Behavior**: Longest-prefix match against `layers[*]` directory entries; `None` when no layer matches (treat file as unassigned, skip warning).

### Capability: Import / Call Inspection

Tree-sitter parse the just-edited file to extract imports + cross-module calls.

#### Feature: Tree-sitter import extraction

- **Description**: Pull import paths/symbols from the file using the same grammar set as Echo/Survey.
- **Inputs**: file path + content.
- **Outputs**: `list[{symbol, source}]` where `source` is the imported module path/dot-path.
- **Behavior**: Lazy `_lib_cartographer.try_import_tree_sitter()`; fall back to regex import detection (less accurate) when missing; record `degraded: true` in audit on fallback.

#### Feature: Cross-layer mapping

- **Description**: For each import source, determine which layer (if any) it belongs to.
- **Inputs**: import source path; `atlas.json.layers`.
- **Outputs**: `imported_layer: str | None`.
- **Behavior**: Same longest-prefix match as edited-file layer assignment.

### Capability: Drift Decision

Combine atlas rules + heuristic baseline.

#### Feature: Heuristic baseline (any cross-layer import is a candidate)

- **Description**: Default to flagging cross-layer imports unless explicitly allowed.
- **Inputs**: `(layer_detected, imported_layer)` pair.
- **Outputs**: candidate-drift bool.
- **Behavior**: When the pair appears in `atlas.json.dependency_edges` AND is not on a `[manual]` whitelist, treat as candidate drift.

#### Feature: `forbidden_imports` rules (atlas-declared)

- **Description**: Strict block list of `{from_layer, to_layer}` pairs from atlas.json that are explicitly forbidden.
- **Inputs**: `forbidden_imports`; `(layer_detected, imported_layer)`.
- **Outputs**: forbidden bool.
- **Behavior**: Forbidden = bool match; warn always when forbidden, regardless of heuristic.

#### Feature: Suggestion synthesis

- **Description**: Produce a "route through `<layer>`" suggestion based on dependency edges.
- **Inputs**: `forbidden_imports`, `dependency_edges`.
- **Outputs**: suggestion string.
- **Behavior**: Pick the most-traveled intermediate layer between `from_layer` and `to_layer` from `dependency_edges`; fall back to "consult atlas.md".

### Capability: Stderr Warning Emission

Mirror `design-quality-check.py` shape — non-blocking, never deny.

#### Feature: Warning template

- **Description**: Stderr message in fixed format including file, layer, forbidden symbol+target layer, suggestion, and rationalization reference.
- **Inputs**: file path, layer_detected, forbidden_target, suggestion.
- **Outputs**: stderr text.
- **Behavior**: Format:
  ```
  [Conformance] Layer drift in <file>:
    Layer: <detected-layer>
    Forbidden import: <imported-symbol> from <imported-layer>
    Suggestion: route through <layer-recommended-by-atlas>
    See: ~/.claude/rules/rationalizations.md (existing pattern is overkill)
  ```

### Capability: Skip Rules

Never block; skip cleanly when atlas missing or signal poor.

#### Feature: Skip when no atlas

- **Description**: Skip with one-liner stderr suggestion to run `/survey`.
- **Inputs**: atlas_dir / atlas.json.
- **Outputs**: stderr "atlas missing for layer check; run /survey" + audit `decision:skip, reason:no-atlas`.

#### Feature: Skip when `layers: {}` or no `forbidden_imports`

- **Description**: Some repos legitimately don't have clear layering.
- **Inputs**: atlas.json.
- **Outputs**: clean, audit `decision:skip, reason:no-layers`.

#### Feature: Skip on large files (>2000 lines)

- **Description**: Layer-drift signal is noise on legacy/generated files.
- **Inputs**: file line count.
- **Outputs**: clean, audit `decision:skip, reason:large-file`.

#### Feature: Skip on missing tree-sitter (degraded fallback)

- **Description**: Try regex fallback; if it produces low-confidence import set, skip warn.
- **Inputs**: tree-sitter availability + regex output.
- **Outputs**: skip if no high-confidence imports; audit `decision:skip, reason:no-tree-sitter`.

### Capability: Audit Emission

Per Phase 1's pattern — every decision logged.

#### Feature: Audit-log emission

- **Description**: Append events with `phase: "conformance"`.
- **Inputs**: tool, file, decision, reason, layer_detected, forbidden_target, suggestion.
- **Outputs**: side effect — JSONL line.
- **Behavior**: Schema fields: `ts`, `session`, `phase: "conformance"`, `tool`, `file`, `decision` ∈ {warn, clean, skip}, `reason`, `layer_detected` (warn only), `forbidden_target` (warn only — `{symbol, from_layer, to_layer}`), `suggestion` (warn only).

### Capability: Hook Wiring

Settings.json PostToolUse block alongside `design-quality-check.py`.

#### Feature: PostToolUse Edit|Write|MultiEdit matcher

- **Description**: Append `cartographer-conformance.py` to PostToolUse hook block.
- **Inputs**: settings.json edit.
- **Outputs**: hook fires after every Edit/Write/MultiEdit.
- **Behavior**: Stderr-only; never blocks.

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── hooks/
│   ├── cartographer-conformance.py      # PostToolUse hook entry
│   └── tests/
│       └── test_cartographer_conformance.py
├── settings.json                        # PostToolUse matcher entry (Edit|Write|MultiEdit)
└── cartographer/projects/<hash>/
    └── atlas.json                       # read by hook (Phase 2 produced)
```

### Module: `cartographer-conformance.py`

- **Maps to capability**: All — layer detection, import inspection, drift decision, warning emission, skip rules, audit.
- **Responsibility**: Single-file PostToolUse hook; reads stdin JSON, applies skip + drift logic, emits stderr warning + audit event.
- **Imports**: `_lib_cartographer` (Phase 0); stdlib only.
- **Constraint**: <400 lines. Split into a `cartographer/conformance/` package if it grows.

### Module: `tests/test_cartographer_conformance.py`

- **Maps to capability**: All — layer detection, forbidden imports, heuristic baseline, atlas-missing, large-file skip, tree-sitter fallback, suggestion synthesis, audit shape.

### Module: `settings.json` (data)

- **Maps to capability**: Hook wiring.
- **Responsibility**: Append PostToolUse matcher block alongside `design-quality-check.py`.

## Dependency Graph

### Upstream (required)

- Phase 0 (`00009`): `_lib_cartographer.py` (project_hash, atlas_dir, append_audit, try_import_tree_sitter), `rules/rationalizations.md` for warning footer.
- Phase 2 (`00011`): atlas.json with `layers`, `forbidden_imports`, `dependency_edges`. Without atlas, hook is a graceful no-op.

### Phase 5 (this PRD)

- **`cartographer-conformance.py`** depends on Phase 0 + Phase 2 atlas.json schema.
- **`settings.json` matcher** depends on the hook.
- **Tests** depend on the hook + fixture atlas + fixture files.

### Downstream (out of scope)

- (none — `audit-conformance` skill is in scope, see Phase 5f.)

## Implementation Phases

### Phase 5a: Hook scaffolding + atlas-missing skip

**Goal**: Hook fires on PostToolUse; reads atlas.json or skips cleanly.

**Tasks**:

- [ ] Create `~/.claude/hooks/cartographer-conformance.py`: read stdin JSON, resolve project hash, attempt to read `atlas.json`, skip with one-liner suggestion when missing. (depends on: Phase 0) — Acceptance: hook runs end-to-end on stub input; audit `decision:skip, reason:no-atlas` on missing atlas.
- [ ] Add settings.json PostToolUse matcher block alongside `design-quality-check.py`. (depends on: above) — Acceptance: hook fires after Edit/Write/MultiEdit; verified in audit log.

**Exit Criteria**: Hook is wired; missing-atlas path is a clean no-op.

### Phase 5b: Layer detection + import extraction

**Goal**: Map edited file + its imports to atlas-declared layers.

**Tasks**:

- [ ] Implement longest-prefix layer detection against `atlas.json.layers`. (depends on: 5a) — Acceptance: pytest with fixture atlas + sample files maps each to expected layer; unassigned file returns None.
- [ ] Implement tree-sitter import extraction across the 5 supported languages; regex fallback for missing tree-sitter. (depends on: above) — Acceptance: pytest covers each language; degraded path marked in audit.

**Exit Criteria**: For an edited file, hook produces `layer_detected` and a list of `(imported_symbol, imported_layer)`.

### Phase 5c: Drift decision + suggestion

**Goal**: Decide warn vs clean using `forbidden_imports` + heuristic baseline.

**Tasks**:

- [ ] Implement `forbidden_imports` strict matching. (depends on: 5b) — Acceptance: pytest with `[{"from_layer":"ui","to_layer":"db"}]` and a UI file importing from DB → warn.
- [ ] Implement heuristic baseline (cross-layer imports flagged unless on `[manual]` whitelist). (depends on: above) — Acceptance: pytest with no explicit forbidden list still flags candidate drift.
- [ ] Implement suggestion synthesis using `dependency_edges` to pick most-traveled intermediate layer; fall back to "consult atlas.md". (depends on: above) — Acceptance: pytest verifies suggestion text on fixture data.

**Exit Criteria**: Drift decisions are correct on fixture atlas + fixture files.

### Phase 5d: Stderr warning + skip rules

**Goal**: Emit warnings non-blocking; honor all skip rules.

**Tasks**:

- [ ] Render warning template with file, layer, forbidden symbol+target, suggestion, rationalization reference. (depends on: 5c) — Acceptance: stderr matches expected format; never blocks.
- [ ] Implement skip rules: `layers: {}`, no `forbidden_imports`, file >2000 lines, tree-sitter missing with low-confidence regex. (depends on: 5b) — Acceptance: pytest covers each skip path.

**Exit Criteria**: Warnings appear when expected; skips behave as expected.

### Phase 5e: Audit emission + tests + perf

**Goal**: Lock behavior; verify <500ms p95.

**Tasks**:

- [ ] Emit audit events for warn/clean/skip with full schema. (depends on: 5a–5d) — Acceptance: 100 mixed runs produce 100 well-formed lines.
- [ ] Write `tests/test_cartographer_conformance.py` covering all capabilities. (depends on: above) — Acceptance: pytest green; coverage >80%.
- [ ] Time hook on 100 invocations against 100-line, 1000-line, and 2000-line files; record p50/p95. (depends on: tests) — Acceptance: p95 <500ms on 1000-line files; 2000-line files trigger skip.

**Exit Criteria**: pytest green; perf budget met or documented gap.

### Phase 5f: audit-conformance skill + audit-claude-config wiring

**Goal**: `audit-conformance` skill exists and is launchable via `audit-claude-config`.

**Tasks**:

- [ ] Create `~/.claude/skills/audit-conformance/SKILL.md` filtering `~/.claude/cartographer/audit.jsonl` to `phase:"conformance"`. Report sections: warn rate per surveyed repo, top forbidden-import sources, false-positive candidates (warns ignored across multiple sessions), missing-atlas skip rate. Follow audit-skill canonical shape. (depends on: 5e) — Acceptance: skill runs on real audit.jsonl; report renders; passes `audit-skills`.
- [ ] Append `audit-conformance` to the `code-quality` row in `~/.claude/skills/audit-claude-config/SKILL.md` Arguments table (created in PRD 00010 Phase 1h). (depends on: above, PRD 00010 Phase 1h complete) — Acceptance: `/audit-claude-config code-quality` now includes `audit-conformance`.
- [ ] Append `audit-conformance` to the numbered Audit Registry in `audit-claude-config/SKILL.md` (category `code-quality`, speed `medium`). (depends on: above) — Acceptance: default dashboard includes `audit-conformance`.

**Exit Criteria**: `/audit-claude-config code-quality` runs `audit-conformance` and surfaces findings.

## Test Strategy

### Critical Scenarios

- **Happy path — UI→DB direct import warned**: atlas declares `forbidden_imports: [{from_layer:"ui",to_layer:"db"}]`; edit on `src/ui/page.ts` adds `import {queryUsers} from "src/db/users"`; expected stderr warning + audit `decision:warn, layer_detected:"ui", forbidden_target:{symbol:"queryUsers",from_layer:"ui",to_layer:"db"}, suggestion:"route through services/users"`.
- **Happy path — same-layer import is clean**: edit on `src/services/orders.ts` imports from `src/services/payments.ts`; expected clean + audit `decision:clean`.
- **Edge case — heuristic candidate without explicit rule**: atlas has `forbidden_imports: []` but `dependency_edges` shows UI→Services normally; UI→DB cross-import not on edges → flag as candidate-drift warning.
- **Edge case — atlas missing**: hook skips with one-liner suggestion; audit `decision:skip, reason:no-atlas`.
- **Edge case — `layers: {}`**: hook skips with `decision:skip, reason:no-layers`.
- **Edge case — file >2000 lines**: skip with `decision:skip, reason:large-file`.
- **Edge case — tree-sitter missing**: regex fallback runs; if no high-confidence imports, skip with `decision:skip, reason:no-tree-sitter`.
- **Edge case — `[manual]` whitelist**: cross-layer import allowed by `[manual]` block does not warn.
- **Error case — malformed atlas.json**: skip + audit `decision:skip, reason:atlas-parse-error`; no crash.

## Risks

- **Atlas layer map wrong → false warnings**: user overrides via atlas.json `[manual]` block (Phase 2 nice-to-have); audit-conformance flags noisy patterns over time.
- **Performance**: tree-sitter on every PostToolUse → file-size cap (2000 lines), lazy-import, conservative parse (only imports section).
- **Repo without clear layering**: skip clean when `layers: {}`.
- **Atlas missing**: graceful no-op + one-liner suggestion.
- **MCP write tools bypass**: PostToolUse should match all write paths Edit/Write/MultiEdit; verify MCP write tools still trigger PostToolUse (they should by default).
- **Warning fatigue**: success metric `<5% warn rate after week 4`; if higher, tune rules or scope.

## Open Questions

Carried from discovery doc:

- **Forbidden-import detection source**: confirmed — both heuristic baseline + atlas-declared `forbidden_imports`.
- **File-size cap**: confirmed — skip when >2000 lines.
- **Rationalizations.md reference in warning**: yes — included in template footer ("existing pattern is overkill" maps to forbidden-import context).
