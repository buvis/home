# Create GitHub Issue

Creates a simple, well-structured GitHub issue for bugs or features.

## Usage
```
/issue-create [brief description]
```

## Process

1. **Understand the Request**: $ARGUMENTS

2. **Research Context**: 
   - Check existing issues for similar requests: `gh issue list --search "$ARGUMENTS"`
   - Review repository structure and relevant files
   - Examine project's issue templates if available

3. **Create Issue**: Generate a clear issue with:
   - Descriptive title following project conventions
   - Problem description or feature request
   - Basic acceptance criteria (2-3 items max)
   - Simple reproduction steps (for bugs)
   - Context and references

4. **Submit**: Use GitHub CLI to create the issue:
   ```bash
   gh issue create --title "[title]" --body "[content]" --label "[appropriate-label]"
   ```

Keep it simple - focus on clarity over completeness. A clear minimal issue is better than a confusing detailed one.