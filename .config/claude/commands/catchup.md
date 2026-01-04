# Catch Up on Branch Changes

## Objective

This command reviews all changes between the current branch and its base branch (usually master, develop or main), analyzes key files, and provides a comprehensive summary to help you catch up on what's been done.

## Steps

Instructions are given for master base branch; adjust accordingly if your base branch is different.

1. Get the current branch name and verify we're not on master
2. Run `git fetch origin master` to ensure we have the latest master branch
3. Run `git diff master...HEAD --name-only` to get list of changed files
4. Run `git diff master...HEAD --stat` to get a summary of changes
5. Run `git log master..HEAD --oneline` to get the commit history for this branch
6. Read and analyze the most important changed files (prioritize: manifests, configs, core logic files)
7. Provide a high-level summary including:
   - Branch purpose and scope of changes
   - Key files modified and their significance
   - Potential impact areas
   - Any notable patterns or architectural changes
   - Suggested review focus areas
