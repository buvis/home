# A repeated string renders a blank page in both single-file Svelte apps

Source: agoge product-QA run, `dev/local/audit-results/agoge-2026-08-17.md`, findings 1 and
2 (both CRITICAL), accepted as one cluster in the 2026-08-17 walkthrough. Found by judy,
driving both real pages in headless chromium.

## Overview

### Problem Statement

Both single-file HTML apps key `{#each}` blocks by the value itself, so any duplicate string
in the data makes Svelte throw `each_key_duplicate` and render nothing at all.

In **debrief-meeting**, five schema-valid `extract.json` inputs each produced a page with
zero body characters while `build.py` exited 0, printed `wrote debrief.html (82 kB)` and left
stderr empty. `SKILL.md:52` asks the model for "3-5 bullets a reader can act on", so two
similar bullets is ordinary LLM output, not abuse.

In **brief-portfolio**, duplicating one existing backlog PRD title made the PRDs tab render
nothing while its chip highlighted orange as though selected — the pane still showed the
previous view, byte-identical before and after the click.

Left alone, every debrief or dashboard whose data happens to repeat a string is a silent
blank page: intermittent, unattributable, and asserted as a success by the build. It voids
the entire output of the skill whenever it fires.

### Target Users

Anyone opening a built debrief or the portfolio dashboard — which is the operator, weekly.

### Success Metrics

- An extract with two identical `tldr` bullets renders a page with **two list items**, not
  zero body characters.
- A `data.json` with two backlog PRDs sharing a title renders the PRDs tab, and the tab's
  content changes when its chip is clicked.
- `rg '\{#each [^)]*\((?!.*\bi\b)' ` over both apps' components finds no value-keyed block —
  or, in plainer terms, no `{#each}` in either app is keyed by its own value.

## Functional Decomposition

### Capability: duplicate data renders, it does not blank the page

The accepted option is the **sweep**: find every value-keyed `{#each}` in both apps and key
by index instead. The two CRITICALs are one defect in two codebases, so fixing them
separately guarantees a third instance.

Index keys lose Svelte's move-detection on reorder. Neither app reorders — both render once
from a static payload — so that loss costs nothing here.

## Structural Decomposition

### Module: skills/debrief-meeting/app/src/components/

`Brief.svelte` lines 35, 43, 50, 77, 92 are the known sites. Sweep the whole component
directory; judy drove only the Brief and Insights tabs.

### Module: skills/brief-portfolio/app/src/components/

`Prds.svelte:53` (`{#each p.backlog as t (t)}`) and `RepoDetail.svelte:201` are the known
sites. Sweep the whole directory for the same reason.

## Implementation Phases

### Phase 1: Sweep and key by index

1. Enumerate every `{#each}` in both apps and classify each key expression as value-keyed,
   index-keyed or composite. Record the list in the commit message — it is the evidence that
   the sweep was a sweep.
2. Key the value-keyed ones by index.
3. Add the regression tests below.

*Acceptance:* both regression tests fail against the current code — demonstrate that, do not
assert it — and the built pages render for duplicate-bearing input.

## Test Strategy

The evidence is already a reproduction. Carry it verbatim:

```
| extract.json                                                        | body chars | console                          |
| {"tldr": ["Ship pagination this week.","Ship pagination this week."]}|      0     | pageerror: e/each_key_duplicate  |
| {"summary": "Same paragraph.\n\nSame paragraph."}                    |      0     | same                             |
| {"agenda": [{"title":"Billing"},{"title":"Billing"}]}                |      0     | same                             |
| two distinct bullets (control)                                       |    277     | []                               |
```

```
pageerror: https://svelte.dev/e/each_key_duplicate
body_chars_before_click: 1146
body_chars_after_PRDs_click: 1146      <- byte-identical
```

- `app/smoke.test.js` mounting `Brief` with `tldr: ['x','x']`, asserting two `<li>`.
- The portfolio equivalent: two backlog entries sharing a title, assert the PRDs pane renders
  non-empty content after the click.

## Risks

- **The sweep touches components no lane drove**, so part of the change ships unverified.
  Mitigation: the enumeration in phase 1 is per-site and reviewable; the two driven pages
  keep their end-to-end checks.
- **A sixth `{#each}` added later reintroduces the class.** Mitigation: the two regression
  tests fail loudly for the components they cover; a lint rule is out of scope here.
