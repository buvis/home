# Checkout Pull Request

Checks out a pull request locally for testing and review.

## Usage
```
/pr-checkout [pr-number]
```

## Process

1. **Fetch PR Details**:
   ```bash
   gh pr view $ARGUMENTS
   ```

2. **Checkout PR Branch**:
   ```bash
   gh pr checkout $ARGUMENTS
   ```

3. **Update Branch**:
   ```bash
   git pull origin HEAD
   ```

4. **Show Context**:
   - Display current branch name
   - Show recent commits: `git log --oneline -5`
   - List changed files: `git diff --name-only HEAD~5..HEAD`

Essential for code reviewers who want to test changes locally before approving.