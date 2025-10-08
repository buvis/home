# Bug Report

Creates a structured bug report issue with system context and error details.

## Usage
```
/bug-report [brief description]
```

## Process

1. **Gather System Context**:
   - Operating system and version
   - Browser/environment details
   - Project version or commit hash: `git rev-parse --short HEAD`

2. **Collect Error Information**:
   - Recent error logs if available
   - Stack traces or console errors
   - Steps that led to the bug

3. **Check for Existing Issues**:
   ```bash
   gh issue list --search "bug $ARGUMENTS" --state open
   ```

4. **Create Bug Issue**:
   ```bash
   gh issue create --title "🐛 Bug: $ARGUMENTS" --label "bug" --body "[structured content]"
   ```

Creates detailed bug reports with context, making them easier to reproduce and fix.