# Fraud Detection Load Tests

Locust-based load testing suite for the Fraud Detection API.

## Quick Start

```bash
# 1. Start infrastructure
docker-compose up -d

# 2. Start API server
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4

# 3. Run load test
cd loadtest
locust -f locustfile.py --host=http://localhost:8000

# 4. Open web UI
# http://localhost:8089
```

## Test Scenarios

### Mixed Traffic (Default)
Realistic traffic mix with fraud injection:
- 95% legitimate transactions
- 2% card testing attacks
- 1% fraud ring patterns
- 1% geo anomaly
- 1% high-value new user

```bash
locust -f locustfile.py --host=http://localhost:8000
```

### Steady State (Baseline)
Only legitimate traffic for clean performance baseline:

```bash
locust -f locustfile.py --host=http://localhost:8000 -u SteadyStateUser
```

### Card Testing Attack
Simulate dedicated card testing attackers:

```bash
locust -f locustfile.py --host=http://localhost:8000 -u CardTestingUser
```

## Headless Mode (CI/CD)

```bash
locust -f locustfile.py \
  --host=http://localhost:8000 \
  --users 100 \
  --spawn-rate 10 \
  --run-time 5m \
  --headless \
  --csv=results/load_test
```

## Distributed Testing

For high RPS (>5000), run in distributed mode:

```bash
# Master node
locust -f locustfile.py --master --host=http://localhost:8000

# Worker nodes (run on multiple machines/terminals)
locust -f locustfile.py --worker --master-host=localhost
```

## Key Metrics

| Metric | Target | SLA |
|--------|--------|-----|
| P50 Latency | <50ms | - |
| P95 Latency | <150ms | - |
| P99 Latency | <200ms | Hard limit |
| Error Rate | <0.1% | <1% |

## Files

- `locustfile.py` - Main test scenarios and user classes
- `data_generator.py` - Realistic transaction data generation

## Documentation

Full documentation: http://localhost:4001/docs/fraud-platform/08-load-testing
