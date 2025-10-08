# Create Pull Request

Creates a pull request for completed work on an issue.

## Usage
```
/pr-create [issue-number]
```

## Process

1. **Prepare Branch**:
   - Ensure all changes are committed
   - Push branch: `git push origin current-branch`
   - Run final tests and linting

2. **Create PR Description**:
   - Reference the issue: "Closes #$ARGUMENTS"
   - Briefly describe what was changed
   - List any testing done
   - Mention any breaking changes

3. **Create Pull Request**:
   ```bash
   gh pr create --title "Fix #$ARGUMENTS: brief description" --body "[description]"
   ```

4. **Link to Issue**: Ensure PR properly references the issue

5. **Request Review**: Add appropriate reviewers if needed

Keep PR descriptions concise but informative. Focus on what changed and why.