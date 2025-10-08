# Analyze GitHub Issue

Analyzes an existing GitHub issue and creates an implementation plan.

## Usage
```
/issue-analyze [issue-number]
```

## Process

1. **Fetch Issue Details**: 
   ```bash
   gh issue view $ARGUMENTS
   ```

2. **Understand Requirements**:
   - Read issue description and comments
   - Identify key requirements
   - Note any constraints or dependencies

3. **Examine Codebase**:
   - Find relevant files and functions
   - Understand current implementation
   - Identify areas that need changes

4. **Create Implementation Plan**:
   - List 3-5 main tasks needed
   - Identify potential risks or challenges
   - Suggest approach and files to modify

5. **Create Branch**: 
   ```bash
   git checkout -b feature/issue-$ARGUMENTS-brief-description
   ```

Present a simple plan and ask for approval before starting work.