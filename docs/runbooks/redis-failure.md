# Runbook: Redis Failure

**Severity:** P1 -- Redis is a critical dependency for velocity counters and idempotency cache.

---

## Detection

| Signal | Source | Threshold |
|--------|--------|-----------|
| Health check returns unhealthy | `GET /health` | `redis: false` |
| Redis latency spike | `fraud_redis_latency_ms` (Prometheus) | P99 > 50ms |
| Velocity counter errors | Application logs | `RedisConnectionError` or `TimeoutError` |
| Idempotency fallback activated | Application logs | `idempotency fallback to postgres` |

---

## Diagnosis

**Step 1: Verify Redis connectivity**

```bash
redis-cli -h <REDIS_HOST> -p <REDIS_PORT> ping
# Expected: PONG
```

**Step 2: Check Docker container status**

```bash
docker-compose ps redis
docker logs --tail 100 frauddetection-redis-1
```

**Step 3: Check connection pool**

```bash
redis-cli -h <REDIS_HOST> info clients
# Look at: connected_clients, blocked_clients, rejected_connections
```

**Step 4: Check memory**

```bash
redis-cli -h <REDIS_HOST> info memory
# Look at: used_memory_human, maxmemory, evicted_keys
```

---

## Impact Assessment

| Component | Impact | Fallback |
|-----------|--------|----------|
| Velocity counters | Unavailable -- all velocity features return zero | Zeroed counters (reduced detection accuracy) |
| Idempotency cache | Primary cache unavailable | Falls back to PostgreSQL lookup |
| Feature computation | Partial degradation | Non-Redis features still computed normally |
| Fraud scoring | Operates with incomplete data | Scores based on available features only |

**Key point:** The system does NOT go fully offline when Redis fails. Idempotency falls back to PostgreSQL, and velocity features default to zeroed counters. Detection accuracy is degraded but the `/decide` endpoint remains operational.

---

## Mitigation

### Activate Safe Mode (if detection accuracy is unacceptable)

```bash
export SAFE_MODE_ENABLED=true
export SAFE_MODE_DECISION=REVIEW   # Options: ALLOW, BLOCK, REVIEW
```

Use `REVIEW` to queue transactions for manual review. Use `BLOCK` only if active fraud attack is suspected. See [safe-mode.md](safe-mode.md) for full details.

---

## Recovery

**Step 1: Restart Redis**

```bash
docker-compose restart redis
```

**Step 2: Verify connectivity**

```bash
redis-cli -h <REDIS_HOST> ping
curl -s http://localhost:8000/health | python -m json.tool
# Confirm redis status is healthy
```

**Step 3: Validate counter behavior**

Velocity counters reset to zero on Redis restart. This is expected -- counters will rebuild as new transactions arrive. There is a brief window of reduced detection accuracy for velocity-based rules.

**Step 4: Deactivate Safe Mode (if activated)**

```bash
export SAFE_MODE_ENABLED=false
```

**Step 5: Monitor post-recovery (30 minutes)**

| Metric | Expected Range | Dashboard |
|--------|---------------|-----------|
| Approval rate | Within 2% of baseline | Grafana: Fraud Overview |
| `fraud_redis_latency_ms` P99 | &lt;10ms | Grafana: Infrastructure |
| Velocity counter hit rate | Increasing toward baseline | Application logs |
| Error rate | 0% Redis errors | Grafana: Error Rate |

---

## Escalation

| Condition | Action |
|-----------|--------|
| Redis does not recover after restart | Check disk, memory, and Docker host resources |
| Repeated failures within 24 hours | Investigate Redis persistence config and host stability |
| Approval rate anomaly post-recovery | Keep safe mode active, escalate to Fraud Ops |
