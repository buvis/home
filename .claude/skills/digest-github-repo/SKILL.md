---
name: digest-github-repo
description: Use when generating a zettelkasten digest of GitHub repo activity (issues, PRs, commits) for triage. Two modes (curated-list for awesome-lists, activity-digest for general repos). Triggers on "digest REPO", "what is new in REPO", pasted GitHub URL.
---

# digest-github-repo

Produces zettelkasten-format digests of new GitHub repository activity, with checkboxes for
triage. Works in two modes depending on repo configuration.

All files live under `~/bim/inbox/automated/digest-github-repo/`.

## Dependencies

- External `~/bim/` tree (hard anchor, no fallback): config `~/bim/inbox/automated/digest-github-repo/repos.yaml`, dedup grep over `~/bim/zettelkasten/` and `~/bim/inbox/`, output into `~/bim/inbox/automated/digest-github-repo/`.

## Triggers

Use this skill whenever the user wants to catch up on a GitHub repository, says things like
"what's new in REPO", "digest REPO", "check awesome-neovim", "any new claude code tools",
"catch me up on REPO", "what did I miss in REPO", "any updates in REPO?",
"check for new neovim plugins", "update my plugin list", "repo digest for REPO",
"check notifications for REPO", or pastes a GitHub URL and asks about recent activity.

---

## Step 0 — Identify the target repository

The user specifies a repo as `owner/repo`, a GitHub URL, or a recognisable shorthand like
"awesome-neovim" or "superpowers". Extract the `owner/repo` form.

If no repo is clear from context, ask: "Which GitHub repository would you like a digest for?"

---

## Step 1 — Load the repo config

Read the config registry at:

```
~/bim/inbox/automated/digest-github-repo/repos.yaml
```

If the file doesn't exist, create it from the template in `references/repos-template.yaml`
(read that file now), which ships with two pre-configured repos (awesome-claude-code and
awesome-neovim) plus a commented example for activity-digest mode.

Look up the requested repo in the config. If it's not listed, ask the user:

> "This repo isn't registered yet. Which mode should I use?
>
> - **curated-list** — each checkbox is a single item (tool, plugin, repo) for you to keep or
>   drop. Dropped items are remembered and never re-added. Best for awesome-lists and catalogues
>   where you're triaging individual entries.
>
> - **activity-digest** — each checkbox is a cluster of related changes (PRs, issues, commits)
>   for you to mark as reviewed. Nothing is kept or dropped, just acknowledged. Best for project
>   repos where you want to stay informed on development activity."

If the user picks **curated-list**, ask one follow-up:

> "Should I also scan open PRs for proposed items (`also_check_prs`)? Useful when the
> maintainer is slow or inactive — PRs show what the community is proposing before (or
> instead of) a merge."

Then add the repo to `repos.yaml` with sensible defaults (recording `also_check_prs` if
chosen), set `last_check` to today's date, and stop with: "Repo registered. Run again to
pick up activity from today onward."

---

## Step 2 — Build the dedup list (curated-list mode only)

This step only applies to repos configured with `mode: curated-list`.

Find all files that track this repo by grepping for the `repo` frontmatter field across two
locations:

```bash
rg -l "^repo: OWNER/REPO" ~/bim/zettelkasten/ ~/bim/inbox/
```

1. `~/bim/zettelkasten/` — the main zettelkasten (tracker files live here after triage)
2. `~/bim/inbox/` (recursive) — previous digest summaries that haven't been triaged yet

Every digest and tracker file produced by this skill includes `repo: OWNER/REPO` in its YAML
frontmatter, so grepping on that field is the fastest and most reliable way to locate them.
For legacy files that predate this convention, fall back to scanning for the repo's URL pattern
(`github.com/OWNER/REPO`) as a secondary check.

In every matching file, collect:

1. **All tracked items** — every GitHub `owner/repo` handle that appears in any checkbox line
   (`- [ ]`, `- [x]`, `- [-]`). This is the full dedup set.
2. **Dropped items** — specifically items on `- [-]` lines. These were deliberately rejected
   and must never be re-added.

The combined set of all found `owner/repo` handles is your **dedup list**.

---

## Step 3 — Collect new activity via `gh`

All collection happens via Bash `gh` (CLI/API), not a browser. `{owner}`, `{repo}` come from
the registered `repos.yaml` entry; `{last_check}` is that repo's stored `last_check` date
(`YYYY-MM-DD`).

Before collecting, run the preflight:

```bash
gh auth status
```

A failure here aborts immediately (see **Auth/permission-failure control flow** below).

### Resolve the default branch (shared, both modes)

```bash
gh api repos/{owner}/{repo} --jq '.default_branch'
```

Use the returned branch name (`{default_branch}`) everywhere below that previously said
`main`/`master`. One call, no probing. This call is also the source-of-truth
auth/permission check for this specific repo (see **Auth/permission-failure control flow**
below).

### For curated-list mode

1. Commits since `last_check` on `{default_branch}`, matched against the config's
   `commit_pattern` regex on the commit title (first line):

```bash
gh api "repos/{owner}/{repo}/commits?sha={default_branch}&since={last_check}T00:00:00Z&per_page=100&page={n}" \
  --jq '.[] | {sha: .sha, title: (.commit.message | split("\n")[0]), date: .commit.author.date}'
```

   Explicit page loop, not `--paginate` — `--paginate` fetches every page before any
   client-side limit can apply, which does not bound the actual number of requests made.
   Loop `page = 1, 2, ...` yourself, stopping when a page returns fewer than 100 items
   (exhausted) or when `page == 20` is reached (a hard ceiling of 2,000 commits — reached only
   on a first-time registration against a high-traffic repo, since `since` already excludes
   everything before `last_check`). If the page-20 ceiling is hit, stop there and note in the
   digest: "more than 2,000 commits since last check; digest may be incomplete — consider a
   more recent `last_check`" (same pattern as the Search API page-10 policy below — a known,
   reported limit, not a crash).

   Match `commit_pattern` against the extracted title only, never the raw multiline
   `.commit.message` — the config's regexes are `$`-anchored to a one-line commit title (e.g.
   `^Add resource: .+ \(#(\d+)\)$`), matching what the old browser flow saw, and a `$` anchor
   against a full multiline message fails once a commit has a body. Apply the config's
   `ignore_patterns` regex list to the same title before testing `commit_pattern`, same as the
   old flow's "ignore automated/maintenance commits."

2. PR behind a matching commit:

```bash
gh api repos/{owner}/{repo}/commits/{sha}/pulls --jq '.[0] | {number, title, body}'
```

   Extract the added item's `owner/repo`, short name, and description from `title`/`body`
   exactly as the current skill extracts them from the PR page. `title`/`body` is the same
   source scope the old browser flow used (it only ever read the PR page's title and
   description, never its diff, files, or comments). New edge case: if `.[0]` is null (no PR
   found for a direct-to-branch commit) or `title`/`body` don't yield a confident `owner/repo`,
   skip that commit with a note rather than guessing (same "note and skip" shape as the
   existing "PR is a 404" edge case).

   **Identifier validation (applies to every extraction site, including the open-PR pass):**
   PR titles and bodies are public, adversary-writable text. Before an extracted
   `{item-owner}/{item-repo}` enters any command, it must match
   `^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$` (GitHub's own identifier charset); anything else is not
   a confident extraction — skip with a note. Pass every API-derived value
   (`{default_branch}`, extracted identifiers) into commands as a single-quoted argument,
   never unquoted, so external text can never alter the command.

3. Item repo metadata:

```bash
gh api repos/{item-owner}/{item-repo} --jq '{description: .description, stars: .stargazers_count, archived: .archived}'
```

   The old edge case bundled two distinct signals ("archived or 404") that the API separates:
   an archived repo stays reachable (`archived: true` in the response, not a 404), while a
   deleted/renamed-away repo 404s. Branch on both: `archived == true` → Dropped with reason
   "archived"; a plain 404 on this call (and only a 404 — any other non-2xx here falls under
   the Auth/permission-failure control flow below) → Dropped with reason "repo not found".
   Fidelity note: this is GitHub's short repo metadata blurb, not the README tagline the old
   browser flow preferred. When `.description` is null/empty, omit the description rather than
   fetching and parsing the README — same "omit rather than guess" pattern as the existing
   "Stars not visible — omit" edge case. Only call this for github.com-hosted items: for an
   item hosted elsewhere (Codeberg, GitLab, …), skip the metadata call, keep the item with the
   description from the PR/commit text, note the host, omit stars.

Skip any item whose `owner/repo` appears in the dedup list.

#### Open-PR pass (only when the repo config has `also_check_prs: true`)

```bash
gh api "search/issues?q=repo:{owner}/{repo}+is:pr+is:open&sort=updated&order=desc&per_page=100&page={n}" --jq '{total_count, items}'
```

Same paged loop, stop condition, page-10 cap, and `total_count` warning as activity-digest
mode below — one shared policy. (`gh pr list` was tried first and its
`--search "sort:updated-desc"` ordering proved unreliable in live runs, which silently breaks
any cap or early-stop logic; the Search API orders correctly.) Keep only PRs whose
`updated_at` is after `last_check`, with `title`/`body` from each search item. For each
date-kept PR, extract the proposed item's `owner/repo`, short name, and description from
`title`/`body` — the exact same extraction task as step 2's commit-behind-a-PR extraction,
same skip-with-note rule when extraction isn't confident, same identifier validation. Skip
PRs that don't propose a list item at all (docs fixes, maintenance PRs, etc.). Every PR that
survives extraction then goes through the same item repo metadata call (step 3 above,
including its `archived` check) and the same dedup list filter as commit-sourced items. Keep
these items separate from commit items: a commit means "accepted into the list", an open PR
means "proposed, pending".

### For activity-digest mode

```bash
gh api "search/issues?q=repo:{owner}/{repo}+is:pr&sort=updated&order=desc&per_page=100&page={n}" --jq '{total_count, items}'
gh api "search/issues?q=repo:{owner}/{repo}+is:issue&sort=updated&order=desc&per_page=100&page={n}" --jq '{total_count, items}'
```

Loop `page = 1, 2, ...`: for each page, keep items with `.updated_at > last_check`; stop
paginating as soon as a page's last (oldest) item's `updated_at` is on or before `last_check`,
or the page is empty.

GitHub's Search API caps total results at 1,000 (page 10 at 100/page) regardless of match
count — a page-11 request errors instead of returning empty. Cap the loop at page 10. Use the
response's own `total_count` to avoid a false-positive warning: only warn when
`total_count > 1000` AND the page-10 boundary item's `updated_at` is still after `last_check`.
When both hold, stop and report: "more than 1,000 updates since last check on this list;
digest may be incomplete — consider a more recent `last_check`." Do not treat this as a
failure.

For PRs, extract `{number, title, state}` (map search-API `state` `open`/`closed` plus
`.pull_request.merged_at` presence to the old `merged/open/closed` triple). For issues, extract
`{number, title, state}` directly (`open`/`closed`).

**Commits**: same paged, `since`-bounded, page-20-capped call and first-line extraction as
curated-list mode's step 1 (no `commit_pattern` filtering — activity-digest wants all commits,
just the title). Skip merge commits and version-bump commits by the same client-side rule as
before (title starts with `Merge ` or matches a `vX.Y.Z` / `chore(release)` bump pattern),
applied to the extracted title.

### Call-count contract

Increment a counter once per `gh` invocation, at the point it's issued — not derived after the
fact. Every invocation counts, the `gh auth status` preflight included. Report the total in
Step 7's footer as `gh calls made: N`.

### Auth/permission-failure control flow

Run `gh auth status` before collecting; a failure aborts. After that, one rule: any
401/403/429/5xx on any call aborts the run, and so does a 404 on a repo-level call (the
default-branch lookup — the repo is a registered config entry — plus commit pages, the open-PR
search, and Search API pages). Only a 404 on a per-item call (`commits/{sha}/pulls`, item-repo
metadata) stays scoped to that commit/PR/item per its edge case. On any run-level abort: do
not write a zettelkasten file, do not advance `last_check` in Step 6; report in chat which
call failed, the HTTP status, and `gh calls made: N` so far. This single rule also covers
Search API rate limits.

---

## Step 4 — Organise and categorise

### For curated-list mode

The config provides a `sections` list with names and descriptions. Place each new item in the
most fitting section based on the item's description and the PR context that added it.

If an item is clearly niche, low-value, or irrelevant for the user (the config may include
a `relevance_hint` describing the user's interests), place it in the **Dropped** section with
a brief reason. This prevents it from appearing in future scans.

Items from the open-PR pass never go into the config sections. They go into a single
**Community Suggestions (Open PRs)** section, each with its PR number and link, so the
proposed-vs-accepted distinction survives into the digest. Relevance filtering still
applies: irrelevant PR items go to Dropped.

### For activity-digest mode

Group collected items into thematic sections. Default themes:

| Theme | Contents |
|---|---|
| Bug fixes | Bug reports + fix PRs |
| New features | New capabilities, integrations, content |
| Platform & compatibility | IDE/tool/platform support |
| Docs & i18n | Documentation, translations |
| Architecture & refactoring | Design discussions, refactoring |
| Infrastructure & CI | Build, CI/CD, testing, deps |
| Community | Questions, showcases, feedback |

Only include themes with actual activity. Use your judgement to rename or merge themes based
on the repo's nature.

---

## Step 5 — Write the zettelkasten summary

Generate a zettelkasten ID using the current timestamp: `YYYYMMDDHHmmss` (use Bash:
`date +%Y%m%d%H%M%S`). Also get the ISO 8601 datetime (`date +%Y-%m-%dT%H:%M:%S`).

Template field guide:
- `<YYYYMMDD>` — date portion of the zettelkasten ID (first 8 digits)
- `<repo-name>` — repository name only, without the owner (e.g. `superpowers`, not `obra/superpowers`)
- `title` and H1 heading must match: `YYYYMMDD - <repo-name> digest`
- `date` — ISO 8601 datetime when the file was created
- `tags` — three tags that best describe the digest content
- `type` — always `github-repo-digest`
- `publish` and `processed` — always `false`

Write the summary to:
```
~/bim/inbox/automated/digest-github-repo/<zettelkasten-id>.md
```

### Curated-list mode template

See `references/output-templates.md` § "Curated-list mode" for the template and its usage notes.

### Activity-digest mode template

See `references/output-templates.md` § "Activity-digest mode" for the template and its usage notes.

---

## Step 6 — Update the config

Update the `last_check` field for this repo in `repos.yaml` to today's date.

---

## Step 7 — Report back in chat

Show the full summary in chat, then add a footer:

```
Saved to: ~/bim/inbox/automated/digest-github-repo/<zettelkasten-id>.md
Check date updated: <old-date> → <today>
gh calls made: N
```

If no new activity was found, say so clearly. Still update the scan date and still create the
zettelkasten file (with a note that there was nothing new).

---

## Edge cases

- **Call fails** — per the Auth/permission-failure control flow: run-level failures abort the
  whole run (no file, no `last_check` advance); only per-item 404s are noted and skipped.
- **Default branch** — resolved once via `gh api repos/{owner}/{repo} --jq '.default_branch'`; no probing needed.
- **PR is a 404** — note it in the summary and skip.
- **Repo is private or gone** — the default-branch lookup returns non-2xx; that aborts the run
  (see Auth/permission-failure control flow).
- **Item repo is archived** — in curated-list mode, add to Dropped with reason "archived"; a
  404 on the item's metadata call → Dropped with reason "repo not found".
- **Item hosted off GitHub** (Codeberg, GitLab, …) — skip the `gh` metadata call; keep the
  item with the description from the PR/commit text, note the host, omit stars.
- **Stars not visible** — omit the star count rather than guessing.
- **No new activity** — say so clearly, still update the scan date and create the zettelkasten.
- **Very many pages** — the pagination ceilings apply (page 20 for commits, page 10 for
  Search API); stop there and add the documented "digest may be incomplete" note.
- **Ambiguous section** — pick the best fit and mention it in the summary.
- **A PR and issue cover the same thing** — group them in one sentence.
