# Log Analysis & Debugging

Analyzes log files and system outputs to identify issues and performance problems.

## Usage
```
/logs-analyze [source: file|container|stream|system]
```

## Process

1. **Collect Log Data**:
   - Gather logs from files, containers, or streaming sources
   - Connect to Kubernetes pods, Docker containers, or system logs
   - Parse multiple log formats (JSON, plain text, structured logs)
   - Filter logs by time range, severity, or application component

2. **Parse & Extract Patterns**:
   - Identify error patterns, exceptions, and stack traces
   - Extract performance metrics and timing information
   - Detect anomalies and unusual patterns in log data
   - Correlate events across multiple services and components

3. **Root Cause Analysis**:
   - Connect related events and trace request flows
   - Identify cascade failures and dependency issues
   - Analyze performance degradation and resource bottlenecks
   - Map errors to specific code paths and functions

4. **Generate Insights**:
   - Provide specific recommendations for fixes
   - Suggest preventive measures and monitoring improvements
   - Create actionable debugging steps and investigation plans
   - Generate summary reports with priority issues

Accelerates debugging and troubleshooting by automatically analyzing complex log data and providing actionable insights.