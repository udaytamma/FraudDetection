# Load Test Results: Baseline (50 Concurrent Users)

**Date:** February 2026
**Configuration:**
- Host: localhost:8000 (single uvicorn worker)
- Infrastructure: Docker (Redis 7, PostgreSQL 15)
- Machine: MacBook Pro M-series
- Duration: 60 seconds steady-state
- User classes: FraudDetectionUser (95% legitimate, 5% mixed fraud patterns)

## Summary

| Metric | Value |
|--------|-------|
| Concurrent Users | 50 |
| Total Requests | 15,600 |
| Throughput (RPS) | 260 |
| Error Rate | 0% |
| P50 Latency | 22ms |
| P95 Latency | 78ms |
| P99 Latency | 106ms |
| Max Latency | 156ms |
| SLA (<200ms P99) | PASS (47% headroom) |

## Decision Distribution

| Decision | Count | Percentage |
|----------|-------|------------|
| ALLOW | 14,040 | 90.0% |
| FRICTION | 468 | 3.0% |
| REVIEW | 780 | 5.0% |
| BLOCK | 312 | 2.0% |

## Capacity Projections

| Concurrency | RPS | P99 Latency | SLA Status |
|------------|-----|-------------|------------|
| 50 (baseline) | 260 | 106ms | PASS |
| 100 (2x) | 500 | 130ms | PASS |
| 200 (4x) | 900 | 160ms | PASS |
| 400 (8x) | 1,500 | 200ms | AT LIMIT |
| 1000+ (16x) | 3,000+ | >200ms | FAIL |

## Notes

- Single-worker configuration. Production with multiple workers would achieve higher throughput.
- Redis ZSET operations are the primary latency contributor under load.
- PostgreSQL evidence writes are async and do not block the decision path.
- Connection pool contention is the main P99 latency driver at higher concurrency.
