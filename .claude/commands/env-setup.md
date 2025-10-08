# Environment Configuration & Setup

Configures development and deployment environments with Infrastructure as Code.

## Usage
```
/env-setup [environment: dev|staging|prod|k8s|docker]
```

## Process

1. **Detect Current Environment**:
   - Analyze existing configuration files and infrastructure
   - Identify required tools, frameworks, and dependencies
   - Check system requirements and compatibility
   - Review current environment variables and secrets

2. **Configure Development Tools**:
   - Set up language-specific development environments
   - Configure linting, formatting, and testing tools
   - Install and configure debugging and profiling tools
   - Set up IDE/editor configurations and plugins

3. **Infrastructure Generation**:
   - Generate Kubernetes manifests (deployments, services, ingress)
   - Create Docker configurations and multi-stage builds
   - Set up CI/CD pipeline configurations
   - Generate infrastructure as code (Terraform, Helm charts)

4. **Environment Validation**:
   - Test development environment setup and tools
   - Validate infrastructure configurations and deployments
   - Check connectivity and service dependencies
   - Verify security configurations and access controls

5. **Documentation & Runbooks**:
   - Create setup documentation and installation guides
   - Generate runbooks for common operations
   - Document troubleshooting and maintenance procedures
   - Create environment-specific configuration references

Ensures consistent, reproducible environments across development, staging, and production.