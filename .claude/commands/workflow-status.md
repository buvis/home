# Check Workflow Status

Quick status check for GitHub issue workflow progress.

## Usage
```
/workflow-status
```

## Process

1. **Check Current Branch**:
   ```bash
   git branch --show-current
   git status
   ```

2. **List Open Issues** (assigned to you):
   ```bash
   gh issue list --assignee @me --state open
   ```

3. **Check Open PRs**:
   ```bash
   gh pr list --author @me --state open
   ```

4. **Recent Activity**:
   ```bash
   gh issue list --author @me --limit 5
   gh pr list --author @me --limit 5
   ```

5. **Summary**: Provide a brief overview of:
   - Current work in progress
   - Open issues and PRs
   - Next steps or blockers

Simple status overview to help track GitHub workflow progress.