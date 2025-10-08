# Generate Tests

Generates comprehensive test cases for code following Clean Code testing principles.

## Usage
```
/test-generate [description or file path]
```

## Process

1. **Analyze Target Code**:
   - Identify functions, classes, and methods to test
   - Detect testing framework (Jest, PyTest, RSpec, etc.)
   - Understand code structure and dependencies

2. **Generate Test Cases**:
   - Unit tests for individual functions
   - Integration tests for component interactions
   - Edge cases and error conditions
   - Mock objects for external dependencies

3. **Create Test Files**:
   - Follow project naming conventions
   - Include setup and teardown methods
   - Add descriptive test names and comments
   - Structure tests for readability

4. **Coverage Analysis**:
   - Identify uncovered code paths
   - Suggest additional test scenarios
   - Recommend coverage targets

5. **Quality Check**:
   - Verify tests follow testing best practices
   - Ensure tests are independent and repeatable
   - Add assertions for expected behaviors

Generates maintainable test suites that improve code quality and catch regressions.