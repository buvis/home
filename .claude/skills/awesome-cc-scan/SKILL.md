---
name: awesome-cc-scan
description: >
  Scans the hesreallyhim/awesome-claude-code GitHub repository for new entries added since the last
  scan, then updates the tracking zettelkasten note at
  /Users/bob/bim/zettelkasten/20251005221747.md with any repos not already present.

  Use this skill whenever the user says anything like: "check notifications",
  "scan awesome-claude-code", "any new repos?", "update my claude code list",
  "check for new Claude Code tools", or pastes the URL
  https://github.com/notifications?query=repo%3Ahesreallyhim%2Fawesome-claude-code.
---

# awesome-cc-scan

Scans `hesreallyhim/awesome-claude-code` for repos added since the last scan date recorded in the
zettelkasten, and appends new entries (with `- [ ]` checkboxes) to the appropriate sections.
Skips any repo already present in the file — in any section, any checkbox state.

---

## Step 1 — Read the zettelkasten

Read `/Users/bob/bim/zettelkasten/20251005221747.md` and extract:

1. **Last scan date** — the date on the line `Last scan: **YYYY-MM-DD**`
2. **All tracked repos** — every GitHub handle that appears anywhere in the file (owner/repo format,
   e.g. `nielsgroen/claude-tmux`). This is your dedup list. Check all sections including Dropped.

---

## Step 2 — Fetch commits since last scan

Fetch the commit history page:

```text
https://github.com/hesreallyhim/awesome-claude-code/commits/main
```

Parse commits dated **after** the last scan date. Ignore automated commits whose messages match
`chore: update repo ticker data` or `chore: update GitHub release data` — these contain no new
repos. Focus only on commits that look like:

```text
Add resource: <name> (#NNN)
```

Each such commit corresponds to one new repo being added to the list.

---

## Step 3 — Look up each new repo

For each new-resource commit, fetch the corresponding PR page:

```text
https://github.com/hesreallyhim/awesome-claude-code/pull/<NNN>
```

Extract:

- **GitHub URL** (owner/repo)
- **Short name** (what it's called in the PR title or body)
- **Description** — one sentence of what it actually does; prefer the repo's own README tagline
  over the PR description if they differ

Also fetch the repo's GitHub page to get the **star count** (★N).

Skip any repo whose owner/repo already appears in the zettelkasten (any section).

---

## Step 4 — Choose the right section

Place each new repo in the most fitting section of the zettelkasten. Current sections and their scope:

| # | Section | Typical contents |
|---|---------|-----------------|
| 1 | Core Infrastructure | hooks, ops starters, official plugin patterns |
| 2 | MCP Integrations | Model Context Protocol servers |
| 3 | Development Methodologies | spec-driven dev, PRPs, kiro-style workflows |
| 4 | Skills & Capabilities | agent skill libraries, skill tooling |
| 5 | Subagents & Orchestration | multi-agent frameworks, orchestrators, pipelines |
| 6 | Context Engineering | memory, context compression, knowledge graphs |
| 7 | Commands & Workflows | slash commands, reusable command collections |
| 8 | Security / Safety | guardrails, permission tools, audit hooks |
| 9 | Cost / Usage Monitoring | token tracking, spend dashboards |
| 10 | Linting / Validation | rule doctors, pre-deploy checks |
| 11 | Developer Tools | UIs, IDE integrations, statuslines, utilities |
| 12 | Dropped | rejected — exists only to prevent re-adding |

If a repo is clearly niche/low-value (e.g. niche language, commercial noise, no description,
<5 stars with no clear use case for a SAP/Python/Rust/Kubernetes engineer), add it to **Section 12
Dropped** with a brief reason instead. This prevents it from re-appearing in future scans.

---

## Step 5 — Write the new entries

For each new repo being added to sections 1–11, append it **at the end** of the unchecked (`- [ ]`)
block in that section, using this format:

```markdown
- [ ] **<short-name>** — [<owner>/<repo>](https://github.com/<owner>/<repo>) — <one-sentence description>. ★<count>
```

For repos added to Section 12 (Dropped), use:

```markdown
- [ ] [<owner>/<repo>](https://github.com/<owner>/<repo>) — <reason for dropping>
```

Do **not** duplicate entries. If owner/repo already appears anywhere in the file, skip it entirely.

---

## Step 6 — Update the scan date

Replace the line:

```text
Last scan: **<old-date>**
```

with today's date:

```text
Last scan: **YYYY-MM-DD**
```

---

## Step 7 — Report back

Summarise what was done:

- Updated scan date from `<old>` → `<new>`
- List each repo added, which section it went into, and its star count
- Mention any repos skipped (already present or dropped)

Keep it concise — the user can open the file for full details.

---

## Edge cases

- **PR is a 404** — note it in the summary as "could not fetch #NNN" and skip.
- **Repo is a 404 or archived** — add to Section 12 Dropped with reason "404/archived".
- **Stars not shown** — omit the ★ count rather than guessing.
- **Ambiguous section** — pick the best fit and mention it briefly in the summary so the user can
  move it if needed.
- **No new commits** — report "No new repos since <last-scan-date>" and leave the file unchanged
  (don't even update the scan date, since nothing was actually scanned).
