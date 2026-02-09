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
| **Policy Engine** | Complete | YAML configuration with hot-reload |
| **Evidence Vault** | Complete | Immutable storage with feature snapshots |
| **Metrics Pipeline** | Complete | Prometheus metrics for all components |
| **Load Testing** | Complete | Measured 260 RPS at 106ms P99 (single worker; projected to 1000+ with horizontal scaling) |

#### Detection Logic (Current)

```python
# Simplified scoring formula (rule-based)
criminal_score = max(
    card_testing.confidence * 0.9,    # Card testing patterns
    velocity.confidence * 0.8,         # Velocity rule triggers
    geo_anomaly.confidence * 0.7,     # Geographic issues
    bot_detection.confidence * 0.95   # Automation signals
)

friendly_score = friendly_fraud.confidence * 0.6

# Policy thresholds (configurable)
if criminal_score >= 0.85 or friendly_score >= 0.95:
    return BLOCK
elif criminal_score >= 0.60 or friendly_score >= 0.70:
    return FRICTION
elif criminal_score >= 0.40 or friendly_score >= 0.50:
    return REVIEW
else:
    return ALLOW
```

---

## Phase 2: Hybrid ML + Rules

### ML Model Specification

#### Criminal Fraud Model

| Attribute | Specification |
|-----------|---------------|
| **Algorithm** | XGBoost (primary), LightGBM (challenger) |
| **Objective** | Binary classification (is_criminal_fraud) |
| **Training Window** | 90 days of transactions with 120-day label maturity |
| **Retraining Frequency** | Weekly (automated pipeline) |
| **Feature Count** | 25+ features |
| **Target AUC** | >0.85 |
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
| user_total_amount_24h | Total spend by user | 24 hours |
| card_decline_rate_1h | Decline rate for card | 1 hour |

**Entity Features (From profiles):**
| Feature | Description | Source |
|---------|-------------|--------|
| card_age_hours | Time since card first seen | Redis |
| device_age_hours | Time since device first seen | Redis |
| user_account_age_days | Account creation age | Profile |
| user_chargeback_count_lifetime | Historical chargebacks | Profile |
| user_chargeback_rate_90d | Recent chargeback rate | Profile |
| card_distinct_devices_30d | Devices using this card | Redis |
| card_distinct_users_30d | Users using this card | Redis |

**Transaction Features (From event):**
| Feature | Description | Computation |
|---------|-------------|-------------|
| amount_usd | Transaction amount | Direct |
| amount_zscore | Amount vs user average | (amount - avg) / std |
| is_new_card_for_user | First time card used | Boolean |
| is_new_device_for_user | First time device used | Boolean |
| hour_of_day | Local time hour | Timezone adjusted |
| is_weekend | Weekend flag | Boolean |

**Device/Network Features:**
| Feature | Description | Source |
|---------|-------------|--------|
| is_emulator | Device is emulated | Fingerprint |
| is_rooted | Device is rooted/jailbroken | Fingerprint |
| is_datacenter_ip | IP from cloud provider | IP intelligence |
| is_vpn | VPN detected | IP intelligence |
| is_tor | Tor exit node | IP intelligence |
| ip_risk_score | Third-party IP score | External API |

#### Label Source

```
Label Definition:
  is_criminal_fraud = TRUE if:
    - Chargeback received with reason code in [10.1, 10.2, 10.3, 10.4, 10.5]
    - OR TC40/SAFE issuer alert received
    - OR manual review classified as fraud

  Label Maturity: 120 days from transaction
    - Reason: Chargebacks can arrive up to 120 days post-transaction
    - Consequence: Training data is always 4 months behind
```

#### Retraining Strategy

```
Weekly Pipeline (Automated):
1. Extract transactions from T-120d to T-30d
2. Join with chargeback outcomes
3. Retrieve point-in-time features from evidence vault
4. Train new model version
5. Validate against holdout (last 7 days)
6. If AUC drop < 2%: Register as challenger
7. If AUC drop >= 2%: Alert DS team, use previous model

Monthly Review (Manual):
1. Compare champion vs challenger performance
2. Analyze feature importance drift
3. Review false positive cases
4. Decide: promote challenger or retrain with adjustments
```

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

Routing: Deterministic hash on auth_id (reproducible)
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

#### Purpose

Historical replay enables:
1. **Threshold simulation** - Test new thresholds on historical data
2. **Model validation** - Compare model predictions to known outcomes
3. **Policy change estimation** - Quantify impact before deployment

#### Implementation

```python
async def replay(
    start_date: datetime,
    end_date: datetime,
    policy_config: Optional[dict] = None,
    model_version: Optional[str] = None
) -> ReplayResults:
    """
    Replay historical transactions with optional config changes.

    Key: Uses point-in-time features from evidence vault,
    NOT current features (which would cause look-ahead bias).
    """

    for transaction in get_historical_transactions(start_date, end_date):
        # Get features AS THEY WERE at transaction time
        features = get_features_at_time(
            transaction.auth_id,
            transaction.timestamp
        )

        # Score with specified model/policy
        new_decision = score_and_decide(
            transaction,
            features,
            model_version,
            policy_config
        )

        # Compare to actual outcome
        actual_fraud = was_transaction_fraud(transaction.auth_id)

        # Record for analysis
        results.append({
            "original_decision": transaction.original_decision,
            "new_decision": new_decision,
            "actual_fraud": actual_fraud
        })

    return analyze_results(results)
```

#### Simulation Use Cases

| Use Case | Input | Output |
|----------|-------|--------|
| Threshold change | New threshold values | Approval rate delta, fraud caught delta |
| Model comparison | Model version A vs B | AUC difference, FP rate difference |
| Rule addition | New rule definition | Transactions affected, score changes |
| Seasonal analysis | Date range comparison | Pattern differences by period |

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
| **Phase 2a** | ML model training | Not started | Weeks 1-2 |
| **Phase 2b** | Champion/challenger | Not started | Weeks 2-3 |
| **Phase 2c** | ML in production | Not started | Week 4+ |
| **Phase 3** | Advanced ML | Future | TBD |

---

## Interview Application

**When asked "What's the AI/ML roadmap?":**

> "The current implementation is rule-based by design - we prioritized getting to market fast with interpretable decisions. But the architecture is ML-ready: features are captured in the evidence vault, the scoring service has a clean interface for model integration, and we have the replay framework for validation.
>
> Phase 2 introduces a simple ML model - XGBoost for criminal fraud - using 25+ features from velocity counters and entity profiles. Labels come from chargebacks with a 120-day maturity window. We'll deploy via champion/challenger: 80% to the proven rules, 15% to the ML challenger, 5% holdout.
>
> Key to success is the ensemble approach: ML informs, but rules have hard overrides for signals like emulators or blocklist matches. This keeps the system interpretable for compliance while improving detection accuracy.
>
> Retraining is weekly and automated, but promotion requires 14 days of data and statistically significant improvement before we graduate a challenger to champion."

---

*This document consolidates the AI/ML strategy with explicit current status, avoiding the impression that ML is already deployed when it's planned for Phase 2.*
