---
name: catchup
description: Review branch changes since fork point from master. Use when resuming work on a branch or onboarding to existing changes. Triggers on "catch up", "catchup", "what changed on this branch", "summarize branch changes", "review branch".
---

# Catch Up on Branch Changes

Review changes made on current branch since it forked from base.

## Workflow

### 1. Run branch diff script

```bash
~/.claude/skills/catchup/scripts/branch-diff.sh
```

This outputs:
- Branch name and base branch
- Changed files list
- Diff stats (insertions/deletions)
- Commit history

### 2. Analyze changes

Load project architecture context alongside the diff: AGENTS.md, agent_docs/, or any `.local/` architecture notes. This enables cross-cutting impact analysis.

With 1M context, load the full diff even for large branches rather than sampling.

Prioritize reading (in order):
1. Config files (package.json, tsconfig, etc.)
2. Schema/model changes
3. Core logic files (most insertions)
4. Test files

### 3. Summarize

Provide high-level summary:
- **Purpose**: What this branch accomplishes
- **Scope**: Key files/areas modified
- **Impact**: What parts of system affected
- **Cross-cutting impact**: What invariants or boundaries might be affected across the system, not just within changed files
- **Patterns**: Any architectural changes
- **Review focus**: Suggested areas to examine closely

### 4. Restore tasks

Invoke `/restore-tasks` to recover any tasks from previous sessions on this branch.

## Manual Commands

If script unavailable:

```bash
# Get current branch
git branch --show-current

# Fetch latest
git fetch origin master

# Find fork point
git merge-base origin/master HEAD

# Changed files
git diff $(git merge-base origin/master HEAD)..HEAD --name-only

# Diff stats
git diff $(git merge-base origin/master HEAD)..HEAD --stat

# Commit log
git log $(git merge-base origin/master HEAD)..HEAD --oneline
```

## Error Handling

| Situation | Action |
|-----------|--------|
| On master | Report "Already on base branch, nothing to compare" |
| No remote | Use local master as base |
| Detached HEAD | Report current commit, ask user for base branch |
