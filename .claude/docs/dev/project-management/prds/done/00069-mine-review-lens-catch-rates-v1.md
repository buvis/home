---
design: skip
catchup: skip
---

# Mine per-lens review catch rates from the archive

> Source: 2026-07-14 setup-review walkthrough (finding 8, "mine first, decide
> after"). The always-all-lenses rule in AGENTS.md stays untouched; this PRD
> only makes it face its own data. Full review:
> `dev/local/audit-results/2026-07-14-claude-setup-brutal-review.md` (S3).
>
> Renumbered 00083 → 00069 on 2026-07-18 (speed front-load, hole reuse
> approved by user). Phase 2 unparks the state-machine trilogy head
> (00051/00052) per the same decision - rationale in
> `dev/local/audit-results/2026-07-18-autopilot-loop-speed.md`.

## Overview

### Problem Statement

The review phase runs every lens on every cycle by standing rule, at the
setup's most expensive recurring price point, and the rule has never been
evaluated against the archive it generates: per-lens findings live in
`dev/local/reviews/*.md`, durable verdicts in
`dev/local/autopilot/ledger/review-verdicts.jsonl`, and outcomes in done PRDs
and rework commits. Nobody has computed which lenses uniquely catch what.

### Target Users

Solo operator deciding future review-depth policy with evidence.

### Success Metrics

- A report in `dev/local/audit-results/` tabulating, per lens (Alice, Blake,
  Bob, Carl, Eve where present): findings raised, findings no other lens
  raised (unique catches), unique catches that survived rework (true
  positives), by change class (code vs docs-only vs config).
- Every number carries its denominator (PRDs and cycles counted); thin-data
  classes are marked "insufficient evidence", never extrapolated.
- The report ends with a decision-ready options block (keep / tier by class /
  cheapen lenses) WITHOUT deciding - the decision is the operator's.

## Functional Decomposition

### Capability: Archive mining

#### Feature: Parse the review corpus
- **Description**: extract per-lens findings and verdicts from review files and
  the ledger.
- **Inputs**: `dev/local/reviews/*.md` (live + `.trash` batches still within
  the retention window), `dev/local/autopilot/ledger/review-verdicts.jsonl`,
  `dev/local/prds/done/*.md`. Premise (re-check at execution): the reviewer
  frontmatter contract (`reviewers:` + `Verdict:`/`Tests:` lines, PRD 00016)
  holds for the files parsed; files predating the contract are counted in a
  "pre-contract, skipped" bucket, never force-parsed.
- **Outputs**: `dev/local/tmp/00069-lens-findings.json`.
- **Behavior**: deterministic parser (code, not model); unparseable files are
  listed by name in the report, not silently dropped.

#### Feature: Attribute uniqueness and survival
- **Description**: mark findings unique to one lens and check survival
  (finding led to a rework commit or an accepted fix rather than being
  dismissed).
- **Inputs**: the findings JSON; rework commit ranges from done PRDs'
  `work_start_sha` records where present.
- **Outputs**: per-lens table rows with unique-catch and survival counts.
- **Behavior**: matching findings across lenses uses normalized text overlap;
  borderline matches count as SHARED (biases against uniqueness, so unique
  catches are a floor, stated in the report).

### Capability: Reporting

#### Feature: Decision-ready report
- **Description**: render the table + methodology + limitations to
  audit-results.
- **Inputs**: attributed rows.
- **Outputs**: `dev/local/audit-results/2026-XX-XX-review-lens-catch-rates.md`
  ending with a verbatim how-to-proceed block.
- **Behavior**: states the archive's model/prompt era explicitly (conclusions
  age); no recommendation is baked in.

## Structural Decomposition

### Repository Structure

```
~/.claude/dev/local/tmp/00069-mine-lenses.py   # Maps to: Archive mining (ephemeral script)
~/.claude/dev/local/tmp/00069-lens-findings.json  # Maps to: Parse the review corpus
~/.claude/dev/local/audit-results/             # Maps to: Decision-ready report
```

### Module: miner script
- **Maps to capability**: Archive mining
- **Responsibility**: parse, attribute, count; stdlib only
- **Exports**: CLI writing the JSON + printing the table

### Module: report
- **Maps to capability**: Reporting
- **Responsibility**: the durable artifact; script is ephemeral
- **Exports**: the audit-results markdown

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **miner script**: pure read of the archive

### Core Layer (Phase 1)
- **report**: Depends on [miner script]

### Integration Layer (Phase 2)
- **queue continuation**: Depends on [report] - unparks 00051/00052 (a lifecycle move, not code)

## Implementation Phases

### Phase 0: Foundation
**Goal**: Trustworthy per-lens numbers.

**Tasks**:
- [ ] Miner script + parse premise re-check (no deps) - Acceptance: JSON
  written; canary: the 00064 review set (known 3 cycles + audit:
  00064-review-1/2/3 + audit; verified present 2026-07-18 - no 00061 set
  exists) parses with the expected reviewer roster; unparseable files listed.

**Exit Criteria**: findings JSON with stated coverage.

### Phase 1: Core
**Goal**: The report exists.

**Tasks**:
- [ ] Attribution + report (depends on: Phase 0) - Acceptance: report in
  audit-results with per-lens/per-class table, denominators, floor-bias note,
  era note, and a how-to-proceed block; no policy change made.

**Exit Criteria**: Success Metrics all verifiably true.

### Phase 2: Integration
**Goal**: Queue continuation - the trilogy head enters the drain queue (user
decision 2026-07-18: pull 00051/00052 forward; this PRD is the last
front-loaded item, so the unpark rides here).

**Tasks**:
- [ ] Unpark the state-machine trilogy head (depends on: Phase 1) -
  Acceptance: `mv` `dev/local/prds/hold/00051-autopilot-state-machine-core-v1.md`
  and `dev/local/prds/hold/00052-autopilot-orchestrator-loop-cutover-v1.md` to
  `dev/local/prds/backlog/` under the verified-move invariant (confirm arrival,
  keep prefixes); 00053 and 00060 stay in hold/ untouched.

**Exit Criteria**: both files present in backlog/, absent from hold/; hold/
still contains 00053 and 00060.

## Test Strategy

### Critical Scenarios
- **Happy path**: 00064's review set → Expected: parsed roster matches its
  files, counts plausible.
- **Edge case**: a pre-contract review file → Expected: counted as skipped,
  named in the report.
- **Error case**: ledger missing → Expected: report proceeds from review files
  alone and says so.

## Risks

- **Thin data over-interpreted**: denominators everywhere + "insufficient
  evidence" marking; five PRDs cannot overturn a safety rule alone.
- **Text-overlap misattribution**: borderline matches count as shared;
  uniqueness is a floor by construction.
