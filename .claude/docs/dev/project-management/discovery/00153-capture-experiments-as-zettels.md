# Discovery: Capture Playground Experiments as Zettels

## Classification

Depth: standard | Date: 2026-08-27 | Status: elicitation complete
Elicited from the 2026-08-26 seed of the same number. Original source:
`discovery/inbox/skill-ideas-2026-07-14.md` (2026-07-14 transcript sweep; trashed
2026-08-26 once split into per-idea docs).

## Problem

Playground and hardware sessions burn real tokens and produce real knowledge -
what worked, what the sensor actually read, which dead end cost an hour - and
none of it lands anywhere durable. The next session re-derives it.

## Requirements

### Must have

1. **Skill `capture-experiment`** (verb-led), invoked on request only. Never
   auto-triggered, no required field beyond a title.
2. **Harvest from the live conversation**, not the transcript file. The skill
   writes from what it has: the commands run, the readings seen, the dead ends
   taken.
3. **Frame as hypothesis -> setup -> observations -> verdict**, with dead ends
   recorded as first-class content rather than omitted.
4. **Readings summarized in the note**: the value that surprised, the range, the
   one that disagreed with the datasheet. No raw serial dumps.
5. **One note per session**, written to `~/bim/inbox/automated/capture-experiment/`
   with `processed: false`. Atomizing into per-hypothesis zettels happens at
   inbox triage, not at capture time.
6. **Vault conventions, not new ones**: `YYYYMMDDHHmmss` id as filename, and
   `title` / `date` (ISO 8601) / `tags` (three) / `type: experiment-log` /
   `publish: false` / `processed: false` frontmatter, matching what
   `digest-github-repo` already writes and varying only `type` (value pinned at
   the 2026-08-28 review; the vault has no experiment-like type to reuse).
7. **Follow-ups as checkboxes** in the note, naming `/spike` or `create-prd`
   where one applies.

### Nice to have

- A backlink line naming the repo and commit the session worked at, so the note
  can be re-anchored to code later.

### Out of scope

- Auto-triggering at session end. Ceremony kills play; this is the seed's own top
  risk and the reason the skill is request-only.
- Transcript parsing.
- Atomizing notes into per-hypothesis zettels - that is a triage-time job.
- **verify-hardware** (flash + serial-assert harness for espx work), the adjacent
  idea cut in the same 2026-07-14 sweep as too niche. This skill keeps the
  knowledge half of it.

## Constraints

- The vault is `~/bim/`, a hard anchor with no fallback: `zettelkasten/`,
  `inbox/automated/<skill>/`, `reference/`, `media-lib/`, `calendar/`, `system/`.
  The `mkdocs-zettelkasten` repo named in the seed is the **site generator**, not
  the vault, and nothing should be written into it.
- Notes land in the inbox, never straight into `~/bim/zettelkasten/`. Tracker
  files reach the main vault only after triage.
- Harvesting from context means the note is bounded by what survived compaction;
  the skill must say so in the note rather than imply completeness.

## Codebase Context

- **Write side is proven**: `digest-github-repo` already emits zettel-format
  output into `~/bim/inbox/automated/digest-github-repo/`, generates the
  `YYYYMMDDHHmmss` id with `date +%Y%m%d%H%M%S`, and pins the frontmatter field
  set. Reuse that shape; do not invent a second one.
- **Vault layout, verified 2026-08-27**: `~/bim/` holds `calendar`, `inbox`,
  `media-lib`, `reference`, `system`, `zettelkasten`; `inbox/automated/` holds
  `digest-github-repo` and `generated-notes`.
- **The transcript trap**: discovery 00147 measured that naive `type=user` rows
  over-count real user turns ~7x, because skill bodies, hook output, task
  notifications and agent prompts all arrive with `role=user`. Only the schema
  fields (`isMeta`, `promptSource`, `origin.kind`) separate them. Harvesting from
  context avoids this class entirely.
- **Hand-offs**: `spike` (throwaway build), `create-prd` (when a finding earns a
  PRD).

## Success Criteria

- A session ends with one file at
  `~/bim/inbox/automated/capture-experiment/{YYYYMMDDHHmmss}.md`, whose
  frontmatter carries all six fields and whose filename matches the id.
- The note contains a hypothesis, a verdict, and at least one dead end when the
  session had one - a note with no dead end in a session that had three is a
  defect.
- Every reading in the note is a summarized value with units, not a pasted
  stream; the note contains no raw serial capture.
- The skill fires only when asked. No hook, no trigger on session end, provable
  by its absence from `dispatch.py` `ROUTES`.
- Follow-ups appear as unchecked boxes naming the skill that would do them.
- The note states the window it covers (first and last event it could see), so
  a compacted session reads as partial; a note without a window line is a
  defect.

## Risks

- **Ceremony kills play**: request-only, one required field, and the note is
  written in one pass with no interview. If a capture ever takes more than a
  couple of minutes, the skill is wrong and should be cut back.
- **Context loss on long sessions**: harvesting from conversation means a
  compacted session has already lost its early dead ends. Mitigation: the note
  states what window it covers, so a thin note reads as thin rather than as
  complete.
- **Inbox never triaged**: the whole atomize-later design rests on triage
  happening. Mitigation: `processed: false` makes the backlog countable, so an
  untriaged pile is visible rather than silent.
- **A second frontmatter dialect**: if the skill invents fields,
  vault-wide queries break. Mitigation: copy `digest-github-repo`'s field set
  verbatim and vary only `type`.

## Open Questions

- Should the note record cost (tokens, wall clock) for the session? The
  2026-07-14 measurement that motivated this idea is stale, and costs.jsonl rows
  are cumulative per session id, so a naive sum overstates.
- Does the espx hardware sketchbook want its own tag convention, or do three free
  tags suffice?

## Evidence (2026-07-14)

playground was the #2 token sink of the fortnight (relcost 3,734 of 25,971,
ahead of ddb), including hardware work in the espx sketchbook. The zettel
infrastructure already exists and `digest-github-repo` already emits
zettel-format output, so the write side is proven.

## Freshness check 2026-08-26

- Still unbuilt: no `capture-experiment` skill anywhere.
- The source still exists (`tbouska/playground`) and so does the vault
  (`~/bim/`); `buvis/mkdocs-zettelkasten` is the site generator, not a
  dependency.
- `spike` and `digest-github-repo` are both installed and current.
- The 2026-07-14 cost share is a stale number; re-measure before sizing the PRD,
  since the model mix has changed twice since.

## Discovery Log

### Q1: What should the skill harvest the experiment from?

**Answer**: **The live conversation**, no transcript parsing. Zero parsing, no
schema to track, and it sidesteps the trap discovery 00147 measured. Accepted:
a session that compacted mid-way has already lost its early dead ends, and the
note can only cover what remains. Rejected: parsing the transcript JSONL (a
parser to maintain against a schema that has already shifted, for a note a human
reviews anyway), a two-path hybrid (two failure modes, and the flag only gets
used after a loss), and interviewing the operator (ceremony at the exact moment
play ends).

### Q2: One zettel per session, or one per hypothesis?

**Answer**: **One per session into the inbox**, atomized at triage. It stays out
of the way when play ends and reuses the `processed: false` convention the vault
already has. Accepted: an untriaged note is a diary entry the next session will
not find, so the design depends on triage happening. Rejected: atomic-per-
hypothesis at capture time (forces structure onto sessions that had one fuzzy
question and three accidents), straight into `~/bim/zettelkasten/` (nothing marks
unatomized notes as needing work), and session-plus-child-notes (a judgement call
per finding, made while tired).

### Q3: Where do hardware readings go - in the note, or a linked data file?

**Answer**: **In the note, summarized.** A note you can reread is the only note
worth writing, and the summarized reading is the knowledge; the raw stream is
just evidence. Accepted: re-analysis means repeating the run. Rejected: a linked
raw capture in `media-lib` (a second artifact and a link that breaks silently), a
size threshold (a number picked with no data), and verdict-only (discards exactly
what the seed set out to keep).

### Inferred (not asked - answered by the scan or the seed)

- Destination corrected: the vault is `~/bim/`, not the `mkdocs-zettelkasten`
  repo, which is the site generator. The seed named the wrong target.
- Frontmatter and id scheme: copy `digest-github-repo`'s, varying only `type`.
- Invocation: request-only, stated in the seed and unchanged.
- Follow-ups: rendered as checkboxes, matching the digest notes already in the
  inbox.
