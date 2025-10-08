# Branch Cleanup

Cleans up merged branches and removes stale tracking branches.

## Usage
```
/branch-cleanup
```

## Process

1. **Show Current State**:
   ```bash
   git branch -a
   git remote prune origin --dry-run
   ```

2. **List Merged Branches**:
   ```bash
   git branch --merged | grep -v -E "(main|master|develop|staging)"
   ```

3. **Delete Merged Local Branches**:
   ```bash
   git branch --merged | grep -v -E "(main|master|develop|staging|\*)" | xargs -n 1 git branch -d
   ```

4. **Clean Remote Tracking**:
   ```bash
   git remote prune origin
   git fetch --prune
   ```

5. **Summary**: Show remaining branches and any cleanup performed

Keeps your local repository clean by removing branches that have been merged into main branches.