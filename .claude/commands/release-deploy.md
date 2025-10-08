# Release Management & Deployment

Manages application releases with advanced deployment strategies and safety mechanisms.

## Usage
```
/release-deploy [strategy: canary|blue-green|rolling|hotfix]
```

## Process

1. **Deployment Strategy Setup**:
   - Configure deployment strategy (canary, blue-green, rolling)
   - Set up traffic splitting and load balancer rules
   - Prepare health checks and readiness probes
   - Define rollback triggers and success criteria

2. **Pre-deployment Validation**:
   - Run automated tests and security scans
   - Verify infrastructure capacity and readiness
   - Check dependency services and external integrations
   - Validate configuration and environment variables

3. **Execute Gradual Deployment**:
   - Deploy to subset of infrastructure (canary/blue-green)
   - Monitor key metrics during gradual rollout
   - Implement automatic traffic shifting based on health
   - Track error rates, latency, and business metrics

4. **Monitor & Control Release**:
   - Real-time monitoring of deployment health
   - Automatic rollback on threshold violations
   - Manual control points for release progression
   - Stakeholder notifications and status updates

5. **Complete or Rollback**:
   - Full production rollout on success criteria
   - Automatic rollback on failure detection
   - Post-deployment validation and smoke tests
   - Release documentation and lessons learned

Enables zero-downtime deployments with automated safety mechanisms and intelligent rollback capabilities.