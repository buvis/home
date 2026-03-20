# Git Conflict Commands Reference

## Diagnostic Commands

### Identify Operation Type
```bash
git status
```

Then check for specific operation markers (each as a separate Bash call):
```bash
ls .git/MERGE_HEAD
```
```bash
ls .git/CHERRY_PICK_HEAD
```
```bash
test -d .git/rebase-merge
```
```bash
test -d .git/rebase-apply
```

The exit code tells you the operation type. Don't use `2>/dev/null`.

### List Conflicted Files
```bash
git diff --name-only --diff-filter=U
```

### See Conflict Details
```bash
# Show conflict markers in file
git diff <file>

# Show three-way diff (ours, base, theirs)
git diff --cc <file>

# Check for whitespace issues
git diff --check
```

### Inspect Versions
```bash
# Base version (common ancestor)
git show :1:<file>

# Ours version
git show :2:<file>

# Theirs version
git show :3:<file>

# What commit is causing conflict (rebase/cherry-pick) — run each separately
git log -1 REBASE_HEAD
git log -1 CHERRY_PICK_HEAD
```

### Understand History
```bash
# Common ancestor
git merge-base HEAD MERGE_HEAD

# Graph of diverged history
git log --oneline --graph HEAD MERGE_HEAD ^$(git merge-base HEAD MERGE_HEAD)
```

## Resolution Commands

### Pick One Side
```bash
# Keep ours (see terminology.md for meaning!)
git checkout --ours <file>
git add <file>

# Keep theirs
git checkout --theirs <file>
git add <file>
```

### After Manual Edit
```bash
git add <file>
```

### For Deleted Files
```bash
# Accept deletion
git rm <file>

# Keep the file
git add <file>
```

## Continue Commands

```bash
# After merge conflicts resolved
git commit

# After rebase conflicts resolved
git rebase --continue

# After cherry-pick conflicts resolved
git cherry-pick --continue
```

## Abort Commands

```bash
git merge --abort
git rebase --abort
git cherry-pick --abort
```

## Rerere (Reuse Recorded Resolution)

```bash
# Check if rerere auto-resolved anything
git rerere status
git rerere diff

# Enable globally (recommended)
git config --global rerere.enabled true

# Auto-stage rerere resolutions
git config --global rerere.autoupdate true
```

## Better Conflict Display

```bash
# Enable diff3 style (shows common ancestor)
git config --global merge.conflictstyle zdiff3

# Or for current merge only
git checkout --conflict=diff3 <file>
```

## Skip Commit (Rebase Only)

```bash
# Skip problematic commit entirely
git rebase --skip
```
