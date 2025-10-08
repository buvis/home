# Observability & Monitoring Setup

Sets up comprehensive monitoring, metrics, and alerting for applications and infrastructure.

## Usage
```
/monitor-setup [type: app|infra|k8s|database]
```

## Process

1. **Configure Monitoring Stack**:
   - Set up Prometheus for metrics collection
   - Configure Grafana dashboards and visualizations
   - Install alert manager for notification routing
   - Set up log aggregation (ELK/EFK stack)

2. **Instrument Applications**:
   - Add application metrics and health checks
   - Configure distributed tracing (Jaeger/Zipkin)
   - Set up custom business metrics and SLIs
   - Implement structured logging with context

3. **Create Alert Rules**:
   - Define SLA-based alerting thresholds
   - Configure escalation policies and routing
   - Set up intelligent alert grouping and suppression
   - Create runbooks for common alert scenarios

4. **Build Dashboards**:
   - Create service-level monitoring dashboards
   - Set up infrastructure monitoring views
   - Build business metrics and KPI dashboards
   - Configure team-specific monitoring perspectives

Provides comprehensive observability into application performance, infrastructure health, and business metrics with proactive alerting.