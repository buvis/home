# Security Scan

Performs comprehensive security audit of code and dependencies.

## Usage
```
/security-scan [target path]
```

## Process

1. **Dependency Vulnerability Scan**:
   - Check for known CVEs in dependencies
   - Identify outdated packages with security issues
   - Review dependency licenses for compliance
   - Generate vulnerability report

2. **Code Security Analysis**:
   - Scan for common security patterns (OWASP Top 10)
   - Check for hardcoded secrets or credentials
   - Identify SQL injection vulnerabilities
   - Review authentication and authorization

3. **Configuration Security**:
   - Review Docker/Kubernetes configurations
   - Check for exposed services and ports
   - Validate encryption and TLS settings
   - Assess access control policies

4. **Infrastructure Security**:
   - Review CI/CD pipeline security
   - Check environment variable handling
   - Validate secret management practices
   - Assess network security configurations

5. **Security Report**:
   - Prioritized vulnerability list
   - Remediation recommendations
   - Compliance status (SOC2, GDPR, etc.)
   - Action plan with timelines

Ensures code meets production security standards and compliance requirements.