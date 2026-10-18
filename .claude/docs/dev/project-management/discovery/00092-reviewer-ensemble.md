# Discovery: Reviewer Ensemble Framework

## Classification
Depth: comprehensive | Date: 2026-07-31 | Status: elicitation complete

## Problem
The AI-code-review training's target architecture (specialist agents in
parallel, agreement raises confidence, aggressive dedup, severity-tiered
judgment, context-engine-fed) is where the review stack should land - then
ship as a plugin. Most of the machinery already exists but is scattered:
ensemble mechanics live in one workflow file, personas live as prose across
three skills and one workflow's inline strings, no specialist sees
repo-specific context, and nothing is packaged. Meanwhile the measured pain
is convergence: under the legacy engine 13/14 PRDs hit rework cap 3 without
converging (~$13/task). Left unaddressed, autopilot keeps thrashing and the
review IP stays unshippable.

## Requirements

### Must have
1. **Engine default flip (A)**: after 3 clean shadow cycles, default
   `consensus_engine` flips `legacy` -> `workflow`; shadow bookkeeping
   retires; 00057 moves to done.
2. **Named agent registry (B)**: ALL reviewers become named agents in
   `~/.claude/agents/` - flat files, terse one-line descriptions (boot-tax
   discipline), no personal-path residue (extract-plugin compatible).
   Native personas dispatch via Agent tool / Workflow `agentType`; CLI
   personas keep direct background Bash dispatch but source their prompt
   from the agent file (frontmatter stripped).
3. **Roster and names (B)**: existing Alice (consensus lead), Blake
   (blind), Bob (codex doubt; Claude fallback is Bob too), Carl (gemini
   frontend), Quinn (qwen advisory), Eve (fable doubt). New names,
   crypto-cast style: Rita (requirements), Cora (correctness), Grace
   (quality), Toby (tests - "Tess" is taken by /work's test author),
   Mallory (security), Trent (rubric judge), Victor (adversarial
   verifier), Pat (/work per-task patch reviewer). Watcher stays unnamed
   (scaffolding, not a reviewer).
4. **Fail closed, no fallback (B)**: a missing or malformed agent file at
   dispatch = review incomplete -> CHANGES_REQUESTED (native) or runner
   error (CLI). No inline-prompt shadow copies anywhere.
5. **Per-agent tuning (B)**: reviewers get read-only tool sets (no
   Edit/Write); Victor gets Read+Bash for reproduction; Eve pins
   `model: fable`.
6. **Rubric namespace disambiguation (B rider)**: the three colliding
   `R{n}` sets (consensus R1-R13, blind R1-R19, doubt R1-R5) get distinct
   prefixes (e.g. doubt D1-D5, blind B1-B19).
7. **Domain specialists (C)**: patterns-compliance dimension (convention
   drift; consumes capsule/atlas text, arms only when a context source
   exists) and performance dimension (N+1, IO-in-loop, accidental O(n^2);
   armed by diff heuristic like security).
8. **Agreement confidence (C)**: findings reported by >=2 dimensions get
   priority for verify-cap slots; agreement never bypasses Victor.
9. **Engram pack wiring (E)**: review step generates `engram pack --diff`;
   workflow lanes receive it via `context_path`, CLI lanes via /tmp
   staging; Blake stays pack-free by construction.
10. **Plugin extraction (F)**: after the proof bar (see Success Criteria),
    extract agents + workflow + a lean review skill into a new buvis
    marketplace plugin; rubric/standards stay a documented input; the
    buvis review-file contract becomes one output mode with plain
    markdown as the generic default; engram optional (degrades to
    no-context). Autopilot keeps its orchestration wrapper.

### Nice to have
- Cheaper model tier for dimension agents once A's economics are measured.
- Findings corpus (engram must-have 11) later feeds 00079
  tune-routing-from-outcomes.
- Retire or re-cite the orphaned `codex_review_run.py` (its exit contract
  is still cited normatively).

### Out of scope
- Rebuilding ensemble mechanics - `review-fanout.workflow.js` IS the
  ensemble (dedup, adversarial verify, fail-closed verdict all exist).
- CLI reviewers as Task agents (hang class, PRD 00034 hard boundary).
- Edit-time quality layer - loupe (00030) and cartographer conformance
  (00024) stay held on their own criteria; C covers the review-time slice.
- New dimensions beyond C's two: frontend/a11y (Carl owns it), deps
  (renovate flow), docs/changelog (hooks).
- Product-time QA - running the product, UI exercising, behavioral gaps
  belong to the QA agent pack (00091), a separate pack and plugin.

## Constraints
- ~/.claude work is meta-spend (<=30% ceiling): B, C, E are meta; engram
  (00090) and F are product.
- CLI-in-agent hang class: codex/gemini/qwen/sonnet dispatch stays direct
  background Bash forever; headless invariants hold (Watcher subagent,
  `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`).
- Review-file contract (`check_review_file.py`) unchanged until F.
- Agent files: flat `~/.claude/agents/*.md`, frontmatter name/description
  required, terse descriptions (registry adds ~1-2K tokens to every
  session's boot prefix - accepted, capped by discipline).
- The registry is shared ground with the QA pack (00091): conventions B
  sets (naming style, frontmatter shape, dispatch patterns) bind both.

## Codebase Context
- **The ensemble**: `workflows/review-fanout.workflow.js` (617 lines,
  75/75 tests green) - 5 dimensions + rubric agent, evidence-keyed dedup,
  Victor-style adversarial verify (refute-by-default, cap 12), fail-closed
  verdict, renderer to the review-file contract. Engine flag tri-state
  wired: `review-work-completion/SKILL.md:72-81`,
  `run-autopilot/references/phase-build.md:85-102`.
- **Persona prompts today** (to be absorbed by B):
  `review-work-completion/references/agent-prompts.md` (shared template +
  Bob/Carl/Quinn appendices), `references/blind-lens-prompt.md` (Blake),
  `run-autopilot/prompts/doubt-review.md` (Bob/Eve), inline `DIMENSIONS`
  strings in the workflow JS, `work/SKILL.md:673-699` (Pat).
- **CLI runners**: `use-codex/scripts/codex-run.sh`,
  `use-gemini/scripts/gemini-run.sh`, `use-qwen/scripts/qwen-run.sh`,
  `use-sonnet/scripts/sonnet-run.sh`.
- **Aggregation**: legacy `scripts/consolidate-findings.sh` dedups on
  exact lowercased strings (under-counts consensus); the workflow's
  evidence-keyed dedup is strictly better and unused on the legacy path.
- **Context sources for C**: cartographer atlas reaches only the main
  session via the recon-brief UserPromptSubmit hook - no reviewer ever
  sees it; capsule via git-ferry catchup; engram packs later (00090
  must-have 12).
- **Conventions**: `~/.claude/agents/` does not exist yet - B creates the
  first personal agents; extract-plugin Phase 5 does a literal
  `cp ~/.claude/agents/<name>.md` (flat files only). Named-persona prompt
  precedents: Tess + Devon in `work/references/` (test authors, distinct
  from reviewers).

## Approach
- **Chosen**: cement-and-extend in ~/.claude, prove in autopilot, extract
  at F. Tracks: B (registry, banks shadow cycles) -> A (flip after
  proof) -> C (specialists); D (engram, 00090) parallel; E (pack wiring)
  after D+A; F (plugin) after the proof bar.
- **Why**: the ensemble mechanics already exist and test green; the gaps
  are persona reuse, repo context, proof, and packaging - none require a
  rebuild. Building in place keeps iteration friction at zero while
  autopilot dogfoods every change.
- **Rejected alternatives**:
  - Plugin-first repo now: packaging/release friction during the
    churniest phase, before the framework is proven.
  - Rebuild ensemble per the training's literal recipe (Chroma, embedding
    context engine inside the reviewer): engram owns context; sqlite-vec
    decision already made in 00090; review-fanout already implements the
    ensemble strategy.
  - More specialists up front: each dimension multiplies agents/cycle and
    noise in a stack whose pain is convergence; two gated adds only.
  - Agreement bypasses verification: two readers of the same diff can
    share a hallucination; agreement only prioritizes verify-cap slots.

## Success Criteria
- **A**: 3 consecutive clean shadow cycles (clean = engine completes
  end-to-end, zero findings-parse failures, rendered review file passes
  check_review_file.py, and the shadow verdict matches or is stricter
  than the legacy verdict on the same diff); stats show dedup collapsing
  (raw > unique); default flipped and legacy path retired from the
  dispatch table.
- **B**: all 14 personas exist as agent files; each dispatch path
  assembles a prompt byte-identical to its pre-extraction prompt on a
  fixture diff (frontmatter stripped; parity on prompt text, not
  findings); no prompt text remains inline in the workflow JS or skill
  references; boot-prefix delta stays ~1-2K tokens; a missing-agent-file
  fixture yields CHANGES_REQUESTED (native) / runner error (CLI); agent
  frontmatter carries the per-agent tool sets and Eve's `model: fable`
  pin; rg finds no undisambiguated `R{n}` rubric references.
- **C**: patterns-compliance arms only with a context source present;
  performance arms only on its heuristic; a quiet diff spawns zero extra
  agents; agreement reorders Victor's queue in journal stats.
- **E**: packs reach workflow lanes via `context_path` and CLI lanes via
  /tmp staging; Blake's prompt provably never contains pack content.
- **F gate (proof bar)**: >=2 real PRDs drained hands-off on the full
  stack with review converging within the rework cap (no human rescue) -
  only then does extraction start.

## Risks
- **Shadow cycles starve** (batch halted): hand-run 00051 + interactive
  reviews opt in via `consensus_engine: shadow`; B itself banks cycles
  when the next batch drains it.
- **More specialists = more noise**: C's dimensions are gated; MEDIUM/LOW
  stay advisory; C lands only after A's economics are measured.
- **Registry drift**: B deletes the inline prompts - the agent files are
  the only source; fail-closed dispatch makes breakage loud (accepted
  cost: a typo blocks review until fixed).
- **Registry conventions diverge from the QA pack**: 00091 builds on the
  same registry; B is the convention-setter and lands first in the
  backlog ordering.
- **Plugin extraction drags autopilot coupling**: F ships workflow +
  agents + a lean skill, never review-work-completion itself.

## Open Questions
- Plugin name (decide at F kickoff): quorum / tribunal / conclave / synod.
- Does E's pack also feed the doubt lens (Bob/codex), or only consensus
  dimensions? (Engram discovery Q8; decide when E's PRD is created.)
- Dimension-agent model tier (nice-to-have): revisit with A's measured
  economics.

## Discovery Log

### Q1: Where should B/C be built - ~/.claude or a plugin-first repo?
**Answer**: In ~/.claude, extract at F. Zero packaging friction while
iterating; accepted meta-spend and an M-sized F.

### Q2: Which domain specialists should C add?
**Answer**: patterns-compliance + performance, both context/trigger-gated;
no further dimensions.

### Q3: When does engram PRD creation start relative to A-C?
**Answer**: Now, parallel tracks - engram (00090) builds in its own repo on
product budget; only E depends on it.

### Q4 (user directive): All reviewers must become named agents in
~/.claude/agents/ for plugin extraction and per-agent improvements over
prompt-based general-purpose subagents.
**Answer**: Adopted as must-have 2/5; CLI lanes keep Bash dispatch but
source prompts from agent files.

### Q5 (user directive): Unnamed roles must get nice names like the others.
**Answer**: Crypto-cast style roster adopted (must-have 3). Tess renamed
Toby after 00091's scan surfaced the existing Tess test-author persona in
/work.

### Q6: How to handle the registry's global boot-context tax?
**Answer**: Accept, with terse-description discipline (~1-2K tokens);
trimming or measurement gates rejected.

### Q7: What proves the framework before F?
**Answer**: >=2 real PRDs converge within the rework cap, hands-off, on
the full stack. Cost-target and judgment-call bars rejected.

### Q8: When and how does B land?
**Answer**: Backlog now; the next autopilot batch drains it. B doubles as
a shadow-cycle generator for A.

### Q9: Missing/malformed agent file at dispatch?
**Answer**: Fail closed, no fallback - review incomplete /
CHANGES_REQUESTED (native), runner error (CLI). No shadow prompt copies.

### Inferred (not asked - answered by prior work this session)
- Problem validation: training audit + measured convergence pain + plugin
  goal (conversation, 2026-07-31).
- Integration points: mapped by the architecture explorer (persona files,
  runners, gates, hooks - see Codebase Context).
- Pattern reuse: extend review-fanout + existing roster; no rebuild (D1).
- Decomposition: six sequenced PRDs A-F with D as a separate repo chain -
  set in the roadmap before elicitation; create-prd consumes this doc per
  track (A and B first).
- Constraints: CLI-in-agent hang boundary, headless invariants,
  review-file contract stability - all standing rules or memories.
