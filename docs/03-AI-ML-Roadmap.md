# AI/ML Roadmap & Current Status

**Author:** Uday Tamma | **Document Version:** 1.0 | **Date:** January 2026

---

## Current Implementation Status

### Phase 1: Rule-Driven Detection (COMPLETE)

The MVP implementation uses a **rule-based detection engine** with hooks for ML integration. This was a deliberate design choice to:

1. **Deliver value faster** - Rules can be tuned immediately without training data
2. **Ensure interpretability** - Every decision has explainable reasons
3. **Establish infrastructure** - Feature pipeline, evidence capture, and policy engine ready for ML

#### What's Implemented

| Component | Status | Description |
|-----------|--------|-------------|
| **Feature Engine** | Complete | Redis velocity counters with sliding windows |
| **Detection Engine** | Complete | 5 detector types (card testing, velocity, geo, bot, friendly) |
| **Risk Scoring** | Complete | Rule-based combination of detector signals |
| **ML Scoring** | Implemented (gated) | XGBoost/LightGBM scoring with champion/challenger routing when enabled |
| **Policy Engine** | Complete | YAML configuration with hot-reload |
| **Evidence Vault** | Complete | Immutable storage with feature snapshots |
| **Metrics Pipeline** | Complete | Prometheus metrics for requests/latency/decisions; model latency/version metrics emitted when ML enabled |
| **Load Testing** | Complete | Measured 260 RPS at 106ms P99 (single worker; projections are modeled, not measured) |

#### Detection Logic (Current)

```python
# Simplified scoring formula (rule-based, current MVP)
criminal_score = min(1.0, max(
    card_testing.score * 1.0,
    velocity.score * 0.9,
    geo_anomaly.score * 0.7,
    bot_detection.score * 1.0,
))

friendly_score = max(friendly_fraud.score, subscription_abuse.score)
risk_score = max(criminal_score, friendly_score)

# Confidence dampening for low-confidence cases
if confidence < 0.5:
    risk_score = 0.3 + (risk_score - 0.3) * confidence * 2

# Policy thresholds are evaluated from config/policy.yaml
decision = policy_engine.evaluate(event, features, scores)
```

---

## Phase 2: Hybrid ML + Rules

Phase 2 is implemented in-process and gated by `ML_ENABLED`. When disabled, the system runs rule-only scoring.

### ML Model Specification

#### Criminal Fraud Model

| Attribute | Specification |
|-----------|---------------|
| **Algorithm** | XGBoost (primary), LightGBM (challenger) |
| **Objective** | Binary classification (is_criminal_fraud) |
| **Training Window** | Configurable window (default 90d; current model trained on 365d for broader coverage) ending at label-maturity cutoff (default T-120d) |
| **Retraining Frequency** | Weekly (automated pipeline) |
| **Feature Count** | 28 features (see feature list below) |
| **Target AUC** | >0.85 (measured: XGBoost 0.909, LightGBM 0.913 on 5-fold CV with synthetic data) |
| **Latency Budget** | <25ms P99 |

#### Feature List

**Velocity Features (Real-time from Redis):**
| Feature | Description | Window |
|---------|-------------|--------|
| card_attempts_10m | Transaction attempts on card | 10 min |
| card_attempts_1h | Transaction attempts on card | 1 hour |
| card_attempts_24h | Transaction attempts on card | 24 hours |
| device_distinct_cards_1h | Unique cards on device | 1 hour |
| device_distinct_cards_24h | Unique cards on device | 24 hours |
| ip_distinct_cards_1h | Unique cards from IP | 1 hour |
| user_amount_24h_cents | Total spend by user (cents) | 24 hours |
| card_decline_rate_1h | Decline rate for card | 1 hour |

**Entity Features (From profiles):**
| Feature | Description | Source |
|---------|-------------|--------|
| card_age_hours | Time since card first seen | Redis |
| device_age_hours | Time since device first seen | Redis |
| user_account_age_days | Account creation age | Profile |
| user_chargeback_count_lifetime | Historical chargebacks | Profile |
| user_chargeback_rate_90d | Recent chargeback rate | Profile |
| user_refund_count_90d | Recent refunds | Profile |
| card_distinct_devices_30d | Devices using this card | Redis |
| card_distinct_users_30d | Users using this card | Redis |

**Transaction Features (From event):**
| Feature | Description | Computation |
|---------|-------------|-------------|
| amount_usd | Transaction amount | Direct |
| amount_zscore | Amount vs user average | (amount - avg) / std |
| is_new_card_for_user | First time card used | Boolean |
| is_new_device_for_user | First time device used | Boolean |
| hour_of_day | Local hour (device timezone if provided; UTC fallback) | Timezone adjusted |
| is_weekend | Weekend flag | Boolean |

**Device/Network Features:**
| Feature | Description | Source |
|---------|-------------|--------|
| is_emulator | Device is emulated | Fingerprint |
| is_rooted | Device is rooted/jailbroken | Fingerprint |
| is_datacenter_ip | IP from cloud provider | IP intelligence |
| is_vpn | VPN detected | IP intelligence |
| is_tor | Tor exit node | IP intelligence |
| ip_risk_score | Derived IP risk score (or external score when available) | IP intelligence flags |

#### Label Source

```
Label Definition:
  is_criminal_fraud = TRUE if:
    - Chargeback received with reason code in [10.1, 10.2, 10.3, 10.4, 10.5]
    - OR chargeback fraud_type = CRIMINAL
    - (Planned) TC40/SAFE issuer alert received
    - (Planned) manual review classified as fraud

  Label Maturity: 120 days from transaction
    - Reason: Chargebacks can arrive up to 120 days post-transaction
    - Consequence: Training data is always 4 months behind
```

#### Retraining Strategy

```
Weekly Pipeline (Automated):
1. Extract transactions from a 90-day window ending at the maturity cutoff (default T-120d)
2. Join with chargeback outcomes
3. Retrieve point-in-time features from evidence vault
4. Train new model version
5. Validate against holdout (last 7 days of the window)
6. If AUC >= min threshold (default 0.85): Register as challenger with success log
7. If AUC < threshold (champion only): Register with warning log -- system requires a champion model to function; skipping would break scoring

**Design rationale:** The fraud detection API must always have a callable model. Blocking champion registration on low AUC would leave the system without a scorer. Instead, below-threshold champions are registered with a warning, and the operations team investigates via the monitoring pipeline. The challenger path correctly enforces the minimum AUC gate.

Monthly Review (Manual):
1. Compare champion vs challenger performance
2. Analyze feature importance drift
3. Review false positive cases
4. Decide: promote challenger or retrain with adjustments
```

Implementation note: the pipeline is implemented in `scripts/train_model.py` and can be scheduled externally.

### Champion/Challenger Framework

#### Experiment Architecture

```
Traffic Routing:
┌─────────────────────────────────────────────────────┐
│                   Load Balancer                      │
└─────────────────────────┬───────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
   ┌─────────┐       ┌─────────┐       ┌─────────┐
   │Champion │       │Challenger│       │ Holdout │
   │  (80%)  │       │  (15%)  │       │  (5%)   │
   │ Model A │       │ Model B │       │Rules Only│
   └─────────┘       └─────────┘       └─────────┘

Routing: Deterministic hash on idempotency_key (reproducible)
```

#### Experiment Metrics

| Metric | Champion | Challenger | Threshold |
|--------|----------|------------|-----------|
| Approval Rate | 91.2% | Must be within 1% | -1% to +2% |
| Fraud Rate (30d lag) | 1.15% | Must improve | <1.15% |
| P99 Latency | 106ms | Must be within 20% | <127ms |
| False Positive Rate | 12% | Must improve | <12% |

#### Promotion Criteria

```
Promote Challenger if ALL true:
  1. Running for >= 14 days
  2. Sample size >= 100,000 transactions
  3. Fraud rate improved by >= 5% (statistically significant)
  4. Approval rate within 1% of champion
  5. No latency degradation
  6. No anomalies in score distribution

Rollback Challenger if ANY true:
  1. Fraud rate increased by > 10%
  2. Approval rate dropped by > 3%
  3. P99 latency exceeded 150ms
  4. Error rate exceeded 0.5%
```

### Replay Framework

Status: Implemented (see `src/ml/replay.py` and `scripts/replay_analysis.py`).

#### Purpose

Historical replay enables:
1. **Threshold simulation** - Test new thresholds on historical data
2. **Model validation** - Compare model predictions to known outcomes
3. **Policy change estimation** - Quantify impact before deployment

#### Implementation

Replay tooling reads point-in-time feature snapshots from `transaction_evidence`
and rescoring is performed with a supplied model + threshold. The CLI wrapper
returns deltas for approval rate, fraud caught, and false positives.

```
python scripts/replay_analysis.py \\
  --start 2025-09-01 --end 2025-10-01 \\
  --model-path models/xgb-20260101.json --model-type xgb_classifier \\
  --threshold 0.7
```

#### Simulation Use Cases

| Use Case | Input | Output |
|----------|-------|--------|
| Threshold change | New threshold values | Approval rate delta, fraud caught delta |
| Model comparison | Model version A vs B | AUC difference, FP rate difference |
| Rule addition | New rule definition | Transactions affected, score changes |
| Seasonal analysis | Date range comparison | Pattern differences by period |

---

## Drift Detection (Implemented)

Drift detection is implemented via **Population Stability Index (PSI)** in `src/ml/drift.py`.
The module compares a training baseline window to a current window and flags features with
`PSI > 0.2` as significant drift.

Typical usage pattern:
- Baseline: training window used for champion model
- Current: most recent 7 days of traffic
- Output: per-feature PSI scores + list of drifted features

---

## Model Monitoring (Implemented)

The ML monitoring helper in `src/ml/monitoring.py` tracks:
- **Per-variant decision rates** (champion/challenger/holdout/rules-only)
- **Fallback rate** (ML unavailable → rules-only)
- **Fraud + approval rates per variant** (fraud rate lags by chargeback arrival)

Metrics are exported via Prometheus (see README metrics list).

---

## Retraining Automation (Implemented)

`scripts/retrain.sh` wraps `scripts/train_model.py` and enforces a minimum AUC
before registering a challenger. This supports weekly cron execution without
hand-editing the pipeline.

---

## Phase 3: Advanced ML (Future)

### Planned Enhancements

| Enhancement | Timeline | Description |
|-------------|----------|-------------|
| **Graph Neural Network** | Phase 3 | Detect fraud rings via card-device-user connections |
| **Sequence Model** | Phase 3 | LSTM/Transformer for transaction sequence patterns |
| **Anomaly Detection** | Phase 3 | Isolation Forest for unknown attack patterns |
| **Real-time Retraining** | Phase 3 | Online learning for rapid adaptation |
| **External Signals** | Phase 3 | BIN intelligence, consortium data, device reputation |

### Graph-Based Fraud Ring Detection

```
Entity Graph:
  Nodes: Cards, Devices, Users, IPs
  Edges: Transaction relationships

Fraud Ring Indicators:
  - Cluster of cards sharing devices
  - Star pattern (one device, many cards)
  - Circular payments between accounts
  - Velocity spikes in connected subgraph

Implementation:
  - Neo4j for graph storage
  - Graph embedding for ML features
  - Community detection for ring identification
```

---

## Architecture for ML Integration

### Current Architecture (ML-Ready)

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                             │
│                      (FastAPI)                               │
└────────────────────────────┬────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│Feature Engine │    │   Detection   │    │ Policy Engine │
│   (Redis)     │    │    Engine     │    │   (YAML)      │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                    │                    │
        │            ┌───────┴───────┐            │
        │            │   Currently   │            │
        │            │  Rule-Based   │            │
        │            │               │            │
        │            │  [ML HOOK]    │◄───────────┘
        │            │   Phase 2     │
        │            └───────────────┘
        │
        ▼
┌───────────────┐
│Evidence Vault │
│(Feature Store)│
└───────────────┘
```

### Phase 2 Architecture (With ML)

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                             │
└────────────────────────────┬────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│Feature Engine │    │   Scoring     │    │ Policy Engine │
│   (Redis)     │    │   Service     │    │   (YAML)      │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                    │                    │
        │         ┌──────────┼──────────┐        │
        │         ▼          ▼          ▼        │
        │    ┌────────┐ ┌────────┐ ┌────────┐   │
        │    │  Rule  │ │   ML   │ │Ensemble│   │
        │    │ Engine │ │ Model  │ │  Layer │◄──┘
        │    └────────┘ └────────┘ └────────┘
        │                    │
        │         ┌──────────┴──────────┐
        │         ▼                     ▼
        │    ┌────────┐           ┌────────┐
        │    │Champion│           │Challngr│
        │    │ Model  │           │ Model  │
        │    └────────┘           └────────┘
        │
        ▼
┌───────────────┐
│Evidence Vault │
│+ ML Features  │
└───────────────┘
```

### Ensemble Scoring

> **Note:** This pseudocode shows the conceptual Phase 2 ensemble design. The current implementation uses `RiskScorer.compute_scores()` in `src/scoring/risk_scorer.py`, which applies a simpler weighted-max approach. The ensemble architecture below represents the target design when ML scoring is fully promoted.

```python
class EnsembleScoringService:
    """Combine rule-based and ML scores."""

    def score(self, features: dict) -> RiskScore:
        # Rule-based score (always runs)
        rule_score = self.rule_engine.score(features)

        # ML score (Phase 2+)
        if self.ml_enabled:
            ml_score = self.ml_model.predict(features)
        else:
            ml_score = None

        # Ensemble combination
        if ml_score is not None:
            # Weighted average with rules as safety net
            combined = (
                ml_score * 0.70 +           # ML carries more weight
                rule_score * 0.30           # Rules as backstop
            )

            # Hard overrides (rules always win for certain signals)
            if features.get("is_emulator"):
                combined = max(combined, 0.95)
            if features.get("blocklist_match"):
                combined = 1.0
        else:
            combined = rule_score

        return RiskScore(
            combined=combined,
            rule_score=rule_score,
            ml_score=ml_score,
            model_version=self.model_version
        )
```

---

## Timeline Summary

| Phase | Scope | Status | Timeline |
|-------|-------|--------|----------|
| **Phase 1** | Rule-based MVP | Complete | Done |
| **Phase 2a** | ML model training | Implemented (manual run) | Weeks 1-2 |
| **Phase 2b** | Champion/challenger | Implemented (routing + registry) | Weeks 2-3 |
| **Phase 2c** | ML in production | Implemented (gated by `ml_enabled`) | Week 4+ |
| **Phase 2d** | Replay + drift + monitoring | Implemented (tooling + metrics) | Ongoing |
| **Phase 3** | Advanced ML | Future | TBD |

---

*This document consolidates the AI/ML strategy with explicit current status, including what is implemented and what remains planned (automated scheduling/cron).* 
