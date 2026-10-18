# Discovery: Engram - Context Engine for Agent Discovery/Memory

## Classification
Depth: comprehensive | Date: 2026-07-31

## Problem
Agents rebuild project context from scratch and lexical tools cap what they
can recall. Capsule (derived invariants), atlas (code map), auto-memory
(curated facts), and agentic grep cover in-repo code and curated facts well.
Three recall classes have no tool:

1. **Semantic recall over prose** - memories, PRDs, decisions, discovery
   docs, ~1,700 cellar transcripts (~900MB JSONL). Paraphrase queries
   ("that time autopilot hung on network death") miss because rg needs the
   exact token.
2. **Cross-repo code reuse** - "have I already built retry-with-backoff / a
   PreToolUse hook that blocks X?" across the 26 gita-registered repos.
   Research-and-reuse rule step 0 mandates this search; today it is manual.
3. **Review context** - reviewers see diff + PRD but not similar local
   code, reuse precedent, or prior findings; findings are mortal (review
   satellites die with their PRD, autopilot artifacts GC at 14 days), so
   review patterns never accumulate into precedent.

Engram: chunking + local embeddings + hybrid scoped vector search over
prose and code, feeding the capsule at catchup, ad-hoc queries mid-task,
and diff-selective review packs.

## Requirements

### Must have
1. **Chunker**: tree-sitter symbol-level for code (whole function/class,
   embedded with signature + docstring + file path); heading-split for
   prose. No blind fixed-token windows.
2. **Local embeddings**: OpenAI-compatible `/v1/embeddings` endpoint on a
   LlamaBarn-served llama.cpp instance - engram never launches its own
   server. Preflight = one real embedding call with a cold-load ceiling
   (`/v1/models` is false-healthy; mirror `qwen-run.sh --preflight`).
   No cloud keys, no Ollama.
3. **Central scoped store**: one sqlite-vec DB under
   `~/.local/share/engram/`; metadata columns: corpus, repo, doc type.
   Every query runs as `--scope repo` (current repo) or
   `--scope portfolio` - never unscoped. Repo-scoped and cross-repo
   retrieval are one engine with different filters. The store records
   embedding model id + dimension; on mismatch engram fails loud and
   requires a full re-embed.
4. **Hybrid retrieval**: FTS5 (BM25) fused with vectors via reciprocal
   rank fusion. Exact-ish queries (error strings, symbol names) win on
   BM25; conceptual queries win on vectors.
5. **Pointers, not chunks**: results are `file:line` + signature/heading +
   score; agents Read the real bytes at HEAD. Exception: mortal sources
   (review findings) are stored as extracted records (see item 11).
6. **Incremental indexing** keyed on content hash (git blob hash for
   tracked files, `git hash-object` for untracked prose). Code corpus =
   tracked files at HEAD of each repo's current checkout
   (`git ls-files`); repo enumeration from gita's
   `~/.config/gita/repos.csv`. Refresh triggers: catchup, immediately
   before pack generation, manual `engram index`. No daemons, no
   per-repo git hooks. Reindex prunes rows whose source no longer
   exists (deleted files, unregistered repos, removed docs); extracted
   records (item 11) are exempt.
7. **CLI-first**: `engram query|index|status|pack`; `status` shows
   per-corpus staleness - fail loud. MCP wrapper only if a need shows up.
8. **Corpora v1**: auto-memories, PRD folders across repos, per-repo
   `dev/local/decisions.md`, discovery docs, cellar transcripts (user +
   assistant text turns PLUS error-bearing tool results), code symbols
   from all registered repos.
9. **Capsule integration**: catchup writes a "Related context" section
   (top engram hits for the branch/PRD topic) into
   `dev/local/project-capsule.md`.
10. **Eval harness**: gold set of real queries (seed: each auto-memory's
    hook line is a natural query/answer pair); engram must beat an
    rg/Explore baseline before it is wired into catchup.
11. **Review-findings corpus**: durable records (severity, file, pattern,
    verdict, PRD, repo) parsed from the review-file contract (frontmatter
    + Verdict:/Tests: lines). Harvest: purge-devlocal pre-trash sweep
    (loss-proof at the GC choke point) + opportunistic harvest at catchup.
    Enables precedent queries, attacking the weak-evidence/low-trust
    review failure mode; accumulates raw material for pattern-to-skill
    distillation.
12. **Diff-selective review packs**: `engram pack --cycle <id>` (or
    `--diff <range>`) consumes the staged `dev/local/tmp/review-diff-{id}.diff`,
    parses it AST-aware (which symbols changed), retrieves per changed
    symbol, and emits `dev/local/tmp/engram-pack-{id}.md` - bounded,
    size-capped, per-section scopes, each labeled with origin:
    - *Similar code* - `--scope repo` ONLY; foreign conventions must
      never read as local precedent.
    - *Reuse precedent* - `--scope portfolio`, labeled per source repo.
    - *Findings precedent* - both scopes, labeled.
    - *Task prose* - PRD, capsule extract, related memories.
    Wiring: CLI reviewer lanes (Bob/codex, Carl/gemini, Quinn/qwen)
    receive the pack via their prompt files (templates in
    review-work-completion `references/agent-prompts.md`); Claude
    consensus/doubt lenses get it prepended. The blind lens (Blake,
    PRD-only) never receives a pack. Incremental reindex runs immediately
    before pack generation.

### Nice to have
- LLM-generated one-liner per code symbol embedded alongside it (big
  NL-to-code retrieval gain; costs an LLM pass over the corpus).
- Post-commit reindex hook.
- Transcript turn summarization before embedding.
- Distill loop: clustering recurring review findings into skill/rule
  candidates. Ships later as a separate consumer skill (audit-echo
  territory); engram v1 only supplies the queryable corpus.

### Out of scope
- **Interactive in-repo code navigation** - agentic grep (rg + Explore)
  owns it. In-repo symbols are indexed regardless (the portfolio corpus
  contains every repo) and review packs consume them, but "find the
  function that does X here" as an agent query stays out; this boundary
  is the main scope-creep risk.
- Call-graph / who-calls / impact queries - LSP and tree-sitter territory.
- Cloud embedding APIs; server-based vector DBs (Chroma etc.) -
  sqlite-vec is one file, no daemon.
- Per-repo indexes (the flagship query is cross-repo by nature).

## Constraints
- Local inference only; servers managed by LlamaBarn, never self-launched;
  embedding model must exist as GGUF (HF hub cache
  `~/.cache/huggingface/hub/`).
- Standalone repo `~/git/src/github.com/buvis/engram` - product, not
  ~/.claude meta-spend. Python, uv-managed, single package.
- Reviewer staging convention: project `dev/local/tmp/`, cycle-id keyed,
  always absolute paths (subagents misresolve relative `dev/local/`).
- Stale results agents trust are worse than none: staleness visible in
  `engram status` and refresh-before-consume at every wired touchpoint.
- Active repo churns mid-session; mid-session edits are not indexed - the
  pointer contract is what makes that safe.

## Codebase Context
- **Relevant code**:
  `~/.claude/skills/review-work-completion/scripts/gather-context.sh`
  (emits `review-context-{id}.md` + `review-diff-{id}.diff` into
  `dev/local/tmp/`, cycle id from PRD filename);
  `references/agent-prompts.md`, `references/blind-lens-prompt.md`,
  `references/agent-invocation.md` (reviewer prompt templates + contract);
  `~/.claude/skills/use-codex/scripts/codex-run.sh`,
  `~/.claude/skills/use-gemini/scripts/gemini-run.sh`,
  `~/.claude/skills/use-qwen/scripts/qwen-run.sh` (CLI lanes, `-f`
  prompt / `-o` output into the same dir);
  `~/.claude/skills/purge-devlocal/scripts/purge_devlocal.py` (GC choke
  point for the pre-trash harvest);
  git-ferry catchup `SKILL.md` (capsule sections, refresh flow);
  `~/.config/gita/repos.csv` (26 repos, `path,name,type,group`);
  per-repo `dev/local/decisions.md` (decision logs, enumerated via
  repos.csv);
  cellar transcripts at
  `~/git/src/github.com/buvis/cellar/.claude/projects/<path-slug>/{uuid}.jsonl`.
- **Conventions**: preflight = real 1-token/embedding call with cold-load
  ceiling (`qwen-run.sh --preflight` is the template); LlamaBarn
  `models.ini` + endpoint registry in `~/.pi/agent/models.json`;
  tree-sitter-language-pack already in use (hooks tests); snake_case
  scripts; action-verb command names; hooks Python-only.
- **Integration points**: catchup SKILL.md (Related-context section +
  reindex call), agent-prompts.md templates (pack reference for CLI lanes
  + consensus/doubt; blind untouched), purge_devlocal.py (pre-trash
  sweep), review invocation doc (pack staging step).
- **Similar implementations**: `qwen-run.sh` (client wrapper over a
  LlamaBarn endpoint with preflight + approved-model registry) is the
  pattern for engram's embedding client; purge-devlocal's trash-first
  manifest is the pattern for harvest bookkeeping.

## Approach
- **Chosen**: single engine; central scoped sqlite-vec store; hybrid
  BM25+vector RRF; CLI-first; LlamaBarn-served local embeddings.
  Delivered as four sequenced PRDs (C split at the corpus/pack seam
  per discovery review 2026-07-31):
  - **A - core**: repo scaffold, chunk/embed/store/query pipeline,
    embedding endpoint + preflight, prose corpora minus transcripts,
    scoped CLI, eval harness gate.
  - **B - heavy corpora**: transcripts (error-bearing filter), cross-repo
    code symbols, capsule/catchup integration.
  - **C1 - findings corpus**: findings corpus + harvest wiring
    (purge pre-trash + catchup).
  - **C2 - review packs**: diff-selective packs, reviewer
    staging/templates.
- **Why**: session-sized PRDs (the review loop demonstrably fails to
  converge on oversized PRDs); eval gate ships first so later phases
  build on proven retrieval.
- **Rejected alternatives**:
  - One PRD or two PRDs: 6-10 days in a PRD is the documented
    non-convergence shape (~$13/task, cap-3 review loops).
  - Review loop before heavy corpora: packs would ship with an empty
    similar-code section (no code corpus yet) - hollow first impression,
    rework risk.
  - Phased prose-first scope (no code): overruled in Q2 - combined build.
  - Pre-retrieval rejected entirely: overruled in Q6 - CLI lanes are
    staged-input consumers, exactly the harness pre-retrieval helps.
  - Per-repo indexes: flagship query is cross-repo; scope filters on one
    DB give repo isolation where needed.
  - Chroma / any daemon vector DB: sqlite-vec is one file, no ops.
  - Post-commit hooks or launchd timer for freshness: rollout/ops burden;
    refresh-at-consumption covers every wired consumer.

## Success Criteria
- Gold-set paraphrase queries over memories/PRDs/transcripts: right doc in
  top-5 for >=80% (rg baseline fails most by construction).
- Seeded cross-repo duplicates (known repeated patterns, e.g. retry
  logic, notify plumbing) surface in the top-5 for >=80% of "have I
  built X" seed queries.
- Catchup emits a Related-context capsule section with zero manual steps.
- Review packs: on a sample of past PRDs, each pack surfaces at least one
  relevant item absent from the diff; no foreign-repo chunk ever appears
  in the similar-code section (scope-filter test).
- Zero-loss harvest: purging a repo with review satellites leaves every
  finding queryable afterwards (tested on a sample repo).
- Incremental reindex of an unchanged portfolio is seconds, not minutes.
- Zero network calls off-machine.

## Risks
- **Transcript noise**: the error-bearing heuristic needs tuning; eval
  judges it, summarization is the upgrade path.
- **Embedding model quality on code**: varies a lot; eval decides the
  model from the shortlist, not vibes. GGUF/LlamaBarn availability
  constrains the shortlist.
- **Staleness trust**: mitigated by refresh-before-consume + status
  banner; capsule inherits stale hits if catchup skips the refresh.
- **Pack budget overflow**: packs eat reviewer context if uncapped; hard
  cap with a defined cut order (open question).
- **Scope creep** back toward in-repo nav or graph queries.
- **Cross-PRD contract drift** across A/B/C1/C2: engram repo owns the CLI
  contract; each integration edit lands inside the PRD that needs it.

## Open Questions
1. Embedding model shortlist (qwen3-embedding? nomic-embed? bge-m3?) +
   GGUF availability under LlamaBarn; eval harness decides.
2. Pack token budget: hard cap and per-section caps, cut order when over
   budget; does the doubt lens get the full pack or findings-precedent
   only?
3. Error-bearing heuristic final shape (start set: tracebacks/panics,
   non-zero exit markers, ERROR/FAIL patterns; tune against eval).
4. Gold set size and composition (~30-50 queries: memory hook lines +
   seeded cross-repo duplicates + known past-incident paraphrases?).

## Discovery Log

### Q1: Does the code piece add value over agentic grep? (2026-07-30)
In-repo navigation: no (identifiers lexically distinctive, index never
stale, zero infra). Reframed as **cross-repo reuse discovery**: yes -
serves research-and-reuse step 0, which grep cannot do across an
unknown-repo portfolio. Decision: include code, cross-repo-scoped;
in-repo nav out.

### Q2: Build scope? (2026-07-30)
Options: phased prose-first, combined day one, full engine incl. in-repo
nav, prose-only. **Decision: combined from day one.**

### Q3: Name? (2026-07-30)
Candidates: engram, hound, dowser, madeleine. **Decision: engram** (the
physical trace a memory leaves - what a stored chunk+embedding is).

### Q4: Architecture defaults (2026-07-30, accepted without objection)
Local llama.cpp embedding serving; central sqlite-vec DB; hybrid
FTS5+vector RRF; tree-sitter/heading chunking; CLI-first; standalone
buvis repo.

### Q5: PR-review training takeaways? (2026-07-31)
Course notes vs existing stack: harness separation, pre-PR review, task
context, standards-as-context, severity tiers, ensemble review - all
already covered by autopilot/review-fanout/rules. **Decision: add the
review-findings corpus** with the mortal-source durability exception;
distill loop deferred to a later consumer skill. Chroma rejected
(daemon). Initial rejection of reviewer context packs - overturned in Q6.

### Q6: Reviewer context packs - challenge to Q5 (2026-07-31)
User overruled the rejection: training showed diff-selective AST/embedding
retrieval measurably improves review results. Original rationale was
half-wrong: CLI reviewer lanes are staged-input consumers, not agentic
explorers - exactly the harness shape pre-retrieval helps; embedding
similarity also surfaces code a reviewer didn't know to grep for.
**Decision: diff-selective review packs are must-have 12.** Follow-up
hazard caught by user: unscoped KNN would return foreign-repo chunks as
local precedent. Resolved via first-class scope filters; similar-code
section repo-scoped only; blind lens stays pack-free.

### Q7: Code corpus source - which repo state? (elicitation 2026-07-31)
**Answer**: Tracked files at HEAD of each repo's current checkout
(`git ls-files`). Blob-hash incrementality native; local commits
included. Accepted drawback: a repo parked on a WIP branch indexes
transient symbols.

### Q8: Reindex triggers? (elicitation 2026-07-31)
**Answer**: Catchup + immediately before pack generation, plus manual
`engram index`. No daemons, no per-repo git hooks. Ad-hoc staleness
between refresh points accepted and surfaced by `engram status`.

### Q9: Transcript filtering? (elicitation 2026-07-31)
**Answer**: User + assistant text turns PLUS error-bearing tool results -
the error text is what future queries hunt for. Accepted cost: an
"error-bearing" heuristic to build and tune (open question 3).

### Q10: Findings harvest trigger? (elicitation 2026-07-31)
**Answer**: purge-devlocal pre-trash sweep (loss-proof at the GC choke
point) + opportunistic harvest at catchup. No edits to review flows.
Accepted lag: precedent may trail its review by days.

### Q11: PRD split? (elicitation 2026-07-31)
**Answer**: 3 sequenced PRDs - A core (pipeline + prose sans transcripts
+ eval gate), B heavy corpora (transcripts, code, capsule), C review
loop (findings, packs, wiring). Accepted drawback: the pack payoff lands
last.

### Inferred (no question asked)
- Repo enumeration: gita `repos.csv` (brownfield scan found 26 repos, no
  groups) - resolves former open question 5.
- Gold-set seed: memory hook lines as query/answer pairs (open question 4
  covers size/composition only).
- Priority: none stated; backlog ordering left to review-prd-backlog.

### Contradiction check (comprehensive-depth pass)
None found. The one tension - packs are the most-wanted piece yet land in
PRD C - was raised and explicitly accepted in Q11.
