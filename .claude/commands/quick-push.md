# Quick Push

Adds all changes, commits with message, and pushes to current branch.

## Usage
```
/quick-push [commit message]
```

## Process

1. **Check Current Status**:
   ```bash
   git status --porcelain
   git branch --show-current
   ```

2. **Stage All Changes**:
   ```bash
   git add .
   ```

3. **Commit Changes**:
   ```bash
   git commit -m "$ARGUMENTS"
   ```

4. **Push to Remote**:
   ```bash
   git push origin HEAD
   ```

5. **Confirm**: Show push result and current branch status

Quick way to save and push work-in-progress changes without multiple Git commands.