# Docker Optimize

Optimizes Docker images for size, security, and performance.

## Usage
```
/docker-optimize [Dockerfile path]
```

## Process

1. **Analyze Current Dockerfile**:
   - Review current image structure
   - Identify optimization opportunities
   - Check base image choices
   - Analyze layer efficiency

2. **Multi-stage Build Setup**:
   - Separate build and runtime stages
   - Minimize runtime image size
   - Copy only necessary artifacts
   - Use slim or distroless base images

3. **Layer Optimization**:
   - Combine RUN commands to reduce layers
   - Optimize package installation order
   - Remove package managers and caches
   - Use .dockerignore effectively

4. **Security Hardening**:
   - Use non-root user
   - Remove unnecessary packages
   - Set proper file permissions
   - Implement health checks

5. **Validation & Metrics**:
   - Compare before/after image sizes
   - Verify functionality remains intact
   - Test build speed improvements
   - Generate optimization report

Creates production-ready Docker images optimized for Kubernetes deployments.