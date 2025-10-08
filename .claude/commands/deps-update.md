# Smart Dependency Management

Analyzes and safely updates project dependencies with security and compatibility checks.

## Usage
```
/deps-update [scope: security|minor|major|all]
```

## Process

1. **Scan Dependencies**:
   - Analyze package files (requirements.txt, Cargo.toml, package.json, go.mod)
   - Identify outdated packages and available updates
   - Check for known security vulnerabilities (CVEs)
   - Review dependency licenses for compliance

2. **Security Assessment**:
   - Prioritize security updates and critical vulnerabilities
   - Check OWASP dependency vulnerability database
   - Analyze transitive dependency risks
   - Generate security risk report

3. **Compatibility Testing**:
   - Run automated tests with updated dependencies
   - Check for breaking changes in major version updates
   - Validate API compatibility and deprecation warnings
   - Test build process and deployment compatibility

4. **Safe Updates**:
   - Apply security patches first (highest priority)
   - Update minor versions with low risk
   - Stage major version updates for review
   - Create separate commits for each update category

5. **Validation Report**:
   - Document all changes and potential impacts
   - Create rollback plan for problematic updates
   - Generate dependency audit report
   - Schedule follow-up monitoring

Keeps dependencies secure and up-to-date while minimizing breaking changes.