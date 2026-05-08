---
name: digest-github-repo
description: Use when generating a zettelkasten digest of GitHub repo activity (issues, PRs, commits) for triage. Two modes (curated-list for awesome-lists, activity-digest for general repos). Triggers on "digest REPO", "what is new in REPO", pasted GitHub URL.
---

# digest-github-repo

Produces zettelkasten-format digests of new GitHub repository activity, with checkboxes for
triage. Works in two modes depending on repo configuration.

All files live under `~/bim/inbox/automated/digest-github-repo/`.

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

Then add the repo to `repos.yaml` with sensible defaults, set `last_check` to today's date,
and stop with: "Repo registered. Run again to pick up activity from today onward."

---

## Step 2 — Build the dedup list (curated-list mode only)

This step only applies to repos configured with `mode: curated-list`.

Find all files that track this repo by grepping for the `repo` frontmatter field across two
locations:

```bash
grep -rl "^repo: OWNER/REPO" ~/bim/zettelkasten/ ~/bim/inbox/ 2>/dev/null
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

## Step 3 — Collect new activity via Claude in Chrome

Use the browser tools. The data you collect depends on the mode.

### For curated-list mode

The config specifies a `commit_pattern` (regex) and a `source_url` for the commits page.

Visit the commits page (e.g. `https://github.com/OWNER/REPO/commits/main`). Parse commits
dated **after** `last_check`. Match only commits whose message fits the `commit_pattern` — each
match represents one new item added to the list. Ignore automated/maintenance commits.

For each matching commit, fetch the corresponding PR page to extract:
- GitHub URL of the added item (owner/repo)
- Short name
- One-sentence description (prefer the item's own README tagline)
- Star count from the item's GitHub page

Skip any item whose `owner/repo` appears in the dedup list.

### For activity-digest mode

Visit these pages in sequence, paginating until past the `last_check` cutoff:

1. **PRs**: `https://github.com/OWNER/REPO/pulls?q=is%3Apr+sort%3Aupdated-desc`
   — collect number, title, status (merged/open/closed)

2. **Issues**: `https://github.com/OWNER/REPO/issues?q=is%3Aissue+sort%3Aupdated-desc`
   — collect number, title, status (open/closed)

3. **Commits**: `https://github.com/OWNER/REPO/commits/main` (try `master` if 404)
   — collect first line of commit message, skip merge commits and version bumps

Use the `.markdown-title` CSS class to extract clean titles from list pages. Stop paginating
once you reach items older than the cutoff date.

---

## Step 4 — Organise and categorise

### For curated-list mode

The config provides a `sections` list with names and descriptions. Place each new item in the
most fitting section based on the item's description and the PR context that added it.

If an item is clearly niche, low-value, or irrelevant for the user (the config may include
a `relevance_hint` describing the user's interests), place it in the **Dropped** section with
a brief reason. This prevents it from appearing in future scans.

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

```markdown
---
id: <zettelkasten-id>
title: "<YYYYMMDD> - <repo-name> digest"
date: <YYYY-MM-DDTHH:mm:ss>
tags: [<tag1>, <tag2>, <tag3>]
type: github-repo-digest
publish: false
processed: false
repo: OWNER/REPO
---

# <YYYYMMDD> - <repo-name> digest

Digest of [OWNER/REPO](https://github.com/OWNER/REPO) — new items.

## <Section name>

<One-sentence description of what goes here>

- [ ] **<short-name>** — [<item-owner>/<item-repo>](https://github.com/<item-owner>/<item-repo>) — <description>. ★<count>

## Dropped

- [-] [<item-owner>/<item-repo>](https://github.com/<item-owner>/<item-repo>) — <reason>
```

Use `- [ ]` for items to evaluate, `- [-]` for items being dropped. Do not duplicate any item
from the dedup list.

### Activity-digest mode template

```markdown
---
id: <zettelkasten-id>
title: "<YYYYMMDD> - <repo-name> digest"
date: <YYYY-MM-DDTHH:mm:ss>
tags: [<tag1>, <tag2>, <tag3>]
type: github-repo-digest
publish: false
processed: false
repo: OWNER/REPO
---

# <YYYYMMDD> - <repo-name> digest

Digest of [OWNER/REPO](https://github.com/OWNER/REPO) — recent activity.

## <Theme>

- <Prose sentence summarising a cluster of related changes, with #NNN references>
- <Another cluster>

## <Next theme>

- <Cluster summary>
```

Each list item is a cluster of related activity (not individual items). Write 2-4 sentences
per cluster, with inline PR/issue references.

---

## Step 6 — Update the config

Update the `last_check` field for this repo in `repos.yaml` to today's date.

---

## Step 7 — Report back in chat

Show the full summary in chat, then add a footer:

```
Saved to: ~/bim/inbox/automated/digest-github-repo/<zettelkasten-id>.md
Check date updated: <old-date> → <today>
```

If no new activity was found, say so clearly. Still update the scan date and still create the
zettelkasten file (with a note that there was nothing new).

---

## Edge cases

- **Page won't load** — note the failure, skip that source, proceed with what loaded.
- **Branch is not `main`** — try `master`, then the default branch visible on the repo homepage.
- **PR is a 404** — note it in the summary and skip.
- **Repo is private** — if you get a 404 or login wall, report it and stop.
- **Item repo is archived or 404** — in curated-list mode, add to Dropped with reason.
- **Stars not visible** — omit the star count rather than guessing.
- **No new activity** — say so clearly, still update the scan date and create the zettelkasten.
- **Very many pages** — paginate fully; don't cut off early.
- **Ambiguous section** — pick the best fit and mention it in the summary.
- **A PR and issue cover the same thing** — group them in one sentence.
