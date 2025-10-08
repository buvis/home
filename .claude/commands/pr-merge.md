# Merge Pull Request

Merges a pull request and cleans up the branch.

## Usage
```
/pr-merge [pr-number]
```

## Process

1. **Check PR Status**:
   ```bash
   gh pr view $ARGUMENTS
   gh pr checks $ARGUMENTS
   ```

2. **Verify Ready to Merge**:
   - All checks passing
   - Required reviews approved
   - No merge conflicts

3. **Merge Pull Request**:
   ```bash
   gh pr merge $ARGUMENTS --squash --delete-branch
   ```

4. **Update Local**:
   ```bash
   git checkout main
   git pull origin main
   ```

5. **Cleanup**: Remove local branch if it exists

Completes the workflow by merging approved PRs and cleaning up branches automatically.