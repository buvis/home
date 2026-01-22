---
name: Catch Up
description: Review branch changes since fork point from main/master
---

# Catch Up on Branch Changes

## Objective

Review changes made specifically on the current branch since it forked from the base branch (main/master). Uses the fork-point to ensure only this branch's commits are shown, excluding changes from other branches or commits already on the base.

## Steps

1. Get the current branch name and verify we're not on master/main
2. Detect the base branch:
   - Check if `origin/main` exists, otherwise use `origin/master`
   - Run `git fetch origin <base>` to ensure we have the latest
3. Find the fork point: `git merge-base origin/<base> HEAD`
4. Run `git diff <fork-point>..HEAD --name-only` to get list of changed files (only on this branch)
5. Run `git diff <fork-point>..HEAD --stat` to get a summary of changes
6. Run `git log <fork-point>..HEAD --oneline` to get the commit history for this branch only
7. Read and analyze the most important changed files (prioritize: manifests, configs, core logic files)
8. Provide a high-level summary including:
   - Branch purpose and scope of changes
   - Key files modified and their significance
   - Potential impact areas
   - Any notable patterns or architectural changes
   - Suggested review focus areas
