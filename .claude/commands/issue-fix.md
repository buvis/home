# Fix GitHub Issue

Implements the solution for a GitHub issue following the analysis.

## Usage
```
/issue-fix [issue-number]
```

## Process

1. **Review Issue and Plan**: 
   - Get issue details: `gh issue view $ARGUMENTS`
   - Review any existing implementation plan
   - Confirm current branch is correct

2. **Implement Solution**:
   - Make necessary code changes
   - Follow existing code style and patterns
   - Keep changes focused and minimal

3. **Test Changes**:
   - Run existing tests to ensure nothing breaks
   - Add new tests if needed
   - Verify the fix addresses the issue

4. **Commit Changes**:
   ```bash
   git add .
   git commit -m "fix: resolve issue #$ARGUMENTS - brief description"
   ```

5. **Update Issue**: Add a comment with implementation summary

Focus on simple, working solutions. Don't over-engineer or add unnecessary features.