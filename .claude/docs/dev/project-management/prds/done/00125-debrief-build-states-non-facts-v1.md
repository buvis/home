# The debrief build knows what went wrong and the page states the opposite

Source: agoge product-QA run, `dev/local/audit-results/agoge-2026-08-17.md`, findings 9 and 10
(HIGH, accepted as one cluster), 14 (MEDIUM), 23 (MEDIUM), 35 (LOW) and 38 (LOW), each
accepted in the 2026-08-17 walkthrough. Found by judy and walter.

## Overview

### Problem Statement

`build.py` detects problems, prints them to stderr, and then hands the page a payload that
says the opposite. Five separate defects, all in the same skill:

1. **A correction that matched nothing is listed as applied.** `build.py` printed
   `WARN: correction 'Kubernetes' -> 'K8s' matched nothing` and set `applied: 0`; the Insights
   tab lists it under a heading reading "Cleanup applied — what was changed before anything
   was read out of this transcript", indistinguishable from the ones that worked except for a
   missing `(2×)`. `Insights.svelte:200` renders the count only `{#if fix.applied}`, and zero
   renders as nothing. The unreplaced word is still in the page.
2. **A build without extraction states "0 decisions" as a fact.** With no `extract.json`,
   `build.py` warned and set `extract = {}` (line 101) with no flag distinguishing "never ran"
   from "found nothing". The page shows `0 DECISIONS / 0 ACTIONS / 0 OPEN QUESTIONS` and "No
   decisions were extracted from this meeting", while the Transcript tab on the same page
   contains "Bob owns pagination, Carla writes the drop off analysis".
3. **A backslash in a correction kills the build** and leaves the old page on disk.
4. **The Insights tab renders a fully blank pane** when there is nothing to show, which is
   indistinguishable from the `each_key_duplicate` crash in PRD 00124.
5. **Two operator mistakes return raw tracebacks** where every other failure in the same
   script exits with a clean message.
6. **The transcript search box has no accessible name** and its result count is never
   announced.

Left alone: a reader is told their meeting had no decisions, or that a substitution happened
that did not. That is worse than an error, because it is actionable and wrong.

### Target Users

Whoever reads a debrief — usually not the person who built it, and a week later.

### Success Metrics

- A build whose extraction step did not run renders "the extraction step hasn't run", never
  `0 DECISIONS`. The sibling skill already words it this way.
- A correction with `applied: 0` renders visibly distinct from an applied one.
- A correction containing `C:\Temp` produces a page, not a `re.PatternError`.
- Clicking Insights on a debrief with no corrections renders text, not an empty pane.
- A truncated `extract.json` produces one line of message, not 16 lines of traceback.
- The search input has an accessible name and the result count is announced.

## Functional Decomposition

### Capability: the page can say what the build knew (findings 9 + 10)

The accepted option is the **warnings channel**: `build.py`'s warnings travel in the payload
and the page renders them. This is one mechanism for both findings, and it also carries the
page half of the portfolio finding in PRD 00126. An `extract_ran` flag rides the same payload
so the zero tiles can be replaced with "this step did not run" wording.

### Capability: valid input cannot crash the build (finding 14)

`pattern.subn(lambda _m: new, turn["text"])` — a callable replacement is used literally, which
removes the escape-interpretation class rather than the character that bit.

### Capability: absence looks like absence, not like a crash (findings 23, 35, 38)

A top-level `{:else}` empty state on Insights matching the sibling tabs; `sys.exit(f"…")` for
the truncated-extract and missing-`--out`-directory cases plus `mkdir(parents=True)` on the
`--out` parent; `aria-label` on the search input and `aria-live="polite"` on its counter.

## Structural Decomposition

### Module: skills/debrief-meeting/scripts/build.py

The warnings payload, the `extract_ran` flag, the callable replacement at line 64, the two
`sys.exit` messages, the `--out` parent `mkdir`.

### Module: skills/debrief-meeting/app/src/components/

`Insights.svelte` (the `{:else}` marker at :200, the top-level empty state at :186, the
warnings render), `Brief.svelte`, `Actions.svelte`, `Decisions.svelte` (the `extract_ran`
copy), `Transcript.svelte` (the two accessibility attributes).

## Implementation Phases

### Phase 1: the payload and the build (findings 9, 10, 14, 35)

1. Add the warnings channel and `extract_ran` to the payload; render both.
2. Switch the correction replacement to a callable.
3. Replace the two tracebacks with messages; `mkdir` the `--out` parent.

### Phase 2: the page's empty and accessible states (findings 23, 38)

4. Top-level `{:else}` on Insights, worded like Actions and Decisions.
5. `aria-label` on the search input, `aria-live="polite"` on the result counter.

*Acceptance:* each regression test below fails against current code before the fix.

## Test Strategy

Evidence carried verbatim from the run:

```
WARN: correction 'Kubernetes' -> 'K8s' matched nothing        (applied: 0, still listed as applied)
Replaced Kubernetes with K8s — house style          <- never happened
"Kubernetes" in pg.content() -> true
```

```
WARN: /tmp/judy1/extract.json not found — building the transcript view only
   page: 0 DECISIONS / 0 ACTIONS / 0 OPEN QUESTIONS
   transcript on the same page: "Bob owns pagination, Carla writes the drop off analysis."
```

```json
{"corrections":[{"from":"cluster","to":"C:\\Temp cluster","reason":"path"}]}
```
```
rc=1  File ".../build.py", line 64, in apply_corrections
    text, count = pattern.subn(new, turn["text"])
re.PatternError: bad escape \T at position 2
```

```
<main> innerHTML after clicking Insights:
"<!----> <!----><!----> <!----> <!----> <!----> <!----> <!----> <!----> <!----> <!----><!---->"
13 empty anchors, zero rendered elements, zero text, console clean
```

```
input: placeholder="Search the transcript", aria-label=null, <label for> lookup: false
page elements matching [aria-live], [role=status], [role=alert]: 0
```

## Risks

- **The warnings channel changes the payload shape.** Mitigation: it is additive; the page
  ignores an absent warnings key.
- **The callable replacement silently drops regex-group references** (`\1`) in corrections.
  Undocumented and probably unused, but it is a behaviour change with no warning.
- **`mkdir(parents=True)` on `--out` means a typo'd path succeeds** into a directory you did
  not mean, and you find the file later in the wrong place.
- **Per-site patches, not a pattern.** Three components in this app have now each learned the
  empty-state lesson separately; a shared `EmptyState` was considered and rejected as a
  refactor for a three-line problem.
