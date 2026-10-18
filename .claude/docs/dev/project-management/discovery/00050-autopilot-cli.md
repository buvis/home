# Discovery: Autopilot CLI (deterministic state machine as Python tooling)

## Classification
Depth: comprehensive | Date: 2026-07-08 | Status: elicitation complete

## Problem

The autopilot workflow has evolved into a formalized, deterministic state machine (PRD selection, frontmatter parse, phase transitions, gate checks, state.json writes, mv-verify, stall/defer records, report render) expressed as ~850 lines of SKILL.md prose plus reference files that every session re-reads and must follow without drift. Deterministic logic executed by an LLM is the wrong tool (rules/ai-app-design.md): it burns context on every session, drifts under paraphrase, and produced the 10 root-caused loop-halt classes. The queued overhaul (PRDs 00014-00019) fixes the architecture in prose+bash; this effort consolidates the settled semantics into a tested Python CLI afterwards, so the skill and references carry judgment only.

## Requirements

### Must have
- A Python CLI (working name `autopilot`) that owns the post-overhaul loop: spawns the routed phase runner (default `claude -p`; runner selection is an extension point), PRD selection, frontmatter parse, state transitions, resume mapping, stall/defer records, wall-clock cap, usage-limit wait, pause file, notifications, per-phase model routing, review-file gate, audit/batch-report/metrics rendering.
- CLI is the sole writer of `state.json`: sessions mutate state only through subcommands (`autopilot phase-done --next review`, `autopilot defer ...`); every write schema-validated at that one boundary; state.json stays human-readable.
- Delivered as 3 sequenced PRDs: (1) state-machine core (testable standalone), (2) orchestrator loop cutover (replaces `autoclaude` bash loop), (3) validators + rendering absorption.
- run-autopilot SKILL.md and references reduced to judgment instructions plus CLI invocations; zero orchestration mechanics in prose.
- Test parity: every retired prose/bash behavior has a CLI test; existing contract tests ported or consciously retired via migration map.
- Interactive parity: manual `/run-autopilot` (non-loop) keeps working - sessions call the same subcommands; only loop ownership changes.

### Nice to have
- `autopilot status` plain-text status/dashboard surface (current dashboard-format.md render moves to code).
- Metrics enrichment beyond 00013/00018 fields once rendering lives in code.

### Out of scope
- Reviewer dispatch: the review-phase session keeps launching Bob/Carl/Quinn via background Bash itself; the CLI only spawns phase sessions and gates their output files.
- Batch-end interactive review: `review-batch` stays a human-driven session; the CLI only notifies when a batch drains.
- work/plan-tasks internals: task dispatch, tiering, qwen routing, TDD flow stay skill-owned; build/review sessions are black boxes that report results via the CLI.
- Plugin extraction: stays a later /extract-plugin PRD (autopilot is on the plugins-to-ship list).

## Constraints
- Consolidation AFTER the overhaul drain: PRDs 00014-00019 land first as written; the CLI encodes the semantics as shipped on disk, not as specced in those PRDs.
- stdlib-only Python (argparse), Python 3.10+; matches every existing autopilot script and the Python-only hooks rule.
- In-tree home first: `~/.claude/skills/run-autopilot/cli/` (or scripts/) package, thin `autopilot` alias in the bash plugin; same pytest umbrella; buvis bare-repo tracked; no CHANGELOG (home-repo exemption).
- Package stays self-contained - no imports from hooks/ or other skills (the notify.py import-path landmine class).
- Cutover only between batches, never mid-batch; state schema versioned so a resumed old batch is detected, not corrupted.

## Codebase Context
- **Wrapper**: `~/.config/bash/plugins/development.plugin.bash` - `_autopilot_loop_watchdog()` (line 36), `autoclaude()` (line 80); old `_autoclaude_pick_model` deleted (line 147 comment). Post-00014 this becomes the headless launch + 5-branch state read the CLI replaces.
- **Deterministic machinery in scripts** (`~/.claude/skills/run-autopilot/scripts/`): autopilot_stop_hook.py (~890 lines) and autopilot_yield_clear_hook.py (deleted by 00014); resume_target.py, autopilot_context_cap_hook.py, review_coverage_hook.py, detect_usage_limit.py, codex_review_run.py, `_walk_up.py` (survivors - absorption candidates); 17 test files incl. test_autoclaude_watchdog.sh, test_loop_metrics.sh.
- **State artifacts**: `dev/local/autopilot/state.json`, deferred/{batch}.json, reports/, loop-metrics.jsonl (00013, in flight).
- **Post-overhaul contracts the CLI encodes**: headless `claude -p` sessions + end-turn hand-offs (00014), `build|review|done|paused` enum (00015), `check_review_file.py` <120-line gate (00016), stall-not-pause policy + stalled/ moves (00017), per-phase model routing + metrics fields (00018), operator interaction contract - watch/pause-file/take-over/forensics (00014).
- **Similar implementations**: warden plugin (Python CLI + config-driven decisions), audit-echo `scripts/report.py` (stdlib argparse report pattern), 00016's check_review_file.py (validator-as-script pattern).
- **Conventions**: stdlib-only, pytest beside sources, executable entry scripts, absolute paths in Bash calls, `mise` for runtimes.

## Approach
- **Chosen**: Orchestrator CLI as post-drain consolidation. Python CLI takes loop ownership from the bash wrapper (spawn `claude -p`, decide from state), becomes sole state.json writer with schema validation, and absorbs gates + rendering. Built in-tree as a stdlib package, shipped via 3 sequenced PRDs (core -> loop cutover -> validators/render).
- **Why**: One tested codebase for everything deterministic; sessions keep only judgment; the halt-class surface (prose drift, malformed writes, inference-based orchestration) is removed structurally. Draining 00014-00019 first proves the semantics on real batches before freezing them into code.
- **Rejected alternatives**:
  - Session-side helper CLI only: leaves two orchestration surfaces (bash loop + CLI) and the LLM still drives the loop - misfollow risk survives.
  - Re-scope 00014-00018 into the CLI now: avoids double work but re-scoping in-flight, already-written PRDs stalls the live drain mid-batch and re-opens settled reviews.
  - Standalone plugin repo now: extraction landmines mid-consolidation and release-cycle friction while the CLI churns.
  - Shared state writes with CLI validation: catches malformed state late (next loop decision) instead of preventing it at write time.

## Success Criteria
- Prose diet: zero orchestration mechanics in run-autopilot SKILL.md/references; concrete before-after line/token numbers reported. Mechanic-vs-judgment test: a behavior is a mechanic (->CLI) if the same input must always produce the same output (rules/ai-app-design.md); it stays judgment (prose) if a rubric can't fully capture the call.
- Unattended reliability: consecutive real batches (target 3) drain with zero loop-halt/thrash notifications and zero manual un-wedging.
- Test parity: migration map accounts for every retired prose/bash behavior; CLI suite + surviving contract tests green.
- Cost/latency: loop-metrics show per-PRD session count and token/cost at or below the pre-CLI baseline (session-count/token/cost emitted by 00018 pre-cutover; baseline = loop-metrics rows dated before the PRD-2 cutover).

## Risks
- **Semantics drift between spec and shipped prose**: the CLI must encode what 00014-00019 actually landed, not what their PRDs say. Mitigation: CLI PRDs derive contracts from the on-disk files + migration map at execution time (same premise discipline as 00048).
- **Mid-batch cutover corruption**: mitigated by between-batches cutover constraint and a state schema version stamp.
- **Subprocess management regressions** (tee, TERM->KILL cap, usage-limit wait): port the test_autoclaude_watchdog and detect_usage_limit contracts into the CLI suite before deleting the bash paths.
- **Accepted double work**: the 00014 bash decision table and signal-prose rewrite get re-implemented in Python; deliberate (Q2) - momentum and proven semantics outweigh the rework.
- **Interactive-mode regression**: manual single-phase runs must behave identically; covered by the interactive-parity requirement and existing resume tests.

## Open Questions
- Exact subcommand surface (select / phase-done / defer / stall / gate / render / metrics / status / pause) - PRD 1 fixes the contract.
- Which surviving scripts (resume_target.py, autopilot_context_cap_hook.py, review_coverage_hook.py, detect_usage_limit.py) fold into the package in PRD 1 vs PRD 3.
- Status surface shape: plain `autopilot status` vs watch mode (dashboard render was not excluded from scope).
- Config surface: keep `_AUTOPILOT_*` env vars or introduce a config file (env vars are the current contract; ponytail says keep them).
- Scheduling: the three CLI PRDs take numbers after the current backlog (00051+); confirm they run after 00041-00049 or jump the queue once 00014-00019 land.

## Discovery Log

### Q1: What runtime role should the Python CLI play (orchestrator vs session-side helper vs phased)?
**Answer**: Orchestrator CLI - one tested codebase owns the whole loop: spawns `claude -p` per phase, owns PRD selection, frontmatter parse, state writes, gates, model routing, metrics, notifications. Sessions become pure judgment phases.

### Q2: What happens to the queued overhaul PRDs 00014-00019?
**Answer**: Drain them first as written; the CLI consolidates AFTER. Semantics get proven in prose across real batches before freezing into code. Accepted cost: the bash decision table, signal-prose rewrite, and gate rewire get built and then re-implemented in Python. Consequence: the CLI targets the POST-overhaul architecture and replaces the bash wrapper loop, not the Stop-hook machinery (already deleted by 00014).

### Q3: Decomposition - one PRD or several?
**Answer**: 3 sequenced PRDs: (1) state-machine core (selection, frontmatter parse, transitions, resume mapping, stall/defer records - testable standalone), (2) orchestrator loop cutover (spawn `claude -p` per phase, wall-clock cap, usage-limit wait, pause file, notifications, model routing - replaces `autoclaude`), (3) validators + rendering absorption (review-file gate, audit.md render, batch report, metrics). Accepted: transitional coexistence of bash loop and CLI core across two batches.

### Q4: Who mutates state.json once the CLI exists?
**Answer**: CLI is sole writer. Sessions call subcommands (`autopilot phase-done --next review`, `autopilot defer ...`); every write is schema-validated at one boundary; state.json stays a human-readable artifact. Accepted: skills rewritten to call the CLI instead of writing state.json; no partial session-side writes.

### Q5: Where does the CLI live?
**Answer**: In-tree package first - `~/.claude/skills/run-autopilot/cli/` (or scripts/) as a stdlib Python package with a thin `autopilot` alias in the bash plugin; same pytest umbrella, buvis-tracked. Plugin extraction stays a later /extract-plugin PRD.

### Q6: What proves the consolidation worked (binding success criteria)?
**Answer**: All four: prose diet with before-after numbers; unattended reliability across consecutive real batches; test parity via migration map; cost/latency at or below pre-CLI baseline per loop-metrics.

### Q7: What is explicitly out of scope?
**Answer**: Reviewer dispatch (stays in the review session), batch-end interactive review (stays human-driven; CLI only notifies), work/plan-tasks internals (skill-owned; sessions are black boxes reporting via CLI). NOT excluded - therefore in scope: a status/dashboard surface (shape is an open question). TUI specifics left open.

### Inferred (not asked - house conventions)
- **Dependencies**: stdlib-only Python, argparse; matches every existing autopilot script and the Python-only hooks rule. Revisit only if a PRD hits a concrete stdlib wall.
- **Python floor**: 3.10+ (strunk compat target).
- **Repo mechanics**: buvis bare-repo tracking, no CHANGELOG entries (home-repo exemption).

### Contradiction check
Q2 (prove semantics in prose first) vs Q1 (orchestrator subsumes wrapper work): resolved by sequencing - the CLI consolidates after the drain rather than replacing the queued PRDs. No other conflicts found.
