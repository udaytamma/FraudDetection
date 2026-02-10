# Runbook: Safe Mode

**Purpose:** Safe mode is an operational override that bypasses fraud scoring and returns a preconfigured decision for all `/decide` requests. It is the primary circuit breaker for the fraud detection platform.

---

## When to Activate

| Scenario | Recommended Decision | Reason |
|----------|---------------------|--------|
| Redis failure (velocity counters unavailable) | `REVIEW` | Scoring accuracy degraded, queue for manual review |
| PostgreSQL failure (evidence capture down) | `REVIEW` | Decisions still possible but unauditable |
| False positive spike (legitimate transactions blocked) | `ALLOW` | Stop blocking good transactions while investigating |
| Suspicious approval rate drop | `REVIEW` | Possible rule misconfiguration, queue for human review |
| Active fraud attack with high volume | `BLOCK` | Block all transactions until attack is mitigated |
| New deployment with unexpected behavior | `REVIEW` | Isolate new code from production decisions |

---

## How to Toggle

### Activate

```bash
export SAFE_MODE_ENABLED=true
export SAFE_MODE_DECISION=REVIEW   # Options: ALLOW, BLOCK, REVIEW
```

For containerized deployments, update the environment in `docker-compose.yml` or your orchestrator and restart:

```yaml
environment:
  SAFE_MODE_ENABLED: "true"
  SAFE_MODE_DECISION: "REVIEW"
```

### Deactivate

```bash
export SAFE_MODE_ENABLED=false
```

### Verify current state

```bash
curl -s http://localhost:8000/health | python -m json.tool
# Check: safe_mode field in response
```

---

## Behavior in Safe Mode

| Component | Behavior |
|-----------|----------|
| `/decide` endpoint | Returns `SAFE_MODE_DECISION` for all requests |
| Velocity counters | Bypassed (not read or incremented) |
| Feature computation | Bypassed |
| Scoring engine | Bypassed |
| Policy evaluation | Bypassed |
| Evidence capture | Active -- records are written with zeroed scores and `safe_mode: true` flag |
| Idempotency | Active -- duplicate requests still return consistent responses |
| Health endpoint | Reports `safe_mode: true` |

**Important:** Evidence is still captured during safe mode. This ensures an audit trail exists and allows post-incident analysis of transactions that were processed under safe mode.

---

## Stakeholder Notification

Notify the following immediately upon activation:

| Audience | Channel | Message Template |
|----------|---------|-----------------|
| Fraud Ops team | Slack: `#fraud-ops` | Safe mode activated. Decision: `{DECISION}`. Reason: `{REASON}`. |
| On-call engineer | PagerDuty | Link to this runbook and incident channel |
| Incident channel | Slack: `#incidents` | Safe mode active for fraud platform. All `/decide` returning `{DECISION}`. |

**Document in the incident timeline:**
- Activation time (UTC)
- Reason for activation
- Configured decision (ALLOW / BLOCK / REVIEW)
- Who activated it

---

## Recovery

### Step 1: Fix the root cause

Resolve the underlying issue that triggered safe mode. Refer to the relevant runbook:
- Redis failure: [redis-failure.md](redis-failure.md)
- Latency spike: [latency-spike.md](latency-spike.md)

### Step 2: Verify system health

```bash
curl -s http://localhost:8000/health | python -m json.tool
# All components should report healthy
```

### Step 3: Deactivate safe mode

```bash
export SAFE_MODE_ENABLED=false
```

### Step 4: Monitor for 30 minutes

| Metric | What to Watch | Action if Anomalous |
|--------|--------------|---------------------|
| Approval rate | Should return to baseline within 5-10 minutes | Re-enable safe mode, escalate |
| Fraud rate | No sudden spike post-recovery | Re-enable safe mode with `BLOCK` |
| E2E latency | P99 &lt; 200ms | See [latency-spike.md](latency-spike.md) |
| Error rate | 0% application errors | Check logs, consider rollback |
| Velocity counters | Rebuilding (values increasing from zero) | Expected behavior, no action needed |

### Step 5: Close out

**Document in the incident timeline:**
- Deactivation time (UTC)
- Duration of safe mode
- Total transactions processed under safe mode
- Any follow-up actions required

---

## Decision Guide

Use this flowchart to choose the correct `SAFE_MODE_DECISION`:

```
Is there an active fraud attack?
  YES --> BLOCK
  NO  --> Is the issue causing false positives (blocking good transactions)?
            YES --> ALLOW
            NO  --> REVIEW
```

| Decision | Use When | Risk |
|----------|----------|------|
| `ALLOW` | False positive spike, legitimate traffic being blocked | Fraud may pass through undetected |
| `BLOCK` | Active attack, compromised scoring | Legitimate transactions will be blocked |
| `REVIEW` | Uncertain situation, partial degradation | Manual review queue will grow; ensure staffing |
