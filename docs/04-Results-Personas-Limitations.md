# Results, Limitations & Personas

**Author:** Uday Tamma | **Document Version:** 1.0 | **Date:** January 2026

---

## Load Test Results

### Test Configuration

| Parameter | Value |
|-----------|-------|
| Environment | Local (M-series Mac) |
| API Workers | 4 uvicorn workers |
| Redis | Single node, local Docker |
| PostgreSQL | Single node, local Docker |
| Test Tool | Locust |
| Duration | 2 minutes |
| Users | 50 concurrent |

### Observed Performance

| Metric | Observed | Target | Status |
|--------|----------|--------|--------|
| **Throughput** | 260 RPS | - | Baseline |
| **P50 Latency** | 22ms | 50ms | 56% buffer |
| **P99 Latency** | 106ms | 200ms | **47% buffer** |
| **Error Rate** | 0.00% | <0.1% | Passing |
| **Failures** | 0 | 0 | Passing |

### Latency Breakdown

```
Total P99: 106ms
├── Feature computation (Redis):  ~50ms (47%)
├── Risk scoring (detection):     ~20ms (19%)
├── Policy evaluation:            ~10ms (9%)
├── Evidence capture (async):     ~20ms (19%)
└── Network/serialization:        ~6ms  (6%)
```

**Key Insight:** Redis velocity lookups dominate latency at 47% of total. At scale, this is the first optimization target.

### Capacity Projection

| Load Level | Est. RPS | Est. P99 | Bottleneck | Mitigation |
|------------|----------|----------|------------|------------|
| Baseline (50 users) | 260 | 106ms | None | - |
| 2x (100 users) | 500 | 130ms | API workers | Add workers |
| 4x (200 users) | 900 | 160ms | Redis connections | Connection pooling |
| 8x (400 users) | 1,500 | 200ms | Redis throughput | Redis Cluster |
| 16x+ (1000 users) | 3,000+ | >200ms | Architecture limit | Kafka + Flink |

### Replay Validation

Using synthetic historical data with known fraud labels:

| Scenario | Transactions | Fraud Injected | Detected | False Positives |
|----------|--------------|----------------|----------|-----------------|
| Normal traffic | 10,000 | 1% (100) | 72/100 | 180/9,900 |
| Card testing attack | 1,000 | 10% (100) | 94/100 | 45/900 |
| Velocity attack | 500 | 20% (100) | 88/100 | 22/400 |
| Mixed realistic | 15,000 | 2% (300) | 221/300 | 195/14,700 |

**Summary:**
- Detection rate: 72-94% depending on attack type
- False positive rate: 1.3-5% depending on scenario
- Card testing attacks have highest detection confidence
- Velocity attacks show strong detection with rule-based approach

---

## Limitations

### Infrastructure Limitations

| Limitation | Impact | Production Path |
|------------|--------|-----------------|
| **Single node architecture** | No failover, limited throughput | Deploy Redis Cluster, PostgreSQL replicas |
| **Local Docker deployment** | Not representative of cloud latency | Deploy to AWS/GCP with network testing |
| **No load balancer** | Single point of failure | Add ALB/NLB with health checks |
| **No auto-scaling** | Cannot handle traffic spikes | Implement Kubernetes HPA |
| **No multi-region** | Geographic latency, DR risk | Deploy to multiple regions |

### Data Limitations

| Limitation | Impact | Mitigation Path |
|------------|--------|-----------------|
| **Synthetic test data** | May not reflect real attack patterns | Shadow deployment on production traffic |
| **No real chargebacks** | Cannot validate label accuracy | Integrate with PSP chargeback feed |
| **Limited feature diversity** | May miss real fraud signals | Add external signals (BIN, device reputation) |
| **No historical baseline** | Cannot compare to existing system | Run parallel with current fraud system |
| **Point-in-time features untested** | Replay may have leakage | Validate with known delayed labels |

### Model Limitations

| Limitation | Impact | Mitigation Path |
|------------|--------|-----------------|
| **Rule-based only** | Lower accuracy than ML | Phase 2 ML integration |
| **No adaptive thresholds** | Static rules don't evolve | Implement threshold optimization |
| **No feedback loop** | Decisions don't improve system | Add analyst feedback to training |
| **Single model** | No redundancy or comparison | Champion/challenger framework |
| **No drift detection** | Model may degrade silently | Implement PSI monitoring |

### Operational Limitations

| Limitation | Impact | Mitigation Path |
|------------|--------|-----------------|
| **No analyst UI** | Manual review is cumbersome | Build case management dashboard |
| **No bulk operations** | Cannot act on patterns efficiently | Add bulk blocklist/threshold tools |
| **Limited alerting** | May miss issues | Full Alertmanager integration |
| **No on-call runbooks** | Incident response unclear | Document response procedures |
| **No disaster recovery** | Single region failure = outage | Multi-region active-passive |

### Honest Assessment

```
What This Proves:
  ✓ Architecture meets latency requirements
  ✓ Detection logic catches known fraud patterns
  ✓ Evidence capture is comprehensive
  ✓ Policy engine is configurable
  ✓ System handles expected load

What This Doesn't Prove:
  ✗ Performance under real production traffic
  ✗ Detection accuracy on real fraud (vs synthetic)
  ✗ ML model performance (not yet implemented)
  ✗ Operational readiness (no real incidents yet)
  ✗ Economic impact (no real financial data)
```

---

## Personas & Dashboard Usage

### Persona 1: Fraud Analyst

**Role:** Reviews flagged transactions, makes manual decisions, investigates patterns

**Primary Dashboard Panels:**

| Panel | Purpose | Key Metrics |
|-------|---------|-------------|
| **Review Queue** | Transactions needing manual decision | Count, age, priority |
| **Decision Distribution** | Current system behavior | ALLOW/FRICTION/REVIEW/BLOCK % |
| **Recent High-Risk** | Emerging patterns | Transactions with score >70% |
| **Triggered Reasons** | Why transactions flagged | Top 10 triggered signals |

**Workflow:**

```
1. Check Review Queue
   └── Sort by priority (HIGH first)
   └── Filter by amount (high value first)

2. For each case:
   └── View transaction details
   └── Review triggered signals
   └── Check customer history
   └── Make decision: APPROVE / DECLINE / ESCALATE

3. Bulk actions:
   └── Add device to blocklist
   └── Add card to blocklist
   └── Flag user for enhanced monitoring

4. End of shift:
   └── Review queue age metrics
   └── Ensure nothing >4h old
```

**Key Decisions:**
- Accept/decline individual transactions
- Add entities to blocklists
- Escalate suspicious patterns to Risk Lead

### Persona 2: Risk Lead / Fraud Manager

**Role:** Sets strategy, monitors KPIs, adjusts thresholds, manages team

**Primary Dashboard Panels:**

| Panel | Purpose | Key Metrics |
|-------|---------|-------------|
| **Approval Rate (24h)** | Customer experience health | Target: >92%, Alert: <90% |
| **Block Rate (24h)** | Fraud prevention activity | Target: <5%, Alert: >8% |
| **Fraud Loss (30d lag)** | Actual financial impact | Rolling 30-day $ |
| **Dispute Win Rate** | Evidence effectiveness | Target: >50% |
| **Review Queue SLA** | Ops efficiency | % within 4h SLA |

**Workflow:**

```
1. Morning Review:
   └── Check 24h approval rate
   └── Review any after-hours alerts
   └── Compare block rate to baseline

2. Weekly Metrics Review:
   └── Fraud rate trend (30d lag)
   └── False positive estimate
   └── Dispute outcomes
   └── Threshold performance

3. Threshold Adjustment:
   └── Run replay simulation on proposed change
   └── Review projected impact
   └── If acceptable: Apply via Policy Settings
   └── Monitor for 48h post-change

4. Incident Response:
   └── Spike in block rate? Check for attack or bug
   └── Drop in approval rate? Check threshold misconfiguration
   └── Latency spike? Escalate to Engineering
```

**Key Decisions:**
- Threshold adjustments (friction/review/block levels)
- Policy rule additions or modifications
- Escalation to Engineering or Security
- Resource allocation (analyst coverage)

### Persona 3: SRE / On-Call Engineer

**Role:** Maintains system reliability, responds to alerts, handles incidents

**Primary Dashboard Panels:**

| Panel | Purpose | Key Metrics |
|-------|---------|-------------|
| **P99 Latency** | System performance | Target: <200ms, Alert: >150ms |
| **Error Rate** | System reliability | Target: <0.1%, Alert: >0.5% |
| **Safe Mode Status** | Fallback state | Normal / SAFE MODE |
| **Component Health** | Dependency status | Redis, PostgreSQL, API status |
| **Throughput** | Traffic volume | RPS vs expected baseline |

**Workflow:**

```
1. Alert Response:
   └── Check alert source and severity
   └── Verify via dashboard (not just alert)
   └── Follow runbook for specific alert type

2. Latency Spike Response:
   └── Check Redis latency panel
   └── Check PostgreSQL latency panel
   └── Identify bottleneck component
   └── Scale or restart as needed

3. Safe Mode Activation:
   └── Automatic if error rate >5%
   └── Manual if component failure detected
   └── Notify Fraud Ops (decisions will be conservative)
   └── Document reason and duration

4. Post-Incident:
   └── Collect metrics from incident window
   └── Write post-mortem
   └── Update runbooks if needed
```

**Key Alerts:**

| Alert | Threshold | Response |
|-------|-----------|----------|
| `FraudDecisionLatencyHigh` | P99 >200ms for 2min | Check Redis, scale API |
| `FraudErrorRateCritical` | >5% for 1min | Safe mode, investigate |
| `FraudSafeModeActive` | Any | Notify stakeholders, investigate |
| `FraudTrafficDrop` | <10 RPS for 5min | Check upstream integration |
| `FraudTrafficSpike` | >2x baseline | Check for attack or event |

---

## Dashboard Mapping

### Demo Dashboard (`dashboard.py`) - Current Implementation

| Tab | Primary Persona | Key Panels |
|-----|-----------------|------------|
| **Transaction Simulator** | Engineer/Demo | Test scenarios, attack presets |
| **Analytics Dashboard** | Risk Lead | Decision distribution, latency charts |
| **Decision History** | Fraud Analyst | Historical decisions with filters |
| **Policy Inspector** | Risk Lead | Current rules, thresholds, lists |
| **Policy Settings** | Risk Lead | Threshold adjustment, rule management |

### Production Dashboard Needs (Gap Analysis)

| Need | Demo Has | Production Needs |
|------|----------|------------------|
| Review queue | No | Yes - Priority sorted, age tracking |
| Case management | No | Yes - Assignment, notes, workflow |
| Bulk actions | No | Yes - Multi-select, batch operations |
| Real-time alerts | No | Yes - Integrated alerting |
| Drill-down | Limited | Yes - Click through to transaction |
| Export | No | Yes - CSV/PDF for investigations |
| Role-based access | No | Yes - Analyst vs Admin views |

---

## Interview Application

**When asked "How would you present results and limitations?":**

> "I'd be transparent about what we've validated and what we haven't. The load test shows we hit 260 RPS at 106ms P99 on local infrastructure - that's 47% headroom to our 200ms SLA. But that's a single-node setup on synthetic data.
>
> Key limitations: we haven't proven this works with real production traffic, real fraud patterns, or real chargebacks. The rule-based detection catches 72-94% of synthetic fraud depending on pattern type, but we need shadow deployment on real traffic to validate.
>
> For dashboards, I'd map them to personas: Fraud Analysts need the review queue and case tools, Risk Leads need the KPI panels and threshold controls, SRE needs the latency and health panels with alert integration. The demo dashboard covers the Risk Lead use case; we'd need to build out the Analyst workflow for production.
>
> The honest answer is: this proves the architecture works, but doesn't prove it works in production until we deploy it in shadow mode on real traffic."

**When asked "What are the known gaps?":**

> "Three categories: infrastructure, data, and operational.
>
> Infrastructure: single-node everything, no auto-scaling, no multi-region. The path is clear - Kubernetes with HPA, Redis Cluster, PostgreSQL replicas - but it's not built yet.
>
> Data: synthetic test data doesn't reflect real attack evolution. We need shadow deployment on production traffic and integration with real chargeback feeds to validate detection accuracy.
>
> Operational: no analyst case management UI, no bulk operations, no real on-call runbooks. The demo dashboard shows the concept, but a Fraud Analyst can't do their job with it in production.
>
> I'd present this honestly to stakeholders: MVP proves the concept, but there's a clear list of work before production readiness."

---

*This document provides an honest assessment of what the system proves and doesn't prove, mapping dashboards to real user personas and their workflows.*
