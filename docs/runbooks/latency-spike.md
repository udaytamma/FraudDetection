# Runbook: Latency Spike

**Severity:** P2 -- Latency exceeding SLA degrades merchant experience and may cause timeouts.

**SLA Target:** P99 &lt; 200ms end-to-end for `/decide` endpoint.

---

## Detection

| Signal | Source | Threshold |
|--------|--------|-----------|
| E2E latency alert | `fraud_e2e_latency_ms` (Prometheus) | P99 > 150ms (warning), P99 > 200ms (critical) |
| Upstream timeouts | Merchant/gateway logs | HTTP 504 or client-side timeout |
| Request queue depth | `uvicorn` metrics | Growing backlog |

---

## Diagnosis

### Step 1: Identify the slow component

Check each component's latency metric to isolate the bottleneck:

| Component | Metric | Normal P99 |
|-----------|--------|------------|
| Feature computation | `fraud_feature_latency_ms` | &lt;20ms |
| Scoring engine | `fraud_scoring_latency_ms` | &lt;10ms |
| Policy evaluation | `fraud_policy_latency_ms` | &lt;5ms |
| Evidence capture (Postgres) | `fraud_postgres_latency_ms` | &lt;30ms |
| Redis operations | `fraud_redis_latency_ms` | &lt;10ms |
| **Total E2E** | `fraud_e2e_latency_ms` | **&lt;100ms** |

```bash
# Quick check via Prometheus query
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,fraud_e2e_latency_ms_bucket)'
```

### Step 2: Check infrastructure health

```bash
# Redis latency
redis-cli --latency -h <REDIS_HOST>

# PostgreSQL active queries
docker exec frauddetection-postgres-1 psql -U fraud -c \
  "SELECT pid, now() - pg_stat_activity.query_start AS duration, query
   FROM pg_stat_activity WHERE state = 'active' ORDER BY duration DESC LIMIT 10;"

# Uvicorn worker load
ps aux | grep uvicorn | wc -l
```

---

## Common Causes and Fixes

### Redis connection exhaustion

**Symptoms:** `fraud_redis_latency_ms` spikes, connection timeout errors in logs.

**Fix:**
```bash
# Check current connections
redis-cli -h <REDIS_HOST> info clients

# If near max, increase pool size in config
export REDIS_POOL_MAX_CONNECTIONS=50  # Default: 20
```

### PostgreSQL evidence write slow

**Symptoms:** `fraud_postgres_latency_ms` spikes, rest of pipeline is normal.

**Fix:**
```bash
# Check for lock contention
docker exec frauddetection-postgres-1 psql -U fraud -c \
  "SELECT * FROM pg_locks WHERE NOT granted;"

# Check table bloat
docker exec frauddetection-postgres-1 psql -U fraud -c \
  "SELECT relname, n_dead_tup, last_autovacuum FROM pg_stat_user_tables;"

# If bloated, trigger manual vacuum
docker exec frauddetection-postgres-1 psql -U fraud -c "VACUUM ANALYZE evidence;"
```

**Quick mitigation:** Switch evidence capture to fire-and-forget mode to remove it from the hot path:

```bash
export EVIDENCE_CAPTURE_MODE=async  # Default: sync
```

Note: In async mode, evidence writes are best-effort. A crash before write completes will lose that evidence record.

### High traffic volume

**Symptoms:** All component latencies increase proportionally, CPU utilization high.

**Fix:**
```bash
# Scale uvicorn workers (rule of thumb: 2 * CPU cores + 1)
uvicorn src.api.main:app --workers 4 --port 8000

# Verify worker count
ps aux | grep uvicorn
```

### Slow feature computation

**Symptoms:** `fraud_feature_latency_ms` dominates E2E time.

**Fix:** Check if external lookups (geo, BIN) are timing out. Consider caching results or increasing timeout thresholds.

---

## Scaling Checklist

If latency is driven by sustained load rather than a transient spike:

| Action | Config / Command | Effect |
|--------|-----------------|--------|
| Add uvicorn workers | `--workers N` | Parallel request handling |
| Increase Redis pool | `REDIS_POOL_MAX_CONNECTIONS=50` | More concurrent Redis ops |
| Async evidence capture | `EVIDENCE_CAPTURE_MODE=async` | Remove Postgres from hot path |
| Connection pooling (Postgres) | `POSTGRES_POOL_SIZE=10` | Reduce connection overhead |
| Rate limiting | Tune `RATE_LIMIT_PER_MINUTE` | Shed excess load |

---

## Escalation

| Condition | Action |
|-----------|--------|
| P99 > 200ms for > 5 minutes | Activate async evidence capture, scale workers |
| P99 > 500ms | Activate safe mode, investigate root cause |
| Latency normal but throughput dropping | Check for connection leaks, restart workers |
| Infrastructure metrics normal but latency high | Profile application code, check for lock contention |
