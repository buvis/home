# loupe Plugin v1

> **Triage decision 2026-07-31 (operator): REFRESH FIRST, then decide backlog
> placement.** Do not un-park or build from this spec as-is — it predates the
> reviewer-ensemble and product-QA discoveries (`dev/local/discovery/00092`
> Rita/Cora/... ensemble, `00091` agoge pack), which may reshape loupe's
> review/QA integration, and the per-edit hook-stack latency budget should be
> re-measured against today's stack (gateguard + cartographer-echo +
> design-quality-check + aegis). Trigger: in a fresh session, run a
> review/refresh pass over THIS file against those two discoveries (e.g.
> `/review-prd-backlog` after moving it to `backlog/`, or a direct design
> review of this file), record the outcome here, then place it. Context: 00030
> is otherwise buildable today (v1 scope-trim 2026-07-07 stands, zero unmet
> dependencies) and is 00114 (ex-00024)-conformance's chosen delivery vehicle.

> **Revision 2026-07-07** (scope trim; overrides the decomposition below where they conflict):
>
> - v1 **cuts Read Coverage Guarding** entirely (`record_read.py`, `guard_edit.py`, `readcoverage.py`, `/loupe-allow-edit`): the 2026-06-09 note already conceded warn-mode false positives (grep results, subagent returns, prior-session context never pass the Read hook), CC's native read-before-edit guard covers the base case, and it adds a hook spawn to every single Read. A warn that is often wrong is noise.
> - v1 **cuts TDI** (`tdi.py`, `/loupe-show-tdi`): solo-dev telemetry with no consumer; the already-deferred weighting formula was the tell. v2 candidate behind demand.
> - v1 **cuts the review-graph cascade** (`cascade.py`): depends on the Cartographer atlas pipeline, which is currently dead (3 atlases, all stale since May, none for active repos). Revisit only after `00049-refresh-atlas-automatically-v1` proves the atlas lives.
> - Commands trim to `/loupe-report` and `/loupe-toggle`; the other four follow the features they reported on (tool health folds into `/loupe-report`).
> - v1 **keeps** the uncovered value: pre-write secrets block, ast-grep + fast-linter analysis with blocking classification (stubs, security), deferred autofix/format + slow lint at `Stop`, tool nudging.
> - Per-edit latency budget is the top risk and the stack is already gateguard + cartographer-echo + design-quality-check + aegis, each a separate Python spawn; the cuts above remove the two riskiest additions (per-Read hook, extra Stop work).
>
> **Revision 2026-06-09** (design review before implementation):
>
> - Compile/type-check-class linters (clippy, svelte-check) moved from per-edit dispatch to the `Stop` queue - clippy compiles the crate and cannot meet the ~1s per-edit budget; a timed-out run is wasted latency with no signal.
> - `read_guard` defaults to `warn` (was unspecified, implicitly `block`): the agent legitimately "reads" code via Grep results, subagent returns, and prior-session context, none of which pass through the Read hook, so `block` false-positives on valid edits. `block` is opt-in per project.
> - TDI v1 is unweighted per-category counts; the open question about a weighting formula is resolved by deferring weights until trend data shows a need.
> - Risks now name the cumulative per-edit hook stack (gateguard, cartographer-echo, design-quality-check) - loupe entry points must stay import-light and short-circuit when disabled.
> - Cartographer Phase 5 Conformance (`00114 (ex-00024)`, deferred; was numbered 00014 pre-renumber) folds into loupe's `analyze.py` as an atlas-aware rule source if reactivated after loupe ships, instead of shipping as a parallel PostToolUse hook.

## Overview

### Problem Statement

AI-driven editing in Claude Code lands code-quality issues - stub bodies,
unsafe patterns, unformatted code, leaked secrets - that surface late or never.
The Pi ecosystem solves this with `pi-lens`, which gives real-time inline
feedback on every write/edit, but it is a Pi extension and cannot run in Claude
Code. `loupe` reimplements that capability natively as a Buvis plugin: a fast,
language-aware feedback loop on every `Write`/`Edit`, with blocking guards for
secrets, stubs, and security violations.

### Target Users

The solo developer running Claude Code across Rust and Python projects (plus
JS/TS, Svelte, shell), who wants quality problems caught at edit time rather
than at review time, without leaving the Claude Code toolchain.

### Success Metrics

- Behavioral test matrix green: planted secret aborts the write; a stub edit
  blocks; a security-rule violation blocks; advisory findings render inline;
  `Stop` runs deferred fix/format/slow-lint exactly once; a missing-but-needed
  tool nudges exactly once per project.
- Test suite at 80%+ line coverage.
- `analyze.py` adds under ~1s p50 latency on a typical source file.
- Dogfood session: loupe installed and used for a real editing session on a
  Buvis repo (e.g. `claude-strunk` or a Rust project), confirmed useful and not
  noisy.

## Functional Decomposition

### Capability: Session & Configuration

Bootstraps loupe per session and resolves runtime settings.

#### Feature: Session bootstrap
- **Description**: On `SessionStart`, detect project root and language profile, resolve available tools, reset runtime state.
- **Inputs**: `SessionStart` hook JSON (cwd).
- **Outputs**: Fresh `state.json` runtime block; cached language profile and tool map.
- **Behavior**: Compute project hash from root path; probe tools via PATH/mise; clear format queue, session findings, read-ranges; preserve TDI history and nudge log.

#### Feature: Config resolution
- **Description**: Load global config with optional per-project override.
- **Inputs**: `~/.claude/loupe/config.json`, optional per-project config.
- **Outputs**: Effective config (`enabled`, `immediate_fix`, `read_guard`).
- **Behavior**: Deep-merge per-project over global; rebuild from defaults if missing/malformed.

#### Feature: Tool resolution and nudging
- **Description**: Locate linters/formatters; never install; nudge once per project for a missing-but-needed tool.
- **Inputs**: Tool name, edited file language.
- **Outputs**: Resolved path or "absent"; queued nudge entry.
- **Behavior**: Try PATH, then mise shims, then `mise which`. On absent-but-needed, record a nudge if not already in the persisted `nudged` set.

### Capability: Secrets Guarding

Blocks credential leaks before they are written.

#### Feature: Pre-write secrets scan
- **Description**: Scan the new content of a write/edit for credentials; abort on detection.
- **Inputs**: `PreToolUse` hook JSON for `Write|Edit|MultiEdit` (new content).
- **Outputs**: Exit 0 (clean) or exit 2 with the matched secret category.
- **Behavior**: Match content against a credential pattern set; exit 2 aborts the write.

### Capability: Read Coverage Guarding

Prevents edits to code the agent has not seen, beyond CC's native guards.

#### Feature: Read range recording
- **Description**: Record which line ranges of each file the agent has read this session.
- **Inputs**: `PostToolUse` hook JSON for `Read` (path, offset, limit).
- **Outputs**: Per-file read-range list in runtime state.
- **Behavior**: Append and merge overlapping ranges; whole-file reads collapse to a full range.

#### Feature: Out-of-range edit guard
- **Description**: Block an edit whose target lines fall outside previously read ranges.
- **Inputs**: `PreToolUse` hook JSON for `Write|Edit|MultiEdit`; recorded read ranges; `read_guard` config.
- **Outputs**: Exit 0, exit 2 (block), or stderr warning (warn mode).
- **Behavior**: Resolve edit target lines; if uncovered and mode is `block`, exit 2; `warn` prints; `off` skips. Markdown/text/log files and `/loupe-allow-edit` overrides are exempt. Default mode: `warn` - the agent legitimately "reads" code via Grep results, subagent returns, and prior-session context, none of which pass through the Read hook, so `block` false-positives on valid edits. `block` is opt-in per project.

### Capability: Code Analysis

Runs read-only quality analysis on every write/edit and classifies findings.

#### Feature: Linter dispatch
- **Description**: Run the language-appropriate native linter on the edited file.
- **Inputs**: Edited file path, language, resolved tool map.
- **Outputs**: Linter findings (advisory).
- **Behavior**: Select linter by language; skip silently if absent; enforce per-tool timeout. Fast linters run per-edit (ruff, biome/eslint, stylelint, sqlfluff, rubocop, shellcheck). Compile/type-check-class linters (clippy, svelte-check) cannot meet the per-edit latency budget - clippy compiles the crate - so they are queued and run once at `Stop` alongside autofix/format, with findings rendered as advisory in the Stop summary.

#### Feature: ast-grep rule dispatch
- **Description**: Run the loupe ast-grep rule pack against the edited file.
- **Inputs**: Edited file path, language, rule pack.
- **Outputs**: Rule findings tagged security / correctness / style / stub.
- **Behavior**: Run JS/TS/Python (ported) or Rust (authored) rules for the file's language; collect matches with category tags.

#### Feature: Findings classification and blocking
- **Description**: Split findings into blocking and advisory and act on them.
- **Inputs**: Linter + ast-grep findings.
- **Outputs**: Exit 2 with blocking detail, or exit 0 with advisory feedback on stdout; updated session findings and TDI counters.
- **Behavior**: Blocking = stub markers + security-category rules; advisory = correctness, style/smell, linter errors. Exit 2 only for blocking; everything else prints inline.

### Capability: Fix & Format

Applies safe autofixes and formatting without mid-turn staleness.

#### Feature: Fix/format queue
- **Description**: Queue each edited file for end-of-turn fix, format, and slow-lint (clippy, svelte-check).
- **Inputs**: Edited file path from `analyze.py`.
- **Outputs**: Append to the runtime format queue.
- **Behavior**: When `immediate_fix` is true, `analyze.py` fixes/formats inline instead of queuing.

#### Feature: Deferred autofix
- **Description**: Apply safe autofixes to queued files at `Stop`.
- **Inputs**: Format queue, resolved tools.
- **Outputs**: Modified files; per-file fix summary.
- **Behavior**: Run safe-only autofixes (ruff `--fix`, biome `check --write`, eslint `--fix`, stylelint `--fix`, sqlfluff `fix`, rubocop `-a`) before formatting.

#### Feature: Config-gated formatter dispatch
- **Description**: Format queued files using project-configured formatters.
- **Inputs**: Queued files, project formatter configs.
- **Outputs**: Formatted files; summary of files changed and any formatter failure.
- **Behavior**: Run a formatter only when project config indicates it; nearest-config-wins on conflicts; Biome/Ruff defaults for unconfigured JS-TS/Python.

### Capability: Telemetry & Reporting

Surfaces project health and diagnostics.

#### Feature: Technical Debt Index
- **Description**: Compute and trend a Technical Debt Index from analysis findings.
- **Inputs**: Session findings counts by category over time.
- **Outputs**: Current TDI value and historical trend in persistent state.
- **Behavior**: Unweighted per-category finding counts (raw counts trend honestly and need no weight tuning; a weighting formula is deferred until trend data shows a need); appended to TDI history at `Stop`.

#### Feature: Review-graph cascade
- **Description**: At `Stop`, render which files the turn's changes affected, using Cartographer's atlas.
- **Inputs**: Cartographer atlas at `~/.claude/cartographer/projects/<hash>/`; turn's edited files.
- **Outputs**: Cascade summary, or nothing if Cartographer is absent.
- **Behavior**: Read the atlas if present and version-compatible; degrade to "cascade unavailable" otherwise.

#### Feature: Slash commands
- **Description**: User-facing reports and controls.
- **Inputs**: Command invocation; loupe state.
- **Outputs**: Rendered report or a config mutation.
- **Behavior**: `/loupe-report`, `/loupe-check-health`, `/loupe-check-tools`, `/loupe-show-tdi`, `/loupe-toggle`, `/loupe-allow-edit <path>`.

## Structural Decomposition

### Repository Structure

```
claude-loupe/
├── hooks/
│   ├── hooks.json              # Maps to: hook registration
│   ├── session_start.py        # Maps to: Session bootstrap
│   ├── scan_secrets.py         # Maps to: Pre-write secrets scan
│   ├── record_read.py          # Maps to: Read range recording
│   ├── guard_edit.py           # Maps to: Out-of-range edit guard
│   ├── analyze.py              # Maps to: Code Analysis capability
│   ├── agent_end.py            # Maps to: Fix & Format + slow-lint + Telemetry at Stop
│   ├── loupe/                  # engine package (imported by hooks)
│   │   ├── __init__.py
│   │   ├── project.py          # Maps to: project hash, root detection
│   │   ├── state.py            # Maps to: state.json I/O + lifecycle
│   │   ├── config.py           # Maps to: Config resolution
│   │   ├── languages.py        # Maps to: language detection/profiles
│   │   ├── tools.py            # Maps to: Tool resolution and nudging
│   │   ├── findings.py         # Maps to: finding model + classification
│   │   ├── secrets.py          # Maps to: secrets patterns
│   │   ├── linters.py          # Maps to: Linter dispatch
│   │   ├── astgrep.py          # Maps to: ast-grep rule dispatch
│   │   ├── readcoverage.py     # Maps to: read-range merge/overlap math
│   │   ├── formatters.py       # Maps to: autofix + formatter dispatch
│   │   ├── tdi.py              # Maps to: Technical Debt Index
│   │   └── cascade.py          # Maps to: Review-graph cascade
│   └── tests/                  # pytest suite + fixtures
├── rules/ast-grep/
│   ├── js/  ts/  python/  rust/ # rule files by language
│   └── NOTICE                  # MIT attribution for ported rules
├── commands/                   # loupe-*.md slash commands
├── dev/bin/release
├── CHANGELOG.md
├── README.md
└── LICENSE
```

### Module: engine-foundation
- **Maps to capability**: Session & Configuration
- **Responsibility**: Project identity, state and config I/O, language detection, tool resolution, the finding data model - the substrate every other module imports.
- **Exports**:
  - `project_hash(cwd)` - stable per-project identifier
  - `load_state()` / `save_state()` - runtime + persistent state I/O
  - `load_config()` - merged effective config
  - `detect_language(path)` - language profile for a file
  - `resolve_tool(name)` - PATH/mise lookup; records nudge when absent
  - `Finding` - finding record with category and severity

### Module: analysis-engine
- **Maps to capability**: Secrets Guarding, Code Analysis
- **Responsibility**: Run secrets scan, linters, and the ast-grep rule pack; classify results into blocking vs advisory.
- **Exports**:
  - `scan_for_secrets(content)` - matched credential categories
  - `run_linter(path, language)` - advisory linter findings
  - `run_astgrep(path, language)` - categorized rule findings
  - `classify(findings)` - blocking vs advisory split

### Module: coverage-engine
- **Maps to capability**: Read Coverage Guarding
- **Responsibility**: Track read line-ranges and decide whether an edit target is covered.
- **Exports**:
  - `record_read(path, offset, limit)` - merge a read range into state
  - `is_covered(path, target_lines)` - coverage check for an edit

### Module: fix-engine
- **Maps to capability**: Fix & Format
- **Responsibility**: Apply safe autofixes and config-gated formatters to queued files.
- **Exports**:
  - `apply_autofix(path, language)` - safe autofixes
  - `apply_formatters(path)` - config-gated formatter run
  - `format_summary(results)` - per-turn fix/format summary

### Module: telemetry-engine
- **Maps to capability**: Telemetry & Reporting
- **Responsibility**: Compute the TDI and render the Cartographer-backed cascade.
- **Exports**:
  - `update_tdi(findings)` - append to TDI history
  - `render_cascade(edited_files)` - cascade summary or unavailable

### Module: hook-entrypoints
- **Maps to capability**: all (orchestration layer)
- **Responsibility**: Thin `PreToolUse`/`PostToolUse`/`Stop`/`SessionStart` entry points that parse hook JSON, call engine modules, and emit exit codes; fail open on internal error.
- **Exports**: executable hook scripts registered via `hooks/hooks.json`.

### Module: rule-pack
- **Maps to capability**: Code Analysis
- **Responsibility**: ast-grep rule files - JS/TS/Python ported from pi-lens (MIT), Rust authored fresh.
- **Exports**: rule YAML/SGConfig files plus `NOTICE` attribution.

### Module: commands
- **Maps to capability**: Telemetry & Reporting
- **Responsibility**: Slash command definitions that invoke engine reporting.
- **Exports**: `/loupe-report`, `/loupe-check-health`, `/loupe-check-tools`, `/loupe-show-tdi`, `/loupe-toggle`, `/loupe-allow-edit`.

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **engine-foundation**: Project identity, state/config I/O, language detection, tool resolution, finding model.

### Core Layer (Phase 1)
- **analysis-engine**: Depends on [engine-foundation]
- **coverage-engine**: Depends on [engine-foundation]
- **fix-engine**: Depends on [engine-foundation]
- **telemetry-engine**: Depends on [engine-foundation, analysis-engine]
- **rule-pack**: Depends on [engine-foundation] (consumed by analysis-engine; authored alongside it)

### Integration Layer (Phase 2)
- **hook-entrypoints**: Depends on [analysis-engine, coverage-engine, fix-engine, telemetry-engine]
- **commands**: Depends on [telemetry-engine, engine-foundation]

### Downstream (out of scope)
- Cartographer Phase 5 Conformance (`00114 (ex-00024)`, deferred): if reactivated after loupe ships, it lands as an atlas-aware rule source inside `analyze.py`'s pipeline, not a separate PostToolUse hook (see delivery note in that PRD).

## Implementation Phases

### Phase 0: Foundation
**Goal**: A reusable engine substrate every analysis module can import.

**Tasks**:
- [ ] Scaffold `claude-loupe` repo, plugin layout, `dev/bin/release`, CHANGELOG, LICENSE (no deps) - Acceptance: repo installs as a plugin with empty hooks.
- [ ] Implement `project.py` + `state.py` (runtime vs persistent split, reset/persist) (no deps) - Acceptance: state round-trips; runtime block resets, TDI/nudge persist; malformed state rebuilds.
- [ ] Implement `config.py` (global + per-project merge, defaults) (no deps) - Acceptance: per-project overrides global; missing/malformed config yields defaults.
- [ ] Implement `languages.py` + `tools.py` (PATH/mise resolution, nudge-once tracking) + `findings.py` (no deps) - Acceptance: tool resolves via mise shim; absent tool records exactly one nudge per project; language detected by extension.

**Exit Criteria**: Engine package imports cleanly; foundation unit tests pass at 80%+.

### Phase 1: Core
**Goal**: Working analysis, coverage, fix, and telemetry engines.

**Tasks**:
- [ ] Implement `secrets.py` + `astgrep.py` + `linters.py` + `classify` (depends on: Phase 0) - Acceptance: secrets matched; ast-grep categorized; classify splits blocking vs advisory.
- [ ] Port JS/TS/Python ast-grep rules from pi-lens with `NOTICE`; author Rust stub/security rules; each rule gets positive + negative fixtures (depends on: Phase 0) - Acceptance: every rule fires on its positive fixture and stays silent on its negative.
- [ ] Implement `readcoverage.py` (range merge + coverage check) (depends on: Phase 0) - Acceptance: two partial reads satisfy a full-file edit; uncovered edit is detected.
- [ ] Implement `formatters.py` (autofix + config-gated formatter dispatch, nearest-wins) (depends on: Phase 0) - Acceptance: formatter runs only when config present; nearest config wins.
- [ ] Implement `tdi.py` + `cascade.py` (depends on: Phase 0, analysis-engine) - Acceptance: TDI appends to history; cascade renders with a stub atlas and degrades gracefully without one.

**Exit Criteria**: All core engine modules pass unit tests at 80%+.

### Phase 2: Integration
**Goal**: Hooks, commands, and marketplace registration - a usable plugin.

**Tasks**:
- [ ] Implement the six hook entry points + `hooks.json`, fail-open wrapping (depends on: Phase 1) - Acceptance: each hook processes synthetic hook JSON and emits correct exit codes; internal errors exit 0.
- [ ] Implement the six `/loupe-*` commands as plugin commands (depends on: Phase 1) - Acceptance: each command renders its report or mutates config.
- [ ] Add the `buvis/claude-plugins` marketplace entry; behavioral test matrix; dogfood session on a real Buvis repo (depends on: all above) - Acceptance: success-metrics matrix green; dogfood confirms useful and non-noisy.

**Exit Criteria**: Plugin installs from the marketplace; behavioral matrix and full suite green at 80%+; dogfood signed off.

## Test Strategy

### Critical Scenarios
- **Happy path**: Edit a clean source file → Expected: advisory-free pass, file queued, `Stop` formats it once, summary printed.
- **Happy path**: Two partial reads (lines 1-100, 101-200) then a full-file edit → Expected: edit allowed, no out-of-range block.
- **Edge case**: `immediate_fix: true` → Expected: `analyze.py` formats inline; next edit re-reads after CC's file-modified guard.
- **Edge case**: Cartographer absent → Expected: cascade section omitted silently, no error.
- **Edge case**: Required linter not installed → Expected: check skipped; exactly one nudge per project at `Stop`.
- **Error case**: Planted secret in new content → Expected: `scan_secrets.py` exits 2, write aborted.
- **Error case**: Stub body / security-rule violation in an edit → Expected: `analyze.py` exits 2 with detail.
- **Error case**: ast-grep subprocess crashes → Expected: reported as advisory warning, hook exits 0.
- **Error case**: Out-of-range edit, `read_guard: block` → Expected: `guard_edit.py` exits 2; `/loupe-allow-edit` overrides for one edit.

## Risks

- **Hook latency**: Linters + ast-grep on every edit add per-edit latency. Mitigation: compile/type-check-class linters (clippy, svelte-check) deferred to `Stop`; per-tool timeouts, parallel runner dispatch, language-gated skipping so only relevant checks run; track p50 against the ~1s budget during dogfood. loupe also joins an existing per-edit hook stack (gateguard, cartographer-echo, design-quality-check) where each hook is a separate Python spawn - entry points must stay import-light and short-circuit before any engine import when loupe is disabled.
- **Stop-defer staleness**: Deferred autofix/format rewrites files after the turn, so the agent's cached read goes stale and trips CC's file-modified guard. Mitigation: keep `analyze.py` strictly read-only so staleness occurs at most once per file per turn; `immediate_fix` is opt-in; document the behavior.
- **Cartographer coupling**: The cascade depends on Cartographer's on-disk atlas format; a format change breaks or misreads it. Mitigation: treat the atlas as optional, version-check it, degrade to "cascade unavailable" rather than erroring.
- **ast-grep rule port fidelity**: Ported pi-lens rules may assume pi-lens runner semantics or produce noisy false positives. Mitigation: positive + negative fixture per rule; triage false positives during the dogfood session before v1 is called done.
- **Scope**: Full pi-lens parity in one v1 is large. Mitigation: strict phase gates; foundation and core land and pass tests before any hook wiring; the PRD's three layers are independently testable.

## Open Questions

- Exact `state.json` schema (field names, TDI history shape) - to be fixed during Phase 0.
- Resolved: TDI v1 is unweighted per-category counts; weighting deferred until trend data shows a need.
- Resolved: `/loupe-*` ship as plugin commands (not skills) - simple report/control invocations fit the command format.
