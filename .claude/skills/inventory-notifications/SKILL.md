---
name: inventory-notifications
description: Use when user wants to inventory, catalog, or summarize repositories from GitHub notifications for a specific repo. Triggers on "inventory notifications", "catalog repos from notifications", "summarize notification repos", "list repos from notifications".
---

# Inventory GitHub Notification Repos

Fetch all GitHub notifications for a repo, extract mentioned repositories, fetch their descriptions, categorize them, and produce a grouped markdown inventory.

## Input

User provides a GitHub notifications URL or repo name. Extract the repo filter (e.g. `rockerBOO/awesome-neovim`).

## Workflow

### 1. Fetch all notifications

```bash
gh api '/notifications?all=true&per_page=50' --paginate \
  --jq '.[] | select(.repository.full_name == "OWNER/REPO") | {title: .subject.title, type: .subject.type, url: .subject.url}'
```

### 2. Extract repo references

Two extraction patterns depending on the awesome-list type:

**Pattern A — title-based** (e.g. awesome-neovim): Repo names appear directly in PR titles as `Add \`owner/repo\``.

```bash
... | select(.title | test("^Add ")) | .title' | sed "s/^Add \`//;s/\`$//" | sort -u
```

Skip non-repo entries (scripts, README updates, config files).

**Pattern B — body-based** (e.g. awesome-claude-code): Repo URLs are in issue/PR bodies, not titles. Titles use formats like `[Resource]: Name` or `Add Name`.

Extract from ALL notification types (issues, PRs, discussions):

```bash
for num in <issue_numbers>; do
  result=$(gh api "repos/OWNER/REPO/issues/$num" --jq '{title: .title, body: .body}')
  title=$(echo "$result" | jq -r '.title')
  repo_url=$(echo "$result" | jq -r '.body // ""' | grep -oE 'https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+' | grep -v 'OWNER/REPO' | head -1)
  echo "$num|$title|$repo_url"
done
```

Same for PRs using the `/pulls/$num` endpoint.

**How to decide:** Check a few notification titles. If they contain `owner/repo` in backticks, use Pattern A. If titles say `[Resource]:` or lack repo identifiers, use Pattern B.

### 3. Fetch repo descriptions in parallel

Split repos into batches of ~25. Use the Task tool with `subagent_type=Bash` to fetch batches in parallel:

```bash
for repo in "owner/name" ...; do
  echo "---"
  gh api "repos/$repo" --jq '{name: .full_name, description: .description, topics: .topics}' 2>&1 || echo "NOT FOUND: $repo"
done
```

### 4. Categorize and write markdown

Group repos by function based on description and topics. Categories should match the ecosystem — don't force a fixed list. Derive categories from what's actually in the data.

Example categories for **neovim plugins:**

| Category | Signal keywords |
|----------|----------------|
| AI / LLM | ai, llm, copilot, agent, chat |
| Colorscheme | theme, colorscheme, color |
| Completion | cmp, completion, source |
| Git | git, diff, merge, commit |
| Search / Navigation | search, find, jump, picker |
| LSP | lsp, language-server, diagnostics |
| UI / Interface | sign, fold, resize, spinner |
| Terminal | terminal, tui |
| Code Runner | runner, execute, run |
| Note-taking | note, study, markdown, pkm |

Example categories for **Claude Code ecosystem:**

| Category | Signal keywords |
|----------|----------------|
| Agent Orchestration | multi-agent, orchestration, session, daemon |
| Agent Skills / Packs | skills, plugins, agents, rules, hooks |
| Hooks / Ops | hooks, ops, autonomous, monitoring |
| Memory / Knowledge | memory, cache, brain, persistent |
| MCP Servers | mcp, mcp-server, tools |
| Security / Safety | security, shield, safety, governance |
| Cost / Usage | cost, budget, token, rate-limit |
| Linting / Validation | linter, validator, doctor, audit |
| Desktop / GUI | gui, desktop, tauri, electron |
| Guides / Documentation | guide, tutorial, documentation |

### 5. Output format

Write to markdown file. Each entry:

```markdown
- [owner/repo](https://github.com/owner/repo) — First sentence of purpose. Second sentence with detail.
```

Group under `## Category` headers. Exclude repos that 404. Note repos with no description under `## Uncategorized`.

## Quick Reference

| Step | Tool | Parallelizable |
|------|------|----------------|
| Fetch notifications | `gh api` | No |
| Extract repo names | Bash (Pattern A) or Task subagents (Pattern B) | Pattern B: Yes |
| Fetch repo info | Task (Bash subagents) | Yes — batch ~25 per agent |
| Write markdown | Write tool | No |
