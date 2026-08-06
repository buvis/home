---
inclusion: manual
---

# Debrief Meeting

Turn a raw meeting transcript into `<transcript>-debrief/debrief.html`: one
self-contained SPA with the agenda, notes, action items, decisions rendered as
ADRs, participants and their speaking share, a clickable timeline, and the
cleaned transcript. Every extracted item carries the timecode it came from, and
clicking it jumps to that moment in the transcript.

Ask for the transcript path if the user has not given one.

## Dependencies

- `python3` on PATH (stdlib only - DOCX is unzipped with `zipfile`). On Windows
  the command is usually `python`.
- `~/.kiro/debrief-meeting/assets/template.html` - the pre-built SPA. Missing it
  means `build.py` exits; copy the folder again from the source repo.
- Privacy: the debrief lands next to the input transcript and contains the whole
  meeting. Treat it as confidential; never commit it to a repo.

## Workflow

### 1. Normalize (deterministic)

```bash
python3 ~/.kiro/debrief-meeting/scripts/parse.py /path/to/transcript.vtt
```

Reads `.vtt`, `.srt`, `.docx` and plain text (including the Teams "copy
transcript" layout and `[00:12:34] Name: text`). Writes
`<transcript>-debrief/transcript.json`. Override the location with `--out DIR`.

It canonicalises speaker names (`Bouska, Tomas` / `T. Bouska` / `Tomas Bouska
(Guest)` collapse into one person), drops the growing duplicate lines live
captions emit, merges cues into turns, and computes speaking stats, the
turn-taking matrix and per-slot participation. Report any `WARN` lines to the
user verbatim - "no timecodes", "only one speaker" and "unattributed speech"
all mean the page will be thinner than usual.

### 2. Correct and extract (model step)

Read `transcript.json` - not the raw file; it is smaller and already cleaned -
and write `extract.json` next to it. Every field is optional: the page hides
sections it has no data for. **Omit a key rather than inventing content.**

```json
{
  "meta": {"title": "", "date": "2026-08-06", "platform": "Teams", "type": "design review",
           "purpose": "one line", "attendees_not_speaking": ["Name"]},
  "tldr": ["3-5 bullets a reader can act on without the rest"],
  "summary": "paragraphs separated by blank lines",
  "agenda": [{"title": "", "planned": true, "t": 0, "end": 300,
              "coverage": "full|partial|skipped", "note": ""}],
  "topics": [{"id": "t1", "title": "", "t": 0, "end": 300, "summary": "", "notes": [""]}],
  "decisions": [{"id": "d1", "title": "", "t": 0, "status": "made|deferred|blocked|revisit",
                 "decision": "", "decider": "", "context": "",
                 "alternatives": [{"option": "", "why_not": ""}], "consequences": [""],
                 "confidence": "high|medium|low", "quote": ""}],
  "actions": [{"id": "a1", "action": "", "assignee": "", "assignee_confidence": "high|medium|low",
               "due": "2026-08-13", "due_raw": "next Friday", "t": 0,
               "priority": "high|normal|low", "status": "new|in-flight|blocked",
               "blocked_by": "", "quote": "", "confidence": "high|medium|low"}],
  "questions": [{"q": "", "asked_by": "", "t": 0, "answered": false, "answer": "", "owner": ""}],
  "risks": [{"risk": "", "raised_by": "", "t": 0, "severity": "high|medium|low",
             "mitigation": "", "addressed": false}],
  "blockers": [{"what": "", "owner": "", "t": 0, "depends_on": ""}],
  "assumptions": [{"assumption": "", "by": "", "t": 0, "validated": false}],
  "disagreements": [{"topic": "", "positions": [{"who": "", "stance": ""}], "t": 0,
                     "resolved": true, "resolution": ""}],
  "entities": {"people": [{"name": "", "role": "", "org": ""}], "teams": [""], "systems": [""],
               "tools": [""], "vendors": [""], "documents": [""], "tickets": [""], "links": [""],
               "metrics": [{"label": "", "value": "", "t": 0}]},
  "glossary": [{"term": "", "expansion": "", "definition": "", "t": 0}],
  "quotes": [{"text": "", "who": "", "t": 0, "why": ""}],
  "followups": [{"what": "", "when": "", "who": ""}],
  "quality": {"on_topic_ratio": 0.8, "tangents": [{"t": 0, "what": ""}], "notes": [""]},
  "dynamics": ["observations about who drove, who went quiet, who was talked over"],
  "email": "draft follow-up email, plain text",
  "corrections": [{"from": "sequel server", "to": "SQL Server", "reason": "ASR", "turn": 12}]
}
```

**Corrections come first.** `corrections` are case-insensitive whole-word
replacements applied across every turn (add `"turn": N` to limit one to a single
turn). Use them only where the transcript is provably wrong: mangled product
and person names, acronyms, numbers contradicted elsewhere in the meeting.
Never rewrite meaning, never tidy grammar - the original wording stays one
toggle away on the page, and every replacement is listed under "Cleanup
applied". `build.py` warns when a correction matches nothing, which usually
means you guessed the misspelling.

Rules for everything else:

- **Ground every item in a timecode.** `t` is seconds from `transcript.json`.
  An item without a `t` still renders but loses its link back to the evidence.
- **Distinguish a commitment from a musing.** "I will talk to reporting before
  Friday" is an action. "Someone should probably look at that" is not - it is
  an open question or a risk.
- **Resolve relative dates** against `meta.date` and put the result in `due`,
  keeping the words actually spoken in `due_raw`.
- **Say when you are unsure.** `confidence: "low"` renders as an "unsure" badge.
  That is far better than a confident wrong assignee.
- **A decision needs a decider or an explicit non-decision.** If the room drifted
  without concluding, that is `status: "deferred"`, not a made decision.
- **Alternatives are what makes an ADR worth having.** Record the option that
  lost and why; an ADR with no rejected option is just a note.
- **Agenda coverage is a finding.** A planned item that never got discussed
  (`coverage: "skipped"`) is one of the most useful things on the page.
- **Prefer fewer, sharper items.** Twelve vague actions are worth less than four
  real ones.

Also worth extracting when the meeting has it: unvalidated assumptions stated as
fact, positions that never converged, jargon a newcomer would not follow,
numbers and estimates, tickets and links mentioned aloud, praise worth
repeating, and anything that needs escalating.

### 3. Build

```bash
python3 ~/.kiro/debrief-meeting/scripts/build.py /path/to/transcript-debrief
```

Applies the corrections, injects `{transcript, extract}` into the template and
writes `debrief.html` beside the JSON (`--out FILE` to redirect). It works
without `extract.json` - you get the transcript view only, and it says so. It
also warns about unknown top-level keys in `extract.json`, which is how a typo
like `action_items` gets caught instead of silently rendering nothing.

Report the written path and let the user open it. The file needs no server: it
is one HTML file with everything inlined, so it opens straight off disk.

## What the page shows

Brief (glance tiles, TL;DR, notes, agenda coverage, open questions, follow-up
email) · Timeline (topic gantt, decision/action/question/risk pins,
who-is-talking strip) · Actions (filter by owner, tick off, copy markdown or
CSV) · Decisions (each expandable into a copyable ADR) · People (speaking share,
pace, questions, interruptions, turn-taking matrix) · Transcript (search, filter
by speaker, original-wording toggle) · Insights (risks, blockers, assumptions,
disagreements, quotes, numbers, jargon, cleanup log).
