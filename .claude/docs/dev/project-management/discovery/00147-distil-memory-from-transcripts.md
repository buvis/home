# Discovery: Distil Memory Candidates From Session Transcripts

## Classification

Depth: comprehensive | Date: 2026-08-26

Replaces the instinct pipeline retired the same day (buvis `24975e2e`).

## Problem

Facts worth carrying between sessions get established in a session and then
lost, unless someone deliberately writes a memory file. That only happens when
the user or the model remembers to do it, which is exactly what people are worst
at noticing. The instinct pipeline was built to close this gap and never
delivered a single fact: it wrote to a path its own encoder computed wrong, and
what it produced were tautologies with the trigger and action set to the same
string. It was deleted rather than repaired (see
`dev/local/audit-results/observer-hooks-audit-2026-08-26.md`). The want survives
the implementation, and the corpus that could answer it already exists: cellar
archives 2,371 transcripts across 25 projects, holding every verified finding
and every correction of the last several months.

## Requirements

### Must have

- An on-demand pass over archived transcripts that proposes auto-memory entries.
- One signal: **verified findings** (-> `project` memories). Corrections the
  user gave are deferred to their own discovery doc; see Out of scope.
- Provenance filtering that separates real content from injected content. The
  user-turn half is now solved upstream (claude-checkup `d10ecb1`), so v1
  depends on a release carrying it rather than rebuilding it. The
  assistant-side extraction still needs its own check, since no equivalent
  filter exists there.
- An LLM distiller that separates a durable fact from a transient verification,
  and emits a complete memory file: frontmatter (`name`, `description`, `type`),
  body, and `[[links]]`.
- Every proposal carries the transcript evidence it came from, so it can be
  judged without reopening the session.
- Deduplication against existing memory: the distiller shortlists candidates
  from the target project's `MEMORY.md` index, then reads the shortlisted memory
  files themselves before deciding, since the index carries hooks rather than
  content. Proposal type is `new` or `update <existing-name>`.
- One-at-a-time approval in chat: keep, edit, or drop per proposal. On edit the
  user states the correction in chat and the distiller re-emits the whole file,
  which is re-checked against the frontmatter contract before it is written.
- A persisted proposal queue, so a partly-walked batch resumes after the session
  ends.
- A cursor, so `--all` drains over several capped runs.
- A rejection record keyed on the proposal's source slice plus the distiller
  rubric version, so a dropped proposal never comes back while the rubric that
  judged it is current, and a rubric change re-opens its drops.
- Every run reports its own yield out loud, including "nothing found".
- A `--project` filter, so the first run is a single-project pilot before any
  full sweep. The Risks section relies on it.
- A dry-run that reports counts per stage of the funnel without calling the
  strong model. The Risks section relies on it.

### Nice to have

- None. Both former candidates (`--project`, the dry-run) were promoted to Must
  have, because the Risks section names them as its two mitigations.

### Out of scope

- Corrections as a second signal (`feedback` memories). The measured yield is
  thin (11 raw matches across 8 files) and no detector, criterion, or funnel
  stage is specified for it here. Deferred to its own discovery doc, which
  reuses this feature's funnel, queue, and walkthrough; see Open Questions.
- Cross-project routing. A fact established about repo B during a session in
  repo A is proposed into A's memory. Deferred; see Open Questions.
- Any automatic write. Nothing reaches a memory directory without an explicit
  per-entry decision.
- Any always-on hook. This is invoked, never triggered.
- Promotion of memories into skills or rules.

## Constraints

- **No silent writes and no computed delivery path.** The retired pipeline
  failed exactly there.
- **Budget.** `~/.claude` work is capped at 30% of monthly spend and this is
  meta work by definition, so the sweep must be bounded by construction rather
  than by care.
- **Corpus scale.** 2,371 transcripts, 1.4 GB. Nothing may read it wholesale.
- **Memory conventions** in `rules/memory.md` and the auto-memory frontmatter
  contract are fixed. Proposals conform; they do not invent a format.
- **Python, stdlib-first**, matching the surrounding scripts.

## Codebase Context

### Relevant code

- `~/.claude/plugins/cache/buvis-plugins/claude-checkup/0.2.1/skills/audit-sessions/scripts/parser.py`
  parses one transcript into user prompts, tool calls and markers. Carries a
  partial provenance filter: `_is_real_user_prompt` checks `isMeta` and rejects
  `_SYNTHETIC_USER_PREFIXES` (`<system-reminder>`, `<task-notification>`,
  `<command-name>`, `<local-command-stdout>`, `[Request interrupted by user`).
- `.../audit-sessions/scripts/analyze.py` builds on it: `detect_repeated_prompts`
  (>=3 occurrences across >=2 sessions), `detect_skill_negative_followup` (user
  text correcting Claude right after a skill ran), a `--days` lookback.
- `.../audit-sessions/SKILL.md` step 2 already asks the model to classify a
  repeated-prompt cluster as "a coherent workflow (skill candidate) or a
  repeated context dump (**memory candidate**)". The concept exists; nothing
  turns it into a memory file.
- `~/.claude/projects/<encoded>/memory/` is the write target, 25 stores.

### MEASURED 2026-08-26: the corpus is 7x smaller than it looks

Counting `type == "user"` rows across 406 transcripts in this project:

| filter applied | user turns remaining |
|---|---|
| none (naive `type == "user"`) | 1,892 |
| minus skill bodies, hook output, command wrappers | 1,061 |
| minus `<task-notification>` and other injected XML | 423 |
| minus generated agent-persona prompts (`You are Pat, ...`) | **272** |

272 is still not clean; the remainder visibly holds more skill bodies
(`# Schedule Cloud Agents`, `# Update Config Skill`) and autopilot dispatch
prompts.

Two consequences:

1. **Skills, hooks and subagent prompts are injected with `role: user`.** A
   distiller mining "user corrections" naively would read the repo's own rule
   files back out and propose them as learned facts. That is the fastest way to
   rebuild what was just deleted.
2. **`isSidechain` does not separate them.** Adding that filter changed the
   count by one turn. Headless reviewer and implementor sessions are their own
   `.jsonl` files in the same project directory, not sidechains.

**CORRECTED 2026-08-26, after the above was first written.** The table measures
a *naive* parse. `parser.py` is not naive: `_is_real_user_prompt` already
rejects `isMeta`, which covers skill bodies and slash-command expansions.
Re-measuring against the real function: it kept **416** prompts, of which
**216 `typed` + 16 `suggestion_accepted` + 13 `queued` = 245 human**, plus
**170 `promptSource: "sdk"`** machine-written agent prompts and 1 entry from a
transcript predating both fields. So the leak was 41% (~1.7x), not the 4x
claimed earlier, and it was one shape only, not four.

Crucially, **the schema names every one of these**, so no text heuristic is
needed and `parser.py` keeps its "no heuristics live here" contract:

| entry kind | `isMeta` | `promptSource` | `origin.kind` |
|---|---|---|---|
| skill body / command expansion | `true` | absent | absent |
| SDK agent prompt | absent | `sdk` | absent |
| typed turn | absent | `typed` / `suggestion_accepted` / `queued` | `human` |

Fixed 2026-08-26 in claude-checkup `d10ecb1`: a negative check on
`promptSource == "sdk"`, chosen over a positive `origin.kind == "human"` check
because 1 of the 416 predates both fields and a positive check would drop it
silently. Verified on the real corpus: 416 -> 246. **Not live until
claude-checkup is released and installed**; 0.2.1 still over-counts.

Consequence for this feature: the provenance filter is largely *solved
upstream*, which shrinks v1. What remains is verifying the assistant-side
extraction, which has no equivalent filter yet.

### MEASURED 2026-08-26: signal density inverts the obvious guess

| signal | raw matches | files |
|---|---|---|
| verification markers (`MEASURED`, `Verified:`, `proven live`, ...) | 1,261 | 276 |
| correction phrases (`never do that`, `actually, use`, ...) | 11 | 8 |

Of the ~272 surviving user turns, 62 carry a correction-shaped word (`don't` 54,
`never` 36, `stop` 11, `wrong` 10, `always` 6, `instead` 5), and most of those
are still injected content.

### MEASURED 2026-08-26: marker abundance is not candidate precision

Assistant-role text only, 406 transcripts: **224 sessions carry a marker, 528
hits, median 2 per session, max 16.**

Most hits are transient process verifications with no durable value ("confirmed
the full suite green: 23 pytest + 48 npm tests", "Red confirmed as expected",
"all 264 tests pass"). A minority are durable facts ("`notify.py` has **zero**
autopilot coupling").

So the marker is a cheap recall filter, not a precision one. Telling "a
transient state was verified" from "a durable fact was established" is the
distiller's real job, and it is genuine model work rather than formatting.

### Conventions

- Memory files: frontmatter `name` / `description` / `metadata.type`, body with
  `**Why:**` and `**How to apply:**` for feedback and project types, `[[links]]`
  between related memories, one-line pointer appended to `MEMORY.md`.
- Existing type mix here: `project` 38, `feedback` 17, `reference` 12, `user` 0.
- Skill reports belong in `dev/local/audit-results/`, and a run ends with a
  verbatim how-to-proceed block (`feedback_skill_reports_to_audit_results`).
- Findings needing a decision are walked one at a time (`rules/communication.md`).

### Integration points

- `parser.py` already carries the provenance fix (claude-checkup `d10ecb1`).
  This feature consumes it, resolves the plugin cache by version glob, and fails
  loudly when the resolved version predates the fix.
- The new skill lives in `~/git/src/github.com/buvis/agent-skills`, reaching
  `~/.claude/skills` via braid.
- It resolves the plugin cache by version glob rather than a pinned path.

### Similar implementations

- `hooks/strunk-ruling-inject.py:resolve_strunk_skills_dir()` is the house
  pattern for importing across a versioned plugin cache: glob
  `<cache>/<plugin>/*/skills/`, parse each directory name into a version tuple,
  take the max. Copy this rather than pinning `0.2.1`.
- ECC's `continuous-learning-v2` is the upstream this idea came from. Worth
  reading for its instinct schema and its `agents/observer.md` prompt, which is
  a model distiller rather than a counter. Note before borrowing further: its
  `config.json` ships `observer.enabled: false`, its observer does not survive
  on native Windows, and its relevance ranking sits behind a feature flag, so
  the always-on half is less proven than the docs imply.

## Approach

### Chosen

A five-stage funnel behind an on-demand skill, each stage bounding a different
cost:

| stage | bounds | mechanism |
|---|---|---|
| lookback window | corpus size | default 30 days; `--all` for full history |
| marker regex | 1.4 GB -> slices | free, no model involved |
| cheap triage (Haiku) | strong-model spend | discards transient verifications |
| strong model | proposal quality | reads only twice-filtered slices |
| per-run cap + cursor | review time | N proposals per run, resumable |

Survivors land in a persisted queue. The walkthrough consumes the queue one
proposal at a time (keep / edit / drop), writes approved entries into the
target project's memory directory, appends the `MEMORY.md` pointer, and records
drops so they never return.

### Why

- The regex does the heavy lifting for free and is the only thing that makes a
  1.4 GB corpus tractable.
- Two model tiers keep the expensive one reading only what already passed two
  filters, which is what holds the sweep inside the meta budget.
- The cursor is load-bearing twice: it makes `--all` drainable and the
  walkthrough resumable.
- Every failure of the retired pipeline is structurally excluded: a model
  distiller instead of a counter, a tested provenance filter instead of a naive
  parse, an explicit human gate instead of a computed path, and a spoken yield
  instead of silence.

### Rejected alternatives

- **Whole-session LLM judgement, no detector**: closest to what just failed.
  Unbounded cost, and with no anchor the output drifts to plausible filler.
- **Repeated-prompt clusters as the signal**: finds what the user repeats, not
  what is true. Proposals would need so much rewriting that the cluster stops
  being evidence.
- **Corrections-only v1** (the Q1 recommendation): withdrawn on measurement. The
  detector exists; the signal does not.
- **Batch review file with keep/drop markers** (the Q3 recommendation): rejected
  by the user in favour of a walkthrough. The scale objection is answered by the
  per-run cap and the resumable queue instead.
- **Bulk approve of a whole batch**: invites rubber-stamping, which is how a
  low-quality entry reaches memory.
- **A home inside claude-checkup**: reasonable while that plugin is Claude-only,
  but it is migrating to the agent-plugins standard, so the skill can live in
  `agent-skills` and still reach other agents.
- **A Claude-only skill in `~/.claude/skills`**: fastest to iterate, but it
  breaks the standing convention for general skills for no lasting gain.
- **Cross-project routing in v1**: the model guessing which repo a fact belongs
  to is the same class of mistake as the encoder bug just retired. Not now.

## Success Criteria

- A run over a 30-day window completes and reports counts at every funnel stage,
  including zero.
- A contract check fails loudly, naming the version it resolved, when the
  installed claude-checkup predates `d10ecb1`. The user-side shapes measured
  here (skill body, agent persona prompt, `<task-notification>`, slash-command
  expansion, hook message) are covered by that release's own tests and are not
  re-tested here.
- The assistant-side extraction has tests that fail on each injected shape it
  can encounter; that list is enumerated during design.
- No proposal's `description` restates its `**How to apply:**` line. A proposal
  whose recall cue and content are the same sentence is rejected before it
  reaches the queue, with a test proving it.
- An approved proposal produces a memory file that passes the same frontmatter
  contract as the existing 70, plus its `MEMORY.md` pointer line.
- Interrupting a walkthrough and re-invoking resumes at the next undecided
  proposal, with no duplicates and no skips.
- A dropped proposal does not reappear on a second run over the same window.
- `--all` over 2,371 transcripts stays within its per-run cap and leaves a
  cursor that a second run advances.

## Risks

- **The distiller reads injected content and proposes the repo's own rules back
  as discoveries**: the failure that killed the last system, one layer up.
  Mitigation on the user side is already shipped and tested upstream
  (claude-checkup `d10ecb1`). The residual risk is the assistant side, which has
  no filter yet, and a stale installed plugin: pin a minimum claude-checkup
  version and fail loudly rather than silently parsing with the old rules.
- **A first `--all` sweep costs more than expected**: mitigation is the funnel,
  plus a dry-run mode that reports per-stage counts before any strong-model
  call.
- **Proposal quality is mediocre and the walkthrough becomes a chore**:
  mitigation is to measure on a single project first and require the yield
  report; if precision is poor the rubric is tuned before the sweep widens.
- **`parser.py` changes underneath the skill**: it lives in another repo, so a
  break surfaces at runtime rather than in the plugin's tests. Mitigation: a
  contract check that asserts the imported parser exposes what is needed and
  fails naming the version it resolved.
- **The plugin cache root moves** when claude-checkup migrates to the
  agent-plugins standard. Mitigation: the resolver's root is a single named
  constant, so the migration is one edit.
- **Memory bloat**: dozens of approved entries could swell the always-loaded
  `MEMORY.md`. Mitigation: the index line is one line per memory, and the
  walkthrough is the throttle. Revisit if a store passes ~100 entries.

## Open Questions

- **Cross-project routing.** A fact about repo B learned in a repo A session
  goes to A's memory. Deferred from Q4 by choosing the sweep over the routing
  option. Revisit after the walkthrough has run a few times and it is clear how
  often this bites.
- **Corrections as a second signal.** Deferred from Q2's "both, verified
  findings first" by review 2026-08-26: the phase named no detector, no success
  criterion and no funnel stage, and its measured yield is thin. It gets its own
  discovery doc once this feature has run, and reuses the funnel, queue and
  walkthrough rather than rebuilding them.
- ~~**Where the parser fix ships.**~~ RESOLVED 2026-08-26: shipped
  independently as claude-checkup `d10ecb1`, ahead of this PRD. This feature now
  depends on a claude-checkup release carrying it; `/create-prd` should record
  that as a prerequisite rather than re-plan the fix.
- **The strong model's rubric for "durable".** The negative class is now well
  evidenced (transient test-pass verifications). The positive class should be
  anchored on the existing 70 memories as few-shot examples; the exact prompt is
  a design task, not a user decision.
- **The per-run cap N.** No basis to pick a number yet. Suggest starting at 10
  and tuning after the first real run.
- **PRD slicing.** This discovery is an epic. Suggested slices: (1) extraction +
  funnel + yield report + dry-run; (2) distiller + dedup + proposal schema;
  (3) queue + cursor + rejection record + walkthrough. `create-prd` may resize
  them but should not merge them into one PRD.

## Discovery Log

### Q1: What signal does the distiller mine?

Options: corrections given / verified findings / repeated context / whole-session
LLM judgement. Recommended corrections-only for v1, on the grounds that a single
sharp target is what the retired pipeline lacked, and a prototype detector
already existed.

**Answer:** "I want to catch corrections I gave and verified findings. Design it
to work better than last time."

Recorded: two signals, not one. "Better than last time" taken as an explicit
quality bar, expanded into the four structural exclusions listed under Approach.

### Post-Q1 measurement (unprompted)

Ran before Q2 because the corrections detector's yield was assumable but not
assumed. Produced the three MEASURED sections above and **contradicted the Q1
recommendation**: the corrections detector exists but its signal is thin, while
verified findings are abundant and sit in uncontaminated assistant text.

### Q2: Does the thin corrections signal change v1 scope?

New evidence put to the user rather than acted on quietly.

**Answer:** "Both, verified findings first."

Recorded: both signals stay, phased. Verified findings ship first and prove the
shared components against the thick signal; corrections follow, reusing them.

Revised by review 2026-08-26: the phasing stands, but corrections moved to Out
of scope and to their own discovery doc, because nothing here specified their
detector, criteria, or funnel stage.

### Q3: How does approval work?

Options: reviewable batch file / one-at-a-time walkthrough / batched
multi-select / batch file with bulk approve. Recommended the batch file on scale
grounds.

**Answer:** "One-at-a-time walkthrough."

Recorded: every proposal decided individually, no bulk approve. The scale
drawback named when offering it is absorbed by design rather than argued: the
queue is persisted and the walkthrough resumable.

### Q4: Which projects does a run cover?

**Answer:** "All projects in one sweep."

Recorded: 2,371 transcripts, 1.4 GB, 25 memory stores. A fact is proposed to the
project whose transcript carried it; cross-project routing was a separate option
and was not chosen.

### Q5: How is the sweep bounded so it stays affordable?

Options: tiered triage + per-run cap / lookback window / cap only / no bound.

**Answer:** "is combination of 1 and 2 possible?" Answered yes, they bound
different costs and compose. Combination adopted as the five-stage funnel.

### Q6: Where does this live?

First framing claimed a home in `agent-skills` forces a second copy of
`parser.py`. The user challenged that. **The claim was wrong**: the
version-globbing idiom in `strunk-ruling-inject.py` imports across a plugin
cache without pinning. Restated with the real tension, dependency direction: a
skill in `agent-skills` exists to reach other agents, and importing a
Claude-only plugin would defeat that.

**Answer:** "proposal 2 is best when you realize that the claude plugin will be
migrated to agent-plugins standard and therefore reusable beyond Claude."

Recorded: the dependency-direction objection dissolves once claude-checkup is
itself cross-agent. Home is `~/git/src/github.com/buvis/agent-skills`, reached
via braid. Two carried risks are listed under Risks.
