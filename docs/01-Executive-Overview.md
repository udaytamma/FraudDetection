# Telco Payment Fraud Detection Platform
## Executive Overview

**Author:** Uday Tamma | **Document Version:** 1.0 | **Date:** January 2026

---

## Problem & Context

### The Business Challenge

A mid-size Telco/MSP operator faces significant payment fraud exposure across SIM activations, device upgrades, mobile top-ups, and international service enablement.

| Challenge | Current State | Business Impact |
|-----------|--------------|-----------------|
| **Annual Fraud Loss** | $2.4M+ (1.8% of payment volume) | Direct P&L hit |
| **False Positive Rate** | 18% of blocks are legitimate | $800K+ lost revenue annually |
| **Decision Latency** | 2-3 seconds (batch scoring) | Poor UX, cart abandonment |
| **Manual Review Volume** | 12% of transactions | $400K+ ops cost, 4-hour SLA |
| **Chargeback Win Rate** | 22% | Recoverable losses left on table |

### Root Cause Analysis

1. **Batch-based detection** cannot catch velocity attacks that complete in minutes
2. **Static rules** cannot adapt to evolving fraud patterns (SIM farms, device resale rings)
3. **Insufficient evidence capture** leads to losing winnable disputes
4. **No profit-based thresholds** results in over-blocking legitimate customers

---

## Goals & Constraints

### Target Metrics

| Metric | Current | Target | Constraint |
|--------|---------|--------|------------|
| **Approval Rate** | 88% | >92% | Cannot drop below 90% |
| **Fraud Rate** | 1.8% | <0.8% | Industry benchmark |
| **P99 Latency** | 2,300ms | <200ms | Hard SLA requirement |
| **Manual Review** | 12% | <3% | Ops budget constraint |
| **Dispute Win Rate** | 22% | >50% | Evidence quality dependent |
| **False Positive Rate** | 18% | <10% | Customer experience KPI |

### Non-Negotiable Constraints

- **<200ms P99 latency** - Payments cannot wait for fraud decisions
- **Exactly-once semantics** - No duplicate charges or blocks
- **PCI/PII compliance** - No raw PAN in fraud platform
- **99.9% availability** - Revenue-critical path

---

## Solution at a Glance

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Payment Gateway                         │
└─────────────────────────────┬───────────────────────────────┘
                              │ POST /decide (<200ms)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Fraud Detection API                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Feature  │  │Detection │  │  Risk    │  │  Policy  │    │
│  │ Engine   │  │ Engine   │  │ Scoring  │  │  Engine  │    │
│  │  (50ms)  │  │  (20ms)  │  │  (20ms)  │  │  (10ms)  │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
└───────┼─────────────┼─────────────┼─────────────┼──────────┘
        │             │             │             │
   ┌────▼────┐   ┌────▼────┐                 ┌────▼────┐
   │  Redis  │   │ Detect  │                 │  YAML   │
   │Velocity │   │5 Signal │                 │Hot-Load │
   │Counters │   │ Types   │                 │ Config  │
   └─────────┘   └─────────┘                 └─────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   PostgreSQL    │
                    │ Evidence Vault  │
                    └─────────────────┘
```

### Key Design Choices

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Streaming vs. Batch** | Real-time API | Velocity attacks complete in minutes |
| **ML vs. Rules** | Rule-based + ML ensemble (gated) | Faster to market, interpretable |
| **Feature Store** | Redis velocity counters | Sub-ms lookups, sliding windows |
| **Policy Engine** | YAML + hot-reload | Business can adjust without deploys |
| **Evidence Storage** | PostgreSQL (immutable) | Dispute representment requirement |

### Detection Coverage (5 Signal Types)

1. **Card Testing** - Rapid small transactions, BIN probing, decline patterns
2. **Velocity Attacks** - Multi-card device, multi-device card, IP clustering
3. **Geographic Anomaly** - Country mismatch, impossible travel, datacenter IPs
4. **Bot/Automation** - Emulators, rooted devices, Tor exit nodes
5. **Friendly Fraud** - Historical chargebacks, refund abuse patterns

---

## Phased Roadmap

### Phase 1: MVP (Sprint 1-2) - COMPLETE

Real-time decisioning foundation with rule-based detection and gated ML scoring.

**Deliverables:**
- Decision API with <200ms P99 latency
- 5 detection signal types
- Redis velocity counters (card, device, IP, user)
- YAML policy engine with hot-reload
- Immutable evidence vault
- Prometheus/Grafana monitoring
- Chargeback + refund ingestion endpoints (manual feed)
- Test suite includes 190+ pytest cases; measured 260 RPS at 106ms P99 on a single worker (higher capacity is projected, not measured)

**Current Status:** MVP complete, ready for shadow deployment

### Phase 2: Hybrid ML + Experiments (Sprint 3-4)

Layer ML scoring while maintaining policy control (implemented behind `ML_ENABLED`).

**Deliverables:**
- XGBoost/LightGBM criminal fraud model (implemented)
- Champion/challenger routing framework (implemented)
- Historical replay for threshold simulation (implemented via `scripts/replay_analysis.py`)
- Economic optimization UI for business users
- Automated chargeback + refund ingestion and labeling

**ML Model Specification:**
- Features: 25+ velocity + behavioral + entity features
- Labels: Chargebacks linked with 120-day maturity window
- Training: Weekly retraining with point-in-time features (pipeline implemented; scheduler TBD)
- Deployment: Shadow mode first; traffic split configurable (default 80/15/5)

### Phase 3: Scale & External Signals (Sprint 5-6)

Production hardening and expanded detection.

**Deliverables:**
- Multi-region deployment (Redis Cluster, PostgreSQL replicas)
- External signal integration (BIN intelligence, consortium data)
- Enhanced analyst tooling (case management, bulk actions)
- IRSF detection for international calls
- SIM swap correlation for ATO detection

---

## Impact Summary

### Projected Before/After Metrics

| Metric | Before | After (Phase 1) | After (Phase 2) | Methodology |
|--------|--------|-----------------|-----------------|-------------|
| **Approval Rate** | 88% | 91% | 93% | Threshold optimization |
| **Fraud Rate** | 1.80% | 1.20% | 0.75% | Velocity detection |
| **P99 Latency** | 2,300ms | 106ms | 120ms | Measured in load test |
| **Manual Review** | 12% | 5% | 2% | Automation + confidence |
| **False Positives** | 18% | 12% | 8% | Better signals |
| **Dispute Win Rate** | 22% | 40% | 55% | Evidence capture |

*Note: Approval rate, fraud rate, manual review, false positives, and dispute win rate are modeled projections, not measured in the MVP.*

### Financial Impact Model

| Line Item | Annual Impact |
|-----------|---------------|
| Fraud loss reduction (1.05% improvement) | +$1,400,000 |
| False positive recovery (6% improvement) | +$300,000 |
| Ops cost reduction (10% less manual review) | +$200,000 |
| Dispute win improvement (+28% win rate) | +$150,000 |
| **Net Annual Benefit** | **+$2,050,000** |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Redis failure | Low | High | Fallback to safe mode, cached features |
| ML model drift | Medium | Medium | Weekly retraining, PSI monitoring (module implemented; schedule external) |
| Threshold misconfiguration | Medium | High | Replay testing, gradual rollout |
| Attack pattern evolution | High | Medium | Champion/challenger experiments |
| Integration delays | Medium | Medium | Shadow mode allows parallel testing |

---

## Executive Recommendation

**Proceed with Phase 2 deployment** based on:

1. Phase 1 MVP meets latency SLA in a local baseline test (106ms P99 vs 200ms target)
2. Load testing measured 260 RPS on a single worker; higher capacity is projected, not measured
3. Rule-based detection provides immediate value while ML matures
4. Evidence capture infrastructure enables dispute win rate improvement
5. Hot-reload policy allows business-led threshold tuning

**Next Actions:**
1. Shadow deployment to production traffic (week 1)
2. Run ML training pipeline with labeled historical data (weeks 1-2)
3. Enable champion/challenger routing in shadow mode (weeks 2-3)
4. Gradual traffic experiment with ML scoring (default 80/15/5 split)

---

*This document is intended for VP/Director-level stakeholders. For technical details, see the full design documentation.*
