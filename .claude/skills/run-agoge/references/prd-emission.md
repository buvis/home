# PRD emission

How an accepted finding becomes a backlog PRD. Read this at step 9, after a
human has accepted something, and never before.

## The gate

**Only explicit per-finding acceptance emits anything.** Deferred and rejected
findings stay in the report and nowhere else. An unattended run emits nothing at
all, whatever it found — a machine that files its own findings as work has
approved them on the operator's behalf, which is the one thing this pack must
not do.

One PRD per accepted finding, or one per cluster the human explicitly approved
as a cluster. Never bundle on your own initiative: the human accepted findings,
not a grouping.

## Claiming the number

Numbers are claimed, not chosen:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/allocate_prd_number.py" /absolute/target/repo <kebab-slug>
```

It scans every `dev/local/prds/` lifecycle directory plus `dev/local/discovery/`,
creates an **empty** file at the next free number with an exclusive create, and
prints the path. Write the body into that path.

Do not compute the number yourself and do not re-scan afterwards. The exclusive
create is what makes two concurrent writers impossible to reconcile wrongly: one
of them gets the name, the other moves on. A scan-then-write has a window; this
does not.

The slug comes from the finding's title: lowercase, words joined by hyphens, no
articles, five words at most. `A book added through the form never appears in the
catalogue` becomes `added-book-missing-from-catalogue`.

## Mapping the packet onto the template

The PRD follows the same template `/create-prd` writes, filled from the packet:

| PRD section | Comes from |
|---|---|
| Title | The finding's `title`, as a problem statement, not a solution |
| Problem Statement | The packet's *what* plus its *if unchanged* — the user-visible symptom and the cost of leaving it |
| Target Users | Who hits the symptom. The finding says what a user experiences; name them |
| Success Metrics | The observation that would flip. "`GET /api/books` returns the same count the catalogue renders", not "fix the cache" |
| Functional Decomposition | The packet's **recommended option**, as behaviour. If the human chose a different option, that one |
| Structural Decomposition | The finding's `paths` — the files that must change |
| Implementation Phases | One phase unless the chosen option names more. Most findings are one change |
| Test Strategy | The finding's `evidence`, restated as the regression check. This is the highest-value transfer in the whole mapping: the evidence is a reproduction someone already ran |
| Risks | The chosen option's stated drawback, and what the change itself could break |

Carry the evidence **verbatim**, in a fenced block, under Test Strategy. A PRD
that says "the API returns an empty list" is a claim; one that carries the
`curl` and its two-byte body is a reproduction the implementer can run before
writing a line.

Name the run in the PRD body: the report path and its date. Whoever picks the
PRD up should be able to find where it came from.

## After writing

State in the report's minutes, on the finding's line, that a PRD was emitted and
under which number. A finding whose minutes say "accepted" with no number is a
finding that was lost between the walkthrough and the backlog.

Emitted PRDs are ordinary backlog PRDs from that moment on. They get reviewed by
`/review-prd-backlog` like any other, and nothing about their origin exempts
them from it.
