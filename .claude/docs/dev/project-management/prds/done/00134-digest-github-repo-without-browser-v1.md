---
consensus_engine: shadow
---

# digest-github-repo cannot run: it requires a browser MCP server that resolves nowhere

Source: agoge product-QA run, `dev/local/audit-results/agoge-2026-08-17.md`, finding 34,
raised by wendy as `unverified` and **upgraded to `verified`** on 2026-08-17 when the operator
ran `/mcp`. Decision taken the same day: drop the browser dependency rather than restore it.

## Overview

### Problem Statement

`agents/chrome-browser.md:4-5` declares `mcpServers: [claude-in-chrome]`, and
`skills/digest-github-repo/SKILL.md:15` makes it a hard stop: *"Activity collection is
browser-driven; without it the skill cannot gather repo activity and must stop."*

That server resolves nowhere. Six independent checks agree:

- `/mcp` in an interactive session does not list it.
- The registered `chrome-browser` agent's tool roster is `Bash, Read, Write, Edit, WebFetch,
  ToolSearch` — no `mcp__claude-in-chrome__*` tool.
- The session's deferred-tool list carries every other server's tools and no chrome one.
- Neither `~/.claude/.mcp.json` nor `~/.mcp.json` exists.
- The `mcpServers` key is absent from `~/.claude.json`, and `claudeInChromeDefaultEnabled` is
  `false`.
- `claude-in-chrome` is absent from `claudeAiMcpEverConnected`.

So the skill is dead by its own declaration. It worked once —
`instincts/projects/bc25f74b0acf/observations.jsonl:53` records
`mcp__claude-in-chrome__tabs_context_mcp` on 2026-07-18 — which is the point: the skill's only
collection path depends on an ambient, extension-injected server with no configuration source in
the repo, and it disappeared silently.

The data the skill wants needs no browser. Every step in Step 3 is a GitHub API call wearing a
web page's clothes: commits, the PR behind a commit, a repo's description and star count, open
PRs, issues. `skills/brief-portfolio/scripts/collect.py` already collects the same classes of
data over `gh`.

### Target Users

Whoever runs `/digest-github-repo` on an awesome-list or a general repo — today they get a skill
that stops at step 3, or worse, one that silently collects nothing.

### Success Metrics

- `rg 'claude-in-chrome|browser tools' skills/digest-github-repo/` returns **0 hits**.
- A digest of a real awesome-list repo produces items with owner/repo, short name, description
  and star count, on a machine where no browser MCP server exists.
- A digest in `activity-digest` mode produces PRs with status, issues with status, and commit
  subjects, with the `last_check` cutoff respected.
- The run reports how many API calls it made, so the cost is visible rather than discovered.

## Functional Decomposition

### Capability: collection over `gh`, not over rendered pages

Replace each browser step with its API equivalent. The mapping is one-to-one, which is what
makes this a rewrite of one step rather than of the skill:

| Current browser step | Replacement |
|---|---|
| Visit `/commits/main`, parse commits after `last_check` | `gh api repos/O/R/commits --paginate` with a `since` parameter; fall back to `master` |
| Fetch the PR page behind a matching commit | `gh api` on the commit's associated PRs |
| Item's README tagline and star count | `gh api repos/O/R` → `description`, `stargazers_count` |
| Visit `/pulls?q=is:pr+is:open+sort:updated-desc` | `gh pr list --state open --json number,title,body,updatedAt` |
| Visit `/pulls?q=is:pr+sort:updated-desc` | `gh pr list --state all --json number,title,state,updatedAt` |
| Visit `/issues?q=is:issue+sort:updated-desc` | `gh issue list --state all --json number,title,state,updatedAt` |
| `.markdown-title` CSS extraction | deleted — JSON has clean titles |

Both modes keep their current semantics, including the `commit_pattern` regex match, the
`also_check_prs` open-PR pass, the accepted-versus-proposed distinction, and the dedup list
built from `- [ ]` / `- [x]` / `- [-]` lines.

### Capability: the skill stops claiming a dependency it does not have

`SKILL.md:15`'s hard-stop line and the `mcpServers` key in `agents/chrome-browser.md` both go.
`chrome-browser` itself stays — it is a general browser-automation agent used elsewhere; only
`digest-github-repo`'s dependency on it is removed.

## Structural Decomposition

- `skills/digest-github-repo/SKILL.md` — line 15 (the dependency and hard stop), Step 3
  (lines 103-146), any downstream step that assumes page-shaped data
- `skills/digest-github-repo/references/` — check for browser instructions carried there
- `agents/chrome-browser.md:4-5` — the `mcpServers` declaration, **only if** nothing else in the
  tree relies on it resolving; verify with a sweep before editing

## Implementation Phases

### Phase 1: replace Step 3

1. Rewrite Step 3 for both modes against the mapping table above, with explicit pagination
   bounded by `last_check`.
2. Delete line 15's dependency and hard stop; delete the `.markdown-title` instruction.
3. Sweep the skill and its references for any remaining browser assumption.

### Phase 2: prove it on a real repo

4. Run both modes against a real repo with no browser server present, and record the output plus
   the API-call count in the PRD's Decision Log.

*Acceptance:* both modes produce a digest on this machine as it stands today. That is the whole
bar — the skill currently cannot.

## Test Strategy

The evidence is the reproduction: the skill's declared prerequisite is absent, so *any*
successful run is the regression test.

```
/mcp -> claude-in-chrome not listed
chrome-browser agent tools: Bash, Read, Write, Edit, WebFetch, ToolSearch   (no mcp__claude-in-chrome__*)
$ ls /Users/bob/.claude/.mcp.json /Users/bob/.mcp.json    -> No such file (both)
$ jq -r '.mcpServers | keys[]' /Users/bob/.claude.json    -> key absent
$ jq -r '.claudeInChromeDefaultEnabled' /Users/bob/.claude.json   -> false
$ jq -r '.cachedChromeExtensionInstalled' ...             -> true
instincts/projects/bc25f74b0acf/observations.jsonl:53 -> mcp__claude-in-chrome__tabs_context_mcp (2026-07-18)
```

- A `gh`-stub test per mode asserting the collection step issues the expected calls and respects
  the `last_check` cutoff.
- One live smoke run per mode, output recorded.

## Risks

- **Something the rendered page gave may not be in the API**: a discussion body rendered by JS,
  or a list entry that only exists in prose on the page. If a mode loses information, say so in
  the Decision Log rather than shipping a quieter digest — that is the failure this whole agoge
  run kept finding.
- **API-call volume.** Paginating commits, PRs and issues over a large repo is many calls, and
  agoge finding 30 showed how quickly that adds up (~184 per portfolio run). Bound the pagination
  by `last_check` and report the count.
- **`gh` auth failure must not read as "no activity."** Agoge finding 15 is exactly that bug in
  the sibling skill: a total `gh` failure written as an empty result. Fail loudly here from the
  start.
- **Editing `agents/chrome-browser.md`** could break another consumer of that agent. Sweep first;
  if anything else declares the server, leave the agent alone and change only the skill.

## Decision Log

### 2026-08-21 — Live proof runs (Phase 2), no browser MCP server present on this machine

Ran the rewritten skill by hand, executing every documented `gh` command via Bash (no
simulation), against the three real registered repos in `~/bim/inbox/automated/digest-github-repo/repos.yaml`.
No run hit a run-level abort; `gh auth status` succeeded all three times. All three output files
were re-read from disk after writing to confirm they match what's summarized here.

**Run 1 — `hesreallyhim/awesome-claude-code`, curated-list mode.**
`gh calls made: 3` (auth status, default-branch lookup, one commits page). Only 3 commits landed
on `main` since `last_check` (2026-08-21, i.e. today — an earlier same-day run had already
advanced it), all automated `chore: update repo ticker data and SVGs [skip ci]` commits; none
matched `commit_pattern` (`^Add resource: .+ \(#(\d+)\)$`), so 0 accepted items, no
`commits/{sha}/pulls` or item-metadata calls needed. `also_check_prs` isn't set for this repo, so
no open-PR pass ran. Fidelity/pattern-drift note: the ticker commits also didn't match either
`ignore_patterns` entry — the live commit title now carries an `and SVGs [skip ci]` suffix the
anchored `^chore: update repo ticker data$` regex no longer covers. Output:
`~/bim/inbox/automated/digest-github-repo/20260821091609.md` ("no new activity", verified on
disk). `last_check` unchanged (already today).

**Run 2 — `alebcay/awesome-shell`, curated-list mode, `also_check_prs: true`.**
`gh calls made: 5` (auth status, default-branch lookup, one commits page [0 results], and two
`gh pr list` invocations — the first mistakenly fetched only a count, the second the full
`number,title,body,updatedAt` payload; both were real calls and both are counted). 0 commits on
`master` since `last_check` (2026-08-21). Open-PR pass exercised specifically: `gh pr list`
returned 100 open PRs (the documented soft cap), but none had `updatedAt` after `last_check` —
the most recently updated open PR (#738) was last touched 2026-08-19, two days before the
cutoff — so 0 items qualified and the "Community Suggestions (Open PRs)" section was correctly
omitted per the template's conditional-inclusion rule (never fabricated to force content into
that section). Fidelity/behavior observation: `--search "sort:updated-desc"` was not strictly
honored by `gh pr list` — PR #570 (`updatedAt` 2026-08-03) appeared out of order between two
PRs updated in March 2026, which didn't change this run's outcome but would matter for any
client that stops paginating early based on sort order. Output:
`~/bim/inbox/automated/digest-github-repo/20260821091736.md` ("no new activity", verified on
disk). `last_check` unchanged (already today).

**Run 3 — `obra/superpowers`, activity-digest mode.**
`gh calls made: 6` (auth status, default-branch lookup, one PR Search API page, one issue Search
API page, one since-filtered commits page [0 results], plus one off-script sanity-check call —
`gh api repos/obra/superpowers/commits?sha=main&per_page=3` with no `since` filter — made to
confirm the surprising 0-commits result wasn't a `since`-filter bug rather than skill-documented
flow). Both Search API calls stopped after page 1: each page's oldest item already predated
`last_check` (2026-08-16), so the stop condition fired correctly with no wasted pages. Result: 23
PRs and 95 issues with `updated_at` strictly after `last_check` (none on/before it), 0 commits on
`main` in the window. Digest grouped the 118 items into 6 thematic clusters (Windows/WSL
compatibility fixes, SDD/TDD workflow correctness, new AI-harness support, planning-workflow
features, community/maintenance, infrastructure) rather than listing each individually, per the
activity-digest template's cluster convention. Notable finding surfaced in the digest, not
hidden: two clustered timestamp batches (2026-08-19T01:03-02:51 and
2026-08-18T18:28-23:46) account for most of the 95 "updated" issues — a maintainer backlog
triage/closure sweep, not new discussion — flagged explicitly so a human triaging the digest
isn't misled into thinking 95 issues are fresh conversation. Also flagged: 0 commits reached
`main` since `last_check` despite heavy PR/issue churn (latest commit on `main` is
2026-08-12T16:53:21Z, "Release v6.3.0") — verified directly rather than trusted blindly, and
reported as an open question (squash-merges landing elsewhere vs. a genuinely stalled `main`)
rather than a collection bug. Output:
`~/bim/inbox/automated/digest-github-repo/20260821091958.md` (verified on disk). `last_check`
advanced 2026-08-16 → 2026-08-21 in `repos.yaml` (run completed successfully, no abort).

**Total across all three runs:** `gh calls made: 14` (3 + 5 + 6). No browser MCP server was
available or used at any point (confirmed absent per the Overview's six checks); all collection
was via `gh` CLI/API exactly as Step 3 documents. Zero run-level aborts. This satisfies Phase 2's
acceptance bar ("both modes produce a digest on this machine as it stands today") and the Test
Strategy's "one live smoke run per mode, output recorded" — with three runs (two curated-list,
one activity-digest) instead of the minimum two, specifically to exercise the open-PR pass in
isolation.

### 2026-08-23 — Cycle-1 review: Metric-2 evidence, sweep record, rework decisions

**Metric-2 evidence gap closed by adoption.** Review cycle 1 (Alice + Bob) correctly flagged
that both recorded curated-mode runs produced 0 accepted items, so the item-extraction /
metadata / drop path behind Success Metric 2 was never exercised by the entries above. Adopted
as evidence: an ad-hoc curated run earlier today,
`~/bim/inbox/automated/digest-github-repo/20260823121507.md` (`rockerBOO/awesome-neovim`,
window 2026-08-16 → 2026-08-23, pre-rework Step 3). It produced 6 new items with owner/repo,
short name, and description; star counts on the GitHub-hosted items (★4, ★2, ★4); the
archived/404 drop path was not hit. Caveats, stated rather than hidden: the run was ad-hoc
(no recorded `gh calls made` count), the output file lacks the template's YAML frontmatter,
and 3 of the 6 items are Codeberg-hosted — the model improvised around the GitHub-only
metadata call, which this rework now codifies as the "Item hosted off GitHub" edge case.

**chrome-browser.md sweep, recorded.** Two independent sweeps (task 1's `rg` over the live
tree; Blake's blind sweep of `skills/`, `commands/`, `agents/`, `plugins/cache/`) found no
other functional consumer of `mcpServers: [claude-in-chrome]`; the only textual hit is a
historical fixture string in `hooks/tests/test_dispatch.py:947`. Decision (per task 1's
contract): leave `agents/chrome-browser.md` untouched — it is agoge judy's browser-automation
playbook and the declaration documents that agent's intended server, dead or not.

**Cycle-1 rework applied to SKILL.md** (review file
`dev/local/reviews/00134-digest-github-repo-without-browser-v1-review-1.md` holds the full
minutes): identifier validation + safe-quoting for adversary-writable PR/commit text; open-PR
pass switched from `gh pr list` (ordering proven unreliable in Run 2) to the Search API paged
flow shared with activity mode; stale browser-era edge cases reconciled ("Page won't load",
"login wall", "paginate fully" all superseded); repo-level 404s defined as run-aborting;
aborts now report the call count; call-count and auth-flow prose condensed. Settled without
change: the gh-stub test line is satisfied by live runs (design § Test strategy outline), and
`commits/{sha}/pulls` `.[0]` selection stays (design-review non-blocker).

### 2026-08-23 — Cycle-2 review + fix (commit `d365e22e`), and deferrals

Cycle-2 incremental review (all five lenses; `review-fanout` as the shadow consensus leg per
the `consensus_engine: shadow` frontmatter) confirmed the cycle-1 findings were resolved but
surfaced new High-severity defects, two of them regressions the cycle-1 rework itself
introduced. Fix commit `d365e22e` closed every clear-cut skill defect:

- **`{default_branch}` command injection** (Bob 🟠; the shadow workflow's security lens raised
  it as blocking HIGH and its adversarial verifier *confirmed* it — legacy Alice had it at ⚪,
  so the shadow leg's harsher call was the correct one). `{default_branch}` was spliced into a
  double-quoted URL with only single-quoting and no charset check. Now validated against
  `^[A-Za-z0-9._/-]+$` with abort-on-failure.
- **Lost non-2xx catch-all** (Bob 🟠): the cycle-1 auth-flow condensation dropped the "ANY
  non-2xx" coverage, letting 400/410/422/451/network/nonzero-exit fall through. Catch-all
  restored.
- **gh-absent silent fallback** (Blake 🟠, the root of his 🔴): the control flow had no
  handling for `gh` missing / not on `PATH`. Now a loud run-level abort — no curl/REST/browser
  fallback.
- Plus the GitHub-vs-off-GitHub identifier-gate conflict, the default_branch overstatement, and
  a skipped-vs-dropped wording slip (all from the shadow workflow's advisory set).

**Supersession note (reconciles the stale pre-implementation sections).** The Functional
Decomposition mapping table (`gh pr list --state open/all`, `gh issue list --state all`,
`gh api ... --paginate`) and the Test Strategy's "gh-stub test per mode" line describe the
*original plan*, not what shipped. What shipped: an explicit page-loop for commits and the
Search API (`search/issues`) for PRs/issues and the open-PR pass; and manual live-run evidence
in place of a stub test (settled at design time for this prose-only skill — there is no code to
bind a unit test to). Those sections are left as the historical spec; this note is the
authority on the delta.

**Deferred, with a durable home (ledger + here):**
- *Historical curl-run artifacts.* Three 2026-08-23 14:53 digest files
  (`20260823145303/145313/145317.md`) were produced by runs that used `curl` (one states "no gh
  CLI available") and omitted the footer/frontmatter. `d365e22e` prevents recurrence; the files
  are user-owned synced vault content and are the user's to clean or keep.
- *Live-evidence gap.* The reworked open-PR Search-API pass and the validation gates have no
  post-rework live run. To be recorded on the next natural `also_check_prs` run; the open-PR
  pass reuses the paging/stop mechanism already live-proven by Run 3.
- *Metric-3 commit subjects.* Never exercised — every recorded run had 0 commits in-window.
  Same deferral: capture it on a run that lands commits.
