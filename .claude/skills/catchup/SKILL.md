---
name: catchup
description: Catch up on project and branch context. Loads raw sources, branch diff, and GitHub state directly into context, then synthesizes a lightweight capsule. Use when starting work, resuming after a break, onboarding to a repo, or context feels thin. Triggers on "catch up", "catchup", "what changed on this branch", "summarize branch changes", "review branch", "bootstrap session", "generate project capsule", "seed context", "project overview", "create capsule", "refresh capsule".
---

# Catch Up

Hydrate context before starting work. With large context windows, load raw sources directly rather than relying on summaries. The capsule captures derived insights — invariants, decisions, health signals — not paraphrases of files you can read.

## Design Principles

- **Load sources, not summaries.** Read the actual files. Don't generate an intermediate summary to read later.
- **Parallel by default.** Scripts and file reads are independent — run them concurrently.
- **Capsule = what you can't grep.** Invariants, implicit rules, cross-cutting concerns, project health. Not a restatement of README or package.json.
- **Full context, no triage.** Don't prioritize which files to read. Load everything, then synthesize.
- **Follow the graph.** Changes don't exist in isolation. Trace imports and reverse dependencies to see blast radius.
- **Surface the "why".** Link code changes to the issues/PRs/conversations that motivated them. Load full bodies, not just titles.
- **CI is context.** A failing build is as important as the code change. Load error logs, not just pass/fail status.

## Workflow

### Phase 1: Gather (parallel)

Run ALL of the following concurrently. Don't wait for one to finish before starting another.

#### 1a. Run scripts

```bash
~/.claude/skills/catchup/scripts/branch-diff.sh   # skip if on master
~/.claude/skills/catchup/scripts/github-state.sh   # skip if no gh / no remote
~/.claude/skills/catchup/scripts/load-memories.sh  # skip if no memories
```

#### 1b. Read project sources

Read every file that exists (skip missing ones):

- `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` — **read these first**, they may contain project-specific catchup rules, priority areas, or workflow requirements that should guide the rest of this process
- `README.md`
- All files in `agent_docs/` (if directory exists)
- All PRDs in `.local/prds/wip/`
- Config files: `package.json`, `Cargo.toml`, `pyproject.toml`, `go.mod`, `tsconfig.json`, `Makefile`, `docker-compose.yml`, etc.
- Directory listing (top 3 levels of `src/`, `lib/`, `app/`, or equivalent)
- Domain model files: `models/`, `types/`, `schemas/`, `entities/` directories

**AGENTS.md awareness**: If AGENTS.md (or CLAUDE.md) specifies rules like "always check X before working", "never modify Y without Z", or defines priority areas — note these. They should influence what you flag in the report and how you frame the capsule. If AGENTS.md defines a project-specific catchup checklist, follow it in addition to (not instead of) this workflow.

#### 1c. Read existing capsule

Read `.local/project-capsule.md` if it exists — its invariants and health signals from the last session are useful context even as you load fresh sources.

#### 1d. Read recent master activity

```bash
git log --oneline -20 master
```

Even on a feature branch, knowing what landed on master recently prevents working against stale assumptions.

### Phase 2: Load branch context (feature branches only)

Skip if on master.

#### 2a. Full diff

After the branch-diff script runs, load the **full diff**:

```bash
git diff $(git merge-base origin/master HEAD)..HEAD
```

With 1M context this fits. Don't sample or skip files. Read the entire diff.

#### 2b. Full file content for changed files

Read the **complete current version** of every file modified on the branch. The diff shows what changed; the full file shows how it fits in context.

```bash
# Get list of changed files from branch-diff output, then read each one
git diff $(git merge-base origin/master HEAD)..HEAD --name-only
```

Read all of them. Don't skip test files or configs — they're context too.

#### 2c. Reverse dependency tracing (blast radius)

For each changed file, find what depends on it. This surfaces ripple effects the diff alone won't show.

Use `ast-grep` (`sg`) for structural matching — it understands syntax, not just text, so it won't false-positive on comments or strings.

For each changed file, find its consumers by matching import/use patterns:

**JS/TS:**
```bash
# Find all files importing from a changed module
sg --pattern 'import $$$BINDINGS from "$MODULE"' --lang ts
sg --pattern 'require("$MODULE")' --lang ts
# Filter results to those referencing the changed file's module path
```

**Python:**
```bash
sg --pattern 'from $MODULE import $$$NAMES' --lang python
sg --pattern 'import $MODULE' --lang python
```

**Rust:**
```bash
sg --pattern 'use $PATH' --lang rust
sg --pattern 'mod $NAME' --lang rust
```

**Go:**
```bash
sg --pattern 'import ($$$)' --lang go
sg --pattern 'import "$PATH"' --lang go
```

Beyond imports, also trace usage of exported symbols that changed. If a function signature, type definition, or interface changed:

```bash
# Find all call sites of a changed function
sg --pattern '$FUNC($$$ARGS)' --lang ts  # then filter to the function name

# Find all implementations/usages of a changed type
sg --pattern '$VAR: ChangedType' --lang ts
```

`ast-grep` shines here because it distinguishes `foo()` the call from `"foo()"` the string and `// foo()` the comment. This matters when tracing blast radius — false positives waste context, false negatives miss breakage.

Read any reverse dependency files that look impacted by the changes. If a utility, type, or interface file changed, always trace its consumers.

#### 2d. Linked issues and PR context

Extract issue/PR references from branch commits and load their full body text:

Find issue references in commit messages (#123, GH-123, fixes #123, etc.) using `Grep`:
```
Grep(pattern="#[0-9]+", path=<commit log output>)
```
Or use separate Bash calls — never pipe through grep/sort:
```bash
git log $(git merge-base origin/master HEAD)..HEAD --format="%B"
```
Then extract `#NNN` references from the output.

For each referenced issue, fetch the full body:
```bash
gh issue view {number} --json title,body,labels,state,comments --jq '.title, .body'
```

If the branch has an open PR, fetch its full description and review comments:
```bash
gh pr view --json title,body,comments,reviews
```

This gives you the "why" behind the changes, not just the "what".

### Phase 3: Synthesize

Now that everything is in context, update or create the capsule. The capsule is NOT a summary of what you just read — it captures insights that aren't in any single file.

#### Write `.local/project-capsule.md`

```markdown
# Project Capsule: {project name}

Generated: {date}

## Key Invariants

{domain rules, boundaries, data flow constraints}
{implicit rules that aren't documented anywhere}
{things an agent most often gets wrong without being told}
{cross-cutting concerns that span multiple files}

## Architecture Decisions

{why the code is structured this way, not just what it is}
{tradeoffs that were made and why}
{patterns that look wrong but are intentional}

## Component Boundaries

{what talks to what, and what doesn't}
{which modules own which data}
{where the seams are between subsystems}

## Active Work

{current branch purpose, PRDs in wip/, recent focus areas}
{what's in flight across branches}

## GitHub State

{open issue count, notable issues (bugs, urgent, P0/P1)}
{open PR count, stale PRs, PRs needing review}
{active branches, orphaned branches}
{latest release, unreleased commits on master}
{failing workflows, recurring CI failures}

## Project Health

{overall assessment: is CI green? are PRs flowing? is debt accumulating?}
{risks or blockers worth knowing about}

## Project Memories

{gotchas, patterns, feedback, and references from memory files}
{only present if memories exist for this project}
```

#### Capsule rules

- Don't restate what's in README, CLAUDE.md, or config files — those are already in context.
- If no memories were loaded, omit the Project Memories section entirely.
- Focus on cross-file insights: "the auth module assumes X because of Y" not "the auth module is in src/auth/".
- Update sections that changed, leave accurate ones alone.
- If this is a first-time capsule and you lack history for some sections (Architecture Decisions, Project Health), leave them sparse — they'll fill in over sessions.

### Phase 4: Restore tasks

Invoke `/restore-tasks` to recover tasks from previous sessions on this branch.

### Phase 5: Report

Summarize what you loaded and what you learned. Flag:
- **Gaps**: missing architecture docs, no tests, unclear boundaries
- **Risks**: failing CI, stale PRs, dependency issues, security advisories in deps
- **Blast radius**: files affected by branch changes that aren't on the branch (reverse deps), open PRs touching the same areas
- **CI status**: if builds are failing, include the specific errors/stack traces — don't just say "CI is red"
- **Linked context**: issues/tickets that explain why current work exists, decisions made in PR reviews
- **AGENTS.md flags**: any project-specific rules or priorities that should guide upcoming work
- **Suggestions**: things to address before starting new work

## Capsule Maintenance During Work

Update the capsule when you discover something that belongs there:

- New invariant or implicit rule discovered → add to Key Invariants
- Architecture decision made or understood → add to Architecture Decisions
- Boundary clarified → update Component Boundaries
- PRD moved to done or new PRD started → update Active Work
- GitHub State is NOT maintained during work — refreshed only on catchup runs

Keep updates surgical — change the relevant section, bump the date, move on.

## Error Handling

| Situation | Action |
|-----------|--------|
| On master, no capsule | Load sources + GitHub state, generate capsule, skip branch diff |
| On master, capsule exists | Load sources, check capsule for stale sections, update |
| No remote | Use local master as base for branch diff |
| Detached HEAD | Report current commit, ask user for base branch |
| Not a git repo | Load sources only, skip all git/GitHub operations |
| `gh` not installed/authenticated | Skip GitHub state, note gap in report |
| No GitHub remote | Skip GitHub state, note gap in report |
| GitHub API rate limited | Skip GitHub state, note gap in report |

## Manual Commands

If scripts unavailable:

### Branch diff
```bash
git branch --show-current
git fetch origin master
FORK=$(git merge-base origin/master HEAD)
git diff "$FORK"..HEAD --name-only
git diff "$FORK"..HEAD --stat
git log "$FORK"..HEAD --oneline
git diff "$FORK"..HEAD
```

### GitHub state
```bash
gh issue list --state open --limit 50 --json number,title,labels,createdAt
gh issue list --state open --label "bug" --limit 20 --json number,title
gh pr list --state open --json number,title,author,baseRefName,headRefName,createdAt,updatedAt,reviewDecision,isDraft
git for-each-ref --sort=-committerdate --format='%(refname:short) %(committerdate:short)' refs/remotes/origin/ | head -20
gh release list --limit 3 --json tagName,publishedAt
gh run list --branch master --status failure --limit 10 --json workflowName,createdAt,headSha
gh run list --limit 5 --json workflowName,status,conclusion,headBranch,createdAt
```

### Recent master
```bash
git log --oneline -20 master
```
