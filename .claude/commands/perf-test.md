# Performance Testing & Benchmarking

Runs comprehensive performance tests and generates optimization recommendations.

## Usage
```
/perf-test [target: api|frontend|database|load]
```

## Process

1. **Setup Test Environment**:
   - Configure performance test scenarios (load, stress, endurance)
   - Set up monitoring and metrics collection
   - Prepare test data and realistic user scenarios
   - Define performance targets and acceptance criteria

2. **Execute Performance Tests**:
   - Run load tests with increasing concurrent users
   - Execute stress tests to find breaking points
   - Perform endurance tests for memory leaks
   - Test database query performance and indexing

3. **Monitor & Collect Metrics**:
   - Track response times, throughput, and error rates
   - Monitor resource usage (CPU, memory, I/O, network)
   - Collect application-specific metrics
   - Record database query performance and slow queries

4. **Analysis & Reporting**:
   - Identify performance bottlenecks and hotspots
   - Generate performance trend analysis
   - Compare results against baseline benchmarks
   - Create actionable optimization recommendations

Creates detailed performance reports with specific improvement suggestions for production optimization.