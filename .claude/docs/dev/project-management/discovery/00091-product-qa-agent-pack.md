# Discovery: agoge - Product QA Agent Pack

## Classification
Depth: comprehensive | Date: 2026-07-31 | Status: complete

## Problem
Autopilot's review pipeline is entirely static and diff-scoped: no lens runs the product, exercises a UI, or verifies user-visible behavior (Carl's `ui` lens reads the diff; the `Tests:` line accepts `none (docs-only)` with no notion of "behavior unverified"). Defects at the feature, workflow, integration, and release level - the kind an end user or the business hits - pass every existing lens. The gap compounds as autopilot drains PRDs unattended: code-correct, product-wrong changes accumulate with no catch point. The pack ("agoge", after the Spartan training regime: hard trials that make the product battle-ready) fills the product-time layer beside edit-time hooks and the review-time ensemble.

## Requirements

### Must have
- Seven specialist agents as flat files in `~/.claude/agents/` (first entries in the registry the reviewer-ensemble D8 decision also mandates): recon (strategy discovery), journey walker (end-to-end user journeys via CLI/UI/API), integration prober (cross-component/external contracts and DB probed live where runnable; for unreachable externals recon may assign a mocking strategy, and mocked probes report as such, never as verified), UX critic (drives the real UI via browser), release warden (upgrade path, changelog-vs-behavior, docs truthfulness, breaking-change fallout), performance prober, runtime security prober (own/authorized projects only).
- Master orchestrator as a skill (action-verb name, e.g. `run-agoge`): dispatches armed specialists, dedups findings (evidence-keyed, review-fanout style), produces one actionable improvement plan.
- Layered execution: behavioral gap analysis always runs; specialists exercise the real product (tests, CLI, browser, db) wherever recon finds a runnable surface; unverifiable areas reported as "unverified", never "passed".
- Per-project strategy discovery by recon; output lands in cartographer's atlas as a QA layer when cartographer is present, else as a self-contained profile file - same content contract either way. Profile is human-editable (pin/veto strategies).
- Durable test authoring available as a strategy recon can assign to any specialist (e.g. UX critic authors a Playwright suite where the project warrants it); authored suites land in the target repo as branch commits, passing per rules/testing.md before commit.
- Findings flow: report in `dev/local/audit-results/`; interactive runs walk findings per the findings-walkthrough protocol, accepted ones become backlog PRDs; unattended runs write packets and stop.
- Runs standalone on demand plus via an autopilot batch-drain hook (once per drained batch, not per cycle).
- Extraction-clean from day one: flat agent files, no `/Users/bob` or `dev/local` residue in agent bodies, cross-cluster deps only on published plugins (`strunk:e2e-testing` etc.), `${CLAUDE_SKILL_DIR}` script paths.
- Ships as a buvis plugin: own repo `~/git/src/github.com/buvis/claude-agoge`, canonical buvis layout (`.claude-plugin/plugin.json` with the four standard keys `{name, version, description, author:{name:"buvis"}}`, `agents/` + `skills/` at plugin root relying on auto-discovery, Python-only `hooks/` + `hooks.json` if any, `dev/bin/release`, README/CHANGELOG/LICENSE), registered in the central marketplace `~/git/src/github.com/buvis/claude-plugins` (`.claude-plugin/marketplace.json` entry pointing at `https://github.com/buvis/claude-agoge.git`), released via `dev/bin/release [patch|minor|major]`.
- Seeded-defect fixture repo(s) (>=2 stacks) with planted product-behavior defects (broken journey, lying changelog, dead integration, runtime perf/security seeds), built before the pack and kept as the permanent eval for catch-rate scoring.

### Nice to have
- Engram context packs feeding specialists once engram ships (no coupling now).
- Atlas QA-layer refresh piggybacking on survey's staleness machinery.

### Out of scope
- CI-pipeline integration (GitHub Actions wiring, v2 candidate) - v1 runs only via Claude Code sessions.
- Code-level review dimensions (correctness, security-in-code, perf-in-code, patterns) - owned by the review-time ensemble (Mallory, planned perf/patterns dimensions).
- Rebuilding ensemble mechanics - review-fanout stays the review-time engine; agoge is a separate product-time layer and, later, a separate plugin from the ensemble's.

## Constraints
- Meta-budget: build is `~/.claude` meta-spend (<=30% monthly ceiling); extraction turns it into product.
- Headless-safe: batch-drain runs headless - CLI/browser lanes need the Watcher + `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` pattern; browser-dependent work degrades gracefully (Playwright if the project has it, else skip loud).
- Subagent dispatch discipline (`work/references/subagent-dispatch.md`): 50KB prompt budget, watchdog, abort wiring; never wrap a CLI in a Task subagent.
- Hooks Python-only; agent frontmatter per validate-agent.sh conventions (prose-form description); skills' fenced bash must pass live-profile lints.
- Runtime security probing targets own/authorized projects only.
- Persona names extend the crypto-cast style (Alice/Bob/Mallory...); pack name fixed: agoge.

## Codebase Context
- **No existing behavioral QA**: `review-work-completion` roster (SKILL.md:34-44) is all static lenses; `work/SKILL.md:742-743` runs project e2e tests opportunistically - the only pipeline touchpoint.
- **Integration surface**: batch-drain hook attaches at autopilot's `done` phase / wrapper drain branch (`development.plugin.bash:789-810`); no new gate, no schema change. Per-cycle lens and fourth-gate options were mapped and rejected (see Approach).
- **Agent conventions**: `~/.claude/agents/` does not exist yet; frontmatter name/description required, model/tools/color optional; extract-plugin Phase 5 is a literal `cp` of flat agent files; check-readiness greps for personal paths and cross-cluster refs.
- **Reviewer-ensemble alignment** (`discovery/00092-reviewer-ensemble.md`, same-day): D8 mandates named agents in `~/.claude/agents/` for all reviewers - agoge joins that registry direction; D2's hard boundary (CLI lanes = background Bash, never Task-wrapped) applies to any CLI/browser lane here; layer separation edit-time / review-time / product-time keeps rosters disjoint (Carl reads diffs; UX critic drives the real UI). Ensemble PRD B should land its agent-file conventions first or share them.
- **Reusable assets**: Tess/Devon prompts (`work/references/test-author-prompt.md`, `adversarial-test-prompt.md`) as authoring-strategy seeds; `strunk:e2e-testing` (Playwright/POM doctrine), `strunk:{python,rust}-testing`; claude-in-chrome MCP (interactive browser); review-fanout's evidence-keyed dedup pattern; findings-walkthrough protocol (`rules/communication.md`).
- **Naming space**: nothing qa/acceptance/browser-named exists; agoge collides with nothing.

## Approach
- **Chosen**: seven flat named agents + master skill; layered assess-and-execute; recon-gated strategies with atlas-or-profile persistence; standalone runs + batch-drain hook; report -> walkthrough -> backlog PRDs; seeded-defect fixture built first as the permanent eval. PRD sequence per Q11: (1) fixture + catch-rate criteria, (2) core pack (agents + master + recon contract, incl. an early smoke test of named-agent dispatch), (3) execution harnesses/playbooks (browser, db, perf, security + graceful degradation), (4) autopilot batch-drain hook + findings-to-PRD flow, (5) plugin extraction: `extract-plugin` into `buvis/claude-agoge` following the shipped-plugin structure (aegis/strunk as templates), marketplace entry in `buvis/claude-plugins`, first release via `dev/bin/release`.
- **Why**: whole-product scope can't live inside per-diff review cycles; named agents make extraction a copy and match the ensemble's D8 direction; fixture-first gives the pack ground truth from its first run (product-level fail-first).
- **Rejected alternatives**:
  - Per-cycle review lens: diff-scoped - blind to workflow/release defects; adds cost to every cycle of an already-expensive loop (~$13/task).
  - Fourth autopilot gate: 6-file registration surface (schema, resume logic, wrapper launch table) and still per-PRD scope.
  - Prompt-file house style: proven but requires conversion at extraction; not independently invocable.
  - Workflow-first orchestration: no plugin packaging story for `~/.claude/workflows/`.
  - Fresh discovery every run: repeated recon cost, no durable place for user strategy vetoes.
  - Auto-emitting PRDs to backlog: ungated machine PRDs pollute the backlog and burn autopilot budget.

## Success Criteria
- Seeded-defect catch rate: fixture repo(s) with planted product-behavior defects (broken journey, lying changelog, dead integration, runtime perf/security seeds); pack catches the target share (number fixed in the fixture PRD) across >=2 stacks.
- End-to-end behavior: recon discovers strategies, armed specialists run, master emits a walkthrough-shaped report on repos of different stacks, degrading loud-and-graceful where surfaces are missing (no browser, no db).
- Findings flow proven: interactive walkthrough turns accepted findings into backlog PRDs; an unattended batch-drain run writes packets and stops.
- Extraction dry-run: extract-plugin check-readiness passes on the pack with zero rewrites.

## Risks
- **Execution flakiness** (real servers, dbs, browsers): recon gates strategies on what's actually runnable; specialists fail loud per lane; master reports unverified-vs-passed distinctly.
- **Cost of a 7-specialist fan-out**: only armed specialists dispatch (strategy gating); batch-drain runs once per batch; meta-budget watched via portfolio brief.
- **Finding duplication across specialists** (a dead integration also breaks journeys): evidence-keyed dedup in the master, severity-strictest merge.
- **Named-agent dispatch unproven in this setup**: core-pack PRD starts with a one-agent smoke test before building all seven.
- **Headless browser gap**: UX critic requires Playwright per project in unattended runs; claude-in-chrome only interactively; skip-loud otherwise.
- **Convention drift vs reviewer ensemble**: adopt ensemble PRD B's agent-file conventions (or land a shared conventions note first) so the registry stays uniform.
- **Fixture-first rework**: scoring may need adjustment once the master's report shape settles - accepted in Q11.

## Open Questions
- Priority/sequencing vs reviewer-ensemble PRDs A-C and engram: does agoge's fixture PRD enter the backlog now or after ensemble PRD B fixes agent conventions? (Batch is currently halted; review-prd-backlog orders it.)
- Catch-rate target number and fixture stack mix (CLI+python, web+svelte, ...) - fix in the fixture PRD.
- Persona names for the seven agents (crypto-cast extension) - design time.
- Batch-drain hook mechanics: wrapper branch vs done-phase step - design time.
- Report format: fresh audit-results shape vs borrowing the review-file contract's Verdict/Tests tail - design time.
- Whether the master skill itself or a thin workflow script does the fan-out (agents are dispatchable either way) - design time.

## Discovery Log

### Q0a (inferred, not asked): What triggers this need?
**Answer**: Stated in input - code reviews (even multi-lens autopilot reviews) catch code defects, not product-behavior defects; QA from end-user/business perspective is missing.

### Q0b (inferred, not asked): What is the master agent's deliverable?
**Answer**: Stated in input - collect all specialist results, produce an actionable improvement plan.

### Q1: What should the specialized QA agents actually DO to assess product behavior?
**Answer**: Layered - behavioral gap analysis always runs; agents execute the real product (tests, CLI, browser) wherever the project offers a runnable surface. (Recommended option chosen.)

### Q2: Where should the QA pack run relative to autopilot?
**Answer**: Standalone run + batch-drain hook - whole-product scope, runs once when autopilot drains plus on demand; per-cycle review cost stays flat. Accepted drawback: findings land as new backlog PRDs, not in-cycle rework. (Recommended option chosen.)

### Q3: How should the specialists be defined and dispatched?
**Answer**: Named agents (flat `~/.claude/agents/*.md`) + master skill orchestrating them. Extraction becomes a literal copy; each specialist independently invocable. Accepted drawback: first personal agents, dispatch quirks unproven. (Recommended option chosen; same-day reviewer-ensemble D8 independently made the same call.)

### Q4: What happens to the master agent's improvement plan?
**Answer**: Report in dev/local/audit-results/ + findings walkthrough when interactive; accepted findings become backlog PRDs. Unattended (batch-drain) runs write packets and stop. (Recommended option chosen.)

### Q5: How should per-project strategy discovery work?
**Answer**: QA layer inside cartographer's atlas - reuse survey's staleness/refresh machinery. (User overrode the recommended standalone profile.) Extraction tension resolved in Q9.

### Q6: Which specialist domains should the v1 pack ship?
**Answer**: All four offered - journey walker, integration prober, UX critic, release warden - plus structural recon and master. (Roster later grew by two in Q10; master settled as a skill per Q3, so final shape = 7 agents + 1 skill.)

### Q7: What is explicitly OUT of scope for v1?
**Answer**: Only CI-pipeline integration. Deliberately kept IN: durable test authoring, performance/load testing, runtime security probing. Owner tension resolved in Q10.

### Q8: How will you know the pack works?
**Answer**: Seeded-defect catch rate against a planted-defect fixture; target share fixed in the fixture PRD. Accepted cost: fixture is real up-front work; seeds may skew easier than wild defects. (Recommended option chosen.)

### Q9 (contradiction 1/2): Atlas home (Q5) vs standalone extraction (Q3)?
**Answer**: Atlas when present, own profile otherwise - same recon prose, one output contract, two landing spots. Accepted cost: two storage paths to test. (Recommended option chosen.)

### Q10 (contradiction 2/2): Perf/security/authoring in scope (Q7) but no roster owner (Q6)?
**Answer**: Grow the roster now - dedicated performance prober and runtime security prober; durable test authoring folds in as a strategy any specialist can be assigned. (User overrode the strategies-not-specialists recommendation.)

### Q11: One PRD or split, and in what order?
**Answer**: Split, fixture first - seeded fixture + catch-rate criteria precede the pack (fail-first at product level), then core pack, harnesses, autopilot hook, extraction. (Recommended option chosen.)

### Q12: Pack name?
**Answer**: agoge (user explored gauntlet's drawbacks - crowded namespace: Gauntlt/Atari/GauntletAI - then picked agoge: the Spartan training regime, hard trials that prepare for battle; near-empty namespace; known cost: obscure, needs the etymology explained). Repo: claude-agoge. Ensemble plugin naming space (quorum/tribunal/conclave/synod) untouched.
